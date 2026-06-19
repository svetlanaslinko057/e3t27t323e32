# LUMEN — Production Secrets Audit

- **Generated:** 2026-06-18T16:52:11.024614+00:00
- **Production mode:** False
- **Verdict:** **BLOCKED**
- **Production-ready:** True

| Check | Status | Detail |
|-------|--------|--------|
| Test/sandbox key patterns absent | BLOCKED | found in: STRIPE_API_KEY |
| No placeholder/changeme secrets | PASS |  |
| Demo/dev backdoors disabled | PASS |  |
| Production-mode sanity (LUMEN_ENV) | BLOCKED | env='preview' — prod checks deferred |
| No debug/dev/bypass routes exposed (openapi, 1376 routes) | PASS |  |

_Read-only. Secret values are never printed — only masked fingerprints._
