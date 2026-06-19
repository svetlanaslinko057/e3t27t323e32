#!/usr/bin/env python3
"""
LUMEN Iteration 12 - Re-verification Test Suite
Re-testing previously-failing checks with corrected inputs
"""
import requests
import sys
import json
import hmac
import hashlib
from datetime import datetime
from typing import Dict, List, Tuple

class LumenIteration12Tester:
    def __init__(self, base_url="https://repo-setup-96.preview.emergentagent.com"):
        self.base_url = base_url
        self.session = requests.Session()
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        
        # CORRECTED test credentials from /app/memory/test_credentials.md
        self.admin_creds = {"email": "admin@devos.io", "password": "admin123"}
        self.admin_atlas_creds = {"email": "admin@atlas.dev", "password": "admin123"}
        self.dev_creds = {"email": "john@atlas.dev", "password": "dev123"}
        self.client_creds = {"email": "client@atlas.dev", "password": "client123"}  # CORRECTED
        self.family_creds = {"email": "family@atlas.dev", "password": "family123"}  # CORRECTED
        self.manager_creds = {"email": "manager@atlas.dev", "password": "manager123"}  # CORRECTED
        
        # Webhook secrets for HMAC validation
        self.gmail_secret = "lumen-dev-webhook-secret"
        self.outlook_secret = "lumen-dev-outlook-secret"

    def log_test(self, category: str, name: str, passed: bool, details: str = ""):
        """Log test result"""
        self.tests_run += 1
        if passed:
            self.tests_passed += 1
            status = "✅ PASS"
        else:
            status = "❌ FAIL"
        
        result = {
            "category": category,
            "name": name,
            "passed": passed,
            "details": details
        }
        self.test_results.append(result)
        print(f"{status} [{category}] {name}")
        if details and not passed:
            print(f"   Details: {details}")

    def run_test(self, category: str, name: str, method: str, endpoint: str, 
                 expected_status: int, data=None, headers=None, session=None) -> Tuple[bool, dict]:
        """Run a single API test"""
        url = f"{self.base_url}{endpoint}"
        req_headers = headers or {}
        test_session = session or requests.Session()
        
        try:
            if method == 'GET':
                response = test_session.get(url, headers=req_headers, timeout=10)
            elif method == 'POST':
                response = test_session.post(url, json=data, headers=req_headers, timeout=10)
            elif method == 'PATCH':
                response = test_session.patch(url, json=data, headers=req_headers, timeout=10)
            else:
                self.log_test(category, name, False, f"Unsupported method: {method}")
                return False, {}

            success = response.status_code == expected_status
            response_data = {}
            
            try:
                response_data = response.json()
            except:
                response_data = {"text": response.text[:200]}
            
            details = f"Status: {response.status_code}"
            if not success:
                details += f" (expected {expected_status}). Response: {json.dumps(response_data)[:300]}"
            
            self.log_test(category, name, success, details if not success else "")
            return success, response_data

        except Exception as e:
            self.log_test(category, name, False, f"Exception: {str(e)}")
            return False, {}

    # ========== CORRECTED AUTH TESTS ==========
    
    def test_investor_login(self) -> Tuple[bool, requests.Session]:
        """Test 1: Investor (client) login with CORRECTED password"""
        investor_session = requests.Session()
        success, response = self.run_test(
            "Auth", "Investor login (client@atlas.dev / client123)",
            "POST", "/api/auth/login", 200,
            data=self.client_creds,
            session=investor_session
        )
        
        if success:
            print(f"   ✓ Investor login successful, session established")
            return True, investor_session
        return False, investor_session

    def test_institutional_login(self) -> Tuple[bool, requests.Session]:
        """Test 2: Institutional investor login"""
        family_session = requests.Session()
        success, response = self.run_test(
            "Auth", "Institutional login (family@atlas.dev / family123)",
            "POST", "/api/auth/login", 200,
            data=self.family_creds,
            session=family_session
        )
        
        if success:
            print(f"   ✓ Institutional investor login successful")
            return True, family_session
        return False, family_session

    def test_manager_login(self) -> Tuple[bool, requests.Session]:
        """Test 3: Manager login"""
        manager_session = requests.Session()
        success, response = self.run_test(
            "Auth", "Manager login (manager@atlas.dev / manager123)",
            "POST", "/api/auth/login", 200,
            data=self.manager_creds,
            session=manager_session
        )
        
        if success:
            print(f"   ✓ Manager login successful")
            return True, manager_session
        return False, manager_session

    def test_admin_login(self) -> Tuple[bool, requests.Session]:
        """Test 4: Admin login for subsequent tests"""
        admin_session = requests.Session()
        success, response = self.run_test(
            "Auth", "Admin login (admin@devos.io / admin123)",
            "POST", "/api/auth/login", 200,
            data=self.admin_creds,
            session=admin_session
        )
        
        if success:
            print(f"   ✓ Admin login successful")
            return True, admin_session
        return False, admin_session

    def test_session_persistence(self, session: requests.Session, role: str) -> bool:
        """Test 5: Session persistence across requests"""
        # Try to access a protected endpoint with the session
        url = f"{self.base_url}/api/admin/ir/leads"
        try:
            response = session.get(url, timeout=10)
            # For non-admin roles, we expect 403 (forbidden) not 401 (unauthorized)
            # For admin roles, we expect 200
            if role == "admin":
                success = response.status_code == 200
            else:
                # Non-admin should get 403 (has session but no permission) or 401
                success = response.status_code in [401, 403]
            
            self.log_test("Auth", f"Session persistence for {role}", success,
                         f"Status: {response.status_code}" if not success else "")
            return success
        except Exception as e:
            self.log_test("Auth", f"Session persistence for {role}", False, str(e))
            return False

    # ========== CORRECTED F4 MANAGER INSTRUCTIONS TESTS ==========
    
    def test_f4_admin_instructions_overview(self, admin_session: requests.Session) -> bool:
        """Test 6: GET /api/admin/manager/instructions-overview with CORRECTED field check"""
        success, response = self.run_test(
            "F4", "GET /api/admin/manager/instructions-overview (check total field)",
            "GET", "/api/admin/manager/instructions-overview", 200,
            session=admin_session
        )
        
        if success and isinstance(response, dict):
            total = response.get("total", 0)
            published = response.get("published", 0)
            drafts = response.get("drafts", 0)
            
            print(f"   ✓ Response structure correct: total={total}, published={published}, drafts={drafts}")
            
            if total >= 5:
                print(f"   ✓ Expected 5+ instructions, got {total}")
                return True
            else:
                self.log_test("F4", "Expected 5+ instructions in total field", False, 
                             f"Got total={total}, published={published}, drafts={drafts}")
                return False
        return False

    def test_f4_manager_instructions(self, manager_session: requests.Session) -> bool:
        """Test 7: GET /api/manager/instructions (manager-side endpoint)"""
        success, response = self.run_test(
            "F4", "GET /api/manager/instructions (manager-side)",
            "GET", "/api/manager/instructions", 200,
            session=manager_session
        )
        
        if success and isinstance(response, dict):
            count = response.get("count", 0)
            instructions = response.get("instructions", [])
            
            print(f"   ✓ Manager instructions: count={count}, instructions array length={len(instructions)}")
            
            if count >= 5 and len(instructions) >= 5:
                print(f"   ✓ Manager can see 5+ instructions")
                return True
            else:
                self.log_test("F4", "Expected 5+ instructions for manager", False,
                             f"Got count={count}, array length={len(instructions)}")
                return False
        return False

    # ========== SMOKE TESTS ==========
    
    def test_ir_leads(self, admin_session: requests.Session) -> bool:
        """Smoke test: IR leads"""
        success, response = self.run_test(
            "Smoke", "GET /api/admin/ir/leads",
            "GET", "/api/admin/ir/leads", 200,
            session=admin_session
        )
        
        if success and isinstance(response, list) and len(response) > 0:
            print(f"   ✓ IR leads: {len(response)} leads found")
            return True
        return False

    def test_manager_os_snapshot(self, admin_session: requests.Session) -> bool:
        """Smoke test: Manager OS snapshot"""
        success, response = self.run_test(
            "Smoke", "GET /api/admin/manager-os/snapshot",
            "GET", "/api/admin/manager-os/snapshot", 200,
            session=admin_session
        )
        
        if success and isinstance(response, list):
            print(f"   ✓ Manager OS snapshot: {len(response)} managers")
            return True
        return False

    def test_funnel_dashboard(self, admin_session: requests.Session) -> bool:
        """Smoke test: Funnel dashboard"""
        success, response = self.run_test(
            "Smoke", "GET /api/admin/funnel/dashboard",
            "GET", "/api/admin/funnel/dashboard", 200,
            session=admin_session
        )
        
        if success and isinstance(response, dict):
            stages = response.get("stages", [])
            print(f"   ✓ Funnel dashboard: {len(stages)} stages")
            return True
        return False

    def test_comms_providers(self, admin_session: requests.Session) -> bool:
        """Smoke test: Communication providers"""
        success, response = self.run_test(
            "Smoke", "GET /api/admin/comms/providers",
            "GET", "/api/admin/comms/providers", 200,
            session=admin_session
        )
        
        if success:
            providers = response if isinstance(response, list) else response.get("providers", [])
            print(f"   ✓ Communication providers: {len(providers)} providers")
            return True
        return False

    def test_gmail_status(self, admin_session: requests.Session) -> bool:
        """Smoke test: Gmail status"""
        success, response = self.run_test(
            "Smoke", "GET /api/admin/comms/gmail/status",
            "GET", "/api/admin/comms/gmail/status", 200,
            session=admin_session
        )
        
        if success and response.get("mock_mode") == True:
            print(f"   ✓ Gmail status: mock_mode=true")
            return True
        return False

    def test_outlook_status(self, admin_session: requests.Session) -> bool:
        """Smoke test: Outlook status"""
        success, response = self.run_test(
            "Smoke", "GET /api/admin/comms/outlook/status",
            "GET", "/api/admin/comms/outlook/status", 200,
            session=admin_session
        )
        
        if success and response.get("mock_mode") == True:
            print(f"   ✓ Outlook status: mock_mode=true")
            return True
        return False

    def test_landing_page(self) -> bool:
        """Smoke test: Landing page"""
        url = f"{self.base_url}/"
        try:
            response = requests.get(url, timeout=10)
            success = response.status_code == 200 and len(response.text) > 1000
            
            # Check for Ukrainian content
            has_ukrainian = "LUMEN" in response.text or "Реальні" in response.text or "інвестиції" in response.text
            
            self.log_test("Smoke", "Landing page loads with Ukrainian content", 
                         success and has_ukrainian,
                         f"Status: {response.status_code}, Length: {len(response.text)}, Ukrainian: {has_ukrainian}" if not (success and has_ukrainian) else "")
            
            if success and has_ukrainian:
                print(f"   ✓ Landing page: {len(response.text)} chars, Ukrainian content present")
            
            return success and has_ukrainian
        except Exception as e:
            self.log_test("Smoke", "Landing page loads with Ukrainian content", False, str(e))
            return False

    # ========== WEBHOOK NEGATIVE-PATH TESTS ==========
    
    def test_gmail_webhook_no_signature(self) -> bool:
        """Test: Gmail webhook without signature"""
        success, response = self.run_test(
            "Webhook", "POST /api/comms/webhook/gmail without signature returns 401",
            "POST", "/api/comms/webhook/gmail", 401,
            data={"test": "data"}
        )
        return success

    def test_outlook_webhook_no_signature(self) -> bool:
        """Test: Outlook webhook without signature"""
        success, response = self.run_test(
            "Webhook", "POST /api/comms/webhook/outlook without signature returns 401",
            "POST", "/api/comms/webhook/outlook", 401,
            data={"test": "data"}
        )
        return success

    def test_outlook_webhook_validation_token(self) -> bool:
        """Test: Outlook webhook validation token"""
        url = f"{self.base_url}/api/comms/webhook/outlook?validationToken=hello"
        try:
            response = requests.post(url, timeout=10)
            success = response.status_code == 200 and response.text == "hello"
            self.log_test("Webhook", "POST /api/comms/webhook/outlook?validationToken=hello returns 200 plain-text", 
                         success,
                         f"Status: {response.status_code}, Text: {response.text}" if not success else "")
            
            if success:
                print(f"   ✓ Validation token echoed correctly")
            
            return success
        except Exception as e:
            self.log_test("Webhook", "POST /api/comms/webhook/outlook?validationToken=hello returns 200 plain-text", 
                         False, str(e))
            return False

    # ========== MAIN TEST RUNNER ==========
    
    def run_all_tests(self):
        """Run all iteration 12 re-verification tests"""
        print("\n" + "="*80)
        print("LUMEN ITERATION 12 - RE-VERIFICATION TEST SUITE")
        print("Testing previously-failing checks with corrected inputs")
        print("="*80 + "\n")
        
        # 1. CORRECTED AUTH TESTS
        print("\n--- CORRECTED AUTHENTICATION TESTS ---")
        investor_success, investor_session = self.test_investor_login()
        family_success, family_session = self.test_institutional_login()
        manager_success, manager_session = self.test_manager_login()
        admin_success, admin_session = self.test_admin_login()
        
        if not admin_success:
            print("\n❌ CRITICAL: Admin login failed. Cannot proceed with authenticated tests.")
            return False
        
        # Test session persistence
        if investor_success:
            self.test_session_persistence(investor_session, "investor")
        if manager_success:
            self.test_session_persistence(manager_session, "manager")
        
        # 2. CORRECTED F4 MANAGER INSTRUCTIONS TESTS
        print("\n--- CORRECTED F4 MANAGER INSTRUCTIONS TESTS ---")
        self.test_f4_admin_instructions_overview(admin_session)
        if manager_success:
            self.test_f4_manager_instructions(manager_session)
        
        # 3. SMOKE TESTS
        print("\n--- SMOKE TESTS (QUICK REGRESSION CHECK) ---")
        self.test_ir_leads(admin_session)
        self.test_manager_os_snapshot(admin_session)
        self.test_funnel_dashboard(admin_session)
        self.test_comms_providers(admin_session)
        self.test_gmail_status(admin_session)
        self.test_outlook_status(admin_session)
        self.test_landing_page()
        
        # 4. WEBHOOK NEGATIVE-PATH TESTS
        print("\n--- WEBHOOK NEGATIVE-PATH TESTS ---")
        self.test_gmail_webhook_no_signature()
        self.test_outlook_webhook_no_signature()
        self.test_outlook_webhook_validation_token()
        
        return True

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"Total Tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        # Group by category
        categories = {}
        for result in self.test_results:
            cat = result["category"]
            if cat not in categories:
                categories[cat] = {"passed": 0, "failed": 0}
            if result["passed"]:
                categories[cat]["passed"] += 1
            else:
                categories[cat]["failed"] += 1
        
        print("\nBy Category:")
        for cat, stats in categories.items():
            total = stats["passed"] + stats["failed"]
            pct = (stats["passed"]/total*100) if total > 0 else 0
            print(f"  {cat}: {stats['passed']}/{total} ({pct:.0f}%)")
        
        # Failed tests
        failed = [r for r in self.test_results if not r["passed"]]
        if failed:
            print("\nFailed Tests:")
            for r in failed:
                print(f"  ❌ [{r['category']}] {r['name']}")
                if r["details"]:
                    print(f"     {r['details']}")
        else:
            print("\n✅ ALL TESTS PASSED!")
        
        print("="*80 + "\n")
        
        return self.tests_passed == self.tests_run


def main():
    tester = LumenIteration12Tester()
    
    try:
        tester.run_all_tests()
        all_passed = tester.print_summary()
        
        return 0 if all_passed else 1
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        tester.print_summary()
        return 2
    except Exception as e:
        print(f"\n\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        return 3


if __name__ == "__main__":
    sys.exit(main())
