#!/usr/bin/env python3
"""
Sprint 13 — Secondary Market — E2E core test.

Covers the FULL lifecycle the user defined:
    Ownership → Listing → Bid/Buy → Trade → Settlement → Ledger
    + ownership split/transfer + platform fee
    + investor UI data (holdings/listings/bids/trades) endpoints
    + admin oversight endpoint

CORE INVARIANT (Sprint 13):
    total ownership units per asset NEVER change — only the owner changes.

Money conservation per trade (gross = units * price):
    buyer  debit  gross           (reason=secondary_purchase)
    seller credit gross - fee      (reason=secondary_sale)
    plat.  credit fee              (reason=platform_fee, investor=platform-revenue)
    ─── Σ = 0 ✓

Plus guards:
    - min listing amount
    - cannot list more than owned
    - cannot buy own listing
    - cannot buy more than remaining
    - insufficient wallet funds (buy-now + settlement)
    - cancel listing / cancel bid / reject bid + auth (only owner/seller)
    - offer must be strictly below listing price

Setup uses pymongo directly (deterministic fixtures with fresh test users
on a throw-away asset). Lifecycle is driven through the real HTTP API.
"""
import os
import sys
import time
import uuid

import bcrypt
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

BASE = os.environ.get("E2E_BASE_URL", "http://localhost:8001")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "evax_devos")

client = MongoClient(MONGO_URL)
db = client[DB_NAME]

EPS = 0.51  # rounding tolerance used by the service (0.5 guards)
RUN = uuid.uuid4().hex[:8]
ASSET_ID = f"asset-e2e-s13-{RUN}"
SELLER_EMAIL = f"seller_{RUN}@e2e.test"
BUYER_EMAIL = f"buyer_{RUN}@e2e.test"
POOR_EMAIL = f"poor_{RUN}@e2e.test"
PWD = "e2e-pass-123"

PASS = []
FAIL = []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  ✅ {name}")
    else:
        FAIL.append(f"{name} :: {detail}")
        print(f"  ❌ {name} :: {detail}")


def approx(a, b, eps=EPS):
    return abs(float(a) - float(b)) <= eps


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _hash(p):
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def _mk_user(email, name):
    uid = f"user_e2e_{uuid.uuid4().hex[:12]}"
    db.users.insert_one({
        "user_id": uid, "id": uid, "email": email, "password_hash": _hash(PWD),
        "name": name, "role": "client", "roles": ["client"], "active_role": "client",
        "states": ["client"], "created_at": _isonow(),
    })
    return uid


def _isonow():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _now_dt():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


def setup_fixtures():
    print("\n[setup] creating fresh asset + users + seller ownership + buyer cash")
    # throw-away asset
    db.lumen_assets.insert_one({
        "id": ASSET_ID, "title": f"E2E Asset {RUN}", "category": "real_estate",
        "status": "open", "yield_pct": 15.0, "min_ticket": 1000,
        "round_target": 1_000_000, "raised_amount": 0.0,
        "created_at": _now_dt(), "updated_at": _now_dt(),
    })

    seller_id = _mk_user(SELLER_EMAIL, "E2E Seller")
    buyer_id = _mk_user(BUYER_EMAIL, "E2E Buyer")
    poor_id = _mk_user(POOR_EMAIL, "E2E Poor Buyer")

    # Seller owns 200000 UAH via an ACTIVE primary investment
    db.lumen_investments.insert_one({
        "id": f"inv-e2e-{uuid.uuid4().hex[:10]}", "investor_id": seller_id,
        "asset_id": ASSET_ID, "amount": 200000.0, "amount_uah": 200000.0,
        "currency": "UAH", "status": "active", "created_at": _now_dt(),
    })
    # materialize ownership row (settlement upserts but compute reads live anyway)
    db.lumen_ownerships.update_one(
        {"investor_id": seller_id, "asset_id": ASSET_ID},
        {"$set": {"investor_id": seller_id, "asset_id": ASSET_ID,
                  "amount_uah": 200000.0, "amount": 200000.0},
         "$setOnInsert": {"id": f"own-e2e-{uuid.uuid4().hex[:10]}"}},
        upsert=True)

    # Buyer has 300000 UAH cash via adjustment credit (counts toward wallet)
    db.lumen_ledger_entries.insert_one({
        "id": f"le-e2e-{uuid.uuid4().hex[:12]}", "entry_type": "credit",
        "reason": "adjustment", "investor_id": buyer_id, "asset_id": None,
        "investment_id": None, "payment_request_id": None,
        "amount": 300000.0, "currency": "UAH", "base_currency": "UAH",
        "fx_rate": 1.0, "amount_uah": 300000.0, "notes": "E2E seed cash",
        "created_by": "e2e", "created_at": _now_dt(),
    })
    return seller_id, buyer_id, poor_id


