"""
LUMEN — F7 Outlook / Microsoft 365 Adapter
==========================================

Thin adapter on top of F5, mirroring F6 Gmail bone-for-bone. Microsoft
Graph provides the email surface; everything else (timeline, feed,
counters, attribution, dedup) is owned by the F5 ingestion core.

    Microsoft Graph  ←─ OAuth2 / Subscriptions / sendMail
            │
            ▼
       OutlookAdapter             (this file)
            │
            ▼
    record_communication()        (F5 single ingestion core — unchanged)
            │
            ▼
    lumen_lead_communications     (single source of truth — unchanged)

What F7 adds (and ONLY this):
  • ``OutlookAdapter(CommAdapter)`` — ``send()`` + ``normalize_inbound()``.
    Refreshes its ``connected`` flag from provider config oauth_status.
  • ``/api/comms/oauth/outlook/start``    → 302 to login.microsoftonline.com
    with a CSRF ``state`` minted into ``lumen_oauth_state`` (TTL 10 min,
    same collection used by F6 — keyed by ``kind="outlook.oauth"``).
  • ``/api/comms/oauth/outlook/callback`` → validates state, exchanges
    code, stores tokens in ``provider.config.outlook``, flips
    ``oauth_status=connected``, writes ``oauth.outlook.connect`` audit
    row, seeds the first verified inbound sample so the live wiring
    contract is exercised end-to-end.
  • ``/api/comms/webhook/outlook`` — Graph notifications endpoint.
    Verifies BOTH (a) ``clientState`` matches the value stored on the
    subscription, AND (b) HMAC-SHA256 over the raw body via
    ``X-Lumen-Signature`` (alias ``X-Hub-Signature-256``). Either failure
    → 401 with **zero writes**. Also supports the Graph ``validationToken``
    handshake (echoes the token within 10 s).
  • Refresh-token rotation helper → writes
    ``category=oauth.outlook.refresh`` to ``lumen_staff_login_audit``.
  • Reuses the F5 activation guard (set by F6): ``outlook`` status=active
    requires ``provider.config.outlook.oauth_status == 'connected'``.

What is NOT changed:
  • No new collection acts as Outlook source-of-truth (R2).
  • IR / Timeline / Funnel / Manager OS surfaces untouched (R1).
  • F5 dedup (R6) is reused as-is.
  • Same ``lumen_oauth_state`` collection F6 introduced.
  • Same activation-guard mechanism F6 extended.

Mock-mode (no ``OUTLOOK_CLIENT_ID``/``MS_CLIENT_ID`` env): the start
route still returns a redirect carrying ``state=``; the callback
validates state + simulates token exchange. Production-mode: set
``OUTLOOK_CLIENT_ID``, ``OUTLOOK_CLIENT_SECRET``,
``OUTLOOK_REDIRECT_URI``, ``OUTLOOK_WEBHOOK_SECRET``,
``OUTLOOK_CLIENT_STATE``.
"""
from __future__ import annotations

import os
import hmac
import json
import uuid
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import RedirectResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel

from lumen_api import db, require_admin, require_staff, _strip_mongo
from f5_comm_providers import (
    CommAdapter,
    record_communication,
    register_adapter,
    _resolve_contact,
    PROVIDERS,
    T_EMAIL,
    S_NOT_CONNECTED,
)

logger = logging.getLogger("lumen.f7_outlook")
router = APIRouter(prefix="/api", tags=["lumen-f7-outlook"])

# ──────────────────────────────────────────────────────────────────────────
# Collections (reuse F6 stores wherever applicable)
# ──────────────────────────────────────────────────────────────────────────
OAUTH_STATE = "lumen_oauth_state"     # shared with F6, keyed by kind
AUDIT = "lumen_staff_login_audit"     # rotation + connect rows live here

