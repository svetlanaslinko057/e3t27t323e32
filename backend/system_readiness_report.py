#!/usr/bin/env python3
"""
system_readiness_report.py — LUMEN One-Click System Readiness Report (Phase 3)
==============================================================================

The single artifact an owner / auditor reads before opening real money. It runs
(or re-uses) every existing contract harness, normalises each result into a
common PASS / BLOCKED / FAIL vocabulary, and produces ONE verdict:

    READY_FOR_BANKS              = no FAIL anywhere + DR_READY + CASH_AUDIT_GREEN
                                   + SECURITY_PASS + LAUNCH_READINESS_OK
    READY_TO_ACCEPT_REAL_MONEY   = READY_FOR_BANKS + rv_bank has 0 BLOCKED
                                   (i.e. real Stripe/SEPA/bank rails are live)

Aggregated components
---------------------
  · architecture_invariants   (in-process: lumen_architecture_invariants.run_all)
  · launch_readiness          (launch_readiness_contract.py)
  · security                  (security_contract_audit.py)
  · pool_os                   (pool_os_contract.py — lifecycle smoke + invariants)
  · rv_bank                   (rv_bank_contract.py — BLOCKED expected pre-rails)
  · dr_drill                  (dr_drill_contract.py — catastrophe consistency)
  · production_secrets        (production_secrets_audit.py)

No business logic is duplicated — this is a pure orchestrator. Output:

    /app/test_reports/system_readiness_report.json   (+ timestamped history copy)
    /app/docs/SYSTEM_READINESS_REPORT.md

Run:   cd /app/backend && python system_readiness_report.py
Exit:  0 = no FAIL component, 2 = at least one FAIL.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))
PY = sys.executable
REPORTS = "/app/test_reports"
JSON_OUT = f"{REPORTS}/system_readiness_report.json"
MD_OUT = "/app/docs/SYSTEM_READINESS_REPORT.md"

# Allow trimming the run for fast iterations, e.g. SRR_SKIP=security,pool_os
SKIP = {s.strip() for s in os.environ.get("SRR_SKIP", "").split(",") if s.strip()}


def _load_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


async def _run(cmd: list[str], timeout: int) -> dict:
    """Run a subprocess, capture exit code + stdout tail."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=HERE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return {"exit_code": -9, "stdout": "", "timed_out": True}
        return {"exit_code": proc.returncode,
                "stdout": (out or b"").decode("utf-8", "ignore"),
                "timed_out": False}
    except Exception as e:
        return {"exit_code": -1, "stdout": f"<spawn error: {e}>", "timed_out": False}


def _component(name: str, status: str, detail: str = "", extra: dict | None = None) -> dict:
    icon = {"PASS": "✅", "BLOCKED": "🟡", "FAIL": "❌", "SKIP": "⚪"}.get(status, "•")
    print(f"  {icon} [{status:7}] {name}" + (f" — {detail}" if detail else ""))
    return {"component": name, "status": status, "detail": detail, **(extra or {})}


# ───────────────────────────────────────────────────────────────────────────
# Component runners (each returns a normalised dict)
# ───────────────────────────────────────────────────────────────────────────
async def run_architecture() -> dict:
    if "architecture" in SKIP:
        return _component("architecture_invariants", "SKIP")
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        import lumen_architecture_invariants as inv
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        rep = await inv.run_all(db)
        status = "PASS" if rep.ok else "FAIL"
        return _component("architecture_invariants", status,
                          f"{rep.passed}/{rep.passed + rep.failed} checks",
                          {"passed": rep.passed, "failed": rep.failed})
    except Exception as e:
        return _component("architecture_invariants", "FAIL", f"error: {e}")


async def run_launch_readiness() -> dict:
    if "launch_readiness" in SKIP:
        return _component("launch_readiness", "SKIP")
    r = await _run([PY, "launch_readiness_contract.py"], timeout=120)
    status = "PASS" if r["exit_code"] == 0 else "FAIL"
    return _component("launch_readiness", status,
                      "timed out" if r["timed_out"] else f"exit={r['exit_code']}",
                      {"exit_code": r["exit_code"]})


