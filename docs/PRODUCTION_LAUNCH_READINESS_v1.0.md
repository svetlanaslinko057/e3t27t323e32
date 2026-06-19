# LUMEN — Production Launch Readiness v1.0

> Canonical pre-go-live checklist. **Generated from `launch_checklist_seed.py` — do not edit by hand.**
> Walk this list before accepting the first real investor money. `🛑 BLOCKER` items MUST be green (auto-detected or admin-overridden with evidence) before go-live.

Total items: **130** across **12** domains.

---

## 1. A2 — Real Funding Rails — A2 — Реальні рейки поповнення

| # | Item | Severity | Owner | Auto | Status |
|---|------|----------|-------|------|--------|
| 1 | Stripe Live: account activated, live keys in prod, payout bank linked | 🛑 BLOCKER | owner | manual |  |
| 2 | Business KYB completed with payment provider (docs, UBO, licences) | 🛑 BLOCKER | owner | manual |  |
| 3 | Real IBAN opened for platform/SPV legal entity | 🛑 BLOCKER | owner | manual |  |
| 4 | SEPA inbound: bank accepts incoming transfers to funding account | 🛑 BLOCKER | owner | manual |  |
| 5 | SWIFT inbound: correspondent details confirmed for intl investors | 🔴 critical | owner | manual |  |
| 6 | Monobank Business / UAH acquiring connected (if UAH needed) | 🟠 major | owner | manual |  |
| 7 | Payment provider selected and pinned in config (not manual_ops) | 🔴 critical | owner | manual |  |
| 8 | Funding webhook signed with secret and verified server-side | 🔴 critical | eng | auto |  |
| 9 | Funding idempotency (webhook replay does not double-post ledger) | 🔴 critical | eng | auto |  |
| 10 | EUR/USD/UAH support with live FX at credit time | 🟠 major | eng | auto |  |
| 11 | Min/max funding limits configured | 🟠 major | ops | manual |  |
| 12 | Payment-proof flow works for manual rails | 🟡 minor | ops | auto |  |

## 2. A3 — Real Withdrawal Rails — A3 — Реальні рейки виводу

| # | Item | Severity | Owner | Auto | Status |
|---|------|----------|-------|------|--------|
| 1 | At least one real withdrawal channel live (SEPA/SWIFT/bank-API/CSV) | 🛑 BLOCKER | owner | manual |  |
| 2 | SEPA payout verified with a real transfer | 🔴 critical | owner | manual |  |
| 3 | SWIFT payout details and routing confirmed | 🟠 major | owner | manual |  |
| 4 | Bank CSV import into withdrawal reconciliation works | 🟠 major | ops | manual |  |
| 5 | Withdrawal approval workflow (maker/checker) implemented | 🔴 critical | eng | auto |  |
| 6 | AML/sanctions re-screen of beneficiary before withdrawal | 🔴 critical | compliance | auto |  |
| 7 | Withdrawal limits and velocity controls configured | 🟠 major | ops | manual |  |
| 8 | Bank fee model accounted for in investor payout | 🟠 major | ops | manual |  |
| 9 | Withdrawal reconciliation: ledger ↔ bank ties out cleanly | 🔴 critical | ops | auto |  |
| 10 | Failed/returned payout handling (retry/return) implemented | 🟡 minor | eng | auto |  |

## 3. RV — Real Provider Validation — RV — Валідація провайдерів (Email)

| # | Item | Severity | Owner | Auto | Status |
|---|------|----------|-------|------|--------|
| 1 | Gmail: real OAuth consent in production completed | 🔴 critical | ops | manual |  |
| 2 | Gmail: push webhook (Pub/Sub) receiving real events | 🟠 major | eng | manual |  |
| 3 | Gmail: real email round-trip succeeds | 🔴 critical | ops | manual |  |
| 4 | Gmail adapter architecturally ready (preflight contract green) | 🟡 minor | eng | auto |  |
| 5 | Outlook: real tenant + app registration confirmed | 🟠 major | ops | manual |  |
| 6 | Outlook: subscription webhook receiving real events | 🟠 major | eng | manual |  |
| 7 | Outlook: real email round-trip succeeds | 🟠 major | ops | manual |  |
| 8 | Outlook adapter architecturally ready (preflight contract green) | 🟡 minor | eng | auto |  |
| 9 | SPF / DKIM / DMARC configured for sending domain | 🔴 critical | eng | manual |  |
| 10 | Transactional email (verification/notifications) works in prod | 🟠 major | eng | auto |  |

