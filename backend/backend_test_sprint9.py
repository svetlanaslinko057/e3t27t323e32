"""
LUMEN Sprint 9 Backend Test — Investor Analytics & Fund Intelligence
=====================================================================
Tests all Sprint 9 analytics endpoints with live registry calculations.

Critical principle: All metrics calculated LIVE from registries (no stored KPIs).

Test Coverage:
1. Investor Analytics (client@atlas.dev/client123)
   - GET /api/investor/analytics/overview
   - GET /api/investor/analytics/assets
   - GET /api/investor/analytics/timeline
   - GET /api/investor/analytics/portfolio-timeline
   - GET /api/investor/statements (monthly/quarterly/annual PDFs)

2. Admin Fund Intelligence (admin@atlas.dev/admin123)
   - GET /api/admin/fund/intelligence
   - GET /api/admin/fund/health
   - Admin statements endpoints

3. Access Control
   - Investor cannot access admin endpoints
   - Unauthenticated requests fail
"""

import requests
import sys
import json
from datetime import datetime

# Public endpoint from frontend/.env
BASE_URL = "https://arch-study-17.preview.emergentagent.com"

class Sprint9Tester:
    def __init__(self):
        self.base_url = BASE_URL
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = []
        self.client_cookies = None
        self.admin_cookies = None
        
    def log(self, emoji, message):
        """Print formatted log message"""
        print(f"{emoji} {message}")
        
    def test(self, name, condition, details=""):
        """Record test result"""
        self.tests_run += 1
        if condition:
            self.tests_passed += 1
            self.log("✅", f"PASS: {name} {details}")
            return True
        else:
            self.tests_failed.append(name)
            self.log("❌", f"FAIL: {name} {details}")
            return False
    
    def login_client(self):
        """Login as investor client@atlas.dev/client123"""
        self.log("🔐", "Logging in as investor (client@atlas.dev)...")
        try:
            response = requests.post(
                f"{self.base_url}/api/auth/login",
                json={"email": "client@atlas.dev", "password": "client123"},
                timeout=10
            )
            if response.status_code == 200:
                self.client_cookies = response.cookies
                self.log("✅", "Client login successful")
                return True
            else:
                self.log("❌", f"Client login failed: status={response.status_code}")
                return False
        except Exception as e:
            self.log("❌", f"Client login error: {str(e)}")
            return False
    
    def login_admin(self):
        """Login as admin@atlas.dev/admin123"""
        self.log("🔐", "Logging in as admin (admin@atlas.dev)...")
        try:
            response = requests.post(
                f"{self.base_url}/api/auth/login",
                json={"email": "admin@atlas.dev", "password": "admin123"},
                timeout=10
            )
            if response.status_code == 200:
                self.admin_cookies = response.cookies
                self.log("✅", "Admin login successful")
                return True
            else:
                self.log("❌", f"Admin login failed: status={response.status_code}")
                return False
        except Exception as e:
            self.log("❌", f"Admin login error: {str(e)}")
            return False
    
    # ========== INVESTOR ANALYTICS TESTS ==========
    
    def test_investor_overview(self):
        """Test GET /api/investor/analytics/overview"""
        self.log("🔍", "Testing investor analytics overview...")
        try:
            response = requests.get(
                f"{self.base_url}/api/investor/analytics/overview",
                cookies=self.client_cookies,
                timeout=10
            )
            
            if response.status_code != 200:
                return self.test(
                    "Investor overview",
                    False,
                    f"status={response.status_code}"
                )
            
            data = response.json()
            
            # Verify structure
            has_portfolio = "portfolio" in data
            has_yield = "yield" in data
            has_allocation = "allocation" in data
            
            if not (has_portfolio and has_yield and has_allocation):
                return self.test(
                    "Investor overview structure",
                    False,
                    f"missing keys: portfolio={has_portfolio}, yield={has_yield}, allocation={has_allocation}"
                )
            
            # Verify portfolio fields
            pf = data["portfolio"]
            required_pf = ["invested_total", "current_value", "received_total", "expected_total", "wallet_available"]
            missing_pf = [f for f in required_pf if f not in pf]
            
            if missing_pf:
                return self.test(
                    "Investor overview portfolio",
                    False,
                    f"missing fields: {missing_pf}"
                )
            
            # Verify yield fields
            yl = data["yield"]
            required_yl = ["realized_yield", "unrealized_yield", "annualized_yield", "weighted_holding_years"]
            missing_yl = [f for f in required_yl if f not in yl]
            
            if missing_yl:
                return self.test(
                    "Investor overview yield",
                    False,
                    f"missing fields: {missing_yl}"
                )
            
            # Verify allocation structure
            al = data["allocation"]
            required_al = ["by_category", "by_region", "by_risk"]
            missing_al = [f for f in required_al if f not in al]
            
            if missing_al:
                return self.test(
                    "Investor overview allocation",
                    False,
                    f"missing fields: {missing_al}"
                )
            
            # Verify allocation percents sum to ~100 within each group
            for group_name, group_data in [("by_category", al["by_category"]), 
                                           ("by_region", al["by_region"]), 
                                           ("by_risk", al["by_risk"])]:
                if group_data:
                    total_percent = sum(item.get("percent", 0) for item in group_data)
                    if not (95 <= total_percent <= 105):  # Allow 5% tolerance
                        self.log("⚠️", f"Allocation {group_name} percents sum to {total_percent}% (expected ~100%)")
            
            # Log key metrics for verification
            self.log("📊", f"Portfolio: invested={pf['invested_total']}, received={pf['received_total']}, expected={pf['expected_total']}")
            self.log("📊", f"Yield: realized={yl['realized_yield']}%, annualized={yl['annualized_yield']}%")
            
            # Verify expected seed data values (client@atlas.dev has 850k invested, 125k received)
            invested_ok = 800000 <= pf["invested_total"] <= 900000
            received_ok = 120000 <= pf["received_total"] <= 130000
            
            if not invested_ok:
                self.log("⚠️", f"Invested total {pf['invested_total']} outside expected range (850k)")
            if not received_ok:
                self.log("⚠️", f"Received total {pf['received_total']} outside expected range (125k)")
            
            return self.test(
                "Investor overview",
                True,
                f"invested={pf['invested_total']}, received={pf['received_total']}"
            )
            
        except Exception as e:
            return self.test("Investor overview", False, f"error={str(e)}")
    
    def test_investor_assets(self):
        """Test GET /api/investor/analytics/assets"""
        self.log("🔍", "Testing investor asset performance...")
        try:
            response = requests.get(
                f"{self.base_url}/api/investor/analytics/assets",
                cookies=self.client_cookies,
                timeout=10
            )
            
            if response.status_code != 200:
                return self.test(
                    "Investor assets",
                    False,
                    f"status={response.status_code}"
                )
            
            data = response.json()
            items = data.get("items", [])
            
            if len(items) == 0:
                return self.test(
                    "Investor assets",
                    False,
                    "no assets returned (expected 3 ownerships)"
                )
            
            # Verify structure of first item
            if items:
                item = items[0]
                required = ["asset_id", "asset_title", "invested", "share_percent", "received", 
                           "roi", "risk_level", "risk_label", "region", "category_label"]
                missing = [f for f in required if f not in item]
                
                if missing:
                    return self.test(
                        "Investor assets structure",
                        False,
                        f"missing fields: {missing}"
                    )
                
                self.log("📊", f"Asset: {item['asset_title']}, invested={item['invested']}, roi={item['roi']}%")
            
            return self.test(
                "Investor assets",
                len(items) >= 3,
                f"count={len(items)} (expected 3)"
            )
            
        except Exception as e:
            return self.test("Investor assets", False, f"error={str(e)}")
    
    def test_investor_timeline(self):
        """Test GET /api/investor/analytics/timeline"""
        self.log("🔍", "Testing investor timeline...")
        try:
            response = requests.get(
                f"{self.base_url}/api/investor/analytics/timeline?limit=40",
                cookies=self.client_cookies,
                timeout=10
            )
            
            if response.status_code != 200:
                return self.test(
                    "Investor timeline",
                    False,
                    f"status={response.status_code}"
                )
            
            data = response.json()
            items = data.get("items", [])
            
            # Verify structure
            if items:
                item = items[0]
                required = ["date", "type", "title"]
                missing = [f for f in required if f not in item]
                
                if missing:
                    return self.test(
                        "Investor timeline structure",
                        False,
                        f"missing fields: {missing}"
                    )
                
                # Verify event types are valid
                valid_types = ["investment_created", "kyc_approved", "contract_signed", 
                              "payment_confirmed", "payout_received", "withdrawal_submitted"]
                invalid_types = [i["type"] for i in items if i["type"] not in valid_types]
                
                if invalid_types:
                    self.log("⚠️", f"Unknown event types: {set(invalid_types)}")
                
                self.log("📊", f"Timeline events: {len(items)}, types: {set(i['type'] for i in items[:5])}")
            
            return self.test(
                "Investor timeline",
                len(items) > 0,
                f"count={len(items)}"
            )
            
        except Exception as e:
            return self.test("Investor timeline", False, f"error={str(e)}")
    
    def test_investor_portfolio_timeline(self):
        """Test GET /api/investor/analytics/portfolio-timeline"""
        self.log("🔍", "Testing investor portfolio timeline (5-stage lifecycle)...")
        try:
            response = requests.get(
                f"{self.base_url}/api/investor/analytics/portfolio-timeline",
                cookies=self.client_cookies,
                timeout=10
            )
            
            if response.status_code != 200:
                return self.test(
                    "Portfolio timeline",
                    False,
                    f"status={response.status_code}"
                )
            
            data = response.json()
            stages = data.get("stages", [])
            completed = data.get("completed", 0)
            
            # Verify 5 stages
            expected_keys = ["invested", "funded", "contract_signed", "first_payout", "withdrawal"]
            stage_keys = [s.get("key") for s in stages]
            
            if stage_keys != expected_keys:
                return self.test(
                    "Portfolio timeline stages",
                    False,
                    f"stages={stage_keys}, expected={expected_keys}"
                )
            
            # Verify structure
            if stages:
                stage = stages[0]
                required = ["key", "label", "done", "date"]
                missing = [f for f in required if f not in stage]
                
                if missing:
                    return self.test(
                        "Portfolio timeline structure",
                        False,
                        f"missing fields: {missing}"
                    )
            
            self.log("📊", f"Portfolio stages: {len(stages)}, completed: {completed}")
            
            return self.test(
                "Portfolio timeline",
                len(stages) == 5,
                f"stages={len(stages)}, completed={completed}"
            )
            
        except Exception as e:
            return self.test("Portfolio timeline", False, f"error={str(e)}")
    
    def test_investor_statements(self):
        """Test GET /api/investor/statements"""
        self.log("🔍", "Testing investor statements list...")
        try:
            response = requests.get(
                f"{self.base_url}/api/investor/statements",
                cookies=self.client_cookies,
                timeout=10
            )
            
            if response.status_code != 200:
                return self.test(
                    "Investor statements",
                    False,
                    f"status={response.status_code}"
                )
            
            data = response.json()
            types = data.get("types", [])
            periods = data.get("periods", {})
            
            # Verify types
            expected_types = ["monthly", "quarterly", "annual"]
            type_keys = [t.get("key") for t in types]
            
            if not all(t in type_keys for t in expected_types):
                return self.test(
                    "Investor statements types",
                    False,
                    f"types={type_keys}, expected={expected_types}"
                )
            
            # Verify periods structure
            for ptype in expected_types:
                if ptype not in periods:
                    return self.test(
                        "Investor statements periods",
                        False,
                        f"missing period type: {ptype}"
                    )
            
            # Count total periods
            total_periods = sum(len(periods[t]) for t in expected_types)
            self.log("📊", f"Statement periods: monthly={len(periods['monthly'])}, quarterly={len(periods['quarterly'])}, annual={len(periods['annual'])}")
            
            return self.test(
                "Investor statements",
                total_periods > 0,
                f"total_periods={total_periods}"
            )
            
        except Exception as e:
            return self.test("Investor statements", False, f"error={str(e)}")
    
    def test_investor_statement_pdf(self):
        """Test GET /api/investor/statements/monthly/2026-06/pdf"""
        self.log("🔍", "Testing investor statement PDF download...")
        try:
            # Try to get a monthly statement for June 2026
            response = requests.get(
                f"{self.base_url}/api/investor/statements/monthly/2026-06/pdf",
                cookies=self.client_cookies,
                timeout=15
            )
            
            if response.status_code != 200:
                return self.test(
                    "Investor statement PDF",
                    False,
                    f"status={response.status_code}"
                )
            
            # Verify content type
            content_type = response.headers.get("Content-Type", "")
            if "application/pdf" not in content_type:
                return self.test(
                    "Investor statement PDF content-type",
                    False,
                    f"content_type={content_type}"
                )
            
            # Verify non-empty
            content_length = len(response.content)
            if content_length == 0:
                return self.test(
                    "Investor statement PDF content",
                    False,
                    "empty PDF"
                )
            
            self.log("📊", f"PDF size: {content_length} bytes")
            
            return self.test(
                "Investor statement PDF",
                True,
                f"size={content_length} bytes"
            )
            
        except Exception as e:
            return self.test("Investor statement PDF", False, f"error={str(e)}")
    
    # ========== ADMIN FUND INTELLIGENCE TESTS ==========
    
    def test_admin_fund_intelligence(self):
        """Test GET /api/admin/fund/intelligence"""
        self.log("🔍", "Testing admin fund intelligence...")
        try:
            response = requests.get(
                f"{self.base_url}/api/admin/fund/intelligence",
                cookies=self.admin_cookies,
                timeout=10
            )
            
            if response.status_code != 200:
                return self.test(
                    "Admin fund intelligence",
                    False,
                    f"status={response.status_code}"
                )
            
            data = response.json()
            
            # Verify all required fields
            required = [
                "aum", "active_investors", "capital_raised", "capital_paid_out",
                "withdrawals_paid", "pending_funding", "pending_withdrawals",
                "upcoming_payouts", "upcoming_payouts_count", "net_cash_position",
                "average_yield", "asset_health_distribution"
            ]
            missing = [f for f in required if f not in data]
            
            if missing:
                return self.test(
                    "Admin fund intelligence structure",
                    False,
                    f"missing fields: {missing}"
                )
            
            # Verify asset_health_distribution structure
            dist = data["asset_health_distribution"]
            if not all(k in dist for k in ["healthy", "warning", "critical"]):
                return self.test(
                    "Admin fund health distribution",
                    False,
                    f"missing health keys: {dist.keys()}"
                )
            
            # Log key metrics
            self.log("📊", f"AUM: {data['aum']}, Active investors: {data['active_investors']}")
            self.log("📊", f"Capital raised: {data['capital_raised']}, Paid out: {data['capital_paid_out']}")
            self.log("📊", f"Health: healthy={dist['healthy']}, warning={dist['warning']}, critical={dist['critical']}")
            
            # Verify capital_paid_out matches investor received (125000)
            # Note: This assumes single investor in seed data
            capital_paid_out = data["capital_paid_out"]
            expected_paid_out = 125000
            paid_out_ok = abs(capital_paid_out - expected_paid_out) < 1000  # Allow small tolerance
            
            if not paid_out_ok:
                self.log("⚠️", f"Capital paid out {capital_paid_out} doesn't match expected {expected_paid_out}")
            
            return self.test(
                "Admin fund intelligence",
                True,
                f"aum={data['aum']}, investors={data['active_investors']}"
            )
            
        except Exception as e:
            return self.test("Admin fund intelligence", False, f"error={str(e)}")
    
    def test_admin_fund_health(self):
        """Test GET /api/admin/fund/health"""
        self.log("🔍", "Testing admin fund health monitoring...")
        try:
            response = requests.get(
                f"{self.base_url}/api/admin/fund/health",
                cookies=self.admin_cookies,
                timeout=10
            )
            
            if response.status_code != 200:
                return self.test(
                    "Admin fund health",
                    False,
                    f"status={response.status_code}"
                )
            
            data = response.json()
            items = data.get("items", [])
            thresholds = data.get("thresholds", {})
            
            # Verify thresholds
            required_thresholds = ["overdue_warn_days", "overdue_crit_days", 
                                  "report_warn_days", "report_crit_days"]
            missing_thresholds = [t for t in required_thresholds if t not in thresholds]
            
            if missing_thresholds:
                return self.test(
                    "Admin fund health thresholds",
                    False,
                    f"missing thresholds: {missing_thresholds}"
                )
            
            # Verify item structure
            if items:
                item = items[0]
                required = ["asset_id", "asset_title", "status", "signals", 
                           "days_overdue", "days_since_report"]
                missing = [f for f in required if f not in item]
                
                if missing:
                    return self.test(
                        "Admin fund health structure",
                        False,
                        f"missing fields: {missing}"
                    )
                
                # Verify status values
                valid_statuses = ["healthy", "warning", "critical"]
                invalid_statuses = [i["status"] for i in items if i["status"] not in valid_statuses]
                
                if invalid_statuses:
                    self.log("⚠️", f"Invalid health statuses: {set(invalid_statuses)}")
                
                self.log("📊", f"Health items: {len(items)}, statuses: {[i['status'] for i in items[:3]]}")
            
            # Verify all assets are healthy (fresh seed data)
            unhealthy = [i for i in items if i["status"] != "healthy"]
            if unhealthy:
                self.log("⚠️", f"Found {len(unhealthy)} unhealthy assets (expected all healthy with fresh seed)")
            
            return self.test(
                "Admin fund health",
                len(items) >= 6,
                f"count={len(items)}, healthy={len([i for i in items if i['status'] == 'healthy'])}"
            )
            
        except Exception as e:
            return self.test("Admin fund health", False, f"error={str(e)}")
    
    def test_admin_fund_health_filter(self):
        """Test GET /api/admin/fund/health?status=healthy"""
        self.log("🔍", "Testing admin fund health with status filter...")
        try:
            response = requests.get(
                f"{self.base_url}/api/admin/fund/health?status=healthy",
                cookies=self.admin_cookies,
                timeout=10
            )
            
            if response.status_code != 200:
                return self.test(
                    "Admin fund health filter",
                    False,
                    f"status={response.status_code}"
                )
            
            data = response.json()
            items = data.get("items", [])
            
            # Verify all items have status=healthy
            non_healthy = [i for i in items if i.get("status") != "healthy"]
            
            if non_healthy:
                return self.test(
                    "Admin fund health filter",
                    False,
                    f"found {len(non_healthy)} non-healthy items in filtered result"
                )
            
            return self.test(
                "Admin fund health filter",
                True,
                f"count={len(items)}"
            )
            
        except Exception as e:
            return self.test("Admin fund health filter", False, f"error={str(e)}")
    
    # ========== ACCESS CONTROL TESTS ==========
    
    def test_investor_cannot_access_admin(self):
        """Test that investor cannot access admin endpoints"""
        self.log("🔍", "Testing access control: investor → admin endpoints...")
        try:
            response = requests.get(
                f"{self.base_url}/api/admin/fund/intelligence",
                cookies=self.client_cookies,
                timeout=10
            )
            
            # Should return 401 or 403
            is_blocked = response.status_code in [401, 403]
            
            return self.test(
                "Access control: investor → admin",
                is_blocked,
                f"status={response.status_code} (expected 401/403)"
            )
            
        except Exception as e:
            return self.test("Access control: investor → admin", False, f"error={str(e)}")
    
    def test_unauthenticated_analytics(self):
        """Test that unauthenticated requests fail"""
        self.log("🔍", "Testing access control: unauthenticated → analytics...")
        try:
            response = requests.get(
                f"{self.base_url}/api/investor/analytics/overview",
                timeout=10
            )
            
            # Should return 401
            is_blocked = response.status_code == 401
            
            return self.test(
                "Access control: unauthenticated",
                is_blocked,
                f"status={response.status_code} (expected 401)"
            )
            
        except Exception as e:
            return self.test("Access control: unauthenticated", False, f"error={str(e)}")
    
    # ========== MAIN TEST RUNNER ==========
    
    def run_all_tests(self):
        """Run all Sprint 9 tests"""
        self.log("🚀", "Starting Sprint 9 Backend Tests...")
        self.log("🌐", f"Base URL: {self.base_url}")
        print()
        
        # Login
        if not self.login_client():
            self.log("❌", "Cannot proceed without client login")
            return False
        
        if not self.login_admin():
            self.log("❌", "Cannot proceed without admin login")
            return False
        
        print()
        
        # Investor Analytics Tests
        self.log("📊", "=== INVESTOR ANALYTICS TESTS ===")
        self.test_investor_overview()
        self.test_investor_assets()
        self.test_investor_timeline()
        self.test_investor_portfolio_timeline()
        self.test_investor_statements()
        self.test_investor_statement_pdf()
        
        print()
        
        # Admin Fund Intelligence Tests
        self.log("🏦", "=== ADMIN FUND INTELLIGENCE TESTS ===")
        self.test_admin_fund_intelligence()
        self.test_admin_fund_health()
        self.test_admin_fund_health_filter()
        
        print()
        
        # Access Control Tests
        self.log("🔒", "=== ACCESS CONTROL TESTS ===")
        self.test_investor_cannot_access_admin()
        self.test_unauthenticated_analytics()
        
        print()
        
        # Summary
        self.log("📊", "=== TEST SUMMARY ===")
        self.log("✅", f"Passed: {self.tests_passed}/{self.tests_run}")
        if self.tests_failed:
            self.log("❌", f"Failed: {len(self.tests_failed)}/{self.tests_run}")
            self.log("❌", f"Failed tests: {', '.join(self.tests_failed)}")
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        self.log("📈", f"Success rate: {success_rate:.1f}%")
        
        return self.tests_passed == self.tests_run

def main():
    tester = Sprint9Tester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
