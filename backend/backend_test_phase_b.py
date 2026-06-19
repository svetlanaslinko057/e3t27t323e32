#!/usr/bin/env python3
"""
Phase B — Asset Intelligence Layer Testing
Tests all new endpoints for Marketplace 2.0 intelligence features.
"""
import requests
import sys
import os
from datetime import datetime

# Get backend URL from environment
BACKEND_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://arch-review-25.preview.emergentagent.com')
BASE_URL = f"{BACKEND_URL}/api"

# Test asset IDs (seeded in lumen_asset_intelligence.py)
TEST_ASSETS = ['asset-podilskyi', 'asset-lavr-tc', 'asset-rivne-warehouse']
ADMIN_CREDS = {'email': 'admin@atlas.dev', 'password': 'admin123'}

class PhaseB_Tester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.session = requests.Session()
        self.admin_cookie = None

    def test(self, name, method, endpoint, expected_status, data=None, auth=False, validate=None):
        """Run a single test"""
        url = f"{BASE_URL}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        self.tests_run += 1
        print(f"\n🔍 Test {self.tests_run}: {name}")
        
        try:
            if auth and self.admin_cookie:
                # Use session with cookie
                if method == 'GET':
                    response = self.session.get(url)
                elif method == 'POST':
                    response = self.session.post(url, json=data)
                elif method == 'PATCH':
                    response = self.session.patch(url, json=data)
                elif method == 'DELETE':
                    response = self.session.delete(url)
            else:
                # No auth
                if method == 'GET':
                    response = requests.get(url, headers=headers)
                elif method == 'POST':
                    response = requests.post(url, json=data, headers=headers)
                elif method == 'PATCH':
                    response = requests.patch(url, json=data, headers=headers)
                elif method == 'DELETE':
                    response = requests.delete(url, headers=headers)

            success = response.status_code == expected_status
            
            if success:
                # Additional validation if provided
                if validate:
                    try:
                        resp_data = response.json()
                        validate(resp_data)
                        self.tests_passed += 1
                        print(f"✅ PASS - Status: {response.status_code}")
                    except AssertionError as e:
                        print(f"❌ FAIL - Validation error: {e}")
                        success = False
                    except Exception as e:
                        print(f"❌ FAIL - Validation exception: {e}")
                        success = False
                else:
                    self.tests_passed += 1
                    print(f"✅ PASS - Status: {response.status_code}")
            else:
                print(f"❌ FAIL - Expected {expected_status}, got {response.status_code}")
                try:
                    print(f"   Response: {response.text[:200]}")
                except:
                    pass

            return success, response.json() if response.status_code < 500 else {}

        except Exception as e:
            print(f"❌ FAIL - Error: {str(e)}")
            return False, {}

    def login_admin(self):
        """Login as admin and store cookie"""
        print("\n🔐 Logging in as admin...")
        url = f"{BASE_URL}/auth/login"
        response = self.session.post(url, json=ADMIN_CREDS)
        
        if response.status_code == 200:
            self.admin_cookie = True
            print("✅ Admin login successful")
            return True
        else:
            print(f"❌ Admin login failed: {response.status_code}")
            return False

    def run_all_tests(self):
        print("=" * 80)
        print("PHASE B — ASSET INTELLIGENCE LAYER TESTS")
        print("=" * 80)
        
        # ═══════════════════════════════════════════════════════════════════════
        # PUBLIC ENDPOINTS (NO AUTH)
        # ═══════════════════════════════════════════════════════════════════════
        
        print("\n" + "─" * 80)
        print("PUBLIC ENDPOINTS (NO AUTH)")
        print("─" * 80)
        
        for asset_id in TEST_ASSETS:
            print(f"\n📦 Testing asset: {asset_id}")
            
            # B1+B2+B3+B5+B6+B7 — Intelligence aggregate
            self.test(
                f"GET /assets/{asset_id}/intelligence",
                "GET",
                f"assets/{asset_id}/intelligence",
                200,
                validate=lambda d: (
                    assert_key(d, 'asset_id'),
                    assert_key(d, 'thesis'),
                    assert_key(d, 'capital_stack'),
                    assert_key(d, 'scenarios'),
                    assert_key(d, 'metrics'),
                    assert_key(d, 'conviction'),
                    assert_key(d, 'liquidity'),
                )
            )
            
            # B2 — Scenarios
            self.test(
                f"GET /assets/{asset_id}/scenarios",
                "GET",
                f"assets/{asset_id}/scenarios",
                200,
                validate=lambda d: (
                    assert_key(d, 'scenarios'),
                    assert_len(d['scenarios'], 3),
                    assert_scenario_order(d['scenarios']),
                )
            )
            
            # B3 — Capital Stack
            self.test(
                f"GET /assets/{asset_id}/capital-stack",
                "GET",
                f"assets/{asset_id}/capital-stack",
                200,
                validate=lambda d: (
                    assert_key(d, 'layers'),
                    assert_key(d, 'asset_value'),
                    assert_key(d, 'investor_share_percent'),
                )
            )
            
            # B4 — Journal
            self.test(
                f"GET /assets/{asset_id}/journal",
                "GET",
                f"assets/{asset_id}/journal",
                200,
                validate=lambda d: (
                    assert_key(d, 'items'),
                    assert_key(d, 'total'),
                )
            )
            
            # B5 — Metrics
            self.test(
                f"GET /assets/{asset_id}/metrics",
                "GET",
                f"assets/{asset_id}/metrics",
                200,
                validate=lambda d: (
                    assert_key(d, 'funding'),
                    assert_key(d, 'investor_count'),
                    assert_key(d, 'secondary'),
                    assert_key(d, 'payout'),
                )
            )
            
            # B6 — Conviction
            self.test(
                f"GET /assets/{asset_id}/conviction",
                "GET",
                f"assets/{asset_id}/conviction",
                200,
                validate=lambda d: (
                    assert_key(d, 'score'),
                    assert_range(d['score'], 0, 100),
                    assert_key(d, 'band'),
                    assert_key(d, 'factors'),
                    assert_factors_weights(d['factors']),
                )
            )
            
            # B7 — Liquidity
            self.test(
                f"GET /assets/{asset_id}/liquidity",
                "GET",
                f"assets/{asset_id}/liquidity",
                200,
                validate=lambda d: (
                    assert_key(d, 'score'),
                    assert_range(d['score'], 0, 10),
                    assert_key(d, 'signals'),
                )
            )
            
            # B8 — Similar
            self.test(
                f"GET /assets/{asset_id}/similar",
                "GET",
                f"assets/{asset_id}/similar",
                200,
                validate=lambda d: (
                    assert_key(d, 'items'),
                )
            )
        
        # 404 test
        self.test(
            "GET /assets/nonexistent-xyz/intelligence (404)",
            "GET",
            "assets/nonexistent-xyz/intelligence",
            404
        )
        
        # ═══════════════════════════════════════════════════════════════════════
        # ADMIN ENDPOINTS (AUTH REQUIRED)
        # ═══════════════════════════════════════════════════════════════════════
        
        print("\n" + "─" * 80)
        print("ADMIN ENDPOINTS (AUTH REQUIRED)")
        print("─" * 80)
        
        if not self.login_admin():
            print("❌ Cannot proceed with admin tests - login failed")
            return
        
        test_asset = 'asset-rivne-warehouse'
        
        # GET admin intelligence
        success, admin_intel = self.test(
            f"GET /admin/assets/{test_asset}/intelligence",
            "GET",
            f"admin/assets/{test_asset}/intelligence",
            200,
            auth=True,
            validate=lambda d: (
                assert_key(d, 'thesis'),
                assert_key(d, 'capital_stack'),
                assert_key(d, 'scenario_defaults'),
            )
        )
        
        # PATCH admin intelligence (update occupancy + scenario factors)
        patch_data = {
            'occupancy_percent': 55,
            'scenario_factors': {
                'bull': {
                    'yield_factor': 1.4,
                    'exit_factor': 1.8
                }
            }
        }
        
        success, patch_resp = self.test(
            f"PATCH /admin/assets/{test_asset}/intelligence",
            "PATCH",
            f"admin/assets/{test_asset}/intelligence",
            200,
            data=patch_data,
            auth=True,
            validate=lambda d: (
                assert_key(d, 'ok'),
                assert_eq(d.get('occupancy_percent'), 55),
            )
        )
        
        # Verify the patch persisted by checking scenarios
        if success:
            self.test(
                f"Verify PATCH persisted (scenarios reflect bull yield_factor 1.4)",
                "GET",
                f"assets/{test_asset}/scenarios",
                200,
                validate=lambda d: (
                    assert_scenario_factor(d['scenarios'], 'bull', 'yield_factor', 1.4),
                )
            )
        
        # POST journal milestone
        milestone_data = {
            'date': '2026-05-20',
            'title': 'QA milestone',
            'body': 'Test milestone from automated testing',
            'kind': 'milestone'
        }
        
        success, milestone_resp = self.test(
            f"POST /admin/assets/{test_asset}/journal",
            "POST",
            f"admin/assets/{test_asset}/journal",
            200,
            data=milestone_data,
            auth=True,
            validate=lambda d: (
                assert_key(d, 'ok'),
                assert_key(d, 'milestone'),
                assert_key(d['milestone'], 'id'),
            )
        )
        
        milestone_id = None
        if success and milestone_resp.get('milestone'):
            milestone_id = milestone_resp['milestone']['id']
            
            # Verify milestone appears in journal
            self.test(
                f"Verify milestone appears in journal",
                "GET",
                f"assets/{test_asset}/journal",
                200,
                validate=lambda d: (
                    assert_milestone_exists(d['items'], 'QA milestone'),
                )
            )
            
            # DELETE milestone
            self.test(
                f"DELETE /admin/asset-journal/{milestone_id}",
                "DELETE",
                f"admin/asset-journal/{milestone_id}",
                200,
                auth=True,
                validate=lambda d: (
                    assert_key(d, 'ok'),
                )
            )
            
            # Verify milestone removed from journal
            self.test(
                f"Verify milestone removed from journal",
                "GET",
                f"assets/{test_asset}/journal",
                200,
                validate=lambda d: (
                    assert_milestone_not_exists(d['items'], 'QA milestone'),
                )
            )
        
        # ═══════════════════════════════════════════════════════════════════════
        # AUTH GUARD TEST
        # ═══════════════════════════════════════════════════════════════════════
        
        print("\n" + "─" * 80)
        print("AUTH GUARD TEST")
        print("─" * 80)
        
        # Try PATCH without auth (should get 401)
        self.test(
            f"PATCH /admin/assets/{test_asset}/intelligence WITHOUT cookie (401)",
            "PATCH",
            f"admin/assets/{test_asset}/intelligence",
            401,
            data={'occupancy_percent': 60},
            auth=False
        )
        
        # ═══════════════════════════════════════════════════════════════════════
        # SUMMARY
        # ═══════════════════════════════════════════════════════════════════════
        
        print("\n" + "=" * 80)
        print(f"📊 RESULTS: {self.tests_passed}/{self.tests_run} tests passed")
        print("=" * 80)
        
        return 0 if self.tests_passed == self.tests_run else 1


