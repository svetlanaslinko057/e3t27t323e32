"""
LUMEN 2.0 — Phase G13 — LP/GP & Waterfall Engine
=================================================

Builds the fund mechanics layer on top of the existing Fund → SPV → Asset
chain (G3):

    Fund → GP (manager) → LPs (commitments)
    Capital Calls (drawdowns from LPs)
    Distributions (Income → Expenses → LP Return → Pref → Carry → Residual)

Collections (NEW, no migration):
    lumen_lp_commitments        — LP/GP commitment to a fund
    lumen_capital_calls         — call notices (% of committed)
    lumen_lp_drawdowns          — per-LP drawdown rows (one per call+commitment)
    lumen_distributions         — distribution runs (Income → waterfall)
    lumen_distribution_lines    — per-LP/GP split of one distribution

NOTE: This is a CASH-BASIS model. No taxes. Currency = UAH.
"""
from __future__ import annotations

import logging
from shared.money import fmt_uah_as_usd, usd_from_uah  # USD display layer
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from lumen_api import (db, get_current_user, require_admin, _strip_mongo,
                       _now, _iso, lr2_perm as _lr2_perm)

logger = logging.getLogger("lumen.lpgp_os")
router = APIRouter(prefix="/api", tags=["lumen-lpgp-os"])


def _uid(u: dict) -> str:
    return u.get("id") or u.get("user_id")


def _round2(v: Any) -> float:
    try:
        return round(float(v or 0), 2)
    except Exception:
        return 0.0


ROLES = ("LP", "GP")
CALL_STATUSES = ("draft", "issued", "completed", "cancelled")
DISTRIBUTION_STATUSES = ("preview", "applied", "cancelled")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — fund + commitments
# ─────────────────────────────────────────────────────────────────────────────

async def _fund_or_404(fund_id: str) -> dict:
    f = await db.lumen_funds.find_one({"id": fund_id}, {"_id": 0})
    if not f:
        raise HTTPException(status_code=404, detail="Фонд не знайдено")
    return f


async def _user_or_404(user_id: str) -> dict:
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "user_id": 1,
                                                        "email": 1, "name": 1})
    if not u:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")
    return u


async def _fund_commitments(fund_id: str) -> list[dict]:
    out: list[dict] = []
    async for c in db.lumen_lp_commitments.find({"fund_id": fund_id}, {"_id": 0}):
        out.append(c)
    return out


async def _fund_calls(fund_id: str) -> list[dict]:
    out: list[dict] = []
    async for c in db.lumen_capital_calls.find({"fund_id": fund_id}, {"_id": 0}).sort("created_at", 1):
        out.append(c)
    return out


async def _fund_distributions(fund_id: str) -> list[dict]:
    out: list[dict] = []
    async for d in db.lumen_distributions.find({"fund_id": fund_id, "status": {"$ne": "cancelled"}},
                                                {"_id": 0}).sort("created_at", -1):
        out.append(d)
    return out


async def _commitment_drawdowns(commitment_id: str) -> list[dict]:
    out: list[dict] = []
    async for d in db.lumen_lp_drawdowns.find({"commitment_id": commitment_id}, {"_id": 0}):
        out.append(d)
    return out


def _commit_out(c: dict, user: Optional[dict] = None, called: float = 0,
                paid: float = 0, distributions: float = 0) -> dict:
    out = _strip_mongo(dict(c))
    out["called_uah"] = _round2(called)
    out["paid_uah"] = _round2(paid)
    out["uncalled_uah"] = _round2(float(c.get("amount_uah") or 0) - called)
    out["distributions_uah"] = _round2(distributions)
    if user:
        out["investor_name"] = user.get("name") or user.get("email")
        out["investor_email"] = user.get("email")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Aggregation: state of a single commitment (called/paid/distributions)
# ─────────────────────────────────────────────────────────────────────────────

async def _commitment_state(c: dict) -> dict:
    called = 0.0
    paid = 0.0
    distros = 0.0
    async for d in db.lumen_lp_drawdowns.find({"commitment_id": c["id"]}, {"_id": 0}):
        called += float(d.get("amount_uah") or 0)
        if d.get("paid_at"):
            paid += float(d.get("amount_uah") or 0)
    async for l in db.lumen_distribution_lines.find({"commitment_id": c["id"]}, {"_id": 0}):
        distros += float(l.get("amount_uah") or 0)
    u = await db.users.find_one({"user_id": c.get("investor_id")},
                                 {"_id": 0, "email": 1, "name": 1})
    return _commit_out(c, u, called=called, paid=paid, distributions=distros)


