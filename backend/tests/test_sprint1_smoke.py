"""
Sprint 1 / Phase 0 smoke test — LUMEN core collections.

Level 3 verification: create + read for every LUMEN core collection through
the repository layer (lumen_repositories) using the Pydantic models
(lumen_models). Cleans up after itself. No business logic touched.

Run:  cd /app/backend && python tests/test_sprint1_smoke.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from motor.motor_asyncio import AsyncIOMotorClient

from lumen_models import (
    LumenAsset,
    LumenInvestmentRound,
    LumenInvestorIntent,
    LumenInvestment,
    LumenOwnership,
    LumenInvestorProfile,
)
from lumen_repositories import (
    ensure_lumen_indexes,
    assets_repo,
    rounds_repo,
    intents_repo,
    investments_repo,
    ownerships_repo,
    profiles_repo,
)

TEST_TAG = "smoke-sprint1"


async def main() -> int:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    failures = []
    created = []  # (repo, id) for cleanup

    def check(name, ok, extra=""):
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name} {extra}")
        if not ok:
            failures.append(name)

    print("== Level 3: LUMEN collections create + read ==")

    # 0) Indexes are idempotent (Sprint 3 added lumen_kyc_documents,
    #    Sprint 4 added contracts/templates/signatures,
    #    Sprint 5 added updates/reports/documents/questions/spvs → 15)
    idx = await ensure_lumen_indexes(db)
    check("ensure_lumen_indexes (idempotent)", len(idx) == 20, f"-> {len(idx)} collections")

    # 1) Asset
    asset = LumenAsset(title=f"[{TEST_TAG}] Test Asset", category="real_estate",
                       target_yield=12.5, total_pool=1_000_000, min_ticket=50_000)
    r = assets_repo(db)
    await r.insert(asset.model_dump(mode="json"))
    created.append((r, asset.id))
    got = await r.get(asset.id)
    check("lumen_assets create+read", bool(got) and got["title"] == asset.title)

    # 2) Investment round
    rnd = LumenInvestmentRound(asset_id=asset.id, round_number=999,
                               round_name="Smoke Round",
                               target_amount=500_000, minimum_ticket=50_000)
    r = rounds_repo(db)
    await r.insert(rnd.model_dump(mode="json"))
    created.append((r, rnd.id))
    got = await r.get(rnd.id)
    check("lumen_investment_rounds create+read", bool(got) and got["asset_id"] == asset.id)

    # 3) Investor intent
    intent = LumenInvestorIntent(asset_id=asset.id, round_id=rnd.id,
                                 investor_id=f"user_{TEST_TAG}", amount=75_000)
    r = intents_repo(db)
    await r.insert(intent.model_dump(mode="json"))
    created.append((r, intent.id))
    got = await r.get(intent.id)
    check("lumen_investor_intents create+read", bool(got) and got["status"] == "submitted")

    # 4) Investment
    inv = LumenInvestment(asset_id=asset.id, round_id=rnd.id,
                          investor_id=f"user_{TEST_TAG}", intent_id=intent.id,
                          amount=75_000, units=75.0, ownership_percent=7.5)
    r = investments_repo(db)
    await r.insert(inv.model_dump(mode="json"))
    created.append((r, inv.id))
    got = await r.get(inv.id)
    check("lumen_investments create+read", bool(got) and got["status"] == "pending_payment")

    # 5) Ownership
    own = LumenOwnership(investor_id=f"user_{TEST_TAG}", asset_id=asset.id,
                         investment_id=inv.id, units=75.0, ownership_percent=7.5)
    r = ownerships_repo(db)
    await r.insert(own.model_dump(mode="json"))
    created.append((r, own.id))
    got = await r.get(own.id)
    check("lumen_ownerships create+read", bool(got) and got["units"] == 75.0)

    # 5b) Unique index (investor_id, asset_id) must reject a duplicate
    dup = LumenOwnership(investor_id=f"user_{TEST_TAG}", asset_id=asset.id, units=1.0)
    try:
        await ownerships_repo(db).insert(dup.model_dump(mode="json"))
        created.append((ownerships_repo(db), dup.id))
        check("lumen_ownerships unique (investor,asset) index", False, "-> duplicate accepted!")
    except Exception:
        check("lumen_ownerships unique (investor,asset) index", True, "-> duplicate rejected")

    # 6) Investor profile
    prof = LumenInvestorProfile(user_id=f"user_{TEST_TAG}",
                                residency_country="UA", risk_profile="balanced")
    r = profiles_repo(db)
    await r.insert(prof.model_dump(mode="json"))
    created.append((r, prof.id))
    got = await r.get(prof.id)
    check("lumen_investor_profiles create+read",
          bool(got) and got["kyc_status"] == "not_started")

    # 7) update + find primitives
    ok = await assets_repo(db).update(asset.id, {"status": "open"})
    got = await assets_repo(db).get(asset.id)
    check("repository update", ok and got["status"] == "open")
    found = await intents_repo(db).find({"investor_id": f"user_{TEST_TAG}"})
    check("repository find", len(found) == 1)

    # Cleanup
    for repo, doc_id in created:
        try:
            await repo.delete(doc_id)
        except Exception:
            pass
    leftovers = await intents_repo(db).count({"investor_id": f"user_{TEST_TAG}"})
    check("cleanup", leftovers == 0)

    print()
    if failures:
        print(f"RESULT: FAIL ({len(failures)} failed): {failures}")
        return 1
    print("RESULT: ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