def teardown():
    print("\n[teardown] removing E2E fixtures")
    db.lumen_assets.delete_many({"id": ASSET_ID})
    db.users.delete_many({"email": {"$in": [SELLER_EMAIL, BUYER_EMAIL, POOR_EMAIL]}})
    db.lumen_investments.delete_many({"asset_id": ASSET_ID})
    db.lumen_ownerships.delete_many({"asset_id": ASSET_ID})
    db.lumen_secondary_listings.delete_many({"asset_id": ASSET_ID})
    db.lumen_secondary_trades.delete_many({"asset_id": ASSET_ID})
    db.lumen_share_transfers.delete_many({"asset_id": ASSET_ID})
    # bids reference listing_id; clean by buyer/seller emails users already gone
    for uid in _created_user_ids:
        db.lumen_ledger_entries.delete_many({"investor_id": uid})
        db.lumen_wallets.delete_many({"investor_id": uid})
        db.lumen_secondary_bids.delete_many({"buyer_id": uid})
    db.lumen_ledger_entries.delete_many({"investor_id": "platform-revenue",
                                         "notes": {"$regex": "trade"}})


_created_user_ids = []


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def login(email, password=PWD):
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": email, "password": password}, timeout=20)
    r.raise_for_status()
    # /auth/login sets a Secure session cookie; pull it from the jar and re-add
    # as a plain cookie so it is sent over http://localhost.
    token = r.cookies.get("session_token")
    if not token:
        body = r.json()
        token = body.get("token") or (body.get("user") or {}).get("token")
    assert token, f"no session token from login: {r.status_code} {r.text[:200]}"
    s = requests.Session()
    s.cookies.set("session_token", token)
    return s


def admin_session():
    return login("admin@atlas.dev", "admin123")


# ---------------------------------------------------------------------------
# Invariant helpers (read truth from DB)
# ---------------------------------------------------------------------------

def total_ownership(asset_id):
    """Σ over every investor of (primary active + inbound − outbound)."""
    investors = set()
    for inv in db.lumen_investments.find({"asset_id": asset_id, "status": "active"}):
        investors.add(inv["investor_id"])
    for t in db.lumen_share_transfers.find({"asset_id": asset_id}):
        investors.add(t["from_investor_id"])
        investors.add(t["to_investor_id"])
    total = 0.0
    per = {}
    for iid in investors:
        primary = sum(float(i.get("amount_uah") or i.get("amount") or 0)
                      for i in db.lumen_investments.find(
                          {"investor_id": iid, "asset_id": asset_id, "status": "active"}))
        inflow = sum(float(t.get("amount_uah") or 0)
                     for t in db.lumen_share_transfers.find(
                         {"to_investor_id": iid, "asset_id": asset_id}))
        outflow = sum(float(t.get("amount_uah") or 0)
                      for t in db.lumen_share_transfers.find(
                          {"from_investor_id": iid, "asset_id": asset_id}))
        owned = primary + inflow - outflow
        per[iid] = round(owned, 2)
        total += owned
    return round(total, 2), per


