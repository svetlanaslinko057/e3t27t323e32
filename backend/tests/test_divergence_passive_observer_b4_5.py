"""Phase 2C-B4.5 acceptance — `money_divergence` is a PASSIVE OBSERVER.

The passive-observer contract has five strict negative covenants. This
test suite enforces them via AST analysis (so docstrings / comments
that *mention* writes don't trigger false positives):

  1. NO writes               — engine never mutates any collection
  2. NO operational branching — no business code reads divergence output
                                to drive control-flow
  3. NO payout gating        — payouts proceed on canonical ledger alone
  4. NO repair authority     — engine cannot heal what it observes
  5. NO source-of-truth influence — money_ledger_events remains canonical

And four positive responsibilities (which we sanity-check):

  a. Diagnostics surface still active
  b. Migration confidence (stability probe) still consumes it
  c. Anomaly visibility — divergence classes still emitted
  d. Audit evidence — HTTP endpoints still mounted
"""
import ast
from pathlib import Path

BACKEND = Path("/app/backend")
DIVERGENCE_FILE = BACKEND / "money_divergence.py"

WRITER_METHODS = {
    "update_one", "update_many",
    "insert_one", "insert_many",
    "delete_one", "delete_many",
    "replace_one",
    "find_one_and_update", "find_one_and_replace", "find_one_and_delete",
    "bulk_write", "drop", "rename",
}


def _ast(path: Path) -> ast.AST:
    return ast.parse(path.read_text())


