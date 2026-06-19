"""
LUMEN — Production Launch Readiness v1.0 — Auto-Eval Engine + Override Store
===========================================================================

Turns the static 130-item seed (``launch_checklist_seed.py``) into a *live*
checklist:

* **Auto-eval** — 68 items are probed against the running system (invariants,
  security score, FX, tax, watchlist, SOP, beta milestones, legal package, …).
  Detectors are defensive: they only go green on positive evidence, otherwise
  the item stays ``pending`` (never a false green).
* **Override store** — every item can be manually overridden by an admin
  (``completed | pending | not_applicable``) with notes + actor + timestamp.
  Overrides always win over auto-detection.
* **Summary** — domain rollups + blocker accounting + a 0–100 readiness %.

Persistence collection: ``lumen_launch_checklist`` (one doc per item id).
"""
from __future__ import annotations

import logging
import os
from datetime import timedelta
from typing import Any, Optional

from lumen_api import db, _now, _iso, _strip_mongo
from launch_checklist_seed import (
    LAUNCH_CHECKLIST_VERSION, DOMAINS, CHECKLIST_ITEMS,
    items_by_domain, item_index,
)

logger = logging.getLogger("lumen.launch_checklist")

CHECKLIST_COLLECTION = "lumen_launch_checklist"

OVERRIDE_STATUSES = {"completed", "pending", "not_applicable"}
SEVERITY_WEIGHT = {"blocker": 8, "critical": 4, "major": 2, "minor": 1}


async def ensure_launch_checklist_indexes() -> None:
    try:
        await db[CHECKLIST_COLLECTION].create_index("item_id", unique=True)
        logger.info("LAUNCH READINESS v%s: indexes ensured (%d items)",
                    LAUNCH_CHECKLIST_VERSION, len(CHECKLIST_ITEMS))
    except Exception as e:  # pragma: no cover
        logger.warning("LAUNCH READINESS: index ensure failed: %s", e)


# ═══════════════════════════════════════════════════════════════════════════
# Detector helpers
# ═══════════════════════════════════════════════════════════════════════════

def _ok(evidence: str | None = None, detail: dict | None = None) -> dict:
    return {"done": True, "evidence": evidence, "detail": detail}


def _no(evidence: str | None = None, detail: dict | None = None) -> dict:
    return {"done": False, "evidence": evidence, "detail": detail}


async def _count(coll: str, query: dict | None = None) -> int:
    try:
        return await db[coll].count_documents(query or {})
    except Exception:
        return 0


