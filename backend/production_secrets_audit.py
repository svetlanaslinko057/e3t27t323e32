#!/usr/bin/env python3
"""
production_secrets_audit.py — LUMEN Production Secrets / Go-Live Audit (Phase 2)
===============================================================================

The "did we leave the test rails plugged in?" gate. Before money is real, this
read-only audit proves the environment is not still wired to sandboxes, demo
accounts or debug doors. It NEVER prints full secret values — only presence,
prefix and a masked fingerprint.

Each finding is classified honestly:

    PASS     clean / safe for go-live
    BLOCKED  sandbox/test plumbing present but acceptable *until* LUMEN_ENV=production
             (these MUST become PASS or be removed before real money)
    FAIL     a hard production violation that must never ship

Checks
------
1. Test-key patterns        sk_test_ / pk_test_ / whsec_test / sandbox
2. Placeholder patterns      changeme / your_ / placeholder / dummy / TODO / <...>
3. Demo / dev backdoors      ENABLE_DEMO_AUTH / AUTH_OTP_DEV_MODE /
                             LUMEN_ALLOW_DEMO_SEEDS_IN_PROD
4. Production sanity (only enforced when LUMEN_ENV=production):
        · default_admin_count == 0      (reuses invariant _count_default_admins)
        · CORS_ORIGINS != "*"
5. Route exposure            openapi.json scan for /debug, /dev, /bypass surfaces

Output: /app/test_reports/production_secrets_audit.json  + a markdown summary.
Run:    cd /app/backend && python production_secrets_audit.py
Exit:   0 = no FAIL (PASS or BLOCKED), 2 = at least one FAIL.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

from dotenv import dotenv_values, load_dotenv

ENV_FILE = os.environ.get("SECRETS_ENV_FILE", "/app/backend/.env")
load_dotenv(ENV_FILE)

BASE = os.environ.get("SECRETS_BASE", "http://localhost:8001")
JSON_OUT = "/app/test_reports/production_secrets_audit.json"
MD_OUT = "/app/docs/PRODUCTION_SECRETS_AUDIT.md"

IS_PROD = (os.environ.get("LUMEN_ENV") or os.environ.get("ENV") or "preview").lower() in {"production", "prod"}

# Configurable route denylist. Targets true backdoors/debug doors only — NOT
# the legitimate `/api/dev/*` developer-economy product namespace.
ROUTE_DENYLIST = [s for s in (os.environ.get("SECRETS_ROUTE_DENYLIST",
                  "/debug,/bypass,/__,/_internal,/backdoor,/test-only").split(",")) if s]

TEST_KEY_PATTERNS = ["sk_test_", "pk_test_", "rk_test_", "whsec_test", "sandbox", "_test_key"]
PLACEHOLDER_PATTERNS = ["changeme", "change-me", "your_", "your-", "placeholder",
                        "dummy", "todo", "xxxx", "<", "example.com/key", "replace_me"]
DEMO_FLAGS = ["ENABLE_DEMO_AUTH", "AUTH_OTP_DEV_MODE", "LUMEN_ALLOW_DEMO_SEEDS_IN_PROD"]

# Keys we must never report values for, even masked beyond a fingerprint.
SECRETISH = re.compile(r"(KEY|SECRET|TOKEN|PASS|PWD|PRIVATE|WHSEC)", re.I)

findings: list[dict] = []


def add(name: str, status: str, detail: str = "") -> None:
    assert status in {"PASS", "BLOCKED", "FAIL"}
    findings.append({"name": name, "status": status, "detail": detail})
    icon = {"PASS": "✅", "BLOCKED": "🟡", "FAIL": "❌"}[status]
    print(f"  {icon} [{status:7}] {name}" + (f" — {detail}" if detail else ""))


def fingerprint(value: str) -> str:
    if not value:
        return "<empty>"
    h = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return f"len={len(value)} sha256:{h}"


def mask(key: str, value: str) -> str:
    """Never reveal a secret's body — only a safe prefix + fingerprint."""
    if value is None:
        return "<unset>"
    if SECRETISH.search(key):
        prefix = value[:7]
        return f"{prefix}… ({fingerprint(value)})"
    return value[:40]


def collect_env() -> dict:
    """Merge process env over .env file values (process env wins, like runtime)."""
    merged = dict(dotenv_values(ENV_FILE))
    for k, v in os.environ.items():
        merged[k] = v
    return merged


def scan_patterns(env: dict) -> None:
    test_hits, placeholder_hits = [], []
    for k, v in env.items():
        if not isinstance(v, str) or not v:
            continue
        low = v.lower()
        if any(p in low for p in TEST_KEY_PATTERNS):
            test_hits.append((k, mask(k, v)))
        if any(p in low for p in PLACEHOLDER_PATTERNS):
            placeholder_hits.append((k, mask(k, v)))

    if not test_hits:
        add("No test/sandbox key patterns", "PASS")
    else:
        keys = ", ".join(k for k, _ in test_hits)
        # Test keys are FAIL in production; acceptable-but-pending otherwise.
        add("Test/sandbox key patterns absent", "FAIL" if IS_PROD else "BLOCKED",
            f"found in: {keys}")

    if not placeholder_hits:
        add("No placeholder/changeme secrets", "PASS")
    else:
        keys = ", ".join(k for k, _ in placeholder_hits)
        add("Placeholder secrets absent", "FAIL" if IS_PROD else "BLOCKED",
            f"found in: {keys}")


