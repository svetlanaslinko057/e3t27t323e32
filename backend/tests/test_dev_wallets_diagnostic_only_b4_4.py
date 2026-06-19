"""Phase 2C-B4.4 acceptance — static guard:
`dev_wallets` collection must have ZERO active writers in production code
outside the explicitly-allowed orphan-canary fixture in `mock_seed.py`.

This is the formal proof that the withdrawal + earnings lifecycle no
longer touches `dev_wallets` as a writer surface. After this guard
passes, `dev_wallets` is contractually demoted to
diagnostic-mirror-only — read-only for user-facing surfaces (already
the case via `dev_wallet_reader` + `projection`), and the only producer
is the deliberately-seeded mock_seed_orphan_canary_v1 row.

The guard is AST-based (not regex-based) so comments and docstrings
that *reference* the historical `dev_wallets.update_one` calls do not
trigger false positives. Only real `.update_one`/`.insert_*`/`.delete_*`
/`.replace_one`/`.find_one_and_*`/`.bulk_write`/`.drop` method calls on
any expression whose attribute chain ends in `dev_wallets` count as
writers.
"""
import ast
import os
import sys
from pathlib import Path

sys.path.insert(0, "/app/backend")

BACKEND = Path("/app/backend")

WRITER_METHODS = {
    "update_one",
    "update_many",
    "insert_one",
    "insert_many",
    "delete_one",
    "delete_many",
    "replace_one",
    "find_one_and_update",
    "find_one_and_replace",
    "find_one_and_delete",
    "bulk_write",
    "drop",
    "rename",
}


def _resolves_to_dev_wallets(node: ast.AST) -> bool:
    """True if `node` is an attribute access that ends in `.dev_wallets`.

    Matches both `db.dev_wallets` and `self.db.dev_wallets` etc.
    """
    if not isinstance(node, ast.Attribute):
        return False
    return node.attr == "dev_wallets"


def _iter_dev_wallets_writes(tree: ast.AST):
    """Yield (lineno, method) for every dev_wallets writer call in tree."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        method = func.attr
        if method not in WRITER_METHODS:
            continue
        # The expression .{method}(...) is on something — is that something
        # a .dev_wallets attribute access?
        if _resolves_to_dev_wallets(func.value):
            yield node.lineno, method


def _scan_file(path: Path):
    src = path.read_text()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    return list(_iter_dev_wallets_writes(tree))


# Files we deliberately allow to write to `dev_wallets`:
# • mock_seed.py — the orphan canary fixture, explicitly preserved as
#   a divergence-engine visibility canary (see mock_seed.py:253-265
#   inline contract).
ALLOWED_WRITER_FILES = {
    "mock_seed.py",
}

# Tests are allowed to write — they need to construct fixtures and
# simulate legacy states.
EXCLUDE_DIRS = {"__pycache__", "tests", "_archive"}


def _scan_production():
    findings = []
    for py in BACKEND.rglob("*.py"):
        rel = py.relative_to(BACKEND)
        parts = set(rel.parts)
        if parts & EXCLUDE_DIRS:
            continue
        writers = _scan_file(py)
        if not writers:
            continue
        for lineno, method in writers:
            findings.append((str(rel), lineno, method))
    return findings


def test_no_unauthorised_dev_wallets_writers_in_production():
    """The post-B4.4 invariant: outside the orphan canary in mock_seed.py,
    no production code may call any writer method on the `dev_wallets`
    collection."""
    findings = _scan_production()
    # Filter out allowed files.
    unauthorised = [
        (rel, lineno, method)
        for rel, lineno, method in findings
        if Path(rel).name not in ALLOWED_WRITER_FILES
    ]
    assert unauthorised == [], (
        f"B4.4 violated — found {len(unauthorised)} unauthorised "
        f"dev_wallets writer call(s) outside the orphan-canary fixture:\n"
        + "\n".join(f"  {rel}:{lineno}  .{m}(...)" for rel, lineno, m in unauthorised)
    )


def test_orphan_canary_writer_still_present_in_mock_seed():
    """The orphan canary is *load-bearing* for the divergence engine's
    self-test. If someone deletes it, the stability probe loses its
    ability to detect a legacy-only writer and a key invariant goes
    silent. Guard against that with an explicit assertion."""
    findings = _scan_file(BACKEND / "mock_seed.py")
    assert findings, (
        "mock_seed.py no longer writes to dev_wallets — the orphan "
        "canary fixture has been removed. This silently disables the "
        "divergence engine's visibility self-test. If this removal "
        "was deliberate, do it as a separate phase with its own "
        "acceptance contract (see mock_seed.py:262-265 inline notice)."
    )
    # Specifically: the upsert at mock_seed.py:266 (line drift tolerated).
    methods = {m for _, m in findings}
    assert methods == {"update_one"}, (
        f"mock_seed.py canary changed shape — expected only update_one "
        f"upsert, got {methods}. If the canary was reshaped, update "
        f"this guard and the audit doc."
    )


def test_dev_wallets_readers_still_exist():
    """Sanity check: `dev_wallets` is still *read* by the diagnostic
    surfaces (divergence engine, projection compare, wallet reader).
    A B4.4 implementation that accidentally rips out the reader paths
    would silently break the divergence engine."""
    reader_files = {
        "dev_wallet_reader.py",
        "money_divergence.py",
        "money_projections.py",
    }
    for fname in reader_files:
        src = (BACKEND / fname).read_text()
        assert "dev_wallets" in src, (
            f"{fname} no longer references dev_wallets at all — the "
            f"diagnostic compare surface is broken. B4.4 contract: "
            f"dev_wallets stays as a diagnostic mirror, only writers "
            f"are removed."
        )


if __name__ == "__main__":
    # Allow running standalone for quick eyeballing.
    findings = _scan_production()
    print(f"All dev_wallets writer call sites in production: {len(findings)}")
    for rel, lineno, method in findings:
        marker = "  (ALLOWED canary)" if Path(rel).name in ALLOWED_WRITER_FILES else "  ❌ UNAUTHORISED"
        print(f"  {rel}:{lineno}  .{method}(...){marker}")
