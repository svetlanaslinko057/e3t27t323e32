"""
Sprint 9 — Investor Statements (PDF).

Виписки інвестора у форматі PDF: Monthly / Quarterly / Annual.
Джерела даних (наживо, без збережених агрегатів):
    lumen_ledger_entries  — рух коштів за період
    lumen_ownerships      — холдинги (станом на кінець періоду)
    lumen_payout_records  — деталізація нарахувань
    lumen_withdrawal_requests — виводи
Рендеринг: reportlab + Liberation Sans (кирилиця).
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from lumen_api import db, get_current_user, require_admin, _now, _iso
from lumen_payments import _round2, BASE_CURRENCY

logger = logging.getLogger("lumen.statements")

router = APIRouter(prefix="/api", tags=["lumen-statements"])

_FONT_REGULAR = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
_FONT_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
_FONTS_READY = False

MONTH_NOM = ["", "Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень",
             "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень"]

STATEMENT_TYPES = ["monthly", "quarterly", "annual"]
STATEMENT_TYPE_LABELS = {"monthly": "Місячна", "quarterly": "Квартальна", "annual": "Річна"}


def _ensure_fonts() -> None:
    global _FONTS_READY
    if _FONTS_READY:
        return
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    pdfmetrics.registerFont(TTFont("LumenSans", _FONT_REGULAR))
    pdfmetrics.registerFont(TTFont("LumenSans-Bold", _FONT_BOLD))
    _FONTS_READY = True


def _aware(dt: Any) -> Optional[datetime]:
    if not isinstance(dt, datetime):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _fmt_uah(x: float) -> str:
    # Display layer: amounts are stored in UAH internally; users see USD.
    from shared.money import fmt_uah_as_usd
    return fmt_uah_as_usd(x, decimals=2)


def _fmt_date(dt: Optional[datetime]) -> str:
    d = _aware(dt)
    return d.strftime("%d.%m.%Y") if d else "—"


# ──────────────────────────────────────────────────────────────────────────────
# Period maths
# ──────────────────────────────────────────────────────────────────────────────

def _period_bounds(ptype: str, pkey: str) -> tuple[datetime, datetime, str]:
    try:
        if ptype == "monthly":
            y, m = pkey.split("-")
            y, m = int(y), int(m)
            start = datetime(y, m, 1, tzinfo=timezone.utc)
            end = datetime(y + (m // 12), (m % 12) + 1, 1, tzinfo=timezone.utc)
            return start, end, f"{MONTH_NOM[m]} {y}"
        if ptype == "quarterly":
            y, q = pkey.split("-Q")
            y, q = int(y), int(q)
            sm = (q - 1) * 3 + 1
            start = datetime(y, sm, 1, tzinfo=timezone.utc)
            em = sm + 3
            end = datetime(y + (1 if em > 12 else 0), (em - 12) if em > 12 else em, 1, tzinfo=timezone.utc)
            return start, end, f"{q}-й квартал {y}"
        if ptype == "annual":
            y = int(pkey)
            return (datetime(y, 1, 1, tzinfo=timezone.utc),
                    datetime(y + 1, 1, 1, tzinfo=timezone.utc), f"{y} рік")
    except Exception:
        pass
    raise HTTPException(status_code=400, detail="Невірний період")


async def _activity_dates(iid: str) -> list[datetime]:
    dates: list[datetime] = []
    async for e in db.lumen_ledger_entries.find({"investor_id": iid}, {"created_at": 1}):
        d = _aware(e.get("created_at"))
        if d:
            dates.append(d)
    async for o in db.lumen_ownerships.find({"investor_id": iid}, {"created_at": 1}):
        d = _aware(o.get("created_at"))
        if d:
            dates.append(d)
    return dates


async def _list_periods(iid: str) -> dict:
    dates = await _activity_dates(iid)
    if not dates:
        return {"monthly": [], "quarterly": [], "annual": []}
    earliest = min(dates)
    now = _now()
    active_months = {(d.year, d.month) for d in dates}
    active_quarters = {(d.year, (d.month - 1) // 3 + 1) for d in dates}
    active_years = {d.year for d in dates}

    monthly, quarterly, annual = [], [], []
    # Monthly (cap 24)
    y, m = earliest.year, earliest.month
    while (y, m) <= (now.year, now.month) and len(monthly) < 24:
        s, e, label = _period_bounds("monthly", f"{y}-{m:02d}")
        monthly.append({"type": "monthly", "key": f"{y}-{m:02d}", "label": label,
                        "period_start": _iso(s), "period_end": _iso(e),
                        "has_activity": (y, m) in active_months})
        m += 1
        if m > 12:
            m = 1
            y += 1
    # Quarterly (cap 12)
    qy, qq = earliest.year, (earliest.month - 1) // 3 + 1
    nowq = (now.month - 1) // 3 + 1
    while (qy, qq) <= (now.year, nowq) and len(quarterly) < 12:
        s, e, label = _period_bounds("quarterly", f"{qy}-Q{qq}")
        quarterly.append({"type": "quarterly", "key": f"{qy}-Q{qq}", "label": label,
                          "period_start": _iso(s), "period_end": _iso(e),
                          "has_activity": (qy, qq) in active_quarters})
        qq += 1
        if qq > 4:
            qq = 1
            qy += 1
    # Annual (cap 6)
    ay = earliest.year
    while ay <= now.year and len(annual) < 6:
        s, e, label = _period_bounds("annual", str(ay))
        annual.append({"type": "annual", "key": str(ay), "label": label,
                       "period_start": _iso(s), "period_end": _iso(e),
                       "has_activity": ay in active_years})
        ay += 1

    monthly.reverse(); quarterly.reverse(); annual.reverse()
    return {"monthly": monthly, "quarterly": quarterly, "annual": annual}


# ──────────────────────────────────────────────────────────────────────────────
# Gather statement data (Ledger + Ownership + Payouts + Withdrawals)
# ──────────────────────────────────────────────────────────────────────────────

async def _gather(iid: str, start: datetime, end: datetime) -> dict:
    assets = {}
    async for a in db.lumen_assets.find({}, {"id": 1, "title": 1}):
        assets[a.get("id")] = a.get("title")

    # Holdings snapshot (current ownership)
    holdings = []
    invested_total = 0.0
    async for o in db.lumen_ownerships.find({"investor_id": iid}):
        u = float(o.get("units") or 0)
        if u <= 0:
            continue
        invested_total += u
        holdings.append({
            "asset_title": assets.get(o.get("asset_id")) or o.get("asset_id"),
            "invested": _round2(u),
            "share_percent": _round2(float(o.get("ownership_percent") or 0)),
        })
    holdings.sort(key=lambda x: -x["invested"])

    # Movements within [start, end)
    movements = []
    received = funded = withdrawn = 0.0
    async for e in db.lumen_ledger_entries.find({"investor_id": iid}):
        d = _aware(e.get("created_at"))
        if not d or not (start <= d < end):
            continue
        et, reason = e.get("entry_type"), e.get("reason")
        amt = float(e.get("amount_uah") or 0)
        if et == "credit" and reason == "payout":
            received += amt
            kind = "Виплата доходу"
        elif et == "credit" and reason == "investment_funding":
            funded += amt
            kind = "Фінансування інвестиції"
        elif et == "debit" and reason == "withdrawal":
            withdrawn += amt
            kind = "Вивід коштів"
        else:
            kind = e.get("reason") or "Операція"
        movements.append({
            "date": d, "kind": kind,
            "asset_title": assets.get(e.get("asset_id")) or "—",
            "direction": et, "amount": _round2(amt),
        })
    movements.sort(key=lambda x: x["date"])

    # Withdrawals submitted in period (registry detail)
    withdrawals = []
    async for w in db.lumen_withdrawal_requests.find({"investor_id": iid}):
        d = _aware(w.get("created_at"))
        if d and start <= d < end:
            withdrawals.append({
                "date": d, "amount": _round2(float(w.get("amount_uah") or w.get("amount") or 0)),
                "status": w.get("status_label") or w.get("status"),
            })

    wallet = await db.lumen_wallets.find_one({"investor_id": iid}) or {}

    return {
        "holdings": holdings,
        "invested_total": _round2(invested_total),
        "movements": movements,
        "withdrawals": withdrawals,
        "received": _round2(received),
        "funded": _round2(funded),
        "withdrawn": _round2(withdrawn),
        "net": _round2(received + funded - withdrawn),
        "wallet_available": _round2(float(wallet.get("available_balance") or 0)),
    }


# ──────────────────────────────────────────────────────────────────────────────
# PDF render
# ──────────────────────────────────────────────────────────────────────────────

def _render_pdf(*, identity: dict, ptype: str, label: str,
                start: datetime, end: datetime, data: dict) -> bytes:
    _ensure_fonts()
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, HRFlowable)

    teal = colors.HexColor("#2E5D4F")
    gold = colors.HexColor("#B8893B")
    muted = colors.HexColor("#6b7280")

    h1 = ParagraphStyle("h1", fontName="LumenSans-Bold", fontSize=18, textColor=teal, leading=22)
    h2 = ParagraphStyle("h2", fontName="LumenSans-Bold", fontSize=12, textColor=teal, leading=16, spaceBefore=10, spaceAfter=4)
    normal = ParagraphStyle("n", fontName="LumenSans", fontSize=9.5, leading=14)
    small = ParagraphStyle("s", fontName="LumenSans", fontSize=8.5, textColor=muted, leading=12)
    right = ParagraphStyle("r", fontName="LumenSans", fontSize=9.5, leading=14, alignment=2)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"Lumen — {STATEMENT_TYPE_LABELS.get(ptype)} виписка {label}")
    story = []
    story.append(Paragraph("LUMEN", h1))
    story.append(Paragraph(f"{STATEMENT_TYPE_LABELS.get(ptype, '')} виписка інвестора · {label}", normal))
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=1.1, color=gold))
    story.append(Spacer(1, 6))

    meta = [
        [Paragraph("Інвестор", small), Paragraph(identity.get("name") or "—", normal)],
        [Paragraph("Email", small), Paragraph(identity.get("email") or "—", normal)],
        [Paragraph("Період", small), Paragraph(f"{_fmt_date(start)} — {_fmt_date(end - __import__('datetime').timedelta(days=1))}", normal)],
        [Paragraph("Сформовано", small), Paragraph(_fmt_date(_now()), normal)],
    ]
    mt = Table(meta, colWidths=[35 * mm, None])
    mt.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    story.append(mt)

    # Summary
    story.append(Paragraph("Підсумок за період", h2))
    sm = [
        [Paragraph("Отримано доходу", small), Paragraph(_fmt_uah(data["received"]), right)],
        [Paragraph("Профінансовано інвестицій", small), Paragraph(_fmt_uah(data["funded"]), right)],
        [Paragraph("Виведено коштів", small), Paragraph(_fmt_uah(data["withdrawn"]), right)],
        [Paragraph("Чистий рух", small), Paragraph(_fmt_uah(data["net"]), right)],
    ]
    st = Table(sm, colWidths=[None, 50 * mm])
    st.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#e5e7eb")),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("FONTNAME", (0, 3), (-1, 3), "LumenSans-Bold"),
    ]))
    story.append(st)

    # Holdings
    story.append(Paragraph("Холдинги (станом на кінець періоду)", h2))
    if data["holdings"]:
        rows = [[Paragraph("Актив", small), Paragraph("Вкладено", small), Paragraph("Частка", small)]]
        for h in data["holdings"]:
            rows.append([Paragraph(h["asset_title"], normal),
                         Paragraph(_fmt_uah(h["invested"]), right),
                         Paragraph(f"{h['share_percent']:.2f}%", right)])
        rows.append([Paragraph("Разом інвестовано", small),
                     Paragraph(_fmt_uah(data["invested_total"]), right), Paragraph("", normal)])
        ht = Table(rows, colWidths=[None, 40 * mm, 25 * mm])
        ht.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, teal),
            ("LINEBELOW", (0, 1), (-1, -2), 0.3, colors.HexColor("#eef0f2")),
            ("FONTNAME", (0, -1), (-1, -1), "LumenSans-Bold"),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(ht)
    else:
        story.append(Paragraph("Немає активних холдингів.", small))

    # Movements
    story.append(Paragraph("Рух коштів за період", h2))
    if data["movements"]:
        rows = [[Paragraph("Дата", small), Paragraph("Операція", small),
                 Paragraph("Актив", small), Paragraph("Сума", small)]]
        for mv in data["movements"]:
            sign = "+" if mv["direction"] == "credit" else "−"
            rows.append([Paragraph(_fmt_date(mv["date"]), normal),
                         Paragraph(mv["kind"], normal),
                         Paragraph(mv["asset_title"], normal),
                         Paragraph(f"{sign} {_fmt_uah(mv['amount'])}", right)])
        mvt = Table(rows, colWidths=[22 * mm, None, 45 * mm, 35 * mm])
        mvt.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, teal),
            ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#eef0f2")),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(mvt)
    else:
        story.append(Paragraph("За цей період рухів коштів не було.", small))

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#e5e7eb")))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"Доступний баланс гаманця на дату формування: {_fmt_uah(data['wallet_available'])}", small))
    story.append(Paragraph(
        "Документ сформовано автоматично платформою Lumen на основі реєстру операцій (ledger). "
        "Носить інформаційний характер.", small))

    doc.build(story)
    return buf.getvalue()


async def _identity(iid: str) -> dict:
    u = await db.users.find_one({"user_id": iid}) or await db.users.find_one({"id": iid})
    if not u:
        return {"name": None, "email": None}
    return {"name": u.get("name") or u.get("full_name"), "email": u.get("email")}


async def _build_response(iid: str, ptype: str, pkey: str) -> Response:
    if ptype not in STATEMENT_TYPES:
        raise HTTPException(status_code=400, detail="Невідомий тип виписки")
    start, end, label = _period_bounds(ptype, pkey)
    identity = await _identity(iid)
    data = await _gather(iid, start, end)
    pdf = _render_pdf(identity=identity, ptype=ptype, label=label, start=start, end=end, data=data)
    safe = f"lumen-statement-{ptype}-{pkey}.pdf".replace(" ", "_")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{safe}"'})


# ──────────────────────────────────────────────────────────────────────────────
# Routes — investor
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/investor/statements")
async def investor_statements(user=Depends(get_current_user)):
    periods = await _list_periods(user["id"])
    return {"types": [{"key": t, "label": STATEMENT_TYPE_LABELS[t]} for t in STATEMENT_TYPES],
            "periods": periods}


@router.get("/investor/statements/{ptype}/{pkey}/pdf")
async def investor_statement_pdf(ptype: str, pkey: str, user=Depends(get_current_user)):
    return await _build_response(user["id"], ptype, pkey)


# ──────────────────────────────────────────────────────────────────────────────
# Routes — admin (any investor)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/admin/investors/{investor_id}/statements")
async def admin_investor_statements(investor_id: str, _=Depends(require_admin)):
    periods = await _list_periods(investor_id)
    return {"investor_id": investor_id,
            "types": [{"key": t, "label": STATEMENT_TYPE_LABELS[t]} for t in STATEMENT_TYPES],
            "periods": periods}


@router.get("/admin/investors/{investor_id}/statements/{ptype}/{pkey}/pdf")
async def admin_investor_statement_pdf(investor_id: str, ptype: str, pkey: str, _=Depends(require_admin)):
    return await _build_response(investor_id, ptype, pkey)


__all__ = ["router"]
