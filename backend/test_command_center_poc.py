"""
H1.3 Controlled Beta Command Center — POC end-to-end smoke
===========================================================

Validates the full Command Center surface in one shot:

1. login as admin
2. GET /api/admin/beta/launch-status — must return all top-header fields
3. GET /api/admin/beta/command-center — must include all 9 sources + checklist
4. GET /api/admin/beta/checklist — must return 7 milestones with required fields
5. POST /api/admin/beta/checklist/{milestone_id}/override — must persist
6. GET /api/admin/beta/checklist — override is reflected
7. DELETE /api/admin/beta/checklist/{milestone_id}/override — restore
8. GET /api/admin/beta/alerts — only critical|warning severities present
9. GET /api/admin/beta/alerts?severity=warning — filter works

Failure of ANY step terminates the script with non-zero exit code.
"""
from __future__ import annotations

import os
import sys

import requests

BASE = os.environ.get("LUMEN_API_BASE", "http://localhost:8001/api")
ADMIN_EMAIL = os.environ.get("LUMEN_ADMIN_EMAIL", "admin@atlas.dev")
ADMIN_PWD = os.environ.get("LUMEN_ADMIN_PWD", "admin123")


def hr(title: str) -> None:
    print("\n" + "═" * 72)
    print(f" {title}")
    print("═" * 72)


def fail(step: str, resp) -> None:
    print(f"❌ FAIL @ {step}")
    print(f"   status_code: {getattr(resp, 'status_code', '?')}")
    try:
        print(f"   body: {resp.json()}")
    except Exception:
        print(f"   body: {getattr(resp, 'text', resp)[:400]}")
    sys.exit(1)