# ─────────────────────────────────────────────────────────────────────────────
# Fund summary (NAV from G3 + aggregates from commitments/calls/distros)
# ─────────────────────────────────────────────────────────────────────────────

async def _fund_summary(fund_id: str) -> dict:
    f = await _fund_or_404(fund_id)
    commits = await _fund_commitments(fund_id)
    total_committed = sum(float(c.get("amount_uah") or 0) for c in commits)

    total_called = 0.0
    total_paid = 0.0
    async for d in db.lumen_lp_drawdowns.find({"fund_id": fund_id}, {"_id": 0}):
        total_called += float(d.get("amount_uah") or 0)
        if d.get("paid_at"):
            total_paid += float(d.get("amount_uah") or 0)

    total_distros = 0.0
    async for ds in db.lumen_distributions.find({"fund_id": fund_id, "status": "applied"},
                                                 {"_id": 0}):
        total_distros += float(ds.get("amount_uah") or 0)

    # NAV from existing institutional engine = sum of SPV asset equity
    nav = 0.0
    try:
        from lumen_institutional_os import _fund_nav_and_holdings
        nav, _ = await _fund_nav_and_holdings(f)
    except Exception:
        pass

    return {
        "fund_id": fund_id,
        "name": f.get("name"),
        "status": f.get("status"),
        "target_size_uah": f.get("target_size_uah"),
        "committed_uah": _round2(total_committed),
        "called_uah": _round2(total_called),
        "paid_uah": _round2(total_paid),
        "uncalled_uah": _round2(total_committed - total_called),
        "distributions_uah": _round2(total_distros),
        "nav_uah": _round2(nav),
        "lp_count": sum(1 for c in commits if c.get("role") == "LP"),
        "gp_count": sum(1 for c in commits if c.get("role") == "GP"),
    }


# ════════════════════════════════════════════════════════════════════════════
# Admin endpoints
# ════════════════════════════════════════════════════════════════════════════

class CommitmentIn(BaseModel):
    investor_id: str
    amount_uah: float = Field(gt=0)
    role: Optional[str] = "LP"
    pref_rate: Optional[float] = 0.08   # 8% preferred return (annualised)
    carry_rate: Optional[float] = 0.20  # 20% carry above pref


@router.get("/admin/funds/{fund_id}/summary")
async def admin_fund_summary(fund_id: str, _=Depends(require_admin)):
    return await _fund_summary(fund_id)


@router.get("/admin/funds/{fund_id}/commitments")
async def admin_list_commitments(fund_id: str, _=Depends(require_admin)):
    await _fund_or_404(fund_id)
    commits = await _fund_commitments(fund_id)
    out = []
    for c in commits:
        out.append(await _commitment_state(c))
    out.sort(key=lambda x: -float(x.get("amount_uah") or 0))
    return {"items": out, "count": len(out)}


@router.post("/admin/funds/{fund_id}/commitments")
async def admin_create_commitment(fund_id: str, payload: CommitmentIn,
                                   admin=Depends(require_admin),
                                   _perm=Depends(_lr2_perm("lp_commitment", "write"))):
    await _fund_or_404(fund_id)
    u = await _user_or_404(payload.investor_id)
    role = (payload.role or "LP").upper()
    if role not in ROLES:
        raise HTTPException(status_code=400, detail=f"role має бути LP або GP")
    existing = await db.lumen_lp_commitments.find_one(
        {"fund_id": fund_id, "investor_id": payload.investor_id})
    if existing:
        raise HTTPException(status_code=400,
                             detail="У цього інвестора вже є зобов'язання у фонді")
    doc = {
        "id": f"com-{uuid.uuid4().hex[:12]}", "fund_id": fund_id,
        "investor_id": payload.investor_id, "investor_name": u.get("name"),
        "role": role, "amount_uah": _round2(payload.amount_uah),
        "pref_rate": payload.pref_rate, "carry_rate": payload.carry_rate,
        "status": "active", "created_at": _now(), "updated_at": _now(),
    }
    await db.lumen_lp_commitments.insert_one(doc)
    await _audit_safe("lpgp.commit.create", "system", "lumen_lp_commitments",
                      doc["id"], f"Commit {role} {doc['amount_uah']} → {u.get('email')}",
                      _uid(admin))
    return await _commitment_state(doc)


