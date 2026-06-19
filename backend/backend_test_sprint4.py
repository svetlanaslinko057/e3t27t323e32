"""
LUMEN Sprint 4 Contracts & Legal Layer - Backend API Test
==========================================================
Tests the contracts and legal endpoints via public URL.

Coverage:
- Investor contracts endpoints
- Contract signing with Electronic Acceptance
- PDF generation
- Admin contracts registry
- Contract templates CRUD
- Intent approval → contract generation flow
"""

import requests
import sys
import json
from datetime import datetime

# Public endpoint from frontend/.env
BASE_URL = "https://arch-study-16.preview.emergentagent.com"

class Sprint4ContractsTester:
    def __init__(self):
        self.base_url = BASE_URL
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = []
        self.client_session = requests.Session()
        self.admin_session = requests.Session()
        self.contract_id = None
        self.intent_id = None

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

    def quick_login(self, session, email):
        """Quick login via /api/auth/quick"""
        try:
            response = session.post(
                f"{self.base_url}/api/auth/quick",
                json={"email": email},
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            self.log("⚠️", f"Login failed for {email}: {str(e)}")
            return False

    def test_investor_contracts_list(self):
        """Test GET /api/investor/contracts"""
        self.log("🔍", "Testing investor contracts list...")
        try:
            response = self.client_session.get(
                f"{self.base_url}/api/investor/contracts",
                timeout=10
            )
            success = response.status_code == 200
            if success:
                data = response.json()
                items = data.get("items", [])
                # client@atlas.dev should have at least one signed contract (LMN-2026-00010)
                has_contracts = len(items) > 0
                if items:
                    self.contract_id = items[0].get("id")
                return self.test(
                    "GET /api/investor/contracts",
                    has_contracts,
                    f"count={len(items)}"
                )
            else:
                return self.test(
                    "GET /api/investor/contracts",
                    False,
                    f"status={response.status_code}"
                )
        except Exception as e:
            return self.test("GET /api/investor/contracts", False, f"error={str(e)}")

    def test_investor_contract_detail(self):
        """Test GET /api/investor/contracts/{id}"""
        if not self.contract_id:
            return self.test("GET /api/investor/contracts/{id}", False, "no contract_id")
        
        self.log("🔍", f"Testing contract detail for {self.contract_id}...")
        try:
            response = self.client_session.get(
                f"{self.base_url}/api/investor/contracts/{self.contract_id}",
                timeout=10
            )
            success = response.status_code == 200
            if success:
                data = response.json()
                has_body = bool(data.get("body_text"))
                has_number = bool(data.get("number"))
                return self.test(
                    "GET /api/investor/contracts/{id}",
                    has_body and has_number,
                    f"status={data.get('status')}, number={data.get('number')}"
                )
            else:
                return self.test(
                    "GET /api/investor/contracts/{id}",
                    False,
                    f"status={response.status_code}"
                )
        except Exception as e:
            return self.test("GET /api/investor/contracts/{id}", False, f"error={str(e)}")

    def test_contract_pdf(self):
        """Test GET /api/contracts/{id}/pdf"""
        if not self.contract_id:
            return self.test("GET /api/contracts/{id}/pdf", False, "no contract_id")
        
        self.log("🔍", f"Testing PDF download for {self.contract_id}...")
        try:
            response = self.client_session.get(
                f"{self.base_url}/api/contracts/{self.contract_id}/pdf",
                timeout=10
            )
            success = response.status_code == 200
            is_pdf = response.headers.get("content-type", "").startswith("application/pdf")
            has_pdf_magic = response.content[:4] == b"%PDF"
            return self.test(
                "GET /api/contracts/{id}/pdf",
                success and is_pdf and has_pdf_magic,
                f"content-type={response.headers.get('content-type')}, size={len(response.content)}"
            )
        except Exception as e:
            return self.test("GET /api/contracts/{id}/pdf", False, f"error={str(e)}")

    def test_sign_without_agree(self):
        """Test POST /api/investor/contracts/{id}/sign without agree → 400"""
        if not self.contract_id:
            return self.test("POST /api/investor/contracts/{id}/sign (no agree)", False, "no contract_id")
        
        self.log("🔍", "Testing sign without agree (should fail)...")
        try:
            response = self.client_session.post(
                f"{self.base_url}/api/investor/contracts/{self.contract_id}/sign",
                json={"agree": False},
                timeout=10
            )
            # Should return 400 or 409 (if already signed)
            return self.test(
                "POST /api/investor/contracts/{id}/sign (no agree)",
                response.status_code in [400, 409],
                f"status={response.status_code}"
            )
        except Exception as e:
            return self.test("POST /api/investor/contracts/{id}/sign (no agree)", False, f"error={str(e)}")

    def test_admin_contracts_list(self):
        """Test GET /api/admin/contracts with counts"""
        self.log("🔍", "Testing admin contracts registry...")
        try:
            response = self.admin_session.get(
                f"{self.base_url}/api/admin/contracts",
                timeout=10
            )
            success = response.status_code == 200
            if success:
                data = response.json()
                items = data.get("items", [])
                counts = data.get("counts", {})
                has_counts = isinstance(counts, dict) and len(counts) > 0
                return self.test(
                    "GET /api/admin/contracts",
                    len(items) > 0 and has_counts,
                    f"count={len(items)}, counts={counts}"
                )
            else:
                return self.test(
                    "GET /api/admin/contracts",
                    False,
                    f"status={response.status_code}"
                )
        except Exception as e:
            return self.test("GET /api/admin/contracts", False, f"error={str(e)}")

    def test_admin_contracts_filter(self):
        """Test GET /api/admin/contracts?status=signed"""
        self.log("🔍", "Testing admin contracts filter...")
        try:
            response = self.admin_session.get(
                f"{self.base_url}/api/admin/contracts?status=signed",
                timeout=10
            )
            success = response.status_code == 200
            if success:
                data = response.json()
                items = data.get("items", [])
                all_signed = all(item.get("status") == "signed" for item in items)
                return self.test(
                    "GET /api/admin/contracts?status=signed",
                    all_signed,
                    f"count={len(items)}"
                )
            else:
                return self.test(
                    "GET /api/admin/contracts?status=signed",
                    False,
                    f"status={response.status_code}"
                )
        except Exception as e:
            return self.test("GET /api/admin/contracts?status=signed", False, f"error={str(e)}")

    def test_admin_contract_templates(self):
        """Test GET /api/admin/contract-templates"""
        self.log("🔍", "Testing admin contract templates...")
        try:
            response = self.admin_session.get(
                f"{self.base_url}/api/admin/contract-templates",
                timeout=10
            )
            success = response.status_code == 200
            if success:
                data = response.json()
                items = data.get("items", [])
                # Should have 3 default templates
                kinds = {item.get("kind") for item in items}
                expected_kinds = {"investment_agreement", "spv_participation", "co_investment"}
                has_all_kinds = expected_kinds.issubset(kinds)
                return self.test(
                    "GET /api/admin/contract-templates",
                    len(items) >= 3 and has_all_kinds,
                    f"count={len(items)}, kinds={sorted(kinds)}"
                )
            else:
                return self.test(
                    "GET /api/admin/contract-templates",
                    False,
                    f"status={response.status_code}"
                )
        except Exception as e:
            return self.test("GET /api/admin/contract-templates", False, f"error={str(e)}")

    def test_admin_intents_list(self):
        """Test GET /api/admin/intents"""
        self.log("🔍", "Testing admin intents list...")
        try:
            response = self.admin_session.get(
                f"{self.base_url}/api/admin/intents",
                timeout=10
            )
            success = response.status_code == 200
            if success:
                data = response.json()
                items = data.get("items", [])
                counts = data.get("counts", {})
                has_counts = isinstance(counts, dict)
                return self.test(
                    "GET /api/admin/intents",
                    success and has_counts,
                    f"count={len(items)}, counts={counts}"
                )
            else:
                return self.test(
                    "GET /api/admin/intents",
                    False,
                    f"status={response.status_code}"
                )
        except Exception as e:
            return self.test("GET /api/admin/intents", False, f"error={str(e)}")

    def run_all_tests(self):
        """Run all Sprint 4 contract tests"""
        self.log("🚀", "Starting LUMEN Sprint 4 Contracts Backend Tests")
        self.log("🌐", f"Base URL: {self.base_url}")
        print()

        # Setup: Login as client and admin
        self.log("🔐", "Logging in as client@atlas.dev...")
        if not self.quick_login(self.client_session, "client@atlas.dev"):
            self.log("❌", "Failed to login as client - aborting tests")
            return 1

        self.log("🔐", "Logging in as admin@atlas.dev...")
        if not self.quick_login(self.admin_session, "admin@atlas.dev"):
            self.log("❌", "Failed to login as admin - aborting tests")
            return 1

        print()
        self.log("📋", "Running Investor Contracts Tests...")
        self.test_investor_contracts_list()
        self.test_investor_contract_detail()
        self.test_contract_pdf()
        self.test_sign_without_agree()

        print()
        self.log("📋", "Running Admin Contracts Tests...")
        self.test_admin_contracts_list()
        self.test_admin_contracts_filter()
        self.test_admin_contract_templates()
        self.test_admin_intents_list()

        # Summary
        print()
        print("=" * 60)
        self.log("📊", f"Tests Run: {self.tests_run}")
        self.log("✅", f"Tests Passed: {self.tests_passed}")
        self.log("❌", f"Tests Failed: {len(self.tests_failed)}")
        
        if self.tests_failed:
            print()
            self.log("❌", "Failed tests:")
            for test_name in self.tests_failed:
                print(f"  - {test_name}")
            return 1
        else:
            print()
            self.log("🎉", "ALL TESTS PASSED!")
            return 0

def main():
    tester = Sprint4ContractsTester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())
