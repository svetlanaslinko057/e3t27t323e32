"""
LUMEN Tier-B Compliance Testing — Sanctions + PEP + Risk + AML
Backend API validation for the compliance screening module.
"""
import requests
import sys
import json
from datetime import datetime

# Use the public endpoint from frontend/.env
BASE_URL = "https://dev-setup-30.preview.emergentagent.com/api"

class ComplianceAPITester:
    def __init__(self):
        self.base_url = BASE_URL
        self.admin_token = None
        self.investor_token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.results = []

    def log(self, test_name, passed, detail=""):
        self.tests_run += 1
        if passed:
            self.tests_passed += 1
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} | {test_name}")
        if detail:
            print(f"     └─ {detail}")
        self.results.append({
            "test": test_name,
            "passed": passed,
            "detail": detail
        })

    def admin_login(self):
        """Login as admin and store session token"""
        print("\n🔐 Admin Authentication")
        try:
            r = requests.post(
                f"{self.base_url}/auth/login",
                json={"email": "admin@devos.io", "password": "admin123"},
                timeout=10
            )
            if r.status_code == 200:
                # Extract session token from cookies
                cookies = r.cookies.get_dict()
                if 'session_token' in cookies:
                    self.admin_token = cookies['session_token']
                    self.log("Admin login", True, f"Authenticated as admin@devos.io")
                    return True
                else:
                    self.log("Admin login", False, "No session_token in response")
                    return False
            else:
                self.log("Admin login", False, f"Status {r.status_code}: {r.text[:200]}")
                return False
        except Exception as e:
            self.log("Admin login", False, f"Exception: {str(e)}")
            return False

    def get_headers(self, admin=True):
        """Get headers with session token"""
        token = self.admin_token if admin else self.investor_token
        if token:
            return {
                'Content-Type': 'application/json',
                'Cookie': f'session_token={token}'
            }
        return {'Content-Type': 'application/json'}

    def test_dashboard(self):
        """Test GET /admin/compliance/dashboard"""
        print("\n📊 Dashboard Endpoint")
        try:
            r = requests.get(
                f"{self.base_url}/admin/compliance/dashboard",
                headers=self.get_headers(),
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                required_fields = [
                    'cases_by_status', 'open_cases_by_risk', 'watchlist_total',
                    'watchlist_by_source', 'screenings_total', 'aml_events_total'
                ]
                missing = [f for f in required_fields if f not in data]
                if not missing:
                    self.log("Dashboard returns all required fields", True,
                            f"watchlist={data.get('watchlist_total')}, screenings={data.get('screenings_total')}")
                    return data
                else:
                    self.log("Dashboard returns all required fields", False, f"Missing: {missing}")
                    return None
            else:
                self.log("Dashboard endpoint", False, f"Status {r.status_code}")
                return None
        except Exception as e:
            self.log("Dashboard endpoint", False, f"Exception: {str(e)}")
            return None

    def test_watchlist(self):
        """Test GET /admin/compliance/watchlist"""
        print("\n🛡️ Watchlist Endpoint")
        try:
            r = requests.get(
                f"{self.base_url}/admin/compliance/watchlist",
                headers=self.get_headers(),
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                by_source = data.get('by_source', {})
                sources = ['ofac', 'eu', 'uk', 'ua_nsdc', 'pep']
                
                for src in sources:
                    count = by_source.get(src, 0)
                    self.log(f"Watchlist has {src} entries", count > 0, f"count={count}")
                
                return data
            else:
                self.log("Watchlist endpoint", False, f"Status {r.status_code}")
                return None
        except Exception as e:
            self.log("Watchlist endpoint", False, f"Exception: {str(e)}")
            return None

    def test_screen_sanction(self):
        """Test POST /admin/compliance/screen with sanctioned name"""
        print("\n🚨 Sanction Screening Test")
        try:
            r = requests.post(
                f"{self.base_url}/admin/compliance/screen",
                headers=self.get_headers(),
                json={
                    "name": "Stanislav Sanctiontest Blockov",
                    "country": "RU"
                },
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                decision = data.get('decision')
                risk_band = data.get('risk_band')
                
                self.log("Sanctioned name → confirmed_match", 
                        decision == 'confirmed_match',
                        f"decision={decision}, top_score={data.get('top_score')}")
                self.log("Sanctioned name → CRITICAL risk",
                        risk_band == 'CRITICAL',
                        f"risk_band={risk_band}")
                return data
            else:
                self.log("Sanction screening", False, f"Status {r.status_code}")
                return None
        except Exception as e:
            self.log("Sanction screening", False, f"Exception: {str(e)}")
            return None

    def test_screen_pep(self):
        """Test POST /admin/compliance/screen with PEP name"""
        print("\n👔 PEP Screening Test")
        try:
            r = requests.post(
                f"{self.base_url}/admin/compliance/screen",
                headers=self.get_headers(),
                json={
                    "name": "Petro Peptest Politov",
                    "country": "UA"
                },
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                pep_hit = data.get('pep_hit')
                risk_band = data.get('risk_band')
                risk_order = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2, 'CRITICAL': 3}
                
                self.log("PEP name → pep_hit=true",
                        pep_hit is True,
                        f"pep_hit={pep_hit}")
                self.log("PEP name → risk ≥ HIGH",
                        risk_order.get(risk_band, 0) >= 2,
                        f"risk_band={risk_band}")
                return data
            else:
                self.log("PEP screening", False, f"Status {r.status_code}")
                return None
        except Exception as e:
            self.log("PEP screening", False, f"Exception: {str(e)}")
            return None

    def test_screen_clean(self):
        """Test POST /admin/compliance/screen with clean name"""
        print("\n✅ Clean Name Screening Test")
        try:
            r = requests.post(
                f"{self.base_url}/admin/compliance/screen",
                headers=self.get_headers(),
                json={
                    "name": "Olha Tymchenko Bezdoganna",
                    "country": "UA"
                },
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                decision = data.get('decision')
                risk_band = data.get('risk_band')
                
                self.log("Clean name → decision=clear",
                        decision == 'clear',
                        f"decision={decision}, matches={len(data.get('matches', []))}")
                self.log("Clean UA name → risk LOW/MEDIUM",
                        risk_band in ['LOW', 'MEDIUM'],
                        f"risk_band={risk_band}")
                return data
            else:
                self.log("Clean screening", False, f"Status {r.status_code}")
                return None
        except Exception as e:
            self.log("Clean screening", False, f"Exception: {str(e)}")
            return None

    def test_cases_list(self):
        """Test GET /admin/compliance/cases"""
        print("\n📋 Cases List Endpoint")
        try:
            # Test without filters
            r = requests.get(
                f"{self.base_url}/admin/compliance/cases",
                headers=self.get_headers(),
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                self.log("Cases list endpoint", True, f"items={len(data.get('items', []))}")
                
                # Test with status filter
                r2 = requests.get(
                    f"{self.base_url}/admin/compliance/cases?status=open",
                    headers=self.get_headers(),
                    timeout=10
                )
                if r2.status_code == 200:
                    self.log("Cases list with status filter", True)
                else:
                    self.log("Cases list with status filter", False, f"Status {r2.status_code}")
                
                # Test with risk filter
                r3 = requests.get(
                    f"{self.base_url}/admin/compliance/cases?risk=CRITICAL",
                    headers=self.get_headers(),
                    timeout=10
                )
                if r3.status_code == 200:
                    self.log("Cases list with risk filter", True)
                else:
                    self.log("Cases list with risk filter", False, f"Status {r3.status_code}")
                
                return data
            else:
                self.log("Cases list endpoint", False, f"Status {r.status_code}")
                return None
        except Exception as e:
            self.log("Cases list endpoint", False, f"Exception: {str(e)}")
            return None

    def test_case_decision(self):
        """Test POST /admin/compliance/cases/{id}/decision"""
        print("\n⚖️ Case Decision Endpoint")
        try:
            # First get a case
            r = requests.get(
                f"{self.base_url}/admin/compliance/cases?status=open",
                headers=self.get_headers(),
                timeout=10
            )
            if r.status_code == 200:
                cases = r.json().get('items', [])
                if cases:
                    case_id = cases[0]['id']
                    # Try to make a decision
                    r2 = requests.post(
                        f"{self.base_url}/admin/compliance/cases/{case_id}/decision",
                        headers=self.get_headers(),
                        json={"decision": "escalate", "reason": "Test escalation for compliance review"},
                        timeout=10
                    )
                    if r2.status_code == 200:
                        data = r2.json()
                        self.log("Case decision endpoint", True, f"case_id={case_id}, new_status={data.get('case', {}).get('status')}")
                        return data
                    else:
                        self.log("Case decision endpoint", False, f"Status {r2.status_code}: {r2.text[:200]}")
                        return None
                else:
                    self.log("Case decision endpoint", False, "No open cases to test with")
                    return None
            else:
                self.log("Case decision endpoint", False, f"Could not fetch cases: {r.status_code}")
                return None
        except Exception as e:
            self.log("Case decision endpoint", False, f"Exception: {str(e)}")
            return None

    def test_aml_audit(self):
        """Test GET /admin/compliance/aml-audit"""
        print("\n📜 AML Audit Journal")
        try:
            r = requests.get(
                f"{self.base_url}/admin/compliance/aml-audit?limit=50",
                headers=self.get_headers(),
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                items = data.get('items', [])
                if items:
                    required_fields = ['actor', 'action', 'at', 'reason']
                    first_item = items[0]
                    has_fields = all(f in first_item for f in required_fields)
                    self.log("AML audit has required fields (actor/action/at/reason)",
                            has_fields,
                            f"items={len(items)}, fields={list(first_item.keys())[:6]}")
                else:
                    self.log("AML audit endpoint", True, "No items yet (expected for fresh system)")
                return data
            else:
                self.log("AML audit endpoint", False, f"Status {r.status_code}")
                return None
        except Exception as e:
            self.log("AML audit endpoint", False, f"Exception: {str(e)}")
            return None

    def test_auth_protection(self):
        """Test that endpoints require admin auth"""
        print("\n🔒 Auth Protection Tests")
        endpoints = [
            '/admin/compliance/dashboard',
            '/admin/compliance/watchlist',
            '/admin/compliance/cases',
            '/admin/compliance/aml-audit'
        ]
        
        for endpoint in endpoints:
            try:
                r = requests.get(
                    f"{self.base_url}{endpoint}",
                    headers={'Content-Type': 'application/json'},  # No auth
                    timeout=10
                )
                # Should get 401 or 403
                protected = r.status_code in [401, 403]
                self.log(f"Auth protection on {endpoint}",
                        protected,
                        f"status={r.status_code} (expected 401/403)")
            except Exception as e:
                self.log(f"Auth protection on {endpoint}", False, f"Exception: {str(e)}")

    def run_all_tests(self):
        """Run all compliance API tests"""
        print("=" * 80)
        print("LUMEN TIER-B COMPLIANCE API TESTING")
        print("=" * 80)
        
        if not self.admin_login():
            print("\n❌ Cannot proceed without admin authentication")
            return False
        
        # Run all test suites
        self.test_dashboard()
        self.test_watchlist()
        self.test_screen_sanction()
        self.test_screen_pep()
        self.test_screen_clean()
        self.test_cases_list()
        self.test_case_decision()
        self.test_aml_audit()
        self.test_auth_protection()
        
        # Summary
        print("\n" + "=" * 80)
        print(f"BACKEND TEST SUMMARY: {self.tests_passed}/{self.tests_run} PASSED")
        print("=" * 80)
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        print(f"Success Rate: {success_rate:.1f}%")
        
        return self.tests_passed == self.tests_run


def main():
    tester = ComplianceAPITester()
    success = tester.run_all_tests()
    
    # Save results
    report = {
        "timestamp": datetime.now().isoformat(),
        "total_tests": tester.tests_run,
        "passed": tester.tests_passed,
        "failed": tester.tests_run - tester.tests_passed,
        "success_rate": f"{(tester.tests_passed / tester.tests_run * 100):.1f}%" if tester.tests_run > 0 else "0%",
        "results": tester.results
    }
    
    with open('/app/test_reports/backend_compliance_test.json', 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n📄 Report saved to /app/test_reports/backend_compliance_test.json")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