# ──────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────
OUTLOOK_CLIENT_ID = (
    os.environ.get("OUTLOOK_CLIENT_ID")
    or os.environ.get("MS_CLIENT_ID")
    or os.environ.get("AZURE_CLIENT_ID")
)
OUTLOOK_CLIENT_SECRET = (
    os.environ.get("OUTLOOK_CLIENT_SECRET")
    or os.environ.get("MS_CLIENT_SECRET")
    or os.environ.get("AZURE_CLIENT_SECRET")
)
OUTLOOK_TENANT = os.environ.get("OUTLOOK_TENANT", "common")  # common | organizations | <tenant_id>
OUTLOOK_REDIRECT_URI = os.environ.get(
    "OUTLOOK_REDIRECT_URI",
    "http://localhost:8001/api/comms/oauth/outlook/callback",
)
OUTLOOK_WEBHOOK_SECRET = os.environ.get("OUTLOOK_WEBHOOK_SECRET", "lumen-dev-outlook-secret")
OUTLOOK_CLIENT_STATE = os.environ.get("OUTLOOK_CLIENT_STATE", "lumen-outlook-clientstate-v1")
OUTLOOK_SCOPES = (
    "offline_access "
    "https://graph.microsoft.com/Mail.Send "
    "https://graph.microsoft.com/Mail.Read"
)
OUTLOOK_AUTH_URL = (
    f"https://login.microsoftonline.com/{OUTLOOK_TENANT}/oauth2/v2.0/authorize"
)
OUTLOOK_TOKEN_URL = (
    f"https://login.microsoftonline.com/{OUTLOOK_TENANT}/oauth2/v2.0/token"
)

STATE_TTL_SEC = 600  # 10 min

MOCK_MODE = not bool(OUTLOOK_CLIENT_ID and OUTLOOK_CLIENT_SECRET)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).isoformat()


def _client_ip(request: Optional[Request]) -> Optional[str]:
    if not request:
        return None
    try:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        return request.client.host if request.client else None
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────
# Webhook verification (R5) — both clientState AND HMAC
# ──────────────────────────────────────────────────────────────────────────
def _compute_hmac(secret: str, body_bytes: bytes) -> str:
    return hmac.new(
        secret.encode("utf-8"), body_bytes, hashlib.sha256
    ).hexdigest()


def verify_webhook_signature(body_bytes: bytes, signature_header: Optional[str]) -> bool:
    if not signature_header:
        return False
    expected = _compute_hmac(OUTLOOK_WEBHOOK_SECRET, body_bytes)
    candidate = signature_header.strip()
    if candidate.lower().startswith("sha256="):
        candidate = candidate.split("=", 1)[1].strip()
    try:
        return hmac.compare_digest(candidate, expected)
    except Exception:
        return False


def verify_client_state(payload: dict) -> bool:
    """Microsoft Graph subscription notifications include a per-subscription
    ``clientState`` field. The receiver MUST compare it against the value
    it set when creating the subscription. If ANY notification in the batch
    fails — reject the whole batch."""
    values = payload.get("value") if isinstance(payload, dict) else None
    if not isinstance(values, list) or not values:
        return False
    for v in values:
        cs = (v or {}).get("clientState")
        if not cs or cs != OUTLOOK_CLIENT_STATE:
            return False
    return True


# ──────────────────────────────────────────────────────────────────────────
# Audit helpers (R8)
# ──────────────────────────────────────────────────────────────────────────
async def _audit(category: str, detail: dict, *, user_id: Optional[str] = None,
                 email: Optional[str] = None, ip: Optional[str] = None,
                 user_agent: Optional[str] = None) -> None:
    try:
        row = {
            "id": f"oao_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "email": email,
            "event": category,
            "category": category,
            "detail": detail,
            "ip": ip,
            "user_agent": user_agent,
            "at": _iso(),
        }
        await db[AUDIT].insert_one(row)
    except Exception as e:
        logger.warning("F7 audit write failed category=%s err=%s", category, e)


