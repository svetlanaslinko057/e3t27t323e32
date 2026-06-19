"""One-shot: enrich seeded portfolio cases with deep-case fields.

Adds the upsell-layer fields (case_study, challenge, solution, hours_spent,
team_size, start/end dates, tags, starting_from, cta_headline, gallery URLs)
to the 5 demo cases produced by the startup seed, so the detail page +
inquiry modal have realistic content to render.

Idempotent: skips cases that already have a non-empty `case_study`.

Usage:
    cd /app/backend && python -m scripts.backfill_portfolio_deep_fields
"""

import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

# Stable mapping by case title (we don't know the random case_id ahead of time).
DEEP_BY_TITLE = {
    "E-Commerce Marketplace Platform": {
        "case_study": (
            "TechRetail Inc. needed to consolidate three legacy storefronts into a single, "
            "real-time marketplace. We rebuilt the catalogue, payments and analytics on a unified "
            "schema, migrated 1.2M SKUs without downtime, and shipped in 14 weeks with a team of 5. "
            "Result: conversion went from 1.9% to 5.8% in the first quarter."
        ),
        "challenge": "Three siloed storefronts, no shared inventory, 11s average checkout time.",
        "solution": "Unified Postgres + event sourcing layer, Stripe Connect for multi-vendor payouts, "
                    "Redis-backed inventory cache, Next.js SSR for the storefront.",
        "hours_spent": 1840,
        "team_size": 5,
        "start_date": "2025-01-14",
        "end_date": "2025-04-22",
        "tags": ["E-commerce", "Payments", "Multi-vendor", "Stripe", "Real-time"],
        "starting_from": 18500.0,
        "cta_headline": "Need a marketplace at this scale?",
        "gallery": [
            "https://images.unsplash.com/photo-1556742111-a301076d9d18?w=1200",
            "https://images.unsplash.com/photo-1607082348824-0a96f2a4b9da?w=1200",
        ],
        "budget": 22000.0,
        "duration_weeks": 14,
    },
    "Healthcare Management System": {
        "case_study": (
            "MedCare Solutions runs 12 outpatient clinics across two regions. Their old scheduling "
            "system was a spreadsheet patchwork that locked staff out during peak hours. "
            "We delivered a HIPAA-compliant patient management platform with telemedicine, audit "
            "logging, and a 99.9%-uptime SLA over the first 90 days post-launch."
        ),
        "challenge": "Manual scheduling, no audit trail, no telemedicine — patient no-shows at 18%.",
        "solution": "Vue 3 + Python FastAPI, WebRTC for video consults, encrypted PHI at rest, "
                    "RBAC + immutable audit log, GCP HIPAA-ready stack.",
        "hours_spent": 2240,
        "team_size": 6,
        "start_date": "2024-09-02",
        "end_date": "2025-01-30",
        "tags": ["Healthcare", "HIPAA", "Telemedicine", "WebRTC", "Compliance"],
        "starting_from": 28000.0,
        "cta_headline": "Building a HIPAA-grade product?",
        "gallery": [
            "https://images.unsplash.com/photo-1505751172876-fa1923c5c528?w=1200",
            "https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=1200",
        ],
        "budget": 34000.0,
        "duration_weeks": 21,
    },
    "Fintech Trading Dashboard": {
        "case_study": (
            "Alpha Investments runs algorithmic trading desks across three time zones. "
            "Their internal dashboard hit a wall at 1,200 concurrent users. We rebuilt the data "
            "pipeline on TimescaleDB + WebSocket fan-out, lifted concurrency to 10,000+ with "
            "sub-100ms tick latency, and moved the whole stack to Kubernetes for live scaling."
        ),
        "challenge": "Dashboard freezing at 1.2K users, 4-second tick latency, no live order book.",
        "solution": "TimescaleDB hypertables, Go ingest service, React + WebSocket fan-out, "
                    "Kubernetes HPA on the WS gateway.",
        "hours_spent": 2680,
        "team_size": 5,
        "start_date": "2024-11-04",
        "end_date": "2025-03-18",
        "tags": ["Fintech", "Real-time", "WebSocket", "TimescaleDB", "Kubernetes"],
        "starting_from": 32000.0,
        "cta_headline": "Need real-time at scale?",
        "gallery": [
            "https://images.unsplash.com/photo-1642790551116-18e150f248e3?w=1200",
            "https://images.unsplash.com/photo-1554260570-9140fd3b7614?w=1200",
        ],
        "budget": 41000.0,
        "duration_weeks": 20,
    },
    "AI-Powered Content Platform": {
        "case_study": (
            "MediaFlow's recommendation engine was rule-based and lost users after their second "
            "session. We integrated an embedding-based ranking layer (OpenAI + pgvector), built a "
            "content studio with AI drafting, and rolled out personalized feeds A/B-tested against "
            "the legacy engine. Engagement doubled; average session went from 4m11s to 6m04s."
        ),
        "challenge": "Stale recommendations, no AI-assisted authoring, churn at 38% in week 2.",
        "solution": "Next.js + Python service, pgvector for embeddings, OpenAI for drafting, "
                    "feature-flagged A/B testing, Redis for hot-feed cache.",
        "hours_spent": 1560,
        "team_size": 4,
        "start_date": "2025-02-10",
        "end_date": "2025-05-12",
        "tags": ["AI", "OpenAI", "Recommendations", "Content", "A/B testing"],
        "starting_from": 14500.0,
        "cta_headline": "Want AI inside your product?",
        "gallery": [
            "https://images.unsplash.com/photo-1620712943543-bcc4688e7485?w=1200",
            "https://images.unsplash.com/photo-1655720828018-edd2daec9349?w=1200",
        ],
        "budget": 19000.0,
        "duration_weeks": 13,
    },
    "Logistics Tracking System": {
        "case_study": (
            "GlobalShip moves 100K+ shipments per month across four continents. Visibility was "
            "fragmented across carriers, with status updates lagging 6–24 hours behind reality. "
            "We built an IoT + carrier-API fusion layer, surfaced live tracking on a dashboard, "
            "and connected the back-end to their ERP. Delays dropped 60% in the first 90 days."
        ),
        "challenge": "Fragmented carrier data, 6–24h status lag, no live ETA per shipment.",
        "solution": "IoT Hub + carrier-API fusion, event-driven ingestion, React map dashboard, "
                    "Postgres + Materialised views for live ETAs, Azure deployment.",
        "hours_spent": 2080,
        "team_size": 5,
        "start_date": "2024-10-07",
        "end_date": "2025-02-21",
        "tags": ["Logistics", "IoT", "Real-time", "Supply chain", "Azure"],
        "starting_from": 24500.0,
        "cta_headline": "Building a supply-chain platform?",
        "gallery": [
            "https://images.unsplash.com/photo-1494412651409-8963ce7935a7?w=1200",
            "https://images.unsplash.com/photo-1601158935942-52255782d322?w=1200",
        ],
        "budget": 30000.0,
        "duration_weeks": 20,
    },
}


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    coll = db.portfolio_cases

    total = await coll.count_documents({})
    print(f"Total portfolio cases: {total}")

    updated = 0
    skipped = 0
    for title, fields in DEEP_BY_TITLE.items():
        doc = await coll.find_one({"title": title}, {"_id": 0, "case_id": 1, "case_study": 1})
        if not doc:
            print(f"  - SKIP (missing): {title}")
            continue
        if doc.get("case_study"):
            print(f"  - SKIP (already enriched): {title}")
            skipped += 1
            continue
        # Enrich
        fields_with_defaults = {
            **fields,
            "show_budget": True,            # Show price by default since starting_from is set
            "show_description": True,
            "status": "delivered",
            "published": True,
            "external_url": fields.get("external_url"),
        }
        r = await coll.update_one(
            {"case_id": doc["case_id"]},
            {"$set": fields_with_defaults},
        )
        if r.modified_count:
            print(f"  + ENRICHED: {title}")
            updated += 1

    print(f"\nDone. Enriched: {updated}, already-rich: {skipped}, missing: {len(DEEP_BY_TITLE) - updated - skipped}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
