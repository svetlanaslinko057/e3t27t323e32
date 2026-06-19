"""
LUMEN — Compliance Screening (Sanctions + PEP + Risk Scoring + AML Audit)
=========================================================================

Closes ТЗ Level-B stopper: until this module existed, the platform trusted
``users.email`` + a self-declared ``is_pep`` flag and performed **no** sanctions
or PEP screening, **no** risk scoring, and kept **no** AML audit trail. An
investment platform cannot legally onboard a single real investor without it.

Contract enforced by ``sanctions_pep_contract.py`` (S1–S9). No external API
keys required — screening runs against a consolidated static watchlist
(OFAC SDN + EU + UK HMT + Ukraine NSDC + a curated PEP list) with deterministic
fuzzy name matching (stdlib ``difflib`` — no new deps). When a paid provider
(Dow Jones / ComplyAdvantage / Refinitiv) lands later, ``screen_name`` is the
single seam to swap.

What this module owns
---------------------
Collections (created idempotently with indexes):
  • ``lumen_watchlist``          — sanctions + PEP entries (seeded, admin-extensible)
  • ``lumen_screening_results``  — every screen run (immutable append; AML evidence)
  • ``lumen_compliance_cases``   — review queue / SoF workflow (risk band + escalation)
  • ``lumen_aml_audit``          — APPEND-ONLY journal (who / what / when / why)

Engine
  • ``_normalize_name``          — unicode-fold + token-sort (handles Latin + Cyrillic)
  • ``screen_name``              — fuzzy match → list of {entry, score, list_type}
  • ``compute_risk_band``        — LOW / MEDIUM / HIGH / CRITICAL from
                                   jurisdiction + PEP + sanction-hit + transaction size
  • ``run_screening``            — orchestrates screen → result → case → AML audit
  • ``is_blocked``               — funding/withdrawal gate decision for an investor

Hooks (called in-architecture from existing flows)
  • ``screen_on_kyc_submit``     — lumen_kyc.submit_kyc
  • ``assert_not_blocked``       — lumen_investment_core.create_intent (sanctions gate)
  • ``screen_on_profile_change`` — lumen_kyc.patch_my_profile
  • ``screen_on_register``       — server.py /auth/register hook (light name screen)

Endpoints
  Admin  /api/admin/compliance/dashboard
         /api/admin/compliance/cases            (+ ?status= ?risk=)
         /api/admin/compliance/cases/{id}
         /api/admin/compliance/cases/{id}/decision   (clear|escalate|block)
         /api/admin/compliance/screen           (ad-hoc manual screen)
         /api/admin/compliance/watchlist        (GET list / POST add)
         /api/admin/compliance/aml-audit        (append-only journal view)
  Investor /api/investor/compliance/status      (coarse, no match-detail leak)
"""
from __future__ import annotations

import os
import re
import uuid
import logging
import unicodedata
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from lumen_api import db, get_current_user, require_admin

logger = logging.getLogger("lumen.compliance")
router = APIRouter(prefix="/api", tags=["lumen-compliance-screening"])

# ──────────────────────────────────────────────────────────────────────────
# Collections
# ──────────────────────────────────────────────────────────────────────────
WATCHLIST = "lumen_watchlist"
RESULTS = "lumen_screening_results"
CASES = "lumen_compliance_cases"
AML = "lumen_aml_audit"

# ──────────────────────────────────────────────────────────────────────────
# Risk model
# ──────────────────────────────────────────────────────────────────────────
RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"
RISK_CRITICAL = "CRITICAL"
RISK_ORDER = {RISK_LOW: 0, RISK_MEDIUM: 1, RISK_HIGH: 2, RISK_CRITICAL: 3}

# FATF "call for action" + "increased monitoring" sample + war/embargo zones.
# ISO-3166 alpha-2.
HIGH_RISK_JURISDICTIONS = {
    "KP", "IR", "MM",                       # FATF call-for-action
    "SY", "AF", "YE", "SS", "SD", "LY",     # conflict / embargo
    "RU", "BY",                             # sanctioned regimes
    "VE", "ZW", "CU",
}
# Elevated (one notch) — FATF grey-list sample.
ELEVATED_JURISDICTIONS = {
    "NG", "ZA", "AE", "TR", "PA", "PH", "KH", "JM", "ML", "MZ", "SN", "TZ",
    "HR", "BG", "MC", "GI", "VU",
}

# Transaction-size thresholds (UAH). > LARGE → bump one notch; > VERY_LARGE → two.
TX_LARGE_UAH = float(os.environ.get("LUMEN_AML_TX_LARGE_UAH", "400000"))      # ~€10k
TX_VERY_LARGE_UAH = float(os.environ.get("LUMEN_AML_TX_VERY_LARGE_UAH", "4000000"))

# Match thresholds
SCORE_CONFIRMED = 0.93   # >= → confirmed match
SCORE_POTENTIAL = 0.82   # >= → potential match (manual review)