@router.delete("/admin/funds/{fund_id}/commitments/{commitment_id}")
async def admin_delete_commitment(fund_id: str, commitment_id: str,
                                   admin=Depends(require_admin),
                                   _perm=Depends(_lr2_perm("lp_commitment", "delete"))):
    # only allow delete if no drawdowns/distributions
    if await db.lumen_lp_drawdowns.count_documents({"commitment_id": commitment_id}):
        raise HTTPException(status_code=400,
                             detail="Не можна видалити: вже є списання капіталу")
    if await db.lumen_distribution_lines.count_documents({"commitment_id": commitment_id}):
        raise HTTPException(status_code=400,
                             detail="Не можна видалити: вже є виплати")
    res = await db.lumen_lp_commitments.delete_one({"id": commitment_id})
    return {"deleted": res.deleted_count > 0}


# ─── Capital calls ──────────────────────────────────────────────────────────

class CapitalCallIn(BaseModel):
    percent: float = Field(gt=0, le=100)  # of committed
    due_date: Optional[str] = None
    note: Optional[str] = None


@router.post("/admin/funds/{fund_id}/calls")
async def admin_create_call(fund_id: str, payload: CapitalCallIn,
                             admin=Depends(require_admin),
                             _perm=Depends(_lr2_perm("capital_call", "write"))):
    await _fund_or_404(fund_id)
    commits = await _fund_commitments(fund_id)
    if not commits:
        raise HTTPException(status_code=400, detail="У фонді немає зобов'язань")
    call_id = f"call-{uuid.uuid4().hex[:12]}"
    seq = await db.lumen_capital_calls.count_documents({"fund_id": fund_id}) + 1
    due = None
    try:
        if payload.due_date:
            due = datetime.fromisoformat(payload.due_date.replace("Z", "+00:00"))
    except Exception:
        due = None
    if not due:
        due = _now() + timedelta(days=14)

    total = 0.0
    lines = []
    for c in commits:
        amt = _round2(float(c.get("amount_uah") or 0) * float(payload.percent) / 100.0)
        if amt <= 0:
            continue
        total += amt
        lines.append({
            "id": f"dd-{uuid.uuid4().hex[:12]}", "call_id": call_id,
            "fund_id": fund_id, "commitment_id": c["id"],
            "investor_id": c["investor_id"], "investor_name": c.get("investor_name"),
            "amount_uah": amt, "status": "issued", "paid_at": None,
            "created_at": _now(), "updated_at": _now(),
        })

    call_doc = {
        "id": call_id, "fund_id": fund_id, "seq": seq,
        "percent": float(payload.percent), "due_date": due,
        "note": payload.note, "status": "issued",
        "total_amount_uah": _round2(total), "lines_count": len(lines),
        "created_at": _now(), "updated_at": _now(),
    }
    await db.lumen_capital_calls.insert_one(call_doc)
    if lines:
        await db.lumen_lp_drawdowns.insert_many(lines)
    await _audit_safe("lpgp.call.create", "system", "lumen_capital_calls",
                      call_id, f"Capital call #{seq} · {payload.percent}% · {fmt_uah_as_usd(total)}",
                      _uid(admin))
    return _strip_mongo(call_doc)


@router.get("/admin/funds/{fund_id}/calls")
async def admin_list_calls(fund_id: str, _=Depends(require_admin)):
    await _fund_or_404(fund_id)
    items = []
    async for c in db.lumen_capital_calls.find({"fund_id": fund_id}, {"_id": 0}).sort("created_at", -1):
        items.append(_strip_mongo(c))
    return {"items": items, "count": len(items)}


