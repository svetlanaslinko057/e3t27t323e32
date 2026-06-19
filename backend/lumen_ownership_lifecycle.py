"""
lumen_ownership_lifecycle.py — LUMEN 2.0 / Phase A3 — Ownership Lifecycle.

Closes the gap between a purchase and a certificate by making the ownership
chain CANONICAL and fully traceable:

    Intent → KYC → Contract → Payment → Funding Confirmed →
    Ownership Created → Certificate Issued → Active → Payouts → Withdrawal

Source of truth stays distributed across the real domain entities; this module
DERIVES the canonical lifecycle (it does not duplicate truth). It also:

  • Block 1  Certificate Binding   — mandatory ownership_id ↔ certificate_id link
  • Block 2  Lifecycle Engine      — canonical state machine + investor timeline
  • Block 5  Portfolio Timeline 2.0— investor-facing 8-step journey
  • Block 6  Ownership Explorer    — admin full trace (investment→payment→ledger→
                                      ownership→certificate→payouts→secondary)

Blocks 3 (canonical ownership event kinds) and 4 (certificate ownership events)
live in lumen_unit_registry / lumen_certificates respectively and are emitted by
those engines; this module reads/links them.
"""
from __future__ import annotations

import logging
from shared.money import fmt_uah_as_usd, usd_from_uah  # USD display layer
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from lumen_api import db

logger = logging.getLogger("lumen.lifecycle")

LIFECYCLE_EVENTS = "lumen_lifecycle_events"

# Canonical lifecycle states (ordered)
STATES = [
    "intent_created",
    "kyc_pending",
    "kyc_approved",
    "contract_pending",
    "contract_signed",
    "payment_pending",
    "payment_confirmed",
    "ownership_created",
    "certificate_issued",
    "active",
]
STATE_INDEX = {s: i for i, s in enumerate(STATES)}

STATE_LABELS = {
    "intent_created":     "Заявка створена",
    "kyc_pending":        "Очікує KYC",
    "kyc_approved":       "KYC підтверджено",
    "contract_pending":   "Очікує підпис договору",
    "contract_signed":    "Договір підписано",
    "payment_pending":    "Очікує оплату",
    "payment_confirmed":  "Оплату підтверджено",
    "ownership_created":  "Володіння створено",
    "certificate_issued": "Сертифікат випущено",
    "active":             "Активна інвестиція",
}


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Any) -> Any:
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
    return v


def _strip(d: Optional[dict]) -> Optional[dict]:
    if not d:
        return d
    d = {k: v for k, v in d.items() if k != "_id"}
    for k, v in list(d.items()):
        if isinstance(v, datetime):
            d[k] = _iso(v)
    return d


def _hist_at(investment: dict, *statuses: str) -> Optional[datetime]:
    """Find the timestamp a given status appeared in the investment history."""
    for h in investment.get("history", []) or []:
        if h.get("status") in statuses:
            return h.get("at")
    return None


async def ensure_indexes() -> None:
    try:
        await db[LIFECYCLE_EVENTS].create_index([("investment_id", 1), ("created_at", -1)])
        await db[LIFECYCLE_EVENTS].create_index([("investor_id", 1), ("created_at", -1)])
        await db.lumen_certificates.create_index([("ownership_id", 1)])
    except Exception:
        logger.exception("lifecycle indexes failed")


# ──────────────────────────────────────────────────────────────────────────────
# Block 1 — Certificate Binding
# ──────────────────────────────────────────────────────────────────────────────

async def bind_all() -> dict:
    """Make the ownership ↔ certificate link mandatory & consistent.
    For every active certificate, link it to its ownership row (both ways)."""
    bound = 0
    async for cert in db.lumen_certificates.find({"status": "active"}):
        own = await db.lumen_ownerships.find_one(
            {"investor_id": cert["investor_id"], "asset_id": cert["asset_id"]})
        if not own:
            continue
        changed = False
        if cert.get("ownership_id") != own["id"]:
            await db.lumen_certificates.update_one(
                {"id": cert["id"]}, {"$set": {"ownership_id": own["id"], "updated_at": _now()}})
            changed = True
        if own.get("certificate_id") != cert["id"]:
            await db.lumen_ownerships.update_one(
                {"id": own["id"]},
                {"$set": {"certificate_id": cert["id"],
                          "certificate_number": cert.get("certificate_number"),
                          "updated_at": _now()}})
            changed = True
        if changed:
            bound += 1
    # clear stale certificate_id on ownerships whose active cert no longer matches
    async for own in db.lumen_ownerships.find({"certificate_id": {"$ne": None}}):
        cert = await db.lumen_certificates.find_one(
            {"id": own.get("certificate_id")})
        if not cert or cert.get("status") != "active":
            # re-point to the current active cert if any
            active = await db.lumen_certificates.find_one(
                {"investor_id": own["investor_id"], "asset_id": own["asset_id"], "status": "active"})
            await db.lumen_ownerships.update_one(
                {"id": own["id"]},
                {"$set": {"certificate_id": (active or {}).get("id"),
                          "certificate_number": (active or {}).get("certificate_number"),
                          "updated_at": _now()}})
    return {"bound": bound}