CASE_OPEN = "open"
CASE_IN_REVIEW = "in_review"
CASE_ESCALATED = "escalated"
CASE_CLEARED = "cleared"
CASE_BLOCKED = "blocked"
OPEN_CASE_STATES = {CASE_OPEN, CASE_IN_REVIEW, CASE_ESCALATED}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ──────────────────────────────────────────────────────────────────────────
# Name normalisation + fuzzy matching
# ──────────────────────────────────────────────────────────────────────────
def _normalize_name(name: Optional[str]) -> str:
    if not name:
        return ""
    # Unicode fold (strip Latin diacritics); keep Cyrillic letters intact.
    nfkd = unicodedata.normalize("NFKD", str(name))
    no_marks = "".join(c for c in nfkd if not unicodedata.combining(c))
    low = no_marks.lower()
    # keep letters/digits/space across scripts
    cleaned = re.sub(r"[^0-9a-zа-яіїєґ\s]", " ", low)
    tokens = sorted(t for t in cleaned.split() if t)
    return " ".join(tokens)


def _token_set(name_norm: str) -> set:
    return set(name_norm.split())


def _match_score(query_norm: str, entry_norm: str) -> float:
    """Hybrid score: token-set Jaccard + sequence ratio of the sorted strings.
    Both are order-insensitive because both sides are token-sorted."""
    if not query_norm or not entry_norm:
        return 0.0
    if query_norm == entry_norm:
        return 1.0
    qs, es = _token_set(query_norm), _token_set(entry_norm)
    inter = len(qs & es)
    union = len(qs | es) or 1
    jaccard = inter / union
    seq = SequenceMatcher(None, query_norm, entry_norm).ratio()
    # Require at least one shared token; otherwise pure seq similarity on short
    # strings produces false positives.
    if inter == 0:
        return min(seq, 0.5)
    return round(0.5 * jaccard + 0.5 * seq, 4)


