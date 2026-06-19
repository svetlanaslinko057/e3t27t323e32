"""
Sprint 10 — Production Hardening Backend Test Suite

Tests all hardening endpoints:
- System Health (11 cards)
- Consistency checks (I1-I10)
- Permissions matrix (45 actions, 6 roles)
- Audit Trail (log, categories, export)
- Monitoring (DB, queues, storage, failures)
- Backups (create, list, verify, delete)
- Storage audit
- Disaster Recovery checks
- Error tracking status
- Rate limiting (429 after 30 requests)
- IDOR protection (401/403)
- Audit writes on asset CRUD
"""
import requests
import sys
import time
from datetime import datetime

# Public endpoint from frontend/.env
BASE_URL = "https://dev-workspace-251.preview.emergentagent.com/api"

class Sprint10Tester:
    def __init__(self):
        self.base_url = BASE_URL
        self.admin_cookie = None
        self.investor_cookie = None
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []

    def log(self, msg, level="INFO"):
        print(f"[{level}] {msg}")

    def test(self, name, method, endpoint, expected_status, data=None, cookies=None, params=None):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {'Content-Type': 'application/json'}
        
        self.tests_run += 1
        self.log(f"Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, cookies=cookies, params=params, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, cookies=cookies, params=params, timeout=10)
            elif method == 'PATCH':
                response = requests.patch(url, json=data, headers=headers, cookies=cookies, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, cookies=cookies, timeout=10)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                self.log(f"✅ PASS - {name} (status: {response.status_code})", "PASS")
                return True, response
            else:
                self.tests_failed += 1
                self.failures.append(f"{name}: Expected {expected_status}, got {response.status_code}")
                self.log(f"❌ FAIL - {name}: Expected {expected_status}, got {response.status_code}", "FAIL")
                self.log(f"   Response: {response.text[:200]}", "FAIL")
                return False, response

        except Exception as e:
            self.tests_failed += 1
            self.failures.append(f"{name}: {str(e)}")
            self.log(f"❌ FAIL - {name}: {str(e)}", "FAIL")
            return False, None

    def login_admin(self):
        """Login as admin and store cookie"""
        self.log("=== Admin Login ===")
        success, response = self.test(
            "Admin Quick Login",
            "POST",
            "/auth/quick",
            200,
            data={"email": "admin@atlas.dev"}
        )
        if success and response:
            # Extract session_token cookie
            cookies = response.cookies
            if 'session_token' in cookies:
                self.admin_cookie = {'session_token': cookies['session_token']}
                self.log(f"Admin cookie obtained: {self.admin_cookie['session_token'][:20]}...")
                return True
        self.log("Failed to obtain admin cookie", "ERROR")
        return False

    def login_investor(self):
        """Login as investor (client role) for IDOR tests"""
        self.log("=== Investor Login ===")
        success, response = self.test(
            "Investor Quick Login",
            "POST",
            "/auth/quick",
            200,
            data={"email": "client@atlas.dev"}
        )
        if success and response:
            cookies = response.cookies
            if 'session_token' in cookies:
                self.investor_cookie = {'session_token': cookies['session_token']}
                self.log(f"Investor cookie obtained: {self.investor_cookie['session_token'][:20]}...")
                return True
        self.log("Failed to obtain investor cookie", "ERROR")
        return False

    def test_system_health(self):
        """Test GET /api/admin/system-health returns 200 with 11 cards"""
        self.log("\n=== System Health ===")
        success, response = self.test(
            "System Health - Admin",
            "GET",
            "/admin/system-health",
            200,
            cookies=self.admin_cookie
        )
        if success and response:
            data = response.json()
            cards = data.get('cards', [])
            expected_keys = {'consistency', 'db', 'queues', 'storage', 'file_audit', 
                           'failures', 'security', 'dr', 'backups', 'audit', 'error_tracking'}
            actual_keys = {c['key'] for c in cards}
            if actual_keys == expected_keys:
                self.log(f"✅ All 11 cards present: {actual_keys}", "PASS")
            else:
                missing = expected_keys - actual_keys
                extra = actual_keys - expected_keys
                self.log(f"❌ Card mismatch. Missing: {missing}, Extra: {extra}", "FAIL")
                self.failures.append(f"System Health cards mismatch")

    def test_consistency_checks(self):
        """Test consistency checks (I1-I10)"""
        self.log("\n=== Consistency Checks ===")
        success, response = self.test(
            "Consistency Check - All",
            "GET",
            "/admin/consistency/check",
            200,
            cookies=self.admin_cookie
        )
        if success and response:
            data = response.json()
            checks = data.get('checks', [])
            expected_codes = {f'I{i}' for i in range(1, 11)}
            actual_codes = {c['code'] for c in checks}
            if actual_codes == expected_codes:
                self.log(f"✅ All 10 invariants present: {actual_codes}", "PASS")
            else:
                missing = expected_codes - actual_codes
                self.log(f"❌ Missing invariants: {missing}", "FAIL")
                self.failures.append(f"Consistency checks incomplete")

        # Test single check
        self.test(
            "Consistency Check - I1",
            "GET",
            "/admin/consistency/check/I1",
            200,
            cookies=self.admin_cookie
        )

    def test_permissions(self):
        """Test permissions matrix and audit"""
        self.log("\n=== Permissions ===")
        success, response = self.test(
            "Permissions Matrix",
            "GET",
            "/admin/permissions/matrix",
            200,
            cookies=self.admin_cookie
        )
        if success and response:
            data = response.json()
            matrix = data.get('matrix', [])
            roles = data.get('roles', [])
            expected_roles = {'investor', 'asset_manager', 'compliance', 'finance', 'admin', 'system'}
            actual_roles = set(roles)
            if actual_roles == expected_roles:
                self.log(f"✅ All 6 roles present", "PASS")
            else:
                self.log(f"❌ Role mismatch. Expected: {expected_roles}, Got: {actual_roles}", "FAIL")
            
            if len(matrix) >= 45:
                self.log(f"✅ Matrix has {len(matrix)} actions (≥45)", "PASS")
            else:
                self.log(f"❌ Matrix has only {len(matrix)} actions (expected ≥45)", "FAIL")

        self.test(
            "Permissions Audit",
            "GET",
            "/admin/permissions/audit",
            200,
            cookies=self.admin_cookie
        )

    def test_audit_trail(self):
        """Test audit trail endpoints"""
        self.log("\n=== Audit Trail ===")
        self.test(
            "Audit Log",
            "GET",
            "/admin/audit/log",
            200,
            cookies=self.admin_cookie,
            params={'limit': 50}
        )
        
        self.test(
            "Audit Categories",
            "GET",
            "/admin/audit/categories",
            200,
            cookies=self.admin_cookie
        )
        
        self.test(
            "Audit Export CSV",
            "GET",
            "/admin/audit/export.csv",
            200,
            cookies=self.admin_cookie,
            params={'since_hours': 24}
        )

    def test_monitoring(self):
        """Test monitoring endpoints"""
        self.log("\n=== Monitoring ===")
        self.test(
            "DB Latency",
            "GET",
            "/admin/monitoring/db",
            200,
            cookies=self.admin_cookie
        )
        
        success, response = self.test(
            "Queue Health",
            "GET",
            "/admin/monitoring/queues",
            200,
            cookies=self.admin_cookie
        )
        if success and response:
            data = response.json()
            queues = data.get('queues', [])
            if len(queues) >= 6:
                self.log(f"✅ Found {len(queues)} queues (≥6)", "PASS")
            else:
                self.log(f"❌ Only {len(queues)} queues found (expected ≥6)", "FAIL")
        
        self.test(
            "Storage Usage",
            "GET",
            "/admin/monitoring/storage",
            200,
            cookies=self.admin_cookie
        )
        
        self.test(
            "Payout Failures",
            "GET",
            "/admin/monitoring/payout-failures",
            200,
            cookies=self.admin_cookie,
            params={'hours': 24}
        )

    def test_backups(self):
        """Test backup operations"""
        self.log("\n=== Backups ===")
        
        # List backups
        success, response = self.test(
            "List Backups",
            "GET",
            "/admin/backups",
            200,
            cookies=self.admin_cookie
        )
        initial_count = 0
        if success and response:
            data = response.json()
            initial_count = len(data.get('items', []))
            self.log(f"Initial backup count: {initial_count}")
        
        # Create backup
        success, response = self.test(
            "Create Backup",
            "POST",
            "/admin/backups",
            200,
            cookies=self.admin_cookie,
            params={'label': 'test-sprint10'}
        )
        
        backup_id = None
        if success and response:
            data = response.json()
            backup_id = data.get('manifest', {}).get('id')
            self.log(f"Created backup: {backup_id}")
        
        # List again to verify
        success, response = self.test(
            "List Backups After Create",
            "GET",
            "/admin/backups",
            200,
            cookies=self.admin_cookie
        )
        if success and response:
            data = response.json()
            new_count = len(data.get('items', []))
            if new_count > initial_count:
                self.log(f"✅ Backup count increased: {initial_count} → {new_count}", "PASS")
            else:
                self.log(f"❌ Backup count did not increase", "FAIL")
        
        # Verify backup
        if backup_id:
            self.test(
                "Verify Backup",
                "GET",
                f"/admin/backups/{backup_id}/verify",
                200,
                cookies=self.admin_cookie
            )
            
            # Delete backup
            self.test(
                "Delete Backup",
                "DELETE",
                f"/admin/backups/{backup_id}",
                200,
                cookies=self.admin_cookie
            )

    def test_storage_audit(self):
        """Test storage audit"""
        self.log("\n=== Storage Audit ===")
        self.test(
            "Storage Audit",
            "GET",
            "/admin/storage/audit",
            200,
            cookies=self.admin_cookie
        )

    def test_disaster_recovery(self):
        """Test DR checks"""
        self.log("\n=== Disaster Recovery ===")
        self.test(
            "DR Check",
            "GET",
            "/admin/disaster-recovery/check",
            200,
            cookies=self.admin_cookie
        )

    def test_error_tracking(self):
        """Test error tracking status"""
        self.log("\n=== Error Tracking ===")
        success, response = self.test(
            "Error Tracking Status",
            "GET",
            "/admin/error-tracking/status",
            200,
            cookies=self.admin_cookie
        )
        if success and response:
            data = response.json()
            if data.get('initialised') == False and data.get('provider') is None:
                self.log("✅ Error tracking correctly shows disabled (no DSN)", "PASS")
            else:
                self.log(f"⚠️  Error tracking state: {data}", "WARN")

    def test_rate_limiting(self):
        """Test rate limiting - 429 after 30 requests in 60s"""
        self.log("\n=== Rate Limiting ===")
        self.log("Sending 35 requests to /api/auth/quick to trigger rate limit...")
        
        hit_429 = False
        for i in range(1, 36):
            try:
                response = requests.post(
                    f"{self.base_url}/auth/quick",
                    json={"email": "test@example.com"},
                    timeout=5
                )
                if response.status_code == 429:
                    self.log(f"✅ Rate limit triggered at request #{i} (status: 429)", "PASS")
                    data = response.json()
                    if data.get('code') == 'rate_limit_exceeded' and data.get('limit') == 30:
                        self.log(f"✅ Rate limit response correct: {data}", "PASS")
                        self.tests_passed += 1
                    hit_429 = True
                    break
                elif i % 10 == 0:
                    self.log(f"Request #{i}: {response.status_code}")
            except Exception as e:
                self.log(f"Request #{i} failed: {e}", "WARN")
        
        self.tests_run += 1
        if not hit_429:
            self.tests_failed += 1
            self.failures.append("Rate limiting: Did not receive 429 after 35 requests")
            self.log("❌ FAIL - Rate limit not triggered", "FAIL")

    def test_idor_protection(self):
        """Test IDOR protection - 401 anon, 403 investor, 200 admin"""
        self.log("\n=== IDOR Protection ===")
        
        # Anonymous (no cookie) → 401
        self.test(
            "System Health - Anonymous (401)",
            "GET",
            "/admin/system-health",
            401,
            cookies=None
        )
        
        # Investor (client role) → 403
        self.test(
            "System Health - Investor (403)",
            "GET",
            "/admin/system-health",
            403,
            cookies=self.investor_cookie
        )
        
        # Admin → 200 (already tested, but verify again)
        self.test(
            "System Health - Admin (200)",
            "GET",
            "/admin/system-health",
            200,
            cookies=self.admin_cookie
        )
        
        # Audit log IDOR
        self.test(
            "Audit Log - Anonymous (401)",
            "GET",
            "/admin/audit/log",
            401,
            cookies=None
        )
        
        self.test(
            "Audit Log - Investor (403)",
            "GET",
            "/admin/audit/log",
            403,
            cookies=self.investor_cookie
        )

    def test_audit_writes(self):
        """Test audit trail writes on asset CRUD operations"""
        self.log("\n=== Audit Trail Writes ===")
        
        # Get initial audit count
        success, response = self.test(
            "Audit Log - Before Asset Create",
            "GET",
            "/admin/audit/log",
            200,
            cookies=self.admin_cookie,
            params={'category': 'asset', 'limit': 10}
        )
        initial_count = 0
        if success and response:
            initial_count = response.json().get('total', 0)
            self.log(f"Initial asset audit count: {initial_count}")
        
        # Create asset
        asset_data = {
            "title": "Test Asset Sprint10",
            "category": "real_estate",
            "location": "Test Location",
            "description": "Test description",
            "status": "draft",
            "target_yield": 15.0,
            "horizon_months": 24,
            "min_ticket": 50000,
            "round_target": 1000000,
            "featured": False
        }
        success, response = self.test(
            "Create Asset",
            "POST",
            "/admin/assets",
            200,
            data=asset_data,
            cookies=self.admin_cookie
        )
        
        asset_id = None
        if success and response:
            asset_id = response.json().get('id')
            self.log(f"Created asset: {asset_id}")
        
        # Check audit log increased
        time.sleep(0.5)  # Brief wait for audit write
        success, response = self.test(
            "Audit Log - After Asset Create",
            "GET",
            "/admin/audit/log",
            200,
            cookies=self.admin_cookie,
            params={'category': 'asset', 'action': 'asset.create', 'limit': 10}
        )
        if success and response:
            items = response.json().get('items', [])
            if any(i.get('action') == 'asset.create' and i.get('target_id') == asset_id for i in items):
                self.log(f"✅ Audit entry found for asset.create", "PASS")
                self.tests_passed += 1
            else:
                self.log(f"❌ No audit entry for asset.create", "FAIL")
                self.tests_failed += 1
                self.failures.append("Audit write: asset.create not found")
            self.tests_run += 1
        
        # Update asset
        if asset_id:
            update_data = {**asset_data, "title": "Updated Test Asset Sprint10"}
            self.test(
                "Update Asset",
                "PATCH",
                f"/admin/assets/{asset_id}",
                200,
                data=update_data,
                cookies=self.admin_cookie
            )
            
            # Check audit
            time.sleep(0.5)
            success, response = self.test(
                "Audit Log - After Asset Update",
                "GET",
                "/admin/audit/log",
                200,
                cookies=self.admin_cookie,
                params={'category': 'asset', 'action': 'asset.update', 'limit': 10}
            )
            if success and response:
                items = response.json().get('items', [])
                if any(i.get('action') == 'asset.update' and i.get('target_id') == asset_id for i in items):
                    self.log(f"✅ Audit entry found for asset.update", "PASS")
                    self.tests_passed += 1
                else:
                    self.log(f"❌ No audit entry for asset.update", "FAIL")
                    self.tests_failed += 1
                    self.failures.append("Audit write: asset.update not found")
                self.tests_run += 1
            
            # Delete asset
            self.test(
                "Delete Asset",
                "DELETE",
                f"/admin/assets/{asset_id}",
                200,
                cookies=self.admin_cookie
            )
            
            # Check audit
            time.sleep(0.5)
            success, response = self.test(
                "Audit Log - After Asset Delete",
                "GET",
                "/admin/audit/log",
                200,
                cookies=self.admin_cookie,
                params={'category': 'asset', 'action': 'asset.delete', 'limit': 10}
            )
            if success and response:
                items = response.json().get('items', [])
                if any(i.get('action') == 'asset.delete' and i.get('target_id') == asset_id for i in items):
                    self.log(f"✅ Audit entry found for asset.delete", "PASS")
                    self.tests_passed += 1
                else:
                    self.log(f"❌ No audit entry for asset.delete", "FAIL")
                    self.tests_failed += 1
                    self.failures.append("Audit write: asset.delete not found")
                self.tests_run += 1

    def test_legacy_endpoints(self):
        """Test that legacy endpoints still work"""
        self.log("\n=== Legacy Endpoints ===")
        self.test(
            "Healthz",
            "GET",
            "/healthz",
            200
        )
        
        self.test(
            "Readyz",
            "GET",
            "/readyz",
            200
        )

    def run_all(self):
        """Run all tests"""
        self.log("=" * 60)
        self.log("Sprint 10 — Production Hardening Backend Test Suite")
        self.log(f"Base URL: {self.base_url}")
        self.log("=" * 60)
        
        # Login
        if not self.login_admin():
            self.log("CRITICAL: Admin login failed. Cannot proceed.", "ERROR")
            return False
        
        if not self.login_investor():
            self.log("WARNING: Investor login failed. IDOR tests will be skipped.", "WARN")
        
        # Run all test suites
        self.test_system_health()
        self.test_consistency_checks()
        self.test_permissions()
        self.test_audit_trail()
        self.test_monitoring()
        self.test_backups()
        self.test_storage_audit()
        self.test_disaster_recovery()
        self.test_error_tracking()
        self.test_rate_limiting()
        self.test_idor_protection()
        self.test_audit_writes()
        self.test_legacy_endpoints()
        
        # Summary
        self.log("\n" + "=" * 60)
        self.log("TEST SUMMARY")
        self.log("=" * 60)
        self.log(f"Total tests run: {self.tests_run}")
        self.log(f"✅ Passed: {self.tests_passed}")
        self.log(f"❌ Failed: {self.tests_failed}")
        
        if self.failures:
            self.log("\nFailed tests:")
            for f in self.failures:
                self.log(f"  - {f}", "FAIL")
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        self.log(f"\nSuccess rate: {success_rate:.1f}%")
        
        return self.tests_failed == 0


def main():
    tester = Sprint10Tester()
    success = tester.run_all()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
