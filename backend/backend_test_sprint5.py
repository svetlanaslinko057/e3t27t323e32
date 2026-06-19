"""
LUMEN Sprint 5 Backend Smoke Test
==================================
Tests Sprint 5 Asset Content Platform APIs.

Focus: Quick smoke tests of key endpoints (backend already tested via test_sprint5_content.py).
"""

import requests
import sys
import os

# Get backend URL from environment
BASE_URL = os.getenv("REACT_APP_BACKEND_URL", "https://arch-review-24.preview.emergentagent.com")

class Sprint5BackendTester:
    def __init__(self):
        self.base_url = BASE_URL
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = []
        self.client_token = None
        self.admin_token = None

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

    def quick_login(self, email):
        """Quick login without password"""
        try:
            response = requests.post(
                f"{self.base_url}/api/auth/quick",
                json={"email": email},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("token")
            return None
        except Exception as e:
            self.log("⚠️", f"Quick login failed for {email}: {e}")
            return None

    def test_asset_content_endpoints(self):
        """Test Sprint 5 content endpoints on asset-podilskyi"""
        asset_id = "asset-podilskyi"
        
        # 1. GET /api/assets/{id} - should have gallery, videos, team, risks, exit_strategy
        self.log("🔍", f"Testing GET /api/assets/{asset_id} (Sprint 5 fields)...")
        try:
            response = requests.get(f"{self.base_url}/api/assets/{asset_id}", timeout=10)
            if response.status_code == 200:
                data = response.json()
                has_gallery = isinstance(data.get("gallery"), list) and len(data.get("gallery", [])) > 0
                has_videos = isinstance(data.get("videos"), list)
                has_team = isinstance(data.get("team"), list)
                has_risks = isinstance(data.get("risks"), list)
                has_exit = "exit_strategy" in data
                
                self.test(
                    f"GET /api/assets/{asset_id} (gallery)",
                    has_gallery,
                    f"gallery_count={len(data.get('gallery', []))}"
                )
                self.test(
                    f"GET /api/assets/{asset_id} (videos)",
                    has_videos,
                    f"videos_count={len(data.get('videos', []))}"
                )
                self.test(
                    f"GET /api/assets/{asset_id} (team)",
                    has_team,
                    f"team_count={len(data.get('team', []))}"
                )
                self.test(
                    f"GET /api/assets/{asset_id} (risks)",
                    has_risks,
                    f"risks_count={len(data.get('risks', []))}"
                )
                self.test(
                    f"GET /api/assets/{asset_id} (exit_strategy)",
                    has_exit,
                    f"has_exit={has_exit}"
                )
            else:
                self.test(f"GET /api/assets/{asset_id}", False, f"status={response.status_code}")
        except Exception as e:
            self.test(f"GET /api/assets/{asset_id}", False, f"error={str(e)}")

        # 2. GET /api/assets/{id}/updates
        self.log("🔍", f"Testing GET /api/assets/{asset_id}/updates...")
        try:
            response = requests.get(f"{self.base_url}/api/assets/{asset_id}/updates", timeout=10)
            if response.status_code == 200:
                data = response.json()
                items = data.get("items", [])
                self.test(
                    f"GET /api/assets/{asset_id}/updates",
                    response.status_code == 200 and isinstance(items, list),
                    f"status=200, items_count={len(items)}"
                )
            else:
                self.test(f"GET /api/assets/{asset_id}/updates", False, f"status={response.status_code}")
        except Exception as e:
            self.test(f"GET /api/assets/{asset_id}/updates", False, f"error={str(e)}")

        # 3. GET /api/assets/{id}/reports
        self.log("🔍", f"Testing GET /api/assets/{asset_id}/reports...")
        try:
            response = requests.get(f"{self.base_url}/api/assets/{asset_id}/reports", timeout=10)
            if response.status_code == 200:
                data = response.json()
                items = data.get("items", [])
                self.test(
                    f"GET /api/assets/{asset_id}/reports",
                    response.status_code == 200 and isinstance(items, list),
                    f"status=200, items_count={len(items)}"
                )
            else:
                self.test(f"GET /api/assets/{asset_id}/reports", False, f"status={response.status_code}")
        except Exception as e:
            self.test(f"GET /api/assets/{asset_id}/reports", False, f"error={str(e)}")

        # 4. GET /api/assets/{id}/documents
        self.log("🔍", f"Testing GET /api/assets/{asset_id}/documents...")
        try:
            response = requests.get(f"{self.base_url}/api/assets/{asset_id}/documents", timeout=10)
            if response.status_code == 200:
                data = response.json()
                items = data.get("items", [])
                self.test(
                    f"GET /api/assets/{asset_id}/documents",
                    response.status_code == 200 and isinstance(items, list),
                    f"status=200, items_count={len(items)}"
                )
            else:
                self.test(f"GET /api/assets/{asset_id}/documents", False, f"status={response.status_code}")
        except Exception as e:
            self.test(f"GET /api/assets/{asset_id}/documents", False, f"error={str(e)}")

        # 5. GET /api/assets/{id}/questions
        self.log("🔍", f"Testing GET /api/assets/{asset_id}/questions...")
        try:
            response = requests.get(f"{self.base_url}/api/assets/{asset_id}/questions", timeout=10)
            if response.status_code == 200:
                data = response.json()
                items = data.get("items", [])
                self.test(
                    f"GET /api/assets/{asset_id}/questions",
                    response.status_code == 200 and isinstance(items, list),
                    f"status=200, items_count={len(items)}"
                )
            else:
                self.test(f"GET /api/assets/{asset_id}/questions", False, f"status={response.status_code}")
        except Exception as e:
            self.test(f"GET /api/assets/{asset_id}/questions", False, f"error={str(e)}")

        # 6. GET /api/assets/{id}/spv
        self.log("🔍", f"Testing GET /api/assets/{asset_id}/spv...")
        try:
            response = requests.get(f"{self.base_url}/api/assets/{asset_id}/spv", timeout=10)
            if response.status_code == 200:
                data = response.json()
                spv = data.get("spv")
                self.test(
                    f"GET /api/assets/{asset_id}/spv",
                    response.status_code == 200 and spv is not None,
                    f"status=200, has_spv={spv is not None}"
                )
            else:
                self.test(f"GET /api/assets/{asset_id}/spv", False, f"status={response.status_code}")
        except Exception as e:
            self.test(f"GET /api/assets/{asset_id}/spv", False, f"error={str(e)}")

    def test_admin_endpoints(self):
        """Test admin endpoints (require auth)"""
        self.log("🔍", "Testing admin login...")
        self.admin_token = self.quick_login("admin@atlas.dev")
        if not self.admin_token:
            self.test("Admin login", False, "quick login failed")
            return

        self.test("Admin login", True, "token received")

        headers = {"Authorization": f"Bearer {self.admin_token}"}

        # Test GET /api/admin/questions
        self.log("🔍", "Testing GET /api/admin/questions...")
        try:
            response = requests.get(f"{self.base_url}/api/admin/questions", headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                items = data.get("items", [])
                counts = data.get("counts", {})
                self.test(
                    "GET /api/admin/questions",
                    response.status_code == 200 and isinstance(items, list) and isinstance(counts, dict),
                    f"status=200, items_count={len(items)}, counts={counts}"
                )
            else:
                self.test("GET /api/admin/questions", False, f"status={response.status_code}")
        except Exception as e:
            self.test("GET /api/admin/questions", False, f"error={str(e)}")

    def run_all_tests(self):
        """Run all Sprint 5 backend smoke tests"""
        self.log("🚀", f"Starting Sprint 5 Backend Smoke Tests (BASE_URL={self.base_url})")
        self.log("", "=" * 80)

        self.test_asset_content_endpoints()
        self.test_admin_endpoints()

        self.log("", "=" * 80)
        self.log("📊", f"Tests completed: {self.tests_passed}/{self.tests_run} passed")
        
        if self.tests_failed:
            self.log("❌", f"Failed tests: {', '.join(self.tests_failed)}")
            return 1
        else:
            self.log("✅", "All Sprint 5 backend smoke tests passed!")
            return 0

def main():
    tester = Sprint5BackendTester()
    exit_code = tester.run_all_tests()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