# ──────────────────────────────────────────────────────────────────────────
# Screening engine
# ──────────────────────────────────────────────────────────────────────────
async def screen_name(name: str, *, dob: Optional[str] = None,
                      country: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return ranked matches against the watchlist. Each item:
    {entry_id, full_name, source, list_type, score, dob_match}."""
    qn = _normalize_name(name)
    if not qn:
        return []
    matches: List[Dict[str, Any]] = []
    cursor = db[WATCHLIST].find({}, {"_id": 0})
    async for e in cursor:
        score = _match_score(qn, e.get("normalized_name", ""))
        # alias matching — take the best of name + aliases
        for al in e.get("aliases", []) or []:
            score = max(score, _match_score(qn, _normalize_name(al)))
        if score < SCORE_POTENTIAL:
            continue
        dob_match = None
        if dob and e.get("dob"):
            dob_match = (str(dob)[:10] == str(e.get("dob"))[:10])
            # A DOB conflict downgrades a fuzzy (non-exact) name match.
            if dob_match is False and score < 0.99:
                score = round(score * 0.9, 4)
        if score < SCORE_POTENTIAL:
            continue
        matches.append({
            "entry_id": e.get("id"),
            "full_name": e.get("full_name"),
            "source": e.get("source"),
            "list_type": e.get("list_type"),
            "program": e.get("program"),
            "score": score,
            "dob_match": dob_match,
        })
    matches.sort(key=lambda m: m["score"], reverse=True)
    return matches[:25]


def _classify(matches: List[Dict[str, Any]]) -> str:
    """clear | potential_match | confirmed_match from match scores."""
    if not matches:
        return "clear"
    top = matches[0]["score"]
    if top >= SCORE_CONFIRMED:
        return "confirmed_match"
    return "potential_match"


def compute_risk_band(*, country: Optional[str] = None, is_pep: bool = False,
                      sanction_decision: str = "clear",
                      amount_uah: Optional[float] = None) -> Dict[str, Any]:
    """Deterministic risk band + the reasons that produced it."""
    reasons: List[str] = []
    level = RISK_ORDER[RISK_LOW]

    cc = (country or "").upper()[:2]
    if cc in HIGH_RISK_JURISDICTIONS:
        level = max(level, RISK_ORDER[RISK_HIGH])
        reasons.append(f"high_risk_jurisdiction:{cc}")
    elif cc in ELEVATED_JURISDICTIONS:
        level = max(level, RISK_ORDER[RISK_MEDIUM])
        reasons.append(f"elevated_jurisdiction:{cc}")

    if is_pep:
        level = max(level, RISK_ORDER[RISK_HIGH])
        reasons.append("pep_positive")

    if sanction_decision == "confirmed_match":
        level = RISK_ORDER[RISK_CRITICAL]
        reasons.append("sanctions_confirmed_match")
    elif sanction_decision == "potential_match":
        level = max(level, RISK_ORDER[RISK_HIGH])
        reasons.append("sanctions_potential_match")

    if amount_uah is not None:
        if amount_uah >= TX_VERY_LARGE_UAH:
            level = min(RISK_ORDER[RISK_CRITICAL], level + 2)
            reasons.append("transaction_very_large")
        elif amount_uah >= TX_LARGE_UAH:
            level = min(RISK_ORDER[RISK_CRITICAL], level + 1)
            reasons.append("transaction_large")

    band = {v: k for k, v in RISK_ORDER.items()}[level]
    return {"band": band, "reasons": reasons}


# ──────────────────────────────────────────────────────────────────────────
# AML append-only audit
# ──────────────────────────────────────────────────────────────────────────
async def aml_audit(*, action: str, subject_type: str, subject_id: Optional[str],
                    actor: Optional[str], reason: str = "",
                    detail: Optional[dict] = None) -> str:
    """Append a row to the immutable AML journal. Never updated/deleted."""
    row_id = _new_id("aml")
    try:
        await db[AML].insert_one({
            "id": row_id,
            "action": action,            # what
            "subject_type": subject_type,
            "subject_id": subject_id,
            "actor": actor,              # who
            "reason": reason,            # why
            "detail": detail or {},
            "at": _now(),                # when
            "at_iso": _iso(),
        })
    except Exception as e:  # pragma: no cover — audit must never crash host
        logger.warning("aml_audit insert failed (%s): %s", action, e)
    return row_id


# ──────────────────────────────────────────────────────────────────────────
# Orchestration: screen → result → case → audit
# ──────────────────────────────────────────────────────────────────────────
async def run_screening(*, subject_type: str, subject_id: str, name: str,
                        dob: Optional[str] = None, country: Optional[str] = None,
                        is_pep: bool = False, amount_uah: Optional[float] = None,
                        triggered_by: str = "manual",
                        actor: Optional[str] = None) -> Dict[str, Any]:
    """Run a full screening pass and persist evidence. Returns the result doc.
    Resilient: any failure returns a soft 'error' result rather than raising."""
    try:
        from compliance_provider import get_provider
        matches = await get_provider().screen_name(name, dob=dob, country=country)
        decision = _classify(matches)
        # A PEP-list match counts as PEP even if is_pep flag wasn't declared.
        pep_hit = any(m.get("list_type") == "pep" for m in matches)
        sanction_matches = [m for m in matches if m.get("list_type") == "sanction"]
        sanction_decision = _classify(sanction_matches)
        risk = compute_risk_band(
            country=country, is_pep=(is_pep or pep_hit),
            sanction_decision=sanction_decision, amount_uah=amount_uah,
        )

        result_id = _new_id("scr")
        result = {
            "id": result_id,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "query_name": name,
            "query_dob": dob,
            "query_country": (country or "").upper()[:2] or None,
            "query_amount_uah": amount_uah,
            "matches": matches,
            "top_score": (matches[0]["score"] if matches else 0.0),
            "decision": decision,
            "sanction_decision": sanction_decision,
            "pep_hit": bool(pep_hit or is_pep),
            "risk_band": risk["band"],
            "risk_reasons": risk["reasons"],
            "triggered_by": triggered_by,
            "actor": actor,
            "created_at": _now(),
            "created_at_iso": _iso(),
        }
        await db[RESULTS].insert_one(dict(result))

        # Open/refresh a compliance case when there is anything to review.
        needs_case = (decision != "clear") or risk["band"] in (RISK_HIGH, RISK_CRITICAL)
        case_id = None
        if subject_type == "investor" and needs_case:
            case_id = await _upsert_case(
                investor_id=subject_id, result=result, risk_band=risk["band"],
                decision=decision)

        await aml_audit(
            action=f"screening.{triggered_by}",
            subject_type=subject_type, subject_id=subject_id, actor=actor,
            reason=f"decision={decision} risk={risk['band']}",
            detail={"result_id": result_id, "top_score": result["top_score"],
                    "case_id": case_id, "pep_hit": result["pep_hit"]},
        )
        result["case_id"] = case_id
        result.pop("_id", None)
        return result
    except Exception as e:  # pragma: no cover
        logger.exception("run_screening failed: %s", e)
        return {"id": None, "decision": "error", "risk_band": RISK_LOW,
                "matches": [], "error": str(e)}


async def _upsert_case(*, investor_id: str, result: dict, risk_band: str,
                       decision: str) -> str:
    """One open case per investor; refresh its risk + latest evidence."""
    existing = await db[CASES].find_one(
        {"investor_id": investor_id, "status": {"$in": list(OPEN_CASE_STATES)}})
    case_type = ("sanctions" if any(m.get("list_type") == "sanction"
                                    for m in result.get("matches", []))
                 else ("pep" if result.get("pep_hit") else "risk"))
    # A confirmed sanction match auto-blocks pending compliance review.
    auto_status = CASE_BLOCKED if result.get("sanction_decision") == "confirmed_match" else CASE_OPEN
    if existing:
        new_status = existing["status"]
        if auto_status == CASE_BLOCKED:
            new_status = CASE_BLOCKED
        await db[CASES].update_one(
            {"id": existing["id"]},
            {"$set": {"risk_band": risk_band, "case_type": case_type,
                      "latest_result_id": result["id"], "status": new_status,
                      "updated_at": _now(), "updated_at_iso": _iso()}},
        )
        return existing["id"]
    case_id = _new_id("case")
    await db[CASES].insert_one({
        "id": case_id,
        "investor_id": investor_id,
        "case_type": case_type,
        "status": auto_status,
        "risk_band": risk_band,
        "screening_result_id": result["id"],
        "latest_result_id": result["id"],
        "investor_name": result.get("query_name"),
        "investor_country": result.get("query_country"),
        "opened_at": _now(),
        "opened_at_iso": _iso(),
        "decided_at": None,
        "decided_by": None,
        "decision_reason": None,
        "notes": [],
        "updated_at": _now(),
    })
    return case_id


# ──────────────────────────────────────────────────────────────────────────
# Gate decision
# ──────────────────────────────────────────────────────────────────────────
async def is_blocked(investor_id: str) -> Dict[str, Any]:
    """True when the investor has an OPEN case in BLOCKED status, OR any
    confirmed sanction screening result that hasn't been explicitly cleared."""
    blocked_case = await db[CASES].find_one(
        {"investor_id": investor_id, "status": CASE_BLOCKED})
    if blocked_case:
        return {"blocked": True, "reason": "compliance_blocked",
                "case_id": blocked_case["id"], "risk_band": blocked_case.get("risk_band")}
    # confirmed sanction match w/o a cleared case
    confirmed = await db[RESULTS].find_one(
        {"subject_id": investor_id, "sanction_decision": "confirmed_match"})
    if confirmed:
        cleared = await db[CASES].find_one(
            {"investor_id": investor_id, "status": CASE_CLEARED})
        if not cleared:
            return {"blocked": True, "reason": "sanctions_confirmed_match",
                    "result_id": confirmed["id"], "risk_band": RISK_CRITICAL}
    return {"blocked": False}


async def assert_not_blocked(investor_id: str) -> None:
    """Raise 403 if the investor is compliance-blocked. Used as a funding /
    withdrawal gate (called from create_intent)."""
    decision = await is_blocked(investor_id)
    if decision.get("blocked"):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "compliance_block",
                "message": "Операцію заблоковано комплаєнс-перевіркою. "
                           "Зверніться до підтримки. / Operation blocked by "
                           "compliance screening. Contact support.",
                "reason": decision.get("reason"),
                "risk_band": decision.get("risk_band"),
            },
        )


