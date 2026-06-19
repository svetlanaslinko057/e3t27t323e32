"""
LUMEN — F3 Staff Security Center (Staff Sessions)
=================================================

Turns the M5 login journal into a real operational control center for staff.

Builds on what already exists:
  • `lumen_staff_login_audit`  — login_ok / login_fail / logout (ip + user_agent)
  • `user_sessions`            — canonical active-session store
  • `lumen_activity_identities`— F2 last_seen_at (real presence)
  • `lumen_staff_acl`          — privilege + scope helpers

Adds (locked scope 1a–5a):
  F3.1  Session enrichment  — ip, user_agent, device_hash, first_seen_at, last_seen_at
  F3.2  Online presence     — online (<5m) / away (5–30m) / offline (>30m) via F2 activity
  F3.3  Suspicious logins   — severity-tiered (failed burst, rapid IP, new device, IP change, concurrency)
  F3.4  Failed logins       — aggregation + brute-force flag
  F3.5  Force logout        — per-session + per-user; writes a force_logout audit row

Config (env-overridable):
  ONLINE_WINDOW_MIN = 5      AWAY_WINDOW_MIN = 30
  FAILED_BURST = 5 / 15 min  RAPID_IP_SWITCH_WINDOW = 60 min
  CONCURRENT_WARN = 3        CONCURRENT_HIGH = 5
"""
from __future__ import annotations

import os
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, Request, Query, HTTPException
from pydantic import BaseModel

from lumen_api import db, require_staff, _strip_mongo
from lumen_staff_acl import is_privileged, staff_uid

logger = logging.getLogger("lumen.staff_sessions")

router = APIRouter(prefix="/api/admin/staff/sessions", tags=["lumen-staff-sessions"])

AUDIT = "lumen_staff_login_audit"
SESSIONS = "user_sessions"
IDENTITIES = "lumen_activity_identities"

STAFF_ROLES = {"admin", "manager", "operator", "team_lead", "owner", "master_admin"}

ONLINE_WINDOW_MIN = int(os.environ.get("F3_ONLINE_WINDOW_MIN", "5"))
AWAY_WINDOW_MIN = int(os.environ.get("F3_AWAY_WINDOW_MIN", "30"))
FAILED_BURST = int(os.environ.get("F3_FAILED_BURST", "5"))
FAILED_BURST_WINDOW_MIN = int(os.environ.get("F3_FAILED_BURST_WINDOW_MIN", "15"))
RAPID_IP_WINDOW_MIN = int(os.environ.get("F3_RAPID_IP_WINDOW_MIN", "60"))
CONCURRENT_WARN = int(os.environ.get("F3_CONCURRENT_WARN", "3"))
CONCURRENT_HIGH = int(os.environ.get("F3_CONCURRENT_HIGH", "5"))

SEV_ORDER = {"low": 1, "medium": 2, "high": 3}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).isoformat()


def _parse(dt: Any) -> Optional[datetime]:
    if isinstance(dt, datetime):
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    if isinstance(dt, str):
        try:
            d = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    return None


def _is_staff_user(user: dict) -> bool:
    role = (user.get("role") or "").lower()
    roles = {str(r).lower() for r in (user.get("roles") or [])}
    return role in STAFF_ROLES or bool(roles & STAFF_ROLES)


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


def device_hash(user_agent: Optional[str], fingerprint: Optional[str] = None) -> Optional[str]:
    raw = f"{user_agent or ''}|{fingerprint or ''}".strip("|")
    if not raw:
        return None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _short_device(ua: Optional[str]) -> str:
    """Human-readable device label from a user-agent string."""
    if not ua:
        return "—"
    s = ua.lower()
    os_name = ("iPhone" if "iphone" in s else "iPad" if "ipad" in s else
               "Android" if "android" in s else "Mac" if "macintosh" in s or "mac os" in s else
               "Windows" if "windows" in s else "Linux" if "linux" in s else "Unknown")
    browser = ("Edge" if "edg/" in s else "Chrome" if "chrome" in s and "edg/" not in s else
               "Firefox" if "firefox" in s else "Safari" if "safari" in s and "chrome" not in s else "Browser")
    return f"{browser} · {os_name}"


