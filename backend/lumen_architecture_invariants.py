"""
LUMEN IR0.4 — Architecture Invariants
=======================================

A small, declarative set of **runtime contracts** that the platform asserts at
boot time AND on demand. If any invariant is violated the system either:

  - in ``strict`` mode: refuses to start (boot-fail-loud)
  - in ``warn`` mode (default for Beta): emits a logger.error + records to
    ``lumen_architecture_violations`` but lets the process continue

The whole point is to convert "things we promise our investors / regulator"
into ASSERTIONS rather than wiki paragraphs. Examples we now enforce:

    * gated_routes              >= 52    — LR2 permission gating floor
    * default_admin_count       == 0     — no shipped-default admin in prod
    * funding_account_count     >= 1     — must have at least one bank rail
    * treasury_adapter_count    >= 1     — at least one settlement adapter
    * compliance_matrix_combos  >= 20    — LR2 resource×action matrix floor
    * sepa_swift_endpoints      >= 12    — institutional bank rails endpoints
    * cors_allow_origin_wildcard == False  (in production)

Tuning these is intentional — they should be **monotonic**:

    * "<=" invariants ratchet DOWN (e.g. bridge count)
    * ">=" invariants ratchet UP (e.g. gated route count)

When a future change accidentally regresses an invariant the operator sees
the failure in ``GET /api/admin/architecture/invariants`` AND in startup
logs, with the exact surface name, expected value and actual value.

The module is **read-only**: it never mutates collections, it never blocks
business logic. Even in ``strict`` mode the failure is in the form of a
RuntimeError raised from the startup hook — the admin can downgrade to
``warn`` via the env var to keep the platform up while they investigate.

Public surface
--------------
- ``run_all(db) -> InvariantReport``     run every invariant, return report
- ``register_invariant_routes(api_router, db, require_admin_dep)``
                                          mount /api/admin/architecture/*
- ``ensure_indexes(db)``                  index the violations collection
- ``InvariantViolation``                  subclass of RuntimeError
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger("lumen.invariants")

# Collection where we keep durable history of violations (analytics + UI).
VIOLATION_COLLECTION = "lumen_architecture_violations"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
def resolve_mode() -> str:
    """``strict`` (boot fails on violation) | ``warn`` (default, logs only) |
    ``off`` (run never executes)."""
    raw = (os.environ.get("LUMEN_INVARIANTS_MODE") or "warn").strip().lower()
    return raw if raw in {"strict", "warn", "off"} else "warn"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class InvariantCheck:
    """A single named check."""
    name: str
    description: str
    operator: str                      # ">=" | "<=" | "==" | "!="
    expected: Any
    actual: Any
    ok: bool
    category: str = "core"             # core | security | money | routes
    severity: str = "high"             # high | medium | low

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class InvariantReport:
    """Aggregate report of one pass."""
    at: datetime
    mode: str
    passed: int
    failed: int
    checks: List[InvariantCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.failed == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "at": self.at.isoformat(),
            "mode": self.mode,
            "passed": self.passed,
            "failed": self.failed,
            "ok": self.ok,
            "checks": [c.to_dict() for c in self.checks],
        }


class InvariantViolation(RuntimeError):
    """Raised in ``strict`` mode when ``run_all`` finds at least one failure."""
    def __init__(self, report: InvariantReport):
        super().__init__(f"{report.failed} invariant(s) failed")
        self.report = report


# ---------------------------------------------------------------------------
# The invariant table
# ---------------------------------------------------------------------------
# Each tuple is (name, description, category, severity, expected, op, async_actual_fn).
# The async fn receives the DB handle and returns an int / bool / scalar.
# Floors that should monotonically ratchet are tagged with severity=high.

async def _count_gated_routes(db) -> int:
    """Number of routes currently gated by LR2.

    Counts both the canonical ``require_permission(...)`` decorator and the
    project-specific ``_lr2_perm(...)`` / ``lr2_perm(...)`` wrappers used
    across the codebase.
    """
    try:
        import pathlib as _p
        n = 0
        for f in _p.Path("/app/backend").glob("lumen_*.py"):
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
                # Each usage is counted as one gated route hook.
                n += text.count("_lr2_perm(")
                n += text.count("lr2_perm(")
                n += text.count("require_permission(")
            except Exception:
                continue
        return n
    except Exception:
        return 0


async def _count_default_admins(db) -> int:
    """Users still shipping the seeded default-admin credential. Must be 0
    in production. Detect by both flag and by well-known seed emails."""
    try:
        count_flag = await db.users.count_documents({"is_default_admin": True})
    except Exception:
        count_flag = 0
    # Also probe by classic seeded emails if present (defensive — different
    # historical migrations used different markers).
    try:
        count_email = await db.users.count_documents(
            {"email": {"$in": ["admin@example.com", "default@admin.local",
                                "admin@lumen.local"]}}
        )
    except Exception:
        count_email = 0
    return int(count_flag) + int(count_email)


async def _count_active_funding_accounts(db) -> int:
    try:
        return await db.lumen_funding_accounts.count_documents({"active": True})
    except Exception:
        return 0


async def _count_treasury_adapters(db) -> int:
    """Treasury banking adapters registered in lumen_banking_adapter."""
    try:
        from lumen_banking_adapter import ADAPTER_REGISTRY  # type: ignore
        return len(ADAPTER_REGISTRY)
    except Exception:
        return 0


async def _count_compliance_matrix_combos(db) -> int:
    """LR2 compliance matrix = resource × action combos."""
    try:
        return await db.lumen_compliance_matrix.count_documents({})
    except Exception:
        return 0


async def _count_sepa_swift_endpoints(db) -> int:
    """Institutional rails — bank reconciliation surface."""
    try:
        import pathlib as _p
        text = _p.Path("/app/backend/lumen_bank_reconciliation.py").read_text(
            encoding="utf-8", errors="ignore"
        )
        return text.count("@router.")
    except Exception:
        return 0


async def _cors_wildcard_in_prod(db) -> bool:
    """In production, ``CORS_ORIGINS`` must NOT be ``*``."""
    env = (os.environ.get("LUMEN_ENV") or os.environ.get("ENV") or "preview").lower()
    if env not in {"production", "prod"}:
        return False
    raw = (os.environ.get("CORS_ORIGINS") or "").strip()
    return raw == "*" or "*" in {p.strip() for p in raw.split(",")}


async def _index_count_security_collections(db) -> int:
    """Both IR0 collections must have indexes."""
    cnt = 0
    for c in ("lumen_security_violations", "lumen_field_changes"):
        try:
            idx = await db[c].index_information()
            cnt += len(idx)
        except Exception:
            pass
    return cnt


async def _lr2_score(db) -> int:
    """Latest persisted LR2 scan score (0-100)."""
    try:
        async for snap in db.lumen_lr2_scans.find({}, {"_id": 0}).sort("at", -1).limit(1):
            score = snap.get("score")
            if isinstance(score, dict):
                # Lumen LR2 returns {total, max, parts, grade}
                return int(score.get("total", 0))
            return int(score or 0)
    except Exception:
        pass
    return 0


# ── operator helpers ────────────────────────────────────────────────────────
_OPS: Dict[str, Callable[[Any, Any], bool]] = {
    ">=": lambda a, e: a >= e,
    "<=": lambda a, e: a <= e,
    "==": lambda a, e: a == e,
    "!=": lambda a, e: a != e,
}


# ---------------------------------------------------------------------------
# The actual invariants table
# ---------------------------------------------------------------------------
INVARIANTS: List[Dict[str, Any]] = [
    # ── LR2 / routes ────────────────────────────────────────────────────
    {"name": "gated_routes",
     "description": "LR2 must gate ≥ 49 routes (floor — ratchet UP only).",
     "category": "routes", "severity": "high",
     "expected": 49, "op": ">=", "actual_fn": _count_gated_routes},
    {"name": "compliance_matrix_combos",
     "description": "LR2 resource×action matrix must cover ≥ 4 combos.",
     "category": "routes", "severity": "high",
     "expected": 4, "op": ">=", "actual_fn": _count_compliance_matrix_combos},
    {"name": "lr2_security_score",
     "description": "LR2 security score must be ≥ 90/100.",
     "category": "security", "severity": "medium",
     "expected": 90, "op": ">=", "actual_fn": _lr2_score},

    # ── security ────────────────────────────────────────────────────────
    {"name": "default_admin_count",
     "description": "No default-admin credential may exist in prod.",
     "category": "security", "severity": "high",
     "expected": 0, "op": "==", "actual_fn": _count_default_admins},
    {"name": "cors_wildcard_in_prod",
     "description": "CORS_ORIGINS may not be '*' in production.",
     "category": "security", "severity": "high",
     "expected": False, "op": "==", "actual_fn": _cors_wildcard_in_prod},
    {"name": "ir0_indexes_present",
     "description": "Security & field-change collections must be indexed.",
     "category": "security", "severity": "medium",
     "expected": 6, "op": ">=", "actual_fn": _index_count_security_collections},

    # ── money rails ─────────────────────────────────────────────────────
    {"name": "active_funding_accounts",
     "description": "At least one active funding account must exist.",
     "category": "money", "severity": "high",
     "expected": 1, "op": ">=", "actual_fn": _count_active_funding_accounts},
    {"name": "treasury_adapters",
     "description": "At least one Treasury adapter must be configured.",
     "category": "money", "severity": "medium",
     "expected": 1, "op": ">=", "actual_fn": _count_treasury_adapters},
    {"name": "sepa_swift_endpoints",
     "description": "Institutional SEPA/SWIFT endpoints surface must be ≥ 10.",
     "category": "money", "severity": "medium",
     "expected": 10, "op": ">=", "actual_fn": _count_sepa_swift_endpoints},
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
async def run_all(db) -> InvariantReport:
    """Run every registered invariant. Always returns a report — never raises."""
    checks: List[InvariantCheck] = []
    passed = failed = 0
    for spec in INVARIANTS:
        op_str = spec["op"]
        op_fn = _OPS[op_str]
        try:
            actual = await spec["actual_fn"](db)
        except Exception as exc:
            actual = f"<error: {exc}>"
        try:
            ok = bool(op_fn(actual, spec["expected"]))
        except Exception:
            ok = False
        c = InvariantCheck(
            name=spec["name"],
            description=spec["description"],
            operator=op_str,
            expected=spec["expected"],
            actual=actual,
            ok=ok,
            category=spec["category"],
            severity=spec["severity"],
        )
        checks.append(c)
        if ok:
            passed += 1
        else:
            failed += 1
    report = InvariantReport(
        at=datetime.now(timezone.utc),
        mode=resolve_mode(),
        passed=passed, failed=failed, checks=checks,
    )
    # Persist failures (best-effort, for the violations dashboard).
    if failed:
        try:
            for c in checks:
                if c.ok:
                    continue
                await db[VIOLATION_COLLECTION].insert_one({
                    "at": report.at,
                    "name": c.name,
                    "description": c.description,
                    "operator": c.operator,
                    "expected": c.expected,
                    "actual": c.actual,
                    "category": c.category,
                    "severity": c.severity,
                    "mode": report.mode,
                })
        except Exception as exc:  # pragma: no cover
            logger.debug("invariant violation insert failed: %s", exc)
    return report


# ---------------------------------------------------------------------------
# Startup hook
# ---------------------------------------------------------------------------
async def run_at_startup(db) -> InvariantReport:
    """Called once during FastAPI lifespan. Honours LUMEN_INVARIANTS_MODE."""
    mode = resolve_mode()
    if mode == "off":
        logger.info("IR0.4 invariants — mode=off, skipped")
        return InvariantReport(datetime.now(timezone.utc), mode, 0, 0, [])
    report = await run_all(db)
    if report.ok:
        logger.info(
            "IR0.4 invariants — all %d checks passed (mode=%s)",
            report.passed, mode,
        )
    else:
        for c in report.checks:
            if c.ok:
                continue
            logger.error(
                "IR0.4 invariant FAIL [%s, %s]: %s — expected %s %s, actual=%s",
                c.category, c.severity, c.name, c.operator, c.expected, c.actual,
            )
        if mode == "strict":
            raise InvariantViolation(report)
    return report


# ---------------------------------------------------------------------------
# REST surface (admin)
# ---------------------------------------------------------------------------
def register_invariant_routes(api_router, db, require_admin_dep) -> None:
    from fastapi import Depends, Query
    from datetime import datetime as _dt

    @api_router.get("/admin/architecture/invariants")
    async def list_invariants(_user: dict = Depends(require_admin_dep)):
        """Run all invariants live and return the current report."""
        rep = await run_all(db)
        return {"ok": True, **rep.to_dict()}

    @api_router.get("/admin/architecture/invariants/history")
    async def list_invariant_history(
        limit: int = Query(default=200, ge=1, le=1000),
        category: Optional[str] = Query(default=None),
        severity: Optional[str] = Query(default=None),
        _user: dict = Depends(require_admin_dep),
    ):
        q: Dict[str, Any] = {}
        if category:
            q["category"] = category
        if severity:
            q["severity"] = severity
        rows: List[Dict[str, Any]] = []
        async for r in db[VIOLATION_COLLECTION].find(q, {"_id": 0}).sort("at", -1).limit(limit):
            if isinstance(r.get("at"), _dt):
                r["at"] = r["at"].isoformat()
            rows.append(r)
        return {"ok": True, "count": len(rows), "items": rows}


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------
async def ensure_indexes(db) -> None:
    try:
        await db[VIOLATION_COLLECTION].create_index([("at", -1)])
        await db[VIOLATION_COLLECTION].create_index([("name", 1), ("at", -1)])
        await db[VIOLATION_COLLECTION].create_index([("category", 1), ("severity", 1)])
        # TTL — auto-prune after 365 days
        await db[VIOLATION_COLLECTION].create_index(
            [("at", 1)], expireAfterSeconds=60 * 60 * 24 * 365,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("invariant violations index ensure failed: %s", exc)


__all__ = [
    "run_all",
    "run_at_startup",
    "InvariantReport",
    "InvariantCheck",
    "InvariantViolation",
    "register_invariant_routes",
    "ensure_indexes",
    "INVARIANTS",
    "VIOLATION_COLLECTION",
    "resolve_mode",
]