@router.get("/admin/funds/{fund_id}/calls/{call_id}")
async def admin_call_detail(fund_id: str, call_id: str, _=Depends(require_admin)):
    c = await db.lumen_capital_calls.find_one({"id": call_id, "fund_id": fund_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Capital call не знайдено")
    lines = []
    async for l in db.lumen_lp_drawdowns.find({"call_id": call_id}, {"_id": 0}):
        lines.append(_strip_mongo(l))
    return {"call": _strip_mongo(c), "lines": lines}


@router.post("/admin/calls/{call_id}/lines/{drawdown_id}/mark-paid")
async def admin_mark_paid(call_id: str, drawdown_id: str,
                           admin=Depends(require_admin),
                           _perm=Depends(_lr2_perm("capital_call", "approve"))):
    res = await db.lumen_lp_drawdowns.update_one(
        {"id": drawdown_id, "call_id": call_id, "paid_at": None},
        {"$set": {"paid_at": _now(), "status": "paid", "updated_at": _now()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Рядок не знайдено або вже оплачений")
    # If all lines paid → mark call as completed
    pending = await db.lumen_lp_drawdowns.count_documents({"call_id": call_id, "paid_at": None})
    if pending == 0:
        await db.lumen_capital_calls.update_one(
            {"id": call_id},
            {"$set": {"status": "completed", "updated_at": _now()}})
    return {"ok": True, "pending": pending}


# ─── Distributions + Waterfall ──────────────────────────────────────────────

class DistributionIn(BaseModel):
    income_uah: float = Field(gt=0)
    expenses_uah: Optional[float] = 0.0
    pref_rate: Optional[float] = 0.08
    carry_rate: Optional[float] = 0.20
    note: Optional[str] = None
    # When applying:
    apply: Optional[bool] = False


def _compute_waterfall(commits: list[dict], total_paid_in_uah: float,
                       income: float, expenses: float,
                       pref_rate: float, carry_rate: float) -> dict:
    """
    Simplified waterfall (no taxes):
      1) Net income = income - expenses
      2) Return of capital to LPs pro rata (cap at paid-in)
      3) Pref return to LPs (pref_rate * paid-in, simple)
      4) Carry to GP from residual (carry_rate)
      5) Residual to LPs pro rata
    Returns dict with stages + per-commit lines.
    """
    net = max(0.0, _round2(income - (expenses or 0.0)))

    lps = [c for c in commits if c.get("role") == "LP"]
    gps = [c for c in commits if c.get("role") == "GP"]
    lp_paid_in = sum(_lp_paid_in_cache(c) for c in lps) if lps else 0.0
    # We won't keep an actual cache — pull synchronously not possible here;
    # the caller is responsible to provide aggregated paid-in via total_paid_in_uah.
    lp_paid_in = max(0.0, total_paid_in_uah)

    pref_pool_needed = lp_paid_in * float(pref_rate or 0)
    # Stage 1: return of capital (cap at lp_paid_in)
    roc = min(net, lp_paid_in)
    net -= roc
    # Stage 2: preferred return
    pref = min(net, pref_pool_needed)
    net -= pref
    # Stage 3: carry
    carry = _round2(net * float(carry_rate or 0))
    net -= carry
    # Stage 4: residual to LPs (pro rata of paid-in or commitment)
    residual = net

    lines = []
    if lp_paid_in > 0 and lps:
        for c in lps:
            paid_in = _lp_paid_in_cache(c)
            share = paid_in / lp_paid_in if lp_paid_in else 0
            line = {
                "commitment_id": c["id"], "investor_id": c["investor_id"],
                "investor_name": c.get("investor_name"), "role": "LP",
                "return_of_capital_uah": _round2(roc * share),
                "preferred_return_uah": _round2(pref * share),
                "residual_uah": _round2(residual * share),
                "carry_uah": 0.0,
            }
            line["amount_uah"] = _round2(line["return_of_capital_uah"] +
                                          line["preferred_return_uah"] +
                                          line["residual_uah"])
            lines.append(line)
    elif lps:
        # No paid-in yet but distribution happening → split pro rata of commitment
        total_commit = sum(float(c.get("amount_uah") or 0) for c in lps)
        for c in lps:
            share = float(c.get("amount_uah") or 0) / total_commit if total_commit else 0
            line = {
                "commitment_id": c["id"], "investor_id": c["investor_id"],
                "investor_name": c.get("investor_name"), "role": "LP",
                "return_of_capital_uah": 0.0, "preferred_return_uah": 0.0,
                "residual_uah": _round2((roc + pref + residual) * share),
                "carry_uah": 0.0,
            }
            line["amount_uah"] = line["residual_uah"]
            lines.append(line)

    # Carry → GPs pro rata of commitment (or single GP gets all)
    if carry > 0 and gps:
        total_gp = sum(float(c.get("amount_uah") or 0) for c in gps) or 1.0
        for c in gps:
            share = float(c.get("amount_uah") or 0) / total_gp
            line = {
                "commitment_id": c["id"], "investor_id": c["investor_id"],
                "investor_name": c.get("investor_name"), "role": "GP",
                "return_of_capital_uah": 0.0, "preferred_return_uah": 0.0,
                "residual_uah": 0.0,
                "carry_uah": _round2(carry * share),
            }
            line["amount_uah"] = line["carry_uah"]
            lines.append(line)
    elif carry > 0 and not gps:
        # No GP commitment → assign carry to a synthetic "Manager"
        lines.append({
            "commitment_id": None, "investor_id": None,
            "investor_name": "GP / Manager", "role": "GP",
            "return_of_capital_uah": 0.0, "preferred_return_uah": 0.0,
            "residual_uah": 0.0, "carry_uah": _round2(carry),
            "amount_uah": _round2(carry),
        })

    summary = {
        "gross_income_uah": _round2(income),
        "expenses_uah": _round2(expenses or 0),
        "net_income_uah": _round2(income - (expenses or 0)),
        "lp_paid_in_uah": _round2(lp_paid_in),
        "stage_return_of_capital_uah": _round2(roc),
        "stage_preferred_return_uah": _round2(pref),
        "stage_carry_uah": _round2(carry),
        "stage_residual_uah": _round2(residual),
        "pref_rate": float(pref_rate or 0),
        "carry_rate": float(carry_rate or 0),
    }
    return {"summary": summary, "lines": lines}


def _lp_paid_in_cache(c: dict) -> float:
    # piggyback paid-in cache attached during /preview enrichment
    return float(c.get("_paid_in", 0.0))


@router.post("/admin/funds/{fund_id}/distributions/preview")
async def admin_preview_distribution(fund_id: str, payload: DistributionIn,
                                      _=Depends(require_admin)):
    await _fund_or_404(fund_id)
    commits = await _fund_commitments(fund_id)
    if not commits:
        raise HTTPException(status_code=400, detail="У фонді немає LP/GP зобов'язань")
    # Enrich commits with paid-in cache
    lp_paid_in_total = 0.0
    for c in commits:
        paid_in = 0.0
        async for d in db.lumen_lp_drawdowns.find(
                {"commitment_id": c["id"], "paid_at": {"$ne": None}}, {"_id": 0}):
            paid_in += float(d.get("amount_uah") or 0)
        c["_paid_in"] = paid_in
        if c.get("role") == "LP":
            lp_paid_in_total += paid_in
    wf = _compute_waterfall(commits, lp_paid_in_total,
                             float(payload.income_uah), float(payload.expenses_uah or 0),
                             float(payload.pref_rate or 0.08),
                             float(payload.carry_rate or 0.20))
    return {"status": "preview", **wf}


@router.post("/admin/funds/{fund_id}/distributions/apply")
async def admin_apply_distribution(fund_id: str, payload: DistributionIn,
                                    admin=Depends(require_admin),
                                    _perm=Depends(_lr2_perm("distribution", "approve"))):
    """Compute and persist a distribution run."""
    f = await _fund_or_404(fund_id)
    commits = await _fund_commitments(fund_id)
    if not commits:
        raise HTTPException(status_code=400, detail="У фонді немає LP/GP зобов'язань")
    lp_paid_in_total = 0.0
    for c in commits:
        paid_in = 0.0
        async for d in db.lumen_lp_drawdowns.find(
                {"commitment_id": c["id"], "paid_at": {"$ne": None}}, {"_id": 0}):
            paid_in += float(d.get("amount_uah") or 0)
        c["_paid_in"] = paid_in
        if c.get("role") == "LP":
            lp_paid_in_total += paid_in

    wf = _compute_waterfall(commits, lp_paid_in_total,
                             float(payload.income_uah), float(payload.expenses_uah or 0),
                             float(payload.pref_rate or 0.08),
                             float(payload.carry_rate or 0.20))

    dist_id = f"dist-{uuid.uuid4().hex[:12]}"
    seq = await db.lumen_distributions.count_documents({"fund_id": fund_id}) + 1
    summary = wf["summary"]
    doc = {
        "id": dist_id, "fund_id": fund_id, "fund_name": f.get("name"),
        "seq": seq, "status": "applied",
        "amount_uah": _round2(summary["net_income_uah"]),
        "income_uah": _round2(payload.income_uah),
        "expenses_uah": _round2(payload.expenses_uah or 0),
        "pref_rate": float(payload.pref_rate or 0.08),
        "carry_rate": float(payload.carry_rate or 0.20),
        "summary": summary, "note": payload.note,
        "created_at": _now(), "updated_at": _now(),
    }
    await db.lumen_distributions.insert_one(doc)
    rows = []
    for line in wf["lines"]:
        rows.append({
            "id": f"dl-{uuid.uuid4().hex[:12]}", "distribution_id": dist_id,
            "fund_id": fund_id,
            **line, "created_at": _now(),
        })
    if rows:
        await db.lumen_distribution_lines.insert_many(rows)
    await _audit_safe("lpgp.distribution.apply", "system", "lumen_distributions",
                      dist_id, f"Distribution #{seq} · {fmt_uah_as_usd(summary['net_income_uah'])}",
                      _uid(admin))
    return {**wf, "id": dist_id, "status": "applied"}


@router.get("/admin/funds/{fund_id}/distributions")
async def admin_list_distributions(fund_id: str, _=Depends(require_admin)):
    await _fund_or_404(fund_id)
    items = []
    async for d in db.lumen_distributions.find({"fund_id": fund_id}, {"_id": 0}).sort("created_at", -1):
        items.append(_strip_mongo(d))
    return {"items": items, "count": len(items)}


@router.get("/admin/distributions/{distribution_id}")
async def admin_distribution_detail(distribution_id: str, _=Depends(require_admin)):
    d = await db.lumen_distributions.find_one({"id": distribution_id}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Виплата не знайдена")
    lines = []
    async for l in db.lumen_distribution_lines.find(
            {"distribution_id": distribution_id}, {"_id": 0}):
        lines.append(_strip_mongo(l))
    return {"distribution": _strip_mongo(d), "lines": lines}


# ════════════════════════════════════════════════════════════════════════════
# Investor / LP endpoints
# ════════════════════════════════════════════════════════════════════════════

@router.get("/investor/lp/funds")
async def my_lp_funds(user=Depends(get_current_user)):
    uid = _uid(user)
    out = []
    async for c in db.lumen_lp_commitments.find({"investor_id": uid}, {"_id": 0}):
        f = await db.lumen_funds.find_one({"id": c.get("fund_id")},
                                            {"_id": 0, "id": 1, "name": 1, "kind": 1, "status": 1})
        state = await _commitment_state(c)
        out.append({
            **state,
            "fund": _strip_mongo(f) if f else None,
        })
    return {"items": out, "count": len(out)}


@router.get("/investor/lp/funds/{fund_id}")
async def my_lp_fund_detail(fund_id: str, user=Depends(get_current_user)):
    uid = _uid(user)
    c = await db.lumen_lp_commitments.find_one(
        {"investor_id": uid, "fund_id": fund_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Зобов'язань у фонді не знайдено")
    state = await _commitment_state(c)
    # Drawdowns + distribution lines
    drawdowns = []
    async for d in db.lumen_lp_drawdowns.find({"commitment_id": c["id"]},
                                                {"_id": 0}).sort("created_at", -1):
        drawdowns.append(_strip_mongo(d))
    lines = []
    async for l in db.lumen_distribution_lines.find(
            {"commitment_id": c["id"]}, {"_id": 0}).sort("created_at", -1):
        # join distribution doc
        ds = await db.lumen_distributions.find_one(
            {"id": l.get("distribution_id")}, {"_id": 0, "seq": 1, "created_at": 1, "note": 1})
        lines.append({**_strip_mongo(l), "distribution": _strip_mongo(ds) if ds else None})
    # Fund-level summary (so LP sees fund context)
    summary = await _fund_summary(fund_id)
    # Crude IRR/NAV/Multiple
    committed = float(state.get("amount_uah") or 0)
    paid = float(state.get("paid_uah") or 0)
    distros = float(state.get("distributions_uah") or 0)
    multiple = (distros / paid) if paid else None
    return {
        **state,
        "fund": summary,
        "drawdowns": drawdowns,
        "distributions": lines,
        "multiple": round(multiple, 2) if multiple is not None else None,
    }


# ════════════════════════════════════════════════════════════════════════════
# Helpers + indexes + seed
# ════════════════════════════════════════════════════════════════════════════

async def _audit_safe(action: str, category: str, target_type: str,
                       target_id: str, summary: str, actor: Optional[str]) -> None:
    try:
        from lumen_audit import write_audit
        await write_audit(action=action, category="system", target_type=target_type,
                           target_id=target_id, summary=summary,
                           actor={"id": actor} if actor else None)
    except Exception:
        pass


async def ensure_lpgp_indexes() -> None:
    try:
        await db.lumen_lp_commitments.create_index(
            [("fund_id", 1), ("investor_id", 1)], unique=True)
        await db.lumen_lp_commitments.create_index([("investor_id", 1)])
        await db.lumen_capital_calls.create_index([("fund_id", 1), ("seq", 1)], unique=True)
        await db.lumen_lp_drawdowns.create_index([("call_id", 1)])
        await db.lumen_lp_drawdowns.create_index([("commitment_id", 1)])
        await db.lumen_distributions.create_index([("fund_id", 1), ("seq", 1)], unique=True)
        await db.lumen_distribution_lines.create_index([("distribution_id", 1)])
        await db.lumen_distribution_lines.create_index([("commitment_id", 1)])
    except Exception:
        logger.exception("LP/GP indexes failed")


async def seed_lpgp_demo() -> dict:
    """Idempotent: layer LP/GP onto existing Phase G funds + demo investors."""
    await ensure_lpgp_indexes()
    if await db.lumen_lp_commitments.count_documents({}) > 0:
        return {"skipped": "commitments already present"}
    stats = {"commitments": 0, "calls": 0, "drawdowns_paid": 0, "distributions": 0}

    # GP = LUMEN Capital operator's admin user (admin@atlas.dev as proxy GP)
    gp_user = await db.users.find_one({"email": "admin@atlas.dev"},
                                       {"_id": 0, "user_id": 1, "name": 1})

    lp_demo = [
        ("family@atlas.dev", 5_000_000.0),
        ("olena.k@lumen.test", 1_500_000.0),
        ("ihor.p@lumen.test", 2_500_000.0),
    ]

    async for f in db.lumen_funds.find({}, {"_id": 0, "id": 1, "name": 1}):
        fid = f["id"]
        # GP carry-only stake (small commitment)
        if gp_user:
            await db.lumen_lp_commitments.insert_one({
                "id": f"com-{uuid.uuid4().hex[:12]}", "fund_id": fid,
                "investor_id": gp_user["user_id"], "investor_name": gp_user.get("name") or "GP",
                "role": "GP", "amount_uah": 1_000_000.0,
                "pref_rate": 0.08, "carry_rate": 0.20,
                "status": "active", "created_at": _now(), "updated_at": _now(),
            })
            stats["commitments"] += 1

        # LPs
        for email, amount in lp_demo:
            u = await db.users.find_one({"email": email},
                                         {"_id": 0, "user_id": 1, "name": 1})
            if not u:
                continue
            await db.lumen_lp_commitments.insert_one({
                "id": f"com-{uuid.uuid4().hex[:12]}", "fund_id": fid,
                "investor_id": u["user_id"], "investor_name": u.get("name"),
                "role": "LP", "amount_uah": float(amount),
                "pref_rate": 0.08, "carry_rate": 0.20,
                "status": "active", "created_at": _now(), "updated_at": _now(),
            })
            stats["commitments"] += 1

        # 1st capital call = 40% of committed, all paid
        commits = await _fund_commitments(fid)
        if commits:
            call_id = f"call-{uuid.uuid4().hex[:12]}"
            total = 0.0
            lines = []
            for c in commits:
                amt = _round2(float(c["amount_uah"]) * 0.4)
                total += amt
                lines.append({
                    "id": f"dd-{uuid.uuid4().hex[:12]}", "call_id": call_id,
                    "fund_id": fid, "commitment_id": c["id"],
                    "investor_id": c["investor_id"],
                    "investor_name": c.get("investor_name"),
                    "amount_uah": amt, "status": "paid",
                    "paid_at": _now() - timedelta(days=30),
                    "created_at": _now() - timedelta(days=45),
                    "updated_at": _now() - timedelta(days=30),
                })
            await db.lumen_capital_calls.insert_one({
                "id": call_id, "fund_id": fid, "seq": 1, "percent": 40.0,
                "due_date": _now() - timedelta(days=14),
                "note": "Seed capital call",
                "status": "completed",
                "total_amount_uah": _round2(total), "lines_count": len(lines),
                "created_at": _now() - timedelta(days=45),
                "updated_at": _now() - timedelta(days=30),
            })
            await db.lumen_lp_drawdowns.insert_many(lines)
            stats["calls"] += 1
            stats["drawdowns_paid"] += len(lines)
    return stats


__all__ = ["router", "ensure_lpgp_indexes", "seed_lpgp_demo"]
