"""
LUMEN Sprint 10 — Ops layer (Blocks 4, 5, 8, 10)

Provides:
  Block 4  Backup Strategy        — mongodump + uploaded files snapshot
  Block 5  Monitoring             — DB latency, queue health, storage usage,
                                    payout failures
  Block 8  File Storage Audit     — KYC docs, payment proofs, statements,
                                    contracts: size + orphan detection
  Block 10 Disaster Recovery      — dry-run checks (missing files, broken
                                    ledger, deleted batches)

All endpoints are admin-only. Backups land in /app/backend/backups/<timestamp>/
so disk usage stays observable via the storage audit.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tarfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from lumen_api import db, require_admin, _now, _iso, _strip_mongo

logger = logging.getLogger("lumen.ops")

ROOT_DIR = Path(__file__).parent
BACKUP_DIR = ROOT_DIR / "backups"
UPLOADS_DIR = ROOT_DIR / "uploads"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

MAX_BACKUPS = 5

# Critical Lumen collections (Block 4 backup priority list)
CRITICAL_COLLECTIONS = [
    "users", "user_sessions",
    "lumen_investor_profiles", "lumen_kyc_documents",
    "lumen_assets", "lumen_investment_rounds",
    "lumen_investments", "lumen_ownerships",
    "lumen_contracts", "lumen_contract_templates",
    "lumen_payment_requests", "lumen_payment_proofs",
    "lumen_funding_accounts",
    "lumen_ledger_entries",
    "lumen_wallets", "lumen_withdrawal_requests",
    "lumen_payout_plans", "lumen_payout_batches", "lumen_payout_records",
    "lumen_audit_log",
]


# ============================================================================
#  Block 5 — Monitoring
# ============================================================================

async def measure_db_latency(samples: int = 3) -> dict:
    timings: list[float] = []
    for _ in range(samples):
        t0 = time.perf_counter()
        try:
            await db.command("ping")
            timings.append((time.perf_counter() - t0) * 1000.0)
        except Exception as exc:
            return {"healthy": False, "error": str(exc), "latency_ms": None}
    avg = sum(timings) / len(timings)
    return {
        "healthy": avg < 200.0,
        "latency_ms": round(avg, 2),
        "samples": [round(x, 2) for x in timings],
        "threshold_ms": 200.0,
    }


async def queue_health() -> dict:
    """Reports pending work that, if grows unbounded, points to failure."""
    pending_payments = await db.lumen_payment_requests.count_documents(
        {"status": {"$in": ["awaiting_payment", "submitted", "under_review"]}})
    submitted_proofs = await db.lumen_payment_requests.count_documents(
        {"status": "submitted"})
    pending_withdrawals = await db.lumen_withdrawal_requests.count_documents(
        {"status": {"$in": ["requested", "under_review", "approved", "processing"]}})
    submitted_kyc = await db.lumen_investor_profiles.count_documents(
        {"kyc_status": {"$in": ["submitted", "under_review"]}})
    unsigned_contracts = await db.lumen_contracts.count_documents(
        {"status": {"$in": ["draft", "awaiting_signature"]}})
    payout_batches_pending = await db.lumen_payout_batches.count_documents(
        {"status": {"$in": ["draft", "approved"]}})

    queues = [
        ("payments_pending", pending_payments, 50),
        ("payment_proofs_submitted", submitted_proofs, 30),
        ("withdrawals_in_flight", pending_withdrawals, 30),
        ("kyc_review_queue", submitted_kyc, 30),
        ("contracts_unsigned", unsigned_contracts, 50),
        ("payout_batches_pending", payout_batches_pending, 20),
    ]
    items = []
    overall_ok = True
    for name, count, threshold in queues:
        ok = count <= threshold
        if not ok:
            overall_ok = False
        items.append({
            "queue": name, "depth": count,
            "threshold": threshold, "healthy": ok,
        })
    return {"healthy": overall_ok, "queues": items}


def _dir_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


async def storage_usage() -> dict:
    uploads_total = _dir_size_bytes(UPLOADS_DIR)
    backups_total = _dir_size_bytes(BACKUP_DIR)
    breakdown = {}
    for sub in ["kyc", "payment_proofs", "contracts", "statements", "asset_content"]:
        breakdown[sub] = _dir_size_bytes(UPLOADS_DIR / sub)
    try:
        usage = shutil.disk_usage(str(ROOT_DIR))
        disk = {
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "used_pct": round(usage.used / usage.total * 100, 2) if usage.total else 0,
        }
    except Exception:
        disk = {}
    return {
        "uploads_total_bytes": uploads_total,
        "backups_total_bytes": backups_total,
        "uploads_breakdown_bytes": breakdown,
        "disk": disk,
        "healthy": (disk.get("used_pct", 0) < 90),
    }


async def payout_failures(hours: int = 24) -> dict:
    from datetime import timedelta
    since = _now() - timedelta(hours=hours)
    failed_batches = await db.lumen_payout_batches.count_documents(
        {"status": "cancelled", "updated_at": {"$gte": since}})
    rejected_withdrawals = await db.lumen_withdrawal_requests.count_documents(
        {"status": "rejected", "updated_at": {"$gte": since}})
    rejected_payments = await db.lumen_payment_requests.count_documents(
        {"status": "rejected", "updated_at": {"$gte": since}})
    return {
        "window_hours": hours,
        "failed_payout_batches": failed_batches,
        "rejected_withdrawals": rejected_withdrawals,
        "rejected_payments": rejected_payments,
        "healthy": failed_batches == 0,
    }


# ============================================================================
#  Block 8 — File Storage Audit (orphans)
# ============================================================================

async def storage_audit() -> dict:
    findings: dict[str, Any] = {}

    # KYC
    kyc_root = UPLOADS_DIR / "kyc"
    referenced_kyc = set()
    async for d in db.lumen_kyc_documents.find({}, {"storage_path": 1}):
        p = d.get("storage_path")
        if p:
            referenced_kyc.add(os.path.realpath(p))
    on_disk_kyc = set()
    if kyc_root.exists():
        for root, _dirs, files in os.walk(kyc_root):
            for f in files:
                on_disk_kyc.add(os.path.realpath(os.path.join(root, f)))
    orphans = list(on_disk_kyc - referenced_kyc)
    missing = [p for p in referenced_kyc if not os.path.exists(p)]
    findings["kyc"] = {
        "on_disk": len(on_disk_kyc),
        "referenced": len(referenced_kyc),
        "orphan_files": len(orphans),
        "missing_files": len(missing),
        "orphans_sample": [os.path.basename(p) for p in orphans[:5]],
        "missing_sample": [os.path.basename(p) for p in missing[:5]],
    }

    # Payment proofs
    pp_root = UPLOADS_DIR / "payment_proofs"
    referenced_pp = set()
    async for p in db.lumen_payment_proofs.find({}, {"storage_path": 1}):
        sp = p.get("storage_path")
        if sp:
            referenced_pp.add(os.path.realpath(sp))
    on_disk_pp = set()
    if pp_root.exists():
        for root, _dirs, files in os.walk(pp_root):
            for f in files:
                on_disk_pp.add(os.path.realpath(os.path.join(root, f)))
    pp_orphans = list(on_disk_pp - referenced_pp)
    pp_missing = [p for p in referenced_pp if not os.path.exists(p)]
    findings["payment_proofs"] = {
        "on_disk": len(on_disk_pp),
        "referenced": len(referenced_pp),
        "orphan_files": len(pp_orphans),
        "missing_files": len(pp_missing),
        "orphans_sample": [os.path.basename(p) for p in pp_orphans[:5]],
        "missing_sample": [os.path.basename(p) for p in pp_missing[:5]],
    }

    healthy = all(
        v.get("orphan_files", 0) <= 5 and v.get("missing_files", 0) == 0
        for v in findings.values()
    )
    return {"healthy": healthy, "findings": findings}


# ============================================================================
#  Block 4 — Backup + Restore (mongo dump + uploaded files)
# ============================================================================

def _list_backups() -> list[dict]:
    items = []
    if not BACKUP_DIR.exists():
        return items
    for sub in sorted(BACKUP_DIR.iterdir(), key=lambda p: p.name, reverse=True):
        if not sub.is_dir():
            continue
        manifest_path = sub / "manifest.json"
        manifest = {}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text())
            except Exception:
                manifest = {"error": "manifest unreadable"}
        items.append({
            "id": sub.name,
            "path": str(sub),
            "size_bytes": _dir_size_bytes(sub),
            "manifest": manifest,
        })
    return items


async def _create_backup_async(label: Optional[str] = None) -> dict:
    """JSON-export of every critical collection + tar of uploads dir.

    We use a JSON export instead of mongodump so the backup is portable across
    machines that may not have mongodump installed (preview pods). For real
    DR use, this can be swapped for mongodump trivially.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    suffix = f"-{label}" if label else ""
    target = BACKUP_DIR / f"backup-{ts}{suffix}"
    target.mkdir(parents=True, exist_ok=True)
    coll_target = target / "collections"
    coll_target.mkdir(exist_ok=True)

    collections_dumped: dict[str, int] = {}
    for name in CRITICAL_COLLECTIONS:
        try:
            docs = []
            async for d in db[name].find({}):
                d.pop("_id", None)
                # serialise datetimes
                for k, v in list(d.items()):
                    if isinstance(v, datetime):
                        d[k] = v.astimezone(timezone.utc).isoformat()
                docs.append(d)
            out_path = coll_target / f"{name}.json"
            out_path.write_text(json.dumps(docs, ensure_ascii=False, default=str))
            collections_dumped[name] = len(docs)
        except Exception as exc:
            logger.exception("backup of %s failed", name)
            collections_dumped[name] = -1

    # Files — tar gzip the uploads directory
    uploads_tar = None
    if UPLOADS_DIR.exists():
        uploads_tar = target / "uploads.tar.gz"
        with tarfile.open(uploads_tar, "w:gz") as tar:
            tar.add(UPLOADS_DIR, arcname="uploads")

    manifest = {
        "id": target.name,
        "created_at": _iso(_now()),
        "label": label,
        "collections": collections_dumped,
        "files_archive": str(uploads_tar.relative_to(target)) if uploads_tar else None,
        "total_size_bytes": _dir_size_bytes(target),
    }
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

    # Retention: keep newest MAX_BACKUPS
    backups = sorted(
        [p for p in BACKUP_DIR.iterdir() if p.is_dir()],
        key=lambda p: p.name, reverse=True,
    )
    for old in backups[MAX_BACKUPS:]:
        try:
            shutil.rmtree(old)
        except Exception:
            logger.exception("failed to prune backup %s", old)

    return manifest


