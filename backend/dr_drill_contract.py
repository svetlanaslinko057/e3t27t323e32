#!/usr/bin/env python3
"""
dr_drill_contract.py — LUMEN Disaster Recovery Harness (Phase 1)
================================================================

The final catastrophe-consistency proof. A backup you have never restored is
not a backup; a restore you have never *re-derived and re-audited* is not a
recovery. This harness proves the whole cycle end-to-end:

    LIVE snapshot (read-only)
        → Backup → Restore (into an isolated scratch DB)
        → Rebuild Derived State   (recompute pools / balances / certificates)
        → Recalculate Pool + Investor Audits
        → Run Architecture + Pool Invariants
        → Compare LIVE vs RESTORED (deterministic aggregates)

It emits a single verdict:

    DR_READY = true
    LEDGER_MATCH = true
    POOL_MATCH = true
    OWNERSHIP_MATCH = true
    CERTIFICATES_MATCH = true
    CASH_AUDIT_MATCH = true

Design guarantees
-----------------
* READ-ONLY to the live DB. The harness only ever WRITES to / DROPS the scratch
  DB `"<DB_NAME><DR_SCRATCH_SUFFIX>"` (default suffix `_dr_verify`).
* No new financial entities. It re-uses the existing service logic
  (`recompute_pool`, `issue_pool_certificates`, `recompute_pool_balance`,
  `check_pool_invariants`, `build_pool_cash_audit`, `build_investor_balance_audit`,
  `lumen_architecture_invariants.run_all`). DB-injection is done by a thin,
  behaviour-preserving monkeypatch of the module-level `db` handle (the cash
  audit functions already accept a `db` parameter).
* The scratch DB is ALWAYS dropped on exit (even on error).

Run:   cd /app/backend && python dr_drill_contract.py
Exit:  0 = DR_READY, 2 = not ready / failure.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import MongoClient
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
SCRATCH_SUFFIX = os.environ.get("DR_SCRATCH_SUFFIX", "_dr_verify")
SCRATCH = f"{DB_NAME}{SCRATCH_SUFFIX}"

JSON_OUT = "/app/test_reports/dr_drill_contract.json"
MD_OUT = "/app/docs/DR_DRILL_REPORT.md"

TOL = 0.01  # money comparison tolerance (cents)


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}", flush=True)


# ───────────────────────────────────────────────────────────────────────────
# Step A — Backup → Restore (logical copy, dependency-free, deterministic)
# ───────────────────────────────────────────────────────────────────────────
def backup_restore(client: MongoClient) -> dict:
    """Copy every collection LIVE → SCRATCH and capture the source snapshot at
    copy time (immune to concurrent live writes). Returns per-collection counts."""
    src = client[DB_NAME]
    dst = client[SCRATCH]
    client.drop_database(SCRATCH)
    snapshot = {}
    for name in src.list_collection_names():
        docs = list(src[name].find({}))
        snapshot[name] = len(docs)
        if docs:
            dst[name].insert_many(docs, ordered=False)
    log(f"backup→restore: {len(snapshot)} collections copied into {SCRATCH}")
    return snapshot


def verify_restore_counts(client: MongoClient, snapshot: dict) -> tuple[bool, list]:
    dst = client[SCRATCH]
    mismatches = []
    for name, s in snapshot.items():
        d = dst[name].count_documents({})
        if s != d:
            mismatches.append({"collection": name, "backed_up": s, "restored": d})
    return (len(mismatches) == 0), mismatches


# ───────────────────────────────────────────────────────────────────────────
# Deterministic aggregate extractors (work on any Motor db handle)
# ───────────────────────────────────────────────────────────────────────────
POOL_FIELDS = ["confirmed_amount", "issued_units", "available_cash", "status",
               "released_amount", "refunded_amount"]


async def agg_pool_fields(db) -> dict:
    out = {}
    async for p in db["lumen_pools"].find({}):
        out[p["id"]] = {k: p.get(k) for k in POOL_FIELDS}
    return out


async def agg_ledger_sums(db) -> dict:
    out = {}
    cur = db["lumen_pool_ledger"].aggregate([
        {"$group": {"_id": {"pool": "$pool_id", "kind": "$kind"},
                    "v": {"$sum": "$amount"}}},
    ])
    async for r in cur:
        out[f"{r['_id']['pool']}|{r['_id']['kind']}"] = round(float(r["v"] or 0), 2)
    return out


async def agg_ownership(db) -> dict:
    out = {}
    cur = db["lumen_pool_allocations"].aggregate([
        {"$group": {"_id": {"pool": "$pool_id", "inv": "$investor_id"},
                    "u": {"$sum": "$units"}}},
    ])
    async for r in cur:
        out[f"{r['_id']['pool']}|{r['_id']['inv']}"] = int(round(float(r["u"] or 0)))
    return out


async def agg_certificates(db) -> dict:
    out = {}
    async for c in db["lumen_pool_certificates"].find({}):
        out[f"{c.get('pool_id')}|{c.get('investor_id')}"] = int(c.get("units") or 0)
    return out


async def agg_cash_audits(db, build_pool_cash_audit) -> dict:
    out = {}
    async for p in db["lumen_pools"].find({}, {"id": 1}):
        a = await build_pool_cash_audit(db, p["id"])
        out[p["id"]] = {
            "in": round(float(a.get("inflows", {}).get("total") or 0), 2),
            "out": round(float(a.get("outflows", {}).get("total") or 0), 2),
            "balance": round(float(a.get("cash_balance") or 0), 2),
            "reconciles": bool(a.get("reconciles")),
        }
    return out


# ───────────────────────────────────────────────────────────────────────────
# Comparators
# ───────────────────────────────────────────────────────────────────────────
def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def compare_maps(live: dict, restored: dict, label: str) -> dict:
    """Generic deep compare with money tolerance. Values may be scalars or dicts."""
    diffs = []
    keys = set(live) | set(restored)
    for k in sorted(keys):
        lv, rv = live.get(k, "<MISSING>"), restored.get(k, "<MISSING>")
        if isinstance(lv, dict) and isinstance(rv, dict):
            for f in set(lv) | set(rv):
                a, b = lv.get(f), rv.get(f)
                na, nb = _num(a), _num(b)
                if na is not None and nb is not None:
                    if abs(na - nb) > TOL:
                        diffs.append({"key": f"{k}.{f}", "live": a, "restored": b})
                elif a != b:
                    diffs.append({"key": f"{k}.{f}", "live": a, "restored": b})
        else:
            na, nb = _num(lv), _num(rv)
            if na is not None and nb is not None:
                if abs(na - nb) > TOL:
                    diffs.append({"key": k, "live": lv, "restored": rv})
            elif lv != rv:
                diffs.append({"key": k, "live": lv, "restored": rv})
    return {"label": label, "match": len(diffs) == 0,
            "live_keys": len(live), "restored_keys": len(restored),
            "diffs": diffs[:50]}


# ───────────────────────────────────────────────────────────────────────────
# Step B/C — Rebuild derived state + recompute audits on RESTORED (scratch)
# ───────────────────────────────────────────────────────────────────────────
async def rebuild_and_audit_scratch(scratch_db):
    """Monkeypatch service-layer db → scratch, then re-derive and re-audit."""
    import lumen_pool_os as pos
    import lumen_pool_cash as pcash
    import lumen_architecture_invariants as inv

    original = pos.db
    pos.db = scratch_db  # behaviour-preserving DB injection
    # Also inject into crypto_os so NFT mirroring during recompute stays on scratch.
    try:
        import lumen_crypto_os as _cos
        _cos_orig = _cos.db
        _cos.db = scratch_db
    except Exception:
        _cos = None
        _cos_orig = None
    try:
        # Rebuild every pool's derived state (idempotent: re-reads source-of-truth,
        # re-issues certificates only when missing).
        pool_ids = [p["id"] async for p in scratch_db["lumen_pools"].find({}, {"id": 1})]
        for pid in pool_ids:
            await pos.recompute_pool(pid)

        # Rebuild every investor/currency balance from distributions + withdrawals.
        pairs = set()
        for coll in ("lumen_revenue_distributions", "lumen_pool_withdrawals",
                     "lumen_pool_balances"):
            async for d in scratch_db[coll].find(
                    {}, {"investor_id": 1, "currency": 1}):
                iid, ccy = d.get("investor_id"), d.get("currency")
                if iid and ccy:
                    pairs.add((iid, ccy))
        for iid, ccy in pairs:
            await pos.recompute_pool_balance(iid, ccy)

        # Per-pool invariants on the restored books.
        pool_inv = {"total": 0, "passed": 0, "failed_pools": []}
        for pid in pool_ids:
            res = await pos.check_pool_invariants(pid)
            pool_inv["total"] += 1
            if res.get("all_passed"):
                pool_inv["passed"] += 1
            else:
                pool_inv["failed_pools"].append({"pool_id": pid, "counts": res.get("counts")})

        # Architecture invariants on the restored DB.
        arch = await inv.run_all(scratch_db)
        arch_summary = {"passed": arch.passed, "failed": arch.failed, "ok": arch.ok}

        # Statement B (platform-wide investor balances) on restored.
        balance_audit = await pcash.build_investor_balance_audit(scratch_db)

        return {
            "pool_invariants": pool_inv,
            "architecture_invariants": arch_summary,
            "investor_balance_audit": balance_audit,
            "build_pool_cash_audit": pcash.build_pool_cash_audit,
        }
    finally:
        pos.db = original
        if _cos is not None:
            _cos.db = _cos_orig


# ───────────────────────────────────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────────────────────────────────
async def run() -> int:
    import lumen_pool_cash as pcash

    started = datetime.now(timezone.utc)
    log(f"DR DRILL — live={DB_NAME} scratch={SCRATCH}")

    # Independent read-only Motor handle for LIVE comparison.
    live_motor = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
    scratch_motor_client = AsyncIOMotorClient(MONGO_URL)
    scratch_motor = scratch_motor_client[SCRATCH]

    pmclient = MongoClient(MONGO_URL)
    result = {
        "harness": "dr_drill_contract",
        "at": started.isoformat(),
        "db": DB_NAME,
        "scratch_db": SCRATCH,
    }
    try:
        # LIVE snapshot (read-only) BEFORE touching anything.
        live = {
            "pools": await agg_pool_fields(live_motor),
            "ledger": await agg_ledger_sums(live_motor),
            "ownership": await agg_ownership(live_motor),
            "certificates": await agg_certificates(live_motor),
            "cash_audits": await agg_cash_audits(live_motor, pcash.build_pool_cash_audit),
        }
        live_balance_audit = await pcash.build_investor_balance_audit(live_motor)
        log(f"LIVE snapshot: {len(live['pools'])} pools, "
            f"{len(live['certificates'])} certificates")

        # Step A — backup → restore.
        snapshot = backup_restore(pmclient)
        counts_ok, count_mismatches = verify_restore_counts(pmclient, snapshot)
        result["restore"] = {"collections": len(snapshot), "counts_match": counts_ok,
                             "mismatches": count_mismatches}

        # Step B/C — rebuild derived state + audits on scratch.
        rebuilt = await rebuild_and_audit_scratch(scratch_motor)

        # RESTORED snapshot (post-rebuild).
        restored = {
            "pools": await agg_pool_fields(scratch_motor),
            "ledger": await agg_ledger_sums(scratch_motor),
            "ownership": await agg_ownership(scratch_motor),
            "certificates": await agg_certificates(scratch_motor),
            "cash_audits": await agg_cash_audits(scratch_motor, pcash.build_pool_cash_audit),
        }

        # Step D — deterministic LIVE vs RESTORED comparisons.
        cmp_ledger = compare_maps(live["ledger"], restored["ledger"], "LEDGER")
        cmp_pool = compare_maps(live["pools"], restored["pools"], "POOL")
        cmp_owner = compare_maps(live["ownership"], restored["ownership"], "OWNERSHIP")
        cmp_cert = compare_maps(live["certificates"], restored["certificates"], "CERTIFICATES")
        cmp_cash = compare_maps(live["cash_audits"], restored["cash_audits"], "CASH_AUDIT")

        LEDGER_MATCH = cmp_ledger["match"]
        POOL_MATCH = cmp_pool["match"]
        OWNERSHIP_MATCH = cmp_owner["match"]
        CERTIFICATES_MATCH = (cmp_cert["match"]
                              and len(live["certificates"]) == len(restored["certificates"]))
        CASH_AUDIT_MATCH = (
            cmp_cash["match"]
            and abs(live_balance_audit.get("distributions_credited", 0)
                    - rebuilt["investor_balance_audit"].get("distributions_credited", 0)) <= TOL
            and bool(rebuilt["investor_balance_audit"].get("reconciles"))
        )

        # Restored consistency (books balance after recovery).
        pool_inv = rebuilt["pool_invariants"]
        arch = rebuilt["architecture_invariants"]
        RESTORED_INVARIANTS_OK = (pool_inv["failed_pools"] == [])
        ALL_CASH_RECONCILES = all(v["reconciles"] for v in restored["cash_audits"].values())

        DR_READY = bool(
            counts_ok and LEDGER_MATCH and POOL_MATCH and OWNERSHIP_MATCH
            and CERTIFICATES_MATCH and CASH_AUDIT_MATCH
            and RESTORED_INVARIANTS_OK and ALL_CASH_RECONCILES
        )

        result.update({
            "flags": {
                "DR_READY": DR_READY,
                "LEDGER_MATCH": LEDGER_MATCH,
                "POOL_MATCH": POOL_MATCH,
                "OWNERSHIP_MATCH": OWNERSHIP_MATCH,
                "CERTIFICATES_MATCH": CERTIFICATES_MATCH,
                "CASH_AUDIT_MATCH": CASH_AUDIT_MATCH,
                "RESTORED_INVARIANTS_OK": RESTORED_INVARIANTS_OK,
                "ALL_CASH_RECONCILES": ALL_CASH_RECONCILES,
            },
            "comparisons": {
                "LEDGER": cmp_ledger, "POOL": cmp_pool, "OWNERSHIP": cmp_owner,
                "CERTIFICATES": cmp_cert, "CASH_AUDIT": cmp_cash,
            },
            "restored_consistency": {
                "pool_invariants": pool_inv,
                "architecture_invariants": arch,
                "investor_balance_audit_reconciles":
                    bool(rebuilt["investor_balance_audit"].get("reconciles")),
            },
            "verdict": "DR_READY" if DR_READY else "NOT_READY",
        })

        _write_reports(result)
        _print_summary(result)
        return 0 if DR_READY else 2

    except Exception as exc:  # pragma: no cover
        import traceback
        result["error"] = f"{exc}"
        result["traceback"] = traceback.format_exc()
        result["verdict"] = "ERROR"
        _write_reports(result)
        log(f"DR DRILL ERROR: {exc}")
        return 2
    finally:
        try:
            pmclient.drop_database(SCRATCH)
            log(f"cleaned up scratch DB {SCRATCH}")
        except Exception as e:
            log(f"cleanup warning: {e}")
        pmclient.close()
        scratch_motor_client.close()


def _write_reports(result: dict) -> None:
    try:
        os.makedirs(os.path.dirname(JSON_OUT), exist_ok=True)
        with open(JSON_OUT, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        log(f"json write warning: {e}")
    try:
        os.makedirs(os.path.dirname(MD_OUT), exist_ok=True)
        flags = result.get("flags", {})
        lines = [
            "# LUMEN — Disaster Recovery Drill Report",
            "",
            f"- **Generated:** {result.get('at')}",
            f"- **Live DB:** `{result.get('db')}`  ·  **Scratch DB:** `{result.get('scratch_db')}`",
            f"- **Verdict:** **{result.get('verdict')}**",
            "",
            "## Verdict flags",
            "",
            "| Flag | Status |",
            "|------|--------|",
        ]
        for k, v in flags.items():
            lines.append(f"| {k} | {'✅ true' if v else '❌ false'} |")
        restore = result.get("restore", {})
        lines += [
            "",
            "## Backup → Restore",
            "",
            f"- Collections copied: **{restore.get('collections')}**",
            f"- Document counts match: **{restore.get('counts_match')}**",
            "",
            "## Restored consistency",
            "",
            f"- Pool invariants passed: "
            f"{result.get('restored_consistency', {}).get('pool_invariants', {}).get('passed')}"
            f"/{result.get('restored_consistency', {}).get('pool_invariants', {}).get('total')}",
            f"- Architecture invariants: "
            f"{result.get('restored_consistency', {}).get('architecture_invariants')}",
            f"- Investor balance audit reconciles: "
            f"{result.get('restored_consistency', {}).get('investor_balance_audit_reconciles')}",
            "",
            "_Read-only against the live DB. Scratch DB always dropped on exit._",
            "",
        ]
        with open(MD_OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception as e:
        log(f"md write warning: {e}")


def _print_summary(result: dict) -> None:
    flags = result.get("flags", {})
    print("\n" + "═" * 70)
    print(f"DR DRILL — {result.get('verdict')}")
    print("═" * 70)
    for k, v in flags.items():
        print(f"  {'✅' if v else '❌'}  {k} = {v}")
    for label, cmp in result.get("comparisons", {}).items():
        if not cmp["match"]:
            print(f"\n  ▸ {label} diffs (first {len(cmp['diffs'])}):")
            for d in cmp["diffs"][:10]:
                print(f"      {d}")
    print("═" * 70)


if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(run()))
