"""
LUMEN 2.0 — Phase G11 — Accreditation OS Backend Tests
========================================================
Tests investor accreditation profile 2.0, review workflow, eligibility engine,
and admin accreditation queue management.
"""
import requests
import sys
from datetime import datetime

# Public endpoint from frontend/.env
BASE_URL = "https://repo-deploy-65.preview.emergentagent.com/api"

class AccreditationTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
        
    def run_test(self, name, method, endpoint, expected_status, data=None, params=None, desc=""):
        """Run a single API test"""
        url = f"{BASE_URL}/{endpoint}"
        self.tests_run += 1
        print(f"\n🔍 Test {self.tests_run}: {name}")
        if desc:
            print(f"   {desc}")
        
        try:
            if method == 'GET':
                response = self.session.get(url, params=params)
            elif method == 'POST':
                response = self.session.post(url, json=data)
            elif method == 'PATCH':
                response = self.session.patch(url, json=data)
            else:
                print(f"❌ Failed - Unsupported method {method}")
                return False, {}

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    return success, response.json()
                except:
                    return success, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    print(f"   Response: {response.json()}")
                except:
                    print(f"   Response: {response.text[:200]}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def login(self, email, password):
        """Login and establish session"""
        success, response = self.run_test(
            f"Login as {email}",
            "POST",
            "auth/login",
            200,
            data={"email": email, "password": password},
            desc=f"Authenticate as {email}"
        )
        return success

    def logout(self):
        """Logout current session"""
        try:
            self.session.post(f"{BASE_URL}/auth/logout")
        except:
            pass

def main():
    tester = AccreditationTester()
    
    print("=" * 80)
    print("LUMEN 2.0 — Phase G11 — Accreditation OS Backend Tests")
    print("=" * 80)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Test 1: Investor accreditation profile (family@atlas.dev - institutional)
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("SECTION 1: Investor Accreditation Profile (Institutional)")
    print("=" * 80)
    
    if not tester.login("family@atlas.dev", "family123"):
        print("❌ Cannot proceed - login failed")
        return 1
    
    success, profile = tester.run_test(
        "GET /api/investor/accreditation (family@atlas.dev)",
        "GET",
        "investor/accreditation",
        200,
        desc="Fetch Profile 2.0 for institutional investor"
    )
    
    if success:
        # Verify profile structure
        required_blocks = ['financial', 'experience', 'jurisdiction', 'tax', 'accreditation']
        missing = [b for b in required_blocks if b not in profile]
        if missing:
            print(f"⚠️  Missing profile blocks: {missing}")
        else:
            print(f"✓ Profile 2.0 structure complete")
        
        # Verify accreditation data
        acc = profile.get('accreditation', {})
        if acc.get('level') == 'institutional' and acc.get('review_status') == 'approved':
            print(f"✓ Accreditation: level={acc['level']}, status={acc['review_status']}")
        else:
            print(f"⚠️  Expected institutional/approved, got {acc.get('level')}/{acc.get('review_status')}")
        
        # Check effective_level
        if profile.get('effective_level'):
            print(f"✓ Effective level: {profile['effective_level']}")
        
        # Check suggested_level
        if acc.get('suggested_level'):
            print(f"✓ Suggested level: {acc['suggested_level']}")
        
        # Check missing_for_submit
        missing_fields = profile.get('missing_for_submit', [])
        print(f"✓ Missing for submit: {len(missing_fields)} fields")
    
    tester.logout()
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Test 2: Update profile (maria.s@lumen.test - retail under_review)
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("SECTION 2: Profile Update & Submit Flow (Retail Investor)")
    print("=" * 80)
    
    if not tester.login("maria.s@lumen.test", "demo123"):
        print("❌ Cannot proceed - login failed")
        return 1
    
    # Get current profile
    success, profile = tester.run_test(
        "GET /api/investor/accreditation (maria.s@lumen.test)",
        "GET",
        "investor/accreditation",
        200,
        desc="Fetch current profile before update"
    )
    
    if success:
        print(f"✓ Current status: {profile.get('accreditation', {}).get('review_status')}")
    
    # Update financial + experience blocks
    update_payload = {
        "financial": {
            "annual_income_uah": 650000,
            "net_worth_uah": 950000,
            "liquid_assets_uah": 320000,
            "investment_horizon": "medium",
            "risk_appetite": "balanced"
        },
        "experience": {
            "years_investing": 2,
            "asset_classes": ["real_estate"],
            "real_estate_experience": "beginner",
            "private_markets_experience": "beginner"
        }
    }
    
    success, updated = tester.run_test(
        "PATCH /api/investor/accreditation/profile",
        "PATCH",
        "investor/accreditation/profile",
        200,
        data=update_payload,
        desc="Update financial and experience blocks"
    )
    
    if success:
        # Verify update persisted
        success2, reloaded = tester.run_test(
            "Re-GET profile to verify persistence",
            "GET",
            "investor/accreditation",
            200,
            desc="Verify updated values persisted"
        )
        if success2:
            fin = reloaded.get('financial', {})
            if fin.get('annual_income_uah') == 650000 and fin.get('risk_appetite') == 'balanced':
                print(f"✓ Profile update persisted correctly")
            else:
                print(f"⚠️  Profile values not persisted as expected")
    
    tester.logout()
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Test 3: Submit accreditation (incomplete profile should fail)
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("SECTION 3: Accreditation Submit Validation")
    print("=" * 80)
    
    if not tester.login("client@atlas.dev", "client123"):
        print("❌ Cannot proceed - login failed")
        return 1
    
    # Get profile to check missing fields
    success, profile = tester.run_test(
        "GET /api/investor/accreditation (client@atlas.dev)",
        "GET",
        "investor/accreditation",
        200,
        desc="Check retail investor profile completeness"
    )
    
    missing = profile.get('missing_for_submit', []) if success else []
    
    if missing:
        # Try to submit incomplete profile (should fail with 400)
        success, resp = tester.run_test(
            "POST /api/investor/accreditation/submit (incomplete)",
            "POST",
            "investor/accreditation/submit",
            400,
            desc="Submit incomplete profile - should return 400 with missing fields"
        )
        if success:
            print(f"✓ Correctly rejected incomplete profile")
    else:
        # Profile is complete, submit should work
        success, resp = tester.run_test(
            "POST /api/investor/accreditation/submit (complete)",
            "POST",
            "investor/accreditation/submit",
            200,
            desc="Submit complete profile - should move to under_review"
        )
        if success:
            acc = resp.get('accreditation', {})
            if acc.get('review_status') == 'under_review':
                print(f"✓ Profile submitted, status now: {acc['review_status']}")
            else:
                print(f"⚠️  Expected under_review, got {acc.get('review_status')}")
    
    tester.logout()
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Test 4: Asset eligibility checks
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("SECTION 4: Asset Eligibility Engine")
    print("=" * 80)
    
    # Test 4a: Institutional investor accessing institutional_only asset
    if not tester.login("family@atlas.dev", "family123"):
        print("❌ Cannot proceed - login failed")
        return 1
    
    success, elig = tester.run_test(
        "GET /api/investor/eligibility (institutional → institutional_only)",
        "GET",
        "investor/eligibility",
        200,
        params={"asset_id": "asset-stoyanka-land", "amount": 300000},
        desc="family@atlas.dev (institutional) accessing asset-stoyanka-land (institutional_only)"
    )
    
    if success:
        if elig.get('eligible'):
            print(f"✓ Eligible: {elig.get('eligible')}, level: {elig.get('your_level')}")
        else:
            print(f"⚠️  Expected eligible=true, got {elig.get('eligible')}")
            print(f"   Blockers: {elig.get('blockers')}")
    
    tester.logout()
    
    # Test 4b: Retail investor accessing institutional_only asset (should be blocked)
    if not tester.login("client@atlas.dev", "client123"):
        print("❌ Cannot proceed - login failed")
        return 1
    
    success, elig = tester.run_test(
        "GET /api/investor/eligibility (retail → institutional_only)",
        "GET",
        "investor/eligibility",
        200,
        params={"asset_id": "asset-stoyanka-land", "amount": 300000},
        desc="client@atlas.dev (retail) accessing asset-stoyanka-land (institutional_only) - should be blocked"
    )
    
    if success:
        if not elig.get('eligible') and elig.get('blockers'):
            print(f"✓ Correctly blocked: eligible={elig.get('eligible')}")
            print(f"  Blockers: {elig.get('blockers')}")
        else:
            print(f"⚠️  Expected eligible=false with blockers, got {elig.get('eligible')}")
    
    tester.logout()
    
    # Test 4c: Retail investor accessing retail_allowed asset (should work)
    if not tester.login("client@atlas.dev", "client123"):
        print("❌ Cannot proceed - login failed")
        return 1
    
    success, elig = tester.run_test(
        "GET /api/investor/eligibility (retail → retail_allowed)",
        "GET",
        "investor/eligibility",
        200,
        params={"asset_id": "asset-podilskyi", "amount": 100000},
        desc="client@atlas.dev (retail) accessing asset-podilskyi (retail_allowed) - should be allowed"
    )
    
    if success:
        if elig.get('eligible'):
            print(f"✓ Eligible: {elig.get('eligible')}, access_level: {elig.get('access_level')}")
        else:
            print(f"⚠️  Expected eligible=true for retail_allowed asset")
            print(f"   Blockers: {elig.get('blockers')}")
    
    tester.logout()
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Test 5: Admin accreditation queue
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("SECTION 5: Admin Accreditation Queue")
    print("=" * 80)
    
    if not tester.login("admin@atlas.dev", "admin123"):
        print("❌ Cannot proceed - admin login failed")
        return 1
    
    # Get full queue
    success, queue = tester.run_test(
        "GET /api/admin/accreditation/queue",
        "GET",
        "admin/accreditation/queue",
        200,
        desc="Fetch full accreditation queue"
    )
    
    if success:
        items = queue.get('items', [])
        counts = queue.get('counts', {})
        print(f"✓ Queue items: {len(items)}")
        print(f"✓ Counts by status: {counts}")
    
    # Filter by status=approved
    success, filtered = tester.run_test(
        "GET /api/admin/accreditation/queue?status=approved",
        "GET",
        "admin/accreditation/queue",
        200,
        params={"status": "approved"},
        desc="Filter queue by status=approved"
    )
    
    if success:
        items = filtered.get('items', [])
        print(f"✓ Approved items: {len(items)}")
        if items:
            print(f"  Example: {items[0].get('full_name')} - {items[0].get('accreditation', {}).get('level')}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Test 6: Admin accreditation card & events
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("SECTION 6: Admin Accreditation Card & Events")
    print("=" * 80)
    
    # Get a user_id from the queue
    if success and items:
        user_id = items[0].get('user_id')
        
        success, card = tester.run_test(
            f"GET /api/admin/accreditation/{user_id}",
            "GET",
            f"admin/accreditation/{user_id}",
            200,
            desc=f"Fetch full accreditation card for {user_id}"
        )
        
        if success:
            print(f"✓ Card loaded: {card.get('full_name')}")
            print(f"  Level: {card.get('accreditation', {}).get('level')}")
            print(f"  Status: {card.get('accreditation', {}).get('review_status')}")
            print(f"  Effective level: {card.get('effective_level')}")
            events = card.get('events', [])
            print(f"✓ Events history: {len(events)} events")
            if events:
                print(f"  Latest: {events[0].get('kind')} → {events[0].get('to_status')}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Test 7: Admin state transitions
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("SECTION 7: Admin State Transitions")
    print("=" * 80)
    
    # Find a user in under_review status to test transitions
    success, queue = tester.run_test(
        "GET queue for under_review",
        "GET",
        "admin/accreditation/queue",
        200,
        params={"status": "under_review"}
    )
    
    if success:
        items = queue.get('items', [])
        if items:
            user_id = items[0].get('user_id')
            
            # Test transition: under_review -> approved
            success, result = tester.run_test(
                f"POST /api/admin/accreditation/{user_id}/transition (approve)",
                "POST",
                f"admin/accreditation/{user_id}/transition",
                200,
                data={
                    "to_status": "approved",
                    "level": "qualified",
                    "note": "Test approval from backend_test_phase_g11.py",
                    "basis": "test_automation"
                },
                desc=f"Approve accreditation for {user_id}"
            )
            
            if success:
                acc = result.get('accreditation', {})
                if acc.get('review_status') == 'approved' and acc.get('level') == 'qualified':
                    print(f"✓ Transition successful: status={acc['review_status']}, level={acc['level']}")
                else:
                    print(f"⚠️  Transition may have failed: {acc}")
            
            # Test illegal transition (should fail with 409)
            success, result = tester.run_test(
                f"POST /api/admin/accreditation/{user_id}/transition (illegal)",
                "POST",
                f"admin/accreditation/{user_id}/transition",
                409,
                data={
                    "to_status": "pending",
                    "note": "Illegal transition test"
                },
                desc=f"Attempt illegal transition approved->pending (should fail)"
            )
            
            if success:
                print(f"✓ Illegal transition correctly rejected with 409")
        else:
            print("⚠️  No users in under_review status to test transitions")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Test 8: Admin asset access management
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("SECTION 8: Admin Asset Access Management")
    print("=" * 80)
    
    success, assets = tester.run_test(
        "GET /api/admin/accreditation/assets/access",
        "GET",
        "admin/accreditation/assets/access",
        200,
        desc="List all assets with access levels"
    )
    
    if success:
        items = assets.get('items', [])
        levels = assets.get('levels', [])
        print(f"✓ Assets: {len(items)}")
        print(f"✓ Available levels: {[l['value'] for l in levels]}")
        
        # Show some examples
        for asset in items[:3]:
            print(f"  {asset['id']}: {asset.get('access_level')} ({asset.get('access_level_label')})")
        
        # Test changing access level
        if items:
            asset_id = items[0]['id']
            current_level = items[0].get('access_level', 'retail_allowed')
            new_level = 'qualified_only' if current_level != 'qualified_only' else 'retail_allowed'
            
            success, result = tester.run_test(
                f"PATCH /api/admin/accreditation/assets/{asset_id}/access",
                "PATCH",
                f"admin/accreditation/assets/{asset_id}/access",
                200,
                data={"access_level": new_level},
                desc=f"Change {asset_id} access level to {new_level}"
            )
            
            if success and result.get('ok'):
                print(f"✓ Access level changed: {asset_id} -> {new_level}")
            
            # Test invalid level (should fail with 400)
            success, result = tester.run_test(
                f"PATCH /api/admin/accreditation/assets/{asset_id}/access (invalid)",
                "PATCH",
                f"admin/accreditation/assets/{asset_id}/access",
                400,
                data={"access_level": "invalid_level"},
                desc=f"Attempt to set invalid access level (should fail)"
            )
            
            if success:
                print(f"✓ Invalid level correctly rejected with 400")
    
    tester.logout()
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Summary
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Tests run: {tester.tests_run}")
    print(f"Tests passed: {tester.tests_passed}")
    print(f"Tests failed: {tester.tests_run - tester.tests_passed}")
    print(f"Success rate: {(tester.tests_passed / tester.tests_run * 100):.1f}%")
    
    if tester.tests_passed == tester.tests_run:
        print("\n✅ ALL TESTS PASSED")
        return 0
    else:
        print(f"\n⚠️  {tester.tests_run - tester.tests_passed} TEST(S) FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