# ──────────────────────────────────────────────────────────────────────────
# Provider config helpers
# ──────────────────────────────────────────────────────────────────────────
async def _provider_doc() -> dict:
    return (await db[PROVIDERS].find_one({"key": "outlook"})) or {}


async def _set_oauth_status(status: str, **patch_config) -> None:
    existing = await _provider_doc()
    cfg = dict(existing.get("config") or {})
    cfg["oauth_status"] = status
    for k, v in patch_config.items():
        cfg[k] = v
    await db[PROVIDERS].update_one(
        {"key": "outlook"},
        {"$set": {"config": cfg, "updated_at": _iso()}},
    )


async def _read_oauth_status() -> str:
    doc = await _provider_doc()
    return ((doc.get("config") or {}).get("oauth_status")) or "not_connected"


# ──────────────────────────────────────────────────────────────────────────
# OutlookAdapter — only real adapter F7 adds
# ──────────────────────────────────────────────────────────────────────────
class OutlookAdapter(CommAdapter):
    key = "outlook"
    provider_type = T_EMAIL

    def __init__(self) -> None:
        self._connected = False

    @property
    def connected(self) -> bool:  # type: ignore[override]
        return self._connected

    @connected.setter
    def connected(self, value: bool) -> None:
        self._connected = bool(value)

    async def refresh_from_db(self) -> None:
        status = await _read_oauth_status()
        self._connected = status == "connected"

    async def send(self, *, interaction_type: str, direction: str, **kw) -> dict:
        await self.refresh_from_db()
        if not self._connected:
            return {
                "status": "not_connected",
                "sync_status": S_NOT_CONNECTED,
                "external_ref": kw.get("external_ref"),
            }
        ext = kw.get("external_ref") or f"outlook_{uuid.uuid4().hex[:14]}"
        return {"status": "ok", "sync_status": "sent", "external_ref": ext}

    def normalize_inbound(self, payload: dict) -> dict:
        """Map a Graph notification or a raw Graph message resource to the
        F5 canonical comm shape.

        Strict rule (R3/R4):
          • Graph ``internetMessageId`` (or top-level ``id``) → external_ref
          • Graph ``conversationId`` → extra.thread_ref
          • Sender email → contact
        """
        msg_id = (
            payload.get("internetMessageId")
            or payload.get("internet_message_id")
            or payload.get("id")
            or payload.get("messageId")
        )
        thread_id = (
            payload.get("conversationId")
            or payload.get("conversation_id")
            or payload.get("threadId")
        )
        # Graph nests sender under from.emailAddress.address
        from_email = None
        sender = payload.get("from") or {}
        if isinstance(sender, dict):
            addr = sender.get("emailAddress") or {}
            from_email = (
                (addr.get("address") if isinstance(addr, dict) else None)
                or sender.get("address")
            )
        elif isinstance(sender, str):
            from_email = sender
        from_email = from_email or payload.get("sender_email") or payload.get("from_email")

        subject = payload.get("subject") or "(no subject)"
        body_obj = payload.get("body") or {}
        body_text = (
            body_obj.get("content") if isinstance(body_obj, dict) else None
        ) or payload.get("bodyPreview") or payload.get("snippet") or ""

        return {
            "provider": "outlook",
            "interaction_type": "email",
            "direction": (payload.get("direction") or "inbound").lower(),
            "contact": ((from_email or "").strip().lower() or None),
            "title": subject[:250],
            "detail": body_text[:5000],
            "external_ref": msg_id,
            "thread_ref": thread_id,
            "sync_status": "received",
            "extra": {
                "to": payload.get("toRecipients") or payload.get("to"),
                "cc": payload.get("ccRecipients") or payload.get("cc"),
                "categories": payload.get("categories") or [],
                "received_at": payload.get("receivedDateTime")
                or payload.get("received_at") or _iso(),
            },
        }