async def restore_dry_run(backup_id: str) -> dict:
    """Verify that a backup archive is readable and structurally consistent.
    Does NOT touch live data. Used before a real restore."""
    target = BACKUP_DIR / backup_id
    if not target.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    manifest_path = target / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=400, detail="Manifest missing")
    manifest = json.loads(manifest_path.read_text())
    issues: list[str] = []
    coll_root = target / "collections"
    for name in CRITICAL_COLLECTIONS:
        p = coll_root / f"{name}.json"
        if not p.exists():
            issues.append(f"missing dump: {name}")
            continue
        try:
            json.loads(p.read_text())
        except Exception as exc:
            issues.append(f"corrupt dump: {name}: {exc!s}")
    tar_rel = manifest.get("files_archive")
    if tar_rel:
        tar_path = target / tar_rel
        if not tar_path.exists():
            issues.append("files archive missing")
        else:
            try:
                with tarfile.open(tar_path, "r:gz") as tar:
                    _ = tar.getnames()[:5]
            except Exception as exc:
                issues.append(f"files archive corrupt: {exc!s}")
    return {
        "backup_id": backup_id,
        "manifest": manifest,
        "issues": issues,
        "healthy": len(issues) == 0,
    }


# ============================================================================
#  Block 10 — Disaster Recovery dry-run checks
# ============================================================================

