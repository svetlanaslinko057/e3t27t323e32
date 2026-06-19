"""
LUMEN 2.0 — Phase G12 — Reporting OS (PDF mandatory)
=====================================================

Derived institutional reports for assets, quarters and funds.

Report kinds
------------
  asset_factsheet : single-asset factsheet — NAV, yield, occupancy,
                    investors, operator, capital stack
  quarterly       : platform / portfolio quarterly snapshot (KPIs)
  fund_report     : per-fund report — NAV, holdings, top assets, LP count

All PDFs are generated on demand with reportlab. Reports are persisted as
metadata in `lumen_reports` (no binary cache — re-rendered every download)
so the library is queryable + auditable.

Endpoints (prefix /api)
-----------------------
Admin
    POST   /admin/reports/generate    {kind, entity_id?, period?}
    GET    /admin/reports              ?kind=...
    GET    /admin/reports/{report_id}
    DELETE /admin/reports/{report_id}
Investor
    GET    /reports                    — reports relevant to me (my
                                          assets + funds + global quarterly)
    GET    /reports/{report_id}
    GET    /reports/{report_id}/pdf    — stream PDF
"""
from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, PageBreak)

from lumen_api import db, get_current_user, require_admin, _strip_mongo, _now, _iso

logger = logging.getLogger("lumen.reporting_os")
router = APIRouter(prefix="/api", tags=["lumen-reporting-os"])

KINDS = ("asset_factsheet", "quarterly", "fund_report")
KIND_LABELS_UK = {
    "asset_factsheet": "Факт-лист активу",
    "quarterly": "Квартальний звіт",
    "fund_report": "Звіт фонду",
}

PRIMARY = colors.HexColor("#2E5D4F")
MUTED = colors.HexColor("#6B7280")
LINE = colors.HexColor("#E5E7EB")

# ────────────────────────────────────────────────────────────────────────────
# Font setup — try to register DejaVu (UTF-8 safe). Fallback to Helvetica.
# ────────────────────────────────────────────────────────────────────────────
_FONT = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"
try:
    import os as _os
    for _p in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    ):
        if _os.path.exists(_p):
            pdfmetrics.registerFont(TTFont("DejaVu", _p))
            pdfmetrics.registerFont(TTFont("DejaVu-Bold",
                _p.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")
                  if _os.path.exists(_p.replace("DejaVuSans.ttf",
                                                "DejaVuSans-Bold.ttf")) else _p))
            _FONT = "DejaVu"
            _FONT_BOLD = "DejaVu-Bold"
            break
except Exception:
    pass


def _money(n: Any) -> str:
    try:
        from shared.money import fmt_uah_as_usd
        return fmt_uah_as_usd(n, decimals=0)
    except Exception:
        return "—"


def _pct(n: Any) -> str:
    try:
        v = float(n)
        if v <= 1.0:
            v = v * 100
        return f"{v:.1f}%"
    except Exception:
        return "—"


def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(name="L_H1", parent=s["Heading1"],
          fontName=_FONT_BOLD, fontSize=20, leading=24, textColor=PRIMARY))
    s.add(ParagraphStyle(name="L_H2", parent=s["Heading2"],
          fontName=_FONT_BOLD, fontSize=13, leading=18, textColor=colors.black,
          spaceBefore=10, spaceAfter=6))
    s.add(ParagraphStyle(name="L_K", parent=s["Normal"],
          fontName=_FONT_BOLD, fontSize=8, leading=10,
          textColor=MUTED, spaceAfter=2))
    s.add(ParagraphStyle(name="L_Body", parent=s["Normal"],
          fontName=_FONT, fontSize=10, leading=14))
    s.add(ParagraphStyle(name="L_Muted", parent=s["Normal"],
          fontName=_FONT, fontSize=9, leading=12, textColor=MUTED))
    return s


# ────────────────────────────────────────────────────────────────────────────
# Data builders (derive every figure from real collections)
# ────────────────────────────────────────────────────────────────────────────

