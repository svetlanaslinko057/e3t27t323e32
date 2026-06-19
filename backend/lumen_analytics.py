"""
Sprint 9 — Investor Analytics & Fund Intelligence.

АРХІТЕКТУРНИЙ ПРИНЦИП SPRINT 9 (критично):
    Усі метрики рахуються НАЖИВО з реєстрів — джерел істини:
        lumen_ledger_entries  — рух коштів (credit/debit, reason)
        lumen_ownerships      — частки інвесторів (units = вкладений капітал)
        lumen_investments     — інвестиції (життєвий цикл)
        lumen_payout_records  — нарахування доходу
        lumen_assets          — активи (категорія/локація/ризики/статус)
        lumen_withdrawal_requests / lumen_payment_requests / lumen_asset_reports
    ЖОДНИХ збережених KPI / materialized totals у Mongo. Sprint 9 — це перевірка,
    що Ledger справді є джерелом істини всієї системи.

Заборони Sprint 9: без вторинного ринку, податкових форм, банк-експорту, CRM,
AI-рекомендацій.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends

from lumen_api import db, get_current_user, require_admin, _now, _iso
from lumen_payments import _round2

logger = logging.getLogger("lumen.analytics")

router = APIRouter(prefix="/api", tags=["lumen-analytics"])

# ──────────────────────────────────────────────────────────────────────────────
# Labels & constants
# ──────────────────────────────────────────────────────────────────────────────

CATEGORY_LABELS = {
    "real_estate":  "Нерухомість",
    "land":         "Земля",
    "commercial":   "Комерція",
    "construction": "Будівництво",
}
RISK_LABELS = {"low": "Низький", "medium": "Середній", "high": "Високий", "unknown": "Невизначений"}
RISK_RANK = {"low": 1, "medium": 2, "high": 3}

# Asset-health thresholds — constants for now (admin-config deferred to Sprint 10).
HEALTH_OVERDUE_WARN_DAYS = 7
HEALTH_OVERDUE_CRIT_DAYS = 30
HEALTH_REPORT_WARN_DAYS = 90
HEALTH_REPORT_CRIT_DAYS = 180

PENDING_WITHDRAWAL_STATUSES = ["requested", "under_review", "approved", "processing"]
PENDING_FUNDING_STATUSES = ["awaiting_payment", "paid", "under_review"]
PENDING_PAYOUT_STATUSES = ["planned", "generated", "approved"]

_HEALTH_ORDER = {"healthy": 0, "warning": 1, "critical": 2}
_YEAR_SECONDS = 365.25 * 86400


def _aware(dt: Any) -> Optional[datetime]:
    if not isinstance(dt, datetime):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _worst(a: str, b: str) -> str:
    return a if _HEALTH_ORDER.get(a, 0) >= _HEALTH_ORDER.get(b, 0) else b


def _category_label(key: Optional[str]) -> str:
    return CATEGORY_LABELS.get(key or "", (key or "Інше").capitalize())


def _asset_region(asset: dict) -> str:
    loc = (asset.get("location") or "").strip()
    if not loc:
        return "Інше"
    return loc.split(",")[0].strip() or "Інше"


def _asset_risk_level(asset: dict) -> str:
    best, rank = "unknown", 0
    for r in (asset.get("risks") or []):
        sev = r.get("severity")
        if sev in RISK_RANK and RISK_RANK[sev] > rank:
            rank, best = RISK_RANK[sev], sev
    return best


async def _load_assets_map() -> dict[str, dict]:
    out: dict[str, dict] = {}
    async for a in db.lumen_assets.find({}):
        out[a.get("id")] = a
    return out


def _alloc_rows(group: dict[str, float], total: float, label_fn) -> list[dict]:
    rows = [
        {"key": k, "label": label_fn(k), "amount": _round2(v),
         "percent": _round2(v / total * 100) if total else 0.0}
        for k, v in group.items() if v > 0
    ]
    rows.sort(key=lambda x: -x["amount"])
    return rows


# ──────────────────────────────────────────────────────────────────────────────
# Investor core — single live pass over the registries
# ──────────────────────────────────────────────────────────────────────────────

async def _investor_core(investor_id: str) -> dict:
    assets_map = await _load_assets_map()

    invested_by_asset: dict[str, float] = {}
    share_by_asset: dict[str, float] = {}
    created_by_asset: dict[str, datetime] = {}
    async for o in db.lumen_ownerships.find({"investor_id": investor_id}):
        u = float(o.get("units") or 0)
        if u <= 0:
            continue
        aid = o.get("asset_id")
        invested_by_asset[aid] = invested_by_asset.get(aid, 0.0) + u
        share_by_asset[aid] = share_by_asset.get(aid, 0.0) + float(o.get("ownership_percent") or 0)
        ca = _aware(o.get("created_at"))
        if ca and (aid not in created_by_asset or ca < created_by_asset[aid]):
            created_by_asset[aid] = ca

    received_by_asset: dict[str, float] = {}
    last_payout_by_asset: dict[str, datetime] = {}
    funding_date_by_asset: dict[str, datetime] = {}
    async for e in db.lumen_ledger_entries.find({"investor_id": investor_id, "entry_type": "credit"}):
        reason = e.get("reason")
        aid = e.get("asset_id") or "—"
        amt = float(e.get("amount_uah") or 0)
        ca = _aware(e.get("created_at"))
        if reason == "payout":
            received_by_asset[aid] = received_by_asset.get(aid, 0.0) + amt
            if ca and (aid not in last_payout_by_asset or ca > last_payout_by_asset[aid]):
                last_payout_by_asset[aid] = ca
        elif reason == "investment_funding":
            if ca and (aid not in funding_date_by_asset or ca < funding_date_by_asset[aid]):
                funding_date_by_asset[aid] = ca

    expected_by_asset: dict[str, float] = {}
    next_payout_by_asset: dict[str, datetime] = {}
    earliest_planned_by_asset: dict[str, datetime] = {}
    async for r in db.lumen_payout_records.find({"investor_id": investor_id}):
        aid = r.get("asset_id") or "—"
        pd = _aware(r.get("planned_date"))
        if pd and (aid not in earliest_planned_by_asset or pd < earliest_planned_by_asset[aid]):
            earliest_planned_by_asset[aid] = pd
        if r.get("status") in PENDING_PAYOUT_STATUSES:
            amt = float(r.get("amount_uah") or 0)
            expected_by_asset[aid] = expected_by_asset.get(aid, 0.0) + amt
            if pd and (aid not in next_payout_by_asset or pd < next_payout_by_asset[aid]):
                next_payout_by_asset[aid] = pd

    return dict(
        assets_map=assets_map,
        invested_by_asset=invested_by_asset,
        share_by_asset=share_by_asset,
        created_by_asset=created_by_asset,
        received_by_asset=received_by_asset,
        last_payout_by_asset=last_payout_by_asset,
        funding_date_by_asset=funding_date_by_asset,
        expected_by_asset=expected_by_asset,
        next_payout_by_asset=next_payout_by_asset,
        earliest_planned_by_asset=earliest_planned_by_asset,
    )


def _holding_start(core: dict, aid: str) -> Optional[datetime]:
    cands = [
        core["created_by_asset"].get(aid),
        core["funding_date_by_asset"].get(aid),
        core["earliest_planned_by_asset"].get(aid),
    ]
    cands = [c for c in cands if c is not None]
    return min(cands) if cands else None


# ──────────────────────────────────────────────────────────────────────────────
# Investor: Portfolio + Yield + Allocation (Blocks 1 & 2)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/investor/analytics/overview")
async def investor_overview(user=Depends(get_current_user)):
    iid = user["id"]
    core = await _investor_core(iid)
    inv = core["invested_by_asset"]
    assets_map = core["assets_map"]

    invested_total = _round2(sum(inv.values()))
    received_total = _round2(sum(core["received_by_asset"].values()))
    expected_total = _round2(sum(core["expected_by_asset"].values()))
    # Current value (mark-to-cost): принципал, що залишається розміщеним у активах,
    # + накопичений, але ще не виплачений дохід (receivable).
    current_value = _round2(invested_total + expected_total)

    # Allocation by category / region / risk (за вкладеним капіталом)
    by_cat: dict[str, float] = {}
    by_region: dict[str, float] = {}
    by_risk: dict[str, float] = {}
    for aid, amount in inv.items():
        a = assets_map.get(aid) or {}
        by_cat[a.get("category") or "other"] = by_cat.get(a.get("category") or "other", 0.0) + amount
        reg = _asset_region(a)
        by_region[reg] = by_region.get(reg, 0.0) + amount
        rl = _asset_risk_level(a)
        by_risk[rl] = by_risk.get(rl, 0.0) + amount

    # Yield analytics
    realized_yield = _round2(received_total / invested_total * 100) if invested_total else 0.0
    unrealized_yield = _round2(expected_total / invested_total * 100) if invested_total else 0.0

    now = _now()
    num = den = 0.0
    for aid, amount in inv.items():
        start = _holding_start(core, aid)
        if start is None:
            start = now
        years = max((now - start).total_seconds() / _YEAR_SECONDS, 1.0 / 365.25)
        num += amount * years
        den += amount
    weighted_years = (num / den) if den else 0.0
    annualized_yield = _round2(realized_yield / weighted_years) if weighted_years > 0 else 0.0

    wallet = await db.lumen_wallets.find_one({"investor_id": iid}) or {}

    return {
        "portfolio": {
            "invested_total": invested_total,
            "current_value": current_value,
            "received_total": received_total,
            "expected_total": expected_total,
            "asset_count": len(inv),
            "wallet_available": _round2(float(wallet.get("available_balance") or 0)),
        },
        "yield": {
            "realized_yield": realized_yield,
            "unrealized_yield": unrealized_yield,
            "annualized_yield": annualized_yield,
            "weighted_holding_years": _round2(weighted_years),
        },
        "allocation": {
            "by_category": _alloc_rows(by_cat, invested_total, _category_label),
            "by_region": _alloc_rows(by_region, invested_total, lambda k: k),
            "by_risk": _alloc_rows(by_risk, invested_total, lambda k: RISK_LABELS.get(k, k)),
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# Investor: Asset Performance (Block 3)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/investor/analytics/assets")
async def investor_asset_performance(user=Depends(get_current_user)):
    core = await _investor_core(user["id"])
    inv = core["invested_by_asset"]
    assets_map = core["assets_map"]
    items = []
    for aid, invested in inv.items():
        a = assets_map.get(aid) or {}
        received = _round2(core["received_by_asset"].get(aid, 0.0))
        expected = _round2(core["expected_by_asset"].get(aid, 0.0))
        roi = _round2(received / invested * 100) if invested else 0.0
        items.append({
            "asset_id": aid,
            "asset_title": a.get("title"),
            "category": a.get("category"),
            "category_label": _category_label(a.get("category")),
            "region": _asset_region(a),
            "risk_level": _asset_risk_level(a),
            "risk_label": RISK_LABELS.get(_asset_risk_level(a)),
            "target_yield": a.get("target_yield"),
            "invested": _round2(invested),
            "share_percent": _round2(core["share_by_asset"].get(aid, 0.0)),
            "received": received,
            "expected": expected,
            "roi": roi,
            "last_payout": _iso(core["last_payout_by_asset"].get(aid)) if core["last_payout_by_asset"].get(aid) else None,
            "next_payout": _iso(core["next_payout_by_asset"].get(aid)) if core["next_payout_by_asset"].get(aid) else None,
        })
    items.sort(key=lambda x: -x["invested"])
    return {"items": items, "total": len(items)}


# ──────────────────────────────────────────────────────────────────────────────
# Investor: Timeline (Block 4) — unified event feed (live from registries)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/investor/analytics/timeline")
async def investor_timeline(limit: int = 60, user=Depends(get_current_user)):
    iid = user["id"]
    events: list[dict] = []

    def push(dt, etype, title, description=None, amount=None):
        d = _aware(dt)
        if d is None:
            return
        events.append({
            "date": _iso(d), "_sort": d, "type": etype,
            "title": title, "description": description, "amount": amount,
        })

    # Investments created
    async for inv in db.lumen_investments.find({"investor_id": iid}):
        push(inv.get("created_at") or inv.get("invested_at"), "investment_created",
             "Інвестицію створено",
             f"{inv.get('asset_title') or ''}", float(inv.get("amount") or inv.get("units") or 0))

    # KYC approved
    try:
        kyc = await db.lumen_kyc_documents.find_one(
            {"investor_id": iid, "status": "approved"}, sort=[("updated_at", -1)])
        if kyc:
            push(kyc.get("reviewed_at") or kyc.get("updated_at") or kyc.get("created_at"),
                 "kyc_approved", "KYC підтверджено", "Верифікацію особи завершено")
        else:
            prof = await db.lumen_investor_profiles.find_one({"investor_id": iid})
            if prof and prof.get("kyc_status") == "approved":
                push(prof.get("kyc_reviewed_at") or prof.get("updated_at"),
                     "kyc_approved", "KYC підтверджено", "Верифікацію особи завершено")
    except Exception as ex:
        logger.debug("timeline kyc: %s", ex)

    # Contracts signed
    try:
        async for c in db.lumen_contracts.find({"investor_id": iid, "status": {"$in": ["signed", "active"]}}):
            push(c.get("signed_at") or c.get("updated_at"), "contract_signed",
                 "Договір підписано", c.get("asset_title") or c.get("number"))
    except Exception as ex:
        logger.debug("timeline contracts: %s", ex)

    # Payments confirmed + payouts received (ledger credits)
    async for e in db.lumen_ledger_entries.find({"investor_id": iid, "entry_type": "credit"}):
        reason = e.get("reason")
        if reason == "investment_funding":
            push(e.get("created_at"), "payment_confirmed", "Оплату підтверджено",
                 e.get("notes"), float(e.get("amount_uah") or 0))
        elif reason == "payout":
            push(e.get("created_at"), "payout_received", "Отримано виплату",
                 e.get("notes"), float(e.get("amount_uah") or 0))

    # Withdrawals submitted
    async for w in db.lumen_withdrawal_requests.find({"investor_id": iid}):
        push(w.get("created_at"), "withdrawal_submitted", "Подано заявку на вивід",
             w.get("status_label") or w.get("status"), float(w.get("amount_uah") or w.get("amount") or 0))

    events.sort(key=lambda x: x["_sort"], reverse=True)
    for e in events:
        e.pop("_sort", None)
    limit = min(max(1, limit), 200)
    return {"items": events[:limit], "total": len(events)}


# ──────────────────────────────────────────────────────────────────────────────
# Investor: Portfolio Timeline — 5-stage investment lifecycle
# Invested → Funded → Contract signed → First payout → Withdrawal
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/investor/analytics/portfolio-timeline")
async def investor_portfolio_timeline(user=Depends(get_current_user)):
    iid = user["id"]

    async def _min_date(coll, q, *fields):
        best = None
        async for d in db[coll].find(q):
            for f in fields:
                v = _aware(d.get(f))
                if v and (best is None or v < best):
                    best = v
                    break
        return best

    invested = await _min_date("lumen_investments", {"investor_id": iid}, "created_at", "invested_at")
    funded = await _min_date("lumen_ledger_entries",
                             {"investor_id": iid, "entry_type": "credit", "reason": "investment_funding"}, "created_at")
    signed = await _min_date("lumen_contracts",
                             {"investor_id": iid, "status": {"$in": ["signed", "active"]}}, "signed_at", "updated_at")
    first_payout = await _min_date("lumen_ledger_entries",
                                   {"investor_id": iid, "entry_type": "credit", "reason": "payout"}, "created_at")
    withdrawal = await _min_date("lumen_withdrawal_requests", {"investor_id": iid}, "created_at")

    stages = [
        {"key": "invested",        "label": "Інвестовано",        "date": invested},
        {"key": "funded",          "label": "Профінансовано",     "date": funded},
        {"key": "contract_signed", "label": "Договір підписано",  "date": signed},
        {"key": "first_payout",    "label": "Перша виплата",      "date": first_payout},
        {"key": "withdrawal",      "label": "Вивід коштів",       "date": withdrawal},
    ]
    out = []
    for s in stages:
        out.append({
            "key": s["key"], "label": s["label"],
            "done": s["date"] is not None,
            "date": _iso(s["date"]) if s["date"] else None,
        })
    completed = sum(1 for s in out if s["done"])
    return {"stages": out, "completed": completed, "total_stages": len(out)}


# ──────────────────────────────────────────────────────────────────────────────
# Asset Health engine (Block 6)
# ──────────────────────────────────────────────────────────────────────────────

async def compute_asset_health(asset: dict, now: Optional[datetime] = None) -> dict:
    now = now or _now()
    aid = asset.get("id")
    level = "healthy"
    signals: list[dict] = []

    # 1) Overdue payouts (pending records with planned_date in the past)
    max_overdue = 0
    async for r in db.lumen_payout_records.find(
            {"asset_id": aid, "status": {"$in": PENDING_PAYOUT_STATUSES}}):
        pd = _aware(r.get("planned_date"))
        if pd and pd < now:
            d = (now - pd).days
            if d > max_overdue:
                max_overdue = d
    if max_overdue > HEALTH_OVERDUE_CRIT_DAYS:
        level = _worst(level, "critical")
        signals.append({"kind": "overdue_payout", "severity": "critical",
                        "message": f"Виплата прострочена на {max_overdue} дн."})
    elif max_overdue > HEALTH_OVERDUE_WARN_DAYS:
        level = _worst(level, "warning")
        signals.append({"kind": "overdue_payout", "severity": "warning",
                        "message": f"Виплата прострочена на {max_overdue} дн."})

    # 2) Reports freshness
    latest = await db.lumen_asset_reports.find_one(
        {"asset_id": aid, "published": True}, sort=[("created_at", -1)])
    base = _aware(latest.get("created_at")) if latest else _aware(asset.get("created_at"))
    days_since_report = (now - base).days if base else None
    if days_since_report is not None:
        if days_since_report > HEALTH_REPORT_CRIT_DAYS:
            level = _worst(level, "critical")
            signals.append({"kind": "stale_reports", "severity": "critical",
                            "message": f"Немає звіту {days_since_report} дн."})
        elif days_since_report > HEALTH_REPORT_WARN_DAYS:
            level = _worst(level, "warning")
            signals.append({"kind": "stale_reports", "severity": "warning",
                            "message": f"Немає звіту {days_since_report} дн."})

    # 3) Paused payout plan
    paused_plan = await db.lumen_payout_plans.find_one({"asset_id": aid, "status": "paused"})
    if paused_plan:
        level = _worst(level, "warning")
        signals.append({"kind": "paused_plan", "severity": "warning",
                        "message": "План виплат призупинено"})

    # 4) Paused asset
    if asset.get("status") == "paused":
        level = _worst(level, "warning")
        signals.append({"kind": "paused_asset", "severity": "warning",
                        "message": "Актив призупинено"})

    return {
        "asset_id": aid,
        "asset_title": asset.get("title"),
        "category": asset.get("category"),
        "status": level,
        "signals": signals,
        "days_overdue": max_overdue,
        "days_since_report": days_since_report,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Admin: Fund Intelligence Dashboard (Block 5 + req #2)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/admin/fund/intelligence")
async def fund_intelligence(_=Depends(require_admin)):
    # AUM + active investors (from ownership registry)
    aum = 0.0
    active = set()
    async for o in db.lumen_ownerships.find({}):
        u = float(o.get("units") or 0)
        if u > 0:
            aum += u
            active.add(o.get("investor_id"))

    # Ledger truths
    capital_raised = capital_paid_out = withdrawals_paid = 0.0
    async for e in db.lumen_ledger_entries.find({}):
        amt = float(e.get("amount_uah") or 0)
        et, reason = e.get("entry_type"), e.get("reason")
        if et == "credit" and reason == "investment_funding":
            capital_raised += amt
        elif et == "credit" and reason == "payout":
            capital_paid_out += amt
        elif et == "debit" and reason == "withdrawal":
            withdrawals_paid += amt

    # Pending funding (committed, not confirmed)
    pending_funding = 0.0
    async for p in db.lumen_payment_requests.find({"status": {"$in": PENDING_FUNDING_STATUSES}}):
        pending_funding += float(p.get("amount_uah") or p.get("amount") or 0)

    # Pending withdrawals (reserved, not yet paid)
    pending_withdrawals = 0.0
    async for w in db.lumen_withdrawal_requests.find({"status": {"$in": PENDING_WITHDRAWAL_STATUSES}}):
        pending_withdrawals += float(w.get("amount_uah") or w.get("amount") or 0)

    # Upcoming payouts (pending payout records)
    upcoming_payouts = 0.0
    upcoming_count = 0
    async for r in db.lumen_payout_records.find({"status": {"$in": PENDING_PAYOUT_STATUSES}}):
        upcoming_payouts += float(r.get("amount_uah") or 0)
        upcoming_count += 1

    # Net cash position = залучений капітал − фактично виведені кошти
    net_cash_position = capital_raised - withdrawals_paid
    average_yield = (capital_paid_out / aum * 100) if aum else 0.0

    # Asset health distribution
    now = _now()
    dist = {"healthy": 0, "warning": 0, "critical": 0}
    async for a in db.lumen_assets.find({}):
        h = await compute_asset_health(a, now)
        dist[h["status"]] = dist.get(h["status"], 0) + 1

    return {
        "aum": _round2(aum),
        "active_investors": len(active),
        "capital_raised": _round2(capital_raised),
        "capital_paid_out": _round2(capital_paid_out),
        "withdrawals_paid": _round2(withdrawals_paid),
        "pending_funding": _round2(pending_funding),
        "pending_withdrawals": _round2(pending_withdrawals),
        "upcoming_payouts": _round2(upcoming_payouts),
        "upcoming_payouts_count": upcoming_count,
        "net_cash_position": _round2(net_cash_position),
        "average_yield": _round2(average_yield),
        "asset_health_distribution": dist,
    }


@router.get("/admin/fund/health")
async def fund_health(status: Optional[str] = None, _=Depends(require_admin)):
    now = _now()
    items = []
    async for a in db.lumen_assets.find({}):
        h = await compute_asset_health(a, now)
        if status and h["status"] != status:
            continue
        items.append(h)
    order = {"critical": 0, "warning": 1, "healthy": 2}
    items.sort(key=lambda x: (order.get(x["status"], 3), -(x["days_overdue"] or 0)))
    return {"items": items, "total": len(items),
            "thresholds": {
                "overdue_warn_days": HEALTH_OVERDUE_WARN_DAYS,
                "overdue_crit_days": HEALTH_OVERDUE_CRIT_DAYS,
                "report_warn_days": HEALTH_REPORT_WARN_DAYS,
                "report_crit_days": HEALTH_REPORT_CRIT_DAYS,
            }}


__all__ = ["router", "compute_asset_health"]
