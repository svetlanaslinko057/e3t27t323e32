"""
LUMEN Sprint 12 — Notification Preferences (Block 7)

Adds a doman model for per-investor notification channels. Push infrastructure
itself is intentionally NOT wired (no FCM / APNS keys in env); we stay on the
existing `lumen_notifications` in-app channel but gate every emission on the
investor's preferences. When push gets wired later (Sprint 13+), the same
preference rows drive it without any code changes downstream.

Channels (the 7 categories the user named)
------------------------------------------
  kyc              — KYC submitted / approved / rejected
  contract         — contract drafted / signed / cancelled
  payment          — payment requested / confirmed / rejected
  payout           — periodic income credited
  withdrawal       — withdrawal status changes
  asset_update     — asset milestone / news
  qa_reply         — Q&A answered

Transports (per channel)
------------------------
  in_app   — lumen_notifications row (always on by default)
  email    — Resend / SMTP (dormant until env keys present)
  push     — FCM / APNS (dormant)

Collection: `lumen_notification_preferences`
  one document per (investor_id). Shape:

  {
    investor_id,
    channels: {
      kyc:           {in_app: true, email: true,  push: true},
      contract:      {...},
      payment:       {...},
      payout:        {...},
      withdrawal:    {...},
      asset_update:  {in_app: true, email: false, push: true},
      qa_reply:      {in_app: true, email: false, push: false},
    },
    quiet_hours: {start: "22:00", end: "08:00"} | None,   # local time, future use
    updated_at,
  }
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from lumen_api import db, get_current_user, require_admin, _strip_mongo, _now, _iso
from lumen_audit import write_audit

logger = logging.getLogger("lumen.notif_prefs")

CHANNELS = ("kyc", "contract", "payment", "payout",
            "withdrawal", "asset_update", "qa_reply")
TRANSPORTS = ("in_app", "email", "push")

DEFAULT_CHANNEL = {"in_app": True, "email": True, "push": True}
# Lower-priority channels default email/push off so we don't spam
LOW_PRIORITY_CHANNEL = {"in_app": True, "email": False, "push": True}

CHANNEL_DEFAULTS = {
    "kyc":          {**DEFAULT_CHANNEL},
    "contract":     {**DEFAULT_CHANNEL},
    "payment":      {**DEFAULT_CHANNEL},
    "payout":       {**DEFAULT_CHANNEL},
    "withdrawal":   {**DEFAULT_CHANNEL},
    "asset_update": {**LOW_PRIORITY_CHANNEL},
    "qa_reply":     {**LOW_PRIORITY_CHANNEL},
}


def _ensure_shape(doc: dict) -> dict:
    """Merge missing channels with defaults so a doc is always full-shape."""
    channels = dict(doc.get("channels") or {})
    for ch in CHANNELS:
        c = dict(channels.get(ch) or {})
        for t in TRANSPORTS:
            c.setdefault(t, CHANNEL_DEFAULTS[ch][t])
        channels[ch] = c
    doc["channels"] = channels
    return doc


async def get_or_default(investor_id: str) -> dict:
    """Return preferences doc for investor (always full-shape, never None)."""
    found = await db.lumen_notification_preferences.find_one({"investor_id": investor_id})
    if found:
        return _ensure_shape(found)
    return _ensure_shape({"investor_id": investor_id, "channels": {},
                          "quiet_hours": None, "updated_at": _now()})


async def is_allowed(investor_id: str, channel: str, transport: str = "in_app") -> bool:
    """Is the (channel,transport) emission allowed for this investor?"""
    if channel not in CHANNELS or transport not in TRANSPORTS:
        return True  # fail-open for unknown categories
    prefs = await get_or_default(investor_id)
    return bool(prefs["channels"].get(channel, {}).get(transport, True))


# ----------------------------------------------------------------------------
# Router
# ----------------------------------------------------------------------------

router = APIRouter(prefix="/api", tags=["lumen-notif-prefs"])


class TransportToggle(BaseModel):
    in_app: Optional[bool] = None
    email: Optional[bool] = None
    push: Optional[bool] = None


class PreferencesPatch(BaseModel):
    channels: Optional[dict[str, TransportToggle]] = None
    quiet_hours: Optional[dict] = None


@router.get("/investor/notification-preferences")
async def get_my_prefs(user=Depends(get_current_user)):
    prefs = await get_or_default(user["id"])
    return {
        "channels": prefs["channels"],
        "quiet_hours": prefs.get("quiet_hours"),
        "available_channels": list(CHANNELS),
        "available_transports": list(TRANSPORTS),
        "labels": {
            "kyc":          "Верифікація (KYC)",
            "contract":     "Договори",
            "payment":      "Платежі",
            "payout":       "Виплати доходу",
            "withdrawal":   "Виведення коштів",
            "asset_update": "Новини об'єктів",
            "qa_reply":     "Відповіді у Q&A",
        },
        "transport_labels": {
            "in_app": "В додатку",
            "email":  "Email",
            "push":   "Push (mobile)",
        },
    }


@router.patch("/investor/notification-preferences")
async def patch_my_prefs(payload: PreferencesPatch, request: Request,
                          user=Depends(get_current_user)):
    current = await get_or_default(user["id"])
    if payload.channels:
        for ch, toggle in payload.channels.items():
            if ch not in CHANNELS:
                raise HTTPException(status_code=400, detail=f"Unknown channel: {ch}")
            row = dict(current["channels"][ch])
            d = toggle.model_dump(exclude_unset=True)
            for t, v in d.items():
                if t in TRANSPORTS and v is not None:
                    row[t] = bool(v)
            current["channels"][ch] = row
    if payload.quiet_hours is not None:
        # Accept {start: "HH:MM", end: "HH:MM"} or None to clear
        if payload.quiet_hours and not (
            isinstance(payload.quiet_hours.get("start"), str)
            and isinstance(payload.quiet_hours.get("end"), str)
        ):
            raise HTTPException(status_code=400,
                                detail="quiet_hours must be {start, end}")
        current["quiet_hours"] = payload.quiet_hours or None

    current["updated_at"] = _now()
    await db.lumen_notification_preferences.update_one(
        {"investor_id": user["id"]},
        {"$set": current},
        upsert=True,
    )
    await write_audit(
        action="notification_prefs.update", category="system",
        target_type="lumen_notification_preferences", target_id=user["id"],
        actor=user, request=request,
        summary=f"Notification preferences updated for {user.get('email')}",
        meta={"channels": current["channels"]},
    )
    return await get_my_prefs(user=user)


@router.post("/investor/notification-preferences/reset")
async def reset_my_prefs(request: Request, user=Depends(get_current_user)):
    fresh = _ensure_shape({"investor_id": user["id"], "channels": {},
                           "quiet_hours": None, "updated_at": _now()})
    await db.lumen_notification_preferences.update_one(
        {"investor_id": user["id"]}, {"$set": fresh}, upsert=True,
    )
    await write_audit(
        action="notification_prefs.reset", category="system",
        target_type="lumen_notification_preferences", target_id=user["id"],
        actor=user, request=request,
        summary="Notification preferences reset to defaults",
    )
    return await get_my_prefs(user=user)


__all__ = ["router", "is_allowed", "get_or_default", "CHANNELS", "TRANSPORTS"]
