#!/usr/bin/env python3
"""
Sprint 6 Backend API Validation
Quick validation of payment/funding/ledger endpoints
"""
import requests
import sys

BASE_URL = "https://full-setup-3.preview.emergentagent.com/api"

class Sprint6Tester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.admin_token = None
        self.investor_token = None
        
    def log(self, msg, level="INFO"):
        prefix = {"INFO": "ℹ️", "PASS": "✅", "FAIL": "❌"}.get(level, "•")
        print(f"{prefix} {msg}")
    
    def test(self, name, method, endpoint, expected_status, cookies=None):
        """Run a single test"""
        url = f"{BASE_URL}/{endpoint}"
        self.tests_run += 1
        self.log(f"Test #{self.tests_run}: {name}", "INFO")
        
        try:
            if method == 'GET':
                response = requests.get(url, cookies=cookies, timeout=10)
            else:
                response = requests.post(url, json={}, cookies=cookies, timeout=10)
            
            if response.status_code == expected_status:
                self.tests_passed += 1
                self.log(f"PASSED - Status: {response.status_code}", "PASS")
                return True, response.json() if response.text else {}
            else:
                self.log(f"FAILED - Expected {expected_status}, got {response.status_code}", "FAIL")
                try:
                    print(f"   Error: {response.json().get('detail', response.text[:200])}")
                except:
                    print(f"   Response: {response.text[:200]}")
                return False, {}
        except Exception as e:
            self.log(f"FAILED - Error: {str(e)}", "FAIL")
            return False, {}
    
    def auth_quick(self, email):
        """Quick login"""
        url = f"{BASE_URL}/auth/quick"
        try:
            response = requests.post(url, json={"email": email}, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return response.cookies.get_dict()
            return None
        except:
            return None
    
    def run(self):
        print("\n" + "="*60)
        print("Sprint 6 Backend API Validation")
        print("="*60 + "\n")
        
        # Auth
        self.log("Authenticating as admin@atlas.dev...", "INFO")
        admin_cookies = self.auth_quick("admin@atlas.dev")
        if not admin_cookies:
            self.log("Admin auth failed", "FAIL")
            return 1
        self.log("Admin authenticated", "PASS")
        
        self.log("Authenticating as client@atlas.dev...", "INFO")
        investor_cookies = self.auth_quick("client@atlas.dev")
        if not investor_cookies:
            self.log("Investor auth failed", "FAIL")
            return 1
        self.log("Investor authenticated", "PASS")
        
        print("\n--- Admin Endpoints ---")
        self.test("GET /api/admin/payments", "GET", "admin/payments", 200, admin_cookies)
        self.test("GET /api/admin/ledger", "GET", "admin/ledger", 200, admin_cookies)
        self.test("GET /api/admin/funding-accounts", "GET", "admin/funding-accounts", 200, admin_cookies)
        
        print("\n--- Public Endpoints ---")
        self.test("GET /api/funding-accounts/public", "GET", "funding-accounts/public", 200)
        
        print("\n--- Investor Endpoints ---")
        self.test("GET /api/investor/payments", "GET", "investor/payments", 200, investor_cookies)
        self.test("GET /api/investor/payments?status=confirmed", "GET", "investor/payments?status=confirmed", 200, investor_cookies)
        self.test("GET /api/investor/notifications", "GET", "investor/notifications", 200, investor_cookies)
        
        # Summary
        print("\n" + "="*60)
        print(f"Tests Run: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {self.tests_run - self.tests_passed}")
        print("="*60 + "\n")
        
        return 0 if self.tests_passed == self.tests_run else 1

if __name__ == "__main__":
    tester = Sprint6Tester()
    sys.exit(tester.run())
