# plan.md — LUMEN Public Assets Upgrade (List + Detail)

## 1) Objectives
- Upgrade **/assets** public list UX: better search (hints + validation), richer sorting, and **progressive pagination** (6 → +6 “Показати більше” / “Show more”).
- Upgrade **/objects/:id** public detail:
  - **Capital Stack**: show **real** raised split **crypto vs fiat** from backend pool contributions; simplify structure (Investors split + Reserve + Own/platform; no debt).
  - **Location**: replace static map with **free, no-key** interactive map (Leaflet + OSM) + “Прокласти маршрут” button (BB Cars style) that uses geolocation and opens Google Maps directions.
- Add **6–9 demo assets** + seeded pools/contributions so list pagination + capital stack have real data.

## 2) Implementation Steps

### Phase 1 — Core POC (prove the hard parts work end-to-end)
**User stories (POC)**
1. As a visitor, I can open an asset and see **crypto vs fiat** amounts computed from real contribution records.
2. As a visitor, the capital stack does **not** show credit/debt.
3. As a visitor, I see an interactive map with a marker at the object location (no API key).
4. As a visitor, I can click “Прокласти маршрут” and get Google Maps directions from my current location.
5. As a visitor, I can load more assets beyond the first 6.

**Backend POC (data + aggregation)**
- Add aggregation helper: sum confirmed `lumen_pool_contributions` by `gateway` for a given `asset_id` → `{fiat_usd, crypto_usd, total_usd}`.
- Update `backend/lumen_asset_intelligence.py:_capital_stack`:
  - Remove `debt` layer.
  - Layers: `investors_fiat`, `investors_crypto` (real aggregation), `reserve` (authored or derived), `platform` (own funds; authored or 0).
  - Keep `asset_value` and `investor_share_percent` (based on investors total / total capital).
- Seed real data:
  - Create pools in `lumen_pools` for each asset.
  - Create **confirmed** contributions in `lumen_pool_contributions` with a realistic crypto/fiat mix.
- Quick verification scripts/curl:
  - `GET /api/assets/{id}/intelligence` returns `capital_stack.layers` including both investor split layers with non-zero values.

**Frontend POC (map + directions + capital stack render)**
- Install `leaflet` and CSS.
- Implement `frontend/src/components/public/AssetMap.jsx` using plain Leaflet (avoid react-leaflet peer issues).
- Replace map block in `frontend/src/pages/PublicAssetDetail.js`:
  - Render Leaflet map if dto.map has lat/lng.
  - Add “Прокласти маршрут” button:
    - `navigator.geolocation.getCurrentPosition()` → open `https://www.google.com/maps/dir/?api=1&origin=LAT,LNG&destination=ALAT,ALNG`.
    - If denied/unavailable: open destination search link.
- Ensure `CapitalStack` component displays the new layers clearly (labels “Кошти інвесторів · фіатом/криптою”).

**Exit criteria (POC)**
- One asset shows correct crypto/fiat split + reserve + platform; Leaflet map renders; directions button opens Google Maps.

---

### Phase 2 — V1 App Development (assets list + detail polish)
**User stories (V1)**
1. As a visitor on /assets, I can search by name/location with helpful suggestions.
2. As a visitor, invalid/empty search behaves gracefully (trim, min chars, clear state).
3. As a visitor, I can sort assets by yield, min ticket, progress, and newest.
4. As a visitor, I see 6 cards by default and can load more via “Показати більше”.
5. As a visitor on /objects/:id, I see capital stack with real crypto/fiat breakdown and a map + route button.

**/assets page upgrades (`PublicAssetsPage.jsx`)**
- Search UX:
  - Trim input; optional min length before filtering (e.g., 2 chars) with subtle hint.
  - Add suggestions dropdown (top matches by title/location) with keyboard + click select.
  - “No results” state remains.
- Sorting:
  - Add sort dropdown: `yield_desc`, `min_ticket_asc/desc`, `progress_desc`, `newest` (by `created_at`/`updated_at` fallback).
- Pagination:
  - Render `visibleCount=6`; button increments by 6.
  - Button label: UA “Показати більше”, EN “Show more” (reuse i18n if available; else UA-only now).
  - Reset visibleCount on filter/query/sort change.
- Add 6–9 demo assets (seed) so pagination is testable.

**Asset detail polish (`PublicAssetDetail.js`)**
- Capital Stack:
  - Add small note: “Дані зібрані з внесків пулу (fiat/crypto)”.
  - Ensure percent bar looks good with new layers.
- Location:
  - Style map container to match LUMEN (rounded, border, subtle shadow).
  - Keep “Відкрити в Google Maps” link.

**Testing (end of Phase 2)**
- Call testing agent for:
  - /assets search + suggestions + validation + sort + show-more.
  - /objects/:id capital stack split correctness + map + directions button.

---

### Phase 3 — Hardening + Admin hooks (as needed)
**User stories (hardening)**
1. As an admin (later), I can set reserve/platform amounts per asset for correct capital structure.
2. As a visitor, capital stack still renders sensibly even if contributions are missing.
3. As a visitor, map gracefully falls back when coords are missing.
4. As a visitor, performance stays smooth with more assets.
5. As a visitor, sorting behaves consistently across pagination.

- Backend fallbacks:
  - If no contributions: set investors split to 0/0 and rely on reserve/platform authored or derived.
- Optional admin additions:
  - Add admin fields to edit `asset.capital_stack.reserve` and `asset.capital_stack.platform`.
- Add lightweight caching of aggregation results per request (optional).
- Regression test again via testing agent.

## 3) Next Actions (immediate)
1. Implement backend aggregation + update `_capital_stack` to output investor_fiat/investor_crypto layers.
2. Add seed script to create pools + confirmed contributions (crypto+fiat mix) for each asset.
3. Install Leaflet and implement `AssetMap.jsx`; wire into `PublicAssetDetail.js` and add “Прокласти маршрут”.
4. Upgrade `/assets` list: suggestions + sorting + show-more + seed extra demo assets.
5. Run testing agent on /assets and /objects/:id.

## 4) Success Criteria (Definition of Done)
- /assets:
  - Search has hints/suggestions + robust behavior; sorting works; shows 6 cards initially; “Показати більше/Show more” loads next items.
  - With seeded assets, pagination is demonstrably meaningful.
- /objects/:id:
  - Capital stack shows real investor split **fiat vs crypto** derived from confirmed contributions; includes reserve + platform; no debt layer.
  - Interactive Leaflet+OSM map renders with marker; “Прокласти маршрут” opens Google Maps directions from user location (or falls back).
- Testing agent validates key flows with no critical console/API errors.
