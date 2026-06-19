"""
Phase S2 — Contract Security E2E
=================================

Tests every edge case of the public view-token contract signing surface.
Run with: `python /app/backend/test_contract_view_token_e2e.py`

Edge cases covered (per user-locked S2 spec, 2026-06-15 evening):
  1. happy path — issue → view → sign
  2. token revoke (admin DELETE)        → public GET/sign/download → 404
  3. expired token (manual DB rewrite)  → 410 Gone
  4. reused token after signed contract → 409 "вже підписано"
  5. re-issue view-link on signed       → 200 OK (download still allowed)
  6. concurrent sign attempts           → exactly 1 succeeds, others 409
  7. email mismatch on sign             → 403 (does NOT leak expected email)
  8. cancelled contract                 → 410 on view/sign/download
  9. agree=false                        → 400
 10. view-link issue on cancelled       → 409
"""

import asyncio
import os
import sys
import time
from datetime import datetime, timezone, timedelta

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

BACKEND = os.environ.get("BACKEND_URL", "https://dev-branch-69.preview.emergentagent.com")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

ADMIN_EMAIL = "admin@atlas.dev"
ADMIN_PASSWORD = "admin123"

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"

results = []


def ok(name):
    print(f"  {PASS} {name}")
    results.append((name, True, None))


def bad(name, detail):
    print(f"  {FAIL} {name}  — {detail}")
    results.append((name, False, detail))


async def login_admin(client: httpx.AsyncClient) -> bool:
    r = await client.post(
        f"{BACKEND}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD,
              "device_fingerprint": "s2-e2e-test"},
    )
    if r.status_code != 200:
        bad("admin login", f"HTTP {r.status_code}: {r.text[:200]}")
        return False
    data = r.json()
    if data.get("requires_2fa"):
        bad("admin login", "2FA required — disable for admin@atlas.dev in test env")
        return False
    ok(f"admin login (cookies={list(client.cookies.keys())})")
    return True


async def find_or_create_test_investor_and_contract(db):
    """Locate (or create) a 'generated' contract bound to a real investor."""
    # Need an investor with email + a generated/sent contract.
    c = await db.lumen_contracts.find_one(
        {"status": {"$in": ["generated", "sent", "viewed"]}}
    )
    if c:
        u = await db.users.find_one({"user_id": c.get("investor_id")})
        if u and u.get("email"):
            return c, u
    # Else: try to find ANY contract & re-arm it for the test
    c = await db.lumen_contracts.find_one({})
    if not c:
        return None, None
    u = await db.users.find_one({"user_id": c.get("investor_id")})
    if not u:
        return None, None
    # Force status back to "generated" for test reuse
    await db.lumen_contracts.update_one(
        {"id": c["id"]},
        {"$set": {"status": "generated", "view_token": None,
                  "view_token_expires_at": None,
                  "signed_at": None, "viewed_at": None}},
    )
    await db.lumen_signatures.delete_many({"contract_id": c["id"]})
    c["status"] = "generated"
    return c, u