# ──────────────────────────────────────────────────────────────────────────
# Hooks called from existing flows (lazy-imported there to avoid cycles)
# ──────────────────────────────────────────────────────────────────────────
async def screen_on_kyc_submit(investor_id: str) -> Dict[str, Any]:
    prof = await db.lumen_investor_profiles.find_one({"user_id": investor_id}) or {}
    name = prof.get("full_name") or ""
    if not name:
        u = await db.users.find_one({"user_id": investor_id}) or {}
        name = u.get("name") or u.get("email") or investor_id
    return await run_screening(
        subject_type="investor", subject_id=investor_id, name=name,
        dob=prof.get("date_of_birth"),
        country=prof.get("residency_country") or prof.get("country"),
        is_pep=bool(prof.get("is_pep")),
        triggered_by="kyc_submit", actor=investor_id)


async def screen_on_profile_change(investor_id: str, *, name: Optional[str],
                                   dob: Optional[str], country: Optional[str]) -> None:
    if not name:
        return
    await run_screening(
        subject_type="investor", subject_id=investor_id, name=name,
        dob=dob, country=country, triggered_by="profile_change", actor=investor_id)


async def screen_on_register(user_id: str, name: str, country: Optional[str] = None) -> None:
    await run_screening(
        subject_type="investor", subject_id=user_id, name=name or "",
        country=country, triggered_by="register", actor=user_id)


async def screen_on_funding(investor_id: str, amount_uah: Optional[float] = None) -> Dict[str, Any]:
    """ТЗ B1 — screening must run AT funding. Pulls the investor's identity
    from their profile and runs a fresh screen (with the transaction size in
    the risk model) right before the funding gate is evaluated."""
    prof = await db.lumen_investor_profiles.find_one({"user_id": investor_id}) or {}
    name = prof.get("full_name")
    if not name:
        u = await db.users.find_one({"user_id": investor_id}) or {}
        name = u.get("name") or u.get("email") or investor_id
    return await run_screening(
        subject_type="investor", subject_id=investor_id, name=name,
        dob=prof.get("date_of_birth"),
        country=prof.get("residency_country") or prof.get("country"),
        is_pep=bool(prof.get("is_pep")), amount_uah=amount_uah,
        triggered_by="funding_intent", actor=investor_id)


# ──────────────────────────────────────────────────────────────────────────
# Admin endpoints
# ──────────────────────────────────────────────────────────────────────────
def _case_out(c: dict) -> dict:
    c = dict(c)
    c.pop("_id", None)
    return c


@router.get("/admin/compliance/dashboard")
async def compliance_dashboard(_=Depends(require_admin)):
    counts_by_status = {}
    for s in (CASE_OPEN, CASE_IN_REVIEW, CASE_ESCALATED, CASE_CLEARED, CASE_BLOCKED):
        counts_by_status[s] = await db[CASES].count_documents({"status": s})
    counts_by_risk = {}
    for r in (RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_CRITICAL):
        counts_by_risk[r] = await db[CASES].count_documents(
            {"risk_band": r, "status": {"$in": list(OPEN_CASE_STATES)}})
    # KYC aging: submitted profiles awaiting compliance, oldest first
    aging = []
    cutoff = _now() - timedelta(days=2)
    async for p in db.lumen_investor_profiles.find(
            {"kyc_status": {"$in": ["submitted", "under_review"]}}).sort("submitted_at", 1).limit(25):
        sub = p.get("submitted_at")
        overdue = False
        try:
            subdt = sub if isinstance(sub, datetime) else datetime.fromisoformat(str(sub).replace("Z", "+00:00"))
            overdue = subdt < cutoff
        except Exception:
            pass
        aging.append({"investor_id": p.get("user_id"),
                      "full_name": p.get("full_name"),
                      "kyc_status": p.get("kyc_status"),
                      "submitted_at": p.get("submitted_at"),
                      "overdue": overdue})
    return {
        "watchlist_total": await db[WATCHLIST].count_documents({}),
        "watchlist_by_source": await _watchlist_by_source(),
        "open_cases": sum(counts_by_status[s] for s in OPEN_CASE_STATES),
        "cases_by_status": counts_by_status,
        "open_cases_by_risk": counts_by_risk,
        "screenings_total": await db[RESULTS].count_documents({}),
        "aml_events_total": await db[AML].count_documents({}),
        "kyc_aging": aging,
        "generated_at": _iso(),
    }


