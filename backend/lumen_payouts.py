"""
Sprint 8 — Payout Engine.

Перехід «інвестор вклав гроші» → «інвестор реально отримує дохід».

Ланцюг доходності:
    Asset → Income (Payout Plan) → Payout (records) → Batch → Ledger(credit) →
    Wallet(available_balance↑) → Withdrawal

Колекції:
    lumen_payout_plans    — план нарахувань по активу (тип/частота/сума/період)
    lumen_payout_records  — фактичні нарахування на інвестора (по ownership)
    lumen_payout_batches  — пакет нарахувань (щоб не проводити 500 виплат поштучно)

Розподіл:
    Сума плану розподіляється між власниками активу пропорційно їхній частці
    у фактично залученому пулі (units з lumen_ownerships). Залишок округлення
    додається найбільшому власнику.

Lifecycle батча:
    generated → approved → credited            (термінальний успіх)
              ↘ cancelled                       (термінальний)
    Кожен payout_record повторює статус батча: planned/generated → approved →
    credited / cancelled.

    На `credited`:
        для кожного record → ledger credit (reason="payout"),
        record.status=credited + paid_date + ledger_entry_id,
        перерахунок гаманців → wallet.available_balance↑.

НЕ робимо у цьому спринті: автобанк, податковий модуль, вторинний ринок,
крипто-виплати, dividend reinvestment.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from lumen_api import db, get_current_user, require_admin, _strip_mongo, _now, _iso
from lumen_payments import _ledger_append, _round2, BASE_CURRENCY
from lumen_wallet import recompute_wallet
from lumen_audit import write_audit

logger = logging.getLogger("lumen.payouts")

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

PAYOUT_TYPES = ["rental_income", "profit_share", "exit_distribution", "manual"]
PAYOUT_TYPE_LABELS = {
    "rental_income":     "Орендний дохід",
    "profit_share":      "Розподіл прибутку",
    "exit_distribution": "Виплата при виході",
    "manual":            "Ручне нарахування",
}

PAYOUT_FREQUENCIES = ["one_time", "monthly", "quarterly", "annual"]
PAYOUT_FREQUENCY_LABELS = {
    "one_time":  "Разово",
    "monthly":   "Щомісячно",
    "quarterly": "Щоквартально",
    "annual":    "Щорічно",
}

PLAN_STATUSES = ["active", "paused", "ended"]
PLAN_STATUS_LABELS = {"active": "активний", "paused": "призупинено", "ended": "завершено"}

# Record / batch lifecycle
RECORD_STATUSES = ["planned", "generated", "approved", "credited", "cancelled"]
RECORD_STATUS_LABELS = {
    "planned":   "заплановано",
    "generated": "сформовано",
    "approved":  "схвалено",
    "credited":  "нараховано",
    "cancelled": "скасовано",
}
BATCH_STATUSES = ["generated", "approved", "credited", "cancelled"]
BATCH_STATUS_LABELS = {
    "generated": "сформовано",
    "approved":  "схвалено",
    "credited":  "нараховано",
    "cancelled": "скасовано",
}

_BATCH_TRANSITIONS = {
    "generated": {"approved", "cancelled"},
    "approved":  {"credited", "cancelled"},
}
_TERMINAL_BATCH = {"credited", "cancelled"}


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _month_add(dt: datetime, months: int) -> datetime:
    if dt is None:
        dt = _now()
    m = dt.month - 1 + months
    y = dt.year + m // 12
    m = m % 12 + 1
    # clamp day
    import calendar
    day = min(dt.day, calendar.monthrange(y, m)[1])
    return dt.replace(year=y, month=m, day=day)


def _period_step_months(frequency: str) -> int:
    return {"monthly": 1, "quarterly": 3, "annual": 12, "one_time": 0}.get(frequency, 1)


def _period_label_for(dt: datetime, frequency: str) -> str:
    if frequency == "one_time":
        return dt.strftime("%d.%m.%Y")
    if frequency == "quarterly":
        q = (dt.month - 1) // 3 + 1
        return f"Q{q} {dt.year}"
    if frequency == "annual":
        return f"{dt.year}"
    return dt.strftime("%m.%Y")  # monthly


def _plan_out(doc: dict) -> dict:
    doc = dict(doc)
    doc["type_label"] = PAYOUT_TYPE_LABELS.get(doc.get("type"), doc.get("type"))
    doc["frequency_label"] = PAYOUT_FREQUENCY_LABELS.get(doc.get("frequency"), doc.get("frequency"))
    doc["status_label"] = PLAN_STATUS_LABELS.get(doc.get("status"), doc.get("status"))
    for k in ("start_date", "end_date", "created_at", "updated_at", "last_generated_period_date"):
        if doc.get(k) is not None:
            doc[k] = _iso(doc[k])
    return _strip_mongo(doc)


def _record_out(doc: dict) -> dict:
    doc = dict(doc)
    doc["status_label"] = RECORD_STATUS_LABELS.get(doc.get("status"), doc.get("status"))
    doc["type_label"] = PAYOUT_TYPE_LABELS.get(doc.get("type"), doc.get("type"))
    for k in ("planned_date", "paid_date", "created_at", "updated_at"):
        if doc.get(k) is not None:
            doc[k] = _iso(doc[k])
    return _strip_mongo(doc)


def _batch_out(doc: dict) -> dict:
    doc = dict(doc)
    doc["status_label"] = BATCH_STATUS_LABELS.get(doc.get("status"), doc.get("status"))
    doc["type_label"] = PAYOUT_TYPE_LABELS.get(doc.get("type"), doc.get("type"))
    for k in ("planned_date", "created_at", "approved_at", "credited_at", "cancelled_at"):
        if doc.get(k) is not None:
            doc[k] = _iso(doc[k])
    return _strip_mongo(doc)


async def _investor_name(investor_id: str) -> tuple[Optional[str], Optional[str]]:
    u = await db.users.find_one({"user_id": investor_id}) or await db.users.find_one({"id": investor_id})
    if not u:
        return None, None
    return (u.get("name") or u.get("full_name")), u.get("email")


async def _asset_title(asset_id: str) -> Optional[str]:
    a = await db.lumen_assets.find_one({"id": asset_id}, {"title": 1})
    return a.get("title") if a else None


# ──────────────────────────────────────────────────────────────────────────────
# Distribution — pro-rata by share of the actually-raised pool (ownership units)
# ──────────────────────────────────────────────────────────────────────────────

async def distribute_amount(asset_id: str, amount: float) -> list[dict]:
    """Return per-investor allocation rows. Rounding remainder → largest holder."""
    owns: list[dict] = []
    total_units = 0.0
    async for o in db.lumen_ownerships.find({"asset_id": asset_id}):
        u = float(o.get("units") or 0)
        if u <= 0:
            continue
        owns.append(o)
        total_units += u
    if total_units <= 0 or amount <= 0:
        return []
    rows = []
    allocated = 0.0
    for o in owns:
        u = float(o.get("units") or 0)
        share = u / total_units
        amt = _round2(amount * share)
        rows.append({
            "investor_id": o.get("investor_id"),
            "ownership_id": o.get("id"),
            "units": u,
            "share_percent": _round2(share * 100),
            "amount": amt,
        })
        allocated += amt
    remainder = _round2(amount - allocated)
    if rows and abs(remainder) >= 0.01:
        rows.sort(key=lambda r: r["units"], reverse=True)
        rows[0]["amount"] = _round2(rows[0]["amount"] + remainder)
    return rows


# ──────────────────────────────────────────────────────────────────────────────
# Plans
# ──────────────────────────────────────────────────────────────────────────────

async def create_plan(*, asset_id: str, type_: str, frequency: str,
                       expected_amount: float, start_date: Optional[datetime],
                       end_date: Optional[datetime], notes: Optional[str],
                       actor_id: str) -> dict:
    if type_ not in PAYOUT_TYPES:
        raise HTTPException(status_code=400, detail=f"Невідомий тип: {type_}")
    if frequency not in PAYOUT_FREQUENCIES:
        raise HTTPException(status_code=400, detail=f"Невідома частота: {frequency}")
    asset = await db.lumen_assets.find_one({"id": asset_id})
    if not asset:
        raise HTTPException(status_code=404, detail="Актив не знайдено")
    if expected_amount is None or float(expected_amount) <= 0:
        raise HTTPException(status_code=400, detail="Сума має бути більшою за 0")
    now = _now()
    doc = {
        "id": f"pp-{uuid.uuid4().hex[:12]}",
        "asset_id": asset_id,
        "asset_title": asset.get("title"),
        "type": type_,
        "frequency": frequency,
        "expected_amount": _round2(expected_amount),
        "currency": BASE_CURRENCY,
        "start_date": start_date or now,
        "end_date": end_date,
        "status": "active",
        "notes": notes,
        "last_generated_period_date": None,
        "created_at": now,
        "updated_at": now,
        "created_by": actor_id,
    }
    await db.lumen_payout_plans.insert_one(dict(doc))
    return _plan_out(doc)


async def update_plan(plan_id: str, *, status: Optional[str], expected_amount: Optional[float],
                      end_date: Optional[datetime], notes: Optional[str]) -> dict:
    plan = await db.lumen_payout_plans.find_one({"id": plan_id})
    if not plan:
        raise HTTPException(status_code=404, detail="План не знайдено")
    upd: dict[str, Any] = {"updated_at": _now()}
    if status is not None:
        if status not in PLAN_STATUSES:
            raise HTTPException(status_code=400, detail=f"Невідомий статус плану: {status}")
        upd["status"] = status
    if expected_amount is not None:
        if float(expected_amount) <= 0:
            raise HTTPException(status_code=400, detail="Сума має бути більшою за 0")
        upd["expected_amount"] = _round2(expected_amount)
    if end_date is not None:
        upd["end_date"] = end_date
    if notes is not None:
        upd["notes"] = notes
    await db.lumen_payout_plans.update_one({"id": plan_id}, {"$set": upd})
    p = await db.lumen_payout_plans.find_one({"id": plan_id})
    return _plan_out(p)


async def recalculate_plan(plan_id: str) -> dict:
    """Preview the distribution for the plan's expected amount (no writes)."""
    plan = await db.lumen_payout_plans.find_one({"id": plan_id})
    if not plan:
        raise HTTPException(status_code=404, detail="План не знайдено")
    rows = await distribute_amount(plan["asset_id"], float(plan["expected_amount"]))
    enriched = []
    for r in rows:
        name, email = await _investor_name(r["investor_id"])
        enriched.append({**r, "investor_name": name, "investor_email": email})
    return {
        "plan": _plan_out(plan),
        "allocations": enriched,
        "investor_count": len(enriched),
        "total_amount": _round2(sum(r["amount"] for r in enriched)),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Batches — generate / approve / credit / cancel
# ──────────────────────────────────────────────────────────────────────────────

async def generate_batch(plan_id: str, *, amount: Optional[float],
                         planned_date: Optional[datetime],
                         period_label: Optional[str], actor_id: str) -> dict:
    plan = await db.lumen_payout_plans.find_one({"id": plan_id})
    if not plan:
        raise HTTPException(status_code=404, detail="План не знайдено")
    if plan.get("status") == "ended":
        raise HTTPException(status_code=409, detail="План завершено — генерація неможлива")

    amt = float(amount) if amount is not None else float(plan["expected_amount"])
    if amt <= 0:
        raise HTTPException(status_code=400, detail="Сума має бути більшою за 0")

    # determine period date
    freq = plan["frequency"]
    step = _period_step_months(freq)
    last = plan.get("last_generated_period_date")
    if planned_date is not None:
        pdate = planned_date
    elif last and step:
        pdate = _month_add(last, step)
    elif step:
        pdate = _month_add(plan.get("start_date") or _now(), 0)
    else:
        pdate = plan.get("start_date") or _now()
    plabel = period_label or _period_label_for(pdate, freq)

    rows = await distribute_amount(plan["asset_id"], amt)
    if not rows:
        raise HTTPException(
            status_code=409,
            detail="Немає власників активу з часткою — нічого розподіляти")

    # D2 — UA withholding tax engine (ПДФО 18% + ВЗ 1.5%). Income-type
    # payouts are taxed at source; capital-return types are not.
    import lumen_tax as _tax
    _tax_cfg = await _tax.get_config()
    # Income-type payouts are taxed at source (ПДФО+ВЗ); other types are not.
    _taxable = plan["type"] in ("rental_income", "profit_share")

    now = _now()
    batch_id = f"pb-{uuid.uuid4().hex[:12]}"
    asset_title = plan.get("asset_title") or await _asset_title(plan["asset_id"])

    created = 0
    total_gross = 0.0
    total_tax = 0.0
    total_net = 0.0
    for r in rows:
        name, email = await _investor_name(r["investor_id"])
        gross = _round2(r["amount"])
        if _taxable:
            wh = await _tax.withholding_for_investor(r["investor_id"], gross, config=_tax_cfg)
        else:
            wh = {"gross": gross, "pdfo": 0.0, "vz": 0.0, "tax_total": 0.0,
                  "net": gross, "effective_rate": 0.0}
        net = wh["net"]
        total_gross = _round2(total_gross + gross)
        total_tax = _round2(total_tax + wh["tax_total"])
        total_net = _round2(total_net + net)
        await db.lumen_payout_records.insert_one({
            "id": f"por-{uuid.uuid4().hex[:12]}",
            "plan_id": plan_id,
            "batch_id": batch_id,
            "asset_id": plan["asset_id"],
            "asset_title": asset_title,
            "investor_id": r["investor_id"],
            "investor_name": name,
            "investor_email": email,
            "ownership_id": r["ownership_id"],
            "type": plan["type"],
            "period_label": plabel,
            "share_percent": r["share_percent"],
            # gross / tax / net transparency (D2)
            "gross_amount": gross,
            "tax_pdfo": wh["pdfo"],
            "tax_vz": wh["vz"],
            "tax_total": wh["tax_total"],
            "tax_rate": wh["effective_rate"],
            "net_amount": net,
            # `amount`/`amount_uah` = NET (what the investor actually receives)
            "amount": net,
            "currency": BASE_CURRENCY,
            "amount_uah": net,
            "status": "generated",
            "planned_date": pdate,
            "paid_date": None,
            "ledger_entry_id": None,
            "created_at": now,
            "updated_at": now,
        })
        created += 1

    batch = {
        "id": batch_id,
        "plan_id": plan_id,
        "asset_id": plan["asset_id"],
        "asset_title": asset_title,
        "type": plan["type"],
        "frequency": freq,
        "period_label": plabel,
        "total_amount": total_net,
        "total_amount_uah": total_net,
        "total_gross_uah": total_gross,
        "total_tax_uah": total_tax,
        "total_net_uah": total_net,
        "taxable": _taxable,
        "currency": BASE_CURRENCY,
        "payout_count": created,
        "status": "generated",
        "planned_date": pdate,
        "notes": None,
        "created_at": now,
        "approved_at": None,
        "credited_at": None,
        "cancelled_at": None,
        "created_by": actor_id,
    }
    await db.lumen_payout_batches.insert_one(dict(batch))
    await db.lumen_payout_plans.update_one(
        {"id": plan_id},
        {"$set": {"last_generated_period_date": pdate, "updated_at": now}})
    return _batch_out(batch)


async def approve_batch(batch_id: str, actor_id: str) -> dict:
    batch = await db.lumen_payout_batches.find_one({"id": batch_id})
    if not batch:
        raise HTTPException(status_code=404, detail="Пакет не знайдено")
    if batch["status"] in _TERMINAL_BATCH:
        raise HTTPException(status_code=409, detail="Пакет вже завершено")
    if "approved" not in _BATCH_TRANSITIONS.get(batch["status"], set()):
        raise HTTPException(status_code=409, detail="Пакет не можна схвалити у цьому статусі")
    now = _now()
    await db.lumen_payout_batches.update_one(
        {"id": batch_id}, {"$set": {"status": "approved", "approved_at": now}})
    await db.lumen_payout_records.update_many(
        {"batch_id": batch_id, "status": "generated"},
        {"$set": {"status": "approved", "updated_at": now}})
    b = await db.lumen_payout_batches.find_one({"id": batch_id})
    return _batch_out(b)


async def credit_batch(batch_id: str, actor_id: str) -> dict:
    batch = await db.lumen_payout_batches.find_one({"id": batch_id})
    if not batch:
        raise HTTPException(status_code=404, detail="Пакет не знайдено")
    if batch["status"] in _TERMINAL_BATCH:
        raise HTTPException(status_code=409, detail="Пакет вже завершено")
    if "credited" not in _BATCH_TRANSITIONS.get(batch["status"], set()):
        raise HTTPException(
            status_code=409,
            detail="Спочатку схваліть пакет, потім нарахуйте")

    now = _now()
    affected_investors: set[str] = set()
    credited = 0
    async for rec in db.lumen_payout_records.find(
            {"batch_id": batch_id, "status": {"$in": ["approved", "generated"]}}):
        if float(rec.get("amount") or 0) <= 0:
            continue
        ledger_id = await _ledger_append(
            entry_type="credit",
            reason="payout",
            investor_id=rec["investor_id"],
            asset_id=rec.get("asset_id"),
            investment_id=None,
            payment_request_id=None,
            amount=rec["amount"],
            currency=rec.get("currency", BASE_CURRENCY),
            fx_rate=1.0,
            amount_uah=rec["amount_uah"],
            actor_id=actor_id,
            notes=f"{PAYOUT_TYPE_LABELS.get(rec.get('type'), 'Виплата')} · "
                  f"{rec.get('asset_title')} · {rec.get('period_label')}",
        )
        await db.lumen_ledger_entries.update_one(
            {"id": ledger_id},
            {"$set": {"payout_record_id": rec["id"], "payout_batch_id": batch_id}})
        await db.lumen_payout_records.update_one(
            {"id": rec["id"]},
            {"$set": {"status": "credited", "paid_date": now,
                      "ledger_entry_id": ledger_id, "updated_at": now}})
        affected_investors.add(rec["investor_id"])
        credited += 1

    await db.lumen_payout_batches.update_one(
        {"id": batch_id}, {"$set": {"status": "credited", "credited_at": now}})

    # D2 — remit the withheld tax into the platform tax-liability account.
    try:
        import lumen_tax as _tax
        total_tax = float(batch.get("total_tax_uah") or 0)
        if total_tax <= 0:
            agg = await db.lumen_payout_records.aggregate([
                {"$match": {"batch_id": batch_id}},
                {"$group": {"_id": None, "t": {"$sum": "$tax_total"}}}]).to_list(1)
            total_tax = float(agg[0]["t"]) if agg else 0.0
        if total_tax > 0:
            await _tax.write_tax_liability(
                amount=total_tax, asset_id=batch.get("asset_id"),
                batch_id=batch_id, actor_id=actor_id,
                notes=f"Withholding for {batch.get('asset_title')} · {batch.get('period_label')}")
    except Exception:
        import logging as _l
        _l.getLogger("lumen.payouts").warning("tax liability write failed", exc_info=True)

    # Recompute wallets + notify
    for iid in affected_investors:
        await recompute_wallet(iid)
        try:
            from lumen_payments import _notify
            await _notify(
                iid,
                "Нараховано дохід",
                f"Вам нараховано дохід за «{batch.get('asset_title')}» "
                f"({batch.get('period_label')}). Кошти зараховано на гаманець.",
                event="payout_credited")
        except Exception:
            pass

    b = await db.lumen_payout_batches.find_one({"id": batch_id})
    out = _batch_out(b)
    out["credited_count"] = credited
    return out


async def cancel_batch(batch_id: str, actor_id: str, reason: Optional[str] = None) -> dict:
    batch = await db.lumen_payout_batches.find_one({"id": batch_id})
    if not batch:
        raise HTTPException(status_code=404, detail="Пакет не знайдено")
    if batch["status"] == "credited":
        raise HTTPException(
            status_code=409,
            detail="Нарахований пакет не можна скасувати (потрібне сторно)")
    if batch["status"] == "cancelled":
        raise HTTPException(status_code=409, detail="Пакет вже скасовано")
    now = _now()
    await db.lumen_payout_batches.update_one(
        {"id": batch_id},
        {"$set": {"status": "cancelled", "cancelled_at": now,
                  "cancel_reason": (reason or "").strip() or None}})
    await db.lumen_payout_records.update_many(
        {"batch_id": batch_id, "status": {"$nin": ["credited", "cancelled"]}},
        {"$set": {"status": "cancelled", "updated_at": now}})
    b = await db.lumen_payout_batches.find_one({"id": batch_id})
    return _batch_out(b)


# ──────────────────────────────────────────────────────────────────────────────
# D1 — Dividend Scheduler: daily cron → due plans → generate → queue approval
# ──────────────────────────────────────────────────────────────────────────────
def _next_period_date(plan: dict) -> Optional[datetime]:
    """The next period date a plan is due to generate, or None if not due/ended."""
    freq = plan.get("frequency")
    step = _period_step_months(freq)
    last = plan.get("last_generated_period_date")
    start = plan.get("start_date") or _now()
    if freq == "one_time":
        return None if last else start
    if last:
        return _month_add(last, step)
    return start


async def due_plans(now: Optional[datetime] = None) -> list[dict]:
    """Active plans whose next period date is on/before `now`."""
    now = now or _now()
    out = []
    async for plan in db.lumen_payout_plans.find({"status": "active"}):
        nxt = _next_period_date(plan)
        if not nxt:
            continue
        nxt_cmp = nxt if nxt.tzinfo else nxt.replace(tzinfo=timezone.utc)
        if nxt_cmp > now:
            continue
        end = plan.get("end_date")
        if isinstance(end, datetime):
            end_cmp = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
            if nxt_cmp > end_cmp:
                continue
        out.append(plan)
    return out


async def run_due_plans(*, actor_id: str = "system-scheduler",
                        auto_credit: bool = False) -> dict:
    """Generate batches for all due plans (queued for admin approval).
    Idempotent per period: generate_batch advances last_generated_period_date,
    so a plan is not double-generated for the same period."""
    plans = await due_plans()
    generated = []
    errors = []
    seen_plans = set()
    for plan in plans:
        if plan["id"] in seen_plans:
            continue
        seen_plans.add(plan["id"])
        # Catch up ALL missed periods for this plan (bounded), one batch each.
        for _ in range(36):
            fresh = await db.lumen_payout_plans.find_one({"id": plan["id"]})
            if not fresh or fresh.get("status") != "active":
                break
            nxt = _next_period_date(fresh)
            if not nxt:
                break
            nxt_cmp = nxt if nxt.tzinfo else nxt.replace(tzinfo=timezone.utc)
            if nxt_cmp > _now():
                break
            end = fresh.get("end_date")
            if isinstance(end, datetime):
                end_cmp = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
                if nxt_cmp > end_cmp:
                    break
            try:
                b = await generate_batch(plan["id"], amount=None, planned_date=None,
                                         period_label=None, actor_id=actor_id)
                generated.append({"plan_id": plan["id"], "batch_id": b["id"],
                                  "asset": fresh.get("asset_title"),
                                  "period": b.get("period_label"),
                                  "total_net_uah": b.get("total_net_uah"),
                                  "total_tax_uah": b.get("total_tax_uah")})
                if auto_credit:
                    await approve_batch(b["id"], actor_id)
                    await credit_batch(b["id"], actor_id)
            except HTTPException as he:
                errors.append({"plan_id": plan["id"], "error": str(he.detail)})
                break
            except Exception as e:  # pragma: no cover
                errors.append({"plan_id": plan["id"], "error": str(e)})
                break
    # Notify admins that batches await approval
    if generated and not auto_credit:
        try:
            from lumen_payments import _notify
            async for adm in db.users.find({"role": "admin"}, {"user_id": 1}):
                await _notify(
                    adm.get("user_id"),
                    "Дивідендні пакети сформовано",
                    f"Планувальник сформував {len(generated)} пакет(ів) виплат — "
                    f"очікують схвалення в розділі «Виплати доходу».",
                    event="payout_batch_pending")
        except Exception:
            pass
    return {"due": len(plans), "generated": generated, "errors": errors,
            "ran_at": _iso(_now())}


async def scheduler_loop() -> None:
    """Daily dividend scheduler. Checks due plans every 6h (cheap, idempotent)."""
    import asyncio
    while True:
        try:
            await asyncio.sleep(6 * 60 * 60)
            res = await run_due_plans()
            if res["generated"] or res["errors"]:
                import logging as _l
                _l.getLogger("lumen.payouts").info(
                    "dividend scheduler: due=%s generated=%s errors=%s",
                    res["due"], len(res["generated"]), len(res["errors"]))
        except asyncio.CancelledError:
            break
        except Exception as e:  # pragma: no cover
            import logging as _l
            _l.getLogger("lumen.payouts").warning("dividend scheduler tick failed: %s", e)



# ──────────────────────────────────────────────────────────────────────────────
# Asset payout summary (for asset cards)
# ──────────────────────────────────────────────────────────────────────────────

async def asset_payout_summary(asset_id: str, investor_id: Optional[str] = None) -> dict:
    q: dict[str, Any] = {"asset_id": asset_id}
    if investor_id:
        q["investor_id"] = investor_id
    total_accrued = 0.0
    last_payout = None
    next_payout = None
    async for rec in db.lumen_payout_records.find(q):
        if rec.get("status") == "credited":
            total_accrued += float(rec.get("amount_uah") or 0)
            pd = rec.get("paid_date")
            if pd and (last_payout is None or pd > last_payout):
                last_payout = pd
        elif rec.get("status") in ("planned", "generated", "approved"):
            pd = rec.get("planned_date")
            if pd and (next_payout is None or pd < next_payout):
                next_payout = pd
    # Fallback next payout from active plan schedule
    if next_payout is None:
        plan = await db.lumen_payout_plans.find_one(
            {"asset_id": asset_id, "status": "active"})
        if plan and plan.get("frequency") != "one_time":
            base = plan.get("last_generated_period_date") or plan.get("start_date")
            if base:
                next_payout = _month_add(base, _period_step_months(plan["frequency"]))
    return {
        "asset_id": asset_id,
        "total_accrued": _round2(total_accrued),
        "last_payout": _iso(last_payout) if last_payout else None,
        "next_payout": _iso(next_payout) if next_payout else None,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Bootstrap: indexes + demo seed (idempotent migration from Sprint 7 raw seed)
# ──────────────────────────────────────────────────────────────────────────────

async def ensure_payout_indexes() -> None:
    await db.lumen_payout_plans.create_index("id", unique=True)
    await db.lumen_payout_plans.create_index([("asset_id", 1), ("status", 1)])
    await db.lumen_payout_records.create_index("id", unique=True)
    await db.lumen_payout_records.create_index([("investor_id", 1), ("status", 1)])
    await db.lumen_payout_records.create_index("batch_id")
    await db.lumen_payout_records.create_index([("asset_id", 1), ("status", 1)])
    await db.lumen_payout_batches.create_index("id", unique=True)
    await db.lumen_payout_batches.create_index([("status", 1), ("created_at", -1)])
    await db.lumen_payout_batches.create_index("plan_id")


async def _seed_demo_payouts() -> dict:
    """Idempotent demo: migrate the Sprint 7 raw dividend seed into the engine.

    Creates a rental_income plan on the asset with the most ownership and
    generates 3 credited historical monthly batches + 1 pending (generated)
    period, so the investor sees real income that funds the wallet.
    """
    # pick asset with ownership
    own = await db.lumen_ownerships.find_one({"units": {"$gt": 0}})
    if not own:
        return {"seeded": False, "reason": "no ownership"}
    asset_id = own["asset_id"]

    # Remove the Sprint 7 raw demo-dividend ledger seed (superseded by engine)
    removed = await db.lumen_ledger_entries.delete_many(
        {"reason": "payout", "notes": {"$regex": "демо-сид"}})

    asset = await db.lumen_assets.find_one({"id": asset_id}) or {}
    now = _now()
    start = _month_add(now, -3)
    plan = await create_plan(
        asset_id=asset_id, type_="rental_income", frequency="monthly",
        expected_amount=25000.0, start_date=start, end_date=None,
        notes="Демо-план орендного доходу", actor_id="system")
    plan_id = plan["id"]

    # 3 credited historical months
    for i in range(3):
        pdate = _month_add(start, i)
        b = await generate_batch(plan_id, amount=None, planned_date=pdate,
                                 period_label=None, actor_id="system")
        await approve_batch(b["id"], "system")
        await credit_batch(b["id"], "system")
    # 1 upcoming (generated, not credited) — shows as "очікується"
    await generate_batch(plan_id, amount=None,
                         planned_date=_month_add(now, 1),
                         period_label=None, actor_id="system")

    # recompute wallets for affected investors
    seen = set()
    async for r in db.lumen_payout_records.find({"plan_id": plan_id}, {"investor_id": 1}):
        iid = r.get("investor_id")
        if iid and iid not in seen:
            seen.add(iid)
            await recompute_wallet(iid)

    return {"seeded": True, "asset_id": asset_id, "plan_id": plan_id,
            "removed_raw_dividends": removed.deleted_count}


async def bootstrap_payouts() -> dict:
    await ensure_payout_indexes()
    res = {"indexes": True}
    try:
        if await db.lumen_payout_plans.count_documents({}) == 0:
            res["demo"] = await _seed_demo_payouts()
    except Exception as ex:
        logger.exception("payout demo seed failed: %s", ex)
        res["demo_error"] = str(ex)
    return res


# ──────────────────────────────────────────────────────────────────────────────
# Router
# ──────────────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api", tags=["lumen-payouts"])


# ---- Investor: Income / Earnings ---------------------------------------------

@router.get("/investor/income")
async def my_income(user=Depends(get_current_user)):
    iid = user["id"]
    # Paid (credited) income from ledger payout credits — wallet-consistent
    paid_total = 0.0
    paid_by_asset: dict[str, float] = {}
    last_by_asset: dict[str, Any] = {}
    async for e in db.lumen_ledger_entries.find(
            {"investor_id": iid, "reason": "payout", "entry_type": "credit"}):
        amt = float(e.get("amount_uah") or 0)
        paid_total += amt
        aid = e.get("asset_id") or "—"
        paid_by_asset[aid] = paid_by_asset.get(aid, 0.0) + amt
        ca = e.get("created_at")
        if aid not in last_by_asset or (ca and ca > last_by_asset[aid]):
            last_by_asset[aid] = ca

    # Expected (not yet credited) from payout_records
    expected_total = 0.0
    expected_by_asset: dict[str, float] = {}
    next_by_asset: dict[str, Any] = {}
    async for r in db.lumen_payout_records.find(
            {"investor_id": iid, "status": {"$in": ["planned", "generated", "approved"]}}):
        amt = float(r.get("amount_uah") or 0)
        expected_total += amt
        aid = r.get("asset_id") or "—"
        expected_by_asset[aid] = expected_by_asset.get(aid, 0.0) + amt
        pd = r.get("planned_date")
        if pd and (aid not in next_by_asset or pd < next_by_asset[aid]):
            next_by_asset[aid] = pd

    # Per-asset breakdown driven by ownership (invested capital)
    by_asset = []
    async for o in db.lumen_ownerships.find({"investor_id": iid}):
        aid = o.get("asset_id")
        invested = float(o.get("units") or 0)
        if invested <= 0:
            continue
        paid = _round2(paid_by_asset.get(aid, 0.0))
        expected = _round2(expected_by_asset.get(aid, 0.0))
        by_asset.append({
            "asset_id": aid,
            "asset_title": o.get("asset_title") or await _asset_title(aid),
            "invested": _round2(invested),
            "paid": paid,
            "expected": expected,
            "yield_percent": _round2(paid / invested * 100) if invested else 0.0,
            "last_payout": _iso(last_by_asset.get(aid)) if last_by_asset.get(aid) else None,
            "next_payout": _iso(next_by_asset.get(aid)) if next_by_asset.get(aid) else None,
        })
    by_asset.sort(key=lambda x: x["paid"], reverse=True)

    invested_total = _round2(sum(a["invested"] for a in by_asset))
    return {
        "summary": {
            "accrued_total": _round2(paid_total + expected_total),
            "paid_total": _round2(paid_total),
            "expected_total": _round2(expected_total),
            "invested_total": invested_total,
            "yield_percent": _round2(paid_total / invested_total * 100) if invested_total else 0.0,
        },
        "by_asset": by_asset,
    }


@router.get("/investor/income/payouts")
async def my_income_payouts(limit: int = 100, user=Depends(get_current_user)):
    items = []
    async for r in (db.lumen_payout_records.find({"investor_id": user["id"]})
                    .sort("created_at", -1).limit(min(max(1, limit), 500))):
        items.append(_record_out(r))
    return {"items": items, "total": len(items)}


@router.get("/assets/{asset_id}/payout-summary")
async def public_asset_payout_summary(asset_id: str):
    return await asset_payout_summary(asset_id)


# ---- Admin: Plans ------------------------------------------------------------

class PlanCreatePayload(BaseModel):
    asset_id: str
    type: str = "rental_income"
    frequency: str = "monthly"
    expected_amount: float = Field(..., gt=0)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    notes: Optional[str] = None


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


@router.get("/admin/payout-plans")
async def admin_list_plans(asset_id: Optional[str] = None, status: Optional[str] = None,
                           _=Depends(require_admin)):
    q: dict[str, Any] = {}
    if asset_id:
        q["asset_id"] = asset_id
    if status:
        q["status"] = status
    items = []
    async for p in db.lumen_payout_plans.find(q).sort("created_at", -1).limit(500):
        items.append(_plan_out(p))
    return {"items": items, "total": len(items),
            "types": PAYOUT_TYPE_LABELS, "frequencies": PAYOUT_FREQUENCY_LABELS}


@router.post("/admin/payout-plans")
async def admin_create_plan(payload: PlanCreatePayload, admin=Depends(require_admin)):
    return await create_plan(
        asset_id=payload.asset_id, type_=payload.type, frequency=payload.frequency,
        expected_amount=payload.expected_amount,
        start_date=_parse_dt(payload.start_date), end_date=_parse_dt(payload.end_date),
        notes=payload.notes, actor_id=admin["id"])


class PlanUpdatePayload(BaseModel):
    status: Optional[str] = None
    expected_amount: Optional[float] = None
    end_date: Optional[str] = None
    notes: Optional[str] = None


@router.patch("/admin/payout-plans/{plan_id}")
async def admin_update_plan(plan_id: str, payload: PlanUpdatePayload,
                            _=Depends(require_admin)):
    return await update_plan(plan_id, status=payload.status,
                             expected_amount=payload.expected_amount,
                             end_date=_parse_dt(payload.end_date), notes=payload.notes)


@router.post("/admin/payout-plans/{plan_id}/recalculate")
async def admin_recalculate_plan(plan_id: str, _=Depends(require_admin)):
    return await recalculate_plan(plan_id)


class GeneratePayload(BaseModel):
    amount: Optional[float] = None
    planned_date: Optional[str] = None
    period_label: Optional[str] = None


@router.post("/admin/payout-plans/{plan_id}/generate")
async def admin_generate_batch(plan_id: str, payload: GeneratePayload = None,
                               admin=Depends(require_admin)):
    payload = payload or GeneratePayload()
    return await generate_batch(
        plan_id, amount=payload.amount, planned_date=_parse_dt(payload.planned_date),
        period_label=payload.period_label, actor_id=admin["id"])


# ---- Admin: Dividend Scheduler (D1) ------------------------------------------

@router.get("/admin/payout-scheduler/due")
async def admin_scheduler_due(admin=Depends(require_admin)):
    """Preview which plans are due to generate right now (no writes)."""
    plans = await due_plans()
    items = []
    for p in plans:
        nxt = _next_period_date(p)
        items.append({"plan_id": p["id"], "asset_id": p.get("asset_id"),
                      "asset_title": p.get("asset_title"), "type": p.get("type"),
                      "frequency": p.get("frequency"),
                      "expected_amount": p.get("expected_amount"),
                      "due_period_date": _iso(nxt) if nxt else None,
                      "last_generated_period_date": _iso(p.get("last_generated_period_date")) if p.get("last_generated_period_date") else None})
    return {"due_count": len(items), "items": items, "checked_at": _iso(_now())}


class SchedulerRunPayload(BaseModel):
    auto_credit: bool = False


@router.post("/admin/payout-scheduler/run")
async def admin_scheduler_run(payload: SchedulerRunPayload = None,
                              admin=Depends(require_admin)):
    """Manually trigger the scheduler: generate batches for all due plans
    (queued for approval; set auto_credit=true to approve+credit immediately)."""
    payload = payload or SchedulerRunPayload()
    return await run_due_plans(actor_id=admin["id"], auto_credit=payload.auto_credit)



# ---- Admin: Batches ----------------------------------------------------------

@router.get("/admin/payout-batches")
async def admin_list_batches(status: Optional[str] = None, plan_id: Optional[str] = None,
                             _=Depends(require_admin)):
    q: dict[str, Any] = {}
    if status:
        q["status"] = status
    if plan_id:
        q["plan_id"] = plan_id
    items = []
    async for b in db.lumen_payout_batches.find(q).sort("created_at", -1).limit(500):
        items.append(_batch_out(b))
    counts = {}
    for s in BATCH_STATUSES:
        counts[s] = await db.lumen_payout_batches.count_documents({"status": s})
    counts["all"] = await db.lumen_payout_batches.count_documents({})
    return {"items": items, "total": len(items), "counts": counts}


@router.get("/admin/payout-batches/{batch_id}")
async def admin_batch_detail(batch_id: str, _=Depends(require_admin)):
    b = await db.lumen_payout_batches.find_one({"id": batch_id})
    if not b:
        raise HTTPException(status_code=404, detail="Пакет не знайдено")
    records = []
    async for r in db.lumen_payout_records.find({"batch_id": batch_id}).sort("amount", -1):
        records.append(_record_out(r))
    return {"batch": _batch_out(b), "records": records}


class BatchActionPayload(BaseModel):
    reason: Optional[str] = None


@router.post("/admin/payout-batches/{batch_id}/approve")
async def admin_approve_batch(batch_id: str, request: Request = None,
                              admin=Depends(require_admin)):
    res = await approve_batch(batch_id, admin["id"])
    await write_audit(
        action="payout_batch.approve", category="payout",
        target_type="lumen_payout_batches", target_id=batch_id,
        actor=admin, request=request,
        summary=f"Payout batch approved: {batch_id}",
        meta={"records": (res or {}).get("records_total"),
              "amount_uah": (res or {}).get("amount_total_uah")},
    )
    return res


@router.post("/admin/payout-batches/{batch_id}/credit")
async def admin_credit_batch(batch_id: str, request: Request = None,
                             admin=Depends(require_admin)):
    res = await credit_batch(batch_id, admin["id"])
    await write_audit(
        action="payout_batch.credit", category="payout",
        target_type="lumen_payout_batches", target_id=batch_id,
        actor=admin, request=request,
        summary=f"Payout batch credited: {batch_id}",
        meta={"credited_records": (res or {}).get("credited_records"),
              "amount_uah": (res or {}).get("credited_amount_uah")},
    )
    return res


@router.post("/admin/payout-batches/{batch_id}/cancel")
async def admin_cancel_batch(batch_id: str, payload: BatchActionPayload = None,
                             request: Request = None,
                             admin=Depends(require_admin)):
    reason = (payload.reason if payload else None)
    res = await cancel_batch(batch_id, admin["id"], reason=reason)
    await write_audit(
        action="payout_batch.cancel", category="payout",
        target_type="lumen_payout_batches", target_id=batch_id,
        actor=admin, request=request,
        summary=f"Payout batch cancelled: {batch_id}",
        meta={"reason": reason},
    )
    return res


# ---- Admin: flat payout records list -----------------------------------------

@router.get("/admin/payout-records")
async def admin_list_records(status: Optional[str] = None, asset_id: Optional[str] = None,
                             investor_id: Optional[str] = None, limit: int = 300,
                             _=Depends(require_admin)):
    q: dict[str, Any] = {}
    if status:
        q["status"] = status
    if asset_id:
        q["asset_id"] = asset_id
    if investor_id:
        q["investor_id"] = investor_id
    items = []
    async for r in (db.lumen_payout_records.find(q)
                    .sort("created_at", -1).limit(min(max(1, limit), 1000))):
        items.append(_record_out(r))
    return {"items": items, "total": len(items)}


__all__ = ["router", "bootstrap_payouts", "ensure_payout_indexes",
           "distribute_amount", "asset_payout_summary"]
