"""POC: Phase F Operator OS — portal scoping, KPI/SLA/reputation, report->SLA reset, admin flows."""
import sys
import requests

BASE = "http://localhost:8001/api"


def login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": pw}, timeout=15)
    r.raise_for_status()
    token = r.cookies.get("session_token")
    if token:
        s.cookies.clear(); s.cookies.set("session_token", token)
    return s, r.json()


def main():
    ok = True
    admin, _ = login("admin@atlas.dev", "admin123")
    op, opu = login("operator@atlas.dev", "operator123")
    print(f"[auth] operator role={opu.get('role')}")
    ok &= opu.get("role") == "operator"

    # F10 operator/me
    me = op.get(f"{BASE}/operator/me").json()
    print(f"[F10] me: {me['name']} status={me['status']} verified={me['verified']} grade={me['reputation']['grade']}")
    ok &= me["verified"] is True

    # F3 dashboard KPI
    dash = op.get(f"{BASE}/operator/dashboard").json()
    k = dash["kpi"]
    print(f"[F3] KPI assets={k['assets_count']} aum={k['aum_uah']} investors={k['investors_count']} reporting={k['reporting_score']} payout={k['payout_timeliness_pct']}")
    ok &= k["assets_count"] >= 1

    # F4 SLA before report
    sla = op.get(f"{BASE}/operator/sla").json()
    print(f"[F4] SLA overall={sla['overall']} counts={sla['counts']}")
    target_asset = None
    for it in sla["items"]:
        if it["status"] in ("warning", "critical", "escalation"):
            target_asset = it["asset_id"]
    print(f"    breaching asset: {target_asset}")

    # F10 assets scoped
    assets = op.get(f"{BASE}/operator/assets").json()
    print(f"[F10] my assets: {[a['id'] for a in assets['items']]}")
    ok &= len(assets["items"]) >= 1
    if not target_asset and assets["items"]:
        target_asset = assets["items"][0]["id"]

    # submit report -> SLA should improve for that asset
    if target_asset:
        rep = op.post(f"{BASE}/operator/assets/{target_asset}/reports",
                      json={"title": "POC квартальний звіт", "period_label": "Q2 2026",
                            "summary": "Операційний звіт", "report_type": "operational"}).json()
        print(f"[F10] submitted report ok={rep.get('ok')}")
        sla2 = op.get(f"{BASE}/operator/sla").json()
        new_status = next((i["status"] for i in sla2["items"] if i["asset_id"] == target_asset), None)
        print(f"[F4] asset SLA after report: {new_status}")
        ok &= new_status == "ok"

    # scoping: operator cannot submit report for an asset they don't manage
    bad = op.post(f"{BASE}/operator/assets/asset-rivne-warehouse/reports",
                  json={"title": "hack"})
    print(f"[scope] foreign asset report -> {bad.status_code} (expect 403)")
    ok &= bad.status_code == 403

    # F10 investors scoped
    inv = op.get(f"{BASE}/operator/investors").json()
    print(f"[F10] investors={inv['total_investors']} capital={inv['total_capital_uah']}")

    # F9 fees
    fees = op.get(f"{BASE}/operator/fees").json()
    print(f"[F9] mgmt%={fees['management_fee_pct']} est_annual={fees['estimated_annual_management_fee_uah']}")

    # F8 dealflow
    df = op.get(f"{BASE}/operator/dealflow").json()
    print(f"[F8] dealflow sourced={df['sourced']} live={df['live']} success%={df['funding_success_pct']}")

    # non-operator (admin) blocked from operator portal
    blocked = admin.get(f"{BASE}/operator/me")
    print(f"[scope] admin->/operator/me {blocked.status_code} (expect 403)")
    ok &= blocked.status_code == 403

    # ADMIN overview + verification + assign
    ops = admin.get(f"{BASE}/admin/operators").json()["items"]
    op_id = next((o["id"] for o in ops if o["name"] == "West Logistics Operator"), ops[0]["id"])
    ov = admin.get(f"{BASE}/admin/operators/{op_id}/overview").json()
    print(f"[F1] overview {ov['operator']['name']} status={ov['operator']['status']} kpi_assets={ov['kpi']['assets_count']} events={len(ov['events'])}")
    ok &= "kpi" in ov and "sla" in ov and "reputation" in ov

    # F2 verification transition
    v = admin.post(f"{BASE}/admin/operators/{op_id}/verification", json={"to_status": "verified", "note": "POC"}).json()
    print(f"[F2] verification -> {v.get('status')}")
    ok &= v.get("status") == "verified"
    # revert
    admin.post(f"{BASE}/admin/operators/{op_id}/verification", json={"to_status": "applied"})

    # F9 fees update
    admin.patch(f"{BASE}/admin/operators/{op_id}/fees", json={"management_fee_pct": 3.0})

    # F7 leaderboard ordering
    lb = admin.get(f"{BASE}/operators/leaderboard").json()["items"]
    scores = [(x["name"], (x.get("reputation") or {}).get("score")) for x in lb]
    print(f"[F7] leaderboard: {scores}")
    ok &= all(scores[i][1] >= scores[i + 1][1] for i in range(len(scores) - 1))

    # public operator card for an asset
    card = requests.get(f"{BASE}/assets/asset-podilskyi/operator-card").json()
    print(f"[F1] asset operator-card: {(card.get('operator') or {}).get('name')} verified={(card.get('operator') or {}).get('verified')}")
    ok &= card.get("operator") is not None

    # F4 SLA scan
    scan = admin.post(f"{BASE}/admin/operators/sla/scan").json()
    print(f"[F4] sla scan flagged={scan.get('flagged')}")

    print("\n=== POC RESULT:", "PASS" if ok else "FAIL", "===")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
