"""
LUMEN IR0.3 — Field-Level Change History
==========================================

A single, generic journal for **field-level diffs** on any sensitive entity:
investor profile, KYC profile, certificate, funding account (IBAN!), round,
contract, asset, SPV, LP/GP record, etc.

Why a dedicated layer (we already have ``lumen_audit_log``)
-----------------------------------------------------------
``lumen_audit_log`` records HIGH-LEVEL actions (``kyc.approve``,
``transfer.reconcile``, ``contract.sign``). It does NOT answer questions like:

  ▸ "Who changed this investor's IBAN from DE89... to UA29...?"
  ▸ "When did the certificate face value drop from 1 000 000 to 950 000?"
  ▸ "Which fields of the round were touched between submitted → review?"

Field-level history fills that gap with a denormalised, per-field row that a
compliance reviewer / regulator / forensic auditor can query in one shot.

Schema (collection ``lumen_field_changes``)
-------------------------------------------
    {
        "id":             "fc_<hex12>",
        "at":             ISODate (UTC),                        # indexed
        "entity_type":    "investor" | "kyc" | "certificate" |
                          "funding_account" | "round" | "contract" |
                          "asset" | "spv" | "lp_commitment" | ...   # indexed
        "entity_id":      "<id>",                                # indexed
        "field":          "iban" | "kyc_status" | "face_value" | ...
        "old_value":      <jsonable scalar | dict | None>,
        "new_value":      <jsonable scalar | dict | None>,
        "changed_by_id":  "<user-id>",
        "changed_by_email": "<email-snapshot>",
        "changed_by_role":  "admin" | "investor" | "operator" | "system",
        "ip":             "<client ip or null>",
        "source":         "api" | "system" | "migration" | "import",
        "request_id":     "<x-request-id correlation>",          # nullable
        "reason":         "<optional free-text reason>",
        "category":       "compliance" | "money" | "asset" | "auth"   # indexed
    }

Public surface
--------------
- ``record_change(...)``  — record ONE field change (caller usually batches)
- ``record_diff(...)``    — diff two dicts and emit one row per changed field
- ``register_field_changes_routes(api_router, db, require_admin_dep)`` —
  admin REST surface:
       GET /api/admin/field-changes/{entity_type}/{entity_id}?limit=...
       GET /api/admin/field-changes/recent?category=money&limit=...
- ``ensure_indexes(db)``  — call once at startup.

The module is dependency-free (no external libraries), additive, and SAFE TO
CALL FROM ANY HANDLER without taking a write lock — all inserts are best-
effort and swallowed on failure (the business operation must not fail
because of an audit-write hiccup).
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

logger = logging.getLogger("lumen.field_changes")

COLLECTION = "lumen_field_changes"

# Fields per entity_type that are considered SENSITIVE and worth logging.
# Anything outside this set is silently skipped — keeps the journal focused
# (you don't want updated_at flooding the history).
SENSITIVE_FIELDS: Dict[str, Set[str]] = {
    "investor": {
        "email", "phone", "country", "tax_id", "tax_residency",
        "investor_segment", "risk_profile", "kyc_status",
        "accreditation_status", "name", "full_name", "wallet_address",
    },
    "kyc": {
        "kyc_status", "review_decision", "rejection_reason",
        "review_notes", "documents",
    },
    "certificate": {
        "status", "face_value", "currency", "owner_id", "owner_email",
        "round_id", "asset_id", "issued_at", "matured_at", "revoked_at",
        "redemption_status",
    },
    "funding_account": {
        "iban", "bic", "account_holder", "currency", "bank_name",
        "purpose", "status",                # active / disabled
    },
    "round": {
        "status", "target_amount", "min_ticket", "max_ticket",
        "currency", "open_at", "close_at", "soft_cap", "hard_cap",
        "interest_rate", "term_months",
    },
    "contract": {
        "status", "signed_at", "version", "template_id", "amount",
        "currency", "iban_outgoing",
    },
    "asset": {
        "status", "publication_state", "target_amount", "operator_id",
        "category", "location", "currency", "interest_rate", "term_months",
    },
    "spv": {
        "status", "jurisdiction", "registration_number", "bank_account",
        "directors",
    },
    "lp_commitment": {
        "status", "amount_committed", "amount_paid", "role", "fund_id",
        "currency",
    },
    "operator": {
        "status", "rating", "kyc_status", "contract_state", "fee_rate",
    },
    "user": {
        "role", "email", "status", "locked",
    },
    "lead": {
        "stage", "manual_stage", "owner_id", "owner_type", "status",
        "user_id", "investor_profile_id", "source", "budget_range",
    },
}

# Category routing — used for "recent activity by domain" queries.
ENTITY_CATEGORY: Dict[str, str] = {
    "investor": "compliance",
    "kyc": "compliance",
    "certificate": "money",
    "funding_account": "money",
    "round": "money",
    "contract": "money",
    "asset": "asset",
    "spv": "asset",
    "lp_commitment": "money",
    "operator": "asset",
    "user": "auth",
    "lead": "investor_relations",
}

# Hard cap on a single row to avoid runaway logs (e.g. a 50 MB JSON blob
# inadvertently pushed into "review_notes"). Values bigger than the cap are
# stored as ``{"_truncated": true, "preview": "<first 256 chars>"}``.
_MAX_VALUE_BYTES = 4096


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return "fc_" + secrets.token_hex(6)


def _safe_value(v: Any) -> Any:
    """Cap any single field value to keep the history collection lean."""
    if v is None:
        return None
    try:
        import json as _json
        encoded = _json.dumps(v, default=str)
    except Exception:
        encoded = str(v)
    if len(encoded) <= _MAX_VALUE_BYTES:
        return v
    return {"_truncated": True, "preview": encoded[:256]}


def _actor_view(actor: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not actor:
        return {"changed_by_id": None, "changed_by_email": None, "changed_by_role": "system"}
    role = (actor.get("role") or "").lower() or "system"
    return {
        "changed_by_id": actor.get("user_id") or actor.get("id"),
        "changed_by_email": actor.get("email"),
        "changed_by_role": role,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def record_change(
    db,
    *,
    entity_type: str,
    entity_id: str,
    field: str,
    old_value: Any,
    new_value: Any,
    actor: Optional[Dict[str, Any]] = None,
    source: str = "api",
    reason: Optional[str] = None,
    request_id: Optional[str] = None,
    ip: Optional[str] = None,
) -> Optional[str]:
    """Record ONE field change. Returns the inserted id or None on failure.

    Skips silently when:
      - entity_type unknown (callers may pass arbitrary types — that's fine,
        they just won't show in the per-entity history feed).
      - field not in SENSITIVE_FIELDS for that type.
      - old_value == new_value.
    """
    try:
        if old_value == new_value:
            return None
        allowed = SENSITIVE_FIELDS.get(entity_type)
        if allowed is not None and field not in allowed:
            return None
        row = {
            "id": _new_id(),
            "at": _now(),
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "field": field,
            "old_value": _safe_value(old_value),
            "new_value": _safe_value(new_value),
            "source": source,
            "reason": (reason or None),
            "request_id": (request_id or None),
            "ip": (ip or None),
            "category": ENTITY_CATEGORY.get(entity_type, "other"),
        }
        row.update(_actor_view(actor))
        await db[COLLECTION].insert_one(row)
        return row["id"]
    except Exception as exc:  # pragma: no cover — best-effort
        logger.debug("record_change failed: %s", exc)
        return None


async def record_diff(
    db,
    *,
    entity_type: str,
    entity_id: str,
    before: Dict[str, Any],
    after: Dict[str, Any],
    actor: Optional[Dict[str, Any]] = None,
    source: str = "api",
    fields: Optional[Sequence[str]] = None,
    reason: Optional[str] = None,
    request_id: Optional[str] = None,
    ip: Optional[str] = None,
) -> List[str]:
    """Diff two dicts and emit one row per CHANGED sensitive field.

    ``fields`` lets callers explicitly restrict the diff to a sub-set; when
    omitted, the union of keys in ``before`` ∪ ``after`` is considered.

    Returns the list of inserted ids (empty when no changes recorded).
    """
    keys: Iterable[str]
    if fields is not None:
        keys = list(fields)
    else:
        keys = set((before or {}).keys()) | set((after or {}).keys())
    ids: List[str] = []
    for k in keys:
        old_v = (before or {}).get(k)
        new_v = (after or {}).get(k)
        if old_v == new_v:
            continue
        new_id = await record_change(
            db, entity_type=entity_type, entity_id=entity_id,
            field=k, old_value=old_v, new_value=new_v,
            actor=actor, source=source, reason=reason,
            request_id=request_id, ip=ip,
        )
        if new_id:
            ids.append(new_id)
    return ids


# ---------------------------------------------------------------------------
# Read API (admin)
# ---------------------------------------------------------------------------
async def list_for_entity(
    db,
    *,
    entity_type: str,
    entity_id: str,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    cursor = db[COLLECTION].find(
        {"entity_type": entity_type, "entity_id": str(entity_id)},
        {"_id": 0},
    ).sort("at", -1).limit(max(1, min(limit, 500)))
    async for r in cursor:
        if isinstance(r.get("at"), datetime):
            r["at"] = r["at"].isoformat()
        rows.append(r)
    return rows


async def list_recent(
    db,
    *,
    category: Optional[str] = None,
    field: Optional[str] = None,
    actor_id: Optional[str] = None,
    since: Optional[datetime] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if category:
        q["category"] = category
    if field:
        q["field"] = field
    if actor_id:
        q["changed_by_id"] = actor_id
    if since:
        q["at"] = {"$gte": since}
    rows: List[Dict[str, Any]] = []
    cursor = db[COLLECTION].find(q, {"_id": 0}).sort("at", -1).limit(max(1, min(limit, 1000)))
    async for r in cursor:
        if isinstance(r.get("at"), datetime):
            r["at"] = r["at"].isoformat()
        rows.append(r)
    return rows


# ---------------------------------------------------------------------------
# REST surface (admin)
# ---------------------------------------------------------------------------
def register_field_changes_routes(api_router, db, require_admin_dep) -> None:
    from fastapi import Depends, Query

    @api_router.get("/admin/field-changes/recent")
    async def field_changes_recent(
        category: Optional[str] = Query(default=None),
        field: Optional[str] = Query(default=None),
        actor_id: Optional[str] = Query(default=None),
        since: Optional[str] = Query(default=None),
        limit: int = Query(default=200, ge=1, le=1000),
        _user: dict = Depends(require_admin_dep),
    ):
        since_dt: Optional[datetime] = None
        if since:
            try:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except Exception:
                since_dt = None
        rows = await list_recent(
            db, category=category, field=field,
            actor_id=actor_id, since=since_dt, limit=limit,
        )
        return {"ok": True, "count": len(rows), "items": rows}

    @api_router.get("/admin/field-changes/{entity_type}/{entity_id}")
    async def field_changes_entity(
        entity_type: str,
        entity_id: str,
        limit: int = Query(default=100, ge=1, le=500),
        _user: dict = Depends(require_admin_dep),
    ):
        rows = await list_for_entity(
            db, entity_type=entity_type, entity_id=entity_id, limit=limit,
        )
        return {
            "ok": True,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "count": len(rows),
            "items": rows,
        }


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------
async def ensure_indexes(db) -> None:
    try:
        await db[COLLECTION].create_index([("at", -1)])
        await db[COLLECTION].create_index(
            [("entity_type", 1), ("entity_id", 1), ("at", -1)],
        )
        await db[COLLECTION].create_index([("changed_by_id", 1), ("at", -1)])
        await db[COLLECTION].create_index([("category", 1), ("at", -1)])
        await db[COLLECTION].create_index([("field", 1), ("at", -1)])
        # TTL — auto-prune after 5 years (regulator-friendly retention)
        retention_seconds = int(os.environ.get("LUMEN_FIELD_HISTORY_TTL_SEC",
                                                 str(60 * 60 * 24 * 365 * 5)))
        await db[COLLECTION].create_index(
            [("at", 1)], expireAfterSeconds=retention_seconds,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("field_changes index ensure failed: %s", exc)


__all__ = [
    "record_change",
    "record_diff",
    "list_for_entity",
    "list_recent",
    "register_field_changes_routes",
    "ensure_indexes",
    "SENSITIVE_FIELDS",
    "ENTITY_CATEGORY",
    "COLLECTION",
]
