"""
LUMEN Contracts & Legal Layer — Sprint 4.

Builds the legal chain of the platform:

    KYC → Investment Approved → Contract Generated → Contract Signed → Active

Entities (see lumen_models.py):
    lumen_contract_templates — reusable legal templates ({{placeholders}})
    lumen_contracts          — contract instances bound to an investment
    lumen_signatures         — electronic acceptance records (timestamp/IP/UA)

Contract lifecycle:
    draft → generated → sent → viewed → signed
                            ↘ expired / cancelled

Endpoints
=========
Investor
    GET  /api/investor/contracts                 — my contracts
    GET  /api/investor/contracts/{id}            — detail (marks `viewed`)
    POST /api/investor/contracts/{id}/sign       — electronic acceptance
    GET  /api/contracts/{id}/pdf                 — PDF download (owner/admin)

Admin
    GET  /api/admin/contracts?status=…           — registry + counts
    GET  /api/admin/contracts/{id}               — detail + signatures
    POST /api/admin/contracts/{id}/cancel        — cancel (reason required)
    GET/POST/PATCH /api/admin/contract-templates — template management

PDF: rendered in-memory with reportlab + Liberation Sans (Cyrillic-safe).
No external e-sign providers (Дія.Підпис arrives in a later sprint) —
Sprint 4 ships Electronic Acceptance: "I agree and sign" + audit trail.
"""

from __future__ import annotations

import io
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from lumen_api import db, get_current_user, require_admin, _strip_mongo, _now, _iso
from lumen_audit import write_audit

logger = logging.getLogger("lumen.contracts")


# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

CONTRACT_STATUSES = ["draft", "generated", "sent", "viewed", "signed", "expired", "cancelled"]

CONTRACT_STATUS_LABELS = {
    "draft":     "чернетка",
    "generated": "згенеровано",
    "sent":      "надіслано на підпис",
    "viewed":    "переглянуто",
    "signed":    "підписано",
    "expired":   "прострочено",
    "cancelled": "скасовано",
}

TEMPLATE_KINDS = ["investment_agreement", "spv_participation", "co_investment"]

TEMPLATE_KIND_LABELS = {
    "investment_agreement": "Договір інвестування",
    "spv_participation":    "Договір участі в SPV",
    "co_investment":        "Договір спільного інвестування",
}

# statuses the investor may still sign from
_SIGNABLE_STATUSES = {"generated", "sent", "viewed"}

# statuses an admin may cancel from
_CANCELLABLE_STATUSES = {"draft", "generated", "sent", "viewed", "expired"}

_FONT_REGULAR = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
_FONT_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"


# ──────────────────────────────────────────────────────────────────────────────
# Default templates (UA legal copy with placeholders)
# ──────────────────────────────────────────────────────────────────────────────

_COMMON_TAIL = """## 4. Права та обов'язки сторін
4.1. Платформа зобов'язується вести реєстр часток, надавати Інвестору щомісячні звіти щодо стану Об'єкта та забезпечувати розподіл доходу пропорційно частці Інвестора.
4.2. Інвестор зобов'язується надати достовірні дані верифікації (KYC), реквізити для виплат та своєчасно повідомляти про їх зміну.
4.3. Інвестор має право на отримання частини доходу від Об'єкта пропорційно до своєї частки, доступ до звітності та документів Об'єкта.

## 5. Розподіл доходу
5.1. Дохід від Об'єкта розподіляється між учасниками пропорційно до їхніх часток у пулі фінансування.
5.2. Виплати здійснюються на банківські реквізити (IBAN), зазначені Інвестором у профілі: {{investor_iban}}.
5.3. Орієнтовна цільова дохідність Об'єкта становить {{target_yield}}% річних. Цільова дохідність не є гарантованою.

## 6. Ризики
6.1. Інвестор підтверджує, що ознайомлений з ризиками інвестування у реальні активи, включно з ризиком часткової або повної втрати інвестованих коштів.
6.2. Минула дохідність не гарантує майбутніх результатів.

## 7. Строк дії та припинення
7.1. Договір набирає чинності з моменту його електронного підписання Інвестором.
7.2. Договір діє протягом усього періоду володіння Інвестором часткою в Об'єкті (орієнтовний горизонт — {{term_months}} міс.).

## 8. Електронний підпис
8.1. Сторони погоджуються, що електронне прийняття умов (Electronic Acceptance) через платформу Lumen із фіксацією дати, часу, IP-адреси та параметрів пристрою Інвестора має юридичну силу простого електронного підпису відповідно до ЗУ «Про електронні довірчі послуги».
8.2. Підтвердженням підписання є запис у реєстрі підписів платформи.

## 9. Реквізити сторін
ПЛАТФОРМА: ТОВ «Лумен Кепітал», Україна
ІНВЕСТОР: {{investor_name}}, РНОКПП: {{investor_tax_id}}, e-mail: {{investor_email}}"""