async def _watchlist_by_source() -> Dict[str, int]:
    out: Dict[str, int] = {}
    pipeline = [{"$group": {"_id": "$source", "n": {"$sum": 1}}}]
    async for row in db[WATCHLIST].aggregate(pipeline):
        out[row["_id"] or "unknown"] = row["n"]
    return out


@router.get("/admin/compliance/cases")
async def list_cases(status: Optional[str] = None, risk: Optional[str] = None,
                     _=Depends(require_admin)):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    if risk:
        q["risk_band"] = risk.upper()
    items = []
    async for c in db[CASES].find(q).sort("opened_at", -1).limit(500):
        items.append(_case_out(c))
    return {"items": items, "total": len(items)}


@router.get("/admin/compliance/cases/{case_id}")
async def get_case(case_id: str, _=Depends(require_admin)):
    c = await db[CASES].find_one({"id": case_id})
    if not c:
        raise HTTPException(status_code=404, detail="Кейс не знайдено")
    result = await db[RESULTS].find_one(
        {"id": c.get("latest_result_id") or c.get("screening_result_id")}, {"_id": 0})
    audit = []
    async for a in db[AML].find({"subject_id": c["investor_id"]}).sort("at", -1).limit(100):
        a.pop("_id", None)
        audit.append(a)
    return {"case": _case_out(c), "screening_result": result, "aml_audit": audit}


class CaseDecisionIn(BaseModel):
    decision: str = Field(..., description="clear | escalate | block")
    reason: str = Field(..., min_length=2)


@router.post("/admin/compliance/cases/{case_id}/decision")
async def decide_case(case_id: str, payload: CaseDecisionIn,
                      admin=Depends(require_admin)):
    c = await db[CASES].find_one({"id": case_id})
    if not c:
        raise HTTPException(status_code=404, detail="Кейс не знайдено")
    decision = payload.decision.lower().strip()
    mapping = {"clear": CASE_CLEARED, "escalate": CASE_ESCALATED, "block": CASE_BLOCKED}
    if decision not in mapping:
        raise HTTPException(status_code=400, detail="decision must be clear|escalate|block")
    new_status = mapping[decision]
    note = {"by": admin.get("id"), "by_email": admin.get("email"),
            "decision": decision, "reason": payload.reason, "at": _iso()}
    update = {"status": new_status, "decision_reason": payload.reason,
              "decided_by": admin.get("id"), "decided_at": _now(),
              "updated_at": _now()}
    if decision == "escalate":
        # escalation raises the risk band one notch (cap CRITICAL)
        cur = RISK_ORDER.get(c.get("risk_band", RISK_MEDIUM), 1)
        update["risk_band"] = {v: k for k, v in RISK_ORDER.items()}[min(3, cur + 1)]
    await db[CASES].update_one({"id": case_id},
                               {"$set": update, "$push": {"notes": note}})
    await aml_audit(
        action=f"case.decision.{decision}",
        subject_type="investor", subject_id=c["investor_id"],
        actor=admin.get("id"), reason=payload.reason,
        detail={"case_id": case_id, "new_status": new_status})
    c = await db[CASES].find_one({"id": case_id})
    return {"ok": True, "case": _case_out(c)}


class ManualScreenIn(BaseModel):
    name: str
    dob: Optional[str] = None
    country: Optional[str] = None
    amount_uah: Optional[float] = None
    is_pep: Optional[bool] = False


@router.post("/admin/compliance/screen")
async def manual_screen(payload: ManualScreenIn, admin=Depends(require_admin)):
    res = await run_screening(
        subject_type="adhoc", subject_id=_new_id("adhoc"),
        name=payload.name, dob=payload.dob, country=payload.country,
        is_pep=bool(payload.is_pep), amount_uah=payload.amount_uah,
        triggered_by="manual", actor=admin.get("id"))
    return res


class WatchlistEntryIn(BaseModel):
    full_name: str
    source: str = Field("manual", description="ofac|eu|uk|ua_nsdc|pep|manual")
    list_type: str = Field("sanction", description="sanction|pep")
    aliases: List[str] = []
    dob: Optional[str] = None
    country: Optional[str] = None
    program: Optional[str] = None


@router.get("/admin/compliance/watchlist")
async def list_watchlist(source: Optional[str] = None, q: Optional[str] = None,
                         limit: int = 100, _=Depends(require_admin)):
    query: Dict[str, Any] = {}
    if source:
        query["source"] = source
    if q:
        query["normalized_name"] = {"$regex": re.escape(_normalize_name(q))}
    items = []
    async for e in db[WATCHLIST].find(query, {"_id": 0}).limit(min(limit, 500)):
        items.append(e)
    return {"items": items, "total": await db[WATCHLIST].count_documents(query),
            "by_source": await _watchlist_by_source()}


