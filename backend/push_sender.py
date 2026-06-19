"""
Push Sender — Expo push transport.

One public entry point: `send_push(tokens, title, body, data)`.

Architectural note
------------------
`_emit_notification()` and `create_notification()` are async coroutines on a
motor-backed FastAPI server. Pushing with `requests.post` synchronously
would block the event loop (every insert would wait on exp.host). We keep
the wire call in `requests` (already a dep, no new transport) but hand it
off to a thread via `asyncio.to_thread`, and we `create_task` it so the
original emitter returns immediately — a push failure never stalls a
module transition or holds a DB write.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Iterable, Optional

import requests

logger = logging.getLogger("push_sender")

EXPO_URL = "https://exp.host/--/api/v2/push/send"
# Cap per-call so a single emit never fires >100 push messages by accident
# (misconfigured device dedupe, duplicated registrations, etc.).
MAX_TOKENS_PER_CALL = 100


def _is_expo_token(t: object) -> bool:
    """Expo-issued tokens always start with one of these two brackets.
    Anything else (FCM, APNs raw, empty string, None) we silently skip —
    exp.host returns a ticket error for them and we don't want the noise."""
    if not isinstance(t, str):
        return False
    return t.startswith("ExponentPushToken[") or t.startswith("ExpoPushToken[")


def _post_to_expo(messages: list[dict]) -> tuple[int, str]:
    try:
        r = requests.post(EXPO_URL, json=messages, timeout=5)
        # Truncate body so a 400 with a huge HTML page doesn't flood logs.
        return r.status_code, (r.text or "")[:300]
    except requests.RequestException as e:
        return 0, str(e)


async def send_push(
    tokens: Iterable[str],
    title: str,
    body: str,
    data: Optional[dict] = None,
) -> None:
    """Fire-and-forget push. Never raises — caller is an emitter, not a
    UX surface. If the Expo tier is down the in-app notification still
    lands (the db.notifications insert has already happened by the time
    this is called)."""
    cleaned = [t for t in (tokens or []) if _is_expo_token(t)]
    if not cleaned:
        return
    cleaned = cleaned[:MAX_TOKENS_PER_CALL]

    messages = [
        {
            "to": t,
            "sound": "default",
            "title": title or "",
            "body": body or "",
            "data": data or {},
        }
        for t in cleaned
    ]

    status, snippet = await asyncio.to_thread(_post_to_expo, messages)
    if status == 0:
        logger.warning("PUSH: transport error — %s", snippet)
    elif status >= 400:
        logger.warning("PUSH: exp.host %s — %s", status, snippet)
    else:
        logger.info("PUSH: sent %d message(s) → exp.host", len(messages))


def send_push_nowait(
    db,
    *,
    user_id: str,
    title: str = "",
    body: str = "",
    data: Optional[dict] = None,
    lang: Optional[str] = None,
    i18n_key_title: Optional[str] = None,
    i18n_key_body: Optional[str] = None,
    i18n_fmt: Optional[dict] = None,
) -> None:
    """Convenience wrapper used inside `_emit_notification` /
    `create_notification`. Looks up this user's push tokens and schedules
    a non-blocking send on the running loop.

    i18n contract (Phase i18n):
      * Callers may pass pre-translated `title`/`body` (legacy path).
      * Or pass `i18n_key_title` / `i18n_key_body` (+ optional `i18n_fmt`):
        the runner will fetch the user's stored `language` (falling back to
        the explicit `lang` arg, then to `en`) and translate at send time.
        This guarantees the push payload that hits the device is in the
        user's preferred locale even if the caller didn't know it.

    Why `create_task` instead of `await`:
      * the emitter is already on the critical path of a user action
        (approve, status transition, payout); a 200-400 ms round-trip to
        exp.host would visibly slow the API
      * we don't need the result — Expo tickets are fetched async anyway
      * if the loop is shutting down this degrades silently to a log line
    """

    async def _runner():
        try:
            # Resolve language: explicit > user record > en. Cheap single fetch.
            resolved_lang = lang
            if not resolved_lang and (i18n_key_title or i18n_key_body):
                try:
                    u = await db.users.find_one(
                        {"user_id": user_id}, {"_id": 0, "language": 1}
                    )
                    if u and u.get("language"):
                        resolved_lang = (u.get("language") or "").strip().lower().split("-", 1)[0]
                except Exception:
                    resolved_lang = None
            resolved_lang = resolved_lang or "en"

            final_title = title or ""
            final_body = body or ""
            if i18n_key_title or i18n_key_body:
                try:
                    from i18n_backend import t as _t  # lazy import to avoid cycles
                    fmt = i18n_fmt or {}
                    if i18n_key_title:
                        final_title = _t(i18n_key_title, resolved_lang, **fmt)
                    if i18n_key_body:
                        final_body = _t(i18n_key_body, resolved_lang, **fmt)
                except Exception as e:
                    logger.debug("PUSH i18n translate failed: %s", e)

            cur = db.push_tokens.find({"user_id": user_id}, {"_id": 0, "token": 1})
            tokens = [t.get("token") async for t in cur if t.get("token")]
            if not tokens:
                return
            await send_push(tokens, title=final_title, body=final_body, data=data)
        except Exception as e:  # noqa: BLE001 — push must never break an emit
            logger.warning("PUSH: unexpected failure for user=%s: %s", user_id, e)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_runner())
    except RuntimeError:
        # Not running in an event loop (e.g. called from a sync test harness).
        # Fall back to a detached run — still non-blocking.
        asyncio.run(_runner())