async def disaster_recovery_check() -> dict:
    """Verify the system can detect and report common DR scenarios safely."""
    findings: list[dict] = []

    # Scenario A: empty critical collections
    for name in ("lumen_assets", "lumen_ledger_entries"):
        cnt = await db[name].count_documents({})
        if cnt == 0:
            findings.append({
                "scenario": "empty_critical_collection",
                "collection": name,
                "severity": "high",
                "detail": "Collection is empty — platform inoperable.",
            })

    # Scenario B: orphan ledger references (handled by consistency I8)
    # Scenario C: contracts referencing missing assets
    bad_contracts = 0
    async for c in db.lumen_contracts.find({}, {"asset_id": 1, "id": 1}):
        aid = c.get("asset_id")
        if aid and not await db.lumen_assets.find_one({"id": aid}):
            bad_contracts += 1
    if bad_contracts:
        findings.append({
            "scenario": "contract_orphan_asset",
            "count": bad_contracts,
            "severity": "medium",
            "detail": "Contracts reference an asset that no longer exists.",
        })

    # Scenario D: payouts pointing to a deleted batch
    pointer_breaks = 0
    async for r in db.lumen_payout_records.find({"batch_id": {"$ne": None}},
                                                {"batch_id": 1}):
        bid = r.get("batch_id")
        if bid and not await db.lumen_payout_batches.find_one({"id": bid}):
            pointer_breaks += 1
    if pointer_breaks:
        findings.append({
            "scenario": "payout_records_orphan_batch",
            "count": pointer_breaks,
            "severity": "medium",
            "detail": "Payout records reference a deleted batch.",
        })

    # Scenario E: KYC docs referenced but file missing on disk
    missing_files = 0
    async for d in db.lumen_kyc_documents.find({}, {"storage_path": 1}):
        sp = d.get("storage_path")
        if sp and not os.path.exists(sp):
            missing_files += 1
    if missing_files:
        findings.append({
            "scenario": "kyc_files_missing",
            "count": missing_files,
            "severity": "high",
            "detail": "KYC documents have DB row but no file on disk.",
        })

    return {
        "healthy": len(findings) == 0,
        "scenario_count": len(findings),
        "findings": findings,
        "checked_at": _iso(_now()),
    }