@router.post("/admin/compliance/watchlist")
async def add_watchlist_entry(payload: WatchlistEntryIn, admin=Depends(require_admin)):
    if payload.list_type not in ("sanction", "pep"):
        raise HTTPException(status_code=400, detail="list_type must be sanction|pep")
    entry_id = _new_id("wl")
    await db[WATCHLIST].insert_one({
        "id": entry_id,
        "full_name": payload.full_name,
        "normalized_name": _normalize_name(payload.full_name),
        "source": payload.source,
        "list_type": payload.list_type,
        "aliases": payload.aliases,
        "dob": payload.dob,
        "country": (payload.country or "").upper()[:2] or None,
        "program": payload.program,
        "added_by": admin.get("id"),
        "added_at": _now(),
    })
    await aml_audit(action="watchlist.add", subject_type="watchlist",
                    subject_id=entry_id, actor=admin.get("id"),
                    reason=f"manual add {payload.list_type}",
                    detail={"full_name": payload.full_name, "source": payload.source})
    return {"ok": True, "id": entry_id}


@router.get("/admin/compliance/aml-audit")
async def list_aml_audit(subject_id: Optional[str] = None, limit: int = 200,
                         _=Depends(require_admin)):
    q: Dict[str, Any] = {}
    if subject_id:
        q["subject_id"] = subject_id
    items = []
    async for a in db[AML].find(q).sort("at", -1).limit(min(limit, 1000)):
        a.pop("_id", None)
        items.append(a)
    return {"items": items, "total": len(items)}


# ──────────────────────────────────────────────────────────────────────────
# Investor surface (coarse — no match-detail leak)
# ──────────────────────────────────────────────────────────────────────────
@router.get("/investor/compliance/status")
async def my_compliance_status(user=Depends(get_current_user)):
    decision = await is_blocked(user["id"])
    case = await db[CASES].find_one(
        {"investor_id": user["id"], "status": {"$in": list(OPEN_CASE_STATES)}})
    last = await db[RESULTS].find_one(
        {"subject_id": user["id"]}, sort=[("created_at", -1)])
    return {
        "blocked": decision.get("blocked", False),
        "under_review": bool(case),
        "risk_band": (case or {}).get("risk_band") or (last or {}).get("risk_band") or RISK_LOW,
        "screened": bool(last),
        "screened_at": (last or {}).get("created_at_iso"),
    }


# ──────────────────────────────────────────────────────────────────────────
# Seed + indexes
# ──────────────────────────────────────────────────────────────────────────
# Consolidated static watchlist. Curated, deterministic. Real well-known
# sanctioned names + a guaranteed synthetic test entry so the contract harness
# can rely on at least one confirmed match without depending on real-list churn.
_SEED_WATCHLIST: List[Dict[str, Any]] = [
    # ── OFAC SDN (real, well-known) ──
    {"full_name": "Vladimir Vladimirovich Putin", "source": "ofac", "list_type": "sanction",
     "aliases": ["Putin Vladimir"], "country": "RU", "program": "RUSSIA-EO14024"},
    {"full_name": "Ramzan Kadyrov", "source": "ofac", "list_type": "sanction",
     "aliases": [], "country": "RU", "program": "MAGNITSKY"},
    {"full_name": "Kim Jong Un", "source": "ofac", "list_type": "sanction",
     "aliases": ["Kim Jong-un"], "country": "KP", "program": "DPRK"},
    # ── EU consolidated ──
    {"full_name": "Yevgeniy Viktorovich Prigozhin", "source": "eu", "list_type": "sanction",
     "aliases": ["Yevgeny Prigozhin"], "country": "RU", "program": "EU-UKRAINE"},
    {"full_name": "Alexander Lukashenko", "source": "eu", "list_type": "sanction",
     "aliases": ["Aliaksandr Lukashenka"], "country": "BY", "program": "EU-BELARUS"},
    # ── UK HMT (OFSI) ──
    {"full_name": "Igor Sechin", "source": "uk", "list_type": "sanction",
     "aliases": [], "country": "RU", "program": "UK-RUSSIA"},
    {"full_name": "Roman Abramovich", "source": "uk", "list_type": "sanction",
     "aliases": [], "country": "RU", "program": "UK-RUSSIA"},
    # ── Ukraine NSDC (РНБО) ──
    {"full_name": "Viktor Medvedchuk", "source": "ua_nsdc", "list_type": "sanction",
     "aliases": ["Віктор Медведчук"], "country": "UA", "program": "NSDC"},
    {"full_name": "Yevhen Murayev", "source": "ua_nsdc", "list_type": "sanction",
     "aliases": ["Євген Мураєв"], "country": "UA", "program": "NSDC"},
    # ── PEP list (sample) ──
    {"full_name": "Volodymyr Zelenskyy", "source": "pep", "list_type": "pep",
     "aliases": ["Володимир Зеленський", "Volodymyr Zelensky"], "country": "UA",
     "program": "PEP-HEAD-OF-STATE"},
    {"full_name": "Denys Shmyhal", "source": "pep", "list_type": "pep",
     "aliases": ["Денис Шмигаль"], "country": "UA", "program": "PEP-PM"},
    # ── Guaranteed synthetic test entries (deterministic for the harness) ──
    {"full_name": "Stanislav Sanctiontest Blockov", "source": "ofac", "list_type": "sanction",
     "aliases": ["Sanctiontest Stanislav"], "dob": "1970-01-01", "country": "RU",
     "program": "TEST-SDN"},
    {"full_name": "Petro Peptest Politov", "source": "pep", "list_type": "pep",
     "aliases": [], "dob": "1965-05-05", "country": "UA", "program": "TEST-PEP"},
]