async def _asset_factsheet_data(asset_id: str) -> dict:
    a = await db.lumen_assets.find_one({"id": asset_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Актив не знайдено")

    # Operator + SPV
    op = await db.lumen_operators.find_one({"id": a.get("operator_id")},
                                            {"_id": 0}) if a.get("operator_id") else None
    spv = await db.lumen_spvs.find_one({"asset_id": asset_id}, {"_id": 0})
    fund = None
    if spv:
        fund = await db.lumen_funds.find_one({"spv_ids": spv["id"]},
                                              {"_id": 0, "id": 1, "name": 1, "kind": 1})

    # Investors derived from certificates
    investors = 0
    nav = 0.0
    cap_table: list[dict] = []
    async for c in db.lumen_certificates.find(
            {"asset_id": asset_id, "status": {"$ne": "voided"}}, {"_id": 0}):
        investors += 1
        nav += float(c.get("value_uah") or 0)
        cap_table.append({
            "investor": c.get("investor_name") or "Інвестор",
            "percent": c.get("ownership_percent"),
            "value_uah": c.get("value_uah"),
        })
    cap_table.sort(key=lambda r: -float(r.get("value_uah") or 0))

    # Payouts / dividends summary
    paid = 0.0
    async for r in db.lumen_payout_records.find({"asset_id": asset_id, "status": "paid"}, {"_id": 0}):
        paid += float(r.get("amount") or 0)

    return {
        "asset": a, "operator": op, "spv": spv, "fund": fund,
        "investors": investors, "nav_uah": nav,
        "paid_total_uah": paid,
        "cap_table": cap_table[:25],
    }


async def _quarterly_data(period: str) -> dict:
    """period = '2026Q2' (year + quarter)"""
    # KPIs aggregated as-of latest snapshot — quarter label is informational
    assets = await db.lumen_assets.count_documents({})
    investors = await db.lumen_investor_profiles.count_documents({})
    funds = await db.lumen_funds.count_documents({"status": {"$ne": "closed"}})
    certs = await db.lumen_certificates.count_documents({"status": {"$ne": "voided"}})
    capital_under_mgmt = 0.0
    async for c in db.lumen_certificates.find({"status": {"$ne": "voided"}}, {"_id": 0}):
        capital_under_mgmt += float(c.get("value_uah") or 0)
    # category breakdown
    by_cat: dict[str, float] = {}
    async for c in db.lumen_certificates.find({"status": {"$ne": "voided"}}, {"_id": 0}):
        a = await db.lumen_assets.find_one({"id": c.get("asset_id")},
                                            {"_id": 0, "category": 1})
        cat = (a or {}).get("category") or "інше"
        by_cat[cat] = by_cat.get(cat, 0) + float(c.get("value_uah") or 0)
    breakdown = sorted([{"category": k, "value_uah": v}
                        for k, v in by_cat.items()], key=lambda x: -x["value_uah"])
    # paid out in the last 90 days
    cutoff = _now() - timedelta(days=90)
    paid_90 = 0.0
    async for r in db.lumen_payout_records.find(
            {"status": "paid", "paid_at": {"$gte": cutoff}}, {"_id": 0}):
        paid_90 += float(r.get("amount") or 0)
    return {
        "period": period,
        "kpi": {"assets": assets, "investors": investors, "funds": funds,
                "certificates": certs, "aum_uah": capital_under_mgmt,
                "distributions_90d_uah": paid_90},
        "breakdown": breakdown,
    }


async def _fund_report_data(fund_id: str) -> dict:
    f = await db.lumen_funds.find_one({"id": fund_id}, {"_id": 0})
    if not f:
        raise HTTPException(status_code=404, detail="Фонд не знайдено")
    holdings: list[dict] = []
    nav = 0.0
    lp_set: set[str] = set()
    for spv_id in (f.get("spv_ids") or []):
        spv = await db.lumen_spvs.find_one({"id": spv_id}, {"_id": 0})
        if not spv:
            continue
        a = await db.lumen_assets.find_one({"id": spv.get("asset_id")},
                                            {"_id": 0})
        val = 0.0
        async for c in db.lumen_certificates.find(
                {"asset_id": spv.get("asset_id"), "status": {"$ne": "voided"}},
                {"_id": 0}):
            val += float(c.get("value_uah") or 0)
            lp_set.add(c.get("investor_id") or "")
        nav += val
        holdings.append({
            "spv_name": spv.get("name"),
            "asset_title": (a or {}).get("title") or "",
            "category": (a or {}).get("category"),
            "value_uah": val,
        })
    holdings.sort(key=lambda r: -r.get("value_uah", 0))
    return {"fund": f, "holdings": holdings, "nav_uah": nav,
            "lp_count": len(lp_set)}


# ────────────────────────────────────────────────────────────────────────────
# PDF renderers
# ────────────────────────────────────────────────────────────────────────────

def _render_factsheet(data: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.6 * cm,
                            rightMargin=1.6 * cm, topMargin=1.6 * cm,
                            bottomMargin=1.6 * cm,
                            title=f"Factsheet · {data['asset'].get('title')}")
    s = _styles()
    story = []
    a = data["asset"]
    story.append(Paragraph("LUMEN · Факт-лист активу", s["L_K"]))
    story.append(Paragraph(a.get("title") or "", s["L_H1"]))
    story.append(Paragraph(f"{a.get('location') or ''} · "
                            f"категорія: {a.get('category') or '—'}", s["L_Muted"]))
    story.append(Spacer(1, 8))

    kpi_rows = [
        ["NAV (від сертифікатів)", _money(data.get("nav_uah"))],
        ["Цільова дохідність", _pct(a.get("target_yield"))],
        ["Завантаженість", _pct(a.get("occupancy_percent"))],
        ["Інвесторів", str(data.get("investors") or 0)],
        ["Виплачено всього", _money(data.get("paid_total_uah"))],
    ]
    if data.get("operator"):
        kpi_rows.append(["Оператор", data["operator"].get("name") or "—"])
    if data.get("spv"):
        kpi_rows.append(["SPV", f"{data['spv'].get('name')} "
                         f"({data['spv'].get('jurisdiction') or 'UA'})"])
    if data.get("fund"):
        kpi_rows.append(["Фонд", data["fund"].get("name") or "—"])
    t = Table(kpi_rows, colWidths=[6 * cm, 10 * cm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("FONTNAME", (1, 0), (1, -1), _FONT_BOLD),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
    ]))
    story.append(t)
    story.append(Spacer(1, 14))

    story.append(Paragraph("Cap Table (топ 25)", s["L_H2"]))
    rows = [["Інвестор", "Частка", "Вартість"]]
    for r in data.get("cap_table") or []:
        rows.append([r.get("investor") or "",
                     _pct(r.get("percent")), _money(r.get("value_uah"))])
    if len(rows) == 1:
        rows.append(["—", "—", "—"])
    ct = Table(rows, colWidths=[8 * cm, 4 * cm, 4 * cm])
    ct.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
        ("FONTNAME", (0, 1), (-1, -1), _FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F4F6")),
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFAFA")]),
    ]))
    story.append(ct)
    story.append(Spacer(1, 12))
    story.append(Paragraph("Звіт згенеровано платформою LUMEN. Усі цифри "
                            "виведено з реальних колекцій (сертифікати, виплати, SPV).",
                            s["L_Muted"]))
    doc.build(story)
    return buf.getvalue()