def wallet_settled(session):
    r = session.get(f"{BASE}/api/investor/wallet", timeout=20)
    r.raise_for_status()
    return float(r.json()["wallet"]["settled_balance"])


def platform_revenue(admin):
    r = admin.get(f"{BASE}/api/admin/secondary/overview", timeout=20)
    r.raise_for_status()
    return float(r.json()["platform_revenue_uah"])


# ---------------------------------------------------------------------------
# Main test
# ---------------------------------------------------------------------------

def run():
    seller_id, buyer_id, poor_id = setup_fixtures()
    _created_user_ids.extend([seller_id, buyer_id, poor_id])

    seller = login(SELLER_EMAIL)
    buyer = login(BUYER_EMAIL)
    poor = login(POOR_EMAIL)
    admin = admin_session()

    print("\n[1] Baseline wallets + invariant")
    # materialize wallets
    s_w0 = wallet_settled(seller)
    b_w0 = wallet_settled(buyer)
    rev0 = platform_revenue(admin)
    base_total, base_per = total_ownership(ASSET_ID)
    check("seller wallet starts at 0", approx(s_w0, 0), f"got {s_w0}")
    check("buyer wallet funded 300000", approx(b_w0, 300000), f"got {b_w0}")
    check("baseline total ownership == 200000", approx(base_total, 200000),
          f"got {base_total}")

    print("\n[2] Holdings endpoint reflects seller ownership")
    r = seller.get(f"{BASE}/api/investor/secondary/holdings", timeout=20)
    h = r.json()
    hold = next((x for x in h["items"] if x["asset_id"] == ASSET_ID), None)
    check("holdings list contains asset", hold is not None, str(h))
    if hold:
        check("holdings owned_uah == 200000", approx(hold["owned_uah"], 200000),
              str(hold))
        check("holdings available_uah == 200000", approx(hold["available_uah"], 200000),
              str(hold))
    check("platform_fee_pct == 0.01", approx(h.get("platform_fee_pct"), 0.01),
          str(h.get("platform_fee_pct")))

    print("\n[3] Guards on listing creation")
    # below min
    r = seller.post(f"{BASE}/api/investor/secondary/listings",
                    json={"asset_id": ASSET_ID, "units_uah": 50, "price_per_unit": 1.0})
    check("listing below MIN rejected (400)", r.status_code == 400, f"{r.status_code} {r.text}")
    # more than owned
    r = seller.post(f"{BASE}/api/investor/secondary/listings",
                    json={"asset_id": ASSET_ID, "units_uah": 999999, "price_per_unit": 1.0})
    check("listing over-owned rejected (400)", r.status_code == 400, f"{r.status_code} {r.text}")
    # bad price
    r = seller.post(f"{BASE}/api/investor/secondary/listings",
                    json={"asset_id": ASSET_ID, "units_uah": 100000, "price_per_unit": 9})
    check("listing price>5 rejected", r.status_code in (400, 422), f"{r.status_code} {r.text}")

    print("\n[4] Create valid listing (100000 @ 1.0)")
    r = seller.post(f"{BASE}/api/investor/secondary/listings",
                    json={"asset_id": ASSET_ID, "units_uah": 100000, "price_per_unit": 1.0})
    check("listing created (200)", r.status_code == 200, f"{r.status_code} {r.text}")
    listing = r.json()
    listing_id = listing["id"]
    check("listing status active", listing.get("status") == "active", str(listing))

    # listing now locks 100000 → available drops to 100000
    r = seller.get(f"{BASE}/api/investor/secondary/holdings", timeout=20)
    hold = next((x for x in r.json()["items"] if x["asset_id"] == ASSET_ID), None)
    check("available_uah after listing == 100000",
          hold and approx(hold["available_uah"], 100000), str(hold))

    # cannot list the locked part again (only 100000 free)
    r = seller.post(f"{BASE}/api/investor/secondary/listings",
                    json={"asset_id": ASSET_ID, "units_uah": 150000, "price_per_unit": 1.0})
    check("over-listing beyond free rejected", r.status_code == 400, f"{r.status_code} {r.text}")

    print("\n[5] Public listing visible, seller_id hidden")
    r = requests.get(f"{BASE}/api/secondary/listings?asset_id={ASSET_ID}", timeout=20)
    pub = r.json()["items"]
    pl = next((x for x in pub if x["id"] == listing_id), None)
    check("public listing visible", pl is not None, str(pub))
    check("public listing hides seller_id", pl is not None and "seller_id" not in pl, str(pl))
    check("public listing has seller_label", pl is not None and bool(pl.get("seller_label")), str(pl))

    print("\n[6] Guards on buying")
    # seller cannot buy own listing
    r = seller.post(f"{BASE}/api/investor/secondary/bids",
                    json={"listing_id": listing_id, "units_uah": 1000})
    check("seller buying own listing rejected (400)", r.status_code == 400, f"{r.status_code} {r.text}")
    # buy more than remaining
    r = buyer.post(f"{BASE}/api/investor/secondary/bids",
                   json={"listing_id": listing_id, "units_uah": 200000})
    check("buy over remaining rejected (400)", r.status_code == 400, f"{r.status_code} {r.text}")
    # poor buyer insufficient funds (buy-now)
    r = poor.post(f"{BASE}/api/investor/secondary/bids",
                  json={"listing_id": listing_id, "units_uah": 10000})
    check("poor buyer insufficient funds (402)", r.status_code == 402, f"{r.status_code} {r.text}")

    print("\n[7] BUY-NOW 60000 @ 1.0 → trade settled")
    r = buyer.post(f"{BASE}/api/investor/secondary/bids",
                   json={"listing_id": listing_id, "units_uah": 60000})
    check("buy-now accepted (200)", r.status_code == 200, f"{r.status_code} {r.text}")
    body = r.json()
    check("mode == buy_now", body.get("mode") == "buy_now", str(body))
    trade1 = body.get("trade", {})
    check("trade1 settled", trade1.get("status") == "settled", str(trade1))
    check("trade1 gross == 60000", approx(trade1.get("gross_uah"), 60000), str(trade1))
    check("trade1 fee == 600 (1%)", approx(trade1.get("fee_uah"), 600), str(trade1))
    check("trade1 seller_net == 59400", approx(trade1.get("seller_net_uah"), 59400), str(trade1))

    # INVARIANT after trade 1
    t1_total, t1_per = total_ownership(ASSET_ID)
    check("INVARIANT total ownership unchanged after buy-now", approx(t1_total, 200000),
          f"got {t1_total}")
    check("seller ownership -60000 (=140000)", approx(t1_per.get(seller_id), 140000),
          str(t1_per))
    check("buyer ownership +60000 (=60000)", approx(t1_per.get(buyer_id), 60000),
          str(t1_per))

    # ledger conservation for trade 1
    le = list(db.lumen_ledger_entries.find({"notes": {"$regex": trade1["id"]}}))
    buyer_deb = sum(e["amount_uah"] for e in le if e["entry_type"] == "debit" and e["investor_id"] == buyer_id)
    seller_cr = sum(e["amount_uah"] for e in le if e["entry_type"] == "credit" and e["investor_id"] == seller_id)
    fee_cr = sum(e["amount_uah"] for e in le if e["reason"] == "platform_fee")
    check("ledger buyer debit 60000", approx(buyer_deb, 60000), str(le))
    check("ledger seller credit 59400", approx(seller_cr, 59400), str(le))
    check("ledger platform fee 600", approx(fee_cr, 600), str(le))
    check("ledger conservation Σ=0", approx(buyer_deb - seller_cr - fee_cr, 0),
          f"{buyer_deb} - {seller_cr} - {fee_cr}")

    # wallet conservation
    s_w1 = wallet_settled(seller)
    b_w1 = wallet_settled(buyer)
    check("seller wallet +59400", approx(s_w1 - s_w0, 59400), f"{s_w0}->{s_w1}")
    check("buyer wallet -60000", approx(b_w1 - b_w0, -60000), f"{b_w0}->{b_w1}")

    print("\n[8] OFFER below price on remaining 40000, seller accepts")
    # offer ABOVE listing price is rejected (offer must be strictly lower;
    # offering AT par is by-design a buy-now, tested separately above)
    r = buyer.post(f"{BASE}/api/investor/secondary/bids",
                   json={"listing_id": listing_id, "units_uah": 40000, "price_per_unit": 1.2})
    check("offer above listing price rejected (400)", r.status_code == 400, f"{r.status_code} {r.text}")
    # valid offer 0.95
    r = buyer.post(f"{BASE}/api/investor/secondary/bids",
                   json={"listing_id": listing_id, "units_uah": 40000, "price_per_unit": 0.95})
    check("offer placed (200)", r.status_code == 200, f"{r.status_code} {r.text}")
    ob = r.json()
    check("mode == offer", ob.get("mode") == "offer", str(ob))
    bid_id = ob["bid"]["id"]

    # non-seller cannot accept
    r = poor.post(f"{BASE}/api/investor/secondary/bids/{bid_id}/accept")
    check("non-seller accept rejected (403)", r.status_code == 403, f"{r.status_code} {r.text}")

    # seller accepts
    r = seller.post(f"{BASE}/api/investor/secondary/bids/{bid_id}/accept")
    check("seller accept (200)", r.status_code == 200, f"{r.status_code} {r.text}")
    trade2 = r.json().get("trade", {})
    check("trade2 settled", trade2.get("status") == "settled", str(trade2))
    check("trade2 gross == 38000", approx(trade2.get("gross_uah"), 38000), str(trade2))
    check("trade2 fee == 380", approx(trade2.get("fee_uah"), 380), str(trade2))

    # INVARIANT after trade 2 — listing now fully filled
    t2_total, t2_per = total_ownership(ASSET_ID)
    check("INVARIANT total ownership unchanged after accept", approx(t2_total, 200000),
          f"got {t2_total}")
    check("seller ownership now 100000", approx(t2_per.get(seller_id), 100000), str(t2_per))
    check("buyer ownership now 100000", approx(t2_per.get(buyer_id), 100000), str(t2_per))

    # listing filled
    r = requests.get(f"{BASE}/api/secondary/listings/{listing_id}", timeout=20)
    check("listing status filled", r.json().get("status") == "filled", str(r.json().get("status")))

    print("\n[9] Wallet + platform revenue final conservation")
    s_w2 = wallet_settled(seller)
    b_w2 = wallet_settled(buyer)
    rev1 = platform_revenue(admin)
    # total spent by buyer == total received by seller + platform fee
    spent = b_w0 - b_w2
    recv = s_w2 - s_w0
    feerev = rev1 - rev0
    check("buyer spent 98000", approx(spent, 98000), f"{spent}")
    check("seller received 97020", approx(recv, 97020), f"{recv}")
    check("platform fee revenue 980", approx(feerev, 980), f"{feerev}")
    check("global money conservation: spent == recv + fee",
          approx(spent, recv + feerev), f"{spent} vs {recv}+{feerev}")

    print("\n[10] Investor my-* endpoints + admin oversight")
    r = seller.get(f"{BASE}/api/investor/secondary/my-listings"); ml = r.json()["items"]
    check("seller my-listings shows filled listing",
          any(x["id"] == listing_id and x["status"] == "filled" for x in ml), str(ml))
    r = buyer.get(f"{BASE}/api/investor/secondary/my-trades"); mt = r.json()["items"]
    check("buyer my-trades has 2 settled trades",
          len([x for x in mt if x.get("asset_id") == ASSET_ID]) >= 2, str(len(mt)))
    r = admin.get(f"{BASE}/api/admin/secondary/overview"); ov = r.json()
    check("admin overview settled>=2", ov["counts"]["trades"].get("settled", 0) >= 2, str(ov["counts"]))
    check("admin overview platform_revenue>=980", ov["platform_revenue_uah"] >= 980 - EPS, str(ov))
    r = admin.get(f"{BASE}/api/admin/secondary/trades")
    check("admin trades list reachable", r.status_code == 200, f"{r.status_code}")
    # admin access control: investor hitting admin endpoint → 403
    r = buyer.get(f"{BASE}/api/admin/secondary/overview")
    check("investor blocked from admin overview (403)", r.status_code == 403, f"{r.status_code}")

    print("\n[11] Cancel flows + guards")
    # New small listing to test cancel
    r = seller.post(f"{BASE}/api/investor/secondary/listings",
                    json={"asset_id": ASSET_ID, "units_uah": 5000, "price_per_unit": 1.0})
    lid2 = r.json()["id"]
    # non-owner cannot cancel
    r = buyer.post(f"{BASE}/api/investor/secondary/listings/{lid2}/cancel")
    check("non-owner cancel listing rejected (403)", r.status_code == 403, f"{r.status_code}")
    # owner cancels
    r = seller.post(f"{BASE}/api/investor/secondary/listings/{lid2}/cancel")
    check("owner cancel listing (200)", r.status_code == 200, f"{r.status_code} {r.text}")
    # double cancel → 409
    r = seller.post(f"{BASE}/api/investor/secondary/listings/{lid2}/cancel")
    check("double cancel rejected (409)", r.status_code == 409, f"{r.status_code}")

    # bid cancel flow: new listing + offer + buyer cancels
    r = seller.post(f"{BASE}/api/investor/secondary/listings",
                    json={"asset_id": ASSET_ID, "units_uah": 5000, "price_per_unit": 1.0})
    lid3 = r.json()["id"]
    r = buyer.post(f"{BASE}/api/investor/secondary/bids",
                   json={"listing_id": lid3, "units_uah": 4000, "price_per_unit": 0.9})
    bid3 = r.json()["bid"]["id"]
    r = buyer.post(f"{BASE}/api/investor/secondary/bids/{bid3}/cancel")
    check("buyer cancel own bid (200)", r.status_code == 200, f"{r.status_code} {r.text}")
    # seller reject path on a fresh bid
    r = buyer.post(f"{BASE}/api/investor/secondary/bids",
                   json={"listing_id": lid3, "units_uah": 4000, "price_per_unit": 0.9})
    bid4 = r.json()["bid"]["id"]
    r = seller.post(f"{BASE}/api/investor/secondary/bids/{bid4}/reject")
    check("seller reject bid (200)", r.status_code == 200, f"{r.status_code} {r.text}")

    print("\n[12] FINAL invariant re-check (nothing leaked)")
    fin_total, fin_per = total_ownership(ASSET_ID)
    check("FINAL total ownership still 200000", approx(fin_total, 200000), f"got {fin_total}")


def main():
    print("=" * 72)
    print(f"Sprint 13 Secondary Market E2E — run {RUN}")
    print("=" * 72)
    ok = True
    try:
        run()
    except Exception as e:
        import traceback
        traceback.print_exc()
        FAIL.append(f"EXCEPTION: {e}")
        ok = False
    finally:
        try:
            teardown()
        except Exception as e:
            print(f"teardown error: {e}")

    print("\n" + "=" * 72)
    print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("\nFAILURES:")
        for f in FAIL:
            print(f"  - {f}")
    print("=" * 72)
    sys.exit(0 if (ok and not FAIL) else 1)


if __name__ == "__main__":
    main()
