#!/usr/bin/env python3
"""
currency_display_contract.py — PUBLIC CURRENCY RULE enforcement harness.

Scans the frontend + backend for forbidden user-facing currency tokens
(`₴`, `грн`, `гривн`, and the visible label `UAH`). The platform is a
USD/USDT product — none of these may appear in anything a user can see.

Internal usage is allowed ONLY via an explicit allowlist:
  * Python identifiers / dict keys ending in `_uah` (internal schema fields).
  * FX tables / rate maps that must reference UAH as a base currency.
  * Comments and docstrings that DOCUMENT the rule.
  * Test / audit / contract harness files.

Output:
  * JSON  → /app/test_reports/currency_display_contract.json
  * Verdict PASS only when there are 0 forbidden hits outside the allowlist.

Exit: 0 = PASS, 2 = FAIL.
"""
from __future__ import annotations
import json
import os
import re
from datetime import datetime, timezone

ROOT = "/app"
REPORT = "/app/test_reports/currency_display_contract.json"

# Forbidden tokens that must never reach a user.
FORBIDDEN = re.compile(r"₴|грн|гривн|\bUAH\b", re.IGNORECASE)

# Directories scanned.
FRONTEND_DIR = os.path.join(ROOT, "frontend", "src")
BACKEND_DIR = os.path.join(ROOT, "backend")

# File extensions to scan.
FE_EXT = (".js", ".jsx", ".ts", ".tsx")
BE_EXT = (".py",)

# Path fragments that are EXEMPT entirely (internal tooling, tests, harnesses).
EXEMPT_PATH = re.compile(
    r"(node_modules|__pycache__|/tests?/|test_|_test|_audit\.py|_contract\.py|"
    r"comm_regression|backend_test|/scripts/|lumen_fx\.py|shared/money\.py|"
    r"currency_display_contract|\.test\.|lumenApi\.js)"
)


def _line_is_allowed(line: str, in_doc: bool = False) -> bool:
    """Return True if a forbidden hit on this line is an allowed internal use.

    ₴ and грн/гривн are ALWAYS user-facing → forbidden unless the line is a pure
    comment. Only the bare currency code 'UAH' may be internal (config / FX /
    docstrings / identifiers / code collections).
    """
    stripped = line.strip()
    is_comment = (
        stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("*")
    )
    has_symbol = ("₴" in line) or bool(re.search(r"грн|гривн", line, re.IGNORECASE))
    if has_symbol:
        # ₴ / грн are display tokens — only acceptable inside a pure comment line.
        return is_comment
    # From here, only the code token 'UAH' is present.
    if is_comment or in_doc:
        return True  # documentation / docstring body
    if stripped.startswith('"""') or stripped.startswith("'''"):
        return True
    # Currency-code collections (tuples/lists/maps/dropdowns of ISO codes) → internal config.
    # Only when UAH appears as an isolated code literal/member, never inside prose.
    if re.search(r"USD|EUR|USDT|USDC", line):
        if re.search(r"['\"]UAH['\"]", line) or re.search(r">\s*UAH\s*<", line) or \
           re.search(r"[\(\[\{][^)\]}]*\bUAH\b[^)\]}]*[\)\]\}]", line):
            return True
    config_ctx = re.compile(
        r"currency|currencies|\bccy\b|BASE_CURRENCY|SUPPORTED|FALLBACK|DEFAULT_FX|"
        r"\brate(s)?\b|per_usd|per_uah|supports|ISO|980|840|978",
        re.IGNORECASE,
    )
    if config_ctx.search(line):
        return True  # internal currency config / FX context
    for m in re.finditer(r"UAH", line, re.IGNORECASE):
        start = m.start()
        prev = line[start - 1] if start > 0 else ""
        if prev == "_" or prev == "-" or prev.isalnum():
            continue  # identifier-attached (e.g. nav_uah, pending-uah testid)
        nxt = line[m.end()] if m.end() < len(line) else ""
        if nxt.isalnum() or nxt == "_" or nxt == "-":
            continue
        return False  # standalone visible 'UAH' in prose/label/amount → forbidden
    return True


def _strip_inline_comment(line: str, is_py: bool) -> str:
    """Return the code portion before an inline comment (best-effort)."""
    marker = "#" if is_py else "//"
    idx = line.find(marker)
    if idx == -1:
        return line
    # crude: ignore markers inside quotes by checking quote balance before idx
    head = line[:idx]
    if head.count('"') % 2 == 0 and head.count("'") % 2 == 0:
        return head
    return line


def scan_dir(base: str, exts: tuple) -> list:
    hits = []
    for dirpath, _dirs, files in os.walk(base):
        for fn in files:
            if not fn.endswith(exts):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, ROOT)
            if EXEMPT_PATH.search("/" + rel):
                continue
            is_py = fn.endswith(".py")
            in_doc = False  # inside triple-quoted docstring/block
            try:
                with open(full, "r", encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        # Track triple-quote docstring state (py + jsx block comments handled loosely).
                        tq = line.count('"""') + line.count("'''")
                        was_in_doc = in_doc
                        if tq % 2 == 1:
                            in_doc = not in_doc
                        # Strip inline comments before checking.
                        code = _strip_inline_comment(line, is_py)
                        if FORBIDDEN.search(code) and not _line_is_allowed(code, in_doc=was_in_doc):
                            hits.append({"file": rel, "line": i, "text": line.strip()[:200]})
            except Exception as e:  # noqa
                hits.append({"file": rel, "line": 0, "text": f"<read error: {e}>"})
    return hits


def main() -> int:
    fe_hits = scan_dir(FRONTEND_DIR, FE_EXT)
    be_hits = scan_dir(BACKEND_DIR, BE_EXT)
    total = len(fe_hits) + len(be_hits)
    verdict = "PASS" if total == 0 else "FAIL"

    report = {
        "harness": "currency_display_contract",
        "at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "counts": {"frontend": len(fe_hits), "backend": len(be_hits), "total": total},
        "frontend_hits": fe_hits[:200],
        "backend_hits": be_hits[:200],
    }
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("=" * 70)
    print("CURRENCY DISPLAY CONTRACT — PUBLIC CURRENCY RULE")
    print("=" * 70)
    print(f"  frontend forbidden hits : {len(fe_hits)}")
    print(f"  backend  forbidden hits : {len(be_hits)}")
    print(f"  VERDICT                 : {verdict}")
    if total:
        print("-" * 70)
        for h in (fe_hits + be_hits)[:60]:
            print(f"  {h['file']}:{h['line']}  {h['text']}")
    print("=" * 70)
    return 0 if verdict == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