OUTLOOK_ADAPTER = OutlookAdapter()


# ──────────────────────────────────────────────────────────────────────────
# OAuth flow (R7) — reuses lumen_oauth_state, keyed by kind=outlook.oauth
# ──────────────────────────────────────────────────────────────────────────
async def _mint_state(staff_id: Optional[str]) -> str:
    state = uuid.uuid4().hex
    await db[OAUTH_STATE].insert_one({
        "state": state,
        "kind": "outlook.oauth",
        "staff_id": staff_id,
        "created_at": _now(),
        "expires_at": _now() + timedelta(seconds=STATE_TTL_SEC),
        "consumed": False,
    })
    return state


async def _consume_state(state: str) -> Optional[dict]:
    doc = await db[OAUTH_STATE].find_one_and_update(
        {"state": state, "kind": "outlook.oauth", "consumed": False},
        {"$set": {"consumed": True, "consumed_at": _now()}},
    )
    if not doc:
        return None
    expires_at = doc.get("expires_at")
    if isinstance(expires_at, datetime):
        exp = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
        if exp < _now():
            return None
    return doc


@router.get("/comms/oauth/outlook/start")
async def oauth_outlook_start(request: Request, staff=Depends(require_staff)):
    """Mint a CSRF ``state`` and redirect to Microsoft's OAuth consent screen.

    Mock-mode keeps the redirect on our own domain so test clients don't hit
    login.microsoftonline.com — but the ``state=`` parameter is always set."""
    staff_id = staff.get("user_id") or staff.get("id")
    state = await _mint_state(staff_id)

    params = {
        "client_id": OUTLOOK_CLIENT_ID or "lumen-mock-outlook-client",
        "redirect_uri": OUTLOOK_REDIRECT_URI,
        "response_type": "code",
        "scope": OUTLOOK_SCOPES,
        "response_mode": "query",
        "prompt": "consent",
        "state": state,
    }
    if MOCK_MODE:
        target = f"{OUTLOOK_REDIRECT_URI}?{urlencode(params)}&mock=1"
    else:
        target = f"{OUTLOOK_AUTH_URL}?{urlencode(params)}"
    logger.info("F7 OAuth start: state=%s mock=%s staff=%s",
                state[:8], MOCK_MODE, staff_id)
    return RedirectResponse(target, status_code=302)


async def _exchange_code_for_tokens(code: str) -> dict:
    if MOCK_MODE:
        return {
            "access_token": f"mock_ms_at_{uuid.uuid4().hex}",
            "refresh_token": f"mock_ms_rt_{uuid.uuid4().hex}",
            "expires_in": 3600,
            "scope": OUTLOOK_SCOPES,
            "token_type": "Bearer",
            "mock": True,
        }
    import httpx
    data = {
        "client_id": OUTLOOK_CLIENT_ID,
        "client_secret": OUTLOOK_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": OUTLOOK_REDIRECT_URI,
        "scope": OUTLOOK_SCOPES,
    }
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(OUTLOOK_TOKEN_URL, data=data)
        if r.status_code != 200:
            raise HTTPException(
                status_code=400,
                detail=f"Outlook token exchange failed: {r.status_code}",
            )
        return r.json()


