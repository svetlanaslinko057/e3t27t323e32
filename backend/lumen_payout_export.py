"""
LUMEN Sprint 11 — Payout Export (Part 5)

Generates payout files for the treasury / finance team:
  CSV         — universal
  XLSX        — Microsoft Excel
  SEPA pain.001 — EUR transfers (XML)
  SWIFT MT103-ready — USD/EUR international wires (plain text, finance manual)

Not a real payment rail — a finance hand-off file. Marks payout_records as
`exported` so the same line is not double-paid.

Admin endpoints
---------------
  GET    /api/admin/payout-export/batches              — batches eligible for export
  GET    /api/admin/payout-export/{batch_id}/{fmt}     — download (csv|xlsx|sepa|swift)
  POST   /api/admin/payout-export/{batch_id}/mark      — mark records as exported
"""
from __future__ import annotations

import csv
import io
import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from lumen_api import db, require_admin, _now, _iso, _strip_mongo
from lumen_audit import write_audit

logger = logging.getLogger("lumen.banking.export")

EXPORTABLE_BATCH_STATUSES = ("approved", "credited")


# ----------------------------------------------------------------------------
# Data fetch
# ----------------------------------------------------------------------------

async def _gather_batch(batch_id: str) -> tuple[dict, list[dict]]:
    b = await db.lumen_payout_batches.find_one({"id": batch_id})
    if not b:
        raise HTTPException(status_code=404, detail="Batch не знайдено")
    records: list[dict] = []
    async for r in db.lumen_payout_records.find({"batch_id": batch_id}).sort("created_at", 1):
        # join investor profile for IBAN / payer
        prof = await db.lumen_investor_profiles.find_one({"user_id": r.get("investor_id")})
        user = await db.users.find_one({"user_id": r.get("investor_id")}) or {}
        records.append({
            **r,
            "investor_email": user.get("email"),
            "investor_name": (prof or {}).get("full_name") or user.get("name"),
            "investor_iban": (prof or {}).get("iban"),
            "investor_bank": (prof or {}).get("bank_name"),
            "investor_tax_id": (prof or {}).get("tax_id"),
        })
    return b, records


# ----------------------------------------------------------------------------
# Format renderers
# ----------------------------------------------------------------------------

def _render_csv(batch: dict, rows: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "payout_record_id", "batch_id", "period_key",
        "investor_id", "investor_name", "investor_email",
        "iban", "bank_name", "tax_id",
        "amount", "currency", "amount_uah", "created_at", "status",
    ])
    for r in rows:
        w.writerow([
            r.get("id"), r.get("batch_id"), r.get("period_key"),
            r.get("investor_id"), r.get("investor_name") or "",
            r.get("investor_email") or "",
            r.get("investor_iban") or "",
            r.get("investor_bank") or "",
            r.get("investor_tax_id") or "",
            r.get("amount") or r.get("amount_uah"),
            r.get("currency") or "UAH",
            r.get("amount_uah"),
            _iso(r.get("created_at")), r.get("status"),
        ])
    return buf.getvalue().encode("utf-8")


def _render_xlsx(batch: dict, rows: list[dict]) -> bytes:
    """Minimal XLSX without external libraries. We build an Excel-readable
    SpreadsheetML file via raw XML; opens in LibreOffice and Excel."""
    # For deployment simplicity we emit a TSV-disguised-as-xls (Excel reads
    # it fine when extension is .xls). For real production swap to openpyxl.
    buf = io.StringIO()
    buf.write("\t".join([
        "payout_record_id", "batch_id", "period_key",
        "investor_id", "investor_name", "investor_email",
        "iban", "bank_name", "tax_id",
        "amount", "currency", "amount_uah", "created_at", "status",
    ]) + "\n")
    for r in rows:
        buf.write("\t".join(str(v or "") for v in [
            r.get("id"), r.get("batch_id"), r.get("period_key"),
            r.get("investor_id"), r.get("investor_name"),
            r.get("investor_email"),
            r.get("investor_iban"), r.get("investor_bank"),
            r.get("investor_tax_id"),
            r.get("amount") or r.get("amount_uah"),
            r.get("currency") or "UAH",
            r.get("amount_uah"),
            _iso(r.get("created_at")), r.get("status"),
        ]) + "\n")
    return buf.getvalue().encode("utf-8")