def _render_quarterly(data: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.6 * cm,
                            rightMargin=1.6 * cm, topMargin=1.6 * cm,
                            bottomMargin=1.6 * cm,
                            title=f"Quarterly · {data.get('period')}")
    s = _styles()
    story = []
    story.append(Paragraph("LUMEN · Квартальний звіт", s["L_K"]))
    story.append(Paragraph(f"Період {data.get('period')}", s["L_H1"]))
    story.append(Spacer(1, 8))
    k = data.get("kpi") or {}
    rows = [
        ["Активи", str(k.get("assets"))],
        ["Інвестори", str(k.get("investors"))],
        ["Фонди", str(k.get("funds"))],
        ["Сертифікати", str(k.get("certificates"))],
        ["AUM (NAV сертифікатів)", _money(k.get("aum_uah"))],
        ["Виплачено за 90 днів", _money(k.get("distributions_90d_uah"))],
    ]
    t = Table(rows, colWidths=[7 * cm, 9 * cm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("FONTNAME", (1, 0), (1, -1), _FONT_BOLD),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 14))
    story.append(Paragraph("Розподіл AUM за категоріями", s["L_H2"]))
    rows = [["Категорія", "Вартість"]]
    for b in data.get("breakdown") or []:
        rows.append([b["category"], _money(b["value_uah"])])
    if len(rows) == 1:
        rows.append(["—", "—"])
    bt = Table(rows, colWidths=[10 * cm, 6 * cm])
    bt.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
        ("FONTNAME", (0, 1), (-1, -1), _FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F4F6")),
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
    ]))
    story.append(bt)
    story.append(Spacer(1, 10))
    story.append(Paragraph("Звіт згенеровано платформою LUMEN. Цифри агрегуються"
                            " з реальних колекцій активів, сертифікатів та виплат.",
                            s["L_Muted"]))
    doc.build(story)
    return buf.getvalue()


