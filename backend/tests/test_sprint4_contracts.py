"""
Sprint 4 smoke test — LUMEN Contracts & Legal Layer.

Legal chain under test:

    KYC → Investment Approved → Contract Generated → Contract Signed → Active

Covers:
  * default templates seeded (3 kinds) + admin template CRUD (create / patch /
    version bump / validation)
  * intent approve → contract auto-generated (status `sent`),
    investment parked as `contract_pending` (KYC already approved)
  * investor registry: GET /investor/contracts, detail marks `viewed`
  * sign validations: agree required (400), foreign investor (403),
    double sign (409), cancelled contract not signable (409)
  * Electronic Acceptance: signature record (timestamp / IP / UA) + audit
  * PDF render: owner / admin 200 (application/pdf), foreign investor 403
  * activation: sign + KYC ok → investment active, ownership + funding update
  * KYC-unapproved investor: sign FIRST → investment stays `kyc_pending`;
    KYC approve afterwards → auto-activation (signed contract)
  * admin registry: list + counts, detail + signatures, cancel rules
    (reason required, signed contract not cancellable, cancel kills the
    linked investment)
  * access rights: investor blocked from all /admin/contract* endpoints
  * cleanup — demo data and funding restored

Run:  cd /app/backend && python tests/test_sprint4_contracts.py
"""
import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

BASE = "http://localhost:8001"
ASSET_ID = "asset-podilskyi"      # open, min_ticket=75000
AMOUNT = 100_000.0

failures = []


def check(name, ok, extra=""):
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name} {extra}")
    if not ok:
        failures.append(name)


def _set_cookie(client: httpx.AsyncClient, resp: httpx.Response) -> None:
    token = resp.cookies.get("session_token")
    assert token, "no session_token cookie returned"
    client.cookies.set("session_token", token)


async def login_quick(client: httpx.AsyncClient, email: str) -> None:
    r = await client.post(f"{BASE}/api/auth/quick", json={"email": email})
    assert r.status_code == 200, f"quick login {email}: {r.status_code}"
    _set_cookie(client, r)


async def onboard(client: httpx.AsyncClient, name: str) -> str:
    """Create a fresh investor; returns user_id."""
    email = f"sprint4-{uuid.uuid4().hex[:8]}@test.lumen"
    r = await client.post(f"{BASE}/api/auth/onboarding",
                          json={"email": email, "name": name, "role": "client"})
    assert r.status_code == 200, f"onboarding: {r.status_code}"
    _set_cookie(client, r)
    me = (await client.get(f"{BASE}/api/auth/me")).json()
    return me.get("user_id") or me.get("id")


async def fill_and_submit_kyc(client: httpx.AsyncClient) -> None:
    """Fill the profile + upload the 2 required documents + submit."""
    r = await client.patch(f"{BASE}/api/investor/profile", json={
        "full_name": "Петренко Петро Петрович",
        "date_of_birth": "1988-08-08",
        "phone": "+380501234567",
        "country": "UA",
        "residency_country": "UA",
        "tax_id": "3211501234",
        "iban": "UA213223130000026007233566001",
        "bank_name": "ПриватБанк",
        "risk_profile": "balanced",
    })
    assert r.status_code == 200, f"profile patch: {r.status_code}"
    for doc_type, fname in (("passport", "p.pdf"), ("tax_id", "t.pdf")):
        r = await client.post(f"{BASE}/api/investor/kyc/documents",
                              data={"doc_type": doc_type},
                              files={"file": (fname, b"%PDF-1.4 sprint4", "application/pdf")})
        assert r.status_code == 200, f"doc upload {doc_type}: {r.status_code}"
    r = await client.post(f"{BASE}/api/investor/kyc/submit")
    assert r.status_code == 200, f"kyc submit: {r.status_code}"


