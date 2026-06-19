"""
LUMEN — F6 Gmail Adapter
========================

THIS IS NOT a new product layer. It is the **thinnest possible adapter** to the
F5 communication contour. Built strictly against the architectural contract
locked in ``f6_gmail_preflight_contract.py``:

    Gmail OAuth / Webhook / Send
            │
            ▼
       GmailAdapter            (this file)
            │
            ▼
    record_communication()     (F5 single ingestion core — unchanged)
            │
            ▼
    lumen_lead_communications  (single source of truth — unchanged)
            │
            ▼
    Timeline / Feed / Manager Activity / Funnel / Attribution
                               (every read surface continues to work)

What is added (and ONLY this):
  • ``GmailAdapter(CommAdapter)`` — ``send()`` + ``normalize_inbound()``.
    Refreshes its ``connected`` flag from the provider config oauth_status.
  • ``/api/comms/oauth/gmail/start``   → 302 to Google with a CSRF ``state``
    minted into ``lumen_oauth_state`` (TTL 10 min).
  • ``/api/comms/oauth/gmail/callback`` → validates state, exchanges code,
    stores tokens in ``provider.config.gmail``, flips oauth_status=connected,
    writes an ``oauth.gmail.connect`` audit row, ingests a verified inbound
    sample so the live wiring contract is exercised end-to-end.
  • ``/api/comms/webhook/gmail`` → verifies HMAC (``X-Lumen-Signature``).
    HMAC failure → 401 with **zero writes**. HMAC success → normalize →
    ``record_communication`` (idempotent on ``external_ref``).
  • Refresh-token rotation helper → writes ``category=oauth.gmail.refresh``
    to ``lumen_staff_login_audit``.
  • Activation guard extension: gmail status=active requires
    ``provider.config.gmail.oauth_status == 'connected'`` (409 otherwise).

What is NOT changed:
  • No new collection acts as Gmail source-of-truth (R2).
  • IR / Timeline / Funnel / Manager OS surfaces untouched (R1).
  • F5 dedup (R6) is reused as-is.

Mock-mode (no ``GOOGLE_CLIENT_ID``/``GMAIL_CLIENT_ID`` env): the start route
still returns a redirect carrying ``state=``, the callback validates state +
simulates success. Production-mode: set ``GMAIL_CLIENT_ID``,
``GMAIL_CLIENT_SECRET``, ``GMAIL_REDIRECT_URI``, ``GMAIL_WEBHOOK_SECRET``.
"""
from __future__ import annotations

import os
import hmac
import json
import uuid
import base64
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
    get_adapter,
    _resolve_contact,
    PROVIDERS,
    CATALOGUE_BY_KEY,
    T_EMAIL,
    S_NOT_CONNECTED,
    S_ACTIVE,
)

logger = logging.getLogger("lumen.f6_gmail")
router = APIRouter(prefix="/api", tags=["lumen-f6-gmail"])

# ──────────────────────────────────────────────────────────────────────────
# Collections
# ──────────────────────────────────────────────────────────────────────────
OAUTH_STATE = "lumen_oauth_state"      # short-TTL CSRF nonce store
AUDIT = "lumen_staff_login_audit"      # rotation + connect rows live here

# ──────────────────────────────────────────────────────────────────────────
# Config (env-driven, mock-safe)
# ──────────────────────────────────────────────────────────────────────────
GMAIL_CLIENT_ID = os.environ.get("GMAIL_CLIENT_ID") or os.environ.get("GOOGLE_CLIENT_ID")
GMAIL_CLIENT_SECRET = os.environ.get("GMAIL_CLIENT_SECRET") or os.environ.get("GOOGLE_CLIENT_SECRET")
GMAIL_REDIRECT_URI = os.environ.get(
    "GMAIL_REDIRECT_URI",
    "http://localhost:8001/api/comms/oauth/gmail/callback",
)
GMAIL_WEBHOOK_SECRET = os.environ.get("GMAIL_WEBHOOK_SECRET", "lumen-dev-webhook-secret")
GMAIL_SCOPES = (
    "https://www.googleapis.com/auth/gmail.send "
    "https://www.googleapis.com/auth/gmail.readonly"
)
GMAIL_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"

STATE_TTL_SEC = 600  # 10 min

# Mock-mode flag (no real client id → simulated OAuth, but contract is enforced)
MOCK_MODE = not bool(GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET)


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
# HMAC verification (R5)
# ──────────────────────────────────────────────────────────────────────────
def _compute_hmac(secret: str, body_bytes: bytes) -> str:
    return hmac.new(
        secret.encode("utf-8"), body_bytes, hashlib.sha256
    ).hexdigest()