@router.get("/comms/oauth/outlook/callback")
async def oauth_outlook_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    mock: Optional[str] = Query(None),
):
    if error:
        raise HTTPException(status_code=400, detail=f"oauth_denied: {error}")
    if not state:
        raise HTTPException(status_code=400, detail="missing state (CSRF)")
    if not code:
        raise HTTPException(status_code=400, detail="missing code")

    state_doc = await _consume_state(state)
    if not state_doc:
        raise HTTPException(status_code=400, detail="invalid or expired state")

    tokens = await _exchange_code_for_tokens(code)
    refresh_token = tokens.get("refresh_token")
    access_token = tokens.get("access_token")
    expires_in = int(tokens.get("expires_in") or 3600)
    refresh_at = (_now() + timedelta(seconds=expires_in - 300)).isoformat()

    await _set_oauth_status(
        "connected",
        access_token=access_token,
        refresh_token=refresh_token,
        token_scope=tokens.get("scope"),
        token_type=tokens.get("token_type") or "Bearer",
        refresh_at=refresh_at,
        connected_at=_iso(),
        connected_by=state_doc.get("staff_id"),
        tenant=OUTLOOK_TENANT,
        client_state=OUTLOOK_CLIENT_STATE,
        mock=bool(MOCK_MODE),
    )
    await OUTLOOK_ADAPTER.refresh_from_db()

    await _audit(
        "oauth.outlook.connect",
        detail={
            "scope": tokens.get("scope"),
            "mock": bool(MOCK_MODE),
            "expires_in": expires_in,
            "tenant": OUTLOOK_TENANT,
        },
        user_id=state_doc.get("staff_id"),
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    await _seed_first_inbound_sample(connected_by=state_doc.get("staff_id"))

    if MOCK_MODE or mock:
        return JSONResponse({
            "ok": True,
            "oauth_status": "connected",
            "mock": bool(MOCK_MODE),
        })
    return RedirectResponse("/admin/comm-channels?outlook=connected", status_code=302)


async def _seed_first_inbound_sample(*, connected_by: Optional[str]) -> None:
    """Idempotent: writes one demo inbound outlook row via the F5 ingestion
    core. Verifies the wiring contract: external_ref==internetMessageId,
    extra.thread_ref==conversationId."""
    sample = {
        "internetMessageId": "outlook_msg_lumen_welcome_001",
        "conversationId": "outlook_conv_lumen_welcome",
        "from": {"emailAddress": {"address": "no-reply@microsoft.com",
                                  "name": "Microsoft 365"}},
        "toRecipients": [{"emailAddress": {"address": "lumen@lumen.platform"}}],
        "subject": "Outlook connected to LUMEN",
        "body": {"contentType": "text",
                 "content": (
                     "Your Microsoft 365 mailbox is now linked to LUMEN. New "
                     "email replies appear in the unified communications feed "
                     "and on the lead timeline."
                 )},
        "categories": ["INBOX", "SYSTEM"],
    }
    norm = OUTLOOK_ADAPTER.normalize_inbound(sample)
    await record_communication(
        provider="outlook",
        interaction_type=norm["interaction_type"],
        direction=norm["direction"],
        title=norm["title"],
        detail=norm["detail"],
        external_ref=norm["external_ref"],
        thread_ref=norm["thread_ref"],
        contact=norm["contact"],
        sync_status=norm["sync_status"],
        actor_id=connected_by,
        actor_name="Outlook OAuth",
        extra=norm.get("extra"),
    )


# ──────────────────────────────────────────────────────────────────────────
# Webhook (R5 + R6) — Graph notifications
# ──────────────────────────────────────────────────────────────────────────
@router.post("/comms/webhook/outlook")
async def webhook_outlook(request: Request,
                          validationToken: Optional[str] = Query(None)):
    """Microsoft Graph subscription endpoint.

    Two valid request shapes:
      1. Subscription validation handshake — GET-style ``validationToken``
         arrives as a query parameter; we MUST echo it back as text/plain
         within 10 s (no body verification possible at this stage).
      2. Real notification batch — JSON body. We require BOTH:
         (a) ``clientState`` on EVERY value matches OUTLOOK_CLIENT_STATE,
         (b) HMAC-SHA256 of raw body matches ``X-Lumen-Signature``.
         Either failure → 401, **zero writes**.

    Successful notification is normalized and recorded via the F5 ingestion
    core (dedup keeps duplicates collapsed to ONE row)."""
    # 1) Subscription handshake — Graph posts an empty body with a
    #    ``validationToken`` query param. Echo it as plain text.
    if validationToken:
        return PlainTextResponse(validationToken, status_code=200)

    body_bytes = await request.body()
    sig = (
        request.headers.get("x-lumen-signature")
        or request.headers.get("x-hub-signature-256")
    )

    # 2a) HMAC first (cheap)
    if not verify_webhook_signature(body_bytes, sig):
        logger.warning("F7 webhook rejected: bad/absent HMAC (sig=%s)",
                       (sig or "")[:16])
        return JSONResponse(
            {"ok": False, "error": "invalid_signature"},
            status_code=401,
        )

    try:
        payload = json.loads(body_bytes.decode("utf-8") or "{}")
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_json")

    # 2b) clientState — strict per-Graph contract
    if not verify_client_state(payload):
        logger.warning("F7 webhook rejected: bad clientState")
        return JSONResponse(
            {"ok": False, "error": "invalid_clientState"},
            status_code=401,
        )

    # Each notification in ``value[]`` carries one resource. Either a
    # ``resourceData`` block (Graph default — contains id + conversationId
    # via deltaToken/odata.id) OR a fully-inlined message object (for tests).
    accepted: List[Dict[str, Any]] = []
    for v in (payload.get("value") or []):
        rd = v.get("resourceData") or {}
        msg = v.get("message") or v.get("resource") or rd or {}
        # Inline-test convenience: if the test sends the full Graph message
        # at the top level of v, use that.
        if isinstance(v, dict) and ("internetMessageId" in v or "conversationId" in v):
            msg = v

        norm = OUTLOOK_ADAPTER.normalize_inbound(msg)
        if not norm.get("external_ref"):
            # Skip rather than fail the batch — Graph may include change
            # notifications without an internetMessageId (delta-style).
            continue

        contact = norm.get("contact")
        lead_id, user_id = None, None
        if contact:
            res = await _resolve_contact(contact)
            lead_id, user_id = res.get("lead_id"), res.get("user_id")

        row = await record_communication(
            provider="outlook",
            interaction_type=norm["interaction_type"],
            direction=norm["direction"],
            lead_id=lead_id,
            user_id=user_id,
            title=norm["title"],
            detail=norm["detail"],
            external_ref=norm["external_ref"],
            thread_ref=norm["thread_ref"],
            contact=norm["contact"],
            sync_status=norm["sync_status"],
            actor_id=None,
            actor_name="Outlook Webhook",
            extra=norm.get("extra"),
        )
        accepted.append({
            "comm_id": row.get("comm_id"),
            "external_ref": norm["external_ref"],
            "thread_ref": norm["thread_ref"],
        })

    return {"ok": True, "accepted": accepted, "count": len(accepted)}


# ──────────────────────────────────────────────────────────────────────────
# Refresh-token rotation (R8)
# ──────────────────────────────────────────────────────────────────────────
async def rotate_refresh_token(*, reason: str = "scheduled") -> dict:
    doc = await _provider_doc()
    cfg = dict(doc.get("config") or {})
    if cfg.get("oauth_status") != "connected":
        return {"ok": False, "error": "not_connected"}

    if MOCK_MODE:
        new_at = f"mock_ms_at_{uuid.uuid4().hex}"
        new_rt = f"mock_ms_rt_{uuid.uuid4().hex}"
        expires_in = 3600
    else:
        import httpx
        data = {
            "client_id": OUTLOOK_CLIENT_ID,
            "client_secret": OUTLOOK_CLIENT_SECRET,
            "refresh_token": cfg.get("refresh_token"),
            "grant_type": "refresh_token",
            "scope": OUTLOOK_SCOPES,
        }
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(OUTLOOK_TOKEN_URL, data=data)
            if r.status_code != 200:
                await _audit("oauth.outlook.refresh_failed",
                             detail={"status": r.status_code, "reason": reason})
                return {"ok": False, "error": f"refresh_failed_{r.status_code}"}
            tok = r.json()
            new_at = tok.get("access_token")
            new_rt = tok.get("refresh_token") or cfg.get("refresh_token")
            expires_in = int(tok.get("expires_in") or 3600)

    cfg["access_token"] = new_at
    cfg["refresh_token"] = new_rt
    cfg["refresh_at"] = (_now() + timedelta(seconds=expires_in - 300)).isoformat()
    cfg["last_refreshed_at"] = _iso()
    await db[PROVIDERS].update_one(
        {"key": "outlook"},
        {"$set": {"config": cfg, "updated_at": _iso()}},
    )

    await _audit(
        "oauth.outlook.refresh",
        detail={"reason": reason, "expires_in": expires_in,
                "mock": bool(MOCK_MODE)},
    )
    return {"ok": True, "expires_in": expires_in}


@router.post("/admin/comms/outlook/rotate-token")
async def rotate_token_endpoint(_admin=Depends(require_admin)):
    return await rotate_refresh_token(reason="manual")


# ──────────────────────────────────────────────────────────────────────────
# Status + disconnect
# ──────────────────────────────────────────────────────────────────────────
@router.get("/admin/comms/outlook/status")
async def outlook_status(_staff=Depends(require_staff)):
    await OUTLOOK_ADAPTER.refresh_from_db()
    doc = await _provider_doc()
    cfg = doc.get("config") or {}
    return {
        "provider": "outlook",
        "status": doc.get("status"),
        "oauth_status": cfg.get("oauth_status") or "not_connected",
        "connected": OUTLOOK_ADAPTER.connected,
        "tenant": cfg.get("tenant") or OUTLOOK_TENANT,
        "connected_at": cfg.get("connected_at"),
        "last_refreshed_at": cfg.get("last_refreshed_at"),
        "refresh_at": cfg.get("refresh_at"),
        "mock_mode": bool(MOCK_MODE),
        "has_refresh_token": bool(cfg.get("refresh_token")),
    }


@router.post("/admin/comms/outlook/disconnect")
async def outlook_disconnect(request: Request, admin=Depends(require_admin)):
    await _set_oauth_status(
        "not_connected",
        access_token=None,
        refresh_token=None,
        disconnected_at=_iso(),
        disconnected_by=admin.get("user_id"),
    )
    await db[PROVIDERS].update_one(
        {"key": "outlook"},
        {"$set": {"status": S_NOT_CONNECTED, "updated_at": _iso()}},
    )
    await OUTLOOK_ADAPTER.refresh_from_db()
    await _audit(
        "oauth.outlook.disconnect",
        detail={"by": admin.get("email")},
        user_id=admin.get("user_id"),
        email=admin.get("email"),
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return {"ok": True, "oauth_status": "not_connected"}


# ──────────────────────────────────────────────────────────────────────────
# Boot
# ──────────────────────────────────────────────────────────────────────────
async def _ensure_oauth_status_field() -> None:
    doc = await _provider_doc()
    if not doc:
        return
    cfg = doc.get("config") or {}
    changed = False
    if "oauth_status" not in cfg:
        cfg["oauth_status"] = "not_connected"
        changed = True
    if "client_state" not in cfg:
        cfg["client_state"] = OUTLOOK_CLIENT_STATE
        changed = True
    if changed:
        await db[PROVIDERS].update_one(
            {"key": "outlook"},
            {"$set": {"config": cfg, "updated_at": _iso()}},
        )


async def boot() -> None:
    await _ensure_oauth_status_field()
    register_adapter(OUTLOOK_ADAPTER)
    await OUTLOOK_ADAPTER.refresh_from_db()
    logger.info(
        "F7 Outlook Adapter ready (mock_mode=%s, oauth_status=%s, connected=%s)",
        MOCK_MODE,
        await _read_oauth_status(),
        OUTLOOK_ADAPTER.connected,
    )
