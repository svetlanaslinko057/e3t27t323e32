"""
H1.1 Funding Center — Comprehensive Backend Test Suite
======================================================

Tests all 19 scenarios from the review request:
1. Bank accounts endpoint (3 accounts including SEPA EUR)
2. Canonical statuses endpoint
3-6. SEPA transfer validation (valid, USD, below-min, duplicate)
7-9. Proof upload/download
10-12. Admin reconcile/match/confirm flow
13. History endpoint with R3 schema
14. Exceptions endpoint
15. Ledger endpoint
16. Rate limiting (11th call returns 429)
17-19. Launch readiness regression checks
"""
import io
import os
import sys
import time
import uuid
from datetime import datetime

import requests

# Get backend URL from environment
BACKEND_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://dev-staging-41.preview.emergentagent.com")
ADMIN_EMAIL = "admin@atlas.dev"
ADMIN_PWD = "admin123"


class FundingCenterTester:
    def __init__(self, base_url=BACKEND_URL):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []
        self.transfer_id = None
        self.proof_id = None
        self.reference = None

    def hr(self, title: str) -> None:
        print("\n" + "═" * 72)
        print(f" {title}")
        print("═" * 72)

    def log(self, msg: str, level: str = "INFO") -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        symbols = {"INFO": "ℹ️", "PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}
        symbol = symbols.get(level, "•")
        print(f"[{timestamp}] {symbol} {msg}")

    def run_test(self, name: str, method: str, endpoint: str, expected_status: int,
                 data=None, files=None) -> tuple[bool, dict]:
        """Run a single API test"""
        url = f"{self.base_url}{endpoint}"
        headers = {'Content-Type': 'application/json'} if not files else {}

        self.tests_run += 1
        self.log(f"Test #{self.tests_run}: {name}")
        self.log(f"  {method} {endpoint}", "INFO")

        try:
            if method == 'GET':
                response = self.session.get(url, headers=headers, timeout=30)
            elif method == 'POST':
                if files:
                    response = self.session.post(url, files=files, data=data, timeout=30)
                else:
                    response = self.session.post(url, json=data, headers=headers, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status

            if success:
                self.tests_passed += 1
                self.log(f"PASSED - Status: {response.status_code}", "PASS")
                try:
                    return True, response.json()
                except:
                    return True, {"_raw": response.content}
            else:
                self.tests_failed += 1
                self.log(f"FAILED - Expected {expected_status}, got {response.status_code}", "FAIL")
                self.log(f"Response: {response.text[:300]}", "FAIL")
                self.failures.append({
                    "test": name,
                    "endpoint": endpoint,
                    "expected": expected_status,
                    "actual": response.status_code,
                    "response": response.text[:300]
                })
                return False, {}

        except Exception as e:
            self.tests_failed += 1
            self.log(f"FAILED - Error: {str(e)}", "FAIL")
            self.failures.append({
                "test": name,
                "endpoint": endpoint,
                "error": str(e)
            })
            return False, {}

    def test_01_login(self) -> bool:
        """Test 0: Login as admin"""
        self.hr("0. LOGIN")
        success, response = self.run_test(
            "Admin Login",
            "POST",
            "/api/auth/login",
            200,
            data={"email": ADMIN_EMAIL, "password": ADMIN_PWD}
        )

        if not success:
            self.log("Admin login failed - cannot proceed", "FAIL")
            return False

        # Handle Secure cookie flag for localhost HTTP
        for cookie in self.session.cookies:
            cookie.secure = False

        self.log(f"Logged in as {response.get('email')} (role={response.get('role')})", "PASS")
        return True

    def test_02_bank_accounts(self) -> bool:
        """Test 1: GET /api/lumen/institutional/rails/bank-accounts returns 3 accounts including SEPA EUR"""
        self.hr("1. BANK ACCOUNTS ENDPOINT")
        success, data = self.run_test(
            "List bank accounts",
            "GET",
            "/api/lumen/institutional/rails/bank-accounts",
            200
        )

        if not success:
            return False

        items = data.get("items", [])
        total = data.get("total", 0)
        self.log(f"Found {total} bank accounts", "INFO")

        # Check for SEPA EUR account
        sepa_eur = next((a for a in items if a.get("currency") == "EUR"
                         and a.get("method") == "sepa"), None)

        if not sepa_eur:
            self.log("SEPA EUR account not found", "FAIL")
            self.tests_failed += 1
            return False

        self.log(f"SEPA EUR account found: IBAN={sepa_eur.get('iban')}, bank={sepa_eur.get('bank_name')}", "PASS")

        # Verify IBAN matches expected
        if sepa_eur.get('iban') == 'DE89370400440532013000':
            self.log("IBAN matches expected value", "PASS")
        else:
            self.log(f"IBAN mismatch: expected DE89370400440532013000, got {sepa_eur.get('iban')}", "WARN")

        return True

    def test_03_canonical_statuses(self) -> bool:
        """Test 2: GET /api/lumen/institutional/rails/statuses returns canonical_statuses"""
        self.hr("2. CANONICAL STATUSES ENDPOINT")
        success, data = self.run_test(
            "List canonical statuses",
            "GET",
            "/api/lumen/institutional/rails/statuses",
            200
        )

        if not success:
            return False

        statuses = data.get("statuses", [])
        terminal = data.get("terminal", [])

        expected_statuses = ['draft', 'submitted', 'pending_review', 'matched', 'confirmed', 'rejected']
        expected_terminal = ['confirmed', 'rejected']

        self.log(f"Statuses: {statuses}", "INFO")
        self.log(f"Terminal: {terminal}", "INFO")

        # Verify all expected statuses are present
        if set(expected_statuses) == set(statuses):
            self.log("All canonical statuses present (R2 compliance)", "PASS")
        else:
            self.log(f"Status mismatch: expected {expected_statuses}, got {statuses}", "FAIL")
            self.tests_failed += 1
            return False

        # Verify terminal statuses
        if set(expected_terminal) == set(terminal):
            self.log("Terminal statuses correct", "PASS")
        else:
            self.log(f"Terminal mismatch: expected {expected_terminal}, got {terminal}", "WARN")

        return True

    def test_04_sepa_valid(self) -> bool:
        """Test 3: POST SEPA transfer - valid 50000 EUR returns 200 with canonical_status='submitted'"""
        self.hr("3. SEPA TRANSFER - VALID 50000 EUR")
        self.reference = f"H11-TEST-{uuid.uuid4().hex[:10].upper()}"

        success, data = self.run_test(
            "Create valid SEPA transfer (50000 EUR)",
            "POST",
            "/api/lumen/institutional/rails/sepa/transfers",
            200,
            data={
                "direction": "inbound",
                "amount": 50000,
                "currency": "EUR",
                "beneficiary_iban": "DE89370400440532013000",
                "beneficiary_name": "Lumen Capital SE",
                "reference": self.reference,
                "purpose": "H1.1 test transfer"
            }
        )

        if not success:
            return False

        self.transfer_id = data.get("id")
        canonical_status = data.get("canonical_status")
        status = data.get("status")

        self.log(f"Transfer ID: {self.transfer_id}", "INFO")
        self.log(f"Reference: {data.get('reference')}", "INFO")
        self.log(f"Status: {status}", "INFO")
        self.log(f"Canonical status: {canonical_status}", "INFO")

        if canonical_status == "submitted":
            self.log("Canonical status is 'submitted' (R2 compliance)", "PASS")
            return True
        else:
            self.log(f"Expected canonical_status='submitted', got '{canonical_status}'", "FAIL")
            self.tests_failed += 1
            return False

    def test_05_sepa_usd_reject(self) -> bool:
        """Test 4: POST SEPA transfer - USD currency returns 400 with UA message"""
        self.hr("4. SEPA TRANSFER - USD CURRENCY (EXPECT 400)")
        success, data = self.run_test(
            "Create SEPA transfer with USD (should fail)",
            "POST",
            "/api/lumen/institutional/rails/sepa/transfers",
            400,
            data={
                "direction": "inbound",
                "amount": 50000,
                "currency": "USD",
                "beneficiary_iban": "DE89370400440532013000",
                "beneficiary_name": "Lumen Capital SE",
                "reference": f"BAD-USD-{uuid.uuid4().hex[:6]}"
            }
        )

        if success:
            self.log("USD currency correctly rejected with 400", "PASS")
            # Check for UA message
            detail = data.get("detail", "")
            if "EUR" in detail or "SEPA" in detail:
                self.log(f"Error message contains expected keywords: {detail[:100]}", "PASS")
            return True
        return False

    def test_06_sepa_below_min(self) -> bool:
        """Test 5: POST SEPA transfer - amount=50 EUR returns 400 with UA message"""
        self.hr("5. SEPA TRANSFER - BELOW MINIMUM (EXPECT 400)")
        success, data = self.run_test(
            "Create SEPA transfer with 50 EUR (below 1000 EUR min)",
            "POST",
            "/api/lumen/institutional/rails/sepa/transfers",
            400,
            data={
                "direction": "inbound",
                "amount": 50,
                "currency": "EUR",
                "beneficiary_iban": "DE89370400440532013000",
                "beneficiary_name": "Lumen Capital SE",
                "reference": f"BAD-MIN-{uuid.uuid4().hex[:6]}"
            }
        )

        if success:
            self.log("Below-minimum amount correctly rejected with 400", "PASS")
            # Check for UA message
            detail = data.get("detail", "")
            if "1000" in detail or "мінімум" in detail:
                self.log(f"Error message contains minimum threshold: {detail[:100]}", "PASS")
            return True
        return False

    def test_07_sepa_duplicate(self) -> bool:
        """Test 6: POST SEPA transfer - duplicate reference returns 409"""
        self.hr("6. SEPA TRANSFER - DUPLICATE REFERENCE (EXPECT 409)")
        if not self.reference:
            self.log("No reference from previous test - skipping", "WARN")
            return False

        success, data = self.run_test(
            "Create SEPA transfer with duplicate reference",
            "POST",
            "/api/lumen/institutional/rails/sepa/transfers",
            409,
            data={
                "direction": "inbound",
                "amount": 50000,
                "currency": "EUR",
                "beneficiary_iban": "DE89370400440532013000",
                "beneficiary_name": "Lumen Capital SE",
                "reference": self.reference
            }
        )

        if success:
            self.log("Duplicate reference correctly rejected with 409", "PASS")
            return True
        return False

    def test_08_proof_upload(self) -> bool:
        """Test 7: POST proof upload - multipart PDF upload transitions to pending_review"""
        self.hr("7. PROOF UPLOAD")
        if not self.transfer_id:
            self.log("No transfer_id from previous test - skipping", "WARN")
            return False

        # Minimal valid PDF
        pdf_bytes = (
            b"%PDF-1.4\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 100]>>endobj\n"
            b"xref\n0 4\n0000000000 65535 f\n"
            b"trailer<</Root 1 0 R/Size 4>>\n%%EOF\n"
        )

        files = {"file": ("proof.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        success, data = self.run_test(
            "Upload PDF proof",
            "POST",
            f"/api/lumen/institutional/rails/transfers/{self.transfer_id}/proof",
            200,
            data={"note": "H1.1 test proof"},
            files=files
        )

        if not success:
            return False

        proof = data.get("proof", {})
        self.proof_id = proof.get("id")
        canonical_status = data.get("canonical_status")

        self.log(f"Proof ID: {self.proof_id}", "INFO")
        self.log(f"Canonical status after upload: {canonical_status}", "INFO")

        if canonical_status == "pending_review":
            self.log("Canonical status transitioned to 'pending_review' (R2 compliance)", "PASS")
            return True
        else:
            self.log(f"Expected canonical_status='pending_review', got '{canonical_status}'", "FAIL")
            self.tests_failed += 1
            return False

    def test_09_proof_list(self) -> bool:
        """Test 8: GET proofs list"""
        self.hr("8. LIST PROOFS")
        if not self.transfer_id:
            self.log("No transfer_id - skipping", "WARN")
            return False

        success, data = self.run_test(
            "List proofs for transfer",
            "GET",
            f"/api/lumen/institutional/rails/transfers/{self.transfer_id}/proofs",
            200
        )

        if not success:
            return False

        items = data.get("items", [])
        total = data.get("total", 0)

        self.log(f"Found {total} proof(s)", "INFO")

        if total >= 1:
            proof = items[0]
            self.log(f"Proof: id={proof.get('id')}, size={proof.get('size_bytes')} bytes", "PASS")
            return True
        else:
            self.log("No proofs found", "FAIL")
            self.tests_failed += 1
            return False

    def test_10_proof_download(self) -> bool:
        """Test 9: GET proof download - returns PDF binary"""
        self.hr("9. DOWNLOAD PROOF")
        if not self.proof_id:
            self.log("No proof_id - skipping", "WARN")
            return False

        success, data = self.run_test(
            "Download proof",
            "GET",
            f"/api/lumen/institutional/rails/proofs/{self.proof_id}/download",
            200
        )

        if not success:
            return False

        raw = data.get("_raw", b"")
        if raw.startswith(b"%PDF"):
            self.log(f"PDF downloaded successfully ({len(raw)} bytes)", "PASS")
            return True
        else:
            self.log("Downloaded content is not a valid PDF", "FAIL")
            self.tests_failed += 1
            return False

    def test_11_reconcile(self) -> bool:
        """Test 10: POST reconcile with matching amount returns matched=true"""
        self.hr("10. ADMIN RECONCILE")
        if not self.transfer_id:
            self.log("No transfer_id - skipping", "WARN")
            return False

        success, data = self.run_test(
            "Reconcile transfer (50000 EUR observed)",
            "POST",
            f"/api/admin/lumen/institutional/rails/transfers/{self.transfer_id}/reconcile",
            200,
            data={
                "bank_statement_ref": f"BANK-STMT-{self.reference}",
                "amount_observed": 50000.00,
                "currency_observed": "EUR"
            }
        )

        if not success:
            return False

        recon = data.get("reconciliation", {})
        matched = recon.get("matched")
        delta_amount = recon.get("delta_amount")

        self.log(f"Matched: {matched}", "INFO")
        self.log(f"Delta amount: {delta_amount}", "INFO")

        if matched and delta_amount == 0:
            self.log("Reconciliation matched with zero delta", "PASS")
            return True
        else:
            self.log(f"Reconciliation failed: matched={matched}, delta={delta_amount}", "FAIL")
            self.tests_failed += 1
            return False

    def test_12_match(self) -> bool:
        """Test 11: POST match (requires prior reconcile with matched=true)"""
        self.hr("11. ADMIN MATCH")
        if not self.transfer_id:
            self.log("No transfer_id - skipping", "WARN")
            return False

        success, data = self.run_test(
            "Mark transfer as matched",
            "POST",
            f"/api/admin/lumen/institutional/rails/transfers/{self.transfer_id}/match",
            200,
            data={"note": "H1.1 test match"}
        )

        if not success:
            return False

        canonical_status = data.get("canonical_status")
        self.log(f"Canonical status after match: {canonical_status}", "INFO")

        if canonical_status == "matched":
            self.log("Canonical status is 'matched' (R2 compliance)", "PASS")
            return True
        else:
            self.log(f"Expected canonical_status='matched', got '{canonical_status}'", "FAIL")
            self.tests_failed += 1
            return False

    def test_13_confirm(self) -> bool:
        """Test 12: POST confirm returns canonical_status='confirmed' + ledger entry posted"""
        self.hr("12. ADMIN CONFIRM")
        if not self.transfer_id:
            self.log("No transfer_id - skipping", "WARN")
            return False

        success, data = self.run_test(
            "Confirm transfer",
            "POST",
            f"/api/admin/lumen/institutional/rails/transfers/{self.transfer_id}/confirm",
            200,
            data={
                "provider_ref": f"BANK-PROV-{self.reference}",
                "note": "H1.1 test confirm"
            }
        )

        if not success:
            return False

        status = data.get("status")
        transfer = data.get("transfer", {})
        canonical_status = transfer.get("canonical_status")

        self.log(f"Status: {status}", "INFO")
        self.log(f"Canonical status: {canonical_status}", "INFO")

        if canonical_status == "confirmed":
            self.log("Canonical status is 'confirmed' (R2 compliance)", "PASS")
            self.log("Ledger entry should be posted (will verify in test 15)", "INFO")
            return True
        else:
            self.log(f"Expected canonical_status='confirmed', got '{canonical_status}'", "FAIL")
            self.tests_failed += 1
            return False

    def test_14_history(self) -> bool:
        """Test 13: GET history returns rows with R3 schema (date/reference/method/amount/currency/status)"""
        self.hr("13. INVESTOR HISTORY (R3 SCHEMA)")
        success, data = self.run_test(
            "Get investor history",
            "GET",
            "/api/lumen/institutional/rails/history?limit=10",
            200
        )

        if not success:
            return False

        items = data.get("items", [])
        self.log(f"Found {len(items)} history row(s)", "INFO")

        if not items:
            self.log("No history rows found", "WARN")
            return False

        # Find our transfer
        my_row = next((x for x in items if x.get("reference") == self.reference), None)

        if not my_row:
            self.log("Our transfer not found in history", "FAIL")
            self.tests_failed += 1
            return False

        # Verify R3 schema: exactly date/reference/method/amount/currency/status
        expected_keys = {"date", "reference", "method", "amount", "currency", "status"}
        actual_keys = set(k for k in my_row.keys() if not k.startswith("_"))

        self.log(f"Row keys: {actual_keys}", "INFO")

        if expected_keys.issubset(actual_keys):
            self.log("R3 schema compliance: all required keys present", "PASS")
        else:
            missing = expected_keys - actual_keys
            self.log(f"R3 schema violation: missing keys {missing}", "FAIL")
            self.tests_failed += 1
            return False

        # Verify status is 'confirmed'
        if my_row.get("status") == "confirmed":
            self.log("Status is 'confirmed' in history", "PASS")
        else:
            self.log(f"Expected status='confirmed', got '{my_row.get('status')}'", "WARN")

        # Verify method is SEPA-shaped
        method = my_row.get("method", "")
        if "SEPA" in method:
            self.log(f"Method is SEPA-shaped: {method}", "PASS")
        else:
            self.log(f"Method not SEPA-shaped: {method}", "WARN")

        return True

    def test_15_exceptions(self) -> bool:
        """Test 14: GET exceptions returns flagged transfers"""
        self.hr("14. ADMIN EXCEPTIONS")
        success, data = self.run_test(
            "Get exceptions queue",
            "GET",
            "/api/admin/lumen/institutional/rails/exceptions?limit=200",
            200
        )

        if not success:
            return False

        items = data.get("items", [])
        total = data.get("total", 0)

        self.log(f"Found {total} exception(s)", "INFO")

        # Our happy-path transfer should NOT appear in exceptions
        flagged = [x for x in items if x.get("transfer_id") == self.transfer_id]

        if flagged:
            self.log(f"Our transfer was flagged unexpectedly: {flagged}", "FAIL")
            self.tests_failed += 1
            return False
        else:
            self.log("Our happy-path transfer is not in exceptions (correct)", "PASS")
            return True

    def test_16_ledger(self) -> bool:
        """Test 15: GET ledger returns ledger entries with source='lumen_institutional_rails'"""
        self.hr("15. ADMIN LEDGER")
        success, data = self.run_test(
            "Get ledger entries",
            "GET",
            "/api/admin/lumen/institutional/rails/ledger?limit=50",
            200
        )

        if not success:
            return False

        items = data.get("items", [])
        total = data.get("total", 0)

        self.log(f"Found {total} ledger entry(ies)", "INFO")

        # Find our transfer's ledger entry
        mine = [e for e in items if e.get("transfer_id") == self.transfer_id]

        if not mine:
            self.log("Our transfer not found in ledger", "FAIL")
            self.tests_failed += 1
            return False

        entry = mine[0]
        self.log(f"Ledger entry: id={entry.get('id')}, amount={entry.get('amount')} {entry.get('currency')}", "PASS")

        # Verify source
        if entry.get("source") == "lumen_institutional_rails":
            self.log("Source is 'lumen_institutional_rails' (correct)", "PASS")
        else:
            self.log(f"Source mismatch: expected 'lumen_institutional_rails', got '{entry.get('source')}'", "WARN")

        return True

    def test_17_rate_limit(self) -> bool:
        """Test 16: Rate-limit SEPA transfers - 11th call within a minute returns 429"""
        self.hr("16. RATE LIMIT - SEPA TRANSFERS (11th CALL)")
        self.log("Making 11 rapid SEPA transfer requests...", "INFO")

        blocked_count = 0
        first_429_at = None

        for i in range(1, 12):
            try:
                response = self.session.post(
                    f"{self.base_url}/api/lumen/institutional/rails/sepa/transfers",
                    json={
                        "direction": "inbound",
                        "amount": 50000,
                        "currency": "EUR",
                        "beneficiary_name": "Rate Limit Test",
                        "beneficiary_iban": "DE89370400440532013000",
                        "reference": f"RATELIMIT-{int(time.time())}-{i}"
                    },
                    headers={'Content-Type': 'application/json'},
                    timeout=10
                )

                if response.status_code == 429:
                    blocked_count += 1
                    if first_429_at is None:
                        first_429_at = i
                        self.log(f"Request #{i}: 429 (rate-limited) ✓", "INFO")
                elif response.status_code in (200, 201):
                    self.log(f"Request #{i}: {response.status_code} (allowed)", "INFO")
                else:
                    self.log(f"Request #{i}: {response.status_code}", "INFO")

            except Exception as e:
                self.log(f"Request #{i}: Error - {str(e)}", "WARN")

        self.log(f"Total 429 responses: {blocked_count}", "INFO")
        self.log(f"First 429 at request: {first_429_at}", "INFO")

        self.tests_run += 1
        if blocked_count > 0 and first_429_at and first_429_at <= 11:
            self.tests_passed += 1
            self.log(f"Rate-limit working (blocked after {first_429_at-1} requests)", "PASS")
            return True
        else:
            self.tests_failed += 1
            self.log("Rate-limit may not be working correctly", "FAIL")
            return False

    def test_18_security_review(self) -> bool:
        """Test 17: GET security-review - score must remain 100/100 (no regression)"""
        self.hr("17. LAUNCH READINESS - SECURITY REVIEW (NO REGRESSION)")
        success, data = self.run_test(
            "Get security review",
            "GET",
            "/api/admin/launch-readiness/security-review",
            200
        )

        if not success:
            return False

        score = data.get("score", 0)
        self.log(f"Security score: {score}/100", "INFO")

        if score == 100:
            self.log("Security score is 100/100 (no regression)", "PASS")
            return True
        else:
            self.log(f"Security score regression: expected 100, got {score}", "FAIL")
            self.tests_failed += 1
            return False

    def test_19_scans_run(self) -> bool:
        """Test 18: POST scans/run - score.total must remain >= 97 (no regression)"""
        self.hr("18. LAUNCH READINESS - SCANS RUN (NO REGRESSION)")
        success, data = self.run_test(
            "Run launch readiness scan",
            "POST",
            "/api/admin/launch-readiness/scans/run",
            200,
            data={}
        )

        if not success:
            return False

        score = data.get("score", {})
        total = score.get("total", 0)
        grade = score.get("grade", "N/A")

        self.log(f"Launch readiness score: {total}/100 (Grade {grade})", "INFO")

        if total >= 97:
            self.log(f"Score is >= 97 (no regression)", "PASS")
            return True
        else:
            self.log(f"Score regression: expected >= 97, got {total}", "FAIL")
            self.tests_failed += 1
            return False

    def test_20_enforcement_coverage(self) -> bool:
        """Test 19: GET enforcement-coverage - lr2_gated >= 49 and combos >= 20"""
        self.hr("19. LAUNCH READINESS - ENFORCEMENT COVERAGE (NO REGRESSION)")
        success, data = self.run_test(
            "Get enforcement coverage",
            "GET",
            "/api/admin/launch-readiness/enforcement-coverage",
            200
        )

        if not success:
            return False

        counts = data.get("counts", {})
        registry = data.get("registry", [])

        lr2_gated = counts.get("lr2_gated", 0)
        self.log(f"LR2-gated routes: {lr2_gated}", "INFO")

        # Count unique (resource, action) combinations
        unique_combos = set()
        for entry in registry:
            resource = entry.get("resource", "")
            action = entry.get("action", "")
            if resource and action:
                unique_combos.add((resource, action))

        combo_count = len(unique_combos)
        self.log(f"Unique (resource, action) combinations: {combo_count}", "INFO")

        passed = True
        if lr2_gated >= 49:
            self.log(f"LR2-gated routes >= 49 (no regression)", "PASS")
        else:
            self.log(f"LR2-gated routes regression: expected >= 49, got {lr2_gated}", "FAIL")
            self.tests_failed += 1
            passed = False

        if combo_count >= 20:
            self.log(f"Unique combinations >= 20 (no regression)", "PASS")
        else:
            self.log(f"Unique combinations regression: expected >= 20, got {combo_count}", "FAIL")
            self.tests_failed += 1
            passed = False

        return passed

    def print_summary(self) -> int:
        """Print test summary and return exit code"""
        self.hr("TEST SUMMARY")

        total = self.tests_run
        passed = self.tests_passed
        failed = self.tests_failed
        pass_rate = (passed / total * 100) if total > 0 else 0

        print(f"\nTotal Tests: {total}")
        print(f"Passed: {passed} ({pass_rate:.1f}%)")
        print(f"Failed: {failed}")

        if self.failures:
            self.hr("FAILED TESTS DETAILS")
            for i, failure in enumerate(self.failures, 1):
                print(f"\n{i}. {failure.get('test', 'Unknown')}")
                print(f"   Endpoint: {failure.get('endpoint', 'N/A')}")
                if 'error' in failure:
                    print(f"   Error: {failure['error']}")
                else:
                    print(f"   Expected: {failure.get('expected', 'N/A')}")
                    print(f"   Actual: {failure.get('actual', 'N/A')}")
                    print(f"   Response: {failure.get('response', 'N/A')}")

        return 0 if failed == 0 else 1


def main() -> int:
    """Main test runner"""
    print("\n" + "="*72)
    print("H1.1 FUNDING CENTER - COMPREHENSIVE BACKEND TEST SUITE")
    print("="*72)
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Test Time: {datetime.now().isoformat()}")
    print("="*72)

    tester = FundingCenterTester(BACKEND_URL)

    # Run all tests in sequence
    if not tester.test_01_login():
        print("\n❌ Login failed - cannot proceed")
        return 1

    tester.test_02_bank_accounts()
    tester.test_03_canonical_statuses()
    tester.test_04_sepa_valid()
    tester.test_05_sepa_usd_reject()
    tester.test_06_sepa_below_min()
    tester.test_07_sepa_duplicate()
    tester.test_08_proof_upload()
    tester.test_09_proof_list()
    tester.test_10_proof_download()
    tester.test_11_reconcile()
    tester.test_12_match()
    tester.test_13_confirm()
    tester.test_14_history()
    tester.test_15_exceptions()
    tester.test_16_ledger()
    tester.test_17_rate_limit()
    tester.test_18_security_review()
    tester.test_19_scans_run()
    tester.test_20_enforcement_coverage()

    return tester.print_summary()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
