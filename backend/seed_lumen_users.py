"""One-off idempotent seed of core test users for a fresh LUMEN_ONLY database.

Mirrors the quick-access users from the legacy startup_event (skipped under
LUMEN_ONLY=true). Run: python seed_lumen_users.py
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone

import bcrypt
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


USERS = [
    {"email": "admin@atlas.dev", "password": "admin123", "name": "Atlas Admin",
     "role": "admin", "roles": ["admin"], "level": "senior",
     "skills": ["management", "architecture"], "source": "core"},
    {"email": "admin@devos.io", "password": "admin123", "name": "DevOS Admin",
     "role": "admin", "roles": ["admin"], "level": "senior",
     "skills": ["management"], "source": "core"},
    {"email": "client@atlas.dev", "password": "client123", "name": "Acme Client",
     "role": "client", "roles": ["client"], "level": "junior",
     "skills": [], "source": "external"},
]


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc).isoformat()
    for u in USERS:
        existing = await db.users.find_one({"email": u["email"]})
        doc = {
            "name": u["name"], "role": u["role"], "roles": u["roles"],
            "level": u["level"], "skills": u["skills"], "source": u["source"],
            "password_hash": hash_password(u["password"]),
            "picture": None, "rating": 5.0, "completed_tasks": 0,
            "active_load": 0, "states": [], "active_context": None,
        }
        if existing:
            await db.users.update_one({"email": u["email"]}, {"$set": doc})
            print(f"updated {u['email']}")
        else:
            doc.update({
                "user_id": f"user_{uuid.uuid4().hex[:12]}",
                "email": u["email"], "created_at": now,
            })
            await db.users.insert_one(doc)
            print(f"created {u['email']}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