# ============================================================================
#  Router
# ============================================================================

router = APIRouter(prefix="/api", tags=["lumen-ops"])


@router.get("/admin/monitoring/db")
async def admin_db_latency(_=Depends(require_admin)):
    return await measure_db_latency()


@router.get("/admin/monitoring/queues")
async def admin_queues(_=Depends(require_admin)):
    return await queue_health()


@router.get("/admin/monitoring/storage")
async def admin_storage(_=Depends(require_admin)):
    return await storage_usage()


@router.get("/admin/monitoring/payout-failures")
async def admin_payout_failures(hours: int = Query(24, ge=1, le=720),
                                _=Depends(require_admin)):
    return await payout_failures(hours)


@router.get("/admin/storage/audit")
async def admin_storage_audit(_=Depends(require_admin)):
    return await storage_audit()


@router.get("/admin/backups")
async def admin_list_backups(_=Depends(require_admin)):
    items = _list_backups()
    return {"items": items, "total": len(items), "max_retention": MAX_BACKUPS}


@router.post("/admin/backups")
async def admin_create_backup(label: Optional[str] = None, _=Depends(require_admin)):
    manifest = await _create_backup_async(label=label)
    return {"ok": True, "manifest": manifest}


@router.get("/admin/backups/{backup_id}/verify")
async def admin_verify_backup(backup_id: str, _=Depends(require_admin)):
    return await restore_dry_run(backup_id)


@router.delete("/admin/backups/{backup_id}")
async def admin_delete_backup(backup_id: str, _=Depends(require_admin)):
    target = BACKUP_DIR / backup_id
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="Backup not found")
    shutil.rmtree(target)
    return {"ok": True, "deleted": backup_id}


@router.get("/admin/disaster-recovery/check")
async def admin_dr_check(_=Depends(require_admin)):
    return await disaster_recovery_check()


__all__ = [
    "router", "measure_db_latency", "queue_health", "storage_usage",
    "payout_failures", "storage_audit", "disaster_recovery_check",
    "restore_dry_run", "_create_backup_async", "_list_backups",
    "CRITICAL_COLLECTIONS", "BACKUP_DIR",
]
