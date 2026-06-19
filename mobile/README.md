# LUMEN — Mobile App (Expo)

Native **iOS + Android** investor app for the LUMEN RWA platform, built with
**Expo (Expo Router)**. It talks to the **same FastAPI backend** as the web app
and reuses the same brand identity (green / gold / cream). All money is shown in
**USD / USDT** — never UAH.

## What's inside (v1 каркас + client flow)
- **Auth**: email/password + one-tap **demo investor** (Bearer-token auth, token in AsyncStorage `atlas_token`).
- **Welcome** onboarding screen.
- **Tabbed cabinet**: Портфель (dashboard) · Активи (opportunities) · Дохід (income/dividends) · OTC (secondary market) · Профіль.
- **Asset detail** + **Invest flow** (USD/USDT, converts to backend UAH base on submit).
- Profile shows placeholders for Documents / Security-2FA / **Referral (coming)** / Settings.

> The "developer" surface from the old EVA-X skeleton is intentionally **excluded** — this is the client app only.

## Configuration
API base URL is read from `EXPO_PUBLIC_API_URL` (fallback: `app.json > extra.apiUrl`).
```
cp .env.example .env       # edit EXPO_PUBLIC_API_URL if needed
```
Default points to the current preview backend so it works out of the box.

## Run (development)
```
cd mobile
yarn install            # already run once
npx expo start          # press i (iOS sim) / a (Android) / scan QR with Expo Go
```

## Build for stores (EAS)
```
npm i -g eas-cli
eas login
eas build -p ios --profile production
eas build -p android --profile production
eas submit -p ios     # / android
```
Update `app.json` `ios.bundleIdentifier` / `android.package` and add proper
store-sized `assets/icon.png` (1024²) & `assets/splash.png` before submitting
(current assets reuse the brand logo as placeholders).

## Backend contract
- Auth: `POST /api/auth/login {email,password}` · `POST /api/auth/quick {email}` → `{ user, session_token }`; `GET /api/auth/me`.
- Data: `GET /api/investor/portfolio`, `GET /api/assets`, `GET /api/assets/:id`,
  `GET /api/investor/income(+/payouts)`, `GET /api/investor/otc/listings`,
  `POST /api/investor/otc/listings/:id/buy`, `POST /api/investor/intent`.
- Send `Authorization: Bearer <session_token>` on every request.

## Roadmap (next)
Documents/certificates screen, 2FA + biometric unlock (expo-local-authentication wired),
referral program, push notifications for dividends, full payments/checkout flow,
EN localization, polished store assets.
