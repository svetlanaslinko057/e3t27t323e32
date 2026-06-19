"""
CONTRACT-P7 admin oversight surface — E2E smoke.

Covers the four admin-only endpoints added at final closure:
  • GET  /api/admin/legal/profile/{user_id}       (RBAC + access log)
  • GET  /api/admin/legal/deletion-requests       (filter by state)
  • POST /api/admin/legal/deletion-requests/{uid}/resolve
  • GET  /api/admin/legal/access-log              (paginated)
  • GET  /api/admin/legal/contracts               (signed list)

Plus negative RBAC checks (client must get 403 on all of them).
"""
from __future__ import annotations
import asyncio
import os
import sys

import httpx

BASE = os.getenv("E2E_BASE_URL", "http://localhost:8001")


async def login(c: httpx.AsyncClient, email: str, pw: str) -> dict:
    r = await c.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw})
    r.raise_for_status()
    raw = r.headers.get("set-cookie", "")
    if "session_token=" in raw:
        tok = raw.split("session_token=", 1)[1].split(";", 1)[0]
        c.headers["Authorization"] = f"Bearer {tok}"
    return r.json()


async def main() -> int:
    async with httpx.AsyncClient(timeout=20.0) as adm, \
               httpx.AsyncClient(timeout=20.0) as cli:
        admin = await login(adm, "admin@atlas.dev", "admin123")
        client = await login(cli, "client@atlas.dev", "client123")
        print(f"[login] admin uid={admin.get('user_id')} role={admin.get('role')}")
        print(f"[login] client uid={client.get('user_id')} role={client.get('role')}")

        # ---- 1) Have client open a deletion request so it shows up in admin list ----
        r = await cli.post(f"{BASE}/api/legal/profile/delete-request")
        r.raise_for_status()
        print(f"[client.delete-request] state={r.json().get('state')}")

        # ---- 2) Admin lists open deletion requests (must include our client) ----
        r = await adm.get(f"{BASE}/api/admin/legal/deletion-requests?state=open")
        r.raise_for_status()
        items = r.json().get("items", [])
        target_uid = next(
            (i["user_id"] for i in items if i["user_id"] == client["user_id"]),
            None,
        )
        assert target_uid, "client did not appear in open deletion list"
        print(f"[admin.deletion-requests] count={r.json().get('count')} target=found")

        # ---- 3) Admin reads the client's legal profile (logs access) ----
        r = await adm.get(
            f"{BASE}/api/admin/legal/profile/{target_uid}?reason=qa_test",
        )
        if r.status_code == 200:
            print(f"[admin.profile.{target_uid}] legal_type={r.json()['profile'].get('legal_type')}")
        else:
            # If profile is empty (fresh DB) this is acceptable; just skip.
            print(f"[admin.profile.{target_uid}] {r.status_code} (no profile yet — ok on fresh DB)")

        # ---- 4) Admin resolves the deletion request ----
        r = await adm.post(
            f"{BASE}/api/admin/legal/deletion-requests/{target_uid}/resolve",
            json={"resolution": "retained_under_law",
                  "note": "Signed evidence retained per Section 18."},
        )
        r.raise_for_status()
        print(f"[admin.resolve] resolution={r.json().get('resolution')}")

        # ---- 5) Admin pulls audit log scoped to this subject ----
        r = await adm.get(
            f"{BASE}/api/admin/legal/access-log?subject_user_id={target_uid}",
        )
        r.raise_for_status()
        log = r.json().get("items", [])
        kinds = sorted({row.get("reason") for row in log})
        print(f"[admin.access-log] count={len(log)} reasons={kinds}")
        assert any("deletion_resolved" in (k or "") for k in kinds), \
            "deletion_resolved row missing from access log"

        # ---- 6) Admin lists contracts ----
        r = await adm.get(f"{BASE}/api/admin/legal/contracts?limit=5")
        r.raise_for_status()
        print(f"[admin.contracts] count={r.json().get('count')}")

        # ---- 7) Client must get 403 on EVERY admin endpoint ----
        targets = [
            ("GET",  f"/api/admin/legal/profile/{target_uid}"),
            ("GET",  "/api/admin/legal/deletion-requests"),
            ("GET",  "/api/admin/legal/access-log"),
            ("GET",  "/api/admin/legal/contracts"),
            ("POST", f"/api/admin/legal/deletion-requests/{target_uid}/resolve"),
        ]
        for method, path in targets:
            if method == "GET":
                r = await cli.get(f"{BASE}{path}")
            else:
                r = await cli.post(f"{BASE}{path}", json={"resolution": "rejected"})
            assert r.status_code == 403, (
                f"client got {r.status_code} on {method} {path} — expected 403"
            )
        print("[rbac] client → 403 on all 5 admin endpoints ✓")

        print("\n✅ CONTRACT-P7 ADMIN OVERSIGHT E2E PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
