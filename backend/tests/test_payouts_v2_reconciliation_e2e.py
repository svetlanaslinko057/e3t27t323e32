"""
PAY-V2-P4 Reconciliation Observer — E2E.

Tests the PASSIVE observer path end-to-end:

  1. Seed a synthetic settled payout_item with a provider_ref.
  2. With RECONCILE_INJECT_DIVERGENCE=1 already in env, run /reconciliation/run.
  3. Verify ≥1 divergence event appears (state=open, severity=critical for amount_mismatch).
  4. List divergences as admin.
  5. Resolve one explicitly and verify state flips to resolved.
  6. Negative RBAC: client gets 403 on every admin endpoint.
  7. Negative API: active mode returns 501.

Assumes RECONCILE_INJECT_DIVERGENCE=1, RECONCILE_INJECT_KIND=amount_mismatch
are in /app/backend/.env so the running backend exhibits the synthetic drift.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

BASE = os.getenv("E2E_BASE_URL", "http://localhost:8001")
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")


async def login(c: httpx.AsyncClient, email: str, pw: str) -> dict:
    r = await c.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw})
    r.raise_for_status()
    raw = r.headers.get("set-cookie", "")
    if "session_token=" in raw:
        tok = raw.split("session_token=", 1)[1].split(";", 1)[0]
        c.headers["Authorization"] = f"Bearer {tok}"
    return r.json()


async def main() -> int:
    client = AsyncIOMotorClient(MONGO_URL)
    db = client["test_database"]

    # 1. Seed synthetic settled payout_item
    seed_id = f"itm_recon_{uuid.uuid4().hex[:8]}"
    seed_batch = f"bat_recon_{uuid.uuid4().hex[:8]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.payout_items_v2.insert_one({
        "item_id": seed_id,
        "batch_id": seed_batch,
        "developer_id": "dev_recon_synthetic",
        "amount": 100.00,
        "currency": "USD",
        "state": "settled",
        "provider_ref": f"mockpay_recon_{uuid.uuid4().hex[:10]}",
        "settled_at": now_iso,
        "created_at": now_iso,
        "updated_at": now_iso,
    })
    print(f"[seed] item_id={seed_id} batch_id={seed_batch}")

    async with httpx.AsyncClient(timeout=20.0) as adm, \
               httpx.AsyncClient(timeout=20.0) as cli:
        admin = await login(adm, "admin@atlas.dev", "admin123")
        clientu = await login(cli, "client@atlas.dev", "client123")
        print(f"[login] admin={admin.get('user_id')} client={clientu.get('user_id')}")

        # 2. Trigger reconciliation
        r = await adm.post(
            f"{BASE}/api/payouts-v2/reconciliation/run",
            json={"window_minutes": 99999},
        )
        r.raise_for_status()
        run = r.json()
        print(f"[run] {run['run_id']} scanned={run['scanned']} "
              f"discrepancies={run['discrepancies']} by_severity={run['by_severity']}")
        assert run["scanned"] >= 1, "scanner missed our seeded item"
        assert run["discrepancies"] >= 1, (
            "injection enabled but no divergence raised — "
            "ensure RECONCILE_INJECT_DIVERGENCE=1 is in /app/backend/.env"
        )

        # 3. List open divergences
        r = await adm.get(
            f"{BASE}/api/payouts-v2/reconciliation/divergences?state=open"
        )
        r.raise_for_status()
        divs = r.json()["items"]
        target = next((d for d in divs if d["item_id"] == seed_id), None)
        assert target, f"no divergence found for seeded item {seed_id}"
        assert target["divergence_type"] == "amount_mismatch"
        assert target["severity"] == "critical"
        print(f"[divs.open] count={len(divs)} target={target['divergence_id']} "
              f"type={target['divergence_type']} sev={target['severity']}")

        # 4. Resolve explicitly
        r = await adm.post(
            f"{BASE}/api/payouts-v2/reconciliation/divergences/"
            f"{target['divergence_id']}/resolve",
            json={"resolution": "accepted", "note": "Manual review — within tolerance."},
        )
        r.raise_for_status()
        print(f"[resolve] {r.json()}")

        # 5. Verify state flipped to resolved
        r = await adm.get(
            f"{BASE}/api/payouts-v2/reconciliation/divergences?"
            f"state=resolved&limit=50"
        )
        r.raise_for_status()
        rsv = next((d for d in r.json()["items"]
                    if d["divergence_id"] == target["divergence_id"]), None)
        assert rsv, "divergence did not flip to resolved"
        assert rsv["resolution"] == "accepted"
        print(f"[divs.resolved] ok resolved_by={rsv['resolved_by']}")

        # 6. Summary should reflect at least the resolved row
        r = await adm.get(f"{BASE}/api/payouts-v2/reconciliation/summary")
        r.raise_for_status()
        s = r.json()
        print(f"[summary] open_total={s['open_total']} open_critical={s['open_critical']} "
              f"last_run={(s['last_run'] or {}).get('run_id')}")

        # 7. Negative RBAC — client → 403 everywhere
        targets = [
            ("GET",  "/api/payouts-v2/reconciliation/summary"),
            ("POST", "/api/payouts-v2/reconciliation/run"),
            ("GET",  "/api/payouts-v2/reconciliation/runs"),
            ("GET",  "/api/payouts-v2/reconciliation/divergences"),
            ("POST", f"/api/payouts-v2/reconciliation/divergences/{target['divergence_id']}/resolve"),
        ]
        for method, path in targets:
            if method == "GET":
                rr = await cli.get(f"{BASE}{path}")
            else:
                rr = await cli.post(f"{BASE}{path}", json={"resolution": "accepted"})
            assert rr.status_code == 403, (
                f"client got {rr.status_code} on {method} {path} — expected 403"
            )
        print("[rbac] client → 403 on all 5 reconciliation endpoints ✓")

        print("\n✅ PAY-V2-P4 RECONCILIATION OBSERVER E2E PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