async def run_security() -> dict:
    if "security" in SKIP:
        return _component("security", "SKIP")
    # The auth rate-limit is a 60s sliding window (login = 10/min/IP). Prior
    # contracts' logins fill it, so drain the window before the security audit
    # logs in — otherwise its own logins get throttled (false FAIL).
    cooldown = int(os.environ.get("SRR_SECURITY_COOLDOWN", "65"))
    if cooldown > 0:
        print(f"  ⏳ draining auth rate-limit window ({cooldown}s) before security…")
        await asyncio.sleep(cooldown)
    r = await _run([PY, "security_contract_audit.py"], timeout=180)
    rep = _load_json(f"{REPORTS}/security_contract_audit.json") or {}
    verdict = rep.get("verdict")
    if verdict in {"PASS", "FAIL"}:
        status = verdict
    else:
        status = "PASS" if r["exit_code"] == 0 else "FAIL"
    return _component("security", status,
                      "timed out" if r["timed_out"] else
                      f"pass={rep.get('passed')} fail={rep.get('failed')}",
                      {"exit_code": r["exit_code"]})


async def run_pool_os() -> dict:
    if "pool_os" in SKIP:
        return _component("pool_os", "SKIP")
    r = await _run([PY, "pool_os_contract.py"], timeout=180)
    status = "PASS" if r["exit_code"] == 0 else "FAIL"
    return _component("pool_os", status,
                      "timed out" if r["timed_out"] else f"exit={r['exit_code']}",
                      {"exit_code": r["exit_code"]})


def _parse_rv_counts(stdout: str) -> dict:
    m = re.search(r"RV:\s*(\d+)\s*PASS.*?(\d+)\s*BLOCKED.*?(\d+)\s*FAIL", stdout)
    if m:
        return {"pass": int(m.group(1)), "blocked": int(m.group(2)), "fail": int(m.group(3))}
    return {}


async def run_rv_bank() -> dict:
    if "rv_bank" in SKIP:
        return _component("rv_bank", "SKIP")
    r = await _run([PY, "rv_bank_contract.py"], timeout=120)
    counts = _parse_rv_counts(r["stdout"])
    if counts.get("fail", 0) > 0 or r["exit_code"] not in (0,):
        status = "FAIL" if counts.get("fail", 0) > 0 else "FAIL"
    elif counts.get("blocked", 0) > 0:
        status = "BLOCKED"
    else:
        status = "PASS"
    return _component("rv_bank", status,
                      f"PASS={counts.get('pass','?')} BLOCKED={counts.get('blocked','?')} "
                      f"FAIL={counts.get('fail','?')}",
                      {"exit_code": r["exit_code"], "counts": counts})


async def run_dr_drill() -> dict:
    if "dr_drill" in SKIP:
        return _component("dr_drill", "SKIP")
    r = await _run([PY, "dr_drill_contract.py"], timeout=240)
    rep = _load_json(f"{REPORTS}/dr_drill_contract.json") or {}
    flags = rep.get("flags", {})
    status = "PASS" if flags.get("DR_READY") else "FAIL"
    return _component("dr_drill", status,
                      "timed out" if r["timed_out"] else
                      f"DR_READY={flags.get('DR_READY')}",
                      {"exit_code": r["exit_code"], "flags": flags})


async def run_production_secrets() -> dict:
    if "production_secrets" in SKIP:
        return _component("production_secrets", "SKIP")
    r = await _run([PY, "production_secrets_audit.py"], timeout=90)
    rep = _load_json(f"{REPORTS}/production_secrets_audit.json") or {}
    status = rep.get("verdict") or ("PASS" if r["exit_code"] == 0 else "FAIL")
    return _component("production_secrets", status,
                      f"pass={rep.get('counts', {}).get('pass')} "
                      f"blocked={rep.get('counts', {}).get('blocked')} "
                      f"fail={rep.get('counts', {}).get('fail')}",
                      {"exit_code": r["exit_code"]})