_DEFAULT_TEMPLATES = [
    {
        "kind": "investment_agreement",
        "name": "Договір інвестування (базовий)",
        "body_text": """# ДОГОВІР ІНВЕСТУВАННЯ № {{contract_number}}
м. Київ — {{date}}

Цей Договір укладено між ТОВ «Лумен Кепітал» (далі — «Платформа») та інвестором {{investor_name}} (далі — «Інвестор») щодо участі у фінансуванні об'єкта «{{asset_title}}».

## 1. Предмет договору
1.1. Інвестор передає кошти у розмірі {{amount}} до пулу колективного фінансування об'єкта «{{asset_title}}» ({{asset_location}}).
1.2. Частка Інвестора у пулі фінансування Об'єкта на момент укладення становить {{ownership_percent}}% ({{round_label}}).
1.3. Облік часток ведеться у реєстрі власності платформи Lumen.

## 2. Структура угоди
2.1. Об'єкт оформлено через окрему юридичну особу (SPV): {{spv_label}}.
2.2. Кошти пулу спрямовуються виключно на фінансування Об'єкта.

## 3. Порядок розрахунків
3.1. Сума інвестиції: {{amount}}. Розрахунки та облік частки здійснюються в доларах США (USD / USDT).
3.2. Інвестиція активується після підтвердження верифікації Інвестора (KYC) та підписання цього Договору.

""" + _COMMON_TAIL,
    },
    {
        "kind": "spv_participation",
        "name": "Договір участі в SPV",
        "body_text": """# ДОГОВІР УЧАСТІ В SPV № {{contract_number}}
м. Київ — {{date}}

Цей Договір укладено між {{spv_label}} (далі — «SPV»), управителем якої є ТОВ «Лумен Кепітал», та інвестором {{investor_name}} (далі — «Інвестор»).

## 1. Предмет договору
1.1. Інвестор набуває право участі у фінансуванні об'єкта «{{asset_title}}» ({{asset_location}}) через SPV {{spv_label}}.
1.2. Розмір участі: {{amount}}, що відповідає {{ownership_percent}}% пулу фінансування ({{round_label}}).
1.3. SPV створена виключно для володіння та управління Об'єктом.

## 2. Структура угоди
2.1. Усі права на Об'єкт оформлені на SPV. Інвестор отримує договірне право на частку доходу SPV пропорційно до участі.
2.2. SPV не має інших активів або зобов'язань, крім пов'язаних з Об'єктом.

## 3. Порядок розрахунків
3.1. Сума участі: {{amount}}. Розрахунки та облік частки здійснюються в доларах США (USD / USDT).
3.2. Участь активується після підтвердження верифікації Інвестора (KYC) та підписання цього Договору.

""" + _COMMON_TAIL,
    },
    {
        "kind": "co_investment",
        "name": "Договір спільного інвестування",
        "body_text": """# ДОГОВІР СПІЛЬНОГО ІНВЕСТУВАННЯ № {{contract_number}}
м. Київ — {{date}}

Цей Договір укладено між ТОВ «Лумен Кепітал» (далі — «Платформа»), співінвесторами пулу об'єкта «{{asset_title}}» та інвестором {{investor_name}} (далі — «Інвестор»).

## 1. Предмет договору
1.1. Інвестор приєднується до пулу спільного інвестування об'єкта «{{asset_title}}» ({{asset_location}}) з внеском {{amount}}.
1.2. Частка Інвестора у пулі: {{ownership_percent}}% ({{round_label}}).
1.3. Співінвестори діють спільно через платформу Lumen; права кожного обліковуються у реєстрі власності.

## 2. Структура угоди
2.1. Об'єкт оформлено через окрему юридичну особу (SPV): {{spv_label}}.
2.2. Рішення щодо Об'єкта приймаються управителем в інтересах усіх співінвесторів пулу.

## 3. Порядок розрахунків
3.1. Сума внеску: {{amount}}. Розрахунки та облік частки здійснюються в доларах США (USD / USDT).
3.2. Внесок активується після підтвердження верифікації Інвестора (KYC) та підписання цього Договору.

""" + _COMMON_TAIL,
    },
]


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _contract_out(doc: dict) -> dict:
    doc = _strip_mongo(dict(doc))
    doc["status_label"] = CONTRACT_STATUS_LABELS.get(doc.get("status"), doc.get("status"))
    doc["template_kind_label"] = TEMPLATE_KIND_LABELS.get(
        doc.get("template_kind"), doc.get("template_kind"))
    for k in ("generated_at", "sent_at", "viewed_at", "signed_at", "cancelled_at"):
        if doc.get(k) is not None:
            doc[k] = _iso(doc[k])
    return doc


def _template_out(doc: dict) -> dict:
    doc = _strip_mongo(dict(doc))
    doc["kind_label"] = TEMPLATE_KIND_LABELS.get(doc.get("kind"), doc.get("kind"))
    return doc


def _signature_out(doc: dict) -> dict:
    doc = _strip_mongo(dict(doc))
    if doc.get("signed_at") is not None:
        doc["signed_at"] = _iso(doc["signed_at"])
    return doc


def _fmt_amount(v: float) -> str:
    # Contracts are USD-denominated for the user; v is stored in UAH internally.
    from shared.money import usd_from_uah
    return f"${usd_from_uah(v):,.0f}"


async def _next_contract_number() -> str:
    """Monotonic contract number, derived from the highest EXISTING number for
    the current year — NOT count_documents(): deletions would shrink the count
    and the unique index ux_contracts_number would reject the re-issued value.
    Zero-padded sequences keep lexicographic order == numeric order."""
    year = _now().year
    prefix = f"LMN-{year}-"
    last = await db.lumen_contracts.find_one(
        {"number": {"$regex": f"^{prefix}"}}, sort=[("number", -1)])
    seq = 0
    if last:
        try:
            seq = int(str(last.get("number", "")).rsplit("-", 1)[1])
        except (ValueError, IndexError):
            seq = 0
    return f"{prefix}{seq + 1:05d}"


def _resolve_placeholders(body: str, ctx: dict) -> str:
    out = body
    for key, value in ctx.items():
        out = out.replace("{{" + key + "}}", str(value if value is not None else "—"))
    return out


