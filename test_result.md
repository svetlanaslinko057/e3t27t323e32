#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: |
  LUMEN RWA platform. Enhance the public Assets experience:
  (A) /assets list: add search SUGGESTIONS + validation, comprehensive SORTING (yield, price/min_ticket,
      progress, newest), and PAGINATION "show 6 by default, then 'Показати більше' (+6)". Added 9 demo
      assets (15 total) so pagination is meaningful.
  (B) Asset detail Capital Stack ("Структура капіталу угоди"): show REAL crypto vs fiat raised computed
      from confirmed pool contributions (lumen_pool_contributions, grouped by gateway). Structure =
      Кошти інвесторів·криптою + ·фіатом + Резервний фонд + Власні кошти. Removed debt/credit.
  (C) Asset detail Location: replaced broken static map image with a FREE no-key interactive Leaflet+OSM
      (CARTO Positron tiles) map with a green marker, plus "Прокласти маршрут" button that detects user
      geolocation and opens Google Maps directions (origin→object).

backend:
  - task: "Real crypto/fiat capital stack from pool contributions"
    implemented: true
    working: true
    file: "backend/lumen_asset_intelligence.py, backend/seed_assets_expansion.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: |
            Added crypto_fiat_split() aggregating confirmed lumen_pool_contributions by gateway.
            Rebuilt _capital_stack to output investors_crypto/investors_fiat/reserve/platform layers
            (no debt) + crypto_raised/fiat_raised/crypto_percent/fiat_percent. Wired into
            GET /api/assets/{id}/capital-stack and /intelligence. Seeded 9 new assets + capital_stack
            + raised_crypto/raised_fiat + geo on all 15 assets + 140 confirmed contributions (crypto+fiat).
            Verified via curl: asset-podilskyi returns crypto 900000 (40%) / fiat 1350000 (60%), reserve,
            platform; no debt. /api/assets returns 15 (12 open).

frontend:
  - task: "/assets list — search suggestions, validation, sorting, Показати більше pagination"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/public/PublicAssetsPage.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: |
            Search input shows suggestions dropdown (asset titles + locations) once >=2 chars; <2 chars
            shows a hint; no-match shows message; clear (x) button; keyboard nav. Sort <select> with 7
            options (featured/yield asc-desc/ticket asc-desc/progress/newest). Pagination: 6 cards then
            "Показати більше" (+6) with "Показано N з M". Result count + reset filters. data-testids:
            assets-search-input, assets-search-suggestions, assets-suggestion-{i}, assets-search-hint,
            assets-search-clear, assets-sort-select, assets-grid, assets-show-more, assets-shown-count,
            assets-result-count.

  - task: "Asset detail — interactive Leaflet map + Прокласти маршрут + crypto/fiat capital stack"
    implemented: true
    working: "NA"
    file: "frontend/src/components/public/AssetMap.jsx, frontend/src/pages/PublicAssetDetail.js, frontend/src/components/lumen/AssetIntelligence.js"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: |
            Replaced broken static map img with AssetMap.jsx (Leaflet + CARTO Positron tiles, free no-key),
            green pulsing marker + popup. "Прокласти маршрут" [asset-map-route] uses navigator.geolocation
            then opens Google Maps directions (origin=user,destination=object) in new tab; falls back to
            destination-only if denied. "Відкрити в Google Maps" [asset-map-open]. CapitalStack now shows
            crypto/fiat highlight tiles [capital-crypto]/[capital-fiat] + note. data-testids: asset-map,
            asset-map-route, asset-map-open, capital-stack, capital-stack-rails.

metadata:
  created_by: "main_agent"
  version: "1.3"
  test_sequence: 3
  run_ui: true

