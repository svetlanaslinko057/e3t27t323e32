"""
LUMEN — Dividend + Tax + FX Contract Harness (D1 + D2 + D3)
===========================================================

11th harness. Tri-state report (PASS/FAIL/SKIP).

  D3 (Live FX)
    F1. GET /admin/fx/rates → USD & EUR rates > 0, meta.source present.
    F2. POST /admin/fx/refresh works; GET /admin/fx/history has ≥1 snapshot.
  D2 (Tax Engine — UA ПДФО 18% + ВЗ 1.5%)
    T1. GET /admin/tax/config → pdfo_rate=0.18, vz_rate=0.015, enabled.
    T2. GET /admin/tax/preview?gross=1000 → pdfo=180, vz=15, net=805.
    T3. Generated dividend batch records carry gross/tax/net; net = gross−tax;
        batch.total_tax_uah ≈ gross×0.195.
    T4. Crediting the batch increases /admin/tax/liability outstanding by ≈ tax.
  D1 (Dividend Scheduler)
    S1. GET /admin/payout-scheduler/due returns a structured due list.
    S2. A past-dated active plan is reported due; running the scheduler
        generates a batch (queued for approval) and the plan leaves the due set.
    S3. Scheduler is idempotent — a second run does not regenerate the period.

Run:  cd /app/backend && python dividend_tax_fx_contract.py
"""
from __future__ import annotations

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta

import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
BASE = os.environ.get("AUDIT_BASE_URL", "http://localhost:8001")
ADMIN_EMAIL = os.environ.get("AUDIT_ADMIN_EMAIL", "admin@devos.io")
ADMIN_PASS = os.environ.get("AUDIT_ADMIN_PASS", "admin123")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
ASSET_ID = os.environ.get("AUDIT_ASSET_ID", "asset-podilskyi")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("dividend-tax-fx")
db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]


class Report:
    def __init__(self):
        self.items, self.fail, self.skip = [], 0, 0

    def add(self, req, check, status, detail=""):
        self.items.append({"req": req, "check": check, "status": status, "detail": detail})
        log.info(f"[{status.upper()}] {req} :: {check} {('— ' + detail) if detail else ''}")
        if status == "fail":
            self.fail += 1
        elif status == "skip":
            self.skip += 1

    def summary(self):
        return {"total": len(self.items),
                "passed": sum(1 for i in self.items if i["status"] == "pass"),
                "failed": self.fail, "skipped": self.skip,
                "verdict": "PASS" if self.fail == 0 else "FAIL",
                "items": self.items, "generated_at": datetime.now(timezone.utc).isoformat()}


report = Report()


async def admin_client():
    c = httpx.AsyncClient(timeout=30)
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


async def fx_checks(c):
    r = await c.get(f"{BASE}/api/admin/fx/rates")
    body = r.json() if r.status_code == 200 else {}
    rates = body.get("rates", {})
    report.add("D3.F1", "FX rates expose USD & EUR > 0",
               "pass" if rates.get("USD", 0) > 0 and rates.get("EUR", 0) > 0 else "fail",
               f"USD={rates.get('USD')} EUR={rates.get('EUR')} src={body.get('meta', {}).get('source')}")
    rr = await c.post(f"{BASE}/api/admin/fx/refresh")
    rh = await c.get(f"{BASE}/api/admin/fx/history")
    n = len(rh.json().get("items", [])) if rh.status_code == 200 else 0
    report.add("D3.F2", "FX refresh + dated snapshot history",
               "pass" if rr.status_code == 200 and n >= 1 else "fail",
               f"refresh={rr.status_code} history={n}")


async def tax_unit_checks(c):
    r = await c.get(f"{BASE}/api/admin/tax/config")
    cfg = r.json() if r.status_code == 200 else {}
    ok = abs(cfg.get("pdfo_rate", 0) - 0.18) < 1e-9 and abs(cfg.get("vz_rate", 0) - 0.015) < 1e-9
    report.add("D2.T1", "Tax config = ПДФО 18% + ВЗ 1.5%",
               "pass" if ok and cfg.get("enabled") else "fail",
               f"pdfo={cfg.get('pdfo_rate')} vz={cfg.get('vz_rate')}")
    rp = await c.get(f"{BASE}/api/admin/tax/preview", params={"gross": 1000})
    p = rp.json() if rp.status_code == 200 else {}
    ok2 = (abs(p.get("pdfo", 0) - 180) < 0.5 and abs(p.get("vz", 0) - 15) < 0.5
           and abs(p.get("net", 0) - 805) < 0.5)
    report.add("D2.T2", "Preview gross=1000 → pdfo=180 vz=15 net=805",
               "pass" if ok2 else "fail",
               f"pdfo={p.get('pdfo')} vz={p.get('vz')} net={p.get('net')}")


async def _create_plan(c, freq, start_dt, expected=100000.0, type_="rental_income"):
    r = await c.post(f"{BASE}/api/admin/payout-plans", json={
        "asset_id": ASSET_ID, "type": type_, "frequency": freq,
        "expected_amount": expected,
        "start_date": start_dt.isoformat() if start_dt else None,
        "notes": "contract probe"})
    return r.json() if r.status_code == 200 else None