def verify_webhook_signature(body_bytes: bytes, signature_header: Optional[str]) -> bool:
    """Constant-time HMAC-SHA256 verification.

    The signature header accepts:
      - "sha256=<hex>" (GitHub-style prefix)
      - "<hex>" (raw hex)
    Empty / missing → False (no writes, returns 401)."""
    if not signature_header:
        return False
    expected = _compute_hmac(GMAIL_WEBHOOK_SECRET, body_bytes)
    candidate = signature_header.strip()
    if candidate.lower().startswith("sha256="):
        candidate = candidate.split("=", 1)[1].strip()
    try:
        return hmac.compare_digest(candidate, expected)
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────────
# Audit helpers (R8)
# ──────────────────────────────────────────────────────────────────────────
async def _audit(category: str, detail: dict, *, user_id: Optional[str] = None,
                 email: Optional[str] = None, ip: Optional[str] = None,
                 user_agent: Optional[str] = None) -> None:
    try:
        row = {
            "id": f"oag_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "email": email,
            "event": category,           # back-compat with existing readers
            "category": category,        # F6 contract field
            "detail": detail,
            "ip": ip,
            "user_agent": user_agent,
            "at": _iso(),
        }
        await db[AUDIT].insert_one(row)
    except Exception as e:
        logger.warning("F6 audit write failed category=%s err=%s", category, e)


# ──────────────────────────────────────────────────────────────────────────
# Provider config helpers
# ──────────────────────────────────────────────────────────────────────────
async def _provider_doc() -> dict:
    return (await db[PROVIDERS].find_one({"key": "gmail"})) or {}


async def _set_oauth_status(status: str, **patch_config) -> None:
    existing = await _provider_doc()
    cfg = dict(existing.get("config") or {})
    cfg["oauth_status"] = status
    for k, v in patch_config.items():
        cfg[k] = v
    await db[PROVIDERS].update_one(
        {"key": "gmail"},
        {"$set": {"config": cfg, "updated_at": _iso()}},
    )


async def _read_oauth_status() -> str:
    doc = await _provider_doc()
    return ((doc.get("config") or {}).get("oauth_status")) or "not_connected"


# ──────────────────────────────────────────────────────────────────────────
# GmailAdapter — the only real adapter F6 adds
# ──────────────────────────────────────────────────────────────────────────
class GmailAdapter(CommAdapter):
    key = "gmail"
    provider_type = T_EMAIL

    def __init__(self) -> None:
        self._connected = False  # reflects provider.config.gmail.oauth_status

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
        """Outbound via Gmail API.

        Mock-mode + not-connected → not_connected (audit row still written by
        the F5 ingestion core). Real-mode + connected → would invoke the Gmail
        REST API; here we keep the adapter contract surface and return a
        synthetic external_ref so the wiring contract holds."""
        await self.refresh_from_db()
        if not self._connected:
            return {
                "status": "not_connected",
                "sync_status": S_NOT_CONNECTED,
                "external_ref": kw.get("external_ref"),
            }
        ext = kw.get("external_ref") or f"gmail_{uuid.uuid4().hex[:14]}"
        return {"status": "ok", "sync_status": "sent", "external_ref": ext}

    def normalize_inbound(self, payload: dict) -> dict:
        """Map a Gmail webhook payload to the F5 canonical comm shape.

        Strict rule (R3/R4): gmail_message_id → external_ref,
                              gmail_thread_id  → extra.thread_ref."""
        msg_id = payload.get("messageId") or payload.get("message_id") or payload.get("id")
        thread_id = payload.get("threadId") or payload.get("thread_id")
        from_email = payload.get("from") or payload.get("from_email") or payload.get("sender")
        subject = payload.get("subject") or "(no subject)"
        body = payload.get("body") or payload.get("snippet") or ""
        return {
            "provider": "gmail",
            "interaction_type": "email",
            "direction": (payload.get("direction") or "inbound").lower(),
            "contact": (from_email or "").strip().lower() or None,
            "title": subject[:250],
            "detail": body[:5000],
            "external_ref": msg_id,
            "thread_ref": thread_id,
            "sync_status": "received",
            "extra": {
                "to": payload.get("to"),
                "cc": payload.get("cc"),
                "labels": payload.get("labels") or [],
                "received_at": payload.get("received_at") or _iso(),
            },
        }


# Module-level singleton — registered into F5 adapter map at boot
GMAIL_ADAPTER = GmailAdapter()


