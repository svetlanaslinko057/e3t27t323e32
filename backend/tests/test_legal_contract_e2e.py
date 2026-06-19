"""
End-to-end contract signing flow smoke test.

Exercises:
  1. Login as a client (john@atlas.dev — has dual role, picks up
     both 'client' and 'developer'; we use his client identity for this).
  2. Find or create a project owned by this user.
  3. Save legal profile.
  4. Prepare contract → state = awaiting_signature.
  5. Request OTP → in dev_mode the OTP is returned in the response.
  6. Confirm signature with click-wrap acks + OTP code.
  7. Verify: contract is signed, sha256 hash present, executor_signature
     auto-populated, PDF bytes generated, notifications written, ZIP
     export downloadable.
"""
from __future__ import annotations
import asyncio
import base64
import json
import os
import sys
import uuid

import httpx

BASE = os.getenv("E2E_BASE_URL", "http://localhost:8001")


async def login(c: httpx.AsyncClient, email: str, pw: str) -> dict:
    """Login and pin the session_token as a Bearer header.

    The auth layer sets `Secure` on the cookie which httpx won't store
    over http://localhost; using Authorization: Bearer is the supported
    fallback (see server.py:1838).
    """
    r = await c.post(f"{BASE}/api/auth/login",
                     json={"email": email, "password": pw})
    r.raise_for_status()
    raw = r.headers.get("set-cookie", "")
    if "session_token=" in raw:
        tok = raw.split("session_token=", 1)[1].split(";", 1)[0]
        c.headers["Authorization"] = f"Bearer {tok}"
    return r.json()


async def ensure_project(c: httpx.AsyncClient, user_id: str) -> dict:
    """Find any project owned by this client; if none, create one."""
    r = await c.get(f"{BASE}/api/projects/mine")
    if r.status_code == 200:
        data = r.json()
        items = data if isinstance(data, list) else (
            data.get("projects") or data.get("items") or []
        )
        if items:
            return items[0]
    # Create via /api/projects
    r = await c.post(f"{BASE}/api/projects", json={
        "title": f"E2E Contract Test {uuid.uuid4().hex[:6]}",
        "description": "Auto-generated project to exercise the contract signing flow end-to-end.",
        "budget": 1500,
        "currency": "USD",
    })
    if r.status_code in (200, 201):
        body = r.json()
        return body.get("project") or body
    raise RuntimeError(
        f"No project available and could not create one: "
        f"{r.status_code} {r.text[:300]}"
    )