async def tax_integration_checks(c):
    plan = await _create_plan(c, "one_time", datetime.now(timezone.utc), expected=100000.0)
    if not plan:
        report.add("D2.T3", "generate dividend batch", "skip", "plan create failed")
        return
    rg = await c.post(f"{BASE}/api/admin/payout-plans/{plan['id']}/generate",
                      json={"amount": 100000.0})
    if rg.status_code != 200:
        report.add("D2.T3", "generate dividend batch", "fail", f"status={rg.status_code} {rg.text[:120]}")
        return
    batch = rg.json()
    gross = batch.get("total_gross_uah", 0)
    tax = batch.get("total_tax_uah", 0)
    net = batch.get("total_net_uah", 0)
    ok = (abs(gross - 100000) < 1.0 and abs(net - (gross - tax)) < 1.0
          and abs(tax - gross * 0.195) < 5.0)
    report.add("D2.T3", "batch records gross/tax/net (net=gross−tax, tax≈19.5%)",
               "pass" if ok else "fail", f"gross={gross} tax={tax} net={net}")
    # record-level breakdown present
    rec = await db.lumen_payout_records.find_one({"batch_id": batch["id"]})
    has_fields = rec and all(k in rec for k in ("gross_amount", "tax_pdfo", "tax_vz", "net_amount"))
    report.add("D2.T3", "per-record gross/tax/net fields present",
               "pass" if has_fields else "fail",
               f"net={rec.get('net_amount') if rec else None} gross={rec.get('gross_amount') if rec else None}")

    # T4 — liability delta on credit
    lb = await c.get(f"{BASE}/api/admin/tax/liability")
    before = lb.json().get("outstanding_liability_uah", 0) if lb.status_code == 200 else 0
    await c.post(f"{BASE}/api/admin/payout-batches/{batch['id']}/approve")
    rc = await c.post(f"{BASE}/api/admin/payout-batches/{batch['id']}/credit")
    la = await c.get(f"{BASE}/api/admin/tax/liability")
    after = la.json().get("outstanding_liability_uah", 0) if la.status_code == 200 else 0
    delta = round(after - before, 2)
    report.add("D2.T4", "crediting batch raises tax-liability account by ≈ withheld tax",
               "pass" if (rc.status_code == 200 and abs(delta - tax) < 5.0) else "fail",
               f"credit={rc.status_code} before={before} after={after} delta={delta} tax={tax}")


async def scheduler_checks(c):
    r = await c.get(f"{BASE}/api/admin/payout-scheduler/due")
    report.add("D1.S1", "scheduler due-list endpoint returns structure",
               "pass" if r.status_code == 200 and "items" in r.json() else "fail",
               f"status={r.status_code}")
    # a monthly plan starting 2 months ago, never generated → due now
    plan = await _create_plan(c, "monthly", datetime.now(timezone.utc) - timedelta(days=62),
                              expected=50000.0)
    if not plan:
        report.add("D1.S2", "past-dated plan due + scheduler generates", "skip", "plan create failed")
        return
    due1 = await c.get(f"{BASE}/api/admin/payout-scheduler/due")
    in_due = any(i["plan_id"] == plan["id"] for i in due1.json().get("items", []))
    run = await c.post(f"{BASE}/api/admin/payout-scheduler/run", json={"auto_credit": False})
    rb = run.json() if run.status_code == 200 else {}
    gen_for_plan = any(g["plan_id"] == plan["id"] for g in rb.get("generated", []))
    due2 = await c.get(f"{BASE}/api/admin/payout-scheduler/due")
    out_due = not any(i["plan_id"] == plan["id"] for i in due2.json().get("items", []))
    report.add("D1.S2", "past-dated plan reported due → scheduler generates a batch",
               "pass" if (in_due and gen_for_plan and out_due) else "fail",
               f"in_due={in_due} generated={gen_for_plan} left_due={out_due}")
    # idempotency — second run must not regenerate this plan's period
    run2 = await c.post(f"{BASE}/api/admin/payout-scheduler/run", json={"auto_credit": False})
    rb2 = run2.json() if run2.status_code == 200 else {}
    regen = any(g["plan_id"] == plan["id"] for g in rb2.get("generated", []))
    report.add("D1.S3", "scheduler idempotent (no double-generate same period)",
               "pass" if not regen else "fail", f"regenerated={regen}")


async def main():
    log.info(f"BASE={BASE} DB={DB_NAME} ASSET={ASSET_ID}")
    c = await admin_client()
    if not c:
        report.add("Auth", "admin login", "fail", "login failed")
        print(json.dumps(report.summary(), indent=2)); return 2
    report.add("Auth", "admin login", "pass", ADMIN_EMAIL)
    try:
        await fx_checks(c)
        await tax_unit_checks(c)
        await tax_integration_checks(c)
        await scheduler_checks(c)
    finally:
        await c.aclose()

    s = report.summary()
    print("\n" + "=" * 76)
    print(f"DIVIDEND + TAX + FX CONTRACT — {s['verdict']} "
          f"(pass={s['passed']} fail={s['failed']} skip={s['skipped']} / total={s['total']})")
    print("=" * 76)
    try:
        os.makedirs("/app/test_reports", exist_ok=True)
        with open("/app/test_reports/dividend_tax_fx_contract.json", "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning(f"write report failed: {e}")
    return 0 if s["verdict"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