def _render_fund(data: dict) -> bytes:
    buf = io.BytesIO()
    f = data["fund"]
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.6 * cm,
                            rightMargin=1.6 * cm, topMargin=1.6 * cm,
                            bottomMargin=1.6 * cm,
                            title=f"Fund Report · {f.get('name')}")
    s = _styles()
    story = []
    story.append(Paragraph("LUMEN · Звіт фонду", s["L_K"]))
    story.append(Paragraph(f.get("name") or "", s["L_H1"]))
    story.append(Paragraph(f"{f.get('kind') or 'mixed'} · регіон: {f.get('region') or '—'}",
                            s["L_Muted"]))
    story.append(Spacer(1, 8))
    rows = [
        ["NAV", _money(data.get("nav_uah"))],
        ["LPs (унікальні власники)", str(data.get("lp_count"))],
        ["SPV у фонді", str(len(f.get("spv_ids") or []))],
        ["Цільовий розмір", _money(f.get("target_size_uah"))],
        ["Статус", f.get("status") or "forming"],
    ]
    t = Table(rows, colWidths=[7 * cm, 9 * cm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("FONTNAME", (1, 0), (1, -1), _FONT_BOLD),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 14))
    story.append(Paragraph("Холдінги фонду", s["L_H2"]))
    rows = [["SPV", "Актив", "Категорія", "Вартість"]]
    for h in data.get("holdings") or []:
        rows.append([h["spv_name"], h["asset_title"], h.get("category") or "—",
                     _money(h["value_uah"])])
    if len(rows) == 1:
        rows.append(["—", "—", "—", "—"])
    ht = Table(rows, colWidths=[5 * cm, 5 * cm, 3 * cm, 3 * cm])
    ht.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
        ("FONTNAME", (0, 1), (-1, -1), _FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F4F6")),
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("ALIGN", (3, 1), (3, -1), "RIGHT"),
    ]))
    story.append(ht)
    story.append(Spacer(1, 10))
    story.append(Paragraph("NAV фонду = сума активних сертифікатів у складових SPV.",
                            s["L_Muted"]))
    doc.build(story)
    return buf.getvalue()


# ────────────────────────────────────────────────────────────────────────────
# CRUD + endpoints
# ────────────────────────────────────────────────────────────────────────────

class GenerateIn(BaseModel):
    kind: str
    entity_id: Optional[str] = None
    period: Optional[str] = None  # for quarterly
    title: Optional[str] = None


def _report_out(d: dict) -> dict:
    out = _strip_mongo(dict(d))
    out["kind_label"] = KIND_LABELS_UK.get(out.get("kind"), out.get("kind"))
    return out


async def _default_title(payload: GenerateIn) -> str:
    if payload.title:
        return payload.title
    if payload.kind == "asset_factsheet" and payload.entity_id:
        a = await db.lumen_assets.find_one({"id": payload.entity_id},
                                            {"_id": 0, "title": 1})
        return f"Факт-лист · {(a or {}).get('title') or payload.entity_id}"
    if payload.kind == "fund_report" and payload.entity_id:
        f = await db.lumen_funds.find_one({"id": payload.entity_id},
                                            {"_id": 0, "name": 1})
        return f"Звіт фонду · {(f or {}).get('name') or payload.entity_id}"
    if payload.kind == "quarterly":
        return f"Квартальний звіт · {payload.period or _current_quarter()}"
    return KIND_LABELS_UK.get(payload.kind, payload.kind)