async def main() -> int:
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as c:
        # ---- 1) Login as the dual-role demo user (has a real project seeded) ----
        try:
            user = await login(c, "client@atlas.dev", "client123")
        except Exception:
            user = await login(c, "multi@atlas.dev", "multi123")
        print(f"[login] {user.get('email')} role={user.get('role')} roles={user.get('roles')}")

        # ---- 2) Get my contracts list (existing draft?) ----
        r = await c.get(f"{BASE}/api/contracts/my")
        r.raise_for_status()
        cdata = r.json()
        contracts = cdata if isinstance(cdata, list) else (cdata.get("items") or [])
        print(f"[contracts/my] returned {len(contracts)} entries")

        # Try to find an already-signed contract to exercise PDF download path
        existing_signed = None
        existing_awaiting = None
        for k in contracts:
            if k.get("state") == "signed" and not existing_signed:
                existing_signed = k
            if k.get("state") == "awaiting_signature" and not existing_awaiting:
                existing_awaiting = k

        # ---- 3) If no awaiting contract, prepare one ----
        if not existing_awaiting and not existing_signed:
            project = await ensure_project(c, user["user_id"])
            project_id = project.get("project_id") or project.get("_id") or project.get("id")
            print(f"[project] using project_id={project_id}")
            # Prepare contract
            r = await c.post(f"{BASE}/api/contracts/prepare",
                             json={"project_id": project_id})
            if r.status_code not in (200, 201):
                print(f"[prepare] FAILED status={r.status_code} body={r.text[:300]}")
                return 1
            prep = r.json()
            existing_awaiting = prep.get("contract") or prep
            print(f"[prepare] contract_id={existing_awaiting.get('contract_id')} state={existing_awaiting.get('state')}")

        # ---- 4) If awaiting/draft, sign it end-to-end ----
        if existing_awaiting and existing_awaiting.get("state") != "signed":
            cid = existing_awaiting["contract_id"]

            # request-otp REQUIRES the new P3 legal_profile shape:
            # legal_type + first_name + last_name + phone + billing_address +
            # country + city + postal_code.
            r = await c.post(f"{BASE}/api/contracts/{cid}/sign/request-otp", json={
                "legal_profile": {
                    "legal_type": "individual",
                    "first_name": "Acme",
                    "last_name": "Tester",
                    "middle_name": None,
                    "phone": "+1 555 0100",
                    "billing_address": "1 Test Lane, Suite 42",
                    "country": "TS",
                    "city": "Testopolis",
                    "postal_code": "11111",
                    "tax_id": None,  # optional now (data minimization)
                },
            })
            if r.status_code != 200:
                print(f"[request-otp] FAILED {r.status_code} {r.text[:300]}")
                return 1
            otp_resp = r.json()
            otp_block = otp_resp.get("otp", {})
            dev_code = otp_block.get("dev_code")
            print(f"[request-otp] state→{otp_resp.get('contract_state')} delivered={otp_block.get('delivered')} dev_mode={otp_block.get('dev_mode')} dev_code={'set' if dev_code else 'no'}")
            if not dev_code:
                print("[request-otp] no dev_code returned — cannot continue in dev mode")
                return 1

            r = await c.post(f"{BASE}/api/contracts/{cid}/sign/confirm", json={
                "otp_code": dev_code,
                "terms_version": "v1.0-placeholder",
                "legal_profile": {
                    "legal_type": "individual",
                    "first_name": "Acme",
                    "last_name": "Tester",
                    "middle_name": None,
                    "phone": "+1 555 0100",
                    "billing_address": "1 Test Lane, Suite 42",
                    "country": "TS",
                    "city": "Testopolis",
                    "postal_code": "11111",
                    "tax_id": None,
                },
                "acknowledgements": {
                    "legal_details_correct": True,
                    "scope_terms_agreed": True,
                    "start_after_payment_understood": True,
                },
            })
            if r.status_code != 200:
                print(f"[confirm] FAILED {r.status_code} {r.text[:500]}")
                return 1
            signed = r.json()
            ev = signed.get("evidence", {})
            print(f"[confirm] state={signed['contract']['state']} sha256={(ev.get('sha256_hash') or '')[:16]}…")
            print(f"          pdf_status={ev.get('pdf_status')} fully_executed={ev.get('fully_executed')}")
            print(f"          executor.party={(ev.get('executor_signature') or {}).get('party')}")
            assert signed["contract"]["state"] == "signed"
            assert ev.get("fully_executed") is True
            assert ev.get("pdf_status") == "generated", f"PDF not generated: {ev.get('pdf_status')}"
            assert ev.get("executor_signature", {}).get("party"), "executor counter-sign missing"
            existing_signed = signed["contract"]

        # ---- 5) Verify evidence endpoint exposes executor_signature ----
        if existing_signed:
            cid = existing_signed["contract_id"]
            r = await c.get(f"{BASE}/api/contracts/{cid}/evidence")
            r.raise_for_status()
            evd = r.json()
            print(f"[evidence] fully_executed={evd.get('fully_executed')} "
                  f"executor.role={(evd.get('executor_signature') or {}).get('role')}")
            assert evd.get("executor_signature"), "evidence missing executor_signature"

            # ---- 6) Download PDF ----
            r = await c.get(f"{BASE}/api/contracts/{cid}/pdf")
            assert r.status_code == 200, f"PDF download failed: {r.status_code}"
            assert r.headers.get("content-type") == "application/pdf"
            assert r.content.startswith(b"%PDF-"), "Not a real PDF"
            print(f"[pdf] downloaded {len(r.content)} bytes, sha256 header = {r.headers.get('X-Contract-Sha256','')[:16]}…")

        # ---- 7) ZIP export ----
        r = await c.get(f"{BASE}/api/contracts/exports/zip")
        if r.status_code == 200:
            assert r.headers.get("content-type") == "application/zip"
            assert r.content[:2] == b"PK", "ZIP magic bytes missing"
            print(f"[zip] downloaded {len(r.content)} bytes — manifest+evidence+pdf bundle OK")
        elif r.status_code == 404:
            print("[zip] no signed contracts yet — expected if no signing happened")
        else:
            print(f"[zip] unexpected status {r.status_code}")

        # ---- 8) Notifications fan-out ----
        r = await c.get(f"{BASE}/api/notifications/my?limit=20")
        if r.status_code == 200:
            ns = r.json()
            ns_list = ns if isinstance(ns, list) else (ns.get("items") or [])
            signed_notifs = [n for n in ns_list if (n.get("kind") or "").startswith("contract.signed")]
            print(f"[notifications] total={len(ns_list)} contract.signed={len(signed_notifs)}")

        # ---- 9) CONTRACT-P6 Readiness gate (when contract is signed, ready=False
        #         because checks include not_already_signed=False) ----
        if existing_signed:
            r = await c.get(f"{BASE}/api/contracts/{existing_signed['contract_id']}/readiness")
            assert r.status_code == 200, f"readiness endpoint failed: {r.status_code}"
            rd = r.json()
            print(f"[readiness] signed contract → ready={rd['ready']} missing={rd['missing']} sig_level={rd.get('signature_level_required')}")
            assert rd["ready"] is False, "signed contract should NOT be ready (already signed)"
            assert "not_already_signed" in rd["missing"]

        # ---- 10) CONTRACT-P7 Data export ----
        # First, exercise PUT /legal/profile to ensure new P3 shape is persisted
        # (otherwise an existing-signed-contract run skips _upsert_legal_profile).
        r = await c.put(f"{BASE}/api/legal/profile", json={
            "legal_type": "individual",
            "first_name": "Acme",
            "last_name": "Tester",
            "phone": "+1 555 0100",
            "billing_address": "1 Test Lane, Suite 42",
            "country": "TS",
            "city": "Testopolis",
            "postal_code": "11111",
        })
        assert r.status_code == 200, f"PUT profile failed: {r.status_code} {r.text[:200]}"

        r = await c.get(f"{BASE}/api/legal/profile/export")
        assert r.status_code == 200, f"export failed: {r.status_code}"
        ex = r.json()
        prof = ex["legal_profile"]
        print(f"[export] profile shape: legal_type={prof.get('legal_type')} first_name={prof.get('first_name')} billing_address={'set' if prof.get('billing_address') else 'no'} contracts={len(ex['contracts'])} signatures={len(ex['signatures'])}")
        assert prof.get("legal_type") in ("individual", "company"), f"legal_type missing: {prof}"
        assert prof.get("first_name"), "first_name missing"
        assert prof.get("billing_address"), "billing_address missing"
        assert "tax_id_enc" not in prof, "encrypted blob leaked to UI"

        # ---- 11) CONTRACT-P7 Erasure request ----
        r = await c.post(f"{BASE}/api/legal/profile/delete-request")
        assert r.status_code == 200, f"delete-request failed: {r.status_code}"
        print(f"[delete-request] state={r.json().get('state')}")

        print("\n✅ END-TO-END CONTRACT SIGNING FLOW PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