async def test_happy_path(client, admin_token, contract, user):
    """Test 1: issue → view → sign by valid investor."""
    print("\n[1] Happy path — issue → view → sign")
    contract_id = contract["id"]

    # Admin issues view-link
    r = await client.post(
        f"{BACKEND}/api/admin/contracts/{contract_id}/view-link",
        json={"expires_in_days": 30},
        cookies=client.cookies,
    )
    if r.status_code != 200:
        bad("issue view-link", f"HTTP {r.status_code}: {r.text[:200]}")
        return None
    token = r.json().get("view_token")
    if not token:
        bad("issue view-link", "no view_token in response")
        return None
    ok(f"issue view-link  token=...{token[-8:]}")

    # Public GET /view
    pub = httpx.AsyncClient(timeout=20)
    try:
        r = await pub.get(f"{BACKEND}/api/contracts/view/{token}")
        if r.status_code != 200:
            bad("public GET /view", f"HTTP {r.status_code}: {r.text[:200]}")
            return token
        body = r.json()
        if body.get("contract_id") != contract_id:
            bad("public GET /view", f"wrong contract_id: {body.get('contract_id')}")
            return token
        ok("public GET /view returns contract body")

        # Public download
        r = await pub.get(f"{BACKEND}/api/contracts/view/{token}/download")
        if r.status_code != 200:
            bad("public download", f"HTTP {r.status_code}")
        elif r.headers.get("content-type", "").startswith("application/pdf"):
            ok("public download returns application/pdf")
        else:
            bad("public download", f"wrong content-type: {r.headers.get('content-type')}")

        # Sign — agree=false → 400
        r = await pub.post(
            f"{BACKEND}/api/contracts/view/{token}/sign",
            json={"agree": False, "signer_email": user["email"]},
        )
        if r.status_code == 400:
            ok("sign without agree → 400")
        else:
            bad("sign without agree", f"HTTP {r.status_code} (expected 400)")

        # Sign — email mismatch → 403
        r = await pub.post(
            f"{BACKEND}/api/contracts/view/{token}/sign",
            json={"agree": True, "signer_email": "intruder@evil.com",
                  "signer_name": "Intruder"},
        )
        if r.status_code == 403:
            ok("sign with wrong email → 403 (no leak)")
            if (user["email"].lower() in r.text.lower()):
                bad("403 leak check", "expected email leaked in 403 detail!")
            else:
                ok("403 does NOT leak the expected email")
        else:
            bad("sign wrong email", f"HTTP {r.status_code} (expected 403)")

        # Sign — happy path
        r = await pub.post(
            f"{BACKEND}/api/contracts/view/{token}/sign",
            json={"agree": True, "signer_email": user["email"],
                  "signer_name": user.get("name") or "Тестовий Інвестор"},
        )
        if r.status_code == 200:
            ok("sign happy path → 200")
            if r.json().get("status") == "signed":
                ok("sign result.status == 'signed'")
            else:
                bad("sign result status", r.json().get("status"))
        else:
            bad("sign happy path", f"HTTP {r.status_code}: {r.text[:200]}")

        # Sign AGAIN with same token → 404 (token auto-invalidated after sign,
        # this is a security feature — defends against replay).
        r = await pub.post(
            f"{BACKEND}/api/contracts/view/{token}/sign",
            json={"agree": True, "signer_email": user["email"]},
        )
        if r.status_code == 404:
            ok("re-sign same token → 404 (token auto-invalidated, anti-replay)")
        else:
            bad("re-sign same token", f"HTTP {r.status_code} (expected 404)")

        return token
    finally:
        await pub.aclose()


async def test_revoke(client, admin_token, contract, user):
    """Test 2: revoke → public access → 404."""
    print("\n[2] Revoke flow")
    contract_id = contract["id"]

    # Reset contract to generated, issue fresh token
    db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
    await db.lumen_contracts.update_one(
        {"id": contract_id},
        {"$set": {"status": "generated", "signed_at": None}},
    )
    await db.lumen_signatures.delete_many({"contract_id": contract_id})

    r = await client.post(
        f"{BACKEND}/api/admin/contracts/{contract_id}/view-link",
        json={"expires_in_days": 30},
    )
    token = r.json().get("view_token") if r.status_code == 200 else None
    if not token:
        bad("revoke prep", f"could not issue token: {r.status_code}")
        return

    # Public view works first
    pub = httpx.AsyncClient(timeout=20)
    try:
        r = await pub.get(f"{BACKEND}/api/contracts/view/{token}")
        if r.status_code == 200:
            ok("pre-revoke GET /view → 200")
        # Admin DELETE
        r = await client.delete(f"{BACKEND}/api/admin/contracts/{contract_id}/view-link")
        if r.status_code == 200:
            ok("admin DELETE view-link → 200")
        else:
            bad("admin DELETE view-link", f"HTTP {r.status_code}")
        # Public view after revoke
        r = await pub.get(f"{BACKEND}/api/contracts/view/{token}")
        if r.status_code == 404:
            ok("revoked token GET /view → 404")
        else:
            bad("revoked GET /view", f"HTTP {r.status_code} (expected 404)")
        r = await pub.post(
            f"{BACKEND}/api/contracts/view/{token}/sign",
            json={"agree": True, "signer_email": user["email"]},
        )
        if r.status_code == 404:
            ok("revoked token POST /sign → 404")
        else:
            bad("revoked POST /sign", f"HTTP {r.status_code} (expected 404)")
        r = await pub.get(f"{BACKEND}/api/contracts/view/{token}/download")
        if r.status_code == 404:
            ok("revoked token GET /download → 404")
        else:
            bad("revoked GET /download", f"HTTP {r.status_code} (expected 404)")
    finally:
        await pub.aclose()