def _current_quarter() -> str:
    n = datetime.now(timezone.utc)
    return f"{n.year}Q{(n.month - 1) // 3 + 1}"


@router.post("/admin/report-builder/generate")
async def admin_generate(payload: GenerateIn, _=Depends(require_admin)):
    if payload.kind not in KINDS:
        raise HTTPException(status_code=400, detail=f"Тип має бути одним з: {KINDS}")
    if payload.kind in ("asset_factsheet", "fund_report") and not payload.entity_id:
        raise HTTPException(status_code=400, detail="Потрібен entity_id")
    if payload.kind == "quarterly" and not payload.period:
        payload.period = _current_quarter()

    # Pre-validate that entity exists
    if payload.kind == "asset_factsheet":
        if not await db.lumen_assets.find_one({"id": payload.entity_id}, {"_id": 1}):
            raise HTTPException(status_code=404, detail="Актив не знайдено")
    if payload.kind == "fund_report":
        if not await db.lumen_funds.find_one({"id": payload.entity_id}, {"_id": 1}):
            raise HTTPException(status_code=404, detail="Фонд не знайдено")

    title = await _default_title(payload)
    rid = f"rpt-{uuid.uuid4().hex[:12]}"
    doc = {
        "id": rid, "kind": payload.kind, "entity_id": payload.entity_id,
        "period": payload.period, "title": title,
        "created_at": _now(),
    }
    # upsert by (kind, entity_id, period) so re-generating updates instead of duplicating
    await db.lumen_reports.update_one(
        {"kind": payload.kind, "entity_id": payload.entity_id, "period": payload.period},
        {"$set": doc}, upsert=True)
    saved = await db.lumen_reports.find_one(
        {"kind": payload.kind, "entity_id": payload.entity_id, "period": payload.period},
        {"_id": 0})
    return _report_out(saved)


@router.get("/admin/report-builder/list")
async def admin_list(kind: Optional[str] = None, _=Depends(require_admin)):
    q: dict[str, Any] = {}
    if kind:
        q["kind"] = kind
    items = []
    async for r in db.lumen_reports.find(q, {"_id": 0}).sort("created_at", -1):
        items.append(_report_out(r))
    return {"items": items, "count": len(items)}