## 4. End-to-End Money Cycle — Повний грошовий цикл (E2E)

| # | Item | Severity | Owner | Auto | Status |
|---|------|----------|-------|------|--------|
| 1 | Real cycle executed: investor→funding→ledger→ownership→certificate→dividend→withdrawal→bank | 🛑 BLOCKER | owner | manual |  |
| 2 | Funding correctly posts a ledger entry | 🔴 critical | eng | auto |  |
| 3 | Ledger → ownership updates correctly (≤100%) | 🔴 critical | eng | auto |  |
| 4 | Ownership certificate issued on confirmed stake | 🔴 critical | eng | auto |  |
| 5 | Dividend accrued by scheduler (D1) correctly | 🔴 critical | eng | auto |  |
| 6 | Rounding policy verified on real amounts (no lost cents) | 🔴 critical | eng | manual |  |
| 7 | FX conversion accurate at posting time (NBU snapshot) | 🔴 critical | eng | auto |  |
| 8 | Bank fees reconciled in the actual cycle | 🟠 major | ops | manual |  |
| 9 | Tax postings (PIT 18% + MT 1.5%) applied to dividend | 🔴 critical | eng | auto |  |
| 10 | End-of-cycle reconciliation ties to zero | 🔴 critical | ops | auto |  |
| 11 | All operator manual steps documented and assigned | 🟠 major | ops | manual |  |
| 12 | Investor statement for the cycle generated correctly | 🟡 minor | eng | auto |  |

## 5. Compliance / AML / KYC / Sanctions — Compliance / AML / KYC / Санкції

| # | Item | Severity | Owner | Auto | Status |
|---|------|----------|-------|------|--------|
| 1 | Sanctions/PEP screening active on onboarding and transactions | 🛑 BLOCKER | compliance | auto |  |
| 2 | Watchlist auto-refreshes from OFAC (freshness ≤ 24–48h) | 🔴 critical | compliance | auto |  |
| 3 | KYC pipeline works: collect→verify→decide→audit | 🛑 BLOCKER | compliance | auto |  |
| 4 | Real KYC provider connected (documents + liveness) | 🔴 critical | owner | manual |  |
| 5 | KYB for institutional investors/SPVs in place | 🟠 major | compliance | manual |  |
| 6 | Transaction monitoring with thresholds and alerts enabled | 🔴 critical | compliance | manual |  |
| 7 | SAR/STR (suspicious activity report) procedure defined | 🟠 major | compliance | manual |  |
| 8 | AML responsible officer (MLRO) assigned | 🔴 critical | owner | manual |  |
| 9 | Investor risk scoring (low/medium/high) applied | 🟠 major | compliance | manual |  |
| 10 | Investor accreditation/qualification checks consistent | 🟠 major | eng | auto |  |
| 11 | PEP matches have manual review/escalation workflow | 🟠 major | compliance | manual |  |
| 12 | KYC/AML record retention periods comply with law | 🟡 minor | legal | manual |  |

## 6. Legal Package — Юридичний пакет

| # | Item | Severity | Owner | Auto | Status |
|---|------|----------|-------|------|--------|
| 1 | Terms of Service published and counsel-approved | 🛑 BLOCKER | legal | auto |  |
| 2 | Privacy Policy published (GDPR/local law) | 🛑 BLOCKER | legal | auto |  |
| 3 | AML Policy documented and available | 🛑 BLOCKER | legal | auto |  |
| 4 | KYC Policy documented | 🔴 critical | legal | auto |  |
| 5 | Risk Disclosure published | 🛑 BLOCKER | legal | auto |  |
| 6 | Dividend Policy published | 🔴 critical | legal | auto |  |
| 7 | Secondary Market Rules published | 🔴 critical | legal | auto |  |
| 8 | Investor agreement/SPV documents reviewed by counsel | 🛑 BLOCKER | legal | manual |  |
| 9 | Cookie consent banner matches policy | 🟠 major | eng | manual |  |
| 10 | GDPR processes (data access/erasure — DSR) defined | 🟠 major | legal | manual |  |
| 11 | Legal structure (platform + SPVs) incorporated and valid | 🔴 critical | owner | manual |  |
| 12 | Regulatory stance/licensing confirmed by counsel | 🛑 BLOCKER | owner | manual |  |