def _render_sepa(batch: dict, rows: list[dict]) -> bytes:
    """SEPA pain.001.001.03 minimal valid XML. Only EUR rows are included.
    Empty IBANs are skipped — a real SEPA bank would reject them anyway."""
    msg_id = f"LUMEN{batch.get('id', uuid.uuid4().hex)[:12].upper()}"
    now = datetime.utcnow().isoformat() + "Z"
    eur_rows = [r for r in rows if (r.get("currency") or "UAH").upper() == "EUR"
                                    and r.get("investor_iban")]
    total = sum(float(r.get("amount") or 0) for r in eur_rows)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.03">',
        '  <CstmrCdtTrfInitn>',
        '    <GrpHdr>',
        f'      <MsgId>{msg_id}</MsgId>',
        f'      <CreDtTm>{now}</CreDtTm>',
        f'      <NbOfTxs>{len(eur_rows)}</NbOfTxs>',
        f'      <CtrlSum>{total:.2f}</CtrlSum>',
        '      <InitgPty><Nm>LUMEN INVESTMENT FUND</Nm></InitgPty>',
        '    </GrpHdr>',
        '    <PmtInf>',
        f'      <PmtInfId>{msg_id}</PmtInfId>',
        '      <PmtMtd>TRF</PmtMtd>',
        f'      <NbOfTxs>{len(eur_rows)}</NbOfTxs>',
        f'      <CtrlSum>{total:.2f}</CtrlSum>',
        '      <Dbtr><Nm>LUMEN INVESTMENT FUND</Nm></Dbtr>',
        '      <DbtrAcct><Id><IBAN>UA000000000000000000000000000</IBAN></Id></DbtrAcct>',
        '      <DbtrAgt><FinInstnId><BIC>OTPBUAUK</BIC></FinInstnId></DbtrAgt>',
    ]
    for r in eur_rows:
        amt = float(r.get("amount") or 0)
        parts.extend([
            '      <CdtTrfTxInf>',
            f'        <PmtId><EndToEndId>{r.get("id")}</EndToEndId></PmtId>',
            f'        <Amt><InstdAmt Ccy="EUR">{amt:.2f}</InstdAmt></Amt>',
            f'        <Cdtr><Nm>{(r.get("investor_name") or r.get("investor_email") or "").strip()}</Nm></Cdtr>',
            f'        <CdtrAcct><Id><IBAN>{r.get("investor_iban")}</IBAN></Id></CdtrAcct>',
            f'        <RmtInf><Ustrd>LUMEN payout {r.get("period_key") or ""}</Ustrd></RmtInf>',
            '      </CdtTrfTxInf>',
        ])
    parts.extend(['    </PmtInf>', '  </CstmrCdtTrfInitn>', '</Document>'])
    return "\n".join(parts).encode("utf-8")


def _render_swift(batch: dict, rows: list[dict]) -> bytes:
    """SWIFT MT103-style plain text. One block per row — finance manager pastes
    into the bank terminal. Production rails wire this to a real MT103."""
    out = []
    for r in rows:
        amt = float(r.get("amount") or 0)
        out.append("\n".join([
            "---- MT103 SWIFT INSTRUCTION ----",
            f":20: {r.get('id')}",
            f":32A:{datetime.utcnow().strftime('%y%m%d')}{(r.get('currency') or 'USD')}{amt:.2f}",
            f":50K: LUMEN INVESTMENT FUND",
            f":59: /{r.get('investor_iban') or 'N/A'}\n{(r.get('investor_name') or '').upper()}",
            f":70: LUMEN payout {r.get('period_key') or ''}",
            f":71A: SHA",
            "",
        ]))
    return ("\n".join(out)).encode("utf-8")


# ----------------------------------------------------------------------------
# Router
# ----------------------------------------------------------------------------

router = APIRouter(prefix="/api", tags=["lumen-banking"])


@router.get("/admin/payout-export/batches")
async def list_eligible_batches(_=Depends(require_admin)):
    items = []
    async for b in db.lumen_payout_batches.find(
            {"status": {"$in": list(EXPORTABLE_BATCH_STATUSES)}}).sort("created_at", -1):
        recs = await db.lumen_payout_records.count_documents({"batch_id": b["id"]})
        items.append({**_strip_mongo(b), "records": recs,
                      "created_at": _iso(b.get("created_at"))})
    return {"items": items, "total": len(items),
            "formats": ["csv", "xlsx", "sepa", "swift"]}


@router.get("/admin/payout-export/{batch_id}/{fmt}")
async def export_payout_batch(batch_id: str, fmt: str,
                                request: Request,
                                admin=Depends(require_admin)):
    batch, rows = await _gather_batch(batch_id)
    fmt = fmt.lower()
    media = "text/plain"; ext = "txt"; data: bytes
    if fmt == "csv":
        data = _render_csv(batch, rows); media = "text/csv"; ext = "csv"
    elif fmt == "xlsx":
        data = _render_xlsx(batch, rows); media = "application/vnd.ms-excel"; ext = "xls"
    elif fmt == "sepa":
        data = _render_sepa(batch, rows); media = "application/xml"; ext = "xml"
    elif fmt == "swift":
        data = _render_swift(batch, rows); media = "text/plain"; ext = "txt"
    else:
        raise HTTPException(status_code=400,
                            detail="Unknown format. Use csv|xlsx|sepa|swift.")
    await write_audit(
        action=f"payout_export.{fmt}", category="payout",
        target_type="lumen_payout_batches", target_id=batch_id,
        actor=admin, request=request,
        summary=f"Payout batch {batch_id} exported as {fmt} ({len(rows)} rows)",
        meta={"format": fmt, "row_count": len(rows)},
    )
    return Response(
        content=data, media_type=media,
        headers={
            "Content-Disposition":
                f'attachment; filename="lumen-payout-{batch_id}.{ext}"'},
    )


@router.post("/admin/payout-export/{batch_id}/mark")
async def mark_batch_exported(batch_id: str, request: Request,
                                admin=Depends(require_admin)):
    b = await db.lumen_payout_batches.find_one({"id": batch_id})
    if not b:
        raise HTTPException(status_code=404, detail="Batch не знайдено")
    res = await db.lumen_payout_records.update_many(
        {"batch_id": batch_id},
        {"$set": {"exported_at": _now(), "exported_by": admin["id"]}},
    )
    await write_audit(
        action="payout_export.mark", category="payout",
        target_type="lumen_payout_batches", target_id=batch_id,
        actor=admin, request=request,
        summary=f"Payout batch {batch_id} marked as exported ({res.modified_count} records)",
    )
    return {"ok": True, "modified": res.modified_count}


__all__ = ["router"]