def _presence(last_seen: Optional[datetime]) -> str:
    if not last_seen:
        return "offline"
    mins = (_now() - last_seen).total_seconds() / 60.0
    if mins <= ONLINE_WINDOW_MIN:
        return "online"
    if mins <= AWAY_WINDOW_MIN:
        return "away"
    return "offline"


# ===========================================================================
# F3.1 — session enrichment (called from login paths + lazy correlation)
# ===========================================================================
async def enrich_session_for_user(
    user_id: str, request: Optional[Request], *, device_fingerprint: Optional[str] = None,
) -> None:
    """Stamp ip/user_agent/device_hash/first_seen_at/last_seen_at onto the most
    recently created session for this user. Best-effort, never raises."""
    if not user_id:
        return
    try:
        sess = await db[SESSIONS].find_one({"user_id": user_id}, sort=[("created_at", -1)])
        if not sess:
            return
        ua = request.headers.get("user-agent") if request else None
        ip = _client_ip(request)
        now = _iso()
        patch = {
            "ip": ip,
            "user_agent": ua,
            "device_hash": device_hash(ua, device_fingerprint),
            "last_seen_at": now,
        }
        if not sess.get("first_seen_at"):
            patch["first_seen_at"] = sess.get("created_at") or now
        await db[SESSIONS].update_one({"_id": sess["_id"]}, {"$set": patch})
    except Exception as e:
        logger.warning("enrich_session_for_user failed uid=%s err=%s", user_id, e)


async def touch_session(session_token: Optional[str]) -> None:
    """Update last_seen_at on an active session (called from F2 activity track)."""
    if not session_token:
        return
    try:
        await db[SESSIONS].update_one(
            {"session_token": session_token}, {"$set": {"last_seen_at": _iso()}}
        )
    except Exception:
        pass


async def _audit_for_user(user_id: str, since: datetime) -> List[dict]:
    rows = []
    try:
        cur = db[AUDIT].find({"user_id": user_id, "event": "login_ok"}).sort("at", -1).limit(50)
        async for r in cur:
            rows.append(_strip_mongo(r))
    except Exception:
        pass
    return rows


async def _enrich_session_view(s: dict, audit_cache: Dict[str, List[dict]]) -> dict:
    """Build a UI session row, filling ip/device from audit when the session
    record itself is not yet enriched (legacy / 2FA / google paths)."""
    uid = s.get("user_id")
    ip = s.get("ip")
    ua = s.get("user_agent")
    dh = s.get("device_hash")
    if (not ip or not ua) and uid:
        if uid not in audit_cache:
            audit_cache[uid] = await _audit_for_user(uid, _now() - timedelta(days=30))
        created = _parse(s.get("created_at"))
        best = None
        for a in audit_cache[uid]:
            at = _parse(a.get("at"))
            if not at:
                continue
            # nearest login_ok at/just-before session creation
            if created is None or abs((at - created).total_seconds()) <= 120:
                best = a
                break
        if best is None and audit_cache[uid]:
            best = audit_cache[uid][0]
        if best:
            ip = ip or best.get("ip")
            ua = ua or best.get("user_agent")
            dh = dh or device_hash(best.get("user_agent"))
    return {
        "session_id": s.get("session_id"),
        "user_id": uid,
        "ip": ip,
        "user_agent": ua,
        "device": _short_device(ua),
        "device_hash": dh,
        "first_seen_at": s.get("first_seen_at") or s.get("created_at"),
        "last_seen_at": s.get("last_seen_at"),
        "created_at": s.get("created_at"),
        "expires_at": s.get("expires_at"),
    }


async def _active_staff_sessions(scope_uid: Optional[str]) -> List[dict]:
    """All non-expired sessions for staff users (optionally scoped to one uid)."""
    now = _now()
    out: List[dict] = []
    user_cache: Dict[str, dict] = {}
    audit_cache: Dict[str, List[dict]] = {}
    q: dict = {}
    if scope_uid:
        q["user_id"] = scope_uid
    try:
        cur = db[SESSIONS].find(q).sort("created_at", -1).limit(1000)
        async for s in cur:
            s = _strip_mongo(s)
            uid = s.get("user_id")
            if not uid:
                continue
            if uid not in user_cache:
                u = (await db.users.find_one({"user_id": uid})
                     or await db.users.find_one({"id": uid}))
                user_cache[uid] = _strip_mongo(u) if u else {}
            u = user_cache[uid]
            if not u or not _is_staff_user(u):
                continue
            exp = _parse(s.get("expires_at"))
            if exp and exp <= now:
                continue
            row = await _enrich_session_view(s, audit_cache)
            row["name"] = u.get("name") or u.get("full_name")
            row["email"] = u.get("email")
            row["role"] = u.get("role")
            out.append(row)
    except Exception as e:
        logger.warning("_active_staff_sessions failed: %s", e)
    return out


