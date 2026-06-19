"""POC: Phase E Capital Formation core loop (deal→committee→commit→allocate→waitlist)."""
import sys
import requests

BASE = "http://localhost:8001/api"


def login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": pw}, timeout=15)
    r.raise_for_status()
    # cookie is marked Secure → re-set as plain so it is sent over http://localhost
    token = r.cookies.get("session_token")
    if token:
        s.cookies.clear()
        s.cookies.set("session_token", token)
    return s, r.json()


def main():
    ok = True
    admin, au = login("admin@atlas.dev", "admin123")
    client, cu = login("client@atlas.dev", "client123")
    print(f"[auth] admin={au['email']} client={cu['email']}")

    # E1: create deal + transition + events
    d = admin.post(f"{BASE}/admin/deals", json={
        "title": "POC Deal — Riverside Lofts", "source": "poc", "owner_name": "POC Owner",
        "region": "Київ", "asset_type": "real_estate",
        "asking_price_uah": 6000000, "team_valuation_uah": 5500000}).json()
    deal_id = d["id"]
    print(f"[E1] created deal {deal_id} stage={d['stage']}")
    admin.post(f"{BASE}/admin/deals/{deal_id}/transition", json={"to_stage": "screening", "note": "ok"})
    admin.post(f"{BASE}/admin/deals/{deal_id}/transition", json={"to_stage": "committee", "note": "to committee"})
    ev = admin.get(f"{BASE}/admin/deals/{deal_id}/events").json()
    print(f"[E1] events={len(ev['items'])}")
    ok &= len(ev["items"]) >= 3

    # E2: memo + reviews + vote + decision
    admin.put(f"{BASE}/admin/deals/{deal_id}/memo", json={"fields": {"opportunity": "x", "recommendation": "approve"}})
    admin.put(f"{BASE}/admin/deals/{deal_id}/risk-review", json={"summary": "low risk", "rating": "low"})
    admin.put(f"{BASE}/admin/deals/{deal_id}/financial-review", json={"summary": "solid", "rating": "strong"})
    admin.post(f"{BASE}/admin/deals/{deal_id}/vote", json={"vote": "approve", "comment": "yes"})
    com = admin.get(f"{BASE}/admin/deals/{deal_id}/committee").json()
    print(f"[E2] tally={com['tally']} recommended={com['recommended']}")
    dec = admin.post(f"{BASE}/admin/deals/{deal_id}/decision", json={"decision": "approved", "note": "go"}).json()
    print(f"[E2] decision stage={dec['stage']}")
    ok &= dec["stage"] == "funding" and com["recommended"] == "approved"

    # E4: commitments that oversubscribe a small capacity
    asset = "asset-lavr-tc"
    c1 = client.post(f"{BASE}/investor/commitments", json={"asset_id": asset, "amount_uah": 500000, "kind": "hard"}).json()
    c2 = client.post(f"{BASE}/investor/commitments", json={"asset_id": asset, "amount_uah": 300000, "kind": "reservation"}).json()
    rb = c2["raise"]
    print(f"[E4] target={rb['target_uah']} committed={rb['committed_uah']} demand%={rb['demand_pct']}")
    ok &= rb["committed_uah"] >= 800000

    # E8: allocate with small capacity to force oversubscription + waitlist overflow
    alloc = admin.post(f"{BASE}/admin/assets/{asset}/allocate",
                       json={"policy": "pro_rata", "capacity_uah": 600000}).json()
    total_alloc = sum(r["allocated_uah"] for r in alloc["results"])
    total_wait = sum(r["waitlisted_uah"] for r in alloc["results"])
    print(f"[E8] policy={alloc['policy']} capacity={alloc['capacity_uah']} allocated={total_alloc} waitlisted={total_wait} over%={alloc['oversubscription_pct']}")
    ok &= abs(total_alloc - 600000) < 5 and total_wait > 0

    # E5: waitlist created from overflow + my waitlist
    wl = admin.get(f"{BASE}/admin/assets/{asset}/waitlist").json()
    print(f"[E5] waitlist entries={len(wl['items'])}")
    ok &= len(wl["items"]) >= 1
    mywl = client.get(f"{BASE}/investor/waitlist").json()
    print(f"[E5] my waitlist={len(mywl['items'])} pos={[w.get('position') for w in mywl['items']]}")

    # E9: analytics
    an = admin.get(f"{BASE}/admin/pipeline/analytics").json()
    print(f"[E9] total_deals={an['total_deals']} counts={an['counts']} rejections={len(an['rejection_reasons'])}")
    ok &= an["total_deals"] >= 1

    # E7 velocity
    vel = admin.get(f"{BASE}/admin/capital/velocity").json()
    print(f"[E7] avg_days_to_close={vel['avg_days_to_close']} rows={len(vel['per_asset'])}")

    # E6 segments
    seg = admin.get(f"{BASE}/admin/capital/segments").json()
    print(f"[E6] segments counts={seg['counts']} investors={len(seg['items'])}")
    ok &= len(seg["items"]) >= 1

    # E3 dataroom gating
    pub = requests.get(f"{BASE}/assets/asset-podilskyi/dataroom").json()
    inv = client.get(f"{BASE}/assets/asset-podilskyi/dataroom").json()
    adm = admin.get(f"{BASE}/assets/asset-podilskyi/dataroom").json()
    print(f"[E3] dataroom public={len(pub['items'])} investor={len(inv['items'])} admin={len(adm['items'])}")
    ok &= len(pub["items"]) <= len(inv["items"]) <= len(adm["items"]) and len(adm["items"]) >= len(pub["items"])

    # E10 operators
    ops = admin.get(f"{BASE}/admin/operators").json()
    print(f"[E10] operators={len(ops['items'])}")
    ok &= len(ops["items"]) >= 1

    # cleanup POC deal
    admin.delete(f"{BASE}/admin/deals/{deal_id}")

    print("\n=== POC RESULT:", "PASS" if ok else "FAIL", "===")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
