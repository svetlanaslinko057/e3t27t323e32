"""
Sprint 7 — Wallet + Withdrawals Backend API Test
=================================================
Tests all Sprint 7 backend endpoints with proper auth.

Run: cd /app/backend && python backend_test_sprint7.py
"""
import requests
import sys
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://repo-setup-93.preview.emergentagent.com")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@atlas.dev"
ADMIN_PASS = "admin123"
INVESTOR_EMAIL = "client@atlas.dev"
INVESTOR_PASS = "client123"

class Sprint7Tester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = []
        self.investor_session = requests.Session()
        self.admin_session = requests.Session()
        self.withdrawal_id = None

    def log(self, emoji, message):
        print(f"{emoji} {message}")

    def test(self, name, condition, details=""):
        self.tests_run += 1
        if condition:
            self.tests_passed += 1
            self.log("✅", f"PASS: {name} {details}")
            return True
        else:
            self.tests_failed.append(name)
            self.log("❌", f"FAIL: {name} {details}")
            return False

    def login(self, session, email, password):
        """Login and store session"""
        try:
            r = session.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=10)
            if r.status_code == 200:
                return True
            return False
        except Exception as e:
            self.log("⚠️", f"Login error for {email}: {str(e)}")
            return False

    def test_investor_wallet(self):
        """Test GET /api/investor/wallet"""
        self.log("🔍", "Testing investor wallet endpoint...")
        try:
            r = self.investor_session.get(f"{API}/investor/wallet", timeout=10)
            success = r.status_code == 200
            if success:
                data = r.json()
                wallet = data.get("wallet", {})
                has_balance = "available_balance" in wallet
                has_pending = "pending_balance" in wallet
                has_totals = "total_in" in wallet and "total_out" in wallet
                avail = wallet.get("available_balance", 0)
                # client@atlas.dev should have 85,000 UAH seeded
                has_funds = avail >= 80000
                return self.test(
                    "Investor wallet (GET /api/investor/wallet)",
                    has_balance and has_pending and has_totals and has_funds,
                    f"status={r.status_code}, available={avail}, has_structure={has_balance and has_pending}"
                )
            else:
                return self.test("Investor wallet", False, f"status={r.status_code}, body={r.text[:200]}")
        except Exception as e:
            return self.test("Investor wallet", False, f"error={str(e)}")

    def test_wallet_transactions(self):
        """Test GET /api/investor/wallet/transactions"""
        self.log("🔍", "Testing wallet transactions endpoint...")
        try:
            r = self.investor_session.get(f"{API}/investor/wallet/transactions?limit=50", timeout=10)
            success = r.status_code == 200
            if success:
                data = r.json()
                items = data.get("items", [])
                has_items = len(items) > 0
                # Check structure of first item
                has_structure = False
                if items:
                    first = items[0]
                    has_structure = "direction" in first and "reason_label" in first and "amount_uah" in first
                return self.test(
                    "Wallet transactions (GET /api/investor/wallet/transactions)",
                    has_items and has_structure,
                    f"status={r.status_code}, count={len(items)}, has_structure={has_structure}"
                )
            else:
                return self.test("Wallet transactions", False, f"status={r.status_code}")
        except Exception as e:
            return self.test("Wallet transactions", False, f"error={str(e)}")

    def test_create_withdrawal(self):
        """Test POST /api/investor/withdrawals"""
        self.log("🔍", "Testing create withdrawal endpoint...")
        try:
            payload = {
                "amount": 10000,
                "currency": "UAH",
                "iban": "UA213223130000026007233566001",
                "bank_name": "ПриватБанк",
                "beneficiary_name": "Тест Інвестор"
            }
            r = self.investor_session.post(f"{API}/investor/withdrawals", json=payload, timeout=10)
            success = r.status_code == 200
            if success:
                data = r.json()
                self.withdrawal_id = data.get("id")
                has_id = bool(self.withdrawal_id)
                is_requested = data.get("status") == "requested"
                return self.test(
                    "Create withdrawal (POST /api/investor/withdrawals)",
                    has_id and is_requested,
                    f"status={r.status_code}, id={self.withdrawal_id}, status={data.get('status')}"
                )
            else:
                return self.test("Create withdrawal", False, f"status={r.status_code}, body={r.text[:200]}")
        except Exception as e:
            return self.test("Create withdrawal", False, f"error={str(e)}")

    def test_insufficient_funds(self):
        """Test POST /api/investor/withdrawals with amount > available"""
        self.log("🔍", "Testing insufficient funds validation...")
        try:
            payload = {
                "amount": 999999999,
                "currency": "UAH",
                "iban": "UA213223130000026007233566001",
                "bank_name": "ПриватБанк",
                "beneficiary_name": "Тест Інвестор"
            }
            r = self.investor_session.post(f"{API}/investor/withdrawals", json=payload, timeout=10)
            # Should return 400
            return self.test(
                "Insufficient funds validation",
                r.status_code == 400,
                f"status={r.status_code}"
            )
        except Exception as e:
            return self.test("Insufficient funds validation", False, f"error={str(e)}")

    def test_list_withdrawals(self):
        """Test GET /api/investor/withdrawals"""
        self.log("🔍", "Testing list withdrawals endpoint...")
        try:
            r = self.investor_session.get(f"{API}/investor/withdrawals", timeout=10)
            success = r.status_code == 200
            if success:
                data = r.json()
                items = data.get("items", [])
                has_items = len(items) > 0
                return self.test(
                    "List withdrawals (GET /api/investor/withdrawals)",
                    has_items,
                    f"status={r.status_code}, count={len(items)}"
                )
            else:
                return self.test("List withdrawals", False, f"status={r.status_code}")
        except Exception as e:
            return self.test("List withdrawals", False, f"error={str(e)}")

    def test_admin_withdrawals_list(self):
        """Test GET /api/admin/withdrawals"""
        self.log("🔍", "Testing admin withdrawals list endpoint...")
        try:
            r = self.admin_session.get(f"{API}/admin/withdrawals", timeout=10)
            success = r.status_code == 200
            if success:
                data = r.json()
                items = data.get("items", [])
                counts = data.get("counts", {})
                pending_uah = data.get("pending_uah", 0)
                has_structure = "items" in data and "counts" in data and "pending_uah" in data
                return self.test(
                    "Admin withdrawals list (GET /api/admin/withdrawals)",
                    has_structure and len(items) > 0,
                    f"status={r.status_code}, count={len(items)}, pending={pending_uah}"
                )
            else:
                return self.test("Admin withdrawals list", False, f"status={r.status_code}")
        except Exception as e:
            return self.test("Admin withdrawals list", False, f"error={str(e)}")

    def test_admin_withdrawal_detail(self):
        """Test GET /api/admin/withdrawals/{id}"""
        if not self.withdrawal_id:
            return self.test("Admin withdrawal detail", False, "no withdrawal_id")
        
        self.log("🔍", f"Testing admin withdrawal detail endpoint for {self.withdrawal_id}...")
        try:
            r = self.admin_session.get(f"{API}/admin/withdrawals/{self.withdrawal_id}", timeout=10)
            success = r.status_code == 200
            if success:
                data = r.json()
                has_withdrawal = "withdrawal" in data
                has_wallet = "wallet" in data
                has_ledger = "ledger_entries" in data
                return self.test(
                    "Admin withdrawal detail (GET /api/admin/withdrawals/{id})",
                    has_withdrawal and has_wallet and has_ledger,
                    f"status={r.status_code}, has_structure={has_withdrawal and has_wallet}"
                )
            else:
                return self.test("Admin withdrawal detail", False, f"status={r.status_code}")
        except Exception as e:
            return self.test("Admin withdrawal detail", False, f"error={str(e)}")

    def test_admin_withdrawal_actions(self):
        """Test admin withdrawal lifecycle actions"""
        if not self.withdrawal_id:
            return self.test("Admin withdrawal actions", False, "no withdrawal_id")
        
        self.log("🔍", "Testing admin withdrawal actions...")
        try:
            # Test review action
            r = self.admin_session.post(
                f"{API}/admin/withdrawals/{self.withdrawal_id}/review",
                json={"comment": "Перевірка реквізитів"},
                timeout=10
            )
            review_ok = r.status_code == 200 and r.json().get("status") == "under_review"
            
            # Test approve action
            r = self.admin_session.post(
                f"{API}/admin/withdrawals/{self.withdrawal_id}/approve",
                json={},
                timeout=10
            )
            approve_ok = r.status_code == 200 and r.json().get("status") == "approved"
            
            return self.test(
                "Admin withdrawal actions (review, approve)",
                review_ok and approve_ok,
                f"review={review_ok}, approve={approve_ok}"
            )
        except Exception as e:
            return self.test("Admin withdrawal actions", False, f"error={str(e)}")

    def test_admin_ledger(self):
        """Test GET /api/admin/ledger"""
        self.log("🔍", "Testing admin ledger endpoint...")
        try:
            r = self.admin_session.get(f"{API}/admin/ledger?limit=50", timeout=10)
            success = r.status_code == 200
            if success:
                data = r.json()
                items = data.get("items", [])
                summary = data.get("summary", {})
                has_structure = "items" in data and "summary" in data
                return self.test(
                    "Admin ledger (GET /api/admin/ledger)",
                    has_structure and len(items) > 0,
                    f"status={r.status_code}, count={len(items)}"
                )
            else:
                return self.test("Admin ledger", False, f"status={r.status_code}")
        except Exception as e:
            return self.test("Admin ledger", False, f"error={str(e)}")

    def test_regression_payments(self):
        """Test Sprint 6 regression - /api/investor/payments"""
        self.log("🔍", "Testing Sprint 6 regression (investor payments)...")
        try:
            r = self.investor_session.get(f"{API}/investor/payments", timeout=10)
            return self.test(
                "Sprint 6 regression - investor payments",
                r.status_code == 200,
                f"status={r.status_code}"
            )
        except Exception as e:
            return self.test("Sprint 6 regression - investor payments", False, f"error={str(e)}")

    def test_regression_admin_payments(self):
        """Test Sprint 6 regression - /api/admin/payments"""
        self.log("🔍", "Testing Sprint 6 regression (admin payments)...")
        try:
            r = self.admin_session.get(f"{API}/admin/payments", timeout=10)
            return self.test(
                "Sprint 6 regression - admin payments",
                r.status_code == 200,
                f"status={r.status_code}"
            )
        except Exception as e:
            return self.test("Sprint 6 regression - admin payments", False, f"error={str(e)}")

    def run_all_tests(self):
        """Run all Sprint 7 backend tests"""
        self.log("🚀", "Starting Sprint 7 Backend API Tests")
        self.log("🌐", f"Base URL: {BASE_URL}")
        self.log("", "=" * 70)
        
        # Login
        self.log("🔐", "Logging in...")
        investor_login = self.login(self.investor_session, INVESTOR_EMAIL, INVESTOR_PASS)
        admin_login = self.login(self.admin_session, ADMIN_EMAIL, ADMIN_PASS)
        
        if not investor_login or not admin_login:
            self.log("❌", "Login failed - cannot proceed with tests")
            return 1
        
        self.log("✅", "Login successful")
        self.log("", "=" * 70)
        
        # Run tests
        self.test_investor_wallet()
        self.test_wallet_transactions()
        self.test_create_withdrawal()
        self.test_insufficient_funds()
        self.test_list_withdrawals()
        self.test_admin_withdrawals_list()
        self.test_admin_withdrawal_detail()
        self.test_admin_withdrawal_actions()
        self.test_admin_ledger()
        self.test_regression_payments()
        self.test_regression_admin_payments()
        
        # Print summary
        self.log("", "=" * 70)
        self.log("📊", f"Tests Run: {self.tests_run}")
        self.log("✅", f"Tests Passed: {self.tests_passed}")
        self.log("❌", f"Tests Failed: {len(self.tests_failed)}")
        
        if self.tests_failed:
            self.log("", "\nFailed tests:")
            for test in self.tests_failed:
                self.log("  ❌", test)
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        self.log("📈", f"Success Rate: {success_rate:.1f}%")
        
        return 0 if len(self.tests_failed) == 0 else 1


def main():
    tester = Sprint7Tester()
    exit_code = tester.run_all_tests()
    
    print("\n" + "=" * 70)
    if exit_code == 0:
        print("✅ ALL SPRINT 7 BACKEND TESTS PASSED")
    else:
        print("❌ SOME SPRINT 7 BACKEND TESTS FAILED")
    print("=" * 70)
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