async def _last_seen_map(user_ids: List[str]) -> Dict[str, datetime]:
    """Best presence signal per user: max(F2 identity last_seen, session last_seen)."""
    out: Dict[str, datetime] = {}
    if not user_ids:
        return out
    try:
        async for ident in db[IDENTITIES].find(
            {"user_id": {"$in": user_ids}}, {"user_id": 1, "last_seen_at": 1}
        ):
            ls = _parse(ident.get("last_seen_at"))
            uid = ident.get("user_id")
            if uid and ls and (uid not in out or ls > out[uid]):
                out[uid] = ls
    except Exception:
        pass
    return out


# ===========================================================================
# Endpoints
# ===========================================================================
@router.get("/online")
async def online(user=Depends(require_staff)):
    """F3.2 — staff presence: online (<5m) / away / offline, with session counts."""
    scope = None if is_privileged(user) else staff_uid(user)
    sessions = await _active_staff_sessions(scope)
    by_user: Dict[str, dict] = {}
    for s in sessions:
        uid = s["user_id"]
        b = by_user.setdefault(uid, {
            "user_id": uid, "name": s.get("name"), "email": s.get("email"),
            "role": s.get("role"), "session_count": 0, "ips": set(), "devices": set(),
            "last_session_at": None,
        })
        b["session_count"] += 1
        if s.get("ip"):
            b["ips"].add(s["ip"])
        if s.get("device"):
            b["devices"].add(s["device"])
        ls = _parse(s.get("last_seen_at")) or _parse(s.get("created_at"))
        if ls and (b["last_session_at"] is None or ls > b["last_session_at"]):
            b["last_session_at"] = ls

    last_seen = await _last_seen_map(list(by_user.keys()))
    rows = []
    counts = {"online": 0, "away": 0, "offline": 0}
    for uid, b in by_user.items():
        ls = last_seen.get(uid)
        if b["last_session_at"] and (ls is None or b["last_session_at"] > ls):
            ls = b["last_session_at"]
        status = _presence(ls)
        counts[status] += 1
        rows.append({
            "user_id": uid,
            "name": b["name"],
            "email": b["email"],
            "role": b["role"],
            "status": status,
            "last_seen_at": _iso(ls) if ls else None,
            "session_count": b["session_count"],
            "distinct_ips": len(b["ips"]),
            "ips": sorted(b["ips"]),
            "devices": sorted(b["devices"]),
        })
    order = {"online": 0, "away": 1, "offline": 2}
    rows.sort(key=lambda r: (order.get(r["status"], 3), -(r["session_count"])))
    return {
        "online_window_min": ONLINE_WINDOW_MIN,
        "away_window_min": AWAY_WINDOW_MIN,
        "counts": counts,
        "staff": rows,
        "generated_at": _iso(),
    }


@router.get("/list")
async def list_sessions(user=Depends(require_staff)):
    """F3.1 — every active staff session, enriched with ip / device / timestamps."""
    scope = None if is_privileged(user) else staff_uid(user)
    sessions = await _active_staff_sessions(scope)
    last_seen = await _last_seen_map([s["user_id"] for s in sessions])
    for s in sessions:
        ls = _parse(s.get("last_seen_at")) or last_seen.get(s["user_id"])
        s["status"] = _presence(ls)
    return {"sessions": sessions, "count": len(sessions), "generated_at": _iso()}


