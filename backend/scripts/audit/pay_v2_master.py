#!/usr/bin/env python3
"""PAY-V2 master guard — phased acceptance check.

Runs all PAY-V2 phase guards in order and reports pass/fail per phase.

Phases:
  - P0 Charter — file exists, decisions+principles sections present
  - P1 Foundation — module surface area + provider mock + indexes
  - P2 Live rails — (placeholder until adapters land)
  - P3 Worker — (placeholder)
  - P4 Reconciliation — (placeholder)
  - P5 UI surface — (placeholder)

Each guard is independent; failing one does not skip the others. Exit code
is the sum of failures (0 means everything passed).
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

GREEN = "\033[32m"
RED = "\033[31m"
YEL = "\033[33m"
DIM = "\033[2m"
RST = "\033[0m"

ROOT = Path("/app")
BACKEND = ROOT / "backend"
CHARTER = ROOT / "docs" / "active-audits" / "PAY_V2_P0_CHARTER.md"


def _fmt(name: str, ok: bool, why: str = "") -> str:
    mark = f"{GREEN}✓{RST}" if ok else f"{RED}✗{RST}"
    extra = f"  {DIM}{why}{RST}" if why else ""
    return f"  {mark} {name}{extra}"


def check_p0_charter() -> int:
    print(f"\n{DIM}▌ PAY-V2-P0 — Charter{RST}")
    if not CHARTER.exists():
        print(_fmt("charter file present", False, f"missing {CHARTER}"))
        return 1
    text = CHARTER.read_text(encoding="utf-8")
    needed = [
        "SIGNED OFF",
        "Decisions",
        "Hard architectural principles",
        "Phased plan",
        "Definition of \"SEALED\"",
        "Stripe Connect",
        "PayPal Payouts",
        "Hybrid",
        "Soft",
        "USD-only",
    ]
    fails = [n for n in needed if n not in text]
    if fails:
        print(_fmt("charter completeness", False, f"missing sections: {fails}"))
        return 1
    print(_fmt("charter signed off + decisions + principles + plan present", True))
    return 0


def check_p1_foundation() -> int:
    print(f"\n{DIM}▌ PAY-V2-P1 — Foundation{RST}")
    fails = 0

    # Files exist
    needed_files = [
        BACKEND / "payouts_v2.py",
        BACKEND / "payouts_v2_api.py",
        BACKEND / "integrations" / "settlement.py",
        BACKEND / "integrations" / "settlement_mock.py",
    ]
    for f in needed_files:
        ok = f.exists()
        print(_fmt(f"file {f.relative_to(ROOT)}", ok))
        if not ok:
            fails += 1
    if fails:
        return fails

    sys.path.insert(0, str(BACKEND))

    # SETTLEMENT capability registered
    try:
        from integrations.base import Capability  # type: ignore
        ok = "SETTLEMENT" in {c.name for c in Capability}
        print(_fmt("Capability.SETTLEMENT registered", ok))
        if not ok:
            fails += 1
    except Exception as e:
        print(_fmt("import integrations.base", False, str(e)))
        fails += 1

    # SettlementProvider ABC + MockSettlementProvider concrete
    try:
        from integrations.settlement import SettlementProvider  # type: ignore
        from integrations.settlement_mock import MockSettlementProvider  # type: ignore
        m = MockSettlementProvider()
        ok = isinstance(m, SettlementProvider)
        print(_fmt("MockSettlementProvider is SettlementProvider", ok))
        if not ok:
            fails += 1
    except Exception as e:
        print(_fmt("instantiate MockSettlementProvider", False, str(e)))
        fails += 1

    # Substrate module surface
    try:
        pv2 = importlib.import_module("payouts_v2")
        for fn in (
            "ensure_indexes", "emit_event", "propose_batch", "release_batch",
            "cancel_batch", "transition_item", "build_queue_view",
            "get_batch_with_items", "get_item_with_history",
            "upsert_payment_profile", "get_payment_profile",
        ):
            ok = callable(getattr(pv2, fn, None))
            print(_fmt(f"payouts_v2.{fn}() defined", ok))
            if not ok:
                fails += 1
        # State machines present
        ok = all(s in pv2.ITEM_STATES for s in ("queued", "initiated", "in_flight", "confirmed", "settled", "reconciled", "failed", "returned", "disputed", "cancelled"))
        print(_fmt("item state machine has 10 canonical states", ok))
        if not ok:
            fails += 1
    except Exception as e:
        print(_fmt("import payouts_v2", False, str(e)))
        fails += 1

    # Router mounted (verify server.py wires it)
    server_py = BACKEND / "server.py"
    text = server_py.read_text(encoding="utf-8")
    for marker, label in [
        ("payouts_v2_api as _pv2_api", "server.py imports payouts_v2_api"),
        ("_pv2_api.register_payouts_v2_routes", "server.py mounts router"),
        ("_pv2_api.scheduler_loop", "server.py starts scheduler loop"),
        ("await _pv2.ensure_indexes", "server.py ensures indexes at startup"),
    ]:
        ok = marker in text
        print(_fmt(label, ok))
        if not ok:
            fails += 1

    return fails


def check_p2_live_rails() -> int:
    print(f"\n{DIM}▌ PAY-V2-P2 — Live rails (Stripe Connect + PayPal Payouts){RST}")
    stripe = BACKEND / "integrations" / "settlement_stripe.py"
    paypal = BACKEND / "integrations" / "settlement_paypal.py"
    if stripe.exists() and paypal.exists():
        print(_fmt("StripeConnect + PayPal adapters present", True))
        return 0
    print(_fmt("not yet implemented (P2 placeholder)", True, "skipped — phase not started"))
    return 0


def check_p3_worker() -> int:
    print(f"\n{DIM}▌ PAY-V2-P3 — Worker / lifecycle drainer{RST}")
    fails = 0

    worker = BACKEND / "payouts_v2_worker.py"
    if not worker.exists():
        print(_fmt("worker module present", False, "missing payouts_v2_worker.py"))
        return 1
    print(_fmt("worker module present", True))

    sys.path.insert(0, str(BACKEND))
    try:
        pv2w = importlib.import_module("payouts_v2_worker")
    except Exception as e:
        print(_fmt("import payouts_v2_worker", False, str(e)))
        return 1

    # Required surface area
    surface = [
        "worker_loop", "reaper_loop", "mock_advancer_loop",
        "worker_status_snapshot", "drain_once_for_test",
        "admin_force_retry", "admin_force_dead_letter",
        "get_provider_for_rail", "WORKER_ID", "CFG",
    ]
    for name in surface:
        ok = hasattr(pv2w, name)
        print(_fmt(f"payouts_v2_worker.{name}", ok))
        if not ok:
            fails += 1

    # Config knobs (env-driven, no hardcoded literals)
    cfg = pv2w.CFG
    knobs = [
        "enabled", "interval_sec", "batch_size", "lease_sec",
        "heartbeat_sec", "max_attempts", "timeout_sec",
        "backoff_base_sec", "backoff_max_sec", "stuck_after_sec",
        "mock_advance_enabled", "mock_advance_delay_sec",
        "reaper_interval_sec",
    ]
    cfg_ok = all(hasattr(cfg, k) for k in knobs)
    print(_fmt(f"worker config has {len(knobs)} env-driven knobs", cfg_ok))
    if not cfg_ok:
        fails += 1

    # server.py wires worker / reaper / advancer
    server_text = (BACKEND / "server.py").read_text(encoding="utf-8")
    for marker, label in [
        ("payouts_v2_worker as _pv2_worker", "server.py imports worker"),
        ("_pv2_worker.worker_loop", "server.py starts worker loop"),
        ("_pv2_worker.reaper_loop", "server.py starts reaper loop"),
        ("_pv2_worker.mock_advancer_loop", "server.py starts mock advancer"),
    ]:
        ok = marker in server_text
        print(_fmt(label, ok))
        if not ok:
            fails += 1

    # Admin endpoints wired
    api_text = (BACKEND / "payouts_v2_api.py").read_text(encoding="utf-8")
    for marker, label in [
        ("/payouts-v2/admin/worker/status", "GET /payouts-v2/admin/worker/status"),
        ("/payouts-v2/admin/worker/drain-once", "POST /payouts-v2/admin/worker/drain-once"),
        ("/payouts-v2/admin/items/{item_id}/force-retry", "POST .../force-retry"),
        ("/payouts-v2/admin/items/{item_id}/dead-letter", "POST .../dead-letter"),
    ]:
        ok = marker in api_text
        print(_fmt(label, ok))
        if not ok:
            fails += 1

    if fails == 0:
        print(_fmt("worker engine wired (claim · lease · retry · dead-letter · reaper)", True))
    return fails


def check_p4_reconcile() -> int:
    print(f"\n{DIM}▌ PAY-V2-P4 — Reconciliation + divergence observer{RST}")
    print(_fmt("not yet implemented (P4 placeholder)", True, "skipped — phase not started"))
    return 0


def check_p5_ui() -> int:
    print(f"\n{DIM}▌ PAY-V2-P5 — UI surface (queue, batch detail, profile){RST}")
    fails = 0

    # Web admin pages
    web_pages_dir = ROOT / "web" / "src" / "pages"
    for page, label in [
        ("AdminPayoutsQueue.js",       "web: AdminPayoutsQueue.js"),
        ("AdminPayoutBatchDetail.js",  "web: AdminPayoutBatchDetail.js"),
    ]:
        ok = (web_pages_dir / page).exists()
        print(_fmt(label, ok))
        if not ok:
            fails += 1

    # Web App.js routes wired
    app_js = (ROOT / "web" / "src" / "App.js").read_text(encoding="utf-8")
    for marker, label in [
        ("AdminPayoutsQueue",               "web: AdminPayoutsQueue imported"),
        ("AdminPayoutBatchDetail",          "web: AdminPayoutBatchDetail imported"),
        ('path="payouts-v2"',               "web: /admin/payouts-v2 route"),
        ('path="payouts-v2/batches/:batchId"', "web: /admin/payouts-v2/batches/:id route"),
    ]:
        ok = marker in app_js
        print(_fmt(label, ok))
        if not ok:
            fails += 1

    # Web nav entry in AdminLayout
    layout = (ROOT / "web" / "src" / "layouts" / "AdminLayout.js").read_text(encoding="utf-8")
    ok = '/admin/payouts-v2' in layout
    print(_fmt("web: AdminLayout nav → /admin/payouts-v2", ok))
    if not ok:
        fails += 1

    # Backend authority: web pages must NOT compute payout aggregates client-side
    # (Pr-7 + WEB-P4). Light heuristic: forbid `.reduce(` on items in these
    # two pages.
    for page in ("AdminPayoutsQueue.js", "AdminPayoutBatchDetail.js"):
        p = web_pages_dir / page
        if p.exists():
            text = p.read_text(encoding="utf-8")
            ok = ".reduce(" not in text
            print(_fmt(f"web: {page} has no client-side .reduce() aggregation", ok))
            if not ok:
                fails += 1

    # Expo screens
    expo_app = ROOT / "frontend" / "app"
    for path, label in [
        (expo_app / "admin" / "payouts.tsx",                     "expo: admin/payouts.tsx"),
        (expo_app / "admin" / "payout-batch" / "[batchId].tsx",  "expo: admin/payout-batch/[batchId].tsx"),
        (expo_app / "developer" / "payout-profile.tsx",          "expo: developer/payout-profile.tsx"),
    ]:
        ok = path.exists()
        print(_fmt(label, ok))
        if not ok:
            fails += 1

    if fails == 0:
        print(_fmt("operational UI wired (web admin · expo admin · developer self-service)", True))
    return fails


def main() -> int:
    print("─" * 60)
    print("PAYOUTS V2 — master guard")
    print("─" * 60)
    fails = 0
    fails += check_p0_charter()
    fails += check_p1_foundation()
    fails += check_p2_live_rails()
    fails += check_p3_worker()
    fails += check_p4_reconcile()
    fails += check_p5_ui()
    print("\n" + "─" * 60)
    if fails == 0:
        print(f"{GREEN}✅ PAY-V2 master guard — current phases pass.{RST}")
        return 0
    print(f"{RED}❌ {fails} guard failure(s) — PAY-V2 not yet at expected state.{RST}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
