#!/usr/bin/env python3
"""
launch_readiness_contract.py — Contract harness for Production Launch Readiness v1.0
====================================================================================

Validates the 130-item checklist engine end-to-end:

  C1  Seed integrity        — 130 unique items, valid severity/owner/domain, 12 domains
  C2  Detector coverage     — every `auto` key has a registered detector
  C3  State assembly        — build_checklist_state shape + totals add up
  C4  Auto-eval honesty     — owner/credential blockers stay pending (no false greens)
  C5  Override roundtrip     — set→completed flips status; clear→restores auto
  C6  Blocker accounting     — go_live_ready ⇔ zero open blockers
  C7  Doc generation        — canonical doc contains all 12 domains + 130 rows
  C8  API auth + endpoints   — 401 without cookie, 200 with admin cookie

Run:  python3 backend/launch_readiness_contract.py
Exit code 0 = all pass.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import httpx  # noqa: E402

BASE = os.environ.get("LR_CONTRACT_BASE", "http://localhost:8001")
ADMIN_EMAIL = os.environ.get("LR_ADMIN_EMAIL", "admin@atlas.dev")
ADMIN_PASS = os.environ.get("LR_ADMIN_PASS", "admin123")

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = ""):
    (PASS if cond else FAIL).append(name)
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail and not cond else ""))


async def main() -> int:
    from launch_checklist_seed import (
        CHECKLIST_ITEMS, DOMAINS, SEVERITIES, OWNERS, item_index,
    )
    from launch_checklist_engine import (
        _DETECTORS, _BETA_MILESTONE_MAP, build_checklist_state,
        set_override, clear_override, render_canonical_doc,
    )

    print("\n── C1 Seed integrity ──")
    ids = [i["id"] for i in CHECKLIST_ITEMS]
    check("C1.1 exactly 130 items", len(CHECKLIST_ITEMS) == 130, f"got {len(CHECKLIST_ITEMS)}")
    check("C1.2 unique ids", len(set(ids)) == len(ids))
    check("C1.3 12 domains", len(DOMAINS) == 12, f"got {len(DOMAINS)}")
    check("C1.4 valid severities", all(i["severity"] in SEVERITIES for i in CHECKLIST_ITEMS))
    check("C1.5 valid owners", all(i["owner"] in OWNERS for i in CHECKLIST_ITEMS))
    dom_ids = {d["id"] for d in DOMAINS}
    check("C1.6 valid domains", all(i["domain"] in dom_ids for i in CHECKLIST_ITEMS))
    check("C1.7 bilingual labels", all(i["label_uk"] and i["label_en"] for i in CHECKLIST_ITEMS))
    blockers = [i for i in CHECKLIST_ITEMS if i["severity"] == "blocker"]
    check("C1.8 has blockers", len(blockers) >= 15, f"{len(blockers)} blockers")

    print("\n── C2 Detector coverage ──")
    auto_keys = {i["auto"] for i in CHECKLIST_ITEMS if i["auto"]}
    covered = set(_DETECTORS.keys()) | set(_BETA_MILESTONE_MAP.keys())
    missing = auto_keys - covered
    check("C2.1 all auto keys have detectors", not missing, f"missing: {missing}")

    print("\n── C3 State assembly ──")
    state = await build_checklist_state()
    t = state["totals"]
    check("C3.1 totals add up", t["completed"] + t["pending"] + t["not_applicable"] == t["total"] == 130)
    check("C3.2 readiness pct in range", 0 <= state["readiness_pct"] <= 100)
    check("C3.3 12 domain rollups", len(state["domains"]) == 12)
    check("C3.4 each domain has items", all(d["total"] > 0 for d in state["domains"]))
    item_count = sum(len(d["items"]) for d in state["domains"])
    check("C3.5 all items resolved", item_count == 130, f"got {item_count}")

    print("\n── C4 Auto-eval honesty (no false greens on owner blockers) ──")
    flat = {it["id"]: it for d in state["domains"] for it in d["items"]}
    owner_blocked = ["fund_stripe_live", "fund_real_iban", "wd_channel_live",
                     "mc_real_cycle_executed", "legal_regulatory_stance"]
    for oid in owner_blocked:
        it = flat.get(oid)
        check(f"C4 {oid} not auto-green", bool(it) and it["status"] == "pending",
              f"status={it['status'] if it else 'MISSING'}")
    # auto-proven items SHOULD be green
    check("C4 lr2 invariants item present", "di_invariants_pass" in flat)

    print("\n── C5 Override roundtrip ──")
    test_id = "fund_stripe_live"
    before = flat[test_id]["status"]
    res = await set_override(test_id, "completed", "contract test evidence", "contract@test")
    check("C5.1 override sets completed", res["status"] == "completed" and res["source"] == "override")
    state2 = await build_checklist_state()
    flat2 = {it["id"]: it for d in state2["domains"] for it in d["items"]}
    check("C5.2 state reflects override", flat2[test_id]["status"] == "completed")
    cleared = await clear_override(test_id)
    check("C5.3 clear restores auto/pending", cleared["status"] == before)

    print("\n── C6 Blocker accounting ──")
    open_blockers = state["blockers"]["open"]
    check("C6.1 go_live ⇔ no open blockers",
          state["go_live_ready"] == (len(open_blockers) == 0))
    check("C6.2 blockers green+open = total",
          state["blockers"]["green"] + len(open_blockers) == state["blockers"]["total"])

    print("\n── C7 Doc generation ──")
    doc = render_canonical_doc(state)
    check("C7.1 doc non-empty", len(doc) > 3000)
    check("C7.2 doc has all domains", all(d["label_en"] in doc for d in DOMAINS))
    check("C7.3 doc row count ~130", doc.count("🛑") + doc.count("🔴") + doc.count("🟠") + doc.count("🟡") >= 130)
    check("C7.4 canonical file exists",
          os.path.exists("/app/docs/PRODUCTION_LAUNCH_READINESS_v1.0.md"))

    print("\n── C8 API auth + endpoints ──")
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        r = await c.get("/api/admin/launch-readiness/checklist/summary")
        check("C8.1 401 without auth", r.status_code == 401, f"got {r.status_code}")
        lg = await c.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
        check("C8.2 admin login ok", lg.status_code == 200, f"got {lg.status_code}")
        # Extract session_token from Set-Cookie (Secure cookies are dropped by
        # httpx over http://localhost, so set it explicitly on the client).
        token = lg.cookies.get("session_token")
        if not token:
            for sc in lg.headers.get_list("set-cookie"):
                if sc.startswith("session_token="):
                    token = sc.split("=", 1)[1].split(";", 1)[0]
                    break
        if token:
            c.headers["Cookie"] = f"session_token={token}"
        r2 = await c.get("/api/admin/launch-readiness/checklist")
        check("C8.3 checklist 200 with auth", r2.status_code == 200, f"got {r2.status_code}")
        if r2.status_code == 200:
            body = r2.json()
            check("C8.4 checklist payload 130", body["totals"]["total"] == 130)
        r3 = await c.post("/api/admin/launch-readiness/checklist/__bad__/override",
                          json={"status": "completed"})
        check("C8.5 unknown id → 404", r3.status_code == 404, f"got {r3.status_code}")
        r4 = await c.post("/api/admin/launch-readiness/checklist/fund_real_iban/override",
                          json={"status": "bogus"})
        check("C8.6 bad status → 400", r4.status_code == 400, f"got {r4.status_code}")
        # cleanup any override created during API test
        await c.delete("/api/admin/launch-readiness/checklist/fund_real_iban/override")
        rdoc = await c.get("/api/admin/launch-readiness/checklist/doc")
        check("C8.7 doc endpoint 200", rdoc.status_code == 200 and len(rdoc.text) > 3000)

    print(f"\n════════ RESULT: {len(PASS)} passed, {len(FAIL)} failed ════════")
    if FAIL:
        print("FAILED:", ", ".join(FAIL))
        return 1
    print("ALL CONTRACT CHECKS GREEN ✅")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