def main() -> None:
    s = requests.Session()

    hr("1. Login as admin")
    r = s.post(f"{BASE}/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PWD})
    if r.status_code != 200:
        fail("login", r)
    for c in s.cookies:
        c.secure = False
    print(f"✅ logged in as {r.json().get('email')} (role={r.json().get('role')})")

    # ────────────────────────────────────────────────────────────────────
    hr("2. GET /admin/beta/launch-status — top header bundle")
    r = s.get(f"{BASE}/admin/beta/launch-status")
    if r.status_code != 200:
        fail("launch-status", r)
    ls = r.json()
    required = {
        "phase", "readiness_score", "readiness_max",
        "security_score", "security_max",
        "open_critical_alerts_count", "open_warnings_count",
        "beta1_progress_completed", "beta1_progress_total",
        "scanner_running", "as_of",
    }
    missing = required - set(ls.keys())
    if missing:
        print(f"missing keys: {missing}")
        fail("launch-status fields", r)
    if ls["phase"] != "CONTROLLED_BETA":
        fail("launch-status: phase must be CONTROLLED_BETA", r)
    if ls["beta1_progress_total"] != 7:
        fail("launch-status: beta1_progress_total must be 7", r)
    print(f"✅ Launch Status: phase={ls['phase']} · readiness={ls['readiness_score']}/{ls['readiness_max']} "
          f"· security={ls['security_score']}/{ls['security_max']}")
    print(f"   alerts: critical={ls['open_critical_alerts_count']} warning={ls['open_warnings_count']} "
          f"· beta1={ls['beta1_progress_completed']}/{ls['beta1_progress_total']}")

    # ────────────────────────────────────────────────────────────────────
    hr("3. GET /admin/beta/command-center — full aggregator")
    r = s.get(f"{BASE}/admin/beta/command-center")
    if r.status_code != 200:
        fail("command-center", r)
    cc = r.json()
    cc_required = {
        "as_of", "launch_status",
        "treasury_pulse", "lr2", "open_alerts",
        "pending_kyc", "pending_compliance", "pending_funding",
        "pending_reconciliation", "pending_capital_calls",
        "pending_distributions", "beta1_checklist",
    }
    missing_cc = cc_required - set(cc.keys())
    if missing_cc:
        print(f"missing keys: {missing_cc}")
        fail("command-center keys", r)
    if "items" not in cc["beta1_checklist"] or len(cc["beta1_checklist"]["items"]) != 7:
        fail("command-center: beta1_checklist must have 7 items", r)
    print("✅ Command Center payload has all 9 sources + Beta-1 Checklist")
    print(f"   treasury_pulse keys: {sorted(cc['treasury_pulse'].keys())}")
    print(f"   lr2.score: {cc['lr2'].get('score')}/{cc['lr2'].get('max')}  grade: {cc['lr2'].get('grade')}")
    print(f"   pending_funding: {cc['pending_funding'].get('total')} "
          f"· pending_kyc: {cc['pending_kyc'].get('total')} "
          f"· pending_compliance: {cc['pending_compliance'].get('total')}")
    print(f"   alerts total: {len(cc['open_alerts'])}")

    # ────────────────────────────────────────────────────────────────────
    hr("4. GET /admin/beta/checklist — 7 milestones with required fields")
    r = s.get(f"{BASE}/admin/beta/checklist")
    if r.status_code != 200:
        fail("checklist", r)
    ck = r.json()
    if ck.get("total") != 7 or len(ck.get("items", [])) != 7:
        fail("checklist: must have 7 items", r)
    required_item_fields = {
        "milestone_id", "status", "detected_at", "detected_entity_id",
        "notes", "overridden_by", "overridden_at",
    }
    for it in ck["items"]:
        missing_fields = required_item_fields - set(it.keys())
        if missing_fields:
            print(f"missing fields on {it.get('milestone_id')}: {missing_fields}")
            fail("checklist item fields", r)
    print(f"✅ Checklist returns 7 items, completed={ck['completed']}/7")
    for it in ck["items"]:
        print(f"   · {it['milestone_id']:<26} status={it['status']:<14} "
              f"detected_at={it.get('detected_at') or '—'}")

    # ────────────────────────────────────────────────────────────────────
    hr("5. POST override on first_quarterly_report")
    target = "first_quarterly_report"
    r = s.post(f"{BASE}/admin/beta/checklist/{target}/override",
                json={"status": "completed",
                      "notes": "POC manual override — accepted as ready"})
    if r.status_code != 200:
        fail("override", r)
    overridden = r.json()
    if overridden.get("status") != "completed":
        fail("override status didn't take", r)
    if not overridden.get("overridden_by") or not overridden.get("overridden_at"):
        fail("override actor/timestamp missing", r)
    print(f"✅ Override applied: {target} → completed by {overridden['overridden_by']} at {overridden['overridden_at']}")

    # ────────────────────────────────────────────────────────────────────
    hr("6. Re-fetch checklist — override must be reflected")
    r = s.get(f"{BASE}/admin/beta/checklist")
    ck2 = r.json()
    over_item = next((it for it in ck2["items"] if it["milestone_id"] == target), None)
    if not over_item or over_item["status"] != "completed":
        fail("re-fetched checklist did not reflect override", r)
    if not over_item.get("overridden_by"):
        fail("override actor missing on re-fetch", r)
    print(f"✅ Re-fetch confirmed override on {target}, completed={ck2['completed']}/7")

    # ────────────────────────────────────────────────────────────────────
    hr("7. DELETE override — restore to pending/auto")
    r = s.delete(f"{BASE}/admin/beta/checklist/{target}/override")
    if r.status_code != 200:
        fail("clear override", r)
    cleared = r.json()
    if cleared.get("overridden_by") is not None:
        fail("override not cleared", r)
    print(f"✅ Override cleared on {target} — overridden_by={cleared.get('overridden_by')}")

    # ────────────────────────────────────────────────────────────────────
    hr("8. GET /admin/beta/alerts — only critical|warning severities present")
    r = s.get(f"{BASE}/admin/beta/alerts")
    if r.status_code != 200:
        fail("alerts", r)
    al = r.json()
    severities = {a.get("severity") for a in al.get("items", [])}
    bad = severities - {"critical", "warning"}
    if bad:
        print(f"unexpected severities: {bad}")
        fail("alerts contain non-critical/warning items", r)
    print(f"✅ Alerts: total={al['counts']['total']} (critical={al['counts']['critical']} warning={al['counts']['warning']})")
    print(f"   severities present: {sorted(severities) if severities else 'none'}")

    # ────────────────────────────────────────────────────────────────────
    hr("9. GET /admin/beta/alerts?severity=warning — filter works")
    r = s.get(f"{BASE}/admin/beta/alerts", params={"severity": "warning"})
    if r.status_code != 200:
        fail("alerts filter", r)
    al2 = r.json()
    bad_filter = [a for a in al2.get("items", [])
                   if a.get("severity") != "warning"]
    if bad_filter:
        fail("warning filter returned non-warning items", r)
    print(f"✅ Severity filter works: warning-only count = {len(al2.get('items', []))}")

    # ────────────────────────────────────────────────────────────────────
    hr("ALL POC STEPS PASSED ✅")


if __name__ == "__main__":
    main()