## 7. Security — Безпека

| # | Item | Severity | Owner | Auto | Status |
|---|------|----------|-------|------|--------|
| 1 | Security score ≥ 90/100 (auto-audit) | 🛑 BLOCKER | eng | auto |  |
| 2 | Rate limiting enabled on sensitive endpoints | 🔴 critical | eng | auto |  |
| 3 | 2FA available for admin/staff accounts | 🔴 critical | eng | auto |  |
| 4 | Password policy (complexity/lockout) enforced | 🟠 major | eng | auto |  |
| 5 | Security headers (CSP/HSTS/etc.) set | 🟠 major | eng | auto |  |
| 6 | Upload validation (type/size/sanitisation) enforced | 🟠 major | eng | auto |  |
| 7 | Audit log captures admin/financial actions | 🔴 critical | eng | auto |  |
| 8 | Secrets in vault/env, not in code; rotation defined | 🛑 BLOCKER | eng | manual |  |
| 9 | RBAC/permission matrix with no violations | 🔴 critical | eng | auto |  |
| 10 | Session management (expiry/revocation) configured | 🟠 major | eng | manual |  |
| 11 | External pentest/security review done before launch | 🟠 major | owner | manual |  |
| 12 | Backups encrypted and stored securely | 🟠 major | eng | manual |  |

## 8. Data Integrity / Invariants — Цілісність даних / Інваріанти

| # | Item | Severity | Owner | Auto | Status |
|---|------|----------|-------|------|--------|
| 1 | All LR2 invariants (capital/ownership/payouts) green | 🛑 BLOCKER | eng | auto |  |
| 2 | Reporting matches source of truth (cross-verify) | 🔴 critical | eng | auto |  |
| 3 | Total ownership per asset ≤ 100% | 🛑 BLOCKER | eng | auto |  |
| 4 | Ledger balanced (debits=credits) | 🔴 critical | eng | auto |  |
| 5 | No demo data/demo accounts in production | 🛑 BLOCKER | eng | auto |  |
| 6 | No high-risk conflicts of interest (LP=GP, voter=operator) | 🟠 major | compliance | auto |  |
| 7 | Σ distribution lines = net income (waterfall) | 🔴 critical | eng | auto |  |
| 8 | Every active certificate is asset-backed | 🟠 major | eng | auto |  |
| 9 | Unique compliance profile per investor | 🟠 major | eng | auto |  |
| 10 | Fund NAV = sum of cert NAV across SPVs | 🟠 major | eng | auto |  |

## 9. Operations / SOP / DR — Операції / SOP / DR

| # | Item | Severity | Owner | Auto | Status |
|---|------|----------|-------|------|--------|
| 1 | Incident runbooks (funding/withdrawal/recon/sanctions/payout) exist | 🔴 critical | ops | auto |  |
| 2 | DR: backup→restore→compare verified (collections identical) | 🛑 BLOCKER | ops | auto |  |
| 3 | Backups scheduled and monitored | 🔴 critical | ops | manual |  |
| 4 | On-call rota and escalation contacts defined | 🔴 critical | ops | manual |  |
| 5 | Monitoring/dashboards (uptime/latency/errors) configured | 🔴 critical | eng | manual |  |
| 6 | Error tracking enabled and reviewed | 🟠 major | eng | auto |  |
| 7 | Owner assigned for reconciliation and exceptions | 🔴 critical | ops | manual |  |
| 8 | KYC/AML exception escalation path defined | 🟠 major | compliance | manual |  |
| 9 | Response/processing SLAs defined and tracked | 🟡 minor | ops | auto |  |
| 10 | Status page/investor incident comms ready | 🟡 minor | ops | manual |  |
| 11 | Deploy/rollback (change management) process documented | 🟡 minor | eng | manual |  |
| 12 | Payout/data export for bank/accounting works | 🟡 minor | ops | auto |  |

