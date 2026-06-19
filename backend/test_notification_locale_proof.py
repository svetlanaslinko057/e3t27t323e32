"""
NOTIFICATION LOCALE PROOF
-------------------------
Verifies the LUMEN notification-locale policy (locked 2026-06-15):

  • admin / manager / owner  → always UK regardless of users.language
  • investor / qualified / institutional → users.language preference (default UK)
  • Legacy Atlas demo seed ("Module delivered" / "Acme Analytics" / "INV-1042")
    is wiped from db.notifications on startup.
  • The /api/notifications bell endpoint returns rows in the recipient's locale.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import uuid
from datetime import datetime, timezone

import bcrypt
import httpx
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

BASE = "http://localhost:8001"
_db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


# ────────────────────────────────────────────────────────────────────────────
async def _ensure_user(email: str, role: str, *, language: str | None = None) -> str:
    u = await _db.users.find_one({"email": email})
    if u:
        uid = u.get("user_id") or u.get("id")
        upd = {"role": role, "roles": [role]}
        if language is not None:
            upd["language"] = language
        else:
            upd["language"] = ""
        await _db.users.update_one({"user_id": uid}, {"$set": upd})
        return uid
    uid = f"user_{uuid.uuid4().hex[:12]}"
    pw_hash = bcrypt.hashpw(b"locale-test-123", bcrypt.gensalt()).decode()
    await _db.users.insert_one({
        "user_id": uid, "id": uid, "email": email,
        "name": email.split("@")[0], "role": role, "roles": [role],
        "level": "junior", "skills": [], "active_load": 0, "states": [],
        "active_context": None, "rating": 5.0, "completed_tasks": 0,
        "password_hash": pw_hash, "picture": None,
        "language": language or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return uid


async def _admin_token() -> str:
    """Login admin@atlas.dev via session_token cookie."""
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{BASE}/api/auth/login",
                          json={"email": "admin@atlas.dev", "password": "admin123"})
        if r.status_code != 200:
            raise RuntimeError(f"admin login failed: {r.status_code}")
        token = r.cookies.get("session_token") or ""
        if not token:
            m = re.search(r"session_token=([^;]+)", r.headers.get("set-cookie", ""))
            token = m.group(1) if m else ""
        return token


async def _user_token(email: str) -> str:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{BASE}/api/auth/login",
                          json={"email": email, "password": "locale-test-123"})
        if r.status_code != 200:
            raise RuntimeError(f"user login failed: {r.status_code} {r.text[:80]}")
        token = r.cookies.get("session_token") or ""
        if not token:
            m = re.search(r"session_token=([^;]+)", r.headers.get("set-cookie", ""))
            token = m.group(1) if m else ""
        return token


async def _bell_titles(token: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=10, headers={"Cookie": f"session_token={token}"}) as c:
        r = await c.get(f"{BASE}/api/notifications")
        if r.status_code != 200:
            print(f"      [bell] HTTP {r.status_code} {r.text[:120]}")
            return []
        return r.json()


# ────────────────────────────────────────────────────────────────────────────
async def main():
    print("\n" + "=" * 78)
    print(" NOTIFICATION LOCALE PROOF")
    print("=" * 78 + "\n")

    # Wipe any prior locale-test rows from prior runs
    await _db.notifications.delete_many({"data.locale_test": True})

    # Make / reset 3 test users
    admin_email = "admin@atlas.dev"
    inv_uk_email = f"loc-uk+{uuid.uuid4().hex[:6]}@atlas.dev"
    inv_en_email = f"loc-en+{uuid.uuid4().hex[:6]}@atlas.dev"

    admin = await _db.users.find_one({"email": admin_email})
    # Force admin.language = "en" to PROVE policy overrides UI choice
    await _db.users.update_one(
        {"email": admin_email}, {"$set": {"language": "en"}}
    )
    admin_uid = admin.get("user_id") or admin.get("id")
    inv_uk_uid = await _ensure_user(inv_uk_email, role="investor", language="uk")
    inv_en_uid = await _ensure_user(inv_en_email, role="investor", language="en")

    print(f"  admin_uid={admin_uid}     (language='en' set on purpose — policy must pin to UK)")
    print(f"  inv_uk_uid={inv_uk_uid}  (language='uk')")
    print(f"  inv_en_uid={inv_en_uid}  (language='en')")
    print()

    # Import server's create_notification straight from the running module
    sys.path.insert(0, "/app/backend")
    from server import create_notification, _get_user_lang, _resolve_user_lang

    # ── Test A — _get_user_lang policy resolution ─────────────────────────
    print("A · _get_user_lang() policy resolution")
    a_admin = await _get_user_lang(admin_uid)
    a_inv_uk = await _get_user_lang(inv_uk_uid)
    a_inv_en = await _get_user_lang(inv_en_uid)
    ok_a = (a_admin == "uk" and a_inv_uk == "uk" and a_inv_en == "en")
    print(f"  admin (UI=en)  → {a_admin}   (expected: uk)")
    print(f"  inv_uk         → {a_inv_uk}   (expected: uk)")
    print(f"  inv_en         → {a_inv_en}   (expected: en)")
    print(f"  → {'PASS' if ok_a else 'FAIL'}\n")

    # ── Test B — _resolve_user_lang (direct-insert sites) — same policy ───
    print("B · _resolve_user_lang() policy resolution")
    b_admin = await _resolve_user_lang(admin_uid)
    b_inv_uk = await _resolve_user_lang(inv_uk_uid)
    b_inv_en = await _resolve_user_lang(inv_en_uid)
    ok_b = (b_admin == "uk" and b_inv_uk == "uk" and b_inv_en == "en")
    print(f"  admin (UI=en)  → {b_admin}   (expected: uk)")
    print(f"  inv_uk         → {b_inv_uk}   (expected: uk)")
    print(f"  inv_en         → {b_inv_en}   (expected: en)")
    print(f"  → {'PASS' if ok_b else 'FAIL'}\n")

    # ── Test C — write a real notification through create_notification ────
    print("C · create_notification() writes a localized row to db.notifications")
    common_fmt = {"amount": 250, "referee": "Test Referee"}
    for uid, _label in [(admin_uid, "admin"), (inv_uk_uid, "inv_uk"), (inv_en_uid, "inv_en")]:
        await create_notification(
            user_id=uid, ntype="referral_earned",
            i18n_key_title="notif.referral_earned.title",
            i18n_key_body="notif.referral_earned.body",
            i18n_fmt=common_fmt,
            data={"locale_test": True},
        )

    # Pull the rows back from Mongo
    rows = await _db.notifications.find(
        {"data.locale_test": True}, {"_id": 0, "user_id": 1, "title": 1, "message": 1}
    ).to_list(20)
    by_uid = {r["user_id"]: r for r in rows}
    admin_row = by_uid.get(admin_uid, {})
    inv_uk_row = by_uid.get(inv_uk_uid, {})
    inv_en_row = by_uid.get(inv_en_uid, {})

    # Expected EN body: "You earned $250 from Test Referee's task."
    # Expected UK body: contains Cyrillic
    def _is_cyrillic(s: str) -> bool:
        return bool(re.search(r"[А-Яа-яЇїІіЄєҐґ]", s or ""))

    admin_uk_ok = _is_cyrillic(admin_row.get("title", "")) and _is_cyrillic(admin_row.get("message", ""))
    inv_uk_ok = _is_cyrillic(inv_uk_row.get("title", "")) and _is_cyrillic(inv_uk_row.get("message", ""))
    inv_en_ok = (not _is_cyrillic(inv_en_row.get("title", ""))) and "Referral earned" in inv_en_row.get("title", "")

    print(f"  admin_row.title:    {admin_row.get('title')!r}")
    print(f"  admin_row.message:  {admin_row.get('message')!r}")
    print(f"  admin (UI=en) is Cyrillic? {admin_uk_ok}   (expected: True — policy override)\n")
    print(f"  inv_uk_row.title:   {inv_uk_row.get('title')!r}")
    print(f"  inv_uk_row.message: {inv_uk_row.get('message')!r}")
    print(f"  inv_uk is Cyrillic? {inv_uk_ok}   (expected: True)\n")
    print(f"  inv_en_row.title:   {inv_en_row.get('title')!r}")
    print(f"  inv_en_row.message: {inv_en_row.get('message')!r}")
    print(f"  inv_en is English?  {inv_en_ok}   (expected: True)\n")

    ok_c = admin_uk_ok and inv_uk_ok and inv_en_ok
    print(f"  → {'PASS' if ok_c else 'FAIL'}\n")

    # ── Test D — Bell endpoint /api/notifications returns localized rows ──
    print("D · /api/notifications (bell endpoint) returns localized rows")
    admin_tok = await _admin_token()
    inv_uk_tok = await _user_token(inv_uk_email)
    inv_en_tok = await _user_token(inv_en_email)

    admin_bell = await _bell_titles(admin_tok)
    inv_uk_bell = await _bell_titles(inv_uk_tok)
    inv_en_bell = await _bell_titles(inv_en_tok)

    a_titles = [n.get("title") for n in admin_bell]
    uk_titles = [n.get("title") for n in inv_uk_bell]
    en_titles = [n.get("title") for n in inv_en_bell]

    print(f"  admin bell ({len(admin_bell)} items)   first title: {a_titles[0] if a_titles else '—'}")
    print(f"  inv_uk bell ({len(inv_uk_bell)} items) first title: {uk_titles[0] if uk_titles else '—'}")
    print(f"  inv_en bell ({len(inv_en_bell)} items) first title: {en_titles[0] if en_titles else '—'}")

    # Bell endpoint should reflect what's stored — already localized
    d_admin_ok = any(_is_cyrillic(t) for t in a_titles)
    d_uk_ok = any(_is_cyrillic(t) for t in uk_titles)
    d_en_ok = any((t and "Referral earned" in t) for t in en_titles)
    print(f"  admin bell has Cyrillic? {d_admin_ok}")
    print(f"  inv_uk bell has Cyrillic? {d_uk_ok}")
    print(f"  inv_en bell has English? {d_en_ok}")
    ok_d = d_admin_ok and d_uk_ok and d_en_ok
    print(f"  → {'PASS' if ok_d else 'FAIL'}\n")

    # ── Test E — Atlas demo seed is gone (the placeholders on the screenshot) ─
    print("E · Atlas demo seed is wiped from db.notifications")
    legacy = await _db.notifications.count_documents({
        "title": {"$in": ["Module delivered", "Invoice paid", "Next phase started",
                          "Payout batch settled", "QA queue has new items",
                          "New developer onboarded", "Dashboard UI ready for review",
                          "Platform milestone", "New module assigned",
                          "Earnings cleared", "Tier promotion"]}
    })
    ok_e = legacy == 0
    print(f"  Atlas demo rows remaining: {legacy}   (expected: 0)")
    print(f"  → {'PASS' if ok_e else 'FAIL'}\n")

    # ── Summary ───────────────────────────────────────────────────────────
    print("=" * 78)
    results = [
        ("A · _get_user_lang() policy", ok_a),
        ("B · _resolve_user_lang() policy", ok_b),
        ("C · create_notification() writes localized rows", ok_c),
        ("D · /api/notifications returns localized rows", ok_d),
        ("E · Atlas demo seed wiped", ok_e),
    ]
    for name, ok in results:
        print(f"  {'[PASS]' if ok else '[FAIL]'}  {name}")
    total_ok = all(ok for _, ok in results)
    print()
    print(f"  RESULT: {'ALL 5/5 PASS ✓' if total_ok else 'SOME FAILED ✗'}")

    # Clean up test rows
    await _db.notifications.delete_many({"data.locale_test": True})
    await _db.users.delete_many({"email": {"$in": [inv_uk_email, inv_en_email]}})

    return 0 if total_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
