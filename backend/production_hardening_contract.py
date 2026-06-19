"""
LUMEN — Production Hardening Contract Harness (RV-3 compliance freshness +
ops runbooks + DR backup-restore + production switch)
==========================================================================

13th harness. Locks the production-readiness items raised in the owner audit
that are code-actionable & credential-free:

  H1. Production switch is a single LUMEN_ENV flag and exposes its controls:
      quick-access (demo bypass) + demo seeders are gated on env.
  H2. Watchlist auto-refresh works: refresh endpoint runs, records a refresh,
      keeps watchlist non-empty (resilient), and separates auto vs seed/manual.
  H3. Compliance freshness — at least one refresh record exists with a status
      (ok or fallback) and a timestamp.
  H4. The six incident runbooks are present in the SOP system.
  H5. Disaster-recovery: backup→restore→compare script runs and verifies all
      collections identical (exit 0).

Run:  cd /app/backend && python production_hardening_contract.py
"""
from __future__ import annotations

import os
import sys
import json
import asyncio
import logging
import subprocess
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
BASE = os.environ.get("AUDIT_BASE_URL", "http://localhost:8001")
ADMIN_EMAIL = os.environ.get("AUDIT_ADMIN_EMAIL", "admin@devos.io")
ADMIN_PASS = os.environ.get("AUDIT_ADMIN_PASS", "admin123")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("production-hardening")

RUNBOOKS = ["funding_failure", "withdrawal_failure", "reconciliation_failure",
            "kyc_escalation", "sanctions_hit", "payout_incident"]


class Report:
    def __init__(self):
        self.items, self.fail = [], 0

    def add(self, req, check, status, detail=""):
        self.items.append({"req": req, "check": check, "status": status, "detail": detail})
        log.info(f"[{status.upper()}] {req} :: {check} {('— ' + detail) if detail else ''}")
        if status == "fail":
            self.fail += 1

    def summary(self):
        return {"total": len(self.items),
                "passed": sum(1 for i in self.items if i["status"] == "pass"),
                "failed": self.fail,
                "verdict": "PASS" if self.fail == 0 else "FAIL",
                "items": self.items, "generated_at": datetime.now(timezone.utc).isoformat()}


report = Report()


async def admin_client():
    c = httpx.AsyncClient(timeout=60)
    r = await c.post(f"{BASE}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    if r.status_code != 200:
        return None
    sc = r.headers.get("set-cookie") or ""
    for part in sc.split(","):
        for kv in part.split(";"):
            kv = kv.strip()
            if kv.startswith("session_token="):
                c.headers["Cookie"] = f"session_token={kv.split('=', 1)[1].strip()}"
    return c


async def h1(c):
    r = await c.get(f"{BASE}/api/admin/launch-readiness/production-switch")
    body = r.json() if r.status_code == 200 else {}
    ctrl = body.get("controls", {})
    report.add("H1", "production switch exposes single LUMEN_ENV + controls",
               "pass" if r.status_code == 200 and "is_production" in body and ctrl else "fail",
               f"env={body.get('env')} controls={list(ctrl.keys())}")
    # demo bypass + seeders must be tied to env (in preview: enabled; would be off in prod)
    coupled = ("quick_access_login_enabled" in ctrl) and ("demo_seeders_enabled" in ctrl)
    report.add("H1", "demo bypass + demo seeders are env-gated controls",
               "pass" if coupled else "fail",
               f"quick_access={ctrl.get('quick_access_login_enabled')} seeders={ctrl.get('demo_seeders_enabled')}")


async def h2(c):
    r = await c.post(f"{BASE}/api/admin/compliance/watchlist/refresh")
    body = r.json() if r.status_code == 200 else {}
    ok = r.status_code == 200 and body.get("status") in ("ok", "fallback")
    report.add("H2", "watchlist refresh endpoint runs (ok|fallback)",
               "pass" if ok else "fail",
               f"status={body.get('status')} inserted={body.get('inserted')}")
    st = await c.get(f"{BASE}/api/admin/compliance/watchlist/refresh-status")
    s = st.json() if st.status_code == 200 else {}
    seed_manual = s.get("seed_manual_count", 0)
    report.add("H2", "watchlist stays populated + auto/seed separated (seed preserved)",
               "pass" if seed_manual >= 5 else "fail",
               f"auto={s.get('auto_fetched_count')} seed_manual={seed_manual}")


async def h3(c):
    st = await c.get(f"{BASE}/api/admin/compliance/watchlist/refresh-status")
    s = st.json() if st.status_code == 200 else {}
    last = s.get("last_refresh") or {}
    report.add("H3", "compliance freshness — refresh recorded with status+timestamp",
               "pass" if last.get("status") and last.get("at_iso") else "fail",
               f"last={last.get('status')} at={last.get('at_iso')}")


async def h4(c):
    r = await c.get(f"{BASE}/api/admin/sop")
    items = r.json().get("items", []) if r.status_code == 200 else []
    keys = {i.get("key") for i in items}
    missing = [k for k in RUNBOOKS if k not in keys]
    report.add("H4", "six incident runbooks present in SOP system",
               "pass" if not missing else "fail",
               f"present={[k for k in RUNBOOKS if k in keys]} missing={missing}")


def h5():
    script = os.path.join(os.path.dirname(__file__), "..", "scripts", "backup_restore_verify.py")
    try:
        p = subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=240)
        verdict_pass = p.returncode == 0 and "VERDICT: PASS" in (p.stdout + p.stderr)
        tail = (p.stdout.strip().splitlines() or ["<no output>"])[-1]
        report.add("H5", "DR backup→restore→compare verifies all collections identical",
                   "pass" if verdict_pass else "fail", f"rc={p.returncode} :: {tail[:90]}")
    except Exception as e:
        report.add("H5", "DR backup→restore→compare runs", "fail", str(e))


async def main():
    log.info(f"BASE={BASE}")
    c = await admin_client()
    if not c:
        report.add("Auth", "admin login", "fail", "login failed")
        print(json.dumps(report.summary(), indent=2)); return 2
    report.add("Auth", "admin login", "pass", ADMIN_EMAIL)
    try:
        await h1(c)
        await h2(c)
        await h3(c)
        await h4(c)
    finally:
        await c.aclose()
    h5()

    s = report.summary()
    print("\n" + "=" * 74)
    print(f"PRODUCTION HARDENING CONTRACT — {s['verdict']} "
          f"(pass={s['passed']} fail={s['failed']} / total={s['total']})")
    print("=" * 74)
    try:
        os.makedirs("/app/test_reports", exist_ok=True)
        with open("/app/test_reports/production_hardening_contract.json", "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning(f"write report failed: {e}")
    return 0 if s["verdict"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
