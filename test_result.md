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
  Deploy the existing LUMEN RWA platform (cloned from GitHub) and continue prior work.
  Latest task: the public "Калькулятор" (/calculator) page showed only a BASIC version
  (amount + term sliders + preset yield). There was a more advanced GLOBAL calculator
  hidden (dead code) in LandingPage.js — it lets the user SELECT a real asset/object,
  shows pool share %, rental cash flow, appreciation, gross/net profit, tax, effective
  IRR, and 3 scenarios. Requirement: delete the basic version and place ONLY the full
  advanced functional calculator on the /calculator page (in blocks).

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
    working: "NA"
    file: "frontend/src/components/public/FaqList.jsx, frontend/src/components/public/public.css, frontend/src/pages/public/PublicContactsPage.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: |
            Replaced the shadcn Accordion FAQ on /contacts with a new editorial component
            FaqList.jsx inspired by a reference design: slash numbering ("1/", "2/", ...),
            large bold question (Space Grotesk), an animated "+" toggle that rotates 135deg
            (into an x) when open, thin gold gradient divider lines, smooth height expand via
            framer-motion. Uses LUMEN palette (deep green ink, gold #C9A961 accents on cream).
            Styles added under .lpub-faq* in public.css. data-testids preserved: contacts-faq
            (container), faq-trigger-{i} (each question button), faq-content-{i} (answer).
            Only one FAQ item open at a time; clicking an open item closes it.

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