"""
Sprint 2 smoke test — LUMEN Investment Core.

End-to-end flow through the live HTTP API (cookie auth):

  investor: submit intent  →  admin: list/approve  →  investment(contract_pending)
       →  investor signs contract (Sprint 4 legal gate)  →  investment(active)
       →  ownership upserted  →  asset.raised_amount updated
       →  portfolio assembled from real registry
  + reject flow, validations, idempotency (double-approve 409).

Run:  cd /app/backend && python tests/test_sprint2_core.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

BASE = "http://localhost:8001"
ASSET_ID = "asset-podilskyi"   # open, min_ticket=75000
AMOUNT = 100_000.0

failures = []


def check(name, ok, extra=""):
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name} {extra}")
    if not ok:
        failures.append(name)


async def login(client: httpx.AsyncClient, email: str) -> None:
    r = await client.post(f"{BASE}/api/auth/quick", json={"email": email})
    assert r.status_code == 200, f"quick login {email}: {r.status_code}"
    # The backend sets the session cookie with Secure=True; httpx refuses to
    # send Secure cookies over http://localhost, so re-set it manually.
    token = r.cookies.get("session_token")
    assert token, "no session_token cookie returned"
    client.cookies.set("session_token", token)


async def main() -> int:
    mongo = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = mongo[os.environ["DB_NAME"]]

    inv_client = httpx.AsyncClient(timeout=30)
    adm_client = httpx.AsyncClient(timeout=30)
    await login(inv_client, "client@atlas.dev")
    await login(adm_client, "admin@atlas.dev")

    me = (await inv_client.get(f"{BASE}/api/auth/me")).json()
    uid = me.get("user_id") or me.get("id")

    print("== Sprint 2: Investment Core flow ==")

    # baseline state
    asset_before = await db.lumen_assets.find_one({"id": ASSET_ID})
    raised_before = float(asset_before.get("raised_amount") or asset_before.get("raised") or 0)
    own_before = await db.lumen_ownerships.find_one({"investor_id": uid, "asset_id": ASSET_ID}) or {}
    units_before = float(own_before.get("units") or 0)

    # backfill sanity: rounds + ownerships registries are populated
    rounds_n = await db.lumen_investment_rounds.count_documents({})
    owns_n = await db.lumen_ownerships.count_documents({})
    check("backfill: rounds registry populated", rounds_n >= 1, f"-> {rounds_n}")
    check("backfill: ownership registry populated", owns_n >= 1, f"-> {owns_n}")

    # 1. submit intent (canonical endpoint)
    r = await inv_client.post(f"{BASE}/api/investor/intents",
                              json={"asset_id": ASSET_ID, "amount": AMOUNT,
                                    "note": "smoke-sprint2"})
    check("POST /investor/intents", r.status_code == 200, f"[{r.status_code}]")
    intent = r.json()
    check("intent status=submitted", intent.get("status") == "submitted")
    check("intent auto-attached to open round", bool(intent.get("round_id")))

    # validations
    r = await inv_client.post(f"{BASE}/api/investor/intents",
                              json={"asset_id": ASSET_ID, "amount": 10})
    check("intent below min_ticket -> 400", r.status_code == 400, f"[{r.status_code}]")
    r = await inv_client.post(f"{BASE}/api/investor/intents",
                              json={"asset_id": "nope", "amount": AMOUNT})
    check("intent unknown asset -> 404", r.status_code == 404, f"[{r.status_code}]")

    # legacy alias writes to the same canonical registry
    r = await inv_client.post(f"{BASE}/api/investor/intent",
                              json={"asset_id": ASSET_ID, "amount": AMOUNT})
    check("legacy POST /investor/intent alias", r.status_code == 200, f"[{r.status_code}]")
    legacy_intent_id = r.json().get("id")
    in_canonical = await db.lumen_investor_intents.find_one({"id": legacy_intent_id})
    check("legacy alias lands in lumen_investor_intents", bool(in_canonical))

    # 2. my intents
    r = await inv_client.get(f"{BASE}/api/investor/intents")
    items = r.json().get("items", [])
    check("GET /investor/intents lists mine",
          any(i["id"] == intent["id"] for i in items), f"-> {len(items)} items")

    # 3. admin list + auth guards
    r = await adm_client.get(f"{BASE}/api/admin/intents?status=submitted")
    adm_items = r.json().get("items", [])
    check("GET /admin/intents?status=submitted",
          any(i["id"] == intent["id"] for i in adm_items))
    r = await inv_client.get(f"{BASE}/api/admin/intents")
    check("admin intents blocked for investor -> 403", r.status_code == 403, f"[{r.status_code}]")

    # 4. approve → investment (contract_pending, Sprint 4 legal gate)
    #    → investor signs contract → active → ownership + funding
    r = await adm_client.post(f"{BASE}/api/admin/intents/{intent['id']}/approve",
                              json={"note": "smoke approve"})
    check("POST /admin/intents/{id}/approve", r.status_code == 200, f"[{r.status_code}]")
    res = r.json()
    investment = res.get("investment") or {}
    check("investment created status=contract_pending (legal gate)",
          investment.get("status") == "contract_pending")
    check("investment history recorded",
          isinstance(investment.get("history"), list) and len(investment["history"]) >= 1)
    contract = res.get("contract") or {}
    check("contract auto-generated on approve", bool(contract.get("id")))
    check("approve response: contract_required flag", res.get("contract_required") is True)
    check("no ownership before contract signed", res.get("ownership") is None)

    # Electronic Acceptance → Sprint 6 awaiting_payment (was: active in Sprint 4)
    r = await inv_client.post(f"{BASE}/api/investor/contracts/{contract['id']}/sign",
                              json={"agree": True})
    check("POST /investor/contracts/{id}/sign", r.status_code == 200, f"[{r.status_code}]")
    check("sign opens payment_request (Sprint 6)",
          r.json().get("investment_status") == "awaiting_payment",
          f"-> {r.json().get('investment_status')}")
    own_doc = await db.lumen_ownerships.find_one({"investor_id": uid, "asset_id": ASSET_ID})
    check("no ownership yet (awaiting payment)",
          float((own_doc or {}).get("units") or 0) < units_before + AMOUNT - 0.01)

    # Sprint 6: admin confirms the payment to activate the investment
    inv_id_real = investment.get("id")
    inv_doc = await db.lumen_investments.find_one({"id": inv_id_real})
    pr_id = inv_doc.get("payment_request_id")
    check("payment_request_id linked on investment", bool(pr_id))
    # upload a dummy proof + submit
    r = await inv_client.post(
        f"{BASE}/api/investor/payments/{pr_id}/proof",
        files={"file": ("proof.pdf", b"%PDF-1.4\n%fake\n%%EOF", "application/pdf")},
    )
    check("upload proof -> 200", r.status_code == 200, f"[{r.status_code}]")
    r = await inv_client.post(f"{BASE}/api/investor/payments/{pr_id}/submit",
                              json={"payment_method": "bank_transfer"})
    check("submit payment -> paid", r.json().get("status") == "paid")
    r = await adm_client.post(f"{BASE}/api/admin/payments/{pr_id}/confirm",
                              json={"note": "smoke confirm"})
    check("admin confirm -> 200", r.status_code == 200, f"[{r.status_code}]")
    check("investment now active after confirm",
          r.json().get("investment_status") == "active")
    own_doc = await db.lumen_ownerships.find_one({"investor_id": uid, "asset_id": ASSET_ID})
    check("ownership upserted (after confirm)",
          float((own_doc or {}).get("units") or 0) >= units_before + AMOUNT - 0.01)

    # idempotency
    r = await adm_client.post(f"{BASE}/api/admin/intents/{intent['id']}/approve", json={})
    check("double approve -> 409", r.status_code == 409, f"[{r.status_code}]")

    # intent converted
    doc = await db.lumen_investor_intents.find_one({"id": intent["id"]})
    check("intent converted + linked",
          doc.get("status") == "converted"
          and doc.get("converted_investment_id") == investment.get("id"))

    # 5. asset funding progress
    asset_after = await db.lumen_assets.find_one({"id": ASSET_ID})
    raised_after = float(asset_after.get("raised_amount") or 0)
    check("asset.raised_amount increased by amount",
          abs(raised_after - (raised_before + AMOUNT)) < 0.01,
          f"-> {raised_before} → {raised_after}")
    check("legacy mirror `raised` synced",
          abs(float(asset_after.get("raised") or 0) - raised_after) < 0.01)

    # round progress
    rnd = await db.lumen_investment_rounds.find_one({"id": intent.get("round_id")})
    check("round.raised_amount updated", float(rnd.get("raised_amount") or 0) >= AMOUNT)

    # 6. reject flow (the legacy-alias intent)
    r = await adm_client.post(f"{BASE}/api/admin/intents/{legacy_intent_id}/reject",
                              json={"note": "smoke reject"})
    check("POST /admin/intents/{id}/reject", r.status_code == 200, f"[{r.status_code}]")
    doc = await db.lumen_investor_intents.find_one({"id": legacy_intent_id})
    check("rejected intent persisted", doc.get("status") == "rejected")

    # 7. portfolio from real registry
    r = await inv_client.get(f"{BASE}/api/investor/portfolio")
    p = r.json()
    check("GET /investor/portfolio", r.status_code == 200, f"[{r.status_code}]")
    check("portfolio includes ownerships registry",
          isinstance(p.get("ownerships"), list) and len(p["ownerships"]) >= 1)
    inv_in_portfolio = [i for i in p.get("investments", []) if i.get("id") == investment.get("id")]
    check("new investment visible in portfolio", len(inv_in_portfolio) == 1)
    if inv_in_portfolio:
        check("portfolio share_percent from ownership registry",
              float(inv_in_portfolio[0].get("share_percent") or 0) > 0)
    check("portfolio summary.active_count > 0",
          (p.get("summary") or {}).get("active_count", 0) > 0)

    # 8. ownership endpoints
    r = await inv_client.get(f"{BASE}/api/investor/ownerships")
    check("GET /investor/ownerships", r.status_code == 200 and r.json().get("total", 0) >= 1)
    r = await adm_client.get(f"{BASE}/api/admin/ownerships?asset_id={ASSET_ID}")
    check("GET /admin/ownerships", r.status_code == 200 and r.json().get("total", 0) >= 1)

    # 9. investment detail + history
    r = await inv_client.get(f"{BASE}/api/investor/investments/{investment['id']}")
    check("GET /investor/investments/{id} detail+history",
          r.status_code == 200 and isinstance(r.json().get("history"), list))

    # ── cleanup: revert smoke artefacts so demo data stays stable ────────────
    await db.lumen_signatures.delete_many({"contract_id": contract.get("id")})
    await db.lumen_contracts.delete_many({"id": contract.get("id")})
    await db.lumen_investments.delete_one({"id": investment.get("id")})
    await db.lumen_investor_intents.delete_many({"id": {"$in": [intent["id"], legacy_intent_id]}})
    # rebuild ownership + funding after removal (self-healing engines)
    from lumen_investment_core import _upsert_ownership, _recompute_asset_funding, _update_round_progress
    await _upsert_ownership(uid, ASSET_ID, None)
    await _recompute_asset_funding(ASSET_ID)
    await _update_round_progress(intent.get("round_id"))
    asset_final = await db.lumen_assets.find_one({"id": ASSET_ID})
    check("cleanup: funding restored",
          abs(float(asset_final.get("raised_amount") or 0) - raised_before) < 0.01,
          f"-> {asset_final.get('raised_amount')}")

    await inv_client.aclose()
    await adm_client.aclose()

    print()
    if failures:
        print(f"RESULT: FAIL ({len(failures)}): {failures}")
        return 1
    print("RESULT: ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