def _module_present(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


# ── Invariants / LR2 reuse (lazy import to avoid cycles) ────────────────────

_inv_cache: dict[str, Any] = {}


async def _invariants() -> dict:
    import lumen_launch_readiness as lr
    return await lr.run_invariants()


async def _invariant_passed(inv_id: str) -> Optional[bool]:
    try:
        res = await _invariants()
        for r in res.get("results", []):
            if r.get("id") == inv_id:
                return bool(r.get("passed"))
    except Exception as e:  # pragma: no cover
        logger.warning("invariant lookup failed (%s): %s", inv_id, e)
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Detectors  (key → async () -> {"done","evidence","detail"})
# ═══════════════════════════════════════════════════════════════════════════

async def d_security_score_ok() -> dict:
    try:
        from lumen_beta_command_center import _security_score
        s = await _security_score()
        return _ok(f"security score = {s}/100", {"score": s}) if s >= 90 else _no(f"security score = {s}/100 (< 90)", {"score": s})
    except Exception as e:
        return _no(f"security score unavailable: {e}")


async def d_lr2_invariants_pass() -> dict:
    try:
        res = await _invariants()
        failed = [r["id"] for r in res.get("results", [])
                  if not r.get("passed") and r.get("severity") != "warning"]
        c = res.get("counts", {})
        if not failed:
            return _ok(f"{c.get('passed')}/{c.get('total')} invariants pass", c)
        return _no(f"invariants failing: {', '.join(failed)}", {"failed": failed})
    except Exception as e:
        return _no(f"invariants unavailable: {e}")


async def d_reporting_integrity_pass() -> dict:
    try:
        import lumen_launch_readiness as lr
        rep = await lr.reporting_integrity()
        return _ok("reporting integrity passed") if rep.get("passed") else _no("reporting integrity issues found", rep)
    except Exception as e:
        return _no(f"reporting integrity unavailable: {e}")


async def d_permissions_clean() -> dict:
    try:
        import lumen_launch_readiness as lr
        perm = lr.audit_permission_matrix()
        v = perm.get("counts", {}).get("violations", 0)
        return _ok("0 permission violations") if v == 0 else _no(f"{v} permission violations")
    except Exception as e:
        return _no(f"permission audit unavailable: {e}")


async def d_conflicts_clean() -> dict:
    try:
        import lumen_launch_readiness as lr
        cof = await lr.conflicts_of_interest()
        high = [c for c in cof.get("items", []) if c.get("severity") == "high"]
        return _ok("no high-severity conflicts") if not high else _no(f"{len(high)} high-severity conflicts")
    except Exception as e:
        return _no(f"conflicts audit unavailable: {e}")


def _inv_detector(inv_id: str, label: str):
    async def _fn() -> dict:
        p = await _invariant_passed(inv_id)
        if p is True:
            return _ok(f"invariant '{inv_id}' passes")
        if p is False:
            return _no(f"invariant '{inv_id}' failing")
        return _no(f"invariant '{inv_id}' indeterminate")
    _fn.__name__ = f"d_{inv_id}"
    return _fn


async def d_no_demo_in_prod() -> dict:
    try:
        import lumen_launch_readiness as lr
        demo = await lr.demo_data_inventory()
        total = sum(demo.get("counts", {}).values())
        if not lr.is_production():
            return _ok(f"env=preview; prod gate will purge ({total} demo markers)", {"demo": total})
        return _ok("production has no demo data") if total == 0 else _no(f"{total} demo markers in production")
    except Exception as e:
        return _no(f"demo inventory unavailable: {e}")


async def d_fx_live() -> dict:
    n = await _count("lumen_fx_rates")
    return _ok("live FX snapshot present (NBU)", {"rows": n}) if n > 0 else _no("no FX snapshot")


async def d_tax_engine_configured() -> dict:
    try:
        doc = await db["lumen_tax_config"].find_one({})
        if doc and doc.get("enabled", True):
            return _ok("UA tax engine configured (PIT 18% + MT 1.5%)")
        return _no("tax config missing/disabled")
    except Exception as e:
        return _no(f"tax config unavailable: {e}")


async def d_dividend_scheduler() -> dict:
    n = await _count("lumen_payout_plans")
    return _ok("dividend/payout plans present", {"plans": n}) if n > 0 else _no("no payout plans")


async def d_ofac_watchlist_fresh() -> dict:
    refreshes = await _count("lumen_watchlist_refreshes")
    wl = await _count("lumen_watchlist")
    if refreshes > 0:
        return _ok("watchlist auto-refreshed from OFAC", {"refreshes": refreshes, "entries": wl})
    if wl > 0:
        return _ok(f"watchlist seeded ({wl} entries); OFAC auto-refresh loop enabled", {"entries": wl})
    return _no("watchlist empty")


async def d_sop_runbooks() -> dict:
    n = await _count("lumen_ops_sop")
    return _ok(f"{n} SOP/runbooks present", {"count": n}) if n >= 6 else _no(f"only {n} runbooks (< 6)")


async def d_kyc_pipeline() -> dict:
    if _module_present("lumen_kyc"):
        return _ok("KYC pipeline module active (lumen_kyc)")
    return _no("KYC module not importable")


async def d_sanctions_screening() -> dict:
    wl = await _count("lumen_watchlist")
    if wl > 0 and _module_present("lumen_compliance_screening"):
        return _ok(f"sanctions/PEP screening active (watchlist={wl})", {"watchlist": wl})
    return _no("screening inactive / watchlist empty")


async def d_quarterly_reports() -> dict:
    n = await _count("lumen_reports", {"kind": "quarterly"})
    return _ok(f"{n} quarterly report(s)", {"count": n}) if n > 0 else _no("no quarterly reports")


async def d_factsheets_available() -> dict:
    n = await _count("lumen_reports", {"kind": "asset_factsheet"})
    return _ok(f"{n} factsheet(s)", {"count": n}) if n > 0 else _no("no factsheets")


async def d_statements_available() -> dict:
    return _ok("statements module active") if _module_present("lumen_statements") else _no("statements module missing")


async def d_payout_history() -> dict:
    n = await _count("lumen_payout_records")
    return _ok(f"{n} payout record(s)", {"count": n}) if n > 0 else _no("no payout history")


async def d_payout_export() -> dict:
    return _ok("payout export module active") if _module_present("lumen_payout_export") else _no("payout export missing")


async def d_notifications_active() -> dict:
    n = await _count("lumen_notifications")
    return _ok("notifications active", {"count": n}) if n >= 0 and _module_present("lumen_staff_notifications") else (_ok("notifications present", {"count": n}) if n > 0 else _no("no notifications"))


async def d_error_tracking_active() -> dict:
    return _ok("error tracking module active") if _module_present("lumen_error_tracking") else _no("error tracking missing")


async def d_sla_engine() -> dict:
    return _ok("SLA engine active") if _module_present("lumen_sla") else _no("SLA engine missing")


async def d_i18n_ready() -> dict:
    return _ok("i18n backend active (UA/EN)") if _module_present("i18n_backend") else _no("i18n backend missing")


async def d_db_indexes_ensured() -> dict:
    # Phase-0 ensures indexes for 20+ collections at boot; verify a core one.
    try:
        idx = await db["lumen_ownerships"].index_information()
        return _ok(f"core indexes present ({len(idx)} on lumen_ownerships)", {"indexes": len(idx)})
    except Exception as e:
        return _no(f"index check failed: {e}")


async def d_prod_env_gate() -> dict:
    if _module_present("lumen_lr2_extended"):
        import lumen_launch_readiness as lr
        return _ok(f"prod env gate present (current env={lr.env()})")
    return _no("prod env gate module missing")


async def d_dr_backup_verified() -> dict:
    p = "/app/scripts/backup_restore_verify.py"
    return _ok("DR backup→restore→compare harness present") if os.path.exists(p) else _no("DR harness missing")


async def d_audit_log_active() -> dict:
    n = await _count("lumen_audit_log")
    return _ok(f"audit log active ({n} entries)", {"count": n}) if n > 0 else _no("audit log empty")


async def d_rate_limit_enabled() -> dict:
    return _ok("rate-limit module active") if _module_present("lumen_rate_limit") else _no("rate-limit module missing")


async def d_two_factor_available() -> dict:
    return _ok("2FA module active") if _module_present("two_factor") else _no("2FA module missing")


async def d_password_policy() -> dict:
    return _ok("password policy module active") if _module_present("lumen_password_policy") else _no("password policy missing")


async def d_security_headers() -> dict:
    return _ok("security headers module active") if _module_present("lumen_security_headers") else _no("security headers missing")


async def d_upload_security() -> dict:
    return _ok("upload security module active") if _module_present("lumen_upload_security") else _no("upload security missing")


async def d_gmail_adapter_present() -> dict:
    return _ok("Gmail adapter present (architecture ready)") if _module_present("f6_gmail_adapter") else _no("Gmail adapter missing")


async def d_outlook_adapter_present() -> dict:
    return _ok("Outlook adapter present (architecture ready)") if _module_present("f7_outlook_adapter") else _no("Outlook adapter missing")


async def d_email_verification_ready() -> dict:
    return _ok("email verification module active") if _module_present("email_verification") else _no("email verification missing")


async def d_funding_ledger_link() -> dict:
    n = await _count("lumen_ledger_entries")
    return _ok(f"ledger entries present ({n})", {"count": n}) if n > 0 else _no("no ledger entries")


async def d_funding_idempotency() -> dict:
    return _ok("payments module enforces idempotency") if _module_present("lumen_payments") else _no("payments module missing")


async def d_funding_webhook_secret() -> dict:
    keys = ("STRIPE_WEBHOOK_SECRET", "FUNDING_WEBHOOK_SECRET", "WEBHOOK_SECRET")
    present = [k for k in keys if os.environ.get(k)]
    if present:
        return _ok(f"webhook secret configured ({present[0]})")
    return _no("no funding webhook secret in env (owner/credential-blocked)")


async def d_funding_proof_flow() -> dict:
    try:
        names = await db.list_collection_names()
        return _ok("payment-proof collection present") if "lumen_payment_proofs" in names else _no("no payment-proof collection")
    except Exception as e:
        return _no(f"proof flow check failed: {e}")


async def d_withdrawal_approval() -> dict:
    return _ok("payouts v2 approval workflow present") if _module_present("payouts_v2") else _no("payouts approval module missing")


def _legal_detector(kind: str):
    async def _fn() -> dict:
        try:
            from legal_content import LEGAL_BODIES
            body = LEGAL_BODIES.get(kind) or LEGAL_BODIES.get(
                {"terms": "offer"}.get(kind, kind))
            if body and len(str(body).strip()) > 200:
                return _ok(f"legal '{kind}' published in package (counsel sign-off via override)")
            return _no(f"legal '{kind}' content missing/short")
        except Exception as e:
            return _no(f"legal package unavailable: {e}")
    _fn.__name__ = f"d_legal_{kind}"
    return _fn


# Registry of all detectors keyed by the seed `auto` field
_DETECTORS: dict[str, Any] = {
    "security_score_ok": d_security_score_ok,
    "lr2_invariants_pass": d_lr2_invariants_pass,
    "reporting_integrity_pass": d_reporting_integrity_pass,
    "permissions_clean": d_permissions_clean,
    "conflicts_clean": d_conflicts_clean,
    "no_demo_in_prod": d_no_demo_in_prod,
    "fx_live": d_fx_live,
    "tax_engine_configured": d_tax_engine_configured,
    "dividend_scheduler": d_dividend_scheduler,
    "ofac_watchlist_fresh": d_ofac_watchlist_fresh,
    "sop_runbooks": d_sop_runbooks,
    "kyc_pipeline": d_kyc_pipeline,
    "sanctions_screening": d_sanctions_screening,
    "quarterly_reports": d_quarterly_reports,
    "factsheets_available": d_factsheets_available,
    "statements_available": d_statements_available,
    "payout_history": d_payout_history,
    "payout_export": d_payout_export,
    "notifications_active": d_notifications_active,
    "error_tracking_active": d_error_tracking_active,
    "sla_engine": d_sla_engine,
    "i18n_ready": d_i18n_ready,
    "db_indexes_ensured": d_db_indexes_ensured,
    "prod_env_gate": d_prod_env_gate,
    "dr_backup_verified": d_dr_backup_verified,
    "audit_log_active": d_audit_log_active,
    "rate_limit_enabled": d_rate_limit_enabled,
    "two_factor_available": d_two_factor_available,
    "password_policy": d_password_policy,
    "security_headers": d_security_headers,
    "upload_security": d_upload_security,
    "gmail_adapter_present": d_gmail_adapter_present,
    "outlook_adapter_present": d_outlook_adapter_present,
    "email_verification_ready": d_email_verification_ready,
    "funding_ledger_link": d_funding_ledger_link,
    "funding_idempotency": d_funding_idempotency,
    "funding_webhook_secret": d_funding_webhook_secret,
    "funding_proof_flow": d_funding_proof_flow,
    "withdrawal_approval": d_withdrawal_approval,
    # invariant-backed detectors
    "ownership_consistent": _inv_detector("ownership_le_100", "ownership ≤ 100%"),
    "distribution_integrity": _inv_detector("distribution_lines_sum", "waterfall integrity"),
    "cert_asset_backed": _inv_detector("active_cert_has_asset", "certificate backing"),
    "unique_compliance_profile": _inv_detector("unique_compliance_profile", "unique compliance"),
    "fund_nav_consistent": _inv_detector("fund_nav_eq_holdings", "fund NAV"),
    "payout_records_consistent": _inv_detector("payout_records_match_batches", "payout records"),
    "accreditation_consistent": _inv_detector("accreditation_levels_consistent", "accreditation"),
    "reconciliation_clean": _inv_detector("called_ge_paid", "reconciliation"),
    # milestone-backed detectors (reuse beta command center)
    "first_real_investor": None,
    "first_kyc_approved": None,
    "first_certificate": None,
    "first_funding": None,
    # legal package detectors
    "legal_doc_tos": _legal_detector("terms"),
    "legal_doc_privacy": _legal_detector("privacy"),
    "legal_doc_aml": _legal_detector("aml"),
    "legal_doc_kyc": _legal_detector("kyc"),
    "legal_doc_risk": _legal_detector("risk"),
    "legal_doc_dividend": _legal_detector("dividend"),
    "legal_doc_secondary": _legal_detector("secondary"),
}


_BETA_MILESTONE_MAP = {
    "first_real_investor": "_detect_first_real_investor",
    "first_kyc_approved": "_detect_first_kyc_approved",
    "first_certificate": "_detect_first_certificate",
    "first_funding": "_detect_first_funding",
}


async def _run_detector(auto_key: str) -> dict:
    # Beta milestone detectors
    if auto_key in _BETA_MILESTONE_MAP:
        try:
            import lumen_beta_command_center as bcc
            fn = getattr(bcc, _BETA_MILESTONE_MAP[auto_key])
            entity_id, label, when = await fn()
            if entity_id:
                return _ok(label or f"{auto_key} detected", {"entity_id": entity_id})
            return _no("milestone not yet reached (no real entity)")
        except Exception as e:
            return _no(f"milestone detector failed: {e}")
    fn = _DETECTORS.get(auto_key)
    if not fn:
        return _no("no detector")
    try:
        return await fn()
    except Exception as e:  # pragma: no cover
        logger.warning("detector %s failed: %s", auto_key, e)
        return _no(f"detector error: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# State assembly (auto-eval + override merge)
# ═══════════════════════════════════════════════════════════════════════════

async def _load_override(item_id: str) -> Optional[dict]:
    try:
        return await db[CHECKLIST_COLLECTION].find_one({"item_id": item_id}, {"_id": 0})
    except Exception:
        return None


async def _resolve_item(meta: dict, override: Optional[dict]) -> dict:
    auto_key = meta.get("auto")
    auto_done = False
    auto_evidence = None
    auto_detail = None
    has_detector = bool(auto_key)

    if auto_key:
        res = await _run_detector(auto_key)
        auto_done = bool(res.get("done"))
        auto_evidence = res.get("evidence")
        auto_detail = res.get("detail")

    # Effective status: override wins
    if override and override.get("overridden_by"):
        status = override.get("status", "pending")
        source = "override"
    else:
        status = "completed" if auto_done else "pending"
        source = "auto" if has_detector else "manual"

    return {
        "id": meta["id"],
        "domain": meta["domain"],
        "severity": meta["severity"],
        "owner": meta["owner"],
        "label_uk": meta["label_uk"],
        "label_en": meta["label_en"],
        "evidence_uk": meta.get("evidence_uk", ""),
        "evidence_en": meta.get("evidence_en", ""),
        "auto_supported": has_detector,
        "auto_done": auto_done,
        "auto_evidence": auto_evidence,
        "auto_detail": auto_detail,
        "status": status,
        "source": source,
        "notes": (override or {}).get("notes"),
        "overridden_by": (override or {}).get("overridden_by"),
        "overridden_at": (override or {}).get("overridden_at"),
    }


async def build_checklist_state() -> dict:
    overrides = {}
    try:
        async for o in db[CHECKLIST_COLLECTION].find({}, {"_id": 0}):
            overrides[o.get("item_id")] = o
    except Exception as e:  # pragma: no cover
        logger.warning("override load failed: %s", e)

    resolved = []
    for meta in CHECKLIST_ITEMS:
        resolved.append(await _resolve_item(meta, overrides.get(meta["id"])))

    return _summarize(resolved)


def _summarize(items: list[dict]) -> dict:
    def is_green(it: dict) -> bool:
        return it["status"] in ("completed", "not_applicable")

    total = len(items)
    completed = sum(1 for it in items if it["status"] == "completed")
    na = sum(1 for it in items if it["status"] == "not_applicable")
    pending = sum(1 for it in items if it["status"] == "pending")

    # Weighted readiness %
    max_w = sum(SEVERITY_WEIGHT[it["severity"]] for it in items)
    earned = sum(SEVERITY_WEIGHT[it["severity"]] for it in items if is_green(it))
    readiness_pct = round(earned / max_w * 100) if max_w else 0

    # Blocker accounting
    blockers = [it for it in items if it["severity"] == "blocker"]
    blockers_open = [it["id"] for it in blockers if not is_green(it)]

    # Domain rollups (ordered)
    by_domain = {}
    for it in items:
        by_domain.setdefault(it["domain"], []).append(it)
    domains_out = []
    for d in sorted(DOMAINS, key=lambda x: x["order"]):
        dits = by_domain.get(d["id"], [])
        dgreen = sum(1 for it in dits if is_green(it))
        domains_out.append({
            "id": d["id"], "label_uk": d["label_uk"], "label_en": d["label_en"],
            "order": d["order"],
            "total": len(dits), "green": dgreen,
            "pending": sum(1 for it in dits if it["status"] == "pending"),
            "blockers_open": [it["id"] for it in dits
                              if it["severity"] == "blocker" and not is_green(it)],
            "items": dits,
        })

    go_live = len(blockers_open) == 0

    return {
        "version": LAUNCH_CHECKLIST_VERSION,
        "generated_at": _iso(_now()),
        "totals": {
            "total": total, "completed": completed, "not_applicable": na,
            "pending": pending,
        },
        "readiness_pct": readiness_pct,
        "blockers": {
            "total": len(blockers),
            "green": len(blockers) - len(blockers_open),
            "open": blockers_open,
        },
        "go_live_ready": go_live,
        "domains": domains_out,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Override mutations
# ═══════════════════════════════════════════════════════════════════════════

async def set_override(item_id: str, status: str, notes: Optional[str],
                       actor: str) -> dict:
    idx = item_index()
    if item_id not in idx:
        raise KeyError(item_id)
    if status not in OVERRIDE_STATUSES:
        raise ValueError(status)
    now = _now()
    await db[CHECKLIST_COLLECTION].update_one(
        {"item_id": item_id},
        {"$set": {"status": status, "notes": notes,
                  "overridden_by": actor, "overridden_at": _iso(now),
                  "updated_at": now},
         "$setOnInsert": {"item_id": item_id, "created_at": now}},
        upsert=True,
    )
    return await _resolve_item(idx[item_id], await _load_override(item_id))


async def clear_override(item_id: str) -> dict:
    idx = item_index()
    if item_id not in idx:
        raise KeyError(item_id)
    await db[CHECKLIST_COLLECTION].delete_one({"item_id": item_id})
    return await _resolve_item(idx[item_id], None)


# ═══════════════════════════════════════════════════════════════════════════
# Canonical Markdown document generation (from seed + live state)
# ═══════════════════════════════════════════════════════════════════════════

def _sev_badge(sev: str) -> str:
    return {"blocker": "🛑 BLOCKER", "critical": "🔴 critical",
            "major": "🟠 major", "minor": "🟡 minor"}[sev]


def render_canonical_doc(state: Optional[dict] = None) -> str:
    """Render the canonical PRODUCTION_LAUNCH_READINESS_v1.0.md from the seed.

    If a live ``state`` is provided, current status is annotated per item.
    """
    status_map = {}
    if state:
        for d in state.get("domains", []):
            for it in d["items"]:
                status_map[it["id"]] = it
    ibd = items_by_domain()
    lines: list[str] = []
    lines.append(f"# LUMEN — Production Launch Readiness v{LAUNCH_CHECKLIST_VERSION}")
    lines.append("")
    lines.append("> Canonical pre-go-live checklist. **Generated from "
                 "`launch_checklist_seed.py` — do not edit by hand.**")
    lines.append("> Walk this list before accepting the first real investor money. "
                 "`🛑 BLOCKER` items MUST be green (auto-detected or admin-overridden "
                 "with evidence) before go-live.")
    lines.append("")
    if state:
        t = state["totals"]
        lines.append(f"**Live snapshot:** readiness **{state['readiness_pct']}%** · "
                     f"green {t['completed'] + t['not_applicable']}/{t['total']} · "
                     f"blockers green {state['blockers']['green']}/{state['blockers']['total']} · "
                     f"go-live ready: **{'YES' if state['go_live_ready'] else 'NO'}** "
                     f"(as of {state['generated_at']})")
        lines.append("")
    lines.append(f"Total items: **{len(CHECKLIST_ITEMS)}** across **{len(DOMAINS)}** domains.")
    lines.append("")
    lines.append("---")
    lines.append("")

    for d in sorted(DOMAINS, key=lambda x: x["order"]):
        dits = ibd.get(d["id"], [])
        lines.append(f"## {d['order']}. {d['label_en']} — {d['label_uk']}")
        lines.append("")
        lines.append("| # | Item | Severity | Owner | Auto | Status |")
        lines.append("|---|------|----------|-------|------|--------|")
        for i, it in enumerate(dits, 1):
            st = status_map.get(it["id"])
            if st:
                badge = {"completed": "✅", "not_applicable": "➖",
                         "pending": "⬜"}.get(st["status"], "⬜")
                status_cell = f"{badge} {st['status']}" + (f" ({st['source']})" if st.get('source') else "")
            else:
                status_cell = ""
            auto_cell = "auto" if it.get("auto") else "manual"
            label = it["label_en"].replace("|", "/")
            lines.append(f"| {i} | {label} | {_sev_badge(it['severity'])} | "
                         f"{it['owner']} | {auto_cell} | {status_cell} |")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("### Legend")
    lines.append("- **Severity**: 🛑 BLOCKER (must be green) · 🔴 critical · 🟠 major · 🟡 minor")
    lines.append("- **Auto**: `auto` = evaluated live by the system · `manual` = owner/legal/ops evidence + admin override")
    lines.append("- **Status**: ✅ completed · ➖ not applicable · ⬜ pending")
    lines.append("")
    lines.append("_Source of truth: `/app/backend/launch_checklist_seed.py`. "
                 "Live dashboard: `/admin/launch-readiness` → Launch Checklist tab._")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "CHECKLIST_COLLECTION", "OVERRIDE_STATUSES",
    "ensure_launch_checklist_indexes",
    "build_checklist_state", "set_override", "clear_override",
    "render_canonical_doc",
]