@router.get("/suspicious")
async def suspicious(
    hours: int = Query(24, ge=1, le=168),
    user=Depends(require_staff),
):
    """F3.3 — severity-tiered suspicious-login detection."""
    privileged = is_privileged(user)
    me = staff_uid(user)
    since = _now() - timedelta(hours=hours)
    prior_cut = since  # history before window used for "new device / new ip"

    # pull recent audit
    recent: List[dict] = []
    try:
        cur = db[AUDIT].find({"at": {"$gte": _iso(since)}}).sort("at", 1).limit(5000)
        async for r in cur:
            recent.append(_strip_mongo(r))
    except Exception as e:
        logger.warning("suspicious audit fetch failed: %s", e)

    # group by user (login_ok) and by email (login_fail)
    ok_by_user: Dict[str, List[dict]] = {}
    fails_by_email: Dict[str, List[dict]] = {}
    for r in recent:
        ev = r.get("event")
        if ev == "login_ok" and r.get("user_id"):
            ok_by_user.setdefault(r["user_id"], []).append(r)
        elif ev == "login_fail":
            key = (r.get("email") or "").lower() or (r.get("ip") or "unknown")
            fails_by_email.setdefault(key, []).append(r)

    # historical IPs / devices (before window) for new-device / ip-changed
    hist_ip: Dict[str, set] = {}
    hist_dev: Dict[str, set] = {}
    try:
        cur = db[AUDIT].find(
            {"event": "login_ok", "at": {"$lt": _iso(prior_cut)}},
            {"user_id": 1, "ip": 1, "user_agent": 1},
        ).limit(20000)
        async for r in cur:
            uid = r.get("user_id")
            if not uid:
                continue
            if r.get("ip"):
                hist_ip.setdefault(uid, set()).add(r["ip"])
            dh = device_hash(r.get("user_agent"))
            if dh:
                hist_dev.setdefault(uid, set()).add(dh)
    except Exception:
        pass

    # active session counts per user
    sessions = await _active_staff_sessions(None if privileged else me)
    sess_count: Dict[str, int] = {}
    for s in sessions:
        sess_count[s["user_id"]] = sess_count.get(s["user_id"], 0) + 1

    findings: Dict[str, dict] = {}

    def add(uid_or_email: str, *, who: dict, signal: dict):
        f = findings.setdefault(uid_or_email, {
            "key": uid_or_email, **who, "signals": [],
        })
        f["signals"].append(signal)

    # 1. failed burst (HIGH) — >=FAILED_BURST within FAILED_BURST_WINDOW_MIN
    for key, rows in fails_by_email.items():
        ts = sorted(_parse(r.get("at")) for r in rows if _parse(r.get("at")))
        burst = False
        win = timedelta(minutes=FAILED_BURST_WINDOW_MIN)
        for i in range(len(ts)):
            j = i
            while j < len(ts) and ts[j] - ts[i] <= win:
                j += 1
            if j - i >= FAILED_BURST:
                burst = True
                break
        if burst:
            sample = rows[-1]
            add(f"fail::{key}", who={
                "user_id": sample.get("user_id"), "email": sample.get("email") or key,
                "name": sample.get("name"), "role": sample.get("role"),
            }, signal={
                "type": "failed_burst", "severity": "high",
                "detail": f"{len(rows)} невдалих спроб за {hours}год (≥{FAILED_BURST}/{FAILED_BURST_WINDOW_MIN}хв)",
                "count": len(rows), "ip": sample.get("ip"), "at": sample.get("at"),
            })

    # per-user signals
    for uid, rows in ok_by_user.items():
        who = {
            "user_id": uid, "email": rows[0].get("email"),
            "name": rows[0].get("name"), "role": rows[0].get("role"),
        }
        ts_ip = sorted(
            [(_parse(r.get("at")), r.get("ip")) for r in rows if _parse(r.get("at")) and r.get("ip")],
            key=lambda x: x[0],
        )
        # 2. rapid IP switch (HIGH) — >=2 distinct IPs within RAPID_IP_WINDOW_MIN
        win = timedelta(minutes=RAPID_IP_WINDOW_MIN)
        rapid = False
        for i in range(len(ts_ip)):
            ips = set()
            for j in range(i, len(ts_ip)):
                if ts_ip[j][0] - ts_ip[i][0] <= win:
                    ips.add(ts_ip[j][1])
                else:
                    break
            if len(ips) >= 2:
                rapid = True
                rapid_ips = ips
                break
        if rapid:
            add(uid, who=who, signal={
                "type": "rapid_ip_switch", "severity": "high",
                "detail": f"Вхід з {len(rapid_ips)} різних IP за {RAPID_IP_WINDOW_MIN}хв: {', '.join(list(rapid_ips)[:4])}",
                "at": rows[-1].get("at"),
            })

        # 4. new device (MEDIUM)
        win_devs = {device_hash(r.get("user_agent")) for r in rows if device_hash(r.get("user_agent"))}
        prev_devs = hist_dev.get(uid, set())
        new_devs = win_devs - prev_devs
        if prev_devs and new_devs:
            uas = {(_short_device(r.get("user_agent"))) for r in rows
                   if device_hash(r.get("user_agent")) in new_devs}
            add(uid, who=who, signal={
                "type": "new_device", "severity": "medium",
                "detail": f"Новий пристрій: {', '.join(list(uas)[:3])}",
                "at": rows[-1].get("at"),
            })

        # 5. ip changed (MEDIUM)
        win_ips = {r.get("ip") for r in rows if r.get("ip")}
        prev_ips = hist_ip.get(uid, set())
        new_ips = win_ips - prev_ips
        if prev_ips and new_ips and not rapid:
            add(uid, who=who, signal={
                "type": "ip_changed", "severity": "medium",
                "detail": f"Новий IP: {', '.join(list(new_ips)[:4])}",
                "at": rows[-1].get("at"),
            })

    # 3/6. concurrency (HIGH >=CONCURRENT_HIGH, LOW >=CONCURRENT_WARN)
    for uid, n in sess_count.items():
        if n >= CONCURRENT_HIGH:
            sev, label = "high", f"≥{CONCURRENT_HIGH}"
        elif n >= CONCURRENT_WARN:
            sev, label = "low", f"≥{CONCURRENT_WARN}"
        else:
            continue
        u = (await db.users.find_one({"user_id": uid}, {"name": 1, "email": 1, "role": 1})) or {}
        add(uid, who={"user_id": uid, "email": u.get("email"), "name": u.get("name"), "role": u.get("role")},
            signal={
                "type": "concurrent_sessions", "severity": sev,
                "detail": f"{n} одночасних активних сесій ({label})",
                "count": n, "at": _iso(),
            })

    rows_out = []
    for f in findings.values():
        if not privileged and f.get("user_id") != me:
            continue
        max_sev = max((SEV_ORDER.get(s["severity"], 0) for s in f["signals"]), default=0)
        f["max_severity"] = next((k for k, v in SEV_ORDER.items() if v == max_sev), "low")
        rows_out.append(f)
    rows_out.sort(key=lambda r: SEV_ORDER.get(r["max_severity"], 0), reverse=True)

    tally = {"high": 0, "medium": 0, "low": 0}
    for r in rows_out:
        tally[r["max_severity"]] = tally.get(r["max_severity"], 0) + 1
    return {
        "window_hours": hours,
        "thresholds": {
            "failed_burst": FAILED_BURST, "failed_burst_window_min": FAILED_BURST_WINDOW_MIN,
            "rapid_ip_window_min": RAPID_IP_WINDOW_MIN,
            "concurrent_warn": CONCURRENT_WARN, "concurrent_high": CONCURRENT_HIGH,
        },
        "tally": tally,
        "findings": rows_out,
        "generated_at": _iso(),
    }