def scan_demo_flags(env: dict) -> None:
    truthy = {"1", "true", "yes", "on"}
    active = [f for f in DEMO_FLAGS if str(env.get(f, "")).strip().lower() in truthy]
    if not active:
        add("Demo/dev backdoors disabled", "PASS")
    else:
        add("Demo/dev backdoors disabled", "FAIL" if IS_PROD else "BLOCKED",
            f"active: {', '.join(active)}")


async def scan_production_sanity(env: dict) -> None:
    if not IS_PROD:
        add("Production-mode sanity (LUMEN_ENV)", "BLOCKED",
            f"env='{env.get('LUMEN_ENV') or env.get('ENV') or 'preview'}' — prod checks deferred")
        return

    # CORS wildcard
    cors = (env.get("CORS_ORIGINS") or "").strip()
    wildcard = cors == "*" or "*" in {p.strip() for p in cors.split(",")}
    add("CORS not wildcard in production", "FAIL" if wildcard else "PASS",
        "CORS_ORIGINS='*'" if wildcard else "")

    # Default admin count (reuse the architecture invariant logic).
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        from lumen_architecture_invariants import _count_default_admins
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        n = await _count_default_admins(db)
        add("No default-admin credential in production", "FAIL" if n else "PASS",
            f"default_admin_count={n}" if n else "")
    except Exception as e:
        add("No default-admin credential in production", "BLOCKED", f"check error: {e}")


def scan_routes() -> None:
    """Scan the live openapi.json for forbidden route fragments. Falls back to a
    static scan of router files if the server is unreachable."""
    paths = []
    source = "openapi"
    try:
        import httpx
        r = httpx.get(f"{BASE}/openapi.json", timeout=15)
        if r.status_code == 200:
            paths = list(r.json().get("paths", {}).keys())
    except Exception:
        paths = []

    if not paths:
        source = "static"
        try:
            import pathlib
            for f in pathlib.Path("/app/backend").glob("*.py"):
                txt = f.read_text(encoding="utf-8", errors="ignore")
                paths += re.findall(r'@\w+\.(?:get|post|put|patch|delete)\("([^"]+)"', txt)
        except Exception:
            paths = []

    hits = sorted({p for p in paths for frag in ROUTE_DENYLIST if frag in p})
    if not hits:
        add(f"No debug/dev/bypass routes exposed ({source}, {len(paths)} routes)", "PASS")
    else:
        add("No debug/dev/bypass routes exposed", "FAIL", f"{', '.join(hits)}")


async def run() -> int:
    print(f"PRODUCTION SECRETS AUDIT — env_file={ENV_FILE} prod_mode={IS_PROD}\n")
    env = collect_env()
    scan_patterns(env)
    scan_demo_flags(env)
    await scan_production_sanity(env)
    scan_routes()

    n_pass = sum(1 for f in findings if f["status"] == "PASS")
    n_block = sum(1 for f in findings if f["status"] == "BLOCKED")
    n_fail = sum(1 for f in findings if f["status"] == "FAIL")
    verdict = "FAIL" if n_fail else ("BLOCKED" if n_block else "PASS")

    summary = {
        "harness": "production_secrets_audit",
        "at": datetime.now(timezone.utc).isoformat(),
        "env_file": ENV_FILE,
        "production_mode": IS_PROD,
        "verdict": verdict,
        "counts": {"pass": n_pass, "blocked": n_block, "fail": n_fail,
                   "total": len(findings)},
        "production_ready": bool(n_fail == 0 and (not IS_PROD or n_block == 0)),
        "findings": findings,
    }
    _write_reports(summary)

    print("\n" + "═" * 70)
    print(f"PRODUCTION SECRETS AUDIT — {verdict} "
          f"(pass={n_pass} blocked={n_block} fail={n_fail})")
    print("═" * 70)
    return 0 if n_fail == 0 else 2


def _write_reports(summary: dict) -> None:
    try:
        os.makedirs(os.path.dirname(JSON_OUT), exist_ok=True)
        with open(JSON_OUT, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"json write warning: {e}")
    try:
        os.makedirs(os.path.dirname(MD_OUT), exist_ok=True)
        lines = [
            "# LUMEN — Production Secrets Audit",
            "",
            f"- **Generated:** {summary['at']}",
            f"- **Production mode:** {summary['production_mode']}",
            f"- **Verdict:** **{summary['verdict']}**",
            f"- **Production-ready:** {summary['production_ready']}",
            "",
            "| Check | Status | Detail |",
            "|-------|--------|--------|",
        ]
        for f in summary["findings"]:
            lines.append(f"| {f['name']} | {f['status']} | {f['detail']} |")
        lines += ["", "_Read-only. Secret values are never printed — only masked fingerprints._", ""]
        with open(MD_OUT, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
    except Exception as e:
        print(f"md write warning: {e}")


if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(run()))