# ──────────────────────────────────────────────────────────────────────────────
# Block 2 — Lifecycle Engine
# ──────────────────────────────────────────────────────────────────────────────

async def _kyc_state(investor_id: str) -> Dict[str, Any]:
    prof = await db.lumen_investor_profiles.find_one(
        {"user_id": investor_id}, {"kyc_status": 1, "kyc_approved_at": 1, "updated_at": 1})
    if not prof:
        user = await db.users.find_one({"user_id": investor_id}, {"kyc_status": 1}) or {}
        return {"approved": user.get("kyc_status") == "approved", "at": None}
    return {"approved": prof.get("kyc_status") == "approved",
            "at": prof.get("kyc_approved_at") or (prof.get("updated_at") if prof.get("kyc_status") == "approved" else None),
            "status": prof.get("kyc_status")}


async def compute_lifecycle(investment: dict) -> dict:
    """Derive the canonical lifecycle + 8-step investor timeline for an investment."""
    investor_id = investment["investor_id"]
    asset_id = investment["asset_id"]

    intent = await db.lumen_investor_intents.find_one({"id": investment.get("intent_id")}) \
        if investment.get("intent_id") else None
    kyc = await _kyc_state(investor_id)
    contract = await db.lumen_contracts.find_one({"id": investment.get("contract_id")}) \
        if investment.get("contract_id") else None
    payment = await db.lumen_payment_requests.find_one(
        {"investment_id": investment["id"]}, sort=[("created_at", -1)])
    ownership = await db.lumen_ownerships.find_one(
        {"investor_id": investor_id, "asset_id": asset_id})
    cert = await db.lumen_certificates.find_one(
        {"investor_id": investor_id, "asset_id": asset_id, "status": "active"})
    first_payout = await db.lumen_payouts.find_one(
        {"investor_id": investor_id, "asset_id": asset_id}, sort=[("created_at", 1)])
    if not first_payout:
        first_payout = await db.lumen_payout_records.find_one(
            {"investor_id": investor_id, "asset_id": asset_id}, sort=[("created_at", 1)])
    withdrawal = await db.lumen_withdrawal_requests.find_one(
        {"investor_id": investor_id, "status": {"$in": ["approved", "paid", "completed"]}},
        sort=[("created_at", 1)])

    inv_status = investment.get("status")
    is_active = inv_status == "active"
    has_units = bool(ownership and (ownership.get("units_int") or ownership.get("units")))
    contract_signed = bool(contract and contract.get("status") == "signed")
    payment_confirmed = bool(payment and payment.get("status") in ("confirmed", "paid")) or is_active

    # canonical state (highest reached)
    if is_active:
        state = "active"
    elif cert:
        state = "certificate_issued"
    elif has_units:
        state = "ownership_created"
    elif payment_confirmed:
        state = "payment_confirmed"
    elif payment:
        state = "payment_pending"
    elif contract_signed:
        state = "contract_signed"
    elif contract:
        state = "contract_pending"
    elif kyc["approved"]:
        state = "kyc_approved"
    elif inv_status == "kyc_pending":
        state = "kyc_pending"
    else:
        state = "intent_created"

    # 8-step investor timeline (Block 5)
    def step(key, label, done, at, detail=None, current=False):
        return {"key": key, "label": label,
                "status": "done" if done else ("current" if current else "pending"),
                "at": _iso(at) if at else None, "detail": detail}

    steps = [
        step("intent", "Заявка", bool(intent) or bool(investment),
             (intent or {}).get("submitted_at") or investment.get("created_at"),
             fmt_uah_as_usd(investment.get('amount', 0))),
        step("kyc", "KYC", kyc["approved"], kyc.get("at"),
             "Верифікацію пройдено" if kyc["approved"] else "Очікує верифікації",
             current=(not kyc["approved"] and inv_status == "kyc_pending")),
        step("contract", "Договір", contract_signed,
             (contract or {}).get("signed_at") or _hist_at(investment, "contract_pending"),
             (contract or {}).get("contract_number") or "Договір",
             current=(kyc["approved"] and not contract_signed and contract is not None)),
        step("payment", "Оплата", payment_confirmed,
             (payment or {}).get("confirmed_at") or investment.get("invested_at")
             or _hist_at(investment, "active"),
             "Кошти отримано" if payment_confirmed else "Очікує оплату",
             current=(contract_signed and not payment_confirmed)),
        step("certificate", "Сертифікат", bool(cert), (cert or {}).get("issue_date"),
             (cert or {}).get("certificate_number")),
        step("active", "Активна інвестиція", is_active,
             investment.get("invested_at") or _hist_at(investment, "active"),
             "Інвестиція активна"),
        step("first_payout", "Перша виплата", bool(first_payout),
             (first_payout or {}).get("created_at"),
             (fmt_uah_as_usd((first_payout or {}).get('amount', 0))) if first_payout else "Ще не було"),
        step("withdrawal", "Виведення доходу", bool(withdrawal),
             (withdrawal or {}).get("created_at"),
             "Дохід виведено" if withdrawal else "Ще не виводився"),
    ]

    progress = sum(1 for s in steps if s["status"] == "done")
    return {
        "investment_id": investment["id"],
        "investor_id": investor_id,
        "asset_id": asset_id,
        "asset_title": investment.get("asset_title"),
        "amount": investment.get("amount"),
        "canonical_state": state,
        "canonical_state_label": STATE_LABELS.get(state, state),
        "state_index": STATE_INDEX.get(state, 0),
        "ownership_id": (ownership or {}).get("id"),
        "certificate_id": (cert or {}).get("id"),
        "certificate_number": (cert or {}).get("certificate_number"),
        "units": int((ownership or {}).get("units_int") or 0),
        "steps": steps,
        "progress": progress,
        "total_steps": len(steps),
    }


