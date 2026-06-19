"""One-shot: add video_url + multi-testimonials to seeded portfolio cases.

Adds:
  - `video_url` — a public sample (Big Buck Bunny mp4) so the player has
    something to render in demo.
  - `testimonials` — list of 1–2 review objects {name, role, company, quote,
    avatar_url, rating}. Replaces the legacy single-string `testimonial`
    where it existed.

Idempotent: skips cases that already have a non-empty `testimonials` array.

Usage:
    cd /app/backend && python -m scripts.backfill_portfolio_media
"""

import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

# Stable W3 / archive.org demo mp4 — small file, embeds cleanly on the web.
SAMPLE_VIDEO = "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"

MEDIA_BY_TITLE = {
    "E-Commerce Marketplace Platform": {
        "video_url": SAMPLE_VIDEO,
        "testimonials": [
            {
                "name": "Sarah Mitchell",
                "role": "VP Engineering",
                "company": "TechRetail Inc.",
                "quote": "We rebuilt three legacy storefronts into one in 14 weeks. Conversion went from 1.9% to 5.8%. The team treated our codebase like their own.",
                "avatar_url": "https://i.pravatar.cc/96?img=47",
                "rating": 5,
            },
            {
                "name": "Marcus Liu",
                "role": "Head of Product",
                "company": "TechRetail Inc.",
                "quote": "Multi-vendor payouts via Stripe Connect went from a Q3 plan to live in week 6. They surface the right tradeoffs early.",
                "avatar_url": "https://i.pravatar.cc/96?img=68",
                "rating": 5,
            },
        ],
    },
    "Healthcare Management System": {
        "video_url": SAMPLE_VIDEO,
        "testimonials": [
            {
                "name": "Dr. Anna Rodriguez",
                "role": "Chief Medical Officer",
                "company": "MedCare Solutions",
                "quote": "HIPAA-grade telemedicine across 12 clinics in 21 weeks. The audit log and PHI encryption passed our compliance review on the first pass.",
                "avatar_url": "https://i.pravatar.cc/96?img=44",
                "rating": 5,
            }
        ],
    },
    "Fintech Trading Dashboard": {
        "video_url": SAMPLE_VIDEO,
        "testimonials": [
            {
                "name": "James Park",
                "role": "Head of Trading",
                "company": "Alpha Investments",
                "quote": "From 1.2K concurrent users with 4-second lag to 10K+ at sub-100ms. The TimescaleDB + WebSocket fan-out architecture was exactly what we needed.",
                "avatar_url": "https://i.pravatar.cc/96?img=12",
                "rating": 5,
            }
        ],
    },
    "AI-Powered Content Platform": {
        "video_url": SAMPLE_VIDEO,
        "testimonials": [
            {
                "name": "Elena Volkov",
                "role": "VP Growth",
                "company": "MediaFlow",
                "quote": "Session time doubled in the first month. The pgvector ranker beat our rule-based engine in every cohort. Clean delivery, clean docs.",
                "avatar_url": "https://i.pravatar.cc/96?img=49",
                "rating": 5,
            }
        ],
    },
    "Logistics Tracking System": {
        "video_url": SAMPLE_VIDEO,
        "testimonials": [
            {
                "name": "Hiroshi Tanaka",
                "role": "VP Supply Chain",
                "company": "GlobalShip",
                "quote": "Live ETAs across 100K+ shipments per month. Delays dropped 60% in the first 90 days. They understood operations, not just code.",
                "avatar_url": "https://i.pravatar.cc/96?img=33",
                "rating": 5,
            },
            {
                "name": "Petra Nielsen",
                "role": "ERP Integration Lead",
                "company": "GlobalShip",
                "quote": "Connecting the IoT layer to our ERP was the part that scared me most going in. It just worked. Documentation was production-grade from day one.",
                "avatar_url": "https://i.pravatar.cc/96?img=26",
                "rating": 5,
            },
        ],
    },
}


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    coll = db.portfolio_cases

    print(f"Total portfolio cases: {await coll.count_documents({})}")
    updated = 0
    skipped = 0
    for title, fields in MEDIA_BY_TITLE.items():
        doc = await coll.find_one({"title": title}, {"_id": 0, "case_id": 1, "testimonials": 1})
        if not doc:
            print(f"  - MISSING: {title}")
            continue
        if doc.get("testimonials"):
            print(f"  - SKIP (already has testimonials): {title}")
            skipped += 1
            continue
        r = await coll.update_one(
            {"case_id": doc["case_id"]},
            {"$set": fields},
        )
        if r.modified_count:
            print(f"  + ENRICHED with media: {title}")
            updated += 1

    print(f"\nDone. Enriched: {updated}, already-rich: {skipped}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
