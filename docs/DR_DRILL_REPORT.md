# LUMEN — Disaster Recovery Drill Report

- **Generated:** 2026-06-18T16:52:09.257328+00:00
- **Live DB:** `lumen_database`  ·  **Scratch DB:** `lumen_database_dr_verify`
- **Verdict:** **DR_READY**

## Verdict flags

| Flag | Status |
|------|--------|
| DR_READY | ✅ true |
| LEDGER_MATCH | ✅ true |
| POOL_MATCH | ✅ true |
| OWNERSHIP_MATCH | ✅ true |
| CERTIFICATES_MATCH | ✅ true |
| CASH_AUDIT_MATCH | ✅ true |
| RESTORED_INVARIANTS_OK | ✅ true |
| ALL_CASH_RECONCILES | ✅ true |

## Backup → Restore

- Collections copied: **94**
- Document counts match: **True**

## Restored consistency

- Pool invariants passed: 2/2
- Architecture invariants: {'passed': 7, 'failed': 2, 'ok': False}
- Investor balance audit reconciles: True

_Read-only against the live DB. Scratch DB always dropped on exit._
