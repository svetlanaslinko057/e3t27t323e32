# LUMEN — Fresh Deployment & Audit Report
_Date: 2026-06-18 · Environment: Emergent preview (new workspace)_
_Preview URL: https://expo-project-hub-1.preview.emergentagent.com_

## 0. TL;DR
- ✅ **Project fully redeployed and running** in this new workspace: Backend (FastAPI + Socket.IO), Frontend (React 19 / CRA+craco), MongoDB, plus the **Expo mobile app** (deps installed & validated).
- **LUMEN** = enterprise **Real-World-Asset (RWA) investment platform** (web) + native **Expo iOS/Android investor app**.
- Scale verified this session: **370 backend Python files · ~1,385 API routes · React 19 web app · Expo mobile app**.
- Landing page renders correctly with live data (assets, open rounds, stats), bilingual UK/EN, currency displayed in **USD/USDT**.

## 1. Deployment Status — DONE
| Service | Status | Notes |
|---|---|---|
| Backend (FastAPI + Socket.IO) | ✅ RUNNING :8001 | clean startup, full demo seed, ~1385 routes |
| Frontend (React 19 + craco) | ✅ RUNNING :3000 | compiles, only ESLint warnings (no errors), HTTP 200 |
| MongoDB | ✅ RUNNING :27017 | DB `lumen_database`, indexes + demo seeds created |
| `/api/healthz` / `/api/readyz` | ✅ `ok` / `ready=true` | mongo + config OK |
| Mobile (Expo) | ✅ deps installed | `expo-doctor` 16/17 pass |

### Setup steps applied during this (re)deployment
1. **Migrated repo into `/app`** (backend, frontend, mobile, packages, docs), preserving the environment's protected `MONGO_URL` and `REACT_APP_BACKEND_URL`.
2. **Backend deps**: installed a **filtered `requirements.txt`** excluding the custom `litellm` wheel + `emergentintegrations` lines (already present in base image) to avoid the known `ResolutionImpossible` conflict. Non-blocking warning remains: emergentintegrations wants `stripe<15`, repo pins `15.0.1`.
3. **Frontend**: full `yarn install` for the repo's React-19 dependency set; removed leftover boilerplate `jsconfig.json` that conflicts with the repo's `tsconfig.json`.
4. **Backend `.env`** configured: `MONGO_URL`, `DB_NAME=lumen_database`, `CORS_ORIGINS=*`, `LUMEN_ONLY=true`, `LUMEN_ENV=preview`, `EMERGENT_LLM_KEY`.
5. **Mobile preview URLs** updated `expo-dev-deploy…` → current preview URL in `app.json`, `eas.json`, `src/api.ts`; mobile `yarn install` done.

## 2. What LUMEN Is
Global RWA platform: users invest in fractional shares of real estate / business assets (from $1,000), earn dividends, and trade shares on a secondary **OTC market**. Ownership = digital certificates. Bilingual **UK/EN**. Display currency = **USD/USDT**; internal accounting in UAH (FX `UAH_PER_USD = 41`).
- **6 role surfaces**: Landing / Investor / Operator / Manager / Institutional / Admin.
- **Domain lock** (`LUMEN_ONLY=true`): legacy "EVA-X" startups skipped (54 skipped / 13 LUMEN active at boot); legacy SaaS code runtime-isolated.
- Subsystems seeded at boot: Funding, Wallet, Payouts, Secondary/OTC market, Asset Intelligence, Community, Liquidity, Capital Formation, Operator OS, Institutional OS, Accreditation, Compliance Vault, LP/GP, Reporting OS.

## 3. Working Credentials (seeded)
| Role | Email | Password |
|---|---|---|
| Operator | `operator@atlas.dev` | `operator123` |
| Manager | `manager@atlas.dev` | `manager123` |
| Demo client | `POST /api/auth/demo` | instant cookie session (HttpOnly `session_token`) |

⚠️ No admin account seeded under `LUMEN_ONLY=true`. An admin user must be created to reach admin pages.

## 4. Verified Working (this session)
- `GET /api/healthz` → `{"status":"ok"}`; `GET /api/readyz` → `{"ready":true,...}`.
- `POST /api/auth/demo` → sets session cookie; `GET /api/auth/me` & `GET /api/investor/portfolio` → **200** with cookie.
- `POST /api/auth/login` (operator) → **200**.
- `GET /api/assets` → **200** (live asset list); `GET /api/public/otc/listings` → **200** (6 listings seeded).
- Landing page renders fully (assets, rounds, stats, USD currency, OTC nav) — confirmed by screenshot.

## 5. Open Items / Findings (for "what's next")
### 5.1 Mobile (Expo) — auth contract drift (genuine, needs fix)
- `mobile/README.md` + `mobile/src` expect `POST /api/auth/quick {email}` → `{user, session_token}`, but the live backend returns `{isNew, email}` (now a **2-step OTP flow** via `auth_otp.py`). **Mobile auth wiring must be updated** to match the current backend, otherwise login on the Expo app will not complete end-to-end.
- The web app uses an **HttpOnly `session_token` cookie**; mobile uses a **Bearer token** in AsyncStorage. Need to confirm the backend issues a body-returned token usable by mobile (OTP-verify path).
- `expo-doctor`: only failure = **non-square store icons** (`icon.png`, `adaptive-icon.png` are 535×99). Need square 1024² assets before an EAS build.

### 5.2 Admin access
- Seed/enable an **admin user** to reach the admin role surfaces (none seeded under `LUMEN_ONLY=true`).

### 5.3 Integrations (config-gated / mock in preview)
Stripe, WayForPay/LiqPay/Monobank, Resend (email), Gmail/Outlook, Google OAuth, Cloudinary, Sentry/Rollbar — all read from env and run in **mock/unavailable mode** until real keys are provided.

### 5.4 Production readiness (from repo's own contracts)
The repo ships self-audit contracts (`system_readiness_report.py`, security/architecture invariants, `pool_os`). Per the prior committed report, `READY_FOR_BANKS=false` in preview with a few genuine security/architecture-invariant items to review before any real-money launch.

## 6. Recommended Next Steps (to discuss)
1. Decide **focus area**: web app, Expo mobile app, or both.
2. Fix **mobile auth contract** drift + square store icons (to make the Expo app runnable end-to-end).
3. Seed/enable an **admin user**.
4. Provide **real keys** when ready (payments / email / OAuth) to lift mock/BLOCKED gates.
5. Review the genuine security + architecture-invariant findings if heading toward production.