@router.get("/failed-logins")
async def failed_logins(
    hours: int = Query(24, ge=1, le=720),
    user=Depends(require_staff),
):
    """F3.4 — failed-login feed + per-email aggregation with brute-force flag."""
    since = _now() - timedelta(hours=hours)
    rows: List[dict] = []
    try:
        cur = db[AUDIT].find(
            {"event": "login_fail", "at": {"$gte": _iso(since)}}
        ).sort("at", -1).limit(1000)
        async for r in cur:
            r = _strip_mongo(r)
            rows.append({
                "email": r.get("email"), "ip": r.get("ip"),
                "user_agent": r.get("user_agent"), "device": _short_device(r.get("user_agent")),
                "at": r.get("at"),
            })
    except Exception as e:
        logger.warning("failed_logins fetch failed: %s", e)

    agg: Dict[str, dict] = {}
    for r in rows:
        key = (r.get("email") or r.get("ip") or "unknown").lower()
        a = agg.setdefault(key, {"email": r.get("email"), "attempts": 0, "ips": set(), "last_at": None})
        a["attempts"] += 1
        if r.get("ip"):
            a["ips"].add(r["ip"])
        at = _parse(r.get("at"))
        if at and (a["last_at"] is None or at > a["last_at"]):
            a["last_at"] = at
    agg_rows = []
    for key, a in agg.items():
        agg_rows.append({
            "email": a["email"] or key,
            "attempts": a["attempts"],
            "distinct_ips": len(a["ips"]),
            "ips": sorted(a["ips"]),
            "brute_force": a["attempts"] >= FAILED_BURST,
            "last_at": _iso(a["last_at"]) if a["last_at"] else None,
        })
    agg_rows.sort(key=lambda r: r["attempts"], reverse=True)
    return {
        "window_hours": hours,
        "total_failures": len(rows),
        "by_target": agg_rows,
        "recent": rows[:200],
        "generated_at": _iso(),
    }


