"""
LUMEN repositories — Sprint 1 / Phase 0.

Thin async repository layer over Motor (MongoDB). Provides:

  • Idempotent index creation for all LUMEN core collections.
  • A minimal CRUD primitive set (`insert`, `get`, `find`, `update`, `delete`)
    that other layers can reuse without sprinkling raw Mongo calls everywhere.

NO business logic lives here — no payment processing, no approval flow, no
yield accrual. Those layers will be added in Sprint 2 (Investment Core)
on top of these repositories.

Design notes
------------
* All identifiers are UUID v4 strings (project-wide rule).
* All datetimes are timezone-aware UTC.
* Repositories do NOT validate Pydantic models — callers are expected to
  serialize via `.model_dump(mode='json')` before calling `insert` / `update`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from lumen_models import LUMEN_COLLECTIONS

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Generic repository
# ──────────────────────────────────────────────────────────────────────────────

class LumenRepository:
    """Async repository for a single LUMEN collection.

    Strict separation from EVA-X legacy: this class deals ONLY with the
    LUMEN_COLLECTIONS set defined in `lumen_models.py`.
    """

    def __init__(self, db: AsyncIOMotorDatabase, collection_name: str):
        if collection_name not in LUMEN_COLLECTIONS:
            raise ValueError(
                f"Unknown LUMEN collection '{collection_name}'. "
                f"Allowed: {sorted(LUMEN_COLLECTIONS.keys())}"
            )
        self.db = db
        self.name = collection_name
        self.col = db[collection_name]

    # --- write ----------------------------------------------------------------

    async def insert(self, doc: Mapping[str, Any]) -> str:
        payload = dict(doc)
        payload.setdefault("created_at", datetime.now(timezone.utc))
        payload.setdefault("updated_at", datetime.now(timezone.utc))
        await self.col.insert_one(payload)
        return payload.get("id") or payload.get("_id")

    async def update(self, doc_id: str, patch: Mapping[str, Any]) -> bool:
        patch = dict(patch)
        patch["updated_at"] = datetime.now(timezone.utc)
        res = await self.col.update_one({"id": doc_id}, {"$set": patch})
        return res.modified_count > 0

    async def delete(self, doc_id: str) -> bool:
        res = await self.col.delete_one({"id": doc_id})
        return res.deleted_count > 0

    # --- read -----------------------------------------------------------------

    async def get(self, doc_id: str) -> Optional[Dict[str, Any]]:
        return await self.col.find_one({"id": doc_id}, {"_id": 0})

    async def find(
        self,
        query: Optional[Mapping[str, Any]] = None,
        *,
        limit: int = 100,
        skip: int = 0,
        sort: Optional[List[tuple]] = None,
    ) -> List[Dict[str, Any]]:
        cursor = self.col.find(query or {}, {"_id": 0})
        if sort:
            cursor = cursor.sort(sort)
        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)
        return await cursor.to_list(length=limit or None)

    async def count(self, query: Optional[Mapping[str, Any]] = None) -> int:
        return await self.col.count_documents(query or {})


# ──────────────────────────────────────────────────────────────────────────────
# Index registry — one place for every LUMEN core index.
# ──────────────────────────────────────────────────────────────────────────────
#
# Each entry: collection_name -> list of (keys_spec, options_dict)
# Indexes are idempotent (Mongo no-ops if already present).

_LUMEN_INDEXES: Dict[str, List[tuple]] = {
    "lumen_assets": [
        ([("id", 1)], {"name": "ux_assets_id", "unique": True}),
        ([("status", 1)], {"name": "ix_assets_status"}),
        ([("category", 1)], {"name": "ix_assets_category"}),
    ],
    "lumen_investment_rounds": [
        ([("id", 1)], {"name": "ux_rounds_id", "unique": True}),
        ([("asset_id", 1), ("round_number", 1)], {
            "name": "ux_rounds_asset_round", "unique": True,
        }),
        ([("status", 1)], {"name": "ix_rounds_status"}),
    ],
    "lumen_investor_intents": [
        ([("id", 1)], {"name": "ux_intents_id", "unique": True}),
        ([("asset_id", 1)], {"name": "ix_intents_asset"}),
        ([("investor_id", 1)], {"name": "ix_intents_investor"}),
        ([("status", 1)], {"name": "ix_intents_status"}),
        ([("submitted_at", -1)], {"name": "ix_intents_submitted_desc"}),
    ],
    "lumen_investments": [
        ([("id", 1)], {"name": "ux_investments_id", "unique": True}),
        ([("asset_id", 1)], {"name": "ix_investments_asset"}),
        ([("investor_id", 1)], {"name": "ix_investments_investor"}),
        ([("status", 1)], {"name": "ix_investments_status"}),
        ([("intent_id", 1)], {"name": "ix_investments_intent"}),
    ],
    "lumen_ownerships": [
        ([("id", 1)], {"name": "ux_ownerships_id", "unique": True}),
        ([("investor_id", 1), ("asset_id", 1)], {
            "name": "ux_ownerships_investor_asset", "unique": True,
        }),
        ([("asset_id", 1)], {"name": "ix_ownerships_asset"}),
    ],
    "lumen_investor_profiles": [
        ([("id", 1)], {"name": "ux_profiles_id", "unique": True}),
        ([("user_id", 1)], {"name": "ux_profiles_user", "unique": True}),
        ([("kyc_status", 1)], {"name": "ix_profiles_kyc_status"}),
    ],
    "lumen_kyc_documents": [
        ([("id", 1)], {"name": "ux_kyc_docs_id", "unique": True}),
        ([("investor_id", 1)], {"name": "ix_kyc_docs_investor"}),
        ([("doc_type", 1)], {"name": "ix_kyc_docs_type"}),
    ],
    "lumen_contract_templates": [
        ([("id", 1)], {"name": "ux_ctpl_id", "unique": True}),
        ([("kind", 1)], {"name": "ix_ctpl_kind"}),
        ([("active", 1)], {"name": "ix_ctpl_active"}),
    ],
    "lumen_contracts": [
        ([("id", 1)], {"name": "ux_contracts_id", "unique": True}),
        ([("investor_id", 1)], {"name": "ix_contracts_investor"}),
        ([("investment_id", 1)], {"name": "ix_contracts_investment"}),
        ([("asset_id", 1)], {"name": "ix_contracts_asset"}),
        ([("status", 1)], {"name": "ix_contracts_status"}),
        ([("number", 1)], {"name": "ux_contracts_number", "unique": True}),
    ],
    "lumen_signatures": [
        ([("id", 1)], {"name": "ux_signatures_id", "unique": True}),
        ([("contract_id", 1)], {"name": "ix_signatures_contract"}),
        ([("user_id", 1)], {"name": "ix_signatures_user"}),
    ],
    "lumen_asset_updates": [
        ([("id", 1)], {"name": "ux_asset_updates_id", "unique": True}),
        ([("asset_id", 1)], {"name": "ix_asset_updates_asset"}),
        ([("published", 1)], {"name": "ix_asset_updates_published"}),
        ([("created_at", -1)], {"name": "ix_asset_updates_created_desc"}),
    ],
    "lumen_asset_reports": [
        ([("id", 1)], {"name": "ux_asset_reports_id", "unique": True}),
        ([("asset_id", 1)], {"name": "ix_asset_reports_asset"}),
        ([("report_type", 1)], {"name": "ix_asset_reports_type"}),
    ],
    "lumen_asset_documents": [
        ([("id", 1)], {"name": "ux_asset_docs_id", "unique": True}),
        ([("asset_id", 1)], {"name": "ix_asset_docs_asset"}),
        ([("doc_type", 1)], {"name": "ix_asset_docs_type"}),
        ([("visibility", 1)], {"name": "ix_asset_docs_visibility"}),
    ],
    "lumen_asset_questions": [
        ([("id", 1)], {"name": "ux_asset_questions_id", "unique": True}),
        ([("asset_id", 1)], {"name": "ix_asset_questions_asset"}),
        ([("investor_id", 1)], {"name": "ix_asset_questions_investor"}),
        ([("status", 1)], {"name": "ix_asset_questions_status"}),
    ],
    "lumen_spvs": [
        ([("id", 1)], {"name": "ux_spvs_id", "unique": True}),
        ([("asset_id", 1)], {"name": "ix_spvs_asset"}),
        ([("status", 1)], {"name": "ix_spvs_status"}),
    ],
    # ── Sprint 6: Payments & Funding + Ledger ──
    "lumen_payment_requests": [
        ([("id", 1)], {"name": "ux_payreq_id", "unique": True}),
        ([("investor_id", 1)], {"name": "ix_payreq_investor"}),
        ([("investment_id", 1)], {"name": "ix_payreq_investment"}),
        ([("asset_id", 1)], {"name": "ix_payreq_asset"}),
        ([("status", 1)], {"name": "ix_payreq_status"}),
        ([("created_at", -1)], {"name": "ix_payreq_created_desc"}),
    ],
    "lumen_payment_proofs": [
        ([("id", 1)], {"name": "ux_payproof_id", "unique": True}),
        ([("payment_request_id", 1)], {"name": "ix_payproof_request"}),
        ([("investor_id", 1)], {"name": "ix_payproof_investor"}),
    ],
    "lumen_funding_accounts": [
        ([("id", 1)], {"name": "ux_fundacc_id", "unique": True}),
        ([("active", 1)], {"name": "ix_fundacc_active"}),
        ([("currency", 1)], {"name": "ix_fundacc_currency"}),
    ],
    "lumen_ledger_entries": [
        ([("id", 1)], {"name": "ux_ledger_id", "unique": True}),
        ([("entry_type", 1)], {"name": "ix_ledger_type"}),
        ([("reason", 1)], {"name": "ix_ledger_reason"}),
        ([("investor_id", 1)], {"name": "ix_ledger_investor"}),
        ([("asset_id", 1)], {"name": "ix_ledger_asset"}),
        ([("investment_id", 1)], {"name": "ix_ledger_investment"}),
        ([("payment_request_id", 1)], {"name": "ix_ledger_payreq"}),
        ([("created_at", -1)], {"name": "ix_ledger_created_desc"}),
    ],
    "lumen_notifications": [
        ([("id", 1)], {"name": "ux_lumen_notif_id", "unique": True}),
        ([("investor_id", 1)], {"name": "ix_lumen_notif_investor"}),
        ([("read", 1)], {"name": "ix_lumen_notif_read"}),
        ([("created_at", -1)], {"name": "ix_lumen_notif_created_desc"}),
    ],
}


async def ensure_lumen_indexes(db: AsyncIOMotorDatabase) -> Dict[str, List[str]]:
    """Create all LUMEN core indexes (idempotent).

    Returns a map of collection -> [created/existing index names] for logging.
    """
    summary: Dict[str, List[str]] = {}
    for coll_name, indexes in _LUMEN_INDEXES.items():
        col = db[coll_name]
        names: List[str] = []
        for keys, opts in indexes:
            try:
                idx_name = await col.create_index(keys, **opts)
                names.append(idx_name)
            except Exception as e:  # pragma: no cover (mongo edge cases)
                logger.warning(
                    "ensure_lumen_indexes: failed on %s.%s: %s",
                    coll_name, opts.get("name"), e,
                )
        summary[coll_name] = names
    return summary


# ──────────────────────────────────────────────────────────────────────────────
# Convenience accessors
# ──────────────────────────────────────────────────────────────────────────────

def assets_repo(db: AsyncIOMotorDatabase) -> LumenRepository:
    return LumenRepository(db, "lumen_assets")


def rounds_repo(db: AsyncIOMotorDatabase) -> LumenRepository:
    return LumenRepository(db, "lumen_investment_rounds")


def intents_repo(db: AsyncIOMotorDatabase) -> LumenRepository:
    return LumenRepository(db, "lumen_investor_intents")


def investments_repo(db: AsyncIOMotorDatabase) -> LumenRepository:
    return LumenRepository(db, "lumen_investments")


def ownerships_repo(db: AsyncIOMotorDatabase) -> LumenRepository:
    return LumenRepository(db, "lumen_ownerships")


def profiles_repo(db: AsyncIOMotorDatabase) -> LumenRepository:
    return LumenRepository(db, "lumen_investor_profiles")


__all__ = [
    "LumenRepository",
    "ensure_lumen_indexes",
    "assets_repo",
    "rounds_repo",
    "intents_repo",
    "investments_repo",
    "ownerships_repo",
    "profiles_repo",
]