# ═══════════════════════════════════════════════════════════════════════════
# VALIDATION HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def assert_key(data, key):
    assert key in data, f"Missing key: {key}"

def assert_len(arr, expected):
    assert len(arr) == expected, f"Expected length {expected}, got {len(arr)}"

def assert_range(value, min_val, max_val):
    assert min_val <= value <= max_val, f"Value {value} not in range [{min_val}, {max_val}]"

def assert_eq(actual, expected):
    assert actual == expected, f"Expected {expected}, got {actual}"

def assert_scenario_order(scenarios):
    """Validate bull yield/exit > base > bear"""
    bear = next((s for s in scenarios if s['key'] == 'bear'), None)
    base = next((s for s in scenarios if s['key'] == 'base'), None)
    bull = next((s for s in scenarios if s['key'] == 'bull'), None)
    
    assert bear and base and bull, "Missing scenario keys"
    
    # Bull should have higher yield and exit than base
    assert bull['annual_yield_percent'] > base['annual_yield_percent'], \
        f"Bull yield {bull['annual_yield_percent']} not > base {base['annual_yield_percent']}"
    assert bull['exit_percent'] > base['exit_percent'], \
        f"Bull exit {bull['exit_percent']} not > base {base['exit_percent']}"
    
    # Base should have higher yield and exit than bear
    assert base['annual_yield_percent'] > bear['annual_yield_percent'], \
        f"Base yield {base['annual_yield_percent']} not > bear {bear['annual_yield_percent']}"
    assert base['exit_percent'] > bear['exit_percent'], \
        f"Base exit {base['exit_percent']} not > bear {bear['exit_percent']}"

def assert_factors_weights(factors):
    """Validate conviction factors weights sum sensibly"""
    total_weight = sum(f.get('weight', 0) for f in factors)
    assert 0.9 <= total_weight <= 1.1, f"Factors weights sum to {total_weight}, expected ~1.0"

def assert_scenario_factor(scenarios, key, field, expected):
    """Validate specific scenario factor value"""
    scenario = next((s for s in scenarios if s['key'] == key), None)
    assert scenario, f"Scenario {key} not found"
    assert scenario.get(field) == expected, \
        f"Scenario {key} {field} is {scenario.get(field)}, expected {expected}"

def assert_milestone_exists(items, title):
    """Validate milestone with title exists in journal"""
    found = any(item.get('title') == title for item in items)
    assert found, f"Milestone '{title}' not found in journal"

def assert_milestone_not_exists(items, title):
    """Validate milestone with title does NOT exist in journal"""
    found = any(item.get('title') == title for item in items)
    assert not found, f"Milestone '{title}' still exists in journal (should be deleted)"


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    tester = PhaseB_Tester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())