# ---------------------------------------------------------------------------
# F3.5 — force logout
# ---------------------------------------------------------------------------
class RevokeBody(BaseModel):
    reason: Optional[str] = None


async def _write_force_logout_audit(actor: dict, target: dict, count: int, reason: Optional[str], scope: str):
    import uuid as _uuid
    try:
        await db[AUDIT].insert_one({
            "id": f"slog_{_uuid.uuid4().hex[:12]}",
            "user_id": target.get("user_id"),
            "email": target.get("email"),
            "name": target.get("name"),
            "role": target.get("role"),
            "event": "force_logout",
            "scope": scope,
            "sessions_revoked": count,
            "reason": (reason or "").strip()[:300] or None,
            "actor_id": actor.get("user_id") or actor.get("id"),
            "actor_email": actor.get("email"),
            "at": _iso(),
        })
    except Exception as e:
        logger.warning("force_logout audit failed: %s", e)


def _require_privileged(user: dict):
    if not is_privileged(user):
        raise HTTPException(status_code=403, detail="Лише привілейований адміністратор може завершувати сесії")


async def _drop_sessions(query: dict) -> int:
    total = 0
    for coll in (SESSIONS, "sessions", "auth_sessions"):
        try:
            res = await db[coll].delete_many(query)
            total += res.deleted_count
        except Exception:
            pass
    return total


@router.post("/{session_id}/revoke")
async def revoke_session(session_id: str, body: RevokeBody, user=Depends(require_staff)):
    """Force-logout a single session."""
    _require_privileged(user)
    sess = await db[SESSIONS].find_one({"session_id": session_id})
    if not sess:
        raise HTTPException(status_code=404, detail="Сесію не знайдено")
    target_uid = sess.get("user_id")
    target = (await db.users.find_one({"user_id": target_uid},
                                      {"user_id": 1, "email": 1, "name": 1, "role": 1})) or {"user_id": target_uid}
    token = sess.get("session_token")
    count = await _drop_sessions({"$or": [{"session_id": session_id}, {"session_token": token}, {"token": token}]})
    await _write_force_logout_audit(user, _strip_mongo(target), count, body.reason, scope="session")
    return {"ok": True, "revoked": count, "session_id": session_id, "user_id": target_uid}


@router.post("/user/{user_id}/revoke-all")
async def revoke_all(user_id: str, body: RevokeBody, user=Depends(require_staff)):
    """Force-logout every active session of a user."""
    _require_privileged(user)
    target = (await db.users.find_one({"user_id": user_id},
                                      {"user_id": 1, "email": 1, "name": 1, "role": 1})) or {"user_id": user_id}
    count = await _drop_sessions({"user_id": user_id})
    await _write_force_logout_audit(user, _strip_mongo(target), count, body.reason, scope="user")
    return {"ok": True, "revoked": count, "user_id": user_id}


# ---------------------------------------------------------------------------
# indexes
# ---------------------------------------------------------------------------
async def ensure_indexes(database=None):
    d = database if database is not None else db
    try:
        await d[SESSIONS].create_index("user_id")
        await d[SESSIONS].create_index("session_id")
        await d[SESSIONS].create_index("session_token")
        await d[AUDIT].create_index([("event", 1), ("at", -1)])
        logger.info("F3 staff-sessions indexes ensured")
    except Exception as e:
        logger.warning("F3 ensure_indexes warn: %s", e)
