"""One-off bootstrap: run the legacy `startup_event` seeder (skipped under LUMEN_ONLY)
to create demo users (admin@atlas.dev, client@atlas.dev, tester@atlas.dev, devs...)
in a fresh database. Idempotent — safe to re-run.
"""
import asyncio
import os
import sys

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

# Temporarily disable LUMEN_ONLY for the import so nothing is auto-skipped;
# we only invoke the specific seed function manually (no background loops).
os.environ["LUMEN_ONLY"] = "false"

import server  # noqa: E402


async def main():
    await server.startup_event()
    users = await server.db.users.count_documents({})
    emails = await server.db.users.distinct("email")
    print(f"USERS SEEDED: {users}")
    for e in sorted(emails):
        print(" -", e)

asyncio.run(main())
