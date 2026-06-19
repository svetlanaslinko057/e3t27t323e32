"""
LUMEN 2.0 — Phase G14 — Audit & Trust Graph OS
==============================================

Consolidated, READ-ONLY traceability layer. Goal: every certificate, every
investor, every entity-id can be opened and a full lifecycle story can be
reconstructed from the REAL collections (no migration, no mocks).

Endpoints (prefix /api)
-----------------------
Investor
    GET  /investor/trust-graph                         — full graph for my certs
    GET  /investor/certificates/{cert_id}/trust-graph  — one cert lineage
    GET  /investor/certificates/{cert_id}/timeline     — issued/voided + payouts +
                                                         secondary trades + governance
    GET  /investor/timeline                            — personal timeline
                                                         (compliance / accreditation +
                                                         ownership changes)

Admin
    GET  /admin/audit/explorer?q=<entity_id>           — universal lookup with
                                                         linked rows + timeline

Nothing here mutates state. Audit writes still happen via lumen_audit.write_audit.
"""
from __future__ import annotations

import logging
from shared.money import fmt_uah_as_usd, usd_from_uah  # USD display layer
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from lumen_api import db, get_current_user, require_admin, _strip_mongo, _iso

logger = logging.getLogger("lumen.audit_os")
router = APIRouter(prefix="/api", tags=["lumen-audit-os"])


def _uid(u: dict) -> str:
    return u.get("id") or u.get("user_id")


EVENT_LABELS_UK = {
    "issued": "Випущено",
    "voided": "Анульовано",
    "reissued": "Перевипущено",
    "replaced": "Замінено",
    "transferred": "Передано",
    "verified": "Перевірено",
    "downloaded": "Завантажено",
}


# ════════════════════════════════════════════════════════════════════════════
# Trust graph walk — one certificate
# ════════════════════════════════════════════════════════════════════════════

async def _cert_trust_graph(cert: dict) -> dict:
    """Walk Certificate → SPV → Operator → Asset → Fund (if any) for one cert."""
    nodes: list[dict] = []
    edges: list[dict] = []
    seen: set[str] = set()

    def add(nid: str, ntype: str, label: str, meta: Optional[dict] = None) -> None:
        if nid in seen:
            return
        seen.add(nid)
        nodes.append({"id": nid, "type": ntype, "label": label, **(meta or {})})

    inv_id = cert.get("investor_id")
    asset_id = cert.get("asset_id")
    inv_name = cert.get("investor_name") or "Інвестор"

    add(f"investor:{inv_id}", "investor", inv_name)
    add(f"cert:{cert.get('id')}", "certificate",
        cert.get("certificate_number") or "Сертифікат",
        {"ownership_percent": cert.get("ownership_percent"),
         "units": cert.get("units"),
         "value_uah": cert.get("value_uah"),
         "status": cert.get("status")})
    edges.append({"from": f"investor:{inv_id}", "to": f"cert:{cert.get('id')}",
                  "rel": "holds"})

    # Asset
    asset = await db.lumen_assets.find_one({"id": asset_id}, {"_id": 0}) if asset_id else None
    if asset:
        add(f"asset:{asset_id}", "asset", asset.get("title") or asset_id,
            {"category": asset.get("category"),
             "location": asset.get("location"),
             "target_yield": asset.get("target_yield")})

        # SPV
        spv = await db.lumen_spvs.find_one({"asset_id": asset_id}, {"_id": 0})
        if spv:
            sid = f"spv:{spv['id']}"
            add(sid, "spv", spv.get("name") or "SPV",
                {"registration_number": spv.get("registration_number"),
                 "jurisdiction": spv.get("jurisdiction")})
            edges.append({"from": f"cert:{cert.get('id')}", "to": sid, "rel": "in_spv"})
            edges.append({"from": sid, "to": f"asset:{asset_id}", "rel": "owns"})

            # Fund holding SPV (if any)
            fund = await db.lumen_funds.find_one({"spv_ids": spv["id"]},
                                                  {"_id": 0, "id": 1, "name": 1, "kind": 1})
            if fund:
                fid = f"fund:{fund['id']}"
                add(fid, "fund", fund.get("name"), {"kind": fund.get("kind")})
                edges.append({"from": fid, "to": sid, "rel": "holds"})

        # Operator
        op_id = asset.get("operator_id")
        if op_id:
            op = await db.lumen_operators.find_one({"id": op_id}, {"_id": 0})
            if op:
                oid = f"operator:{op_id}"
                add(oid, "operator", op.get("name") or "Оператор",
                    {"verified": op.get("status") in ("verified", "approved")})
                edges.append({"from": oid, "to": f"asset:{asset_id}", "rel": "manages"})

    return {
        "nodes": nodes, "edges": edges,
        "counts": {"nodes": len(nodes), "edges": len(edges)},
        "root": {"type": "certificate", "id": cert.get("id")},
    }