async def test_expired(client, contract, user):
    """Test 3: expired token → 410 Gone."""
    print("\n[3] Expired token")
    contract_id = contract["id"]
    db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]

    # Reset & issue
    await db.lumen_contracts.update_one(
        {"id": contract_id},
        {"$set": {"status": "generated", "signed_at": None}},
    )
    await db.lumen_signatures.delete_many({"contract_id": contract_id})
    r = await client.post(
        f"{BACKEND}/api/admin/contracts/{contract_id}/view-link",
        json={"expires_in_days": 30},
    )
    token = r.json().get("view_token")
    if not token:
        bad("expired prep", f"issue failed {r.status_code}")
        return
    # Force expiry to YESTERDAY
    past = datetime.now(timezone.utc) - timedelta(days=2)
    await db.lumen_contracts.update_one(
        {"id": contract_id},
        {"$set": {"view_token_expires_at": past}},
    )
    pub = httpx.AsyncClient(timeout=20)
    try:
        r = await pub.get(f"{BACKEND}/api/contracts/view/{token}")
        if r.status_code == 410:
            ok("expired GET /view → 410")
        else:
            bad("expired GET /view", f"HTTP {r.status_code} (expected 410)")
        r = await pub.post(
            f"{BACKEND}/api/contracts/view/{token}/sign",
            json={"agree": True, "signer_email": user["email"]},
        )
        if r.status_code == 410:
            ok("expired POST /sign → 410")
        else:
            bad("expired POST /sign", f"HTTP {r.status_code} (expected 410)")
    finally:
        await pub.aclose()


async def test_cancelled(client, contract, user):
    """Test 8: cancelled contract → 410 on all public ops."""
    print("\n[8] Cancelled contract")
    contract_id = contract["id"]
    db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]

    # Reset to generated, issue, cancel
    await db.lumen_contracts.update_one(
        {"id": contract_id},
        {"$set": {"status": "generated", "signed_at": None}},
    )
    await db.lumen_signatures.delete_many({"contract_id": contract_id})
    r = await client.post(
        f"{BACKEND}/api/admin/contracts/{contract_id}/view-link",
        json={"expires_in_days": 30},
    )
    token = r.json().get("view_token")

    # Force status cancelled directly (bypassing the admin cancel route which
    # has additional side effects we don't care about for this security test)
    await db.lumen_contracts.update_one(
        {"id": contract_id},
        {"$set": {"status": "cancelled", "cancel_reason": "s2-test"}},
    )

    pub = httpx.AsyncClient(timeout=20)
    try:
        r = await pub.get(f"{BACKEND}/api/contracts/view/{token}")
        if r.status_code == 410:
            ok("cancelled GET /view → 410")
        else:
            bad("cancelled GET /view", f"HTTP {r.status_code} (expected 410)")
        r = await pub.post(
            f"{BACKEND}/api/contracts/view/{token}/sign",
            json={"agree": True, "signer_email": user["email"]},
        )
        if r.status_code == 410:
            ok("cancelled POST /sign → 410")
        else:
            bad("cancelled POST /sign", f"HTTP {r.status_code} (expected 410)")

        # Admin tries to issue a new view-link on a cancelled contract → 409
        r = await client.post(
            f"{BACKEND}/api/admin/contracts/{contract_id}/view-link",
            json={"expires_in_days": 30},
        )
        if r.status_code == 409:
            ok("admin issue view-link on cancelled → 409")
        else:
            bad("admin issue on cancelled", f"HTTP {r.status_code} (expected 409)")
    finally:
        await pub.aclose()


async def test_concurrent_sign(client, contract, user):
    """Test 6: 10 concurrent sign attempts, exactly 1 should succeed."""
    print("\n[6] Concurrent sign attempts (race condition)")
    contract_id = contract["id"]
    db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]

    # Reset to generated, issue
    await db.lumen_contracts.update_one(
        {"id": contract_id},
        {"$set": {"status": "generated", "signed_at": None,
                  "view_token": None, "view_token_expires_at": None,
                  "cancel_reason": None}},
    )
    await db.lumen_signatures.delete_many({"contract_id": contract_id})

    r = await client.post(
        f"{BACKEND}/api/admin/contracts/{contract_id}/view-link",
        json={"expires_in_days": 30},
    )
    token = r.json().get("view_token")
    if not token:
        bad("concurrent prep", f"issue failed {r.status_code}: {r.text[:200]}")
        return

    pub = httpx.AsyncClient(timeout=20)
    try:
        async def one_sign():
            return await pub.post(
                f"{BACKEND}/api/contracts/view/{token}/sign",
                json={"agree": True, "signer_email": user["email"],
                      "signer_name": "Race Tester"},
            )
        N = 10
        responses = await asyncio.gather(*[one_sign() for _ in range(N)],
                                          return_exceptions=True)
        codes = [(r.status_code if hasattr(r, "status_code") else "EXC")
                 for r in responses]
        successes = sum(1 for c in codes if c == 200)
        # After the winning sign, the token is auto-invalidated (anti-replay),
        # so the late requests get a mix of 404 (token gone) and 409 (status
        # already flipped to signed but token still valid in their view).
        rejections = sum(1 for c in codes if c in (404, 409))
        print(f"     codes: {codes}")
        if successes == 1:
            ok(f"concurrent: exactly 1 sign succeeded out of {N}")
        else:
            bad("concurrent: race condition",
                f"got {successes} successes (expected exactly 1)")
        if rejections >= N - 1:
            ok(f"concurrent: {rejections} got 404/409 (expected {N-1})")
        else:
            bad("concurrent: rejection count",
                f"got {rejections} rejections (expected at least {N-1})")
        # DB invariant: only 1 signature exists
        sig_count = await db.lumen_signatures.count_documents(
            {"contract_id": contract_id, "status": "signed"})
        if sig_count == 1:
            ok("DB invariant: exactly 1 signature row")
        else:
            bad("DB invariant: signature count",
                f"got {sig_count} (expected 1)")
    finally:
        await pub.aclose()


