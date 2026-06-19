"""Index definitions for LUMEN Capital Pool OS."""
from __future__ import annotations

import logging

logger = logging.getLogger("lumen.pool_os")


async def ensure_pool_os_indexes(db) -> None:
    try:
        await db.lumen_pools.create_index("id", unique=True)
        await db.lumen_pools.create_index("asset_id")
        await db.lumen_pools.create_index("status")

        await db.lumen_pool_contributions.create_index("id", unique=True)
        await db.lumen_pool_contributions.create_index("pool_id")
        await db.lumen_pool_contributions.create_index("investor_id")
        await db.lumen_pool_contributions.create_index("reference", unique=True)
        await db.lumen_pool_contributions.create_index([("pool_id", 1), ("status", 1)])

        await db.lumen_pool_allocations.create_index("id", unique=True, sparse=True)
        await db.lumen_pool_allocations.create_index(
            [("pool_id", 1), ("investor_id", 1)], unique=True)

        await db.lumen_pool_ledger.create_index("id", unique=True)
        await db.lumen_pool_ledger.create_index("pool_id")
        await db.lumen_pool_ledger.create_index("kind")
        await db.lumen_pool_ledger.create_index("created_at")

        await db.lumen_pool_releases.create_index("id", unique=True)
        await db.lumen_pool_releases.create_index("pool_id")

        await db.lumen_pool_certificates.create_index("id", unique=True)
        await db.lumen_pool_certificates.create_index([("pool_id", 1), ("investor_id", 1)])
        await db.lumen_pool_certificates.create_index("investor_id")

        await db.lumen_revenue_events.create_index("id", unique=True)
        await db.lumen_revenue_events.create_index("pool_id")
        await db.lumen_revenue_events.create_index("status")

        await db.lumen_revenue_distributions.create_index("id", unique=True)
        await db.lumen_revenue_distributions.create_index("pool_id")
        await db.lumen_revenue_distributions.create_index("investor_id")
        await db.lumen_revenue_distributions.create_index("revenue_event_id")

        await db.lumen_pool_balances.create_index(
            [("investor_id", 1), ("currency", 1)], unique=True)

        await db.lumen_pool_withdrawals.create_index("id", unique=True)
        await db.lumen_pool_withdrawals.create_index("investor_id")
        await db.lumen_pool_withdrawals.create_index("status")

        logger.info("POOL OS: indexes ensured")
    except Exception as e:  # pragma: no cover
        logger.warning("POOL OS: index ensure failed: %s", e)