async def _build_cert_timeline(cert: dict) -> list[dict]:
    """Aggregate certificate lifecycle: issued/voided + payouts + secondary trades + governance."""
    out: list[dict] = []
    cid = cert.get("id")
    inv_id = cert.get("investor_id")
    asset_id = cert.get("asset_id")

    # 1. Certificate events
    async for ev in db.lumen_certificate_events.find({"certificate_id": cid}, {"_id": 0}):
        et = ev.get("event_type")
        out.append({
            "at": _iso(ev.get("created_at")),
            "kind": "certificate",
            "event": et,
            "event_label": EVENT_LABELS_UK.get(et, et),
            "summary": ev.get("note") or EVENT_LABELS_UK.get(et, et),
            "meta": {"actor": ev.get("actor")},
        })

    # 2. Payout records for this investor on this asset
    if inv_id and asset_id:
        async for r in db.lumen_payout_records.find(
                {"investor_id": inv_id, "asset_id": asset_id},
                {"_id": 0}).sort("created_at", -1).limit(200):
            out.append({
                "at": _iso(r.get("paid_at") or r.get("created_at")),
                "kind": "payout",
                "event": r.get("status") or "paid",
                "event_label": "Виплата",
                "summary": f"Виплата · {r.get('plan_label') or r.get('period_label') or ''}".strip(" ·"),
                "amount_uah": r.get("amount"),
                "meta": {"plan_id": r.get("plan_id"), "batch_id": r.get("batch_id")},
            })

    # 3. Secondary trades touching this asset by this investor
    if inv_id and asset_id:
        async for t in db.lumen_secondary_trades.find(
                {"asset_id": asset_id,
                 "$or": [{"seller_id": inv_id}, {"buyer_id": inv_id}]},
                {"_id": 0}).sort("created_at", -1).limit(50):
            role = "продаж" if t.get("seller_id") == inv_id else "купівля"
            out.append({
                "at": _iso(t.get("settled_at") or t.get("created_at")),
                "kind": "secondary_trade",
                "event": t.get("status"),
                "event_label": f"Вторинний ринок · {role}",
                "summary": f"{role.capitalize()} {t.get('units')} од. за {fmt_uah_as_usd(t.get('amount_uah'))}",
                "amount_uah": t.get("amount_uah"),
                "meta": {"trade_id": t.get("id"), "counterparty": (
                    t.get("buyer_id") if t.get("seller_id") == inv_id else t.get("seller_id"))},
            })

    # 4. Governance votes by this investor on this asset/SPV/Fund scope
    if inv_id and asset_id:
        async for v in db.lumen_gov_votes.find(
                {"voter_id": inv_id}, {"_id": 0}).sort("created_at", -1).limit(50):
            prop = await db.lumen_gov_proposals.find_one(
                {"id": v.get("proposal_id")}, {"_id": 0})
            if not prop:
                continue
            if prop.get("scope") == "asset" and prop.get("scope_id") != asset_id:
                continue
            out.append({
                "at": _iso(v.get("created_at")),
                "kind": "governance",
                "event": v.get("choice"),
                "event_label": "Голосування",
                "summary": f"{prop.get('title')} → «{v.get('choice')}»",
                "meta": {"proposal_id": prop.get("id"), "weight": v.get("weight")},
            })

    out.sort(key=lambda r: r.get("at") or "", reverse=True)
    return out