async def _pick_template(asset: dict) -> Optional[dict]:
    """SPV-backed assets get the SPV participation agreement, the rest get the
    base investment agreement. Co-investment is selected manually by admins."""
    kind = "spv_participation" if (asset.get("spv_label") or "").strip() else "investment_agreement"
    tpl = await db.lumen_contract_templates.find_one({"kind": kind, "active": True})
    if not tpl:
        tpl = await db.lumen_contract_templates.find_one({"active": True})
    return tpl


async def generate_contract_for_investment(investment: dict, *, mark_signed: bool = False,
                                           actor_id: str = "system") -> Optional[dict]:
    """Create a contract instance for an investment (idempotent per investment).

    mark_signed=True is used ONLY by the startup backfill for historical
    active investments that predate the legal layer.
    """
    existing = await db.lumen_contracts.find_one({"investment_id": investment["id"]})
    if existing:
        return existing

    asset = await db.lumen_assets.find_one({"id": investment["asset_id"]}) or {}
    user = await db.users.find_one({"user_id": investment["investor_id"]}) or {}
    profile = await db.lumen_investor_profiles.find_one(
        {"user_id": investment["investor_id"]}) or {}

    tpl = await _pick_template(asset)
    if not tpl:
        logger.error("No active contract template — cannot generate contract")
        return None

    now = _now()
    number = await _next_contract_number()
    ctx = {
        "contract_number": number,
        "date": now.strftime("%d.%m.%Y"),
        "investor_name": profile.get("full_name") or user.get("name") or user.get("email"),
        "investor_tax_id": profile.get("tax_id") or "—",
        "investor_iban": profile.get("iban") or "вказується у профілі інвестора",
        "investor_email": user.get("email") or "—",
        "asset_title": asset.get("title") or "—",
        "asset_location": asset.get("location") or "—",
        "spv_label": asset.get("spv_label") or "ТОВ «Лумен-SPV»",
        "amount": _fmt_amount(float(investment.get("amount") or 0)),
        "ownership_percent": investment.get("ownership_percent") or investment.get("share_percent") or 0,
        "round_label": investment.get("round_label") or "Раунд I",
        "target_yield": asset.get("target_yield") or investment.get("current_yield") or "—",
        "term_months": asset.get("term_months") or asset.get("horizon_months") or "—",
    }
    body = _resolve_placeholders(tpl["body_text"], ctx)

    contract = {
        "id": str(uuid.uuid4()),
        "number": number,
        "investor_id": investment["investor_id"],
        "asset_id": investment["asset_id"],
        "investment_id": investment["id"],
        "template_id": tpl["id"],
        "template_kind": tpl["kind"],
        "status": "signed" if mark_signed else "sent",
        "title": f"{TEMPLATE_KIND_LABELS.get(tpl['kind'], 'Договір')} № {number}",
        "body_text": body,
        "version": int(tpl.get("version") or 1),
        "generated_at": now,
        "sent_at": now,
        "viewed_at": now if mark_signed else None,
        "signed_at": now if mark_signed else None,
        "cancelled_at": None,
        "cancel_reason": None,
        "pdf_url": None,
        # display denormalisation
        "asset_title": asset.get("title"),
        "investor_name": ctx["investor_name"],
        "amount": float(investment.get("amount") or 0),
        "created_at": now,
        "updated_at": now,
    }
    contract["pdf_url"] = f"/api/contracts/{contract['id']}/pdf"
    await db.lumen_contracts.insert_one(contract)

    if mark_signed:
        await db.lumen_signatures.insert_one({
            "id": str(uuid.uuid4()),
            "contract_id": contract["id"],
            "user_id": investment["investor_id"],
            "status": "signed",
            "signed_at": investment.get("invested_at") or now,
            "ip": "system-backfill",
            "user_agent": "lumen-legal-backfill/sprint4",
            "created_at": now,
        })

    await db.lumen_investments.update_one(
        {"id": investment["id"]},
        {"$set": {"contract_id": contract["id"], "updated_at": now}},
    )
    return contract


# ──────────────────────────────────────────────────────────────────────────────
# PDF rendering (reportlab, in-memory, Cyrillic-safe)
# ──────────────────────────────────────────────────────────────────────────────

_FONTS_READY = False


def _ensure_fonts() -> None:
    global _FONTS_READY
    if _FONTS_READY:
        return
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    pdfmetrics.registerFont(TTFont("LumenSans", _FONT_REGULAR))
    pdfmetrics.registerFont(TTFont("LumenSans-Bold", _FONT_BOLD))
    _FONTS_READY = True