async def persist_state(investment: dict, computed: dict) -> None:
    """Persist canonical state on investment + emit lifecycle event on change."""
    prev = investment.get("lifecycle_state")
    new = computed["canonical_state"]
    if prev == new:
        return
    await db.lumen_investments.update_one(
        {"id": investment["id"]},
        {"$set": {"lifecycle_state": new, "lifecycle_state_at": _now()}})
    await db[LIFECYCLE_EVENTS].insert_one({
        "id": f"lce-{investment['id'][:8]}-{STATE_INDEX.get(new, 0)}-{int(_now().timestamp())}",
        "investment_id": investment["id"],
        "investor_id": investment["investor_id"],
        "asset_id": investment["asset_id"],
        "from_state": prev,
        "to_state": new,
        "created_at": _now(),
    })


async def reconcile_all() -> dict:
    """Bind certificates + refresh canonical state for every investment."""
    await ensure_indexes()
    binding = await bind_all()
    advanced = 0
    async for inv in db.lumen_investments.find({}):
        try:
            computed = await compute_lifecycle(inv)
            if inv.get("lifecycle_state") != computed["canonical_state"]:
                await persist_state(inv, computed)
                advanced += 1
        except Exception:
            logger.exception("lifecycle reconcile failed for investment %s", inv.get("id"))
    return {"bound": binding["bound"], "state_changes": advanced}


# ──────────────────────────────────────────────────────────────────────────────
# Block 6 — Ownership Explorer (admin full trace)
# ──────────────────────────────────────────────────────────────────────────────