# ════════════════════════════════════════════════════════════════════════════
# Investor endpoints
# ════════════════════════════════════════════════════════════════════════════

@router.get("/investor/trust-graph")
async def my_trust_graph(user=Depends(get_current_user)):
    inv_id = _uid(user)
    merged_nodes: dict[str, dict] = {}
    merged_edges: list[dict] = []
    cert_count = 0
    async for c in db.lumen_certificates.find(
            {"investor_id": inv_id, "status": {"$ne": "voided"}}, {"_id": 0}):
        cert_count += 1
        g = await _cert_trust_graph(c)
        for n in g["nodes"]:
            merged_nodes[n["id"]] = n
        merged_edges.extend(g["edges"])
    # dedupe edges
    seen_e = set()
    deduped = []
    for e in merged_edges:
        k = (e["from"], e["to"], e.get("rel"))
        if k in seen_e:
            continue
        seen_e.add(k)
        deduped.append(e)
    return {
        "nodes": list(merged_nodes.values()),
        "edges": deduped,
        "counts": {"nodes": len(merged_nodes), "edges": len(deduped),
                   "certificates": cert_count},
    }


@router.get("/investor/certificates/{cert_id}/trust-graph")
async def cert_trust_graph(cert_id: str, user=Depends(get_current_user)):
    cert = await db.lumen_certificates.find_one({"id": cert_id}, {"_id": 0})
    if not cert:
        raise HTTPException(status_code=404, detail="Сертифікат не знайдено")
    if cert.get("investor_id") != _uid(user) and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Доступ заборонено")
    return await _cert_trust_graph(cert)


@router.get("/investor/certificates/{cert_id}/timeline")
async def cert_timeline(cert_id: str, user=Depends(get_current_user)):
    cert = await db.lumen_certificates.find_one({"id": cert_id}, {"_id": 0})
    if not cert:
        raise HTTPException(status_code=404, detail="Сертифікат не знайдено")
    if cert.get("investor_id") != _uid(user) and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Доступ заборонено")
    items = await _build_cert_timeline(cert)
    return {
        "certificate": {
            "id": cert.get("id"),
            "number": cert.get("certificate_number"),
            "status": cert.get("status"),
            "asset_id": cert.get("asset_id"),
            "asset_title": cert.get("asset_title"),
        },
        "items": items,
        "counts": {"total": len(items)},
    }


@router.get("/investor/timeline")
async def investor_timeline(user=Depends(get_current_user)):
    inv_id = _uid(user)
    out: list[dict] = []

    # 1. Audit rows referencing this investor as target
    async for a in db.lumen_audit_log.find(
            {"$or": [{"target_id": inv_id}, {"actor_id": inv_id}]},
            {"_id": 0}).sort("at", -1).limit(200):
        out.append({
            "at": _iso(a.get("at")),
            "kind": a.get("category") or "system",
            "event": a.get("action"),
            "event_label": (a.get("summary") or a.get("action") or "")[:80],
            "summary": a.get("summary"),
            "meta": {"actor_role": a.get("actor_role"),
                      "target_type": a.get("target_type")},
        })

    # 2. Certificate issuance events
    async for c in db.lumen_certificates.find(
            {"investor_id": inv_id}, {"_id": 0}).sort("issue_date", -1):
        out.append({
            "at": _iso(c.get("issue_date")),
            "kind": "certificate",
            "event": c.get("status"),
            "event_label": "Сертифікат · " + (EVENT_LABELS_UK.get(c.get("status"))
                                              or c.get("status") or ""),
            "summary": f"{c.get('certificate_number')} · {c.get('asset_title')}",
            "meta": {"asset_id": c.get("asset_id"),
                      "value_uah": c.get("value_uah")},
        })

    # 3. Investments
    async for i in db.lumen_investments.find(
            {"investor_id": inv_id}, {"_id": 0}).sort("invested_at", -1).limit(50):
        out.append({
            "at": _iso(i.get("invested_at") or i.get("created_at")),
            "kind": "investment",
            "event": i.get("status"),
            "event_label": "Інвестиція",
            "summary": f"Інвестовано {fmt_uah_as_usd(i.get('amount_uah'))} у {i.get('asset_title')}",
            "amount_uah": i.get("amount_uah"),
            "meta": {"asset_id": i.get("asset_id")},
        })

    out.sort(key=lambda r: r.get("at") or "", reverse=True)
    return {"items": out, "counts": {"total": len(out)}}