@router.get("/admin/report-builder/{report_id}")
async def admin_one(report_id: str, _=Depends(require_admin)):
    r = await db.lumen_reports.find_one({"id": report_id}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Звіт не знайдено")
    return _report_out(r)


@router.delete("/admin/report-builder/{report_id}")
async def admin_delete(report_id: str, _=Depends(require_admin)):
    res = await db.lumen_reports.delete_one({"id": report_id})
    return {"deleted": res.deleted_count > 0}


@router.get("/reports")
async def my_reports(user=Depends(get_current_user)):
    uid = user.get("id") or user.get("user_id")
    # Discover my assets/funds via certificates
    asset_ids: set[str] = set()
    fund_ids: set[str] = set()
    async for c in db.lumen_certificates.find(
            {"investor_id": uid, "status": {"$ne": "voided"}},
            {"_id": 0, "asset_id": 1}):
        if c.get("asset_id"):
            asset_ids.add(c["asset_id"])
            spv = await db.lumen_spvs.find_one({"asset_id": c["asset_id"]},
                                                {"_id": 0, "id": 1})
            if spv:
                async for f in db.lumen_funds.find({"spv_ids": spv["id"]},
                                                    {"_id": 0, "id": 1}):
                    fund_ids.add(f["id"])
    relevant = {"$or": [
        {"kind": "quarterly"},
        {"kind": "asset_factsheet", "entity_id": {"$in": list(asset_ids)}},
        {"kind": "fund_report", "entity_id": {"$in": list(fund_ids)}},
    ]}
    items = []
    async for r in db.lumen_reports.find(relevant, {"_id": 0}).sort("created_at", -1):
        items.append(_report_out(r))
    return {"items": items, "count": len(items),
            "my_assets": len(asset_ids), "my_funds": len(fund_ids)}


@router.get("/reports/{report_id}")
async def one_report(report_id: str, user=Depends(get_current_user)):
    r = await db.lumen_reports.find_one({"id": report_id}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Звіт не знайдено")
    return _report_out(r)


@router.get("/reports/{report_id}/pdf")
async def report_pdf(report_id: str, user=Depends(get_current_user)):
    r = await db.lumen_reports.find_one({"id": report_id}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Звіт не знайдено")
    kind = r.get("kind")
    try:
        if kind == "asset_factsheet":
            data = await _asset_factsheet_data(r.get("entity_id"))
            pdf = _render_factsheet(data)
            fname = f"factsheet-{r.get('entity_id')}.pdf"
        elif kind == "quarterly":
            data = await _quarterly_data(r.get("period") or _current_quarter())
            pdf = _render_quarterly(data)
            fname = f"quarterly-{r.get('period')}.pdf"
        elif kind == "fund_report":
            data = await _fund_report_data(r.get("entity_id"))
            pdf = _render_fund(data)
            fname = f"fund-{r.get('entity_id')}.pdf"
        else:
            raise HTTPException(status_code=400, detail="Невідомий тип звіту")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("PDF render failed")
        raise HTTPException(status_code=500, detail=f"Не вдалося згенерувати PDF: {e}")
    return StreamingResponse(
        io.BytesIO(pdf), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ────────────────────────────────────────────────────────────────────────────
# Indexes + idempotent demo seed
# ────────────────────────────────────────────────────────────────────────────

async def ensure_reporting_indexes() -> None:
    try:
        await db.lumen_reports.create_index([("kind", 1), ("entity_id", 1),
                                              ("period", 1)], unique=True,
                                             sparse=True)
        await db.lumen_reports.create_index([("created_at", -1)])
    except Exception:
        logger.exception("reporting indexes failed")


async def seed_reporting_demo() -> dict:
    """Pre-generate a quarterly report + factsheets for first 2 assets + fund reports."""
    await ensure_reporting_indexes()
    if await db.lumen_reports.count_documents({}) > 0:
        return {"skipped": "reports already present"}
    stats = {"quarterly": 0, "factsheets": 0, "funds": 0}

    # Quarterly for current period
    q = _current_quarter()
    await db.lumen_reports.update_one(
        {"kind": "quarterly", "entity_id": None, "period": q},
        {"$set": {"id": f"rpt-{uuid.uuid4().hex[:12]}", "kind": "quarterly",
                   "entity_id": None, "period": q,
                   "title": f"Квартальний звіт · {q}", "created_at": _now()}},
        upsert=True)
    stats["quarterly"] = 1

    # First 3 assets
    cnt = 0
    async for a in db.lumen_assets.find({}, {"_id": 0, "id": 1, "title": 1}).limit(3):
        await db.lumen_reports.update_one(
            {"kind": "asset_factsheet", "entity_id": a["id"], "period": None},
            {"$set": {"id": f"rpt-{uuid.uuid4().hex[:12]}", "kind": "asset_factsheet",
                       "entity_id": a["id"], "period": None,
                       "title": f"Факт-лист · {a.get('title')}",
                       "created_at": _now()}}, upsert=True)
        cnt += 1
    stats["factsheets"] = cnt

    # All funds
    cnt = 0
    async for f in db.lumen_funds.find({}, {"_id": 0, "id": 1, "name": 1}):
        await db.lumen_reports.update_one(
            {"kind": "fund_report", "entity_id": f["id"], "period": None},
            {"$set": {"id": f"rpt-{uuid.uuid4().hex[:12]}", "kind": "fund_report",
                       "entity_id": f["id"], "period": None,
                       "title": f"Звіт фонду · {f.get('name')}",
                       "created_at": _now()}}, upsert=True)
        cnt += 1
    stats["funds"] = cnt
    return stats


__all__ = ["router", "ensure_reporting_indexes", "seed_reporting_demo"]
