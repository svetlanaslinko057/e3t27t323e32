"""
LUMEN Production Hardening — Backend API Tests
Tests watchlist auto-refresh, SOP runbooks, and production switch endpoints.
"""
import requests
import sys
import time
from datetime import datetime

BASE_URL = "https://dev-setup-30.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@devos.io"
ADMIN_PASSWORD = "admin123"

RUNBOOKS = ["funding_failure", "withdrawal_failure", "reconciliation_failure",
            "kyc_escalation", "sanctions_hit", "payout_incident"]

class ProductionHardeningTester:
    def __init__(self):
        self.session = requests.Session()
        self.tests_run = 0
        self.tests_passed = 0

    def log(self, msg, status="INFO"):
        prefix = {
            "PASS": "✅",
            "FAIL": "❌",
            "INFO": "🔍",
            "WARN": "⚠️"
        }.get(status, "ℹ️")
        print(f"{prefix} {msg}")

    def test(self, name, method, endpoint, expected_status, data=None, json_data=None, check_fn=None):
        """Run a single API test"""
        url = f"{BASE_URL}/{endpoint}"
        self.tests_run += 1
        self.log(f"Testing {name}...", "INFO")
        
        try:
            if method == 'GET':
                response = self.session.get(url, timeout=30)
            elif method == 'POST':
                if json_data is not None:
                    response = self.session.post(url, json=json_data, timeout=30)
                else:
                    response = self.session.post(url, data=data, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")

            # Check status code
            if response.status_code != expected_status:
                self.log(f"FAILED - Expected {expected_status}, got {response.status_code}", "FAIL")
                self.log(f"Response: {response.text[:300]}", "FAIL")
                return False, {}

            # Parse JSON response
            try:
                resp_data = response.json()
            except:
                resp_data = {}

            # Run custom check function
            if check_fn and not check_fn(resp_data):
                self.log(f"FAILED - Custom check failed", "FAIL")
                return False, resp_data

            self.tests_passed += 1
            self.log(f"PASSED - Status: {response.status_code}", "PASS")
            return True, resp_data

        except Exception as e:
            self.log(f"FAILED - Error: {str(e)}", "FAIL")
            return False, {}

    def test_login(self):
        """Test admin login"""
        self.log("=" * 70, "INFO")
        self.log("TEST 1: Admin Login", "INFO")
        self.log("=" * 70, "INFO")
        
        success, resp = self.test(
            "Admin Login",
            "POST",
            "auth/login",
            200,
            json_data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        
        if success:
            self.log(f"Admin logged in: {ADMIN_EMAIL}", "INFO")
        
        return success

    def test_watchlist_refresh(self):
        """Test POST /api/admin/compliance/watchlist/refresh"""
        self.log("=" * 70, "INFO")
        self.log("TEST 2: Watchlist Auto-Refresh (Real OFAC Fetch)", "INFO")
        self.log("=" * 70, "INFO")
        
        def check_refresh(data):
            status = data.get("status")
            inserted = data.get("inserted", 0)
            watchlist_total = data.get("watchlist_total", 0)
            
            self.log(f"Status: {status}", "INFO")
            self.log(f"Inserted: {inserted}", "INFO")
            self.log(f"Watchlist total: {watchlist_total}", "INFO")
            
            # Status should be 'ok' or 'fallback'
            if status not in ("ok", "fallback"):
                self.log(f"Invalid status: {status}", "FAIL")
                return False
            
            # If status is 'ok', inserted should be in hundreds/thousands
            if status == "ok" and inserted < 100:
                self.log(f"Expected hundreds/thousands of entries for 'ok' status, got {inserted}", "FAIL")
                return False
            
            # Watchlist total should be non-zero
            if watchlist_total == 0:
                self.log("Watchlist total is 0", "FAIL")
                return False
            
            return True
        
        success, resp = self.test(
            "Watchlist Refresh",
            "POST",
            "admin/compliance/watchlist/refresh",
            200,
            check_fn=check_refresh
        )
        
        return success

    def test_watchlist_refresh_status(self):
        """Test GET /api/admin/compliance/watchlist/refresh-status"""
        self.log("=" * 70, "INFO")
        self.log("TEST 3: Watchlist Refresh Status", "INFO")
        self.log("=" * 70, "INFO")
        
        def check_status(data):
            last_refresh = data.get("last_refresh")
            auto_fetched_count = data.get("auto_fetched_count", 0)
            seed_manual_count = data.get("seed_manual_count", 0)
            history = data.get("history", [])
            
            self.log(f"Auto-fetched count: {auto_fetched_count}", "INFO")
            self.log(f"Seed/manual count: {seed_manual_count}", "INFO")
            self.log(f"History entries: {len(history)}", "INFO")
            
            # Seed/manual count should be >= 5 (seeded entries preserved)
            if seed_manual_count < 5:
                self.log(f"Expected seed_manual_count >= 5, got {seed_manual_count}", "FAIL")
                return False
            
            # Last refresh should exist
            if not last_refresh:
                self.log("No last_refresh found", "FAIL")
                return False
            
            self.log(f"Last refresh: status={last_refresh.get('status')}, at={last_refresh.get('at_iso')}", "INFO")
            
            return True
        
        success, resp = self.test(
            "Watchlist Refresh Status",
            "GET",
            "admin/compliance/watchlist/refresh-status",
            200,
            check_fn=check_status
        )
        
        return success

    def test_watchlist_entries(self):
        """Test GET /api/admin/compliance/watchlist"""
        self.log("=" * 70, "INFO")
        self.log("TEST 4: Watchlist Entries (by_source)", "INFO")
        self.log("=" * 70, "INFO")
        
        def check_entries(data):
            items = data.get("items", [])
            by_source = data.get("by_source", {})
            
            self.log(f"Total items: {len(items)}", "INFO")
            self.log(f"By source: {by_source}", "INFO")
            
            # Should have entries
            if len(items) == 0:
                self.log("No watchlist entries found", "FAIL")
                return False
            
            # Should have by_source breakdown
            if not by_source:
                self.log("No by_source breakdown", "FAIL")
                return False
            
            # Check for expected sources (ofac, eu, uk, ua_nsdc, pep)
            expected_sources = ["ofac", "eu", "uk", "ua_nsdc", "pep"]
            found_sources = [s for s in expected_sources if s in by_source]
            self.log(f"Found sources: {found_sources}", "INFO")
            
            return True
        
        success, resp = self.test(
            "Watchlist Entries",
            "GET",
            "admin/compliance/watchlist?limit=100",
            200,
            check_fn=check_entries
        )
        
        return success

    def test_sop_list(self):
        """Test GET /api/admin/sop"""
        self.log("=" * 70, "INFO")
        self.log("TEST 5: SOP List (11 SOPs including 6 incident runbooks)", "INFO")
        self.log("=" * 70, "INFO")
        
        def check_sop_list(data):
            items = data.get("items", [])
            count = data.get("count", 0)
            
            self.log(f"Total SOPs: {count}", "INFO")
            
            # Should have 11 SOPs
            if count < 11:
                self.log(f"Expected 11 SOPs, got {count}", "FAIL")
                return False
            
            # Check for the 6 incident runbooks
            keys = {item.get("key") for item in items}
            missing_runbooks = [rb for rb in RUNBOOKS if rb not in keys]
            
            if missing_runbooks:
                self.log(f"Missing runbooks: {missing_runbooks}", "FAIL")
                return False
            
            self.log(f"All 6 incident runbooks present: {RUNBOOKS}", "PASS")
            
            return True
        
        success, resp = self.test(
            "SOP List",
            "GET",
            "admin/sop",
            200,
            check_fn=check_sop_list
        )
        
        return success

    def test_sop_runbooks(self):
        """Test GET /api/admin/sop/{key} for each runbook"""
        self.log("=" * 70, "INFO")
        self.log("TEST 6: Individual SOP Runbooks", "INFO")
        self.log("=" * 70, "INFO")
        
        all_passed = True
        for runbook_key in RUNBOOKS:
            def check_runbook(data):
                key = data.get("key")
                title = data.get("title")
                body = data.get("body")
                
                if key != runbook_key:
                    self.log(f"Key mismatch: expected {runbook_key}, got {key}", "FAIL")
                    return False
                
                if not title:
                    self.log(f"No title for {runbook_key}", "FAIL")
                    return False
                
                if not body:
                    self.log(f"No body for {runbook_key}", "FAIL")
                    return False
                
                self.log(f"Runbook {runbook_key}: title='{title}', body_length={len(body)}", "INFO")
                return True
            
            success, resp = self.test(
                f"SOP Runbook: {runbook_key}",
                "GET",
                f"admin/sop/{runbook_key}",
                200,
                check_fn=check_runbook
            )
            
            if not success:
                all_passed = False
        
        return all_passed

    def test_production_switch(self):
        """Test GET /api/admin/launch-readiness/production-switch"""
        self.log("=" * 70, "INFO")
        self.log("TEST 7: Production Switch Status", "INFO")
        self.log("=" * 70, "INFO")
        
        def check_switch(data):
            env = data.get("env")
            is_production = data.get("is_production")
            controls = data.get("controls", {})
            
            self.log(f"Environment: {env}", "INFO")
            self.log(f"Is production: {is_production}", "INFO")
            self.log(f"Controls: {controls}", "INFO")
            
            # Should have env and is_production
            if env is None or is_production is None:
                self.log("Missing env or is_production", "FAIL")
                return False
            
            # Should have controls
            expected_controls = ["quick_access_login_enabled", "demo_seeders_enabled"]
            for ctrl in expected_controls:
                if ctrl not in controls:
                    self.log(f"Missing control: {ctrl}", "FAIL")
                    return False
            
            return True
        
        success, resp = self.test(
            "Production Switch",
            "GET",
            "admin/launch-readiness/production-switch",
            200,
            check_fn=check_switch
        )
        
        return success

    def test_auth_gating(self):
        """Test auth gating - endpoints should return 401/403 without auth"""
        self.log("=" * 70, "INFO")
        self.log("TEST 8: Auth Gating (Unauthenticated)", "INFO")
        self.log("=" * 70, "INFO")
        
        # Use a session without cookies
        no_auth_session = requests.Session()
        
        endpoints = [
            "admin/compliance/watchlist/refresh",
            "admin/compliance/watchlist/refresh-status",
            "admin/compliance/watchlist",
            "admin/sop",
            "admin/launch-readiness/production-switch",
        ]
        
        all_passed = True
        for endpoint in endpoints:
            try:
                if endpoint == "admin/compliance/watchlist/refresh":
                    resp = no_auth_session.post(f"{BASE_URL}/{endpoint}", timeout=10)
                else:
                    resp = no_auth_session.get(f"{BASE_URL}/{endpoint}", timeout=10)
                
                if resp.status_code in [401, 403]:
                    self.log(f"✓ {endpoint}: {resp.status_code}", "PASS")
                else:
                    self.log(f"✗ {endpoint}: Expected 401/403, got {resp.status_code}", "FAIL")
                    all_passed = False
            except Exception as e:
                self.log(f"✗ {endpoint}: Error {e}", "FAIL")
                all_passed = False
        
        self.tests_run += 1
        if all_passed:
            self.tests_passed += 1
        
        return all_passed

    def run_all_tests(self):
        """Run all tests in order"""
        print("\n" + "=" * 70)
        print("LUMEN PRODUCTION HARDENING - BACKEND API TESTS")
        print("=" * 70 + "\n")
        
        tests = [
            ("Admin Login", self.test_login),
            ("Watchlist Auto-Refresh", self.test_watchlist_refresh),
            ("Watchlist Refresh Status", self.test_watchlist_refresh_status),
            ("Watchlist Entries", self.test_watchlist_entries),
            ("SOP List", self.test_sop_list),
            ("SOP Runbooks", self.test_sop_runbooks),
            ("Production Switch", self.test_production_switch),
            ("Auth Gating", self.test_auth_gating),
        ]
        
        for name, test_fn in tests:
            try:
                test_fn()
            except Exception as e:
                self.log(f"Test '{name}' crashed: {e}", "FAIL")
                self.tests_run += 1
            print()  # Blank line between tests
        
        # Print summary
        print("=" * 70)
        print(f"TESTS COMPLETED: {self.tests_passed}/{self.tests_run} passed")
        print("=" * 70)
        
        return 0 if self.tests_passed == self.tests_run else 1


def main():
    tester = ProductionHardeningTester()
    return tester.run_all_tests()


if __name__ == "__main__":
    sys.exit(main())