async def ensure_indexes() -> None:
    try:
        await db[WATCHLIST].create_index("id", unique=True)
        await db[WATCHLIST].create_index("normalized_name")
        await db[WATCHLIST].create_index([("source", 1), ("list_type", 1)])
        await db[RESULTS].create_index("id", unique=True)
        await db[RESULTS].create_index([("subject_id", 1), ("created_at", -1)])
        await db[RESULTS].create_index("sanction_decision")
        await db[CASES].create_index("id", unique=True)
        await db[CASES].create_index([("investor_id", 1), ("status", 1)])
        await db[CASES].create_index([("status", 1), ("risk_band", 1)])
        await db[AML].create_index("id", unique=True)
        await db[AML].create_index([("subject_id", 1), ("at", -1)])
        await db[AML].create_index([("at", -1)])
        logger.info("compliance_screening indexes ensured")
    except Exception as e:
        logger.warning("compliance ensure_indexes warning: %s", e)


async def seed_watchlist() -> int:
    """Idempotent — upsert by normalized_name+source so re-runs are cheap."""
    n = 0
    for raw in _SEED_WATCHLIST:
        norm = _normalize_name(raw["full_name"])
        existing = await db[WATCHLIST].find_one(
            {"normalized_name": norm, "source": raw["source"]})
        if existing:
            continue
        await db[WATCHLIST].insert_one({
            "id": _new_id("wl"),
            "full_name": raw["full_name"],
            "normalized_name": norm,
            "source": raw["source"],
            "list_type": raw["list_type"],
            "aliases": raw.get("aliases", []),
            "dob": raw.get("dob"),
            "country": (raw.get("country") or "").upper()[:2] or None,
            "program": raw.get("program"),
            "added_by": "seed",
            "added_at": _now(),
        })
        n += 1
    if n:
        logger.info("watchlist seeded: %d new entries", n)
    return n


async def boot() -> None:
    await ensure_indexes()
    await seed_watchlist()
    logger.info("Compliance Screening ready (watchlist=%d, sources=OFAC/EU/UK/UA/PEP)",
                await db[WATCHLIST].count_documents({}))


# ──────────────────────────────────────────────────────────────────────────
# Watchlist auto-refresh (production) — pulls the official OFAC consolidated
# list daily and upserts it, so screening runs against fresh data instead of a
# static seed. Resilient: any fetch/parse failure keeps the existing list and
# is recorded as a 'fallback' refresh. Seeded + manual entries are NEVER purged
# by a refresh; only previously auto-fetched OFAC rows are replaced.
# ──────────────────────────────────────────────────────────────────────────
REFRESHES = "lumen_watchlist_refreshes"
# Public, machine-readable OFAC SDN list (a couple of mirrors for resilience).
OFAC_SDN_URLS = [
    "https://www.treasury.gov/ofac/downloads/sdn.csv",
    "https://ofac.treasury.gov/media/2676/download?inline",  # sdn.csv mirror
]
# Cap auto-ingested rows so Python-side fuzzy screening stays responsive.
# Production with a dedicated screening provider can raise/remove this.
WATCHLIST_AUTO_CAP = int(os.environ.get("LUMEN_WATCHLIST_MAX", "2000"))


async def _fetch_ofac_sdn() -> Optional[List[Dict[str, Any]]]:
    """Fetch + parse the OFAC SDN CSV → [{full_name, list_type, program, ...}].
    Returns None on any failure (caller falls back to existing list)."""
    import csv
    import io
    try:
        import httpx
        text = None
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as c:
            for url in OFAC_SDN_URLS:
                try:
                    r = await c.get(url)
                    if r.status_code == 200 and r.text and "," in r.text:
                        text = r.text
                        break
                except Exception:
                    continue
        if not text:
            return None
        out: List[Dict[str, Any]] = []
        # SDN CSV columns (positional): ent_num, SDN_Name, SDN_Type, Program, ...
        reader = csv.reader(io.StringIO(text))
        for row in reader:
            if len(row) < 3:
                continue
            name = (row[1] or "").strip().strip('"')
            sdn_type = (row[2] or "").strip().strip('"').lower()
            program = (row[3].strip().strip('"') if len(row) > 3 else "") or "OFAC-SDN"
            if not name or name == "-0-":
                continue
            # individuals + entities are screenable; skip vessels/aircraft
            if sdn_type and sdn_type not in ("individual", "entity", "-0-", ""):
                continue
            out.append({"full_name": name, "list_type": "sanction",
                        "source": "ofac", "program": program[:80]})
            if len(out) >= WATCHLIST_AUTO_CAP:
                break
        return out or None
    except Exception as e:
        logger.info("OFAC fetch unavailable (%s)", e)
        return None