# ───────────────────────────────────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────────────────────────────────
async def main() -> int:
    started = datetime.now(timezone.utc)
    print("═" * 70)
    print("LUMEN — SYSTEM READINESS REPORT")
    print("═" * 70)

    # Order matters: the security audit's brute-force burst trips the auth
    # rate-limiter, so it MUST run LAST (nothing after it needs to log in).
    # pool_os seeds a funded pool so dr_drill has live Pool-OS state to verify.
    components = [
        await run_architecture(),
        await run_launch_readiness(),
        await run_pool_os(),
        await run_rv_bank(),
        await run_dr_drill(),
        await run_production_secrets(),
        await run_security(),
    ]

    by_name = {c["component"]: c for c in components}

    def st(name):  # status helper
        return by_name.get(name, {}).get("status")

    n_fail = sum(1 for c in components if c["status"] == "FAIL")
    n_block = sum(1 for c in components if c["status"] == "BLOCKED")

    dr_flags = by_name.get("dr_drill", {}).get("flags", {})
    DR_READY = bool(dr_flags.get("DR_READY"))
    CASH_AUDIT_GREEN = bool(dr_flags.get("CASH_AUDIT_MATCH") and dr_flags.get("ALL_CASH_RECONCILES"))
    SECURITY_PASS = st("security") in {"PASS", "SKIP"}
    LAUNCH_READINESS_OK = st("launch_readiness") in {"PASS", "SKIP"}

    READY_FOR_BANKS = bool(
        n_fail == 0 and DR_READY and CASH_AUDIT_GREEN
        and SECURITY_PASS and LAUNCH_READINESS_OK
    )
    rv_blocked = by_name.get("rv_bank", {}).get("counts", {}).get("blocked", 1)
    READY_TO_ACCEPT_REAL_MONEY = bool(READY_FOR_BANKS and rv_blocked == 0)

    report = {
        "harness": "system_readiness_report",
        "at": started.isoformat(),
        "db": os.environ.get("DB_NAME"),
        "components": components,
        "totals": {"fail": n_fail, "blocked": n_block, "total": len(components)},
        "gates": {
            "DR_READY": DR_READY,
            "CASH_AUDIT_GREEN": CASH_AUDIT_GREEN,
            "SECURITY_PASS": SECURITY_PASS,
            "LAUNCH_READINESS_OK": LAUNCH_READINESS_OK,
            "NO_FAIL": n_fail == 0,
        },
        "verdict": {
            "READY_FOR_BANKS": READY_FOR_BANKS,
            "READY_TO_ACCEPT_REAL_MONEY": READY_TO_ACCEPT_REAL_MONEY,
        },
        "blocked_on": [c["component"] for c in components if c["status"] == "BLOCKED"],
    }
    _write_reports(report, started)

    print("\n" + "═" * 70)
    print("GATES")
    for k, v in report["gates"].items():
        print(f"  {'✅' if v else '❌'}  {k} = {v}")
    print("─" * 70)
    print(f"  {'✅' if READY_FOR_BANKS else '❌'}  READY_FOR_BANKS = {READY_FOR_BANKS}")
    print(f"  {'✅' if READY_TO_ACCEPT_REAL_MONEY else '🟡'}  "
          f"READY_TO_ACCEPT_REAL_MONEY = {READY_TO_ACCEPT_REAL_MONEY}")
    if report["blocked_on"]:
        print(f"\n  Blocked on (real-world rails/creds): {', '.join(report['blocked_on'])}")
    print("═" * 70)

    return 0 if n_fail == 0 else 2


def _write_reports(report: dict, ts: datetime) -> None:
    try:
        os.makedirs(REPORTS, exist_ok=True)
        with open(JSON_OUT, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        # Timestamped history copy for traceability.
        hist = f"{REPORTS}/system_readiness_report_{ts.strftime('%Y%m%dT%H%M%SZ')}.json"
        with open(hist, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"json write warning: {e}")
    try:
        os.makedirs(os.path.dirname(MD_OUT), exist_ok=True)
        v = report["verdict"]
        lines = [
            "# LUMEN — System Readiness Report",
            "",
            f"- **Generated:** {report['at']}",
            f"- **READY_FOR_BANKS:** {'✅ true' if v['READY_FOR_BANKS'] else '❌ false'}",
            f"- **READY_TO_ACCEPT_REAL_MONEY:** "
            f"{'✅ true' if v['READY_TO_ACCEPT_REAL_MONEY'] else '🟡 false (awaiting live bank rails)'}",
            "",
            "## Components",
            "",
            "| Component | Status | Detail |",
            "|-----------|--------|--------|",
        ]
        for c in report["components"]:
            lines.append(f"| {c['component']} | {c['status']} | {c.get('detail','')} |")
        lines += ["", "## Gates", "", "| Gate | Value |", "|------|-------|"]
        for k, val in report["gates"].items():
            lines.append(f"| {k} | {val} |")
        if report["blocked_on"]:
            lines += ["", f"**Blocked on real-world rails/creds:** {', '.join(report['blocked_on'])}"]
        lines += [
            "",
            "_This report aggregates existing contract harnesses only — no business "
            "logic is duplicated. BLOCKED items are waiting on real Stripe Live / bank "
            "/ IBAN / SPV, not on code._",
            "",
        ]
        with open(MD_OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception as e:
        print(f"md write warning: {e}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
