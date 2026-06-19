"""
LUMEN Deployment Verification — Backend API Tests
Tests health, public assets, public OTC, auth flows, and investor portfolio.
"""
import requests
import sys
import time
from datetime import datetime

BASE_URL = "https://web-expo-app.preview.emergentagent.com/api"
OPERATOR_EMAIL = "operator@atlas.dev"
OPERATOR_PASSWORD = "operator123"
MANAGER_EMAIL = "manager@atlas.dev"
MANAGER_PASSWORD = "manager123"

class LumenDeploymentTester:
    def __init__(self):
        self.session = requests.Session()
        self.tests_run = 0
        self.tests_passed = 0
        self.demo_session = None
        self.operator_session = None
        self.test_listing_id = None

    def log(self, msg, status="INFO"):
        prefix = {
            "PASS": "✅",
            "FAIL": "❌",
            "INFO": "🔍",
            "WARN": "⚠️"
        }.get(status, "ℹ️")
        print(f"{prefix} {msg}")

    def test(self, name, method, endpoint, expected_status, data=None, json_data=None, check_fn=None, session=None):
        """Run a single API test"""
        url = f"{BASE_URL}/{endpoint}"
        self.tests_run += 1
        self.log(f"Testing {name}...", "INFO")
        
        # Use provided session or default
        req_session = session if session else self.session
        
        try:
            if method == 'GET':
                response = req_session.get(url)
            elif method == 'POST':
                if json_data is not None:
                    response = req_session.post(url, json=json_data)
                else:
                    response = req_session.post(url, data=data)
            elif method == 'DELETE':
                response = req_session.delete(url)
            else:
                raise ValueError(f"Unsupported method: {method}")

            # Check status code
            if response.status_code != expected_status:
                self.log(f"FAILED - Expected {expected_status}, got {response.status_code}", "FAIL")
                self.log(f"Response: {response.text[:500]}", "FAIL")
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

    def test_health_endpoints(self):
        """Test health and readiness endpoints"""
        self.log("=" * 60, "INFO")
        self.log("TEST 1: Health Endpoints", "INFO")
        self.log("=" * 60, "INFO")
        
        # Test /api/healthz
        def check_healthz(data):
            if data.get("status") != "ok":
                self.log("FAILED: healthz status is not 'ok'", "FAIL")
                return False
            return True
        
        success1, _ = self.test(
            "GET /api/healthz",
            "GET",
            "healthz",
            200,
            check_fn=check_healthz
        )
        
        # Test /api/readyz
        def check_readyz(data):
            if not data.get("ready"):
                self.log("FAILED: readyz ready is not true", "FAIL")
                return False
            checks = data.get("checks", {})
            if not checks.get("mongo"):
                self.log("FAILED: mongo check failed", "FAIL")
                return False
            if not checks.get("config"):
                self.log("FAILED: config check failed", "FAIL")
                return False
            return True
        
        success2, _ = self.test(
            "GET /api/readyz",
            "GET",
            "readyz",
            200,
            check_fn=check_readyz
        )
        
        return success1 and success2

    def test_public_assets(self):
        """Test GET /api/assets - public asset list"""
        self.log("=" * 60, "INFO")
        self.log("TEST 2: Public Assets", "INFO")
        self.log("=" * 60, "INFO")
        
        def check_assets(data):
            assets = data.get("assets", [])
            if not assets:
                self.log("WARNING: No assets found (may be empty)", "WARN")
                return True  # Empty is valid
            
            self.log(f"Found {len(assets)} asset(s)", "INFO")
            
            # Check first asset structure
            first = assets[0]
            required_fields = ["id", "title", "category", "location"]
            for field in required_fields:
                if field not in first:
                    self.log(f"FAILED: Missing asset.{field}", "FAIL")
                    return False
            
            self.log(f"Asset structure OK: {first.get('title')}", "PASS")
            return True
        
        success, resp = self.test(
            "GET /api/assets",
            "GET",
            "assets",
            200,
            check_fn=check_assets
        )
        
        return success

    def test_public_otc_listings(self):
        """Test GET /api/public/otc/listings - public OTC marketplace"""
        self.log("=" * 60, "INFO")
        self.log("TEST 3: Public OTC Listings", "INFO")
        self.log("=" * 60, "INFO")
        
        def check_listings(data):
            listings = data.get("listings", [])
            if not listings:
                self.log("WARNING: No OTC listings found (market may be empty)", "WARN")
                return True  # Empty market is valid
            
            self.log(f"Found {len(listings)} listing(s)", "INFO")
            
            # Check first listing structure
            first = listings[0]
            
            # Check for asset enrichment
            if "asset" not in first:
                self.log("FAILED: Missing 'asset' enrichment", "FAIL")
                return False
            
            asset = first["asset"]
            required_asset_fields = ["id", "title", "location", "category"]
            for field in required_asset_fields:
                if field not in asset:
                    self.log(f"FAILED: Missing asset.{field}", "FAIL")
                    return False
            
            self.log(f"Asset enrichment OK: {asset.get('title')}", "PASS")
            
            # Check for metrics enrichment
            if "metrics" not in first:
                self.log("FAILED: Missing 'metrics' enrichment", "FAIL")
                return False
            
            metrics = first["metrics"]
            self.log(f"Metrics enrichment OK: share={metrics.get('share_percent')}%", "PASS")
            
            # Store first listing ID for detail test
            self.test_listing_id = first.get("id")
            self.log(f"Stored listing ID: {self.test_listing_id}", "INFO")
            
            return True
        
        success, resp = self.test(
            "GET /api/public/otc/listings",
            "GET",
            "public/otc/listings",
            200,
            check_fn=check_listings
        )
        
        return success

    def test_public_otc_listing_detail(self):
        """Test GET /api/public/otc/listings/{id} - lot detail with payout history"""
        self.log("=" * 60, "INFO")
        self.log("TEST 4: Public OTC Lot Detail", "INFO")
        self.log("=" * 60, "INFO")
        
        if not self.test_listing_id:
            self.log("SKIPPED: No listing ID available", "WARN")
            return True
        
        def check_detail(data):
            listing = data.get("listing")
            if not listing:
                self.log("FAILED: No listing in response", "FAIL")
                return False
            
            # Check asset enrichment
            if "asset" not in listing:
                self.log("FAILED: Missing 'asset' enrichment", "FAIL")
                return False
            
            # Check metrics enrichment
            if "metrics" not in listing:
                self.log("FAILED: Missing 'metrics' enrichment", "FAIL")
                return False
            
            # Check payout_history
            if "payout_history" not in listing:
                self.log("FAILED: Missing 'payout_history'", "FAIL")
                return False
            
            history = listing["payout_history"]
            if not isinstance(history, list):
                self.log("FAILED: payout_history is not a list", "FAIL")
                return False
            
            self.log(f"Payout history OK: {len(history)} points", "PASS")
            self.log(f"Lot detail fully enriched: {listing['asset'].get('title')}", "PASS")
            
            return True
        
        success, resp = self.test(
            f"GET /api/public/otc/listings/{self.test_listing_id}",
            "GET",
            f"public/otc/listings/{self.test_listing_id}",
            200,
            check_fn=check_detail
        )
        
        return success

    def test_auth_demo(self):
        """Test POST /api/auth/demo - instant demo session"""
        self.log("=" * 60, "INFO")
        self.log("TEST 5: Auth Demo Session", "INFO")
        self.log("=" * 60, "INFO")
        
        # Create a new session for demo
        self.demo_session = requests.Session()
        
        def check_demo(data):
            if not data.get("ok"):
                self.log("FAILED: Response 'ok' is not True", "FAIL")
                return False
            
            user = data.get("user")
            if not user:
                self.log("FAILED: No 'user' in response", "FAIL")
                return False
            
            if not user.get("user_id"):
                self.log("FAILED: No user_id in user", "FAIL")
                return False
            
            self.log(f"Demo user created: {user.get('user_id')}", "PASS")
            
            # Check for session cookie
            cookies = self.demo_session.cookies.get_dict()
            if 'session_token' not in cookies:
                self.log("WARNING: No session_token cookie set", "WARN")
            else:
                self.log("Session cookie set", "PASS")
            
            return True
        
        success, resp = self.test(
            "POST /api/auth/demo",
            "POST",
            "auth/demo",
            200,
            json_data={},
            check_fn=check_demo,
            session=self.demo_session
        )
        
        return success

    def test_auth_me_with_demo(self):
        """Test GET /api/auth/me with demo session cookie"""
        self.log("=" * 60, "INFO")
        self.log("TEST 6: Auth Me (with demo session)", "INFO")
        self.log("=" * 60, "INFO")
        
        if not self.demo_session:
            self.log("SKIPPED: No demo session available", "WARN")
            return True
        
        def check_me(data):
            if not data.get("user_id"):
                self.log("FAILED: No user_id in response", "FAIL")
                return False
            
            self.log(f"Auth me OK: {data.get('user_id')}", "PASS")
            return True
        
        success, resp = self.test(
            "GET /api/auth/me",
            "GET",
            "auth/me",
            200,
            check_fn=check_me,
            session=self.demo_session
        )
        
        return success

    def test_investor_portfolio_with_demo(self):
        """Test GET /api/investor/portfolio with demo session"""
        self.log("=" * 60, "INFO")
        self.log("TEST 7: Investor Portfolio (with demo session)", "INFO")
        self.log("=" * 60, "INFO")
        
        if not self.demo_session:
            self.log("SKIPPED: No demo session available", "WARN")
            return True
        
        def check_portfolio(data):
            # Portfolio may be empty for new demo user
            self.log("Portfolio endpoint accessible", "PASS")
            return True
        
        success, resp = self.test(
            "GET /api/investor/portfolio",
            "GET",
            "investor/portfolio",
            200,
            check_fn=check_portfolio,
            session=self.demo_session
        )
        
        return success

    def test_operator_login(self):
        """Test POST /api/auth/login with operator credentials"""
        self.log("=" * 60, "INFO")
        self.log("TEST 8: Operator Login", "INFO")
        self.log("=" * 60, "INFO")
        
        # Create a new session for operator
        self.operator_session = requests.Session()
        
        def check_login(data):
            # Check for user_id or user object
            user_id = data.get("user_id") or (data.get("user") or {}).get("user_id")
            if not user_id:
                self.log("FAILED: No user_id in response", "FAIL")
                return False
            
            self.log(f"Operator logged in: {user_id}", "PASS")
            
            # Check for session cookie
            cookies = self.operator_session.cookies.get_dict()
            if 'session_token' not in cookies:
                self.log("WARNING: No session_token cookie set", "WARN")
            else:
                self.log("Session cookie set", "PASS")
            
            return True
        
        success, resp = self.test(
            "POST /api/auth/login",
            "POST",
            "auth/login",
            200,
            json_data={"email": OPERATOR_EMAIL, "password": OPERATOR_PASSWORD},
            check_fn=check_login,
            session=self.operator_session
        )
        
        return success

    def run_all_tests(self):
        """Run all deployment verification tests"""
        self.log("=" * 60, "INFO")
        self.log("LUMEN DEPLOYMENT VERIFICATION — BACKEND API TESTS", "INFO")
        self.log("=" * 60, "INFO")
        self.log(f"Base URL: {BASE_URL}", "INFO")
        self.log(f"Operator: {OPERATOR_EMAIL}", "INFO")
        self.log("", "INFO")
        
        # Run tests in order
        self.test_health_endpoints()
        self.test_public_assets()
        self.test_public_otc_listings()
        self.test_public_otc_listing_detail()
        self.test_auth_demo()
        self.test_auth_me_with_demo()
        self.test_investor_portfolio_with_demo()
        self.test_operator_login()
        
        # Summary
        self.log("", "INFO")
        self.log("=" * 60, "INFO")
        self.log("TEST SUMMARY", "INFO")
        self.log("=" * 60, "INFO")
        self.log(f"Tests Run: {self.tests_run}", "INFO")
        self.log(f"Tests Passed: {self.tests_passed}", "PASS" if self.tests_passed == self.tests_run else "FAIL")
        self.log(f"Tests Failed: {self.tests_run - self.tests_passed}", "FAIL" if self.tests_passed < self.tests_run else "INFO")
        self.log(f"Success Rate: {(self.tests_passed / self.tests_run * 100):.1f}%", "INFO")
        
        return self.tests_passed == self.tests_run

def main():
    tester = LumenDeploymentTester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
