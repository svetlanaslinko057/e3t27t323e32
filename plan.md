# plan.md — LUMEN Public Website Restructure (Multi‑page, Far Minerals / ECO style)

## 1) Objectives
- Convert the public marketing site from a **single scrolling landing** into a **multi-page public site** where every menu item opens a dedicated route.
- Implement a shared **PublicLayout shell** (sticky header + animated overlay menu + page transitions + giant multi-column footer) used by all public marketing routes.
- Refactor Landing (`/`) into **selling teasers only** with “Детальніше” CTAs routing to dedicated pages.
- Create/upgrade public pages (UA only):
  - `/how` (Принцип роботи та безпека)
  - `/assets` (каталог + відкриті раунди)
  - `/calculator` (дохідність)
  - `/contacts` (Контакти + FAQ)
  - keep `/otc`, `/app`
- Keep **LUMEN palette** and premium animation style inspired by Farm Minerals + ECO reference repo.

## 2) Implementation Steps

### Phase 1 — Core POC (Public shell + routing + menu)
User stories:
1. As a visitor, I can open the full-screen menu and navigate to any section as a standalone page.
2. As a visitor, the URL changes for each section (e.g. `/how`) and the page loads from the top.
3. As a visitor, I see a consistent header/footer across all public pages.
4. As a visitor, I experience smooth transitions (menu stagger, page curtain) without layout jumps.
5. As a visitor, I can always find Contacts from any page.

Steps:
- Create `layouts/PublicLayout.jsx` (modeled after ECO `PublicLayout`):
  - sticky header (left menu trigger, center logo, right phone + CTA + auth)
  - overlay menu with staggered reveal, watermark in scrim, ESC/scroll-lock
  - route-change scroll reset + optional “curtain” transition component
  - `<Outlet />` for public pages
- Extract/replace current menu logic:
  - move `MenuOverlay` out of `LandingPage.js` into `components/public/PublicMenuOverlay.jsx`
  - centralize NAV config (UA only) in `components/public/publicNav.js`
- Add public routes under the layout in `App.js`:
  - `/`, `/how`, `/assets`, `/calculator`, `/contacts`, `/otc`, `/otc/:id`, `/app`
- POC verification (manual): open menu → navigate between all public pages, confirm header/footer persist, no console errors.

### Phase 2 — V1 App Development (pages + footer + landing teasers)
User stories:
1. As a visitor, the landing page quickly explains the value and guides me via “Детальніше” buttons.
2. As a visitor, `/assets` shows live assets and open rounds with clear cards and a “Деталі” action.
3. As a visitor, `/calculator` lets me estimate income/yield and understand assumptions.
4. As a visitor, `/how` explains the full flow (buy → ownership → payouts) and the security model (SPV + certificate).
5. As a visitor, `/contacts` shows direct channels + FAQ + a quick request form.

Steps:
- Build reusable UI primitives (LUMEN palette):
  - `components/public/PageHero.jsx` (breadcrumb “ГОЛОВНА • …”, title, subtitle)
  - `components/public/Reveal.jsx` (framer-motion `useInView` scroll reveal)
  - `components/public/PublicCurtain.jsx` (simple route transition)
- Implement **giant footer** (`components/public/PublicFooter.jsx`) inspired by ECO:
  - brand + tagline + CTA buttons
  - columns: “Сайт”, “Довідник”
  - contacts block
  - newsletter signup (backend endpoint if exists; otherwise graceful no-op + message)
  - giant wordmark background “LUMEN”
  - bottom bar (© year, badges, privacy/terms links)
- Create/upgrade pages:
  - `pages/public/PublicHowPage.jsx` (`/how`) — combine “як працює” + “безпека та власність”, expanded UA content
  - `pages/public/PublicAssetsPage.jsx` (`/assets`) — call existing `/api/assets`, filters (basic), link to existing `/objects/:id`
  - `pages/public/PublicCalculatorPage.jsx` (`/calculator`) — inputs + computed outputs; optional “приклади сценаріїв” blocks
  - `pages/public/PublicContactsPage.jsx` (`/contacts`) — direct channels, “manager online” indicator, FAQ accordion, request form
- Refactor Landing (`LandingPage.js`):
  - remove deep content sections (How/Security/FAQ/Calculator long blocks)
  - keep hero + key selling narrative + teaser cards pointing to `/how`, `/assets`, `/calculator`, `/otc`, `/app`, `/contacts`
- Ensure `/otc` and `/app` render inside the new PublicLayout (consistent header/footer).
- Call testing agent for V1 end-to-end validation of navigation + page rendering + key interactions.

### Phase 3 — Hardening + missing public endpoints (only if needed)
User stories:
1. As a visitor, contact requests always give me a clear success/error message.
2. As a visitor, newsletter signup validates email and confirms subscription.
3. As a visitor, pages load fast and animations don’t stutter.
4. As a visitor, the menu works on mobile and desktop consistently.
5. As a visitor, I can share any page URL and it opens correctly.

Steps:
- Audit backend for existing public endpoints:
  - newsletter: `/api/public/footer` / subscribe endpoint equivalents
  - contact request endpoint
- If missing, add **minimal** backend endpoints:
  - `POST /api/public/contact` (store to collection + optional email outbox)
  - `POST /api/public/newsletter/subscribe`
- Add form validation + loading/success/error states.
- Polish animations: delays, easing, reduced motion support.
- Call testing agent again for regression (routes, forms, assets list, otc).

### Phase 4 — Future (after approval)
- Re-enable bilingual content (restore `bi()` usage) once UA-only V1 is accepted.
- Add SEO: titles/meta per route, OpenGraph for share.
- Add “Knowledge/Blog” if desired, and legal docs links in footer.

## 3) Next Actions (immediate)
1. Create `PublicLayout` + `PublicMenuOverlay` + `PublicFooter` scaffold and wire routes.
2. Implement `/how` and `/contacts` first (highest “style” signal pages), matching ECO/Farm animations.
3. Refactor Landing into teasers with clean CTAs.
4. Build `/assets` (live data) and `/calculator` (working compute).
5. Run testing agent on navigation + page rendering + forms.

## 4) Success Criteria (Definition of Done)
- Menu items open dedicated URLs: `/how`, `/assets`, `/calculator`, `/otc`, `/app`, `/contacts`.
- Landing (`/`) no longer duplicates full content; it only teases and routes to pages.
- PublicLayout header/footer consistent across all public pages; overlay menu animated and usable.
- Footer is “розмашистий” (multi-column + newsletter + giant wordmark) and fits LUMEN palette.
- `/assets` displays live assets from backend; `/calculator` computes; `/contacts` form behaves correctly.
- No red-screen errors, no critical console errors; testing agent validates core flows.