def render_contract_pdf(contract: dict, signature: Optional[dict] = None) -> bytes:
    """Render the contract body (line-oriented markup) into a PDF.

    Markup: `# ` title, `## ` section heading, blank line = spacer,
    everything else = paragraph.
    """
    _ensure_fonts()
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from xml.sax.saxutils import escape

    styles = {
        "title": ParagraphStyle("title", fontName="LumenSans-Bold", fontSize=14,
                                leading=19, spaceAfter=6, textColor=colors.HexColor("#1A3C32")),
        "h2": ParagraphStyle("h2", fontName="LumenSans-Bold", fontSize=11,
                             leading=15, spaceBefore=10, spaceAfter=4,
                             textColor=colors.HexColor("#2E5D4F")),
        "body": ParagraphStyle("body", fontName="LumenSans", fontSize=9.5,
                               leading=14, spaceAfter=3),
        "meta": ParagraphStyle("meta", fontName="LumenSans", fontSize=8,
                               leading=11, textColor=colors.HexColor("#6B7280")),
    }

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
        title=contract.get("title") or "Договір Lumen",
        author="Lumen Capital",
    )
    story = []
    for raw_line in (contract.get("body_text") or "").splitlines():
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 4))
        elif line.startswith("# "):
            story.append(Paragraph(escape(line[2:]), styles["title"]))
        elif line.startswith("## "):
            story.append(Paragraph(escape(line[3:]), styles["h2"]))
        else:
            story.append(Paragraph(escape(line), styles["body"]))

    # signature block
    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=0.7, color=colors.HexColor("#2E5D4F")))
    story.append(Spacer(1, 6))
    if contract.get("status") == "signed" and signature:
        story.append(Paragraph("ПІДПИСАНО ЕЛЕКТРОННО (Electronic Acceptance)", styles["h2"]))
        story.append(Paragraph(
            f"Підписант: {contract.get('investor_name') or signature.get('user_id')}",
            styles["body"]))
        story.append(Paragraph(f"Дата та час (UTC): {_iso(signature.get('signed_at'))}", styles["body"]))
        story.append(Paragraph(f"IP-адреса: {signature.get('ip') or '—'}", styles["body"]))
        story.append(Paragraph(f"Пристрій: {signature.get('user_agent') or '—'}", styles["meta"]))
    else:
        story.append(Paragraph("Договір не підписано", styles["h2"]))
        story.append(Paragraph(
            "Підпис здійснюється електронним прийняттям умов у кабінеті інвестора Lumen.",
            styles["meta"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f"Документ згенеровано платформою Lumen · {contract.get('number')} · версія шаблону {contract.get('version')}",
        styles["meta"]))

    doc.build(story)
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────────────────────
# Router
# ──────────────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api", tags=["lumen-contracts"])


@router.on_event("startup")
async def _sprint4_bootstrap():
    """Idempotent: seed default templates + backfill contracts for existing
    investments (historical active ones get an auto-signed legacy contract)."""
    try:
        for tpl in _DEFAULT_TEMPLATES:
            existing = await db.lumen_contract_templates.find_one({"kind": tpl["kind"]})
            if not existing:
                now = _now()
                await db.lumen_contract_templates.insert_one({
                    "id": str(uuid.uuid4()),
                    "kind": tpl["kind"],
                    "name": tpl["name"],
                    "body_text": tpl["body_text"],
                    "version": 1,
                    "active": True,
                    "created_at": now,
                    "updated_at": now,
                })
                logger.info("[Sprint 4] Seeded contract template: %s", tpl["kind"])

        # Backfill: every investment must have a contract
        async for inv in db.lumen_investments.find({"contract_id": None}):
            await generate_contract_for_investment(
                inv, mark_signed=(inv.get("status") == "active"))
        async for inv in db.lumen_investments.find({"contract_id": {"$exists": False}}):
            await generate_contract_for_investment(
                inv, mark_signed=(inv.get("status") == "active"))
    except Exception:  # pragma: no cover
        logger.exception("Sprint 4 bootstrap failed")


# ---- Investor -----------------------------------------------------------------

@router.get("/investor/contracts")
async def my_contracts(user=Depends(get_current_user)):
    items = []
    async for c in db.lumen_contracts.find({"investor_id": user["id"]}).sort("created_at", -1):
        items.append(_contract_out(c))
    return {"items": items, "total": len(items)}


@router.get("/investor/contracts/{contract_id}")
async def my_contract_detail(contract_id: str, user=Depends(get_current_user)):
    c = await db.lumen_contracts.find_one({"id": contract_id})
    if not c:
        raise HTTPException(status_code=404, detail="Договір не знайдено")
    if c.get("investor_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Немає доступу")
    # first open marks `viewed`
    if c.get("status") in ("generated", "sent"):
        now = _now()
        await db.lumen_contracts.update_one(
            {"id": contract_id},
            {"$set": {"status": "viewed", "viewed_at": now, "updated_at": now}},
        )
        c["status"], c["viewed_at"] = "viewed", now
    out = _contract_out(c)
    sig = await db.lumen_signatures.find_one(
        {"contract_id": contract_id, "status": "signed"})
    out["signature"] = _signature_out(sig) if sig else None
    inv = await db.lumen_investments.find_one({"id": c.get("investment_id")}) or {}
    out["investment_status"] = inv.get("status")
    return out


class SignPayload(BaseModel):
    agree: bool = False


@router.post("/investor/contracts/{contract_id}/sign")
async def sign_contract(contract_id: str, payload: SignPayload, request: Request,
                        user=Depends(get_current_user)):
    if not payload.agree:
        raise HTTPException(
            status_code=400,
            detail="Для підписання потрібно підтвердити згоду з умовами договору")
    c = await db.lumen_contracts.find_one({"id": contract_id})
    if not c:
        raise HTTPException(status_code=404, detail="Договір не знайдено")
    if c.get("investor_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Немає доступу")
    if c.get("status") == "signed":
        raise HTTPException(status_code=409, detail="Договір вже підписано")
    if c.get("status") not in _SIGNABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Договір не можна підписати (статус: {CONTRACT_STATUS_LABELS.get(c.get('status'), c.get('status'))})")

    now = _now()
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or \
        (request.client.host if request.client else None)
    user_agent = request.headers.get("user-agent")

    signature = {
        "id": str(uuid.uuid4()),
        "contract_id": contract_id,
        "user_id": user["id"],
        "status": "signed",
        "signed_at": now,
        "ip": ip,
        "user_agent": user_agent,
        "created_at": now,
    }
    await db.lumen_signatures.insert_one(signature)
    await db.lumen_contracts.update_one(
        {"id": contract_id},
        {"$set": {"status": "signed", "signed_at": now, "updated_at": now}},
    )
    # IR0.3 — field-level history: contract signed.
    try:
        from lumen_field_changes import record_change as _ir0_record
        await _ir0_record(
            db, entity_type="contract", entity_id=contract_id,
            field="status", old_value=c.get("status"), new_value="signed",
            actor={"id": user["id"], "email": user.get("email"), "role": "investor"},
            source="api", reason="investor e-signature",
        )
    except Exception:
        pass

    # legal gate satisfied → open payment_request (Sprint 6) instead of
    # immediately activating. Investment becomes `active` only after
    # admin confirms the payment.
    from lumen_investment_core import activate_ready_investments, _notify
    from lumen_payments import open_payment_requests_for_investor
    # First: move kyc_pending → contract_pending (if KYC ok but old flow).
    # Then: open awaiting_payment for anything contract_pending+signed.
    res = await activate_ready_investments(user["id"], actor_id=user["id"])
    pay_res = await open_payment_requests_for_investor(user["id"],
                                                       actor_id=user["id"])

    inv = await db.lumen_investments.find_one({"id": c.get("investment_id")}) or {}
    inv_status = inv.get("status")
    if inv_status == "awaiting_payment":
        await _notify(
            user["id"],
            "Договір підписано — очікуємо оплату",
            f"Договір {c.get('number')} підписано. Перейдіть у «Мої платежі» "
            f"та оплатіть інвестицію у «{c.get('asset_title')}». Після "
            "підтвердження оплати інвестиція стане активною.",
        )
    elif inv_status == "contract_pending":
        # KYC still missing — covered by KYC approval hook (Sprint 3)
        await _notify(
            user["id"],
            "Договір підписано",
            f"Договір {c.get('number')} підписано. Інвестиція стане активною "
            "після підтвердження верифікації (KYC) та оплати.",
        )
    else:
        await _notify(
            user["id"],
            "Договір підписано",
            f"Договір {c.get('number')} підписано.",
        )

    await write_audit(
        action="contract.sign", category="contract",
        target_type="lumen_contracts", target_id=contract_id,
        actor=user, request=request,
        summary=f"Contract signed: {c.get('number')} (asset={c.get('asset_title')})",
        meta={"investment_id": c.get("investment_id"),
              "asset_id": c.get("asset_id"),
              "investment_status_after": inv_status,
              "payment_requests_opened": pay_res.get("opened", 0)},
    )

    return {
        "contract_id": contract_id,
        "status": "signed",
        "signed_at": _iso(now),
        "signature": _signature_out(signature),
        "investment_status": inv_status,
        "payment_requests_opened": pay_res.get("opened", 0),
    }
    # NOTE: audit write executes BEFORE return — see helper above the return.


@router.get("/contracts/{contract_id}/pdf")
async def contract_pdf(contract_id: str, user=Depends(get_current_user)):
    c = await db.lumen_contracts.find_one({"id": contract_id})
    if not c:
        raise HTTPException(status_code=404, detail="Договір не знайдено")
    if c.get("investor_id") != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Немає доступу")
    sig = await db.lumen_signatures.find_one({"contract_id": contract_id, "status": "signed"})
    pdf_bytes = render_contract_pdf(c, sig)
    fname = f"{c.get('number', 'contract')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )


# ──────────────────────────────────────────────────────────────────────────────
# Public view-token surface  (Phase S1.2)
# ──────────────────────────────────────────────────────────────────────────────
# Why: lets an investor open, read AND sign a contract from a one-time link
# WITHOUT logging in. This is the BiBi pattern ported into LUMEN's domain.
#
# How it works:
#   1. An admin / manager creates the contract the usual way OR explicitly
#      issues a view link via POST /admin/contracts/{id}/view-link.
#   2. A `view_token` (32-hex urlsafe) is stored on the contract document
#      together with `view_token_expires_at` (default +30 days).
#   3. The investor opens `/c/view/<view_token>` in the browser; the SPA
#      hits the three endpoints below.
#   4. Every open/sign is rate-limited and the IP/UA is captured in the
#      signature record exactly like the in-cabinet flow.
# ──────────────────────────────────────────────────────────────────────────────

import secrets
from datetime import timedelta


def _public_contract_out(c: dict, sig: Optional[dict]) -> dict:
    """Compact representation safe to return to an unauthenticated viewer."""
    out = _contract_out(c)
    return {
        "contract_id":    out["id"],
        "number":         out.get("number"),
        "title":          out.get("title"),
        "status":         out.get("status"),
        "status_label":   out.get("status_label"),
        "asset_title":    out.get("asset_title"),
        "investor_name":  out.get("investor_name"),
        "amount":         out.get("amount"),
        "body_text":      c.get("body_text"),
        "generated_at":   out.get("generated_at"),
        "sent_at":        out.get("sent_at"),
        "viewed_at":      out.get("viewed_at"),
        "signed_at":      out.get("signed_at"),
        "expires_at":     _iso(c.get("view_token_expires_at")) if c.get("view_token_expires_at") else None,
        "view_count":     int(c.get("view_count") or 0),
        "signature":      _signature_out(sig) if sig else None,
    }


async def _lookup_by_view_token(view_token: str) -> dict:
    """Resolve a contract from its view-token. Raises 404 / 410 as needed.

    410 Gone is used when:
        • token expired
        • contract was cancelled (revokes external access)
        • contract was already expired by lifecycle (status="expired")
    """
    c = await db.lumen_contracts.find_one({"view_token": view_token})
    if not c:
        raise HTTPException(status_code=404, detail="Посилання не знайдено або вже неактивне")
    exp = c.get("view_token_expires_at")
    if exp and isinstance(exp, datetime):
        # Mongo stores datetimes as naive by default; normalize to UTC-aware
        # before comparing or we'll crash every public request.
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Посилання прострочено")
    if c.get("status") == "cancelled":
        raise HTTPException(status_code=410, detail="Договір скасовано — посилання деактивовано")
    if c.get("status") == "expired":
        raise HTTPException(status_code=410, detail="Договір прострочено — посилання деактивовано")
    c.pop("_id", None)  # strip Mongo ObjectId before any downstream serialization
    return c


@router.get("/contracts/view/{view_token}")
async def public_contract_view(view_token: str, request: Request):
    """Public read: opens the contract for an unauthenticated visitor."""
    c = await _lookup_by_view_token(view_token)
    now = _now()
    # First open marks `viewed` + bumps view_count (sent → viewed only)
    set_patch: dict[str, Any] = {"updated_at": now}
    inc_patch = {"view_count": 1}
    if c.get("status") in ("generated", "sent"):
        set_patch["status"] = "viewed"
        set_patch["viewed_at"] = now
        c["status"], c["viewed_at"] = "viewed", now
    await db.lumen_contracts.update_one(
        {"id": c["id"]},
        {"$set": set_patch, "$inc": inc_patch,
         "$push": {"view_log": {
             "at": now,
             "ip": (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
                    or (request.client.host if request.client else None)),
             "ua": request.headers.get("user-agent"),
         }}},
    )
    sig = await db.lumen_signatures.find_one({"contract_id": c["id"], "status": "signed"})
    return _public_contract_out(c, sig)


@router.get("/contracts/view/{view_token}/download")
async def public_contract_download(view_token: str):
    """Public PDF download via the view-token. Same protections as /view."""
    c = await _lookup_by_view_token(view_token)
    sig = await db.lumen_signatures.find_one({"contract_id": c["id"], "status": "signed"})
    pdf_bytes = render_contract_pdf(c, sig)
    fname = f"{c.get('number', 'contract')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


class _PublicSignPayload(BaseModel):
    agree: bool = False
    signer_name: Optional[str] = None       # confirmation of "I am ..."
    signer_email: Optional[str] = None      # MUST match contract investor_email
    signer_tax_id: Optional[str] = None     # OPTIONAL — adds extra evidence


@router.post("/contracts/view/{view_token}/sign")
async def public_contract_sign(view_token: str, payload: _PublicSignPayload,
                                request: Request):
    """Public signature acceptance from the one-time link.

    Identity is anchored to the contract's `investor_email`:
        • payload.signer_email is REQUIRED and must match the stored email
          (case-insensitive). Anything else is rejected with 403.
        • A signature record is stored with full IP + UA evidence.
        • The same activation logic as the in-cabinet flow runs after sign
          (open payment requests, fire notifications, audit-write).
    """
    if not payload.agree:
        raise HTTPException(
            status_code=400,
            detail="Для підписання потрібно підтвердити згоду з умовами договору",
        )
    c = await _lookup_by_view_token(view_token)

    if c.get("status") == "signed":
        raise HTTPException(status_code=409, detail="Договір вже підписано")
    if c.get("status") not in _SIGNABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Договір не можна підписати (статус: "
                   f"{CONTRACT_STATUS_LABELS.get(c.get('status'), c.get('status'))})",
        )

    # Identity check — anchor to contract's investor_email.
    stored_user = await db.users.find_one({"user_id": c.get("investor_id")}) or {}
    expected_email = (stored_user.get("email") or "").strip().lower()
    supplied_email = (payload.signer_email or "").strip().lower()
    if not supplied_email:
        raise HTTPException(status_code=400,
                            detail="Вкажіть e-mail, на який було надіслано посилання")
    if expected_email and supplied_email != expected_email:
        # NOTE: do not echo the expected address back — that would be a leak.
        raise HTTPException(status_code=403,
                            detail="E-mail не співпадає з адресою отримувача договору")

    now = _now()
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or \
        (request.client.host if request.client else None)
    user_agent = request.headers.get("user-agent")

    signature = {
        "id": str(uuid.uuid4()),
        "contract_id": c["id"],
        "user_id": c.get("investor_id"),
        "status": "signed",
        "signed_at": now,
        "ip": ip,
        "user_agent": user_agent,
        "source": "public_view_token",
        "signer_name":   (payload.signer_name or "").strip() or None,
        "signer_email":  supplied_email,
        "signer_tax_id": (payload.signer_tax_id or "").strip() or None,
        "created_at": now,
    }

    # PHASE S2 — race condition fix: atomic compare-and-swap.
    # The previous read-then-update path allowed N parallel signers to all
    # pass the status check, then all insert a signature row, then all flip
    # the contract to "signed". Now we ONLY flip status if it's still
    # signable. Whoever wins the CAS gets to record the signature; the
    # others see modified_count == 0 and get a 409.
    cas = await db.lumen_contracts.update_one(
        {"id": c["id"], "status": {"$in": list(_SIGNABLE_STATUSES)}},
        {"$set": {"status": "signed", "signed_at": now, "updated_at": now,
                  # Auto-invalidate the view-token after a successful sign
                  # so a leaked link can't be re-used for replay.
                  "view_token": None,
                  "view_token_expires_at": None,
                  "view_token_consumed_at": now}},
    )
    if cas.modified_count == 0:
        # Someone else won the race, or the contract moved into a non-signable
        # state in the meantime. Re-read to give a precise error.
        fresh = await db.lumen_contracts.find_one({"id": c["id"]}, {"status": 1})
        cur = (fresh or {}).get("status") or c.get("status")
        if cur == "signed":
            raise HTTPException(status_code=409, detail="Договір вже підписано")
        raise HTTPException(
            status_code=409,
            detail=f"Договір не можна підписати (статус: "
                   f"{CONTRACT_STATUS_LABELS.get(cur, cur)})",
        )

    await db.lumen_signatures.insert_one(signature)

    # IR0.3 — field-level history
    try:
        from lumen_field_changes import record_change as _ir0_record
        await _ir0_record(
            db, entity_type="contract", entity_id=c["id"],
            field="status", old_value=c.get("status"), new_value="signed",
            actor={"id": c.get("investor_id"), "email": supplied_email,
                   "role": "investor"},
            source="public_view_token", reason="external signature",
        )
    except Exception:
        pass

    # Same activation hooks as the in-cabinet sign endpoint.
    try:
        from lumen_investment_core import activate_ready_investments, _notify
        from lumen_payments import open_payment_requests_for_investor
        await activate_ready_investments(c.get("investor_id"),
                                          actor_id=c.get("investor_id"))
        pay_res = await open_payment_requests_for_investor(
            c.get("investor_id"), actor_id=c.get("investor_id"))
        await _notify(
            c.get("investor_id"),
            "Договір підписано через зовнішнє посилання",
            f"Договір {c.get('number')} підписано. "
            f"IP: {ip or '—'}.  Інвестиція очікує оплати.",
        )
    except Exception as e:
        logger.warning(f"post-sign activation hook failed: {e}")
        pay_res = {"opened": 0}

    await write_audit(
        action="contract.sign.public", category="contract",
        target_type="lumen_contracts", target_id=c["id"],
        actor={"id": c.get("investor_id"), "email": supplied_email, "role": "investor"},
        request=request,
        summary=f"Contract signed via public view-token: {c.get('number')}",
        meta={
            "view_token_tail": view_token[-8:],
            "signer_name":  payload.signer_name,
            "signer_email": supplied_email,
            "payment_requests_opened": pay_res.get("opened", 0),
        },
    )
    return {
        "contract_id": c["id"],
        "status": "signed",
        "signed_at": _iso(now),
        "signature": _signature_out(signature),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Admin: issue / rotate / revoke a view-token
# ──────────────────────────────────────────────────────────────────────────────

class _ViewLinkPayload(BaseModel):
    expires_in_days: Optional[int] = 30


def _gen_view_token() -> str:
    # ~32 chars URL-safe; collision-resistant.
    return secrets.token_urlsafe(24).replace("-", "").replace("_", "")[:32]


@router.post("/admin/contracts/{contract_id}/view-link")
async def admin_issue_view_link(contract_id: str, payload: _ViewLinkPayload,
                                 admin=Depends(require_admin)):
    """Issue or rotate a public view-token for an existing contract."""
    c = await db.lumen_contracts.find_one({"id": contract_id})
    if not c:
        raise HTTPException(status_code=404, detail="Договір не знайдено")
    if c.get("status") in ("cancelled", "expired"):
        raise HTTPException(status_code=409,
                            detail=f"Не можна випустити посилання для договору у статусі '{c.get('status')}'")
    days = max(1, min(int(payload.expires_in_days or 30), 365))
    token = _gen_view_token()
    expires = datetime.now(timezone.utc) + timedelta(days=days)
    now = _now()
    await db.lumen_contracts.update_one(
        {"id": contract_id},
        {"$set": {
            "view_token": token,
            "view_token_expires_at": expires,
            "view_token_issued_at": now,
            "view_token_issued_by": admin.get("id") or admin.get("user_id"),
            "updated_at": now,
        }},
    )
    await write_audit(
        action="contract.view_link.issue", category="contract",
        target_type="lumen_contracts", target_id=contract_id,
        actor=admin,
        summary=f"Public view-link issued for contract {c.get('number')}",
        meta={"expires_in_days": days, "view_token_tail": token[-8:]},
    )
    return {
        "contract_id": contract_id,
        "view_token":  token,
        "expires_at":  _iso(expires),
        "view_url":    f"/c/view/{token}",
    }


@router.delete("/admin/contracts/{contract_id}/view-link")
async def admin_revoke_view_link(contract_id: str, admin=Depends(require_admin)):
    """Revoke any active view-token for the contract."""
    c = await db.lumen_contracts.find_one({"id": contract_id})
    if not c:
        raise HTTPException(status_code=404, detail="Договір не знайдено")
    now = _now()
    await db.lumen_contracts.update_one(
        {"id": contract_id},
        {"$set": {"view_token": None, "view_token_expires_at": None,
                  "view_token_revoked_at": now, "updated_at": now}},
    )
    await write_audit(
        action="contract.view_link.revoke", category="contract",
        target_type="lumen_contracts", target_id=contract_id,
        actor=admin,
        summary=f"Public view-link revoked for contract {c.get('number')}",
    )
    return {"contract_id": contract_id, "revoked_at": _iso(now)}


# ---- Admin --------------------------------------------------------------------

@router.get("/admin/contracts")
async def admin_contracts(status: Optional[str] = None, asset_id: Optional[str] = None,
                          _=Depends(require_admin)):
    q: dict[str, Any] = {}
    if status:
        if status not in CONTRACT_STATUSES:
            raise HTTPException(status_code=400, detail=f"Невідомий статус: {status}")
        q["status"] = status
    if asset_id:
        q["asset_id"] = asset_id
    items = []
    async for c in db.lumen_contracts.find(q).sort("created_at", -1).limit(500):
        out = _contract_out(c)
        u = await db.users.find_one({"user_id": c["investor_id"]}) or {}
        out["investor_email"] = u.get("email")
        items.append(out)
    counts = {}
    for s in CONTRACT_STATUSES:
        counts[s] = await db.lumen_contracts.count_documents({"status": s})
    return {"items": items, "total": len(items), "counts": counts}


@router.get("/admin/contracts/{contract_id}")
async def admin_contract_detail(contract_id: str, _=Depends(require_admin)):
    c = await db.lumen_contracts.find_one({"id": contract_id})
    if not c:
        raise HTTPException(status_code=404, detail="Договір не знайдено")
    out = _contract_out(c)
    u = await db.users.find_one({"user_id": c["investor_id"]}) or {}
    out["investor_email"] = u.get("email")
    sigs = []
    async for s in db.lumen_signatures.find({"contract_id": contract_id}).sort("created_at", -1):
        sigs.append(_signature_out(s))
    out["signatures"] = sigs
    inv = await db.lumen_investments.find_one({"id": c.get("investment_id")}) or {}
    out["investment_status"] = inv.get("status")
    return out


class CancelPayload(BaseModel):
    reason: str


@router.post("/admin/contracts/{contract_id}/cancel")
async def admin_cancel_contract(contract_id: str, payload: CancelPayload,
                                admin=Depends(require_admin)):
    reason = (payload.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Причина скасування обов'язкова")
    c = await db.lumen_contracts.find_one({"id": contract_id})
    if not c:
        raise HTTPException(status_code=404, detail="Договір не знайдено")
    if c.get("status") == "signed":
        raise HTTPException(status_code=409, detail="Підписаний договір не можна скасувати")
    if c.get("status") not in _CANCELLABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Договір не можна скасувати (статус: {c.get('status')})")
    now = _now()
    await db.lumen_contracts.update_one(
        {"id": contract_id},
        {"$set": {"status": "cancelled", "cancelled_at": now,
                  "cancel_reason": reason, "updated_at": now}},
    )
    # the linked investment is cancelled as well (it can never activate)
    inv = await db.lumen_investments.find_one({"id": c.get("investment_id")})
    if inv and inv.get("status") in ("kyc_pending", "contract_pending", "pending_payment"):
        await db.lumen_investments.update_one(
            {"id": inv["id"]},
            {"$set": {"status": "cancelled", "updated_at": now},
             "$push": {"history": {
                 "status": "cancelled", "at": now, "by": admin["id"],
                 "comment": f"Договір скасовано: {reason}",
             }}},
        )
    from lumen_investment_core import _notify
    await _notify(
        c["investor_id"],
        "Договір скасовано",
        f"Договір {c.get('number')} скасовано адміністратором. Причина: {reason}.",
    )
    return {"contract_id": contract_id, "status": "cancelled", "reason": reason}


# ---- Admin: templates -----------------------------------------------------------

@router.get("/admin/contract-templates")
async def admin_templates(_=Depends(require_admin)):
    items = []
    async for t in db.lumen_contract_templates.find({}).sort("created_at", 1):
        items.append(_template_out(t))
    return {"items": items, "total": len(items)}


class TemplatePayload(BaseModel):
    name: Optional[str] = None
    kind: Optional[str] = None
    body_text: Optional[str] = None
    active: Optional[bool] = None


@router.post("/admin/contract-templates")
async def admin_create_template(payload: TemplatePayload, _=Depends(require_admin)):
    if not (payload.name or "").strip() or not (payload.body_text or "").strip():
        raise HTTPException(status_code=400, detail="Потрібні name та body_text")
    kind = payload.kind or "investment_agreement"
    if kind not in TEMPLATE_KINDS:
        raise HTTPException(status_code=400, detail=f"Невідомий тип шаблону: {kind}")
    now = _now()
    tpl = {
        "id": str(uuid.uuid4()),
        "kind": kind,
        "name": payload.name.strip(),
        "body_text": payload.body_text,
        "version": 1,
        "active": payload.active if payload.active is not None else True,
        "created_at": now,
        "updated_at": now,
    }
    await db.lumen_contract_templates.insert_one(tpl)
    return _template_out(tpl)


@router.patch("/admin/contract-templates/{template_id}")
async def admin_update_template(template_id: str, payload: TemplatePayload,
                                _=Depends(require_admin)):
    tpl = await db.lumen_contract_templates.find_one({"id": template_id})
    if not tpl:
        raise HTTPException(status_code=404, detail="Шаблон не знайдено")
    patch: dict[str, Any] = {}
    if payload.name is not None:
        patch["name"] = payload.name.strip()
    if payload.kind is not None:
        if payload.kind not in TEMPLATE_KINDS:
            raise HTTPException(status_code=400, detail=f"Невідомий тип шаблону: {payload.kind}")
        patch["kind"] = payload.kind
    if payload.body_text is not None:
        patch["body_text"] = payload.body_text
        patch["version"] = int(tpl.get("version") or 1) + 1
    if payload.active is not None:
        patch["active"] = payload.active
    if not patch:
        raise HTTPException(status_code=400, detail="Немає полів для оновлення")
    patch["updated_at"] = _now()
    await db.lumen_contract_templates.update_one({"id": template_id}, {"$set": patch})
    tpl = await db.lumen_contract_templates.find_one({"id": template_id})
    return _template_out(tpl)
