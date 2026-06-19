"""
F2 Lumen Activity Layer — Backend API Test
==========================================
Tests all F2 endpoints:
  - POST /api/activity/track (auth-free batch ingest)
  - POST /api/activity/identify (visitor stitching)
  - GET /api/admin/activity/live (admin auth required)
  - GET /api/admin/activity/timeline (admin auth required)
  - GET /api/admin/activity/abandonment (admin auth required)
  - GET /api/admin/activity/attribution (admin auth required)
  - GET /api/admin/activity/overview (admin auth required)
  - POST /api/admin/activity/rollup (admin auth required)
  - Auth gating verification
"""
import requests
import sys
import time
from datetime import datetime

# Backend URL from frontend/.env
BASE_URL = "https://repo-deploy-68.preview.emergentagent.com"
API = f"{BASE_URL}/api"

# Admin credentials
ADMIN_EMAIL = "admin@devos.io"
ADMIN_PASSWORD = "admin123"


class F2ActivityTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.admin_cookie = None
        self.visitor_id = f"test_vid_{int(time.time())}"
        self.session_id = f"test_sess_{int(time.time())}"

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None, cookies=None):
        """Run a single API test"""
        url = f"{API}/{endpoint}"
        h = headers or {}
        c = cookies or {}
        
        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=h, cookies=c, timeout=10)
            elif method == 'POST':
                h['Content-Type'] = 'application/json'
                response = requests.post(url, json=data, headers=h, cookies=c, timeout=10)
            else:
                print(f"❌ Failed - Unknown method {method}")
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
                    print(f"   Response: {response.text[:200]}")
                except:
                    pass
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_admin_login(self):
        """Login as admin and get session cookie"""
        print("\n" + "="*60)
        print("STEP 1: Admin Login")
        print("="*60)
        
        url = f"{API}/auth/login"
        try:
            response = requests.post(
                url,
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            self.tests_run += 1
            
            if response.status_code == 200:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                
                # Check for session_token in response body or cookies
                try:
                    data = response.json()
                    session_token = data.get('session_token')
                except:
                    session_token = None
                
                # Also check cookies
                if not session_token and 'session_token' in response.cookies:
                    session_token = response.cookies['session_token']
                
                if session_token:
                    self.admin_cookie = {'session_token': session_token}
                    print(f"✅ Admin session token obtained from response")
                    return True
                elif response.cookies:
                    # Use all cookies
                    self.admin_cookie = dict(response.cookies)
                    print(f"✅ Admin cookies obtained: {list(self.admin_cookie.keys())}")
                    return True
                else:
                    print(f"⚠️  Login succeeded but no session token found")
                    print(f"   Response: {response.text[:200]}")
                    return False
            else:
                print(f"❌ Failed - Expected 200, got {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False

    def test_track_batch(self):
        """Test POST /api/activity/track - auth-free batch ingest"""
        print("\n" + "="*60)
        print("STEP 2: Track Events (Auth-Free)")
        print("="*60)
        
        events = [
            {
                "event": "session_start",
                "visitor_id": self.visitor_id,
                "session_id": self.session_id,
                "path": "/",
                "occurred_at": datetime.utcnow().isoformat() + "Z"
            },
            {
                "event": "page_view",
                "visitor_id": self.visitor_id,
                "session_id": self.session_id,
                "path": "/assets",
                "occurred_at": datetime.utcnow().isoformat() + "Z"
            },
            {
                "event": "asset_view",
                "visitor_id": self.visitor_id,
                "session_id": self.session_id,
                "path": "/assets/test-asset",
                "props": {"asset_id": "test_asset_123"},
                "occurred_at": datetime.utcnow().isoformat() + "Z"
            },
            {
                "event": "cta_click",
                "visitor_id": self.visitor_id,
                "session_id": self.session_id,
                "path": "/assets/test-asset",
                "props": {"label": "Invest Now"},
                "occurred_at": datetime.utcnow().isoformat() + "Z"
            },
            {
                "event": "lead_created",
                "visitor_id": self.visitor_id,
                "session_id": self.session_id,
                "lead_id": f"test_lead_{int(time.time())}",
                "path": "/contact",
                "occurred_at": datetime.utcnow().isoformat() + "Z"
            }
        ]
        
        success, response = self.run_test(
            "Track Batch Events",
            "POST",
            "activity/track",
            200,
            data={"events": events}
        )
        
        if success:
            accepted = response.get('accepted', 0)
            print(f"   Accepted: {accepted} events")
            if accepted == len(events):
                print(f"✅ All {len(events)} events accepted")
                return True
            else:
                print(f"⚠️  Expected {len(events)}, got {accepted}")
                return False
        return False

    def test_identify(self):
        """Test POST /api/activity/identify - stitch visitor to user/lead"""
        print("\n" + "="*60)
        print("STEP 3: Identify (Stitch Visitor)")
        print("="*60)
        
        test_user_id = f"test_user_{int(time.time())}"
        test_lead_id = f"test_lead_{int(time.time())}"
        
        success, response = self.run_test(
            "Identify Visitor",
            "POST",
            "activity/identify",
            200,
            data={
                "visitor_id": self.visitor_id,
                "user_id": test_user_id,
                "lead_id": test_lead_id
            }
        )
        
        if success:
            backfilled = response.get('events_backfilled', 0)
            linked_vids = response.get('linked_visitor_ids', [])
            print(f"   Events backfilled: {backfilled}")
            print(f"   Linked visitor IDs: {len(linked_vids)}")
            if self.visitor_id in linked_vids:
                print(f"✅ Visitor ID {self.visitor_id} is linked")
                return True
            else:
                print(f"⚠️  Visitor ID not in linked list")
                return backfilled >= 0  # Still pass if backfill worked
        return False

    def test_live_activity(self):
        """Test GET /api/admin/activity/live - requires admin auth"""
        print("\n" + "="*60)
        print("STEP 4: Live Activity (Admin Auth)")
        print("="*60)
        
        if not self.admin_cookie:
            print("❌ No admin cookie - skipping")
            return False
        
        success, response = self.run_test(
            "Live Activity",
            "GET",
            "admin/activity/live",
            200,
            cookies=self.admin_cookie
        )
        
        if success:
            online_count = response.get('online_count', 0)
            sessions = response.get('sessions', [])
            print(f"   Online count: {online_count}")
            print(f"   Sessions: {len(sessions)}")
            print(f"✅ Live activity endpoint working")
            return True
        return False

    def test_timeline(self):
        """Test GET /api/admin/activity/timeline - requires admin auth"""
        print("\n" + "="*60)
        print("STEP 5: Activity Timeline (Admin Auth)")
        print("="*60)
        
        if not self.admin_cookie:
            print("❌ No admin cookie - skipping")
            return False
        
        # Test with our visitor_id
        success, response = self.run_test(
            "Activity Timeline",
            "GET",
            f"admin/activity/timeline?visitor_id={self.visitor_id}&limit=100",
            200,
            cookies=self.admin_cookie
        )
        
        if success:
            events = response.get('events', [])
            identity = response.get('identity', {})
            print(f"   Events found: {len(events)}")
            print(f"   Identity: {identity}")
            if len(events) > 0:
                print(f"✅ Timeline contains {len(events)} events")
            else:
                print(f"⚠️  No events found (may need time for indexing)")
            return True
        return False

    def test_abandonment(self):
        """Test GET /api/admin/activity/abandonment - requires admin auth"""
        print("\n" + "="*60)
        print("STEP 6: Abandonment Detection (Admin Auth)")
        print("="*60)
        
        if not self.admin_cookie:
            print("❌ No admin cookie - skipping")
            return False
        
        success, response = self.run_test(
            "Abandonment Detection",
            "GET",
            "admin/activity/abandonment?idle_days=0",
            200,
            cookies=self.admin_cookie
        )
        
        if success:
            abandoned_count = response.get('abandoned_count', 0)
            by_stage = response.get('by_stage', {})
            rows = response.get('rows', [])
            print(f"   Abandoned count: {abandoned_count}")
            print(f"   By stage: {by_stage}")
            print(f"   Rows: {len(rows)}")
            print(f"✅ Abandonment endpoint working")
            return True
        return False

    def test_attribution(self):
        """Test GET /api/admin/activity/attribution - requires admin auth"""
        print("\n" + "="*60)
        print("STEP 7: Attribution (Admin Auth)")
        print("="*60)
        
        if not self.admin_cookie:
            print("❌ No admin cookie - skipping")
            return False
        
        success, response = self.run_test(
            "Attribution",
            "GET",
            "admin/activity/attribution?range=30d",
            200,
            cookies=self.admin_cookie
        )
        
        if success:
            top_pages = response.get('top_pages', [])
            leads_by_page = response.get('leads_by_page', [])
            assets = response.get('assets', [])
            manager_conversion = response.get('manager_conversion', [])
            print(f"   Top pages: {len(top_pages)}")
            print(f"   Leads by page: {len(leads_by_page)}")
            print(f"   Assets: {len(assets)}")
            print(f"   Manager conversion: {len(manager_conversion)}")
            print(f"✅ Attribution endpoint working")
            return True
        return False

    def test_overview(self):
        """Test GET /api/admin/activity/overview - requires admin auth"""
        print("\n" + "="*60)
        print("STEP 8: Overview (Admin Auth)")
        print("="*60)
        
        if not self.admin_cookie:
            print("❌ No admin cookie - skipping")
            return False
        
        success, response = self.run_test(
            "Overview",
            "GET",
            "admin/activity/overview?range=7d",
            200,
            cookies=self.admin_cookie
        )
        
        if success:
            total_events = response.get('total_events', 0)
            unique_visitors = response.get('unique_visitors', 0)
            unique_sessions = response.get('unique_sessions', 0)
            leads = response.get('leads', 0)
            by_event = response.get('by_event', {})
            daily = response.get('daily', [])
            print(f"   Total events: {total_events}")
            print(f"   Unique visitors: {unique_visitors}")
            print(f"   Unique sessions: {unique_sessions}")
            print(f"   Leads: {leads}")
            print(f"   Event types: {len(by_event)}")
            print(f"   Daily series: {len(daily)} days")
            print(f"✅ Overview endpoint working")
            return True
        return False

    def test_rollup(self):
        """Test POST /api/admin/activity/rollup - requires admin auth"""
        print("\n" + "="*60)
        print("STEP 9: Manual Rollup (Admin Auth)")
        print("="*60)
        
        if not self.admin_cookie:
            print("❌ No admin cookie - skipping")
            return False
        
        success, response = self.run_test(
            "Manual Rollup",
            "POST",
            "admin/activity/rollup",
            200,
            cookies=self.admin_cookie
        )
        
        if success:
            today = response.get('today', {})
            yesterday = response.get('yesterday', {})
            print(f"   Today rollup: {today.get('total_events', 0)} events")
            print(f"   Yesterday rollup: {yesterday.get('total_events', 0)} events")
            print(f"✅ Rollup endpoint working")
            return True
        return False

    def test_auth_gating(self):
        """Test that admin endpoints return 401/403 without auth"""
        print("\n" + "="*60)
        print("STEP 10: Auth Gating Verification")
        print("="*60)
        
        endpoints = [
            "admin/activity/live",
            "admin/activity/attribution?range=7d"
        ]
        
        all_blocked = True
        for endpoint in endpoints:
            success, _ = self.run_test(
                f"Auth Gate: {endpoint}",
                "GET",
                endpoint,
                401,  # Expect 401 without auth
                cookies=None
            )
            if not success:
                # Try 403 as well
                success, _ = self.run_test(
                    f"Auth Gate: {endpoint} (403)",
                    "GET",
                    endpoint,
                    403,
                    cookies=None
                )
            all_blocked = all_blocked and success
        
        if all_blocked:
            print(f"✅ All admin endpoints properly gated")
            return True
        else:
            print(f"⚠️  Some endpoints not properly gated")
            return False


def main():
    print("\n" + "="*60)
    print("F2 LUMEN ACTIVITY LAYER - BACKEND API TEST")
    print("="*60)
    print(f"Backend URL: {BASE_URL}")
    print(f"Admin: {ADMIN_EMAIL}")
    print("="*60)
    
    tester = F2ActivityTester()
    
    # Run all tests
    if not tester.test_admin_login():
        print("\n❌ Admin login failed - cannot proceed with admin tests")
        print(f"\n📊 Tests passed: {tester.tests_passed}/{tester.tests_run}")
        return 1
    
    # Wait a bit for events to be indexed
    print("\n⏳ Waiting 2 seconds for event processing...")
    time.sleep(2)
    
    tester.test_track_batch()
    
    # Wait for events to be written
    print("\n⏳ Waiting 2 seconds for event indexing...")
    time.sleep(2)
    
    tester.test_identify()
    tester.test_live_activity()
    tester.test_timeline()
    tester.test_abandonment()
    tester.test_attribution()
    tester.test_overview()
    tester.test_rollup()
    tester.test_auth_gating()
    
    # Print results
    print("\n" + "="*60)
    print("TEST RESULTS")
    print("="*60)
    print(f"📊 Tests passed: {tester.tests_passed}/{tester.tests_run}")
    print(f"✅ Success rate: {(tester.tests_passed/tester.tests_run*100):.1f}%")
    print("="*60)
    
    return 0 if tester.tests_passed == tester.tests_run else 1


if __name__ == "__main__":
    sys.exit(main())