async def trace_ownership(investor_id: str, asset_id: str) -> dict:
    ownership = await db.lumen_ownerships.find_one(
        {"investor_id": investor_id, "asset_id": asset_id})

    investments = []
    async for inv in db.lumen_investments.find(
            {"investor_id": investor_id, "asset_id": asset_id}).sort("created_at", 1):
        investments.append(_strip(inv))

    payments = []
    inv_ids = [i["id"] for i in investments]
    async for p in db.lumen_payment_requests.find(
            {"investment_id": {"$in": inv_ids}}).sort("created_at", 1):
        payments.append(_strip(p))

    ledger = []
    async for le in db.lumen_ledger_entries.find(
            {"investor_id": investor_id}).sort("created_at", -1).limit(50):
        # keep only entries that reference this asset where possible
        if le.get("asset_id") in (None, asset_id):
            ledger.append(_strip(le))

    certificates = []
    async for c in db.lumen_certificates.find(
            {"investor_id": investor_id, "asset_id": asset_id}).sort("issue_date", -1):
        certificates.append(_strip(c))

    payouts = []
    async for po in db.lumen_payouts.find(
            {"investor_id": investor_id, "asset_id": asset_id}).sort("created_at", -1).limit(50):
        payouts.append(_strip(po))

    trades = []
    async for t in db.lumen_secondary_trades.find(
            {"asset_id": asset_id,
             "$or": [{"buyer_id": investor_id}, {"seller_id": investor_id}]}
    ).sort("created_at", -1).limit(50):
        trades.append(_strip(t))

    ownership_events = []
    async for e in db.lumen_ownership_events.find(
            {"asset_id": asset_id, "investor_id": investor_id}).sort("created_at", -1).limit(50):
        ownership_events.append(_strip(e))

    # lifecycle from the latest active (or last) investment
    primary_inv = None
    for inv in reversed(investments):
        if inv.get("status") == "active":
            primary_inv = inv
            break
    primary_inv = primary_inv or (investments[-1] if investments else None)
    raw_inv = await db.lumen_investments.find_one({"id": primary_inv["id"]}) if primary_inv else None
    lifecycle = await compute_lifecycle(raw_inv) if raw_inv else None

    name = await db.users.find_one(
        {"$or": [{"user_id": investor_id}, {"id": investor_id}]}, {"name": 1, "email": 1})

    return {
        "investor_id": investor_id,
        "investor_name": (name or {}).get("name") or (name or {}).get("email") or investor_id,
        "asset_id": asset_id,
        "ownership": _strip(ownership),
        "lifecycle": lifecycle,
        "investments": investments,
        "payments": payments,
        "ledger": ledger,
        "certificates": certificates,
        "payouts": payouts,
        "secondary_trades": trades,
        "ownership_events": ownership_events,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Router
# ──────────────────────────────────────────────────────────────────────────────

def build_lifecycle_router(db_ignored, get_current_user, require_admin) -> APIRouter:
    try:
        from lumen_api import lr2_perm as _lr2_perm
    except Exception:  # pragma: no cover
        def _lr2_perm(*a, **k): return require_admin  # type: ignore
    router = APIRouter(prefix="/api", tags=["ownership-lifecycle"])

    # ---- Investor: Portfolio Timeline 2.0 -----------------------------------
    @router.get("/investor/lifecycle")
    async def my_lifecycle(user=Depends(get_current_user)):
        items = []
        async for inv in db.lumen_investments.find(
                {"investor_id": user["id"]}).sort("created_at", -1):
            items.append(await compute_lifecycle(inv))
        return {"items": items, "total": len(items)}

    @router.get("/investor/lifecycle/{investment_id}")
    async def my_lifecycle_detail(investment_id: str, user=Depends(get_current_user)):
        inv = await db.lumen_investments.find_one(
            {"id": investment_id, "investor_id": user["id"]})
        if not inv:
            raise HTTPException(status_code=404, detail="Інвестицію не знайдено")
        return await compute_lifecycle(inv)

    # ---- Admin: Ownership Explorer (trace) ----------------------------------
    @router.get("/admin/ownership/trace")
    async def admin_trace(investor_id: str, asset_id: str, _=Depends(require_admin)):
        return await trace_ownership(investor_id, asset_id)

    @router.get("/admin/ownership/{ownership_id}/trace")
    async def admin_trace_by_id(ownership_id: str, _=Depends(require_admin)):
        own = await db.lumen_ownerships.find_one({"id": ownership_id})
        if not own:
            raise HTTPException(status_code=404, detail="Володіння не знайдено")
        return await trace_ownership(own["investor_id"], own["asset_id"])

    @router.get("/admin/lifecycle/states")
    async def admin_states(_=Depends(require_admin)):
        counts: Dict[str, int] = {}
        for s in STATES:
            counts[s] = await db.lumen_investments.count_documents({"lifecycle_state": s})
        return {"states": STATES, "labels": STATE_LABELS, "counts": counts}

    @router.post("/admin/lifecycle/reconcile")
    async def admin_reconcile(_=Depends(require_admin),
                              _perm=Depends(_lr2_perm("certificate", "override"))):
        return await reconcile_all()

    return router