# ════════════════════════════════════════════════════════════════════════════
# Admin explorer — universal lookup by any id
# ════════════════════════════════════════════════════════════════════════════

EXPLORER_TARGETS = (
    ("lumen_certificates", "certificate", "certificate_number"),
    ("lumen_assets", "asset", "title"),
    ("lumen_spvs", "spv", "name"),
    ("lumen_funds", "fund", "name"),
    ("lumen_operators", "operator", "name"),
    ("lumen_investor_profiles", "investor_profile", "full_name"),
    ("lumen_investments", "investment", None),
    ("users", "user", "email"),
)


@router.get("/admin/audit/explorer")
async def admin_audit_explorer(
    q: str = Query(..., min_length=2),
    _=Depends(require_admin),
):
    q = q.strip()
    matches: list[dict] = []

    # Direct id-based lookups across all entity collections
    for coll, etype, label_field in EXPLORER_TARGETS:
        # try id, user_id, certificate_number, email lookups
        cur = db[coll].find({
            "$or": [
                {"id": q},
                {"user_id": q},
                {"certificate_number": q},
                {"verify_code": q},
                {"email": q},
            ]
        }, {"_id": 0}).limit(5)
        async for row in cur:
            label = (row.get(label_field) if label_field else None) or row.get("id")
            matches.append({
                "entity_type": etype,
                "collection": coll,
                "id": row.get("id") or row.get("user_id") or row.get("certificate_number"),
                "label": label,
                "summary": _summary_for(etype, row),
            })

    # If we hit a certificate, also include its timeline + graph
    extra: dict[str, Any] = {}
    for m in matches:
        if m["entity_type"] == "certificate":
            cert = await db.lumen_certificates.find_one({"id": m["id"]}, {"_id": 0})
            if cert:
                extra["certificate_timeline"] = await _build_cert_timeline(cert)
                extra["certificate_graph"] = await _cert_trust_graph(cert)
            break

    # Recent audit rows referencing this id
    audit_rows: list[dict] = []
    async for a in db.lumen_audit_log.find(
            {"$or": [{"target_id": q}, {"actor_id": q}]},
            {"_id": 0}).sort("at", -1).limit(50):
        audit_rows.append({
            "id": a.get("id"), "at": _iso(a.get("at")),
            "category": a.get("category"), "action": a.get("action"),
            "summary": a.get("summary"), "actor_id": a.get("actor_id"),
            "actor_email": a.get("actor_email"),
            "target_type": a.get("target_type"), "target_id": a.get("target_id"),
        })

    return {
        "query": q,
        "matches": matches,
        "counts": {"matches": len(matches), "audit": len(audit_rows)},
        "audit": audit_rows,
        **extra,
    }


def _summary_for(etype: str, row: dict) -> str:
    if etype == "certificate":
        return f"{row.get('certificate_number')} · {row.get('asset_title')} · {row.get('status')}"
    if etype == "asset":
        return f"{row.get('title')} · {row.get('category')} · {row.get('status')}"
    if etype == "investor_profile":
        return f"{row.get('full_name')} · {row.get('segment')} · KYC {row.get('kyc_status')}"
    if etype == "investment":
        return f"{row.get('asset_title')} · {fmt_uah_as_usd(row.get('amount_uah'))} · {row.get('status')}"
    if etype == "user":
        return f"{row.get('email')} · {row.get('role')}"
    return row.get("name") or row.get("title") or row.get("id") or ""


__all__ = ["router"]