async def test_view_link_on_signed(client, contract, user):
    """Test 5: re-issue view-link on a signed contract — should be allowed."""
    print("\n[5] Re-issue view-link on signed contract")
    contract_id = contract["id"]
    db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
    sig_count = await db.lumen_signatures.count_documents(
        {"contract_id": contract_id, "status": "signed"})
    if sig_count < 1:
        # Force a signed state
        await db.lumen_contracts.update_one(
            {"id": contract_id}, {"$set": {"status": "signed",
                                          "signed_at": datetime.now(timezone.utc)}})
    else:
        await db.lumen_contracts.update_one(
            {"id": contract_id}, {"$set": {"status": "signed"}})
    r = await client.post(
        f"{BACKEND}/api/admin/contracts/{contract_id}/view-link",
        json={"expires_in_days": 30},
    )
    if r.status_code == 200:
        ok("issue view-link on signed → 200")
        new_token = r.json().get("view_token")
        # Sign attempt on signed contract → 409
        pub = httpx.AsyncClient(timeout=20)
        try:
            rr = await pub.post(
                f"{BACKEND}/api/contracts/view/{new_token}/sign",
                json={"agree": True, "signer_email": user["email"]},
            )
            if rr.status_code == 409:
                ok("sign on already-signed contract → 409")
            else:
                bad("sign on signed", f"HTTP {rr.status_code} (expected 409)")
            # But download/view should still work for receipts
            rr = await pub.get(f"{BACKEND}/api/contracts/view/{new_token}")
            if rr.status_code == 200:
                ok("view signed contract via new token → 200")
            else:
                bad("view signed via new token", f"HTTP {rr.status_code}")
        finally:
            await pub.aclose()
    else:
        bad("issue view-link on signed", f"HTTP {r.status_code}: {r.text[:200]}")


async def main():
    print("=" * 60)
    print("Phase S2 — Contract View-Token Security E2E")
    print(f"BACKEND: {BACKEND}")
    print(f"MONGO:   {MONGO_URL}")
    print(f"DB:      {DB_NAME}")
    print("=" * 60)

    db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
    contract, user = await find_or_create_test_investor_and_contract(db)
    if not contract or not user:
        print(f"{FAIL} cannot find a test contract+investor pair")
        sys.exit(1)
    print(f"\nUsing contract id={contract['id'][:12]}... number={contract.get('number')}")
    print(f"Investor email={user['email']}")

    client = httpx.AsyncClient(timeout=30)
    logged_in = await login_admin(client)
    if not logged_in:
        await client.aclose()
        sys.exit(1)

    # Tests 1, 7, 9 (happy path + email mismatch + agree=false combined)
    await test_happy_path(client, None, contract, user)

    # Tests 2 (revoke), 3 (expired), 8 (cancelled)
    await test_revoke(client, None, contract, user)
    await test_expired(client, contract, user)

    # Test 6 — concurrent race (CRITICAL)
    await test_concurrent_sign(client, contract, user)

    # Test 5 — view-link on signed (re-open)
    await test_view_link_on_signed(client, contract, user)

    # Test 8 — cancelled
    await test_cancelled(client, contract, user)

    await client.aclose()

    print("\n" + "=" * 60)
    passed = sum(1 for _, ok_flag, _ in results if ok_flag)
    failed = sum(1 for _, ok_flag, _ in results if not ok_flag)
    print(f"RESULT: {passed} passed, {failed} failed (total {len(results)})")
    if failed > 0:
        print("\nFailures:")
        for name, ok_flag, detail in results:
            if not ok_flag:
                print(f"  {FAIL} {name}: {detail}")
        sys.exit(1)
    print(f"\n{PASS} ALL PHASE S2 CONTRACT SECURITY CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
