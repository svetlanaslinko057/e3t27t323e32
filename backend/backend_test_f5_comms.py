"""
F5 Communication Provider Layer — Backend API Test Suite
Tests all provider registry, send/ingest, feed, stats, and activation guard endpoints.
"""
import requests
import sys
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://repo-deploy-68.preview.emergentagent.com')

class F5CommsTester:
    def __init__(self):
        self.base_url = BASE_URL
        self.session_token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.results = []

    def log(self, test_name, passed, details=""):
        self.tests_run += 1
        if passed:
            self.tests_passed += 1
        status = "✅ PASS" if passed else "❌ FAIL"
        msg = f"{status} | {test_name}"
        if details:
            msg += f" | {details}"
        print(msg)
        self.results.append({"test": test_name, "passed": passed, "details": details})

    def login(self):
        """Login as admin to get session_token cookie"""
        print("\n🔐 Logging in as admin...")
        try:
            r = requests.post(f"{self.base_url}/api/auth/login", json={
                "email": "admin@devos.io",
                "password": "admin123"
            }, timeout=10)
            if r.status_code == 200:
                # Check for session_token in response cookies
                if 'session_token' in r.cookies:
                    self.session_token = r.cookies['session_token']
                    print(f"✅ Login successful, session_token from cookie: {self.session_token[:20]}...")
                    return True
                # Also check JSON body
                data = r.json()
                self.session_token = data.get("session_token")
                if self.session_token:
                    print(f"✅ Login successful, session_token from body: {self.session_token[:20]}...")
                    return True
                else:
                    print(f"❌ Login response missing session_token in both cookie and body")
                    print(f"   Cookies: {list(r.cookies.keys())}")
                    print(f"   Body keys: {list(data.keys())}")
                    return False
            else:
                print(f"❌ Login failed: {r.status_code} {r.text[:200]}")
                return False
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False

    def get(self, path):
        """GET request with session cookie"""
        cookies = {"session_token": self.session_token} if self.session_token else {}
        return requests.get(f"{self.base_url}{path}", cookies=cookies, timeout=10)

    def post(self, path, data=None):
        """POST request with session cookie"""
        cookies = {"session_token": self.session_token} if self.session_token else {}
        return requests.post(f"{self.base_url}{path}", json=data, cookies=cookies, timeout=10)

    def patch(self, path, data=None):
        """PATCH request with session cookie"""
        cookies = {"session_token": self.session_token} if self.session_token else {}
        return requests.patch(f"{self.base_url}{path}", json=data, cookies=cookies, timeout=10)

    def test_providers_list(self):
        """Test GET /api/admin/comms/providers - should return 9 providers"""
        print("\n📋 Testing provider list...")
        try:
            r = self.get("/api/admin/comms/providers")
            if r.status_code == 200:
                data = r.json()
                providers = data.get("providers", [])
                if len(providers) == 9:
                    manual = next((p for p in providers if p["key"] == "manual"), None)
                    if manual and manual.get("status") == "active" and manual.get("connected"):
                        self.log("GET /api/admin/comms/providers", True, f"9 providers, manual active & connected")
                    else:
                        self.log("GET /api/admin/comms/providers", False, f"manual provider not active/connected: {manual}")
                else:
                    self.log("GET /api/admin/comms/providers", False, f"Expected 9 providers, got {len(providers)}")
            else:
                self.log("GET /api/admin/comms/providers", False, f"Status {r.status_code}: {r.text[:200]}")
        except Exception as e:
            self.log("GET /api/admin/comms/providers", False, str(e))

    def test_send_manual(self):
        """Test POST /api/comms/send with manual provider - should succeed"""
        print("\n📤 Testing send with manual provider...")
        try:
            r = self.post("/api/comms/send", {
                "provider": "manual",
                "interaction_type": "call",
                "direction": "outbound",
                "contact": "investor@example.com",
                "subject": "Intro",
                "body": "hi"
            })
            if r.status_code == 200:
                data = r.json()
                if data.get("ok") and data.get("sync_status") == "logged" and data.get("comm"):
                    self.log("POST /api/comms/send (manual)", True, f"ok=true, sync_status=logged")
                else:
                    self.log("POST /api/comms/send (manual)", False, f"Unexpected response: {data}")
            else:
                self.log("POST /api/comms/send (manual)", False, f"Status {r.status_code}: {r.text[:200]}")
        except Exception as e:
            self.log("POST /api/comms/send (manual)", False, str(e))

    def test_send_dormant(self):
        """Test POST /api/comms/send with dormant provider - should return not_connected but record"""
        print("\n📤 Testing send with dormant provider (ringostat)...")
        try:
            r = self.post("/api/comms/send", {
                "provider": "ringostat",
                "interaction_type": "call",
                "direction": "inbound",
                "contact": "+380501234567"
            })
            if r.status_code == 200:
                data = r.json()
                if not data.get("ok") and data.get("result") == "not_connected" and data.get("sync_status") == "not_connected" and data.get("comm"):
                    self.log("POST /api/comms/send (ringostat)", True, f"ok=false, result=not_connected, comm recorded")
                else:
                    self.log("POST /api/comms/send (ringostat)", False, f"Unexpected response: {data}")
            else:
                self.log("POST /api/comms/send (ringostat)", False, f"Status {r.status_code}: {r.text[:200]}")
        except Exception as e:
            self.log("POST /api/comms/send (ringostat)", False, str(e))

    def test_ingest(self):
        """Test POST /api/comms/ingest with gmail - should succeed"""
        print("\n📥 Testing ingest with gmail...")
        try:
            r = self.post("/api/comms/ingest", {
                "provider": "gmail",
                "interaction_type": "email",
                "direction": "inbound",
                "contact": "investor@example.com",
                "title": "Re",
                "body": "x",
                "external_ref": "gmail_1",
                "thread_ref": "t1"
            })
            if r.status_code == 200:
                data = r.json()
                if data.get("ok") and data.get("comm"):
                    self.log("POST /api/comms/ingest (gmail)", True, f"ok=true, comm recorded")
                else:
                    self.log("POST /api/comms/ingest (gmail)", False, f"Unexpected response: {data}")
            else:
                self.log("POST /api/comms/ingest (gmail)", False, f"Status {r.status_code}: {r.text[:200]}")
        except Exception as e:
            self.log("POST /api/comms/ingest (gmail)", False, str(e))

    def test_activation_guard(self):
        """Test PATCH /api/admin/comms/providers/ringostat with status='active' - should return 409"""
        print("\n🚫 Testing activation guard (ringostat -> active)...")
        try:
            r = self.patch("/api/admin/comms/providers/ringostat", {"status": "active"})
            if r.status_code == 409:
                self.log("PATCH /api/admin/comms/providers/ringostat (activation guard)", True, f"409 Conflict as expected")
            else:
                self.log("PATCH /api/admin/comms/providers/ringostat (activation guard)", False, f"Expected 409, got {r.status_code}: {r.text[:200]}")
        except Exception as e:
            self.log("PATCH /api/admin/comms/providers/ringostat (activation guard)", False, str(e))

    def test_disable_enable(self):
        """Test PATCH /api/admin/comms/providers/twilio disable then enable"""
        print("\n🔄 Testing disable/enable twilio...")
        try:
            # Disable
            r1 = self.patch("/api/admin/comms/providers/twilio", {"status": "disabled"})
            if r1.status_code == 200:
                data1 = r1.json()
                if data1.get("status") == "disabled":
                    # Enable back
                    r2 = self.patch("/api/admin/comms/providers/twilio", {"status": "not_connected"})
                    if r2.status_code == 200:
                        data2 = r2.json()
                        if data2.get("status") == "not_connected":
                            self.log("PATCH /api/admin/comms/providers/twilio (disable/enable)", True, f"disabled -> not_connected")
                        else:
                            self.log("PATCH /api/admin/comms/providers/twilio (disable/enable)", False, f"Enable failed: {data2}")
                    else:
                        self.log("PATCH /api/admin/comms/providers/twilio (disable/enable)", False, f"Enable status {r2.status_code}")
                else:
                    self.log("PATCH /api/admin/comms/providers/twilio (disable/enable)", False, f"Disable failed: {data1}")
            else:
                self.log("PATCH /api/admin/comms/providers/twilio (disable/enable)", False, f"Disable status {r1.status_code}")
        except Exception as e:
            self.log("PATCH /api/admin/comms/providers/twilio (disable/enable)", False, str(e))

    def test_provider_test(self):
        """Test POST /api/admin/comms/providers/{key}/test"""
        print("\n🧪 Testing provider test endpoints...")
        try:
            # Test manual - should be connected
            r1 = self.post("/api/admin/comms/providers/manual/test")
            if r1.status_code == 200:
                data1 = r1.json()
                if data1.get("connected") and data1.get("result") == "ok":
                    self.log("POST /api/admin/comms/providers/manual/test", True, f"connected=true, result=ok")
                else:
                    self.log("POST /api/admin/comms/providers/manual/test", False, f"Unexpected: {data1}")
            else:
                self.log("POST /api/admin/comms/providers/manual/test", False, f"Status {r1.status_code}")

            # Test gmail - should not be connected
            r2 = self.post("/api/admin/comms/providers/gmail/test")
            if r2.status_code == 200:
                data2 = r2.json()
                if not data2.get("connected") and data2.get("result") == "not_connected":
                    self.log("POST /api/admin/comms/providers/gmail/test", True, f"connected=false, result=not_connected")
                else:
                    self.log("POST /api/admin/comms/providers/gmail/test", False, f"Unexpected: {data2}")
            else:
                self.log("POST /api/admin/comms/providers/gmail/test", False, f"Status {r2.status_code}")
        except Exception as e:
            self.log("POST /api/admin/comms/providers/*/test", False, str(e))

    def test_feed(self):
        """Test GET /api/admin/comms/feed with filters"""
        print("\n📰 Testing feed endpoint...")
        try:
            # Get all
            r1 = self.get("/api/admin/comms/feed")
            if r1.status_code == 200:
                data1 = r1.json()
                items = data1.get("items", [])
                if len(items) > 0:
                    # Check structure
                    first = items[0]
                    if all(k in first for k in ["provider", "provider_type", "direction", "interaction_type", "sync_status"]):
                        self.log("GET /api/admin/comms/feed", True, f"{len(items)} items with correct structure")
                    else:
                        self.log("GET /api/admin/comms/feed", False, f"Missing fields in item: {first.keys()}")
                else:
                    self.log("GET /api/admin/comms/feed", True, f"0 items (no comms yet)")
            else:
                self.log("GET /api/admin/comms/feed", False, f"Status {r1.status_code}")

            # Test filter by provider
            r2 = self.get("/api/admin/comms/feed?provider=manual")
            if r2.status_code == 200:
                data2 = r2.json()
                items2 = data2.get("items", [])
                if all(it.get("provider") == "manual" for it in items2):
                    self.log("GET /api/admin/comms/feed?provider=manual", True, f"Filter works, {len(items2)} items")
                else:
                    self.log("GET /api/admin/comms/feed?provider=manual", False, f"Filter failed")
            else:
                self.log("GET /api/admin/comms/feed?provider=manual", False, f"Status {r2.status_code}")

            # Test filter by direction
            r3 = self.get("/api/admin/comms/feed?direction=inbound")
            if r3.status_code == 200:
                data3 = r3.json()
                items3 = data3.get("items", [])
                if all(it.get("direction") == "inbound" for it in items3):
                    self.log("GET /api/admin/comms/feed?direction=inbound", True, f"Filter works, {len(items3)} items")
                else:
                    self.log("GET /api/admin/comms/feed?direction=inbound", False, f"Filter failed")
            else:
                self.log("GET /api/admin/comms/feed?direction=inbound", False, f"Status {r3.status_code}")
        except Exception as e:
            self.log("GET /api/admin/comms/feed", False, str(e))

    def test_stats(self):
        """Test GET /api/admin/comms/stats"""
        print("\n📊 Testing stats endpoint...")
        try:
            r = self.get("/api/admin/comms/stats")
            if r.status_code == 200:
                data = r.json()
                if all(k in data for k in ["total", "by_provider", "by_direction", "by_type"]):
                    self.log("GET /api/admin/comms/stats", True, f"total={data.get('total')}, stats present")
                else:
                    self.log("GET /api/admin/comms/stats", False, f"Missing fields: {data.keys()}")
            else:
                self.log("GET /api/admin/comms/stats", False, f"Status {r.status_code}")
        except Exception as e:
            self.log("GET /api/admin/comms/stats", False, str(e))

    def test_auth_gating(self):
        """Test auth gating - endpoints should return 401 without cookie"""
        print("\n🔒 Testing auth gating...")
        try:
            # Save current token
            saved_token = self.session_token
            self.session_token = None

            r1 = self.get("/api/admin/comms/providers")
            if r1.status_code == 401:
                self.log("Auth gating: GET /api/admin/comms/providers", True, f"401 without cookie")
            else:
                self.log("Auth gating: GET /api/admin/comms/providers", False, f"Expected 401, got {r1.status_code}")

            r2 = self.post("/api/comms/send", {"provider": "manual"})
            if r2.status_code == 401:
                self.log("Auth gating: POST /api/comms/send", True, f"401 without cookie")
            else:
                self.log("Auth gating: POST /api/comms/send", False, f"Expected 401, got {r2.status_code}")

            # Restore token
            self.session_token = saved_token
        except Exception as e:
            self.log("Auth gating", False, str(e))

    def run_all(self):
        print("=" * 80)
        print("F5 COMMUNICATION PROVIDER LAYER — BACKEND TEST SUITE")
        print("=" * 80)
        print(f"Base URL: {self.base_url}")
        print(f"Started: {datetime.now().isoformat()}")

        if not self.login():
            print("\n❌ Login failed, cannot proceed with tests")
            return False

        # Run all tests
        self.test_providers_list()
        self.test_send_manual()
        self.test_send_dormant()
        self.test_ingest()
        self.test_activation_guard()
        self.test_disable_enable()
        self.test_provider_test()
        self.test_feed()
        self.test_stats()
        self.test_auth_gating()

        # Summary
        print("\n" + "=" * 80)
        print(f"RESULTS: {self.tests_passed}/{self.tests_run} tests passed")
        print("=" * 80)

        return self.tests_passed == self.tests_run

def main():
    tester = F5CommsTester()
    success = tester.run_all()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