async def main() -> int:
    mongo = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = mongo[os.environ["DB_NAME"]]

    # ── actors ────────────────────────────────────────────────────────────────
    adm = httpx.AsyncClient(timeout=30)
    await login_quick(adm, "admin@atlas.dev")

    inv_a = httpx.AsyncClient(timeout=30)          # main investor (KYC approved)
    uid_a = await onboard(inv_a, "Sprint4 Investor A")

    foreign = httpx.AsyncClient(timeout=30)        # foreign investor (demo)
    await login_quick(foreign, "client@atlas.dev")

    print("== Sprint 4: Contracts & Legal Layer ==")

    # ── 0. templates seeded ───────────────────────────────────────────────────
    r = await adm.get(f"{BASE}/api/admin/contract-templates")
    tpls = (r.json() or {}).get("items", [])
    kinds = {t.get("kind") for t in tpls}
    check("templates seeded (3 kinds)", r.status_code == 200 and
          {"investment_agreement", "spv_participation", "co_investment"} <= kinds,
          f"-> {sorted(kinds)}")

    # ── 1. KYC approve investor A (clean — no investments yet) ───────────────
    await fill_and_submit_kyc(inv_a)
    r = await adm.post(f"{BASE}/api/admin/kyc/{uid_a}/approve", json={"note": "sprint4"})
    check("setup: investor A KYC approved", r.status_code == 200, f"[{r.status_code}]")

    asset_before = await db.lumen_assets.find_one({"id": ASSET_ID})
    raised_before = float(asset_before.get("raised_amount") or 0)

    # ── 2. approve intent → contract generated, investment contract_pending ──
    r = await inv_a.post(f"{BASE}/api/investor/intents",
                         json={"asset_id": ASSET_ID, "amount": AMOUNT, "note": "smoke-sprint4"})
    intent = r.json()
    check("investor A submits intent", r.status_code == 200, f"[{r.status_code}]")

    r = await adm.post(f"{BASE}/api/admin/intents/{intent['id']}/approve", json={})
    res = r.json()
    investment = res.get("investment") or {}
    contract_ref = res.get("contract") or {}
    check("approve → investment contract_pending",
          r.status_code == 200 and investment.get("status") == "contract_pending")
    check("approve → contract auto-generated", bool(contract_ref.get("id")))
    check("approve response: contract_required flag", res.get("contract_required") is True)
    check("no ownership before signature", res.get("ownership") is None)
    cid = contract_ref.get("id")

    c_doc = await db.lumen_contracts.find_one({"id": cid})
    check("contract status=sent after generation", (c_doc or {}).get("status") == "sent")
    check("contract number assigned (LMN-…)",
          str((c_doc or {}).get("number") or "").startswith("LMN-"))
    check("placeholders resolved in body",
          "{{" not in ((c_doc or {}).get("body_text") or "x"))
    check("investment linked to contract",
          bool(await db.lumen_investments.find_one({"id": investment["id"], "contract_id": cid})))

    # ── 3. investor registry ─────────────────────────────────────────────────
    r = await inv_a.get(f"{BASE}/api/investor/contracts")
    items = (r.json() or {}).get("items", [])
    check("GET /investor/contracts lists mine",
          r.status_code == 200 and any(c["id"] == cid for c in items))

    r = await inv_a.get(f"{BASE}/api/investor/contracts/{cid}")
    det = r.json()
    check("GET /investor/contracts/{id} detail", r.status_code == 200, f"[{r.status_code}]")
    check("first open marks viewed", det.get("status") == "viewed")
    check("detail exposes investment_status",
          det.get("investment_status") == "contract_pending")
    r = await foreign.get(f"{BASE}/api/investor/contracts/{cid}")
    check("foreign investor detail -> 403", r.status_code == 403, f"[{r.status_code}]")
    r = await inv_a.get(f"{BASE}/api/investor/contracts/nonexistent")
    check("unknown contract -> 404", r.status_code == 404, f"[{r.status_code}]")

    # ── 4. PDF before signing ────────────────────────────────────────────────
    r = await inv_a.get(f"{BASE}/api/contracts/{cid}/pdf")
    check("owner downloads PDF",
          r.status_code == 200 and r.headers.get("content-type", "").startswith("application/pdf")
          and r.content[:4] == b"%PDF")
    r = await foreign.get(f"{BASE}/api/contracts/{cid}/pdf")
    check("foreign investor PDF -> 403", r.status_code == 403, f"[{r.status_code}]")
    r = await adm.get(f"{BASE}/api/contracts/{cid}/pdf")
    check("admin downloads PDF", r.status_code == 200, f"[{r.status_code}]")

    # ── 5. sign validations ──────────────────────────────────────────────────
    r = await inv_a.post(f"{BASE}/api/investor/contracts/{cid}/sign", json={"agree": False})
    check("sign without agree -> 400", r.status_code == 400, f"[{r.status_code}]")
    r = await foreign.post(f"{BASE}/api/investor/contracts/{cid}/sign", json={"agree": True})
    check("foreign investor sign -> 403", r.status_code == 403, f"[{r.status_code}]")

    # ── 6. Electronic Acceptance → Sprint 6: opens payment_request ────────────
    r = await inv_a.post(f"{BASE}/api/investor/contracts/{cid}/sign", json={"agree": True})
    sig_res = r.json()
    check("sign contract (agree=true)", r.status_code == 200, f"[{r.status_code}]")
    check("sign → investment awaiting_payment (Sprint 6)",
          sig_res.get("investment_status") == "awaiting_payment")
    check("sign response carries signature audit",
          bool((sig_res.get("signature") or {}).get("signed_at")))

    sig_doc = await db.lumen_signatures.find_one({"contract_id": cid, "status": "signed"})
    check("signature persisted with IP + UA",
          sig_doc is not None and bool(sig_doc.get("ip")) and bool(sig_doc.get("user_agent")))

    inv_doc = await db.lumen_investments.find_one({"id": investment["id"]})
    check("investment awaiting_payment in registry (Sprint 6)",
          (inv_doc or {}).get("status") == "awaiting_payment")
    own = await db.lumen_ownerships.find_one({"investor_id": uid_a, "asset_id": ASSET_ID})
    check("no ownership yet (awaiting payment)",
          own is None or float(own.get("units") or 0) < AMOUNT - 0.01)
    asset_after = await db.lumen_assets.find_one({"id": ASSET_ID})
    check("asset.raised_amount NOT yet increased (awaiting payment)",
          abs(float(asset_after.get("raised_amount") or 0) - raised_before) < 0.01,
          f"-> {asset_after.get('raised_amount')}")

    # Sprint 6: confirm payment to actually activate
    pr_id_a = (inv_doc or {}).get("payment_request_id")
    check("payment_request_id linked", bool(pr_id_a))
    await inv_a.post(f"{BASE}/api/investor/payments/{pr_id_a}/proof",
                     files={"file": ("p.pdf", b"%PDF-1.4\n%fake\n%%EOF", "application/pdf")})
    await inv_a.post(f"{BASE}/api/investor/payments/{pr_id_a}/submit",
                     json={"payment_method": "bank_transfer"})
    r = await adm.post(f"{BASE}/api/admin/payments/{pr_id_a}/confirm", json={})
    check("admin confirm payment → 200", r.status_code == 200, f"[{r.status_code}]")
    inv_doc = await db.lumen_investments.find_one({"id": investment["id"]})
    check("investment active after confirm", (inv_doc or {}).get("status") == "active")
    own = await db.lumen_ownerships.find_one({"investor_id": uid_a, "asset_id": ASSET_ID})
    check("ownership created after confirm",
          own is not None and abs(float(own.get("units") or 0) - AMOUNT) < 0.01)
    asset_after = await db.lumen_assets.find_one({"id": ASSET_ID})
    check("asset.raised_amount increased after confirm",
          abs(float(asset_after.get("raised_amount") or 0) - (raised_before + AMOUNT)) < 0.01,
          f"-> {asset_after.get('raised_amount')}")

    r = await inv_a.post(f"{BASE}/api/investor/contracts/{cid}/sign", json={"agree": True})
    check("double sign -> 409", r.status_code == 409, f"[{r.status_code}]")

    r = await inv_a.get(f"{BASE}/api/investor/contracts/{cid}")
    det = r.json()
    check("detail shows signed + signature", det.get("status") == "signed"
          and bool((det.get("signature") or {}).get("signed_at")))
    r = await inv_a.get(f"{BASE}/api/contracts/{cid}/pdf")
    check("signed PDF renders", r.status_code == 200 and r.content[:4] == b"%PDF")

    # ── 7. admin registry ────────────────────────────────────────────────────
    r = await adm.get(f"{BASE}/api/admin/contracts")
    body = r.json()
    check("GET /admin/contracts", r.status_code == 200
          and any(c["id"] == cid for c in body.get("items", [])))
    check("admin registry exposes counts",
          isinstance(body.get("counts"), dict) and body["counts"].get("signed", 0) >= 1)
    r = await adm.get(f"{BASE}/api/admin/contracts?status=bogus")
    check("admin registry invalid status -> 400", r.status_code == 400, f"[{r.status_code}]")
    r = await adm.get(f"{BASE}/api/admin/contracts?status=signed")
    check("admin registry status filter works",
          r.status_code == 200 and all(c["status"] == "signed" for c in r.json().get("items", [])))

    r = await adm.get(f"{BASE}/api/admin/contracts/{cid}")
    adm_det = r.json()
    check("admin detail + signatures", r.status_code == 200
          and len(adm_det.get("signatures") or []) >= 1
          and adm_det.get("investment_status") == "active")

    r = await adm.post(f"{BASE}/api/admin/contracts/{cid}/cancel", json={"reason": "test"})
    check("cancel SIGNED contract -> 409", r.status_code == 409, f"[{r.status_code}]")

    # investor blocked from admin surface
    for path in ("/api/admin/contracts", f"/api/admin/contracts/{cid}",
                 "/api/admin/contract-templates"):
        r = await inv_a.get(f"{BASE}{path}")
        if r.status_code not in (401, 403):
            check(f"investor blocked from {path}", False, f"[{r.status_code}]")
            break
    else:
        check("investor blocked from admin contract endpoints", True)

    # ── 8. cancel flow (second contract) ─────────────────────────────────────
    r = await inv_a.post(f"{BASE}/api/investor/intents",
                         json={"asset_id": ASSET_ID, "amount": AMOUNT, "note": "smoke-sprint4-2"})
    intent2 = r.json()
    r = await adm.post(f"{BASE}/api/admin/intents/{intent2['id']}/approve", json={})
    res2 = r.json()
    inv2 = res2.get("investment") or {}
    cid2 = (res2.get("contract") or {}).get("id")
    check("second approve → fresh contract", bool(cid2) and cid2 != cid)

    r = await adm.post(f"{BASE}/api/admin/contracts/{cid2}/cancel", json={"reason": "   "})
    check("cancel blank reason -> 400/422", r.status_code in (400, 422), f"[{r.status_code}]")
    r = await adm.post(f"{BASE}/api/admin/contracts/{cid2}/cancel",
                       json={"reason": "Помилкова заявка (smoke)"})
    check("cancel with reason", r.status_code == 200, f"[{r.status_code}]")

    c2 = await db.lumen_contracts.find_one({"id": cid2})
    check("contract cancelled + reason stored",
          (c2 or {}).get("status") == "cancelled"
          and bool((c2 or {}).get("cancel_reason")))
    inv2_doc = await db.lumen_investments.find_one({"id": inv2.get("id")})
    check("linked investment cancelled too", (inv2_doc or {}).get("status") == "cancelled")
    r = await inv_a.post(f"{BASE}/api/investor/contracts/{cid2}/sign", json={"agree": True})
    check("sign cancelled contract -> 409", r.status_code == 409, f"[{r.status_code}]")

    # funding untouched by the cancelled position
    asset_now = await db.lumen_assets.find_one({"id": ASSET_ID})
    check("funding untouched by cancelled contract",
          abs(float(asset_now.get("raised_amount") or 0) - (raised_before + AMOUNT)) < 0.01)

    # ── 9. KYC-unapproved investor: sign first, then KYC ─────────────────────
    inv_c = httpx.AsyncClient(timeout=30)
    uid_c = await onboard(inv_c, "Sprint4 Investor C")

    r = await inv_c.post(f"{BASE}/api/investor/intents",
                         json={"asset_id": ASSET_ID, "amount": AMOUNT, "note": "smoke-sprint4-c"})
    intent_c = r.json()
    r = await adm.post(f"{BASE}/api/admin/intents/{intent_c['id']}/approve", json={})
    res_c = r.json()
    inv_c_doc = res_c.get("investment") or {}
    cid_c = (res_c.get("contract") or {}).get("id")
    check("no-KYC approve → investment kyc_pending",
          inv_c_doc.get("status") == "kyc_pending" and res_c.get("kyc_required") is True)
    check("contract generated even before KYC", bool(cid_c))

    r = await inv_c.post(f"{BASE}/api/investor/contracts/{cid_c}/sign", json={"agree": True})
    sig_c = r.json()
    check("sign before KYC allowed", r.status_code == 200, f"[{r.status_code}]")
    check("…but investment stays kyc_pending (KYC gate)",
          sig_c.get("investment_status") == "kyc_pending"
          and sig_c.get("payment_requests_opened", 0) == 0)

    await fill_and_submit_kyc(inv_c)
    r = await adm.post(f"{BASE}/api/admin/kyc/{uid_c}/approve", json={})
    res_kyc = r.json()
    # Sprint 6: KYC approve no longer activates — it OPENS a payment_request.
    check("KYC approve opens payment_request for SIGNED investment",
          r.status_code == 200 and res_kyc.get("activated_investments", 0) >= 1,
          f"-> {res_kyc.get('activated_investments')}")
    inv_c_after = await db.lumen_investments.find_one({"id": inv_c_doc.get("id")})
    check("investor C investment awaiting_payment (Sprint 6)",
          (inv_c_after or {}).get("status") == "awaiting_payment")

    # ── 10. template CRUD ────────────────────────────────────────────────────
    r = await adm.post(f"{BASE}/api/admin/contract-templates", json={"name": "x"})
    check("create template w/o body -> 400", r.status_code == 400, f"[{r.status_code}]")
    r = await adm.post(f"{BASE}/api/admin/contract-templates",
                       json={"name": "Smoke шаблон", "kind": "co_investment",
                             "body_text": "# Тест {{investor_name}}"})
    tpl = r.json()
    check("create template", r.status_code == 200 and tpl.get("version") == 1)
    r = await adm.patch(f"{BASE}/api/admin/contract-templates/{tpl['id']}",
                        json={"body_text": "# Тест v2 {{investor_name}}"})
    check("patch body bumps version", r.status_code == 200 and r.json().get("version") == 2)
    r = await adm.patch(f"{BASE}/api/admin/contract-templates/{tpl['id']}",
                        json={"kind": "bogus"})
    check("patch invalid kind -> 400", r.status_code == 400, f"[{r.status_code}]")
    r = await adm.patch(f"{BASE}/api/admin/contract-templates/nonexistent",
                        json={"name": "x"})
    check("patch unknown template -> 404", r.status_code == 404, f"[{r.status_code}]")
    await db.lumen_contract_templates.delete_one({"id": tpl["id"]})

    # ── cleanup ──────────────────────────────────────────────────────────────
    for uid in (uid_a, uid_c):
        c_ids = [c["id"] async for c in db.lumen_contracts.find({"investor_id": uid})]
        await db.lumen_signatures.delete_many({"contract_id": {"$in": c_ids}})
        await db.lumen_contracts.delete_many({"investor_id": uid})
        await db.lumen_investments.delete_many({"investor_id": uid})
        await db.lumen_investor_intents.delete_many({"investor_id": uid})
        await db.lumen_ownerships.delete_many({"investor_id": uid})
        async for d in db.lumen_kyc_documents.find({"investor_id": uid}):
            sp = d.get("storage_path")
            if sp and os.path.exists(sp):
                try:
                    os.remove(sp)
                except OSError:
                    pass
        await db.lumen_kyc_documents.delete_many({"investor_id": uid})
        await db.lumen_investor_profiles.delete_many({"user_id": uid})
        await db.lumen_notifications.delete_many({"investor_id": uid})
        await db.users.delete_one({"user_id": uid})
        await db.user_sessions.delete_many({"user_id": uid})

    from lumen_investment_core import _recompute_asset_funding, _update_round_progress
    await _recompute_asset_funding(ASSET_ID)
    await _update_round_progress(intent.get("round_id"))
    asset_final = await db.lumen_assets.find_one({"id": ASSET_ID})
    check("cleanup: funding restored",
          abs(float(asset_final.get("raised_amount") or 0) - raised_before) < 0.01,
          f"-> {asset_final.get('raised_amount')}")

    await adm.aclose()
    await inv_a.aclose()
    await inv_c.aclose()
    await foreign.aclose()

    print()
    if failures:
        print(f"RESULT: FAIL ({len(failures)}): {failures}")
        return 1
    print("RESULT: ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