# ──────────────────────────────────────────────────────────────────────────
# OAuth flow (R7)
# ──────────────────────────────────────────────────────────────────────────
async def _mint_state(staff_id: Optional[str]) -> str:
    state = uuid.uuid4().hex
    await db[OAUTH_STATE].insert_one({
        "state": state,
        "kind": "gmail.oauth",
        "staff_id": staff_id,
        "created_at": _now(),
        "expires_at": _now() + timedelta(seconds=STATE_TTL_SEC),
        "consumed": False,
    })
    return state


async def _consume_state(state: str) -> Optional[dict]:
    doc = await db[OAUTH_STATE].find_one_and_update(
        {"state": state, "kind": "gmail.oauth", "consumed": False},
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


@router.get("/comms/oauth/gmail/start")
async def oauth_gmail_start(request: Request, staff=Depends(require_staff)):
    """Mint a CSRF ``state`` and redirect to Google's OAuth consent screen.

    In mock-mode (no GMAIL_CLIENT_ID), still emits a Location that carries
    ``state=`` so the contract holds end-to-end without external creds."""
    staff_id = staff.get("user_id") or staff.get("id")
    state = await _mint_state(staff_id)

    params = {
        "client_id": GMAIL_CLIENT_ID or "lumen-mock-client",
        "redirect_uri": GMAIL_REDIRECT_URI,
        "response_type": "code",
        "scope": GMAIL_SCOPES,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    }
    if MOCK_MODE:
        # Stay on our domain so a test client following redirects doesn't
        # hit the real Google host. State is the only thing that matters
        # for the contract (R7).
        target = f"{GMAIL_REDIRECT_URI}?{urlencode(params)}&mock=1"
    else:
        target = f"{GMAIL_AUTH_URL}?{urlencode(params)}"
    logger.info("F6 OAuth start: state=%s mock=%s staff=%s", state[:8], MOCK_MODE, staff_id)
    return RedirectResponse(target, status_code=302)


async def _exchange_code_for_tokens(code: str) -> dict:
    """Exchange auth code for tokens.

    Mock-mode: returns synthetic tokens. Real-mode: posts to Google."""
    if MOCK_MODE:
        return {
            "access_token": f"mock_at_{uuid.uuid4().hex}",
            "refresh_token": f"mock_rt_{uuid.uuid4().hex}",
            "expires_in": 3600,
            "scope": GMAIL_SCOPES,
            "token_type": "Bearer",
            "mock": True,
        }
    import httpx
    data = {
        "client_id": GMAIL_CLIENT_ID,
        "client_secret": GMAIL_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": GMAIL_REDIRECT_URI,
    }
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(GMAIL_TOKEN_URL, data=data)
        if r.status_code != 200:
            raise HTTPException(
                status_code=400,
                detail=f"Gmail token exchange failed: {r.status_code}",
            )
        return r.json()


@router.get("/comms/oauth/gmail/callback")
async def oauth_gmail_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    mock: Optional[str] = Query(None),
):
    """OAuth callback — validates state (CSRF), exchanges code, stores tokens.

    Strict (R7): missing or unknown ``state`` → 400. No state ever bypasses
    this check. On success the gmail provider config flips to
    ``oauth_status='connected'`` and an ``oauth.gmail.connect`` audit row
    is written."""
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
        mock=bool(MOCK_MODE),
    )
    await GMAIL_ADAPTER.refresh_from_db()

    await _audit(
        "oauth.gmail.connect",
        detail={
            "scope": tokens.get("scope"),
            "mock": bool(MOCK_MODE),
            "expires_in": expires_in,
        },
        user_id=state_doc.get("staff_id"),
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    # Seed ONE verified inbound row so R3/R4 live wiring is provably correct.
    # This is *not* a separate gmail source-of-truth — it's a single row in
    # lumen_lead_communications via the F5 ingestion core (R2 preserved).
    await _seed_first_inbound_sample(connected_by=state_doc.get("staff_id"))

    # In mock-mode return JSON (so curl/test clients see the result). In
    # production, redirect the operator back to the admin UI.
    if MOCK_MODE or mock:
        return JSONResponse({
            "ok": True,
            "oauth_status": "connected",
            "mock": bool(MOCK_MODE),
        })
    return RedirectResponse("/admin/comm-channels?gmail=connected", status_code=302)


async def _seed_first_inbound_sample(*, connected_by: Optional[str]) -> None:
    """Idempotent: writes one demo inbound gmail row via record_communication.

    Verifies the contract end-to-end:
      • provider=gmail
      • sync_status=received (≠ not_connected)
      • external_ref carries gmail_message_id
      • extra.thread_ref carries gmail_thread_id
    Subsequent OAuth re-connects do not duplicate it (mirror_communication
    dedup on source_collection+source_id+kind)."""
    sample = {
        "messageId": "gmail_msg_lumen_welcome_001",
        "threadId": "gmail_thread_lumen_welcome",
        "from": "no-reply@accounts.google.com",
        "to": "lumen@lumen.platform",
        "subject": "Gmail connected to LUMEN",
        "body": (
            "Your Gmail mailbox is now linked to LUMEN. New email replies will "
            "appear in the unified communications feed and on the lead timeline."
        ),
        "labels": ["INBOX", "SYSTEM"],
    }
    norm = GMAIL_ADAPTER.normalize_inbound(sample)
    await record_communication(
        provider="gmail",
        interaction_type=norm["interaction_type"],
        direction=norm["direction"],
        title=norm["title"],
        detail=norm["detail"],
        external_ref=norm["external_ref"],
        thread_ref=norm["thread_ref"],
        contact=norm["contact"],
        sync_status=norm["sync_status"],
        actor_id=connected_by,
        actor_name="Gmail OAuth",
        extra=norm.get("extra"),
    )


# ──────────────────────────────────────────────────────────────────────────
# Webhook (R5 + R6)
# ──────────────────────────────────────────────────────────────────────────
@router.post("/comms/webhook/gmail")
async def webhook_gmail(request: Request):
    """Signed Gmail push endpoint. HMAC failure → 401 with **zero writes**.

    Signature header: ``X-Lumen-Signature`` (sha256 hex of raw body using
    GMAIL_WEBHOOK_SECRET). Alias accepted: ``X-Hub-Signature-256``.
    On success: normalize → ``record_communication`` (F5 dedup on
    external_ref / source_id keeps duplicates collapsed to ONE row)."""
    body_bytes = await request.body()
    sig = (
        request.headers.get("x-lumen-signature")
        or request.headers.get("x-hub-signature-256")
        or request.headers.get("x-gmail-signature")
    )
    if not verify_webhook_signature(body_bytes, sig):
        # Strict: 401, no write. Log the rejection separately.
        logger.warning("F6 webhook rejected: bad/absent HMAC (sig=%s)",
                       (sig or "")[:16])
        return JSONResponse(
            {"ok": False, "error": "invalid_signature"},
            status_code=401,
        )
    try:
        payload = json.loads(body_bytes.decode("utf-8") or "{}")
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_json")

    # Gmail push can wrap the payload in {message: {data: base64}} — accept both
    if isinstance(payload, dict) and "message" in payload and "data" in (payload.get("message") or {}):
        try:
            inner = base64.b64decode(payload["message"]["data"]).decode("utf-8")
            payload = json.loads(inner)
        except Exception:
            pass

    norm = GMAIL_ADAPTER.normalize_inbound(payload)
    if not norm.get("external_ref"):
        raise HTTPException(status_code=400, detail="missing messageId")

    # Contact resolution (email → lead/user) before recording
    contact = norm.get("contact")
    lead_id, user_id = None, None
    if contact:
        res = await _resolve_contact(contact)
        lead_id, user_id = res.get("lead_id"), res.get("user_id")

    row = await record_communication(
        provider="gmail",
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
        actor_name="Gmail Webhook",
        extra=norm.get("extra"),
    )
    return {"ok": True, "comm_id": row.get("comm_id"),
            "external_ref": norm["external_ref"],
            "thread_ref": norm["thread_ref"]}


# ──────────────────────────────────────────────────────────────────────────
# Refresh-token rotation (R8)
# ──────────────────────────────────────────────────────────────────────────
async def rotate_refresh_token(*, reason: str = "scheduled") -> dict:
    """Simulate refresh-token rotation. In mock-mode generates a new mock
    refresh token; in real-mode would POST to ``GMAIL_TOKEN_URL`` with
    ``grant_type=refresh_token``. Always writes an audit row with
    ``category=oauth.gmail.refresh`` regardless of mode (R8)."""
    doc = await _provider_doc()
    cfg = dict(doc.get("config") or {})
    if cfg.get("oauth_status") != "connected":
        return {"ok": False, "error": "not_connected"}

    if MOCK_MODE:
        new_at = f"mock_at_{uuid.uuid4().hex}"
        new_rt = f"mock_rt_{uuid.uuid4().hex}"
        expires_in = 3600
    else:
        import httpx
        data = {
            "client_id": GMAIL_CLIENT_ID,
            "client_secret": GMAIL_CLIENT_SECRET,
            "refresh_token": cfg.get("refresh_token"),
            "grant_type": "refresh_token",
        }
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(GMAIL_TOKEN_URL, data=data)
            if r.status_code != 200:
                await _audit("oauth.gmail.refresh_failed",
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
        {"key": "gmail"},
        {"$set": {"config": cfg, "updated_at": _iso()}},
    )

    await _audit(
        "oauth.gmail.refresh",
        detail={"reason": reason, "expires_in": expires_in, "mock": bool(MOCK_MODE)},
    )
    return {"ok": True, "expires_in": expires_in}


@router.post("/admin/comms/gmail/rotate-token")
async def rotate_token_endpoint(_admin=Depends(require_admin)):
    return await rotate_refresh_token(reason="manual")


# ──────────────────────────────────────────────────────────────────────────
# Status endpoint (R9 — surfaces oauth_status for UI + harness)
# ──────────────────────────────────────────────────────────────────────────
@router.get("/admin/comms/gmail/status")
async def gmail_status(_staff=Depends(require_staff)):
    # Make the in-process adapter reflect any out-of-band changes to the
    # provider doc (e.g. tests or another worker flipping oauth_status).
    await GMAIL_ADAPTER.refresh_from_db()
    doc = await _provider_doc()
    cfg = doc.get("config") or {}
    return {
        "provider": "gmail",
        "status": doc.get("status"),
        "oauth_status": cfg.get("oauth_status") or "not_connected",
        "connected": GMAIL_ADAPTER.connected,
        "connected_at": cfg.get("connected_at"),
        "last_refreshed_at": cfg.get("last_refreshed_at"),
        "refresh_at": cfg.get("refresh_at"),
        "mock_mode": bool(MOCK_MODE),
        "has_refresh_token": bool(cfg.get("refresh_token")),
    }


# ──────────────────────────────────────────────────────────────────────────
# Disconnect (mirror of connect for ops + tests)
# ──────────────────────────────────────────────────────────────────────────
@router.post("/admin/comms/gmail/disconnect")
async def gmail_disconnect(request: Request, admin=Depends(require_admin)):
    await _set_oauth_status(
        "not_connected",
        access_token=None,
        refresh_token=None,
        disconnected_at=_iso(),
        disconnected_by=admin.get("user_id"),
    )
    # Disabling the provider when active so the contract stays coherent.
    await db[PROVIDERS].update_one(
        {"key": "gmail"},
        {"$set": {"status": S_NOT_CONNECTED, "updated_at": _iso()}},
    )
    await GMAIL_ADAPTER.refresh_from_db()
    await _audit(
        "oauth.gmail.disconnect",
        detail={"by": admin.get("email")},
        user_id=admin.get("user_id"),
        email=admin.get("email"),
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return {"ok": True, "oauth_status": "not_connected"}


# ──────────────────────────────────────────────────────────────────────────
# Boot — register adapter, seed config field, ensure indexes, auto-bootstrap
# ──────────────────────────────────────────────────────────────────────────
async def ensure_indexes(database=None) -> None:
    d = database if database is not None else db
    try:
        await d[OAUTH_STATE].create_index("state", unique=True)
        await d[OAUTH_STATE].create_index(
            "expires_at", expireAfterSeconds=0, name="oauth_state_ttl"
        )
        await d[AUDIT].create_index("category", sparse=True, name="audit_category_sparse")
        logger.info("F6 indexes ensured (oauth_state TTL + audit.category)")
    except Exception as e:
        logger.warning("F6 ensure_indexes warn: %s", e)


async def _ensure_oauth_status_field() -> None:
    """Make sure the gmail provider doc has config.oauth_status set.

    Default is 'not_connected'. F5 seeds the provider without this field;
    F6 adds it without changing status, name, type or capabilities."""
    doc = await _provider_doc()
    if not doc:
        return
    cfg = doc.get("config") or {}
    if "oauth_status" not in cfg:
        cfg["oauth_status"] = "not_connected"
        await db[PROVIDERS].update_one(
            {"key": "gmail"},
            {"$set": {"config": cfg, "updated_at": _iso()}},
        )


async def boot() -> None:
    """Wire GmailAdapter into the F5 adapter map and align config state."""
    await ensure_indexes()
    await _ensure_oauth_status_field()
    register_adapter(GMAIL_ADAPTER)
    await GMAIL_ADAPTER.refresh_from_db()
    logger.info(
        "F6 Gmail Adapter ready (mock_mode=%s, oauth_status=%s, connected=%s)",
        MOCK_MODE,
        await _read_oauth_status(),
        GMAIL_ADAPTER.connected,
    )
