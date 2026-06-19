"""
Sprint 3 smoke test — LUMEN KYC + Investor Profile.

Covers (per Definition of Done):
  * profile auto-creation + PATCH lifecycle (not_started → draft)
  * field validation (risk_profile, accreditation 'verified' admin-only)
  * KYC documents: upload / list / download / delete + type validation
  * submission gating: completeness check, edit-lock after submit
  * access rights: investor vs admin vs foreign investor
  * admin queue / card / approve / reject (reason REQUIRED)
  * Investment Core integration (Sprint 4 legal chain):
        intent approve while KYC not approved → investment `kyc_pending`
        (no ownership / no funding change)
        KYC approve → unsigned investments move to `contract_pending`
        contract sign (Electronic Acceptance) → investment activates
        (ownership + funding recomputed)
  * cleanup — demo data stays untouched

Run:  cd /app/backend && python tests/test_sprint3_kyc.py
"""
import asyncio
import io
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


async def main() -> int:
    mongo = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = mongo[os.environ["DB_NAME"]]

    # ── actors ────────────────────────────────────────────────────────────────
    # fresh investor with NO KYC (created via onboarding so demo data is untouched)
    test_email = f"kyc-smoke-{uuid.uuid4().hex[:8]}@test.lumen"
    inv = httpx.AsyncClient(timeout=30)
    r = await inv.post(f"{BASE}/api/auth/onboarding",
                       json={"email": test_email, "name": "KYC Smoke", "role": "client"})
    check("setup: onboarding fresh investor", r.status_code == 200, f"[{r.status_code}]")
    _set_cookie(inv, r)
    me = (await inv.get(f"{BASE}/api/auth/me")).json()
    uid = me.get("user_id") or me.get("id")
    check("setup: fresh investor session", bool(uid))

    adm = httpx.AsyncClient(timeout=30)
    await login_quick(adm, "admin@atlas.dev")

    other = httpx.AsyncClient(timeout=30)   # foreign investor (KYC-approved demo)
    await login_quick(other, "client@atlas.dev")

    print("== Sprint 3: KYC + Investor Profile ==")

    # ── 1. profile lifecycle ─────────────────────────────────────────────────
    r = await inv.get(f"{BASE}/api/investor/profile")
    p = r.json()
    check("GET /investor/profile auto-creates", r.status_code == 200, f"[{r.status_code}]")
    check("initial kyc_status=not_started", p.get("kyc_status") == "not_started")
    check("profile exposes missing_for_submit",
          isinstance(p.get("missing_for_submit"), list) and len(p["missing_for_submit"]) >= 5)
    check("profile can_edit=true initially", p.get("can_edit") is True)

    # invalid values rejected
    r = await inv.patch(f"{BASE}/api/investor/profile", json={"risk_profile": "yolo"})
    check("PATCH invalid risk_profile -> 400", r.status_code == 400, f"[{r.status_code}]")
    r = await inv.patch(f"{BASE}/api/investor/profile", json={"accreditation_status": "verified"})
    check("PATCH accreditation=verified (admin-only) -> 400", r.status_code == 400, f"[{r.status_code}]")
    r = await inv.patch(f"{BASE}/api/investor/profile", json={})
    check("PATCH empty payload -> 400", r.status_code == 400, f"[{r.status_code}]")

    # fill the profile → moves to draft
    r = await inv.patch(f"{BASE}/api/investor/profile", json={
        "full_name": "Іваненко Іван Іванович",
        "date_of_birth": "1990-04-12",
        "phone": "+380501112233",
        "country": "UA",
        "residency_country": "UA",
        "tax_id": "3184501234",
        "iban": "UA213223130000026007233566001",
        "bank_name": "ПриватБанк",
        "risk_profile": "balanced",
        "accreditation_status": "self_declared",
    })
    p = r.json()
    check("PATCH valid profile fields", r.status_code == 200, f"[{r.status_code}]")
    check("editing moves not_started -> draft", p.get("kyc_status") == "draft")

    # legacy mirror synced
    u = await db.users.find_one({"user_id": uid}, {"kyc_status": 1})
    check("users.kyc_status mirror = draft", (u or {}).get("kyc_status") == "draft")

    # ── 2. KYC documents ─────────────────────────────────────────────────────
    r = await inv.post(f"{BASE}/api/investor/kyc/documents",
                       data={"doc_type": "alien_card"},
                       files={"file": ("x.pdf", b"%PDF-1.4 smoke", "application/pdf")})
    check("upload unknown doc_type -> 400", r.status_code == 400, f"[{r.status_code}]")

    r = await inv.post(f"{BASE}/api/investor/kyc/documents",
                       data={"doc_type": "passport"},
                       files={"file": ("empty.pdf", b"", "application/pdf")})
    check("upload empty file -> 400", r.status_code == 400, f"[{r.status_code}]")

    r = await inv.post(f"{BASE}/api/investor/kyc/documents",
                       data={"doc_type": "passport"},
                       files={"file": ("passport.pdf", b"%PDF-1.4 passport-smoke", "application/pdf")})
    check("upload passport", r.status_code == 200, f"[{r.status_code}]")
    passport_doc = r.json()
    check("doc response hides storage_path", "storage_path" not in passport_doc)

    r = await inv.post(f"{BASE}/api/investor/kyc/documents",
                       data={"doc_type": "tax_id"},
                       files={"file": ("inn.png", b"\x89PNG smoke", "image/png")})
    check("upload tax_id", r.status_code == 200, f"[{r.status_code}]")
    tax_doc = r.json()

    r = await inv.get(f"{BASE}/api/investor/kyc/documents")
    check("GET documents -> 2", r.status_code == 200 and r.json().get("total") == 2)

    # download: owner OK, foreign investor 403, admin OK
    r = await inv.get(f"{BASE}/api/kyc/documents/{passport_doc['id']}/file")
    check("owner downloads own file", r.status_code == 200, f"[{r.status_code}]")
    r = await other.get(f"{BASE}/api/kyc/documents/{passport_doc['id']}/file")
    check("foreign investor download -> 403", r.status_code == 403, f"[{r.status_code}]")
    r = await adm.get(f"{BASE}/api/kyc/documents/{passport_doc['id']}/file")
    check("admin downloads file", r.status_code == 200, f"[{r.status_code}]")

    # delete foreign document forbidden
    r = await other.delete(f"{BASE}/api/investor/kyc/documents/{passport_doc['id']}")
    check("foreign delete document -> 403", r.status_code == 403, f"[{r.status_code}]")

    # delete + re-upload own document (allowed in draft)
    r = await inv.delete(f"{BASE}/api/investor/kyc/documents/{tax_doc['id']}")
    check("owner deletes own document (draft)", r.status_code == 200, f"[{r.status_code}]")
    r = await inv.post(f"{BASE}/api/investor/kyc/documents",
                       data={"doc_type": "tax_id"},
                       files={"file": ("inn2.png", b"\x89PNG smoke2", "image/png")})
    check("re-upload tax_id", r.status_code == 200, f"[{r.status_code}]")

    # ── 3. soft-mode: intent approved BEFORE KYC → kyc_pending ───────────────
    asset_before = await db.lumen_assets.find_one({"id": ASSET_ID})
    raised_before = float(asset_before.get("raised_amount") or 0)

    r = await inv.post(f"{BASE}/api/investor/intents",
                       json={"asset_id": ASSET_ID, "amount": AMOUNT, "note": "smoke-sprint3"})
    check("investor without KYC can submit intent", r.status_code == 200, f"[{r.status_code}]")
    intent = r.json()

    r = await adm.post(f"{BASE}/api/admin/intents/{intent['id']}/approve", json={})
    res = r.json()
    check("admin approves intent (KYC not approved)", r.status_code == 200, f"[{r.status_code}]")
    investment = res.get("investment") or {}
    check("investment parked as kyc_pending", investment.get("status") == "kyc_pending")
    check("approve response flags kyc_required", res.get("kyc_required") is True)
    check("no ownership before KYC", res.get("ownership") is None)

    own = await db.lumen_ownerships.find_one({"investor_id": uid, "asset_id": ASSET_ID})
    check("ownership registry NOT touched", own is None or float(own.get("units") or 0) == 0)
    asset_mid = await db.lumen_assets.find_one({"id": ASSET_ID})
    check("asset.raised_amount unchanged while kyc_pending",
          abs(float(asset_mid.get("raised_amount") or 0) - raised_before) < 0.01,
          f"-> {asset_mid.get('raised_amount')}")

    # kyc_pending visible in investor portfolio
    r = await inv.get(f"{BASE}/api/investor/portfolio")
    port = r.json()
    pend = [i for i in port.get("investments", []) if i.get("id") == investment.get("id")]
    check("kyc_pending investment visible in portfolio",
          len(pend) == 1 and pend[0].get("status") == "kyc_pending")
    check("kyc_pending NOT counted in summary.active_count",
          (port.get("summary") or {}).get("active_count", 0) == 0)

    # ── 4. submission gating ─────────────────────────────────────────────────
    # temporarily remove tax_id field to prove completeness validation
    await db.lumen_investor_profiles.update_one({"user_id": uid}, {"$set": {"tax_id": None}})
    r = await inv.post(f"{BASE}/api/investor/kyc/submit")
    body = r.json() or {}
    # error envelope: {ok, code, message, details:{missing}} (details preferred,
    # raw FastAPI `detail` kept as fallback for direct uvicorn runs)
    det = body.get("details") or body.get("detail") or {}
    check("submit incomplete -> 400 + missing list",
          r.status_code == 400 and "tax_id" in (det.get("missing") or []),
          f"[{r.status_code}] {det.get('missing')}")
    await db.lumen_investor_profiles.update_one({"user_id": uid}, {"$set": {"tax_id": "3184501234"}})

    r = await inv.post(f"{BASE}/api/investor/kyc/submit")
    check("submit complete profile", r.status_code == 200 and r.json().get("kyc_status") == "submitted",
          f"[{r.status_code}]")

    # locked while under review
    r = await inv.patch(f"{BASE}/api/investor/profile", json={"phone": "+380999999999"})
    check("PATCH while submitted -> 409", r.status_code == 409, f"[{r.status_code}]")
    r = await inv.post(f"{BASE}/api/investor/kyc/documents",
                       data={"doc_type": "selfie"},
                       files={"file": ("s.png", b"\x89PNG s", "image/png")})
    check("upload while submitted -> 409", r.status_code == 409, f"[{r.status_code}]")
    r = await inv.delete(f"{BASE}/api/investor/kyc/documents/{passport_doc['id']}")
    check("delete doc while submitted -> 409", r.status_code == 409, f"[{r.status_code}]")
    r = await inv.post(f"{BASE}/api/investor/kyc/submit")
    check("double submit -> 409", r.status_code == 409, f"[{r.status_code}]")

    # ── 5. access rights on admin endpoints ──────────────────────────────────
    r = await inv.get(f"{BASE}/api/admin/kyc")
    check("investor blocked from /admin/kyc", r.status_code in (401, 403), f"[{r.status_code}]")
    r = await inv.post(f"{BASE}/api/admin/kyc/{uid}/approve", json={})
    check("investor cannot self-approve", r.status_code in (401, 403), f"[{r.status_code}]")

    # ── 6. admin queue + card ────────────────────────────────────────────────
    r = await adm.get(f"{BASE}/api/admin/kyc")
    q = r.json()
    check("GET /admin/kyc queue", r.status_code == 200, f"[{r.status_code}]")
    check("submitted investor in default queue",
          any(i.get("user_id") == uid for i in q.get("items", [])))
    check("queue exposes status counts",
          isinstance(q.get("counts"), dict) and q["counts"].get("submitted", 0) >= 1)

    r = await adm.get(f"{BASE}/api/admin/kyc?status=bogus")
    check("queue invalid status filter -> 400", r.status_code == 400, f"[{r.status_code}]")

    r = await adm.get(f"{BASE}/api/admin/kyc/{uid}")
    card = r.json()
    check("GET /admin/kyc/{id} card", r.status_code == 200, f"[{r.status_code}]")
    check("card includes documents", len(card.get("documents") or []) >= 2)
    check("card shows kyc_pending_investments", card.get("kyc_pending_investments", 0) >= 1)

    r = await adm.get(f"{BASE}/api/admin/kyc/nonexistent-user")
    check("card for unknown investor -> 404", r.status_code == 404, f"[{r.status_code}]")

    # ── 7. reject flow (reason required) ─────────────────────────────────────
    r = await adm.post(f"{BASE}/api/admin/kyc/{uid}/reject", json={})
    check("reject without reason -> 4xx", r.status_code in (400, 422), f"[{r.status_code}]")
    r = await adm.post(f"{BASE}/api/admin/kyc/{uid}/reject", json={"reason": "  "})
    check("reject with blank reason -> 400", r.status_code == 400, f"[{r.status_code}]")

    r = await adm.post(f"{BASE}/api/admin/kyc/{uid}/reject",
                       json={"reason": "Невідповідність даних паспорта"})
    check("reject with reason", r.status_code == 200, f"[{r.status_code}]")
    r = await inv.get(f"{BASE}/api/investor/profile")
    p = r.json()
    check("investor sees rejected + reason",
          p.get("kyc_status") == "rejected"
          and p.get("kyc_notes") == "Невідповідність даних паспорта")
    check("rejected profile editable again", p.get("can_edit") is True)

    # double-decision guard: not actionable anymore
    r = await adm.post(f"{BASE}/api/admin/kyc/{uid}/approve", json={})
    check("approve non-actionable (rejected) -> 409", r.status_code == 409, f"[{r.status_code}]")

    # ── 8. re-application + approve → auto-activation ────────────────────────
    r = await inv.patch(f"{BASE}/api/investor/profile", json={"phone": "+380671234567"})
    check("edit after reject -> draft again",
          r.status_code == 200 and r.json().get("kyc_status") == "draft", f"[{r.status_code}]")
    r = await inv.post(f"{BASE}/api/investor/kyc/submit")
    check("re-submit after fix", r.status_code == 200, f"[{r.status_code}]")

    r = await adm.post(f"{BASE}/api/admin/kyc/{uid}/approve",
                       json={"note": "ok, документи валідні"})
    res = r.json()
    check("admin approves KYC", r.status_code == 200, f"[{r.status_code}]")
    # Sprint 4 legal gate: KYC approve alone does NOT activate — the unsigned
    # investment moves to `contract_pending` and waits for the signature.
    check("KYC approve: unsigned investments NOT activated",
          res.get("activated_investments", 0) == 0,
          f"-> activated={res.get('activated_investments')}")
    check("KYC approve: investments moved to contract signing",
          res.get("contracts_awaiting_sign", 0) >= 1,
          f"-> awaiting={res.get('contracts_awaiting_sign')}")

    inv_doc = await db.lumen_investments.find_one({"id": investment["id"]})
    check("investment now contract_pending",
          (inv_doc or {}).get("status") == "contract_pending")
    check("transition appended to history",
          any(h.get("comment", "").startswith("KYC підтверджено")
              for h in (inv_doc or {}).get("history", [])))

    own = await db.lumen_ownerships.find_one({"investor_id": uid, "asset_id": ASSET_ID})
    check("ownership NOT created before contract signed",
          own is None or float(own.get("units") or 0) == 0)
    asset_mid2 = await db.lumen_assets.find_one({"id": ASSET_ID})
    check("asset.raised_amount unchanged before contract signed",
          abs(float(asset_mid2.get("raised_amount") or 0) - raised_before) < 0.01,
          f"-> {asset_mid2.get('raised_amount')}")

    # sign the contract (Electronic Acceptance) → Sprint 6 opens payment_request
    contract_id = (inv_doc or {}).get("contract_id")
    check("contract auto-generated on intent approve", bool(contract_id))
    r = await inv.post(f"{BASE}/api/investor/contracts/{contract_id}/sign",
                       json={"agree": True})
    check("investor signs contract", r.status_code == 200, f"[{r.status_code}]")

    inv_doc = await db.lumen_investments.find_one({"id": investment["id"]})
    check("investment now awaiting_payment (Sprint 6)",
          (inv_doc or {}).get("status") == "awaiting_payment")

    # Sprint 6 confirm payment
    pr_id_s3 = (inv_doc or {}).get("payment_request_id")
    await inv.post(f"{BASE}/api/investor/payments/{pr_id_s3}/proof",
                   files={"file": ("p.pdf", b"%PDF-1.4\n%fake\n%%EOF", "application/pdf")})
    await inv.post(f"{BASE}/api/investor/payments/{pr_id_s3}/submit",
                   json={"payment_method": "bank_transfer"})
    await adm.post(f"{BASE}/api/admin/payments/{pr_id_s3}/confirm", json={})

    inv_doc = await db.lumen_investments.find_one({"id": investment["id"]})
    check("investment active after payment confirm",
          (inv_doc or {}).get("status") == "active")
    own = await db.lumen_ownerships.find_one({"investor_id": uid, "asset_id": ASSET_ID})
    check("ownership created after activation",
          own is not None and abs(float(own.get("units") or 0) - AMOUNT) < 0.01)
    asset_after = await db.lumen_assets.find_one({"id": ASSET_ID})
    check("asset.raised_amount increased after activation",
          abs(float(asset_after.get("raised_amount") or 0) - (raised_before + AMOUNT)) < 0.01,
          f"-> {asset_after.get('raised_amount')}")

    r = await inv.get(f"{BASE}/api/investor/profile")
    p = r.json()
    check("profile approved + locked", p.get("kyc_status") == "approved" and p.get("can_edit") is False)
    u = await db.users.find_one({"user_id": uid}, {"kyc_status": 1})
    check("users.kyc_status mirror = approved", (u or {}).get("kyc_status") == "approved")

    # next intent of the SAME investor (KYC ok) → contract_pending immediately;
    # signing the fresh contract opens payment_request (Sprint 6 chain)
    r = await inv.post(f"{BASE}/api/investor/intents",
                       json={"asset_id": ASSET_ID, "amount": AMOUNT, "note": "smoke-sprint3-2"})
    intent2 = r.json()
    r = await adm.post(f"{BASE}/api/admin/intents/{intent2['id']}/approve", json={})
    res2 = r.json()
    check("post-KYC intent approve -> contract_pending (no KYC gate)",
          r.status_code == 200
          and (res2.get("investment") or {}).get("status") == "contract_pending"
          and res2.get("kyc_required") is False)
    contract2_id = (res2.get("contract") or {}).get("id")
    r = await inv.post(f"{BASE}/api/investor/contracts/{contract2_id}/sign",
                       json={"agree": True})
    check("post-KYC contract sign -> awaiting_payment (Sprint 6)",
          r.status_code == 200 and r.json().get("investment_status") == "awaiting_payment")

    # ── cleanup: remove all smoke artefacts, restore funding ─────────────────
    contract_ids = [c["id"] async for c in db.lumen_contracts.find({"investor_id": uid})]
    await db.lumen_signatures.delete_many({"contract_id": {"$in": contract_ids}})
    await db.lumen_contracts.delete_many({"investor_id": uid})
    await db.lumen_investments.delete_many({"investor_id": uid})
    await db.lumen_investor_intents.delete_many({"investor_id": uid})
    await db.lumen_ownerships.delete_many({"investor_id": uid})
    # remove uploaded files from disk
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

    await inv.aclose()
    await adm.aclose()
    await other.aclose()

    print()
    if failures:
        print(f"RESULT: FAIL ({len(failures)}): {failures}")
        return 1
    print("RESULT: ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