test_plan:
  current_focus:
    - "Real crypto/fiat capital stack from pool contributions"
    - "/assets list — search suggestions, validation, sorting, Показати більше pagination"
    - "Asset detail — interactive Leaflet map + Прокласти маршрут + crypto/fiat capital stack"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: |
        Test BACKEND + FRONTEND for the public Assets upgrade. No login needed (public pages).

        BACKEND (curl):
        1. GET /api/assets?limit=60 → total 15, ~12 open.
        2. GET /api/assets/asset-podilskyi/capital-stack → crypto_raised>0, fiat_raised>0, layers contain
           investors_crypto + investors_fiat + reserve + platform, NO layer with key "debt".
        3. GET /api/assets/asset-kharkiv-bc/intelligence → capital_stack has crypto/fiat split.

        FRONTEND (https://admin-logic-test-1.preview.emergentagent.com ; pages are lazy-loaded, a brief
        'Завантаження…' spinner may flash — wait for content):
        4. /assets: type >=2 chars in [data-testid=assets-search-input] → suggestions dropdown
           [assets-search-suggestions] appears; typing 1 char shows hint [assets-search-hint]; clicking a
           suggestion [assets-suggestion-0] fills the search; clear button [assets-search-clear] resets.
        5. /assets: change [assets-sort-select] (e.g. yield_desc) → grid order changes.
        6. /assets: by default 6 cards in [assets-grid]; [assets-show-more] visible; clicking it loads +6;
           [assets-shown-count] updates.
        7. /objects/asset-podilskyi: capital stack [capital-stack] shows crypto tile [capital-crypto] and
           fiat tile [capital-fiat]; Location block has an interactive map [asset-map] and a
           "Прокласти маршрут" button [asset-map-route] (do NOT need to grant geolocation — just confirm
           the button exists and is clickable) + "Відкрити в Google Maps" [asset-map-open].
        Do NOT test drag-and-drop, camera, or voice.

frontend:
  - task: "Advanced asset-based yield calculator on /calculator page"
    implemented: true
    working: true
    file: "frontend/src/components/public/AssetYieldCalculator.jsx, frontend/src/pages/public/PublicCalculatorPage.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: |
            Extracted the advanced calculator (computeProjection model + AssetSelect popover)
            from dead code in LandingPage.js into a new reusable, publicly-styled component
            AssetYieldCalculator.jsx. Removed the basic version from PublicCalculatorPage.jsx
            and now render the advanced calculator + explanatory 'how income is calculated'
            blocks + CTA.
        - working: true
          agent: "testing"
          comment: |
            100% pass (iteration_3.json). Verified: asset selector lists 3 open assets and
            updates info + projection on change; amount input + slider update all projection
            metrics (pool share %, monthly rental, appreciation, gross/net profit, 19.5% tax,
            effective IRR, total at exit, 3 scenarios); min-ticket validation shows red error
            and hides projection; CTA navigates to /objects/{id}; OLD basic calculator UI fully
            removed. No issues found.

  - task: "FAQ redesign — editorial numbered accordion on /contacts page"
    implemented: true
    working: true
    file: "frontend/src/components/public/FaqList.jsx, frontend/src/components/public/public.css, frontend/src/pages/public/PublicContactsPage.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: |
            Replaced the shadcn Accordion FAQ on /contacts with a new editorial component
            FaqList.jsx (slash numbering, large bold question, animated "+" toggle, gold lines).
        - working: true
          agent: "testing"
          comment: |
            100% pass (iteration_4.json). Verified slash numbering 1/..6/ in gold, large bold
            deep-green questions, "+" rotates 135deg to "x" on open, thin gold gradient dividers,
            single-open behavior, smooth framer-motion expand/collapse, cream bg rgb(251,249,244),
            no console errors. Note: frontend needed a restart to pick up the new component file.

metadata:
  created_by: "main_agent"
  version: "1.2"
  test_sequence: 2
  run_ui: true

test_plan:
  current_focus:
    - "FAQ redesign — editorial numbered accordion on /contacts page"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: |
        Test ONLY the FAQ on the /contacts public page (no login needed). The page is
        lazy-loaded (brief 'Завантаження…' Suspense flash is normal). Verify:
        1. The FAQ section [data-testid=contacts-faq] renders 6 questions, each prefixed with
           slash numbering "1/", "2/", … "6/", with a "+" icon on the right and a thin divider
           line under each row.
        2. Clicking a question [data-testid=faq-trigger-{i}] expands its answer
           [data-testid=faq-content-{i}] with a smooth animation and rotates the "+" into an
           "x" (135deg). Clicking it again collapses it.
        3. Opening a different question closes the previously open one (single-open behavior).
        4. No console errors; styling uses green/gold LUMEN palette on cream background.
        Do NOT test drag-and-drop, camera, or voice. Frontend-only test.