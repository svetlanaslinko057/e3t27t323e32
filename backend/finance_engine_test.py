"""
LUMEN Finance Engine Backend Tests (D1+D2+D3)
Tests FX rates, Tax config/preview/liability, and Dividend Scheduler endpoints.
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://dev-setup-30.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@devos.io"
ADMIN_PASSWORD = "admin123"
ASSET_ID = "asset-podilskyi"

class FinanceEngineTester:
    def __init__(self):
        self.session = requests.Session()
        self.tests_run = 0
        self.tests_passed = 0

    def log(self, msg, status="INFO"):
        prefix = {"PASS": "✅", "FAIL": "❌", "INFO": "🔍"}.get(status, "ℹ️")
        print(f"{prefix} {msg}")

    def test(self, name, method, endpoint, expected_status, json_data=None, check_fn=None):
        """Run a single API test"""
        url = f"{BASE_URL}/{endpoint}"
        self.tests_run += 1
        self.log(f"Testing {name}...", "INFO")
        
        try:
            if method == 'GET':
                response = self.session.get(url)
            elif method == 'POST':
                response = self.session.post(url, json=json_data or {})
            elif method == 'PUT':
                response = self.session.put(url, json=json_data or {})
            else:
                raise ValueError(f"Unsupported method: {method}")

            if response.status_code != expected_status:
                self.log(f"FAILED - Expected {expected_status}, got {response.status_code}", "FAIL")
                self.log(f"Response: {response.text[:300]}", "FAIL")
                return False, {}

            try:
                resp_data = response.json()
            except:
                resp_data = {}

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
        self.log("TEST: Admin Login", "INFO")
        self.log("=" * 70, "INFO")
        
        success, resp = self.test(
            "Admin Login",
            "POST",
            "auth/login",
            200,
            json_data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        
        if success:
            cookies = self.session.cookies.get_dict()
            if 'session_token' in cookies:
                self.log(f"Session cookie set", "PASS")
            else:
                self.log("WARNING: No session_token cookie found", "FAIL")
                return False
        
        return success

    def test_fx_rates(self):
        """Test GET /api/admin/fx/rates"""
        self.log("=" * 70, "INFO")
        self.log("TEST: FX Rates (D3)", "INFO")
        self.log("=" * 70, "INFO")
        
        def check_fx(data):
            rates = data.get("rates", {})
            meta = data.get("meta", {})
            
            usd = rates.get("USD", 0)
            eur = rates.get("EUR", 0)
            source = meta.get("source")
            
            self.log(f"USD rate: {usd}", "INFO")
            self.log(f"EUR rate: {eur}", "INFO")
            self.log(f"Source: {source}", "INFO")
            
            if usd <= 0:
                self.log("USD rate must be > 0", "FAIL")
                return False
            if eur <= 0:
                self.log("EUR rate must be > 0", "FAIL")
                return False
            if not source:
                self.log("meta.source must be present", "FAIL")
                return False
            
            return True
        
        return self.test("FX Rates", "GET", "admin/fx/rates", 200, check_fn=check_fx)[0]

    def test_fx_refresh(self):
        """Test POST /api/admin/fx/refresh"""
        self.log("=" * 70, "INFO")
        self.log("TEST: FX Refresh (D3)", "INFO")
        self.log("=" * 70, "INFO")
        
        def check_refresh(data):
            source = data.get("source")
            rates = data.get("rates", {})
            self.log(f"Refresh source: {source}", "INFO")
            self.log(f"Rates: USD={rates.get('USD')}, EUR={rates.get('EUR')}", "INFO")
            return source is not None
        
        return self.test("FX Refresh", "POST", "admin/fx/refresh", 200, check_fn=check_refresh)[0]

    def test_fx_history(self):
        """Test GET /api/admin/fx/history"""
        self.log("=" * 70, "INFO")
        self.log("TEST: FX History (D3)", "INFO")
        self.log("=" * 70, "INFO")
        
        def check_history(data):
            items = data.get("items", [])
            self.log(f"History snapshots: {len(items)}", "INFO")
            if len(items) < 1:
                self.log("Expected at least 1 snapshot", "FAIL")
                return False
            return True
        
        return self.test("FX History", "GET", "admin/fx/history", 200, check_fn=check_history)[0]

    def test_tax_config(self):
        """Test GET /api/admin/tax/config"""
        self.log("=" * 70, "INFO")
        self.log("TEST: Tax Config (D2)", "INFO")
        self.log("=" * 70, "INFO")
        
        def check_config(data):
            pdfo = data.get("pdfo_rate", 0)
            vz = data.get("vz_rate", 0)
            enabled = data.get("enabled", False)
            
            self.log(f"ПДФО rate: {pdfo}", "INFO")
            self.log(f"ВЗ rate: {vz}", "INFO")
            self.log(f"Enabled: {enabled}", "INFO")
            
            if abs(pdfo - 0.18) > 0.001:
                self.log(f"Expected pdfo_rate=0.18, got {pdfo}", "FAIL")
                return False
            if abs(vz - 0.015) > 0.001:
                self.log(f"Expected vz_rate=0.015, got {vz}", "FAIL")
                return False
            if not enabled:
                self.log("Tax should be enabled", "FAIL")
                return False
            
            return True
        
        return self.test("Tax Config", "GET", "admin/tax/config", 200, check_fn=check_config)[0]

    def test_tax_preview(self):
        """Test GET /api/admin/tax/preview?gross=1000"""
        self.log("=" * 70, "INFO")
        self.log("TEST: Tax Preview (D2)", "INFO")
        self.log("=" * 70, "INFO")
        
        def check_preview(data):
            pdfo = data.get("pdfo", 0)
            vz = data.get("vz", 0)
            net = data.get("net", 0)
            
            self.log(f"Preview gross=1000: pdfo={pdfo}, vz={vz}, net={net}", "INFO")
            
            # Expected: pdfo=180, vz=15, net=805
            if abs(pdfo - 180) > 1:
                self.log(f"Expected pdfo≈180, got {pdfo}", "FAIL")
                return False
            if abs(vz - 15) > 1:
                self.log(f"Expected vz≈15, got {vz}", "FAIL")
                return False
            if abs(net - 805) > 1:
                self.log(f"Expected net≈805, got {net}", "FAIL")
                return False
            
            return True
        
        return self.test("Tax Preview", "GET", "admin/tax/preview?gross=1000", 200, check_fn=check_preview)[0]

    def test_tax_liability(self):
        """Test GET /api/admin/tax/liability"""
        self.log("=" * 70, "INFO")
        self.log("TEST: Tax Liability (D2)", "INFO")
        self.log("=" * 70, "INFO")
        
        def check_liability(data):
            outstanding = data.get("outstanding_liability_uah", 0)
            self.log(f"Outstanding liability: {outstanding} UAH", "INFO")
            # Just check that the field exists and is a number
            return isinstance(outstanding, (int, float))
        
        return self.test("Tax Liability", "GET", "admin/tax/liability", 200, check_fn=check_liability)[0]

    def test_scheduler_due(self):
        """Test GET /api/admin/payout-scheduler/due"""
        self.log("=" * 70, "INFO")
        self.log("TEST: Scheduler Due Plans (D1)", "INFO")
        self.log("=" * 70, "INFO")
        
        def check_due(data):
            due_count = data.get("due_count")
            items = data.get("items", [])
            self.log(f"Due plans: {due_count}", "INFO")
            self.log(f"Items: {len(items)}", "INFO")
            # Just check structure exists
            return "due_count" in data and "items" in data
        
        return self.test("Scheduler Due", "GET", "admin/payout-scheduler/due", 200, check_fn=check_due)[0]

    def test_scheduler_run(self):
        """Test POST /api/admin/payout-scheduler/run"""
        self.log("=" * 70, "INFO")
        self.log("TEST: Scheduler Run (D1)", "INFO")
        self.log("=" * 70, "INFO")
        
        def check_run(data):
            due = data.get("due")
            generated = data.get("generated", [])
            errors = data.get("errors", [])
            self.log(f"Scheduler run: due={due}, generated={len(generated)}, errors={len(errors)}", "INFO")
            # Just check structure
            return "due" in data and "generated" in data
        
        return self.test("Scheduler Run", "POST", "admin/payout-scheduler/run", 200, 
                        json_data={"auto_credit": False}, check_fn=check_run)[0]

    def test_auth_gating(self):
        """Test that all endpoints require admin auth"""
        self.log("=" * 70, "INFO")
        self.log("TEST: Auth Gating (401/403 without auth)", "INFO")
        self.log("=" * 70, "INFO")
        
        no_auth = requests.Session()
        endpoints = [
            "admin/fx/rates",
            "admin/fx/refresh",
            "admin/fx/history",
            "admin/tax/config",
            "admin/tax/preview?gross=1000",
            "admin/tax/liability",
            "admin/payout-scheduler/due",
        ]
        
        all_passed = True
        for endpoint in endpoints:
            try:
                if endpoint == "admin/fx/refresh":
                    resp = no_auth.post(f"{BASE_URL}/{endpoint}")
                else:
                    resp = no_auth.get(f"{BASE_URL}/{endpoint}")
                
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
        print("LUMEN FINANCE ENGINE - BACKEND API TESTS (D1+D2+D3)")
        print("=" * 70 + "\n")
        
        tests = [
            ("Login", self.test_login),
            ("FX Rates", self.test_fx_rates),
            ("FX Refresh", self.test_fx_refresh),
            ("FX History", self.test_fx_history),
            ("Tax Config", self.test_tax_config),
            ("Tax Preview", self.test_tax_preview),
            ("Tax Liability", self.test_tax_liability),
            ("Scheduler Due", self.test_scheduler_due),
            ("Scheduler Run", self.test_scheduler_run),
            ("Auth Gating", self.test_auth_gating),
        ]
        
        for name, test_fn in tests:
            try:
                test_fn()
            except Exception as e:
                self.log(f"Test '{name}' crashed: {e}", "FAIL")
                self.tests_run += 1
            print()
        
        print("=" * 70)
        print(f"TESTS COMPLETED: {self.tests_passed}/{self.tests_run} passed")
        print("=" * 70)
        
        return 0 if self.tests_passed == self.tests_run else 1


def main():
    tester = FinanceEngineTester()
    return tester.run_all_tests()


if __name__ == "__main__":
    sys.exit(main())