## 10. Reporting / Transparency — Звітність / Прозорість

| # | Item | Severity | Owner | Auto | Status |
|---|------|----------|-------|------|--------|
| 1 | Quarterly reports generated and available to investors | 🔴 critical | eng | auto |  |
| 2 | Fund/asset factsheets produced | 🟠 major | eng | auto |  |
| 3 | Investor statements (contributions/dividends/taxes) correct | 🔴 critical | eng | auto |  |
| 4 | Ownership certificates downloadable | 🔴 critical | eng | auto |  |
| 5 | Dividend/payout history transparently displayed | 🟠 major | eng | auto |  |
| 6 | Investor portfolio shows stake, NAV, yield transparently | 🟠 major | eng | manual |  |
| 7 | Annual tax documents/certificates produced | 🟠 major | eng | auto |  |
| 8 | Full audit trail of financial events available to admin | 🟠 major | eng | auto |  |
| 9 | Platform fees transparently disclosed to investor | 🟡 minor | ops | manual |  |
| 10 | Regulatory/tax reporting (if required) set up | 🟠 major | legal | manual |  |

## 11. Infrastructure / Deployment — Інфраструктура / Деплой

| # | Item | Severity | Owner | Auto | Status |
|---|------|----------|-------|------|--------|
| 1 | LUMEN_ENV=production enables prod gates (seed off, bypass off, purge demo) | 🛑 BLOCKER | eng | auto |  |
| 2 | Demo accounts/quick-access bypass disabled in prod | 🛑 BLOCKER | eng | auto |  |
| 3 | All prod env vars/secrets set and verified | 🔴 critical | eng | manual |  |
| 4 | Health-check endpoints configured for orchestrator | 🟠 major | eng | manual |  |
| 5 | DB indexes ensured for key collections | 🟠 major | eng | auto |  |
| 6 | Scaling/resource parameters set for expected load | 🟡 minor | eng | manual |  |
| 7 | TLS/HTTPS enforced on all domains | 🔴 critical | eng | manual |  |
| 8 | CORS restricted to trusted origins in prod | 🟠 major | eng | manual |  |
| 9 | Log retention/rotation configured | 🟡 minor | ops | manual |  |
| 10 | Prod domain, DNS and certificates configured | 🟠 major | owner | manual |  |

## 12. Investor Experience — Досвід інвестора

| # | Item | Severity | Owner | Auto | Status |
|---|------|----------|-------|------|--------|
| 1 | Investor onboarding (signup→KYC→first contribution) seamless | 🔴 critical | eng | auto |  |
| 2 | KYC flow clear, with statuses and guidance | 🔴 critical | eng | auto |  |
| 3 | Funding UX clear, with confirmation and receipt | 🔴 critical | eng | auto |  |
| 4 | Investor cabinet shows portfolio/payouts/documents | 🟠 major | eng | manual |  |
| 5 | Notifications (funding/dividend/KYC) work and are localised | 🟠 major | eng | auto |  |
| 6 | Investor support channel defined and staffed | 🟠 major | ops | manual |  |
| 7 | Localisation (UA/EN) complete on key screens | 🟡 minor | eng | auto |  |
| 8 | Mobile/responsive experience verified | 🟡 minor | eng | manual |  |

---

### Legend
- **Severity**: 🛑 BLOCKER (must be green) · 🔴 critical · 🟠 major · 🟡 minor
- **Auto**: `auto` = evaluated live by the system · `manual` = owner/legal/ops evidence + admin override
- **Status**: ✅ completed · ➖ not applicable · ⬜ pending

_Source of truth: `/app/backend/launch_checklist_seed.py`. Live dashboard: `/admin/launch-readiness` → Launch Checklist tab._