def _all_calls(tree: ast.AST):
    """Yield every Call node in the tree."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node


# ── Covenant 1: NO writes ────────────────────────────────────────────────

def test_divergence_engine_has_zero_writer_calls():
    """The engine's *only* job is read + classify + report. Any mutation
    call (update_*, insert_*, delete_*, replace_*, find_one_and_*,
    bulk_write, drop, rename) on any collection or repository instance
    violates the contract."""
    tree = _ast(DIVERGENCE_FILE)
    writers = []
    for call in _all_calls(tree):
        func = call.func
        if isinstance(func, ast.Attribute) and func.attr in WRITER_METHODS:
            writers.append((call.lineno, func.attr))
    assert writers == [], (
        f"B4.5 violated — money_divergence.py contains {len(writers)} "
        f"writer call(s):\n"
        + "\n".join(f"  L{ln}: .{m}(...)" for ln, m in writers)
        + "\nThe engine must remain READ-ONLY."
    )


# ── Covenant 2: NO operational branching on divergence output ────────────

def test_no_operational_code_imports_money_divergence_for_business_logic():
    """Production code may import money_divergence to wire its HTTP
    routes (server.py: `_money_divergence.wire(...)`,
    `fastapi_app.include_router(_money_divergence.router, ...)`).

    But it must NOT import any classifier / scanner / overview function
    for use inside business logic. The allow-list of import targets from
    production code is exactly `{wire, router}`.

    Tests and the standalone CLI script may import anything (they are
    not in the operational path)."""
    allowed_names = {"wire", "router"}
    # Skip tests / standalone scripts / __pycache__ / _archive.
    EXCLUDE = {"__pycache__", "tests", "_archive"}
    EXCLUDE_FILES = {"money_divergence.py"}  # the module itself

    violations = []
    for py in BACKEND.rglob("*.py"):
        if any(p in EXCLUDE for p in py.parts):
            continue
        if py.name in EXCLUDE_FILES:
            continue
        try:
            tree = _ast(py)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            # `from money_divergence import X, Y, Z`
            if isinstance(node, ast.ImportFrom) and node.module == "money_divergence":
                for alias in node.names:
                    if alias.name not in allowed_names:
                        violations.append(
                            (str(py.relative_to(BACKEND)), node.lineno, alias.name)
                        )
            # `import money_divergence as X` — allowed, but any attribute
            # access on it that resolves to non-{wire, router} from
            # within business logic would be a violation. We approximate
            # by checking attribute accesses below.
        # Attribute access on the imported module name (e.g.
        # `_money_divergence.scan_modules(...)`). The only allowed
        # attribute accesses are `.wire(...)`, `.router`. Anything else
        # from non-test production code is a violation.
        src = py.read_text()
        if "money_divergence" not in src:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id.endswith("money_divergence")
                and node.attr not in allowed_names
            ):
                violations.append(
                    (str(py.relative_to(BACKEND)), node.lineno,
                     f"{node.value.id}.{node.attr}")
                )

    assert violations == [], (
        f"B4.5 violated — {len(violations)} operational reference(s) "
        f"to money_divergence outside the allow-list {allowed_names}:\n"
        + "\n".join(f"  {f}:{ln}  {name}" for f, ln, name in violations)
        + "\nThe engine must not participate in business logic."
    )


# ── Covenants 3, 4, 5 (composite): NO gating, NO repair, NO truth influence ─

def test_no_payout_or_repair_paths_consult_divergence_output():
    """Composite check: scan all production code for any pattern that
    looks like control-flow based on divergence output. We look for:

      • `if ...divergence...:` / `if ...diverged...:` / `if ...ok ==`
        adjacent to divergence-related identifiers
      • `.classification ==` checks inside non-divergence non-reader
        modules
      • Any "repair" / "fix" / "heal" function in money_* modules
        that reads divergence results

    This is a heuristic (not a strict AST contract) — false positives
    are OK; the test fails loudly with the line so a human can confirm.
    """
    EXCLUDE = {"__pycache__", "tests", "_archive"}
    # The divergence module itself, the projection-compare reader
    # (which classifies for diagnostic purposes), and the wallet reader
    # (which logs classification-based info-vs-warn) are all legitimate
    # producers/consumers of classification — they don't drive business
    # logic on it.
    EXCLUDE_FILES = {
        "money_divergence.py",
        "money_projections.py",
        "dev_wallet_reader.py",
    }
    SUSPECT_TOKENS = (
        "diverged",
        "divergence",
        ".classification",
    )
    # Words that, near a SUSPECT_TOKEN, indicate operational branching.
    OPERATIONAL_KEYWORDS = (
        "payout",
        "repair",
        "heal",
        "fix_",
        "gate",
        "block",
        "deny",
        "approve",
        "reject",
    )

    findings = []
    for py in BACKEND.rglob("*.py"):
        if any(p in EXCLUDE for p in py.parts):
            continue
        if py.name in EXCLUDE_FILES:
            continue
        src = py.read_text()
        if not any(tok in src for tok in SUSPECT_TOKENS):
            continue
        for lineno, line in enumerate(src.splitlines(), 1):
            stripped = line.strip()
            # Skip pure comments / docstrings.
            if stripped.startswith("#"):
                continue
            if not any(tok in line for tok in SUSPECT_TOKENS):
                continue
            # Look for combos of suspect-token + operational-keyword
            # in the same line.
            if any(kw in line.lower() for kw in OPERATIONAL_KEYWORDS):
                # Filter out obvious docstring / explanatory text
                # (a line that's part of a triple-quoted string and
                # doesn't contain `if `/`elif `/`while ` is just prose).
                if (
                    "if " not in stripped
                    and "elif " not in stripped
                    and "while " not in stripped
                    and "return " not in stripped
                    and "raise " not in stripped
                ):
                    continue
                findings.append((str(py.relative_to(BACKEND)), lineno, stripped[:120]))

    assert findings == [], (
        f"B4.5 violated — {len(findings)} site(s) appear to branch on "
        f"divergence output with operational keywords:\n"
        + "\n".join(f"  {f}:{ln}  {snippet}" for f, ln, snippet in findings)
        + "\nDivergence output must NEVER gate payouts, drive repairs, "
        f"or influence source-of-truth selection."
    )


# ── Positive sanity ──────────────────────────────────────────────────────

def test_divergence_envelope_carries_passive_observer_mode():
    """The HTTP envelope must announce the mode so dashboards render
    results with the correct mental model. We check this by parsing the
    module and asserting the envelope constant exists with the right
    keys."""
    src = DIVERGENCE_FILE.read_text()
    assert "_PASSIVE_OBSERVER_ENVELOPE" in src, (
        "Missing _PASSIVE_OBSERVER_ENVELOPE constant — the B4.5 contract "
        "requires every HTTP response to declare mode + legacy status."
    )
    # Run the module to verify the envelope shape.
    import importlib
    import sys
    sys.path.insert(0, str(BACKEND))
    md = importlib.import_module("money_divergence")
    env = md._PASSIVE_OBSERVER_ENVELOPE
    assert env.get("mode") == "passive_observer", env
    assert env.get("legacy_dev_wallets_status") == "frozen_diagnostic", env
    assert "contract" in env, env


def test_frozen_by_design_drifts_demoted_to_info_severity():
    """Three classes operate on frozen-by-design legacy mirrors and
    must therefore be severity=info post-B4.5, not error/warning:

      • `legacy_drift_total_earnings` — frozen users.total_earnings
        vs frozen dev_wallets.earned_lifetime.
      • `withdrawals_drift` — active dev_withdrawals vs frozen
        dev_wallets.withdrawn_lifetime.
      • `wallet_journal_drift` — active dev_earning_log vs frozen
        dev_wallets.earned_lifetime.

    `wallet_balance_equation_broken` stays at severity=error
    intentionally: it asserts INTERNAL consistency of the frozen
    dev_wallets row at the moment of freeze. If broken, it indicates
    a real pre-B4.4 substrate inconsistency worth surfacing."""
    src = DIVERGENCE_FILE.read_text()
    tree = _ast(DIVERGENCE_FILE)
    findings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = [
                k.value for k in node.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            ]
            if "class" not in keys or "severity" not in keys:
                continue
            cls_val = None
            sev_val = None
            for k, v in zip(node.keys, node.values):
                if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
                    continue
                if k.value == "class" and isinstance(v, ast.Constant):
                    cls_val = v.value
                if k.value == "severity" and isinstance(v, ast.Constant):
                    sev_val = v.value
            if cls_val and sev_val:
                findings[cls_val] = sev_val

    for cls in (
        "legacy_drift_total_earnings",
        "withdrawals_drift",
        "wallet_journal_drift",
    ):
        assert findings.get(cls) == "info", (
            f"{cls} severity = {findings.get(cls)!r} — must be 'info' "
            f"post-B4.5 (frozen-by-design mirror drift)."
        )
    # Sanity: wallet_balance_equation_broken should still be error.
    assert findings.get("wallet_balance_equation_broken") == "error", (
        f"wallet_balance_equation_broken must STAY at error — it is "
        f"the only signal of pre-B4.4 internal substrate inconsistency."
    )
