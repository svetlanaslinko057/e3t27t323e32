"""
LUMEN — Manager OS · M1 — Staff ACL / Ownership Scope.

Single source of truth for "which staff user may see which lead". This is the
foundation of the whole Manager OS: without real enforcement a manager sees
the entire pipeline. Mirrors the locked 2-level model (Admin → Manager).

Role policy
-----------
  * admin / owner / master_admin / team_lead  →  PRIVILEGED, see everything
  * manager / operator                         →  SCOPED by ``lumen_managers.scope``
        - scope = "all"    → every lead (admin must grant this deliberately)
        - scope = "owned"  → only leads where owner_id == their user id (DEFAULT)
        - scope = "team"   → treated as "owned" until a team model exists
  * anything else                              →  denied (handled by require_staff)

The helpers are pure-async and dependency-free (only need ``db``), so any
router can reuse ONE policy instead of duplicating filters per call-site.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException

from lumen_api import db

logger = logging.getLogger("lumen.staff_acl")

MANAGERS = "lumen_managers"
META = "lumen_meta"

# Roles that always see everything (oversight). team_lead is deprecated but
# kept here so a legacy team-lead account is not locked out during transition.
PRIVILEGED_ROLES = {"admin", "owner", "master_admin", "team_lead"}


def staff_uid(user: dict) -> Optional[str]:
    return user.get("user_id") or user.get("id")


def is_privileged(user: dict) -> bool:
    """True when the user sees the entire pipeline regardless of ownership."""
    role = (user.get("role") or "").lower()
    roles = {str(r).lower() for r in (user.get("roles") or [])}
    return role in PRIVILEGED_ROLES or bool(roles & PRIVILEGED_ROLES)


async def get_manager_scope(user: dict) -> str:
    """Return the effective scope string for a user: 'all' | 'owned' | 'team'.

    Privileged users are always 'all'. A scoped manager defaults to 'owned'
    unless an admin has explicitly stored 'all' / 'team' on their manager row.
    """
    if is_privileged(user):
        return "all"
    uid = staff_uid(user)
    if not uid:
        return "owned"
    try:
        m = await db[MANAGERS].find_one({"user_id": uid}, {"scope": 1})
    except Exception:
        m = None
    scope = (m or {}).get("scope")
    if scope in ("all", "owned", "team"):
        return scope
    return "owned"


async def lead_scope_filter(user: dict) -> dict:
    """Return a Mongo filter limiting ``lumen_leads`` to what ``user`` may see.

    Merge this into any leads query: ``{**await lead_scope_filter(user), ...}``.
    """
    scope = await get_manager_scope(user)
    if scope == "all":
        return {}
    # owned + team (team == owned until a team membership model exists)
    return {"owner_id": staff_uid(user)}


async def can_see_lead(user: dict, lead: Optional[dict]) -> bool:
    if is_privileged(user):
        return True
    if not lead:
        return False
    scope = await get_manager_scope(user)
    if scope == "all":
        return True
    return lead.get("owner_id") == staff_uid(user)


async def assert_can_see_lead(user: dict, lead: Optional[dict]) -> None:
    if not await can_see_lead(user, lead):
        raise HTTPException(status_code=403, detail="Доступ лише до власних лідів")


# ---------------------------------------------------------------------------
# One-time normalization
# ---------------------------------------------------------------------------
# Historically ``upsert_manager_from_user`` stamped scope="all" on EVERY
# manager row (admins + managers alike). With real enforcement turned on that
# would let every manager see the whole pipeline. We reset non-admin managers
# to the safe 'owned' default exactly once (guarded by a meta marker), leaving
# admins (privileged anyway) untouched. Admin can re-grant 'all' deliberately.
NORMALIZE_VERSION = "acl_scope_owned_v1"


async def normalize_manager_scopes() -> dict:
    marker = await db[META].find_one({"key": "acl_scope_normalize"})
    if marker and marker.get("version") == NORMALIZE_VERSION:
        return {"skipped": True, "version": NORMALIZE_VERSION}
    updated = 0
    try:
        async for m in db[MANAGERS].find({"scope": "all"}):
            role = (m.get("role_in_users") or "").lower()
            # Resolve the live user role too (role_in_users may be stale).
            uid = m.get("user_id")
            u = (await db.users.find_one({"user_id": uid})
                 or await db.users.find_one({"id": uid}) or {})
            live_role = (u.get("role") or "").lower()
            live_roles = {str(r).lower() for r in (u.get("roles") or [])}
            privileged = (role in PRIVILEGED_ROLES
                          or live_role in PRIVILEGED_ROLES
                          or bool(live_roles & PRIVILEGED_ROLES))
            if privileged:
                continue  # keep admins/team_leads at 'all'
            await db[MANAGERS].update_one(
                {"user_id": uid},
                {"$set": {"scope": "owned"}},
            )
            updated += 1
    except Exception as e:
        logger.warning("normalize_manager_scopes failed: %s", e)
    await db[META].update_one(
        {"key": "acl_scope_normalize"},
        {"$set": {"key": "acl_scope_normalize", "version": NORMALIZE_VERSION,
                  "updated": updated}},
        upsert=True,
    )
    logger.info("[staff_acl] normalized %d manager scopes to 'owned'", updated)
    return {"skipped": False, "version": NORMALIZE_VERSION, "updated": updated}