async def refresh_watchlist(*, actor: str = "scheduler") -> Dict[str, Any]:
    """Refresh the auto-fetched portion of the watchlist from OFAC.
    Idempotent + resilient. Records a row in lumen_watchlist_refreshes."""
    refresh_id = _new_id("wlref")
    fetched = await _fetch_ofac_sdn()
    status = "ok"
    inserted = 0
    if not fetched:
        status = "fallback"
        existing_auto = await db[WATCHLIST].count_documents({"auto_fetched": True})
        doc = {"id": refresh_id, "source": "ofac", "status": status,
               "fetched": 0, "inserted": 0, "kept": existing_auto,
               "actor": actor, "at": _now(), "at_iso": _iso(),
               "note": "official source unreachable — existing list retained"}
        await db[REFRESHES].insert_one(dict(doc))
        await aml_audit(action="watchlist.refresh.fallback", subject_type="watchlist",
                        subject_id=refresh_id, actor=actor,
                        reason="OFAC source unreachable; retained existing list")
        doc.pop("_id", None)
        return doc
    # Replace previously auto-fetched OFAC rows (keep seed/manual entries).
    await db[WATCHLIST].delete_many({"auto_fetched": True, "source": "ofac"})
    now = _now()
    batch = []
    seen = set()
    for e in fetched:
        norm = _normalize_name(e["full_name"])
        if not norm or norm in seen:
            continue
        seen.add(norm)
        batch.append({
            "id": _new_id("wl"), "full_name": e["full_name"],
            "normalized_name": norm, "source": "ofac", "list_type": "sanction",
            "aliases": [], "dob": None, "country": None,
            "program": e.get("program"), "auto_fetched": True,
            "refresh_id": refresh_id, "added_by": "ofac-refresh", "added_at": now})
    if batch:
        await db[WATCHLIST].insert_many(batch)
        inserted = len(batch)
    doc = {"id": refresh_id, "source": "ofac", "status": status,
           "fetched": len(fetched), "inserted": inserted,
           "actor": actor, "at": now, "at_iso": _iso(),
           "watchlist_total": await db[WATCHLIST].count_documents({})}
    await db[REFRESHES].insert_one(dict(doc))
    await aml_audit(action="watchlist.refresh.ok", subject_type="watchlist",
                    subject_id=refresh_id, actor=actor,
                    reason=f"OFAC refresh: {inserted} entries",
                    detail={"fetched": len(fetched), "inserted": inserted})
    logger.info("watchlist refresh: source=ofac inserted=%d total=%d",
                inserted, doc["watchlist_total"])
    doc.pop("_id", None)
    return doc


async def last_refresh() -> Optional[dict]:
    r = await db[REFRESHES].find_one(sort=[("at", -1)])
    if r:
        r.pop("_id", None)
    return r


async def _needs_refresh() -> bool:
    """True if the live (auto-fetched) list is empty or the last refresh is
    older than 24h — used for boot-time hardening so screening never runs on a
    stale/seed-only watchlist after a fresh deploy."""
    try:
        auto = await db[WATCHLIST].count_documents({"auto_fetched": True})
        if auto == 0:
            return True
        last = await last_refresh()
        at = (last or {}).get("at")
        if not at:
            return True
        if isinstance(at, str):
            try:
                at = datetime.fromisoformat(at)
            except Exception:
                return True
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        return (_now() - at) > timedelta(hours=24)
    except Exception:
        return True


async def watchlist_scheduler_loop() -> None:
    """Daily watchlist refresh. Does a boot-time refresh first when the live list
    is empty or stale (>24h), then refreshes every 24h. Resilient — never crashes
    boot. Runs as a background task so startup is not blocked by the download."""
    import asyncio
    # Boot-time production hardening: load live OFAC immediately if needed.
    try:
        if await _needs_refresh():
            res = await refresh_watchlist(actor="boot")
            logger.info("boot watchlist refresh: status=%s inserted=%s",
                        res.get("status"), res.get("inserted"))
    except Exception as e:  # pragma: no cover
        logger.warning("boot watchlist refresh failed: %s", e)
    while True:
        try:
            await asyncio.sleep(24 * 60 * 60)
            await refresh_watchlist(actor="scheduler")
        except asyncio.CancelledError:
            break
        except Exception as e:  # pragma: no cover
            logger.warning("watchlist scheduler tick failed: %s", e)


@router.post("/admin/compliance/watchlist/refresh")
async def admin_refresh_watchlist(admin=Depends(require_admin)):
    return await refresh_watchlist(actor=admin.get("id", "admin"))


@router.get("/admin/compliance/watchlist/refresh-status")
async def admin_refresh_status(_=Depends(require_admin)):
    items = []
    async for r in db[REFRESHES].find({}, {"_id": 0}).sort("at", -1).limit(30):
        items.append(r)
    return {"last_refresh": await last_refresh(),
            "auto_fetched_count": await db[WATCHLIST].count_documents({"auto_fetched": True}),
            "seed_manual_count": await db[WATCHLIST].count_documents({"auto_fetched": {"$ne": True}}),
            "history": items}
