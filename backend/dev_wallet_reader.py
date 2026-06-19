"""
Phase 2C-B3 — developer wallet read facade (dual-read switch).

Purpose
-------
Every user-facing read of a developer's wallet (UI, payout eligibility,
dashboard tiles) flows through `read_dev_wallet()`. The facade reads
BOTH the canonical projection (`dev_wallets_projection`) AND the legacy
collection (`dev_wallets`), compares them on every call, logs structured
warnings when they disagree, and returns whichever source the operator
has selected via the `MONEY_READS_FROM_PROJECTION` feature flag.

Stage rollout — implemented by THIS file
----------------------------------------
    Stage A  (default)  flag=false  →  return legacy, log on mismatch
    Stage B             flag=true   →  return projection, log on mismatch
    Stage C             flag=true   →  same as B, divergence engine keeps
                                       reading legacy directly (for the
                                       compare/divergence endpoints).

Critical invariants this file MUST uphold
-----------------------------------------
    1. PROJECTION NEVER MUTATES STATE.  This file does not write to
       `dev_wallets_projection`. The shadow rebuild runs through
       `/api/admin/money/projections/dev-wallets/rebuild` only.
    2. LEGACY WRITES UNTOUCHED.  This file does not write to
       `dev_wallets`. The 11 grandfathered legacy writers stay.
    3. NEITHER MoneyService NOR money_projections IS MODIFIED.  The
       facade is a thin read-only adapter.
    4. The OUTPUT SHAPE matches the legacy `dev_wallets` document
       (float dollars, fields: `user_id`, `available_balance`,
       `earned_lifetime`, `withdrawn_lifetime`, `pending_withdrawal`),
       so call-sites can be migrated without touching their consumers.

Flag wiring
-----------
Read at every call (NOT cached) so an operator can flip a config map
without restarting the backend. Reading an env var on every call is
cheap (~µs) and worth the rollout safety.

Mismatch logging
----------------
Mismatches are logged as a single structured WARN line tagged
`event=dev_wallet_read.mismatch` with: `user_id`, `field`,
`legacy_cents`, `projection_cents`, `delta_cents`, and the
classification from `money_projections.compare_dev_wallet_projection`.
The `mock_orphan` developer is EXPECTED to mismatch and is logged at
INFO (not WARN) so it does not pollute the alarm channel.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import money_projections as _projections


log = logging.getLogger(__name__)


PROJECTION_FLAG_ENV = "MONEY_READS_FROM_PROJECTION"

# Schema the facade always returns, regardless of source. Matches what
# every existing legacy reader expects (float dollars).
WALLET_FIELDS = (
    "user_id",
    "available_balance",
    "earned_lifetime",
    "withdrawn_lifetime",
    "pending_withdrawal",
)


def _flag_on() -> bool:
    """`True` when the operator has flipped the cutover flag to Stage B.
    Read on every call so config changes apply without a restart."""
    return os.environ.get(PROJECTION_FLAG_ENV, "false").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _cents_to_dollars(c: int | None) -> float:
    return round((int(c) if c is not None else 0) / 100.0, 2)


# ── Shape adapters ─────────────────────────────────────────────────────────
def _projection_to_legacy_shape(projection: dict, legacy: dict) -> dict:
    """Translate the cents-based projection into the float-dollar
    `dev_wallets` document shape every caller already expects.

    Phase 2C-B4.3-C — `pending_withdrawal` source semantics:

      • If the projection has any ledger activity on `ac_reserved:<dev>`
        (flag `_pending_has_ledger_source = True`), use the projection
        value. This is the converged case post-B4.3-D.

      • If `_pending_has_ledger_source = False` AND legacy reports a
        non-zero pending, the writers in `server.py` have not yet been
        migrated (B4.3-D step 2). Fall back to legacy pending so the UI
        stays correct during the transition window.

      • If both projection and legacy have zero pending (or no legacy
        doc), report zero — same as before.

    This fallback is REMOVED in B4.3-D step 4 (or earlier, depending on
    the replay schedule). At that point legacy `pending_withdrawal` may
    drift without affecting the UI — exactly the goal state stated in
    the acceptance contract.
    """
    proj_pending_cents = projection.get("pending_withdrawal_cents")
    legacy_pending = round(float(legacy.get("pending_withdrawal") or 0), 2)
    has_ledger_source = bool(projection.get("_pending_has_ledger_source"))

    if has_ledger_source or proj_pending_cents:
        # Ledger has authoritative info (either a non-zero balance or at
        # least one row on ac_reserved). Trust projection.
        pending_value = _cents_to_dollars(proj_pending_cents)
        pending_source = "ledger"
    elif legacy_pending > 0:
        # Transition fallback — writer not migrated yet, legacy is correct.
        pending_value = legacy_pending
        pending_source = "legacy_fallback"
    else:
        pending_value = 0.0
        pending_source = "ledger"

    return {
        "user_id": projection["user_id"],
        "available_balance": _cents_to_dollars(
            projection.get("available_balance_cents")
        ),
        "earned_lifetime": _cents_to_dollars(
            projection.get("earned_lifetime_cents")
        ),
        "withdrawn_lifetime": _cents_to_dollars(
            projection.get("withdrawn_lifetime_cents")
        ),
        "pending_withdrawal": pending_value,
        # Forensic-only fields. UI consumers ignore them, but they keep
        # the response trail traceable through the dual-read window.
        "_read_source": "projection",
        "_pending_source": pending_source,
        "_accrual_pending_cents": projection.get("accrual_pending_cents"),
    }


def _legacy_normalised(legacy: dict, user_id: str) -> dict:
    """Return the legacy doc in canonical schema with `_read_source`
    tagged. Missing-doc case returns zeros (same as the original
    `find_one(...) or {default}` fallback at every call-site)."""
    if not legacy:
        return {
            "user_id": user_id,
            "available_balance": 0.0,
            "earned_lifetime": 0.0,
            "withdrawn_lifetime": 0.0,
            "pending_withdrawal": 0.0,
            "_read_source": "legacy_missing",
        }
    out: dict[str, Any] = {"_read_source": "legacy"}
    for f in WALLET_FIELDS:
        if f == "user_id":
            out[f] = legacy.get("user_id") or user_id
        else:
            out[f] = round(float(legacy.get(f) or 0), 2)
    return out


# ── The facade ─────────────────────────────────────────────────────────────
async def read_dev_wallet(db, user_id: str) -> dict[str, Any]:
    """Single canonical entry-point for "what's in this dev's wallet?".

    Always performs the dual-read and the compare so the divergence
    signal flows whether or not the cutover flag is on. Returns either
    legacy (Stage A) or projection (Stage B) depending on the flag.

    NEVER raises on projection failure — if the projection read fails
    for any reason, the facade falls back to legacy and logs the error.
    A bad projection must not break the UI.
    """
    legacy = (
        await db.dev_wallets.find_one({"user_id": user_id}, {"_id": 0})
        or {}
    )

    projection: dict[str, Any] | None = None
    classification = "skipped"
    try:
        comparison = await _projections.compare_dev_wallet_projection(
            db, user_id
        )
        projection = comparison.get("projection") or {}
        classification = comparison.get("classification") or "unknown"
        _log_compare(user_id, comparison)
    except Exception as e:  # noqa: BLE001 — projection must NEVER break UI reads
        log.warning(
            "event=dev_wallet_read.projection_error user_id=%s err=%r "
            "→ falling back to legacy", user_id, e,
        )
        projection = None

    use_projection = _flag_on() and projection is not None
    if use_projection:
        out = _projection_to_legacy_shape(projection, legacy)
    else:
        out = _legacy_normalised(legacy, user_id)

    # Forensic: which stage we are in for THIS read.
    out["_stage"] = "projection_primary" if _flag_on() else "legacy_primary"
    out["_classification"] = classification
    return out


def _log_compare(user_id: str, comparison: dict[str, Any]) -> None:
    """Emit a structured WARN for every legacy↔projection mismatch.

    Five classifications represent KNOWN demo/seed/transition/post-migration
    divergence patterns where the canonical ledger has nothing to compare
    against OR the legacy mirror is intentionally lagging:
      • `mock_orphan` — legacy claims a payout the ledger never recorded
        (the Phase 2C-D seeded orphan).
      • `legacy_only` — legacy doc exists, ledger has zero activity for
        this dev (other demo/seed-only wallets that pre-date the bridge).
      • `ledger_only` — Phase 2C-B4.4 post-migration steady state. The
        canonical ledger has activity for this dev (earnings, reserves,
        payouts) but the legacy `dev_wallets` mirror is empty. This is
        the *expected* shape for any developer who started earning AFTER
        B4.4 demoted `dev_wallets` to diagnostic-only: the canary in
        `mock_seed.py` is the only remaining writer, so any non-canary
        dev with canonical activity will naturally drift into this
        classification. Pre-B4.4 this was a "something is wrong" signal;
        post-B4.4 it is the new normal and must not page on-call.
      • `pending_pre_b4_3_d` — Phase 2C-B4.3-C transition state. Legacy
        has a non-zero `pending_withdrawal` (from
        `request_developer_withdrawal` writer), but `ac_reserved` is
        empty because the writer hasn't been migrated to emit the
        canonical `withdrawal_reserved` ledger event yet (B4.3-D step 2).
        Other balances converge — this is purely a transition signal,
        not a money-loss event.
      • `pending_post_b4_3_d1` — Phase 2C-B4.3-D1 transition state. The
        admin reject writer no longer decrements legacy pending; legacy
        stays "stuck" while the ledger correctly releases the reserve.
        UI reads from projection so the drift is invisible to users.
        This class disappears in B4.3-D step 4 once the request writer
        is also migrated.
      • `pending_post_b4_3_d2` — Phase 2C-B4.3-D2 transition state. The
        developer-request writer is ledger-only; legacy mirror stays at
        the pre-request shape until the withdrawal terminates.

    All six are operationally expected and must NOT page the on-call.
    They are logged at INFO so the divergence trail is still searchable.
    Anything else (`diverged`, …) wakes operations up.
    """
    classification = comparison.get("classification") or "unknown"
    diff = comparison.get("diff_cents") or {}
    nonzero = {k: v for k, v in diff.items() if int(v or 0) != 0}

    if not nonzero:
        # Either `matches` or both sides empty — nothing to report.
        return

    msg = (
        f"event=dev_wallet_read.mismatch user_id={user_id} "
        f"classification={classification} diff_cents={nonzero}"
    )
    if classification in (
        "mock_orphan",
        "legacy_only",
        "ledger_only",  # Phase 2C-B4.4 — post-migration steady state
        "pending_pre_b4_3_d",
        "pending_post_b4_3_d1",
        "pending_post_b4_3_d2",
    ):
        log.info(msg)
    else:
        log.warning(msg)
