"""
LUMEN IR1 Slice 2 Backend Test Suite
Tests IR1.3 Notes + IR1.4 Tasks + IR1.5 Meetings + IR1.6 Timeline + IR1.8 Health
"""
import requests
import sys
import time
from datetime import datetime, timedelta

# Backend URL from frontend .env
BACKEND_URL = "https://repo-deploy-67.preview.emergentagent.com"

# Test credentials
ADMIN_EMAIL = "admin@atlas.dev"
ADMIN_PASSWORD = "admin123"

class IR1Slice2Tester:
    def __init__(self, base_url=BACKEND_URL):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []
        self.lead_id = None
        self.note_id = None
        self.task_id = None
        self.meeting_id = None

    def log(self, msg, level="INFO"):
        """Log test messages"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [{level}] {msg}")

    def run_test(self, name, method, endpoint, expected_status, data=None):
        """Run a single API test"""
        url = f"{self.base_url}{endpoint}"
        headers = {'Content-Type': 'application/json'}

        self.tests_run += 1
        self.log(f"\n🔍 Test #{self.tests_run}: {name}")
        self.log(f"   {method} {endpoint}")
        
        try:
            if method == 'GET':
                response = self.session.get(url, headers=headers, timeout=30)
            elif method == 'POST':
                response = self.session.post(url, json=data, headers=headers, timeout=30)
            elif method == 'PATCH':
                response = self.session.patch(url, json=data, headers=headers, timeout=30)
            elif method == 'DELETE':
                response = self.session.delete(url, headers=headers, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            
            if success:
                self.tests_passed += 1
                self.log(f"✅ PASSED - Status: {response.status_code}", "PASS")
                try:
                    resp_json = response.json()
                    return True, resp_json
                except:
                    return True, {}
            else:
                self.tests_failed += 1
                self.log(f"❌ FAILED - Expected {expected_status}, got {response.status_code}", "FAIL")
                try:
                    error_detail = response.json()
                    self.log(f"   Response: {error_detail}", "FAIL")
                except:
                    self.log(f"   Response: {response.text[:300]}", "FAIL")
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
            self.log(f"❌ FAILED - Error: {str(e)}", "FAIL")
            self.failures.append({
                "test": name,
                "endpoint": endpoint,
                "error": str(e)
            })
            return False, {}

    def test_login(self):
        """Test admin login"""
        self.log("\n" + "="*80)
        self.log("AUTHENTICATION TEST")
        self.log("="*80)
        
        success, response = self.run_test(
            "Admin Login",
            "POST",
            "/api/auth/login",
            200,
            data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        
        if not success:
            self.log("❌ Admin login failed - cannot proceed", "FAIL")
            return False
            
        cookies = self.session.cookies.get_dict()
        if 'session_token' in cookies:
            self.log(f"   Admin session cookie obtained", "INFO")
        
        return True

    def test_create_lead(self):
        """Test creating a lead"""
        self.log("\n" + "="*80)
        self.log("IR1 - CREATE LEAD")
        self.log("="*80)
        
        unique_email = f"test.lead.{int(time.time())}@example.com"
        success, data = self.run_test(
            "Create Lead",
            "POST",
            "/api/admin/ir/leads",
            200,
            data={
                "email": unique_email,
                "full_name": "Test Lead IR1 Slice2",
                "phone": "+380501234567",
                "source": "manual",
                "interest": "real_estate",
                "budget_range": "50k-100k"
            }
        )
        
        if success and data:
            self.lead_id = data.get('lead_id')
            manual_stage = data.get('manual_stage')
            owner_id = data.get('owner_id')
            user_id = data.get('user_id')
            
            self.log(f"   Lead ID: {self.lead_id}", "INFO")
            self.log(f"   Manual stage: {manual_stage}", "INFO")
            self.log(f"   Owner: {owner_id}", "INFO")
            self.log(f"   User ID: {user_id}", "INFO")
            
            # Verify requirements
            if manual_stage == 'lead' and owner_id is None and user_id is None:
                self.log(f"   ✓ Lead created with correct defaults", "PASS")
            else:
                self.log(f"   ⚠ Lead defaults not as expected", "WARN")
        
        return success

    def test_ir13_notes(self):
        """Test IR1.3 Notes - POST/GET/DELETE"""
        self.log("\n" + "="*80)
        self.log("IR1.3 - NOTES")
        self.log("="*80)
        
        if not self.lead_id:
            self.log("❌ No lead_id - skipping notes tests", "FAIL")
            return False
        
        # Get initial last_interaction_at
        success, lead_data = self.run_test(
            "Get Lead Before Note",
            "GET",
            f"/api/admin/ir/leads/{self.lead_id}",
            200
        )
        
        initial_last_interaction = None
        if success and lead_data:
            initial_last_interaction = lead_data.get('last_interaction_at')
            self.log(f"   Initial last_interaction_at: {initial_last_interaction}", "INFO")
        
        # POST - Create note
        success, note_data = self.run_test(
            "IR1.3 - Create Note",
            "POST",
            f"/api/admin/ir/leads/{self.lead_id}/notes",
            200,
            data={"body": "Test note for IR1.3 - checking last_interaction_at bump"}
        )
        
        if success and note_data:
            self.note_id = note_data.get('id')
            body = note_data.get('body')
            author_name = note_data.get('author_name')
            
            self.log(f"   Note ID: {self.note_id}", "INFO")
            self.log(f"   Body: {body[:50]}...", "INFO")
            self.log(f"   Author: {author_name}", "INFO")
            
            if self.note_id and body:
                self.log(f"   ✓ Note created successfully", "PASS")
        
        # Verify last_interaction_at was bumped
        time.sleep(1)  # Small delay to ensure timestamp difference
        success, lead_data = self.run_test(
            "Get Lead After Note (verify last_interaction_at bump)",
            "GET",
            f"/api/admin/ir/leads/{self.lead_id}",
            200
        )
        
        if success and lead_data:
            health = lead_data.get('health', {})
            new_last_interaction = health.get('last_interaction_at')
            self.log(f"   New last_interaction_at: {new_last_interaction}", "INFO")
            
            if new_last_interaction and new_last_interaction != initial_last_interaction:
                self.log(f"   ✓ last_interaction_at was bumped after note creation", "PASS")
            else:
                self.log(f"   ⚠ last_interaction_at was NOT bumped", "WARN")
        
        # GET - List notes
        success, notes_data = self.run_test(
            "IR1.3 - List Notes",
            "GET",
            f"/api/admin/ir/leads/{self.lead_id}/notes",
            200
        )
        
        if success and notes_data:
            notes = notes_data.get('notes', [])
            self.log(f"   Notes count: {len(notes)}", "INFO")
            
            if len(notes) > 0 and any(n.get('id') == self.note_id for n in notes):
                self.log(f"   ✓ Note found in list", "PASS")
        
        # DELETE - Remove note
        if self.note_id:
            success, delete_data = self.run_test(
                "IR1.3 - Delete Note",
                "DELETE",
                f"/api/admin/ir/notes/{self.note_id}",
                200
            )
            
            if success and delete_data:
                ok = delete_data.get('ok')
                if ok:
                    self.log(f"   ✓ Note deleted successfully", "PASS")
        
        return True

    def test_ir14_tasks(self):
        """Test IR1.4 Tasks - POST with FREE task_type, PATCH to complete"""
        self.log("\n" + "="*80)
        self.log("IR1.4 - TASKS")
        self.log("="*80)
        
        if not self.lead_id:
            self.log("❌ No lead_id - skipping tasks tests", "FAIL")
            return False
        
        # POST - Create task with FREE task_type (not enum)
        free_task_types = ["email", "follow_up", "custom_action", "call_investor"]
        
        for task_type in free_task_types:
            success, task_data = self.run_test(
                f"IR1.4 - Create Task (task_type='{task_type}')",
                "POST",
                f"/api/admin/ir/leads/{self.lead_id}/tasks",
                200,
                data={
                    "title": f"Test task with type {task_type}",
                    "description": "Testing free task_type field",
                    "task_type": task_type,
                    "priority": "normal",
                    "due_date": (datetime.now() + timedelta(days=7)).isoformat()
                }
            )
            
            if success and task_data:
                task_id = task_data.get('id')
                returned_task_type = task_data.get('task_type')
                status = task_data.get('status')
                
                self.log(f"   Task ID: {task_id}", "INFO")
                self.log(f"   Task type: {returned_task_type}", "INFO")
                self.log(f"   Status: {status}", "INFO")
                
                if returned_task_type == task_type and status == 'open':
                    self.log(f"   ✓ Task created with FREE task_type '{task_type}'", "PASS")
                    
                    # Save first task for completion test
                    if not self.task_id:
                        self.task_id = task_id
        
        # PATCH - Complete task and verify last_interaction_at bump
        if self.task_id:
            # Get current last_interaction_at
            success, lead_data = self.run_test(
                "Get Lead Before Task Completion",
                "GET",
                f"/api/admin/ir/leads/{self.lead_id}",
                200
            )
            
            before_last_interaction = None
            if success and lead_data:
                health = lead_data.get('health', {})
                before_last_interaction = health.get('last_interaction_at')
            
            time.sleep(1)
            
            success, task_data = self.run_test(
                "IR1.4 - Complete Task (PATCH status=done)",
                "PATCH",
                f"/api/admin/ir/tasks/{self.task_id}",
                200,
                data={"status": "done"}
            )
            
            if success and task_data:
                status = task_data.get('status')
                completed_at = task_data.get('completed_at')
                
                self.log(f"   Status: {status}", "INFO")
                self.log(f"   Completed at: {completed_at}", "INFO")
                
                if status == 'done' and completed_at:
                    self.log(f"   ✓ Task completed successfully", "PASS")
            
            # Verify last_interaction_at was bumped
            time.sleep(1)
            success, lead_data = self.run_test(
                "Get Lead After Task Completion (verify last_interaction_at bump)",
                "GET",
                f"/api/admin/ir/leads/{self.lead_id}",
                200
            )
            
            if success and lead_data:
                health = lead_data.get('health', {})
                after_last_interaction = health.get('last_interaction_at')
                
                if after_last_interaction and after_last_interaction != before_last_interaction:
                    self.log(f"   ✓ last_interaction_at was bumped after task completion", "PASS")
                else:
                    self.log(f"   ⚠ last_interaction_at was NOT bumped", "WARN")
        
        return True

    def test_ir15_meetings(self):
        """Test IR1.5 Meetings - POST with calendar placeholder fields"""
        self.log("\n" + "="*80)
        self.log("IR1.5 - MEETINGS")
        self.log("="*80)
        
        if not self.lead_id:
            self.log("❌ No lead_id - skipping meetings tests", "FAIL")
            return False
        
        # POST - Create meeting
        success, meeting_data = self.run_test(
            "IR1.5 - Create Meeting",
            "POST",
            f"/api/admin/ir/leads/{self.lead_id}/meetings",
            200,
            data={
                "title": "Initial consultation call",
                "scheduled_at": (datetime.now() + timedelta(days=3)).isoformat(),
                "type": "video",
                "duration_min": 45,
                "outcome_note": "Discuss investment opportunities"
            }
        )
        
        if success and meeting_data:
            self.meeting_id = meeting_data.get('id')
            title = meeting_data.get('title')
            status = meeting_data.get('status')
            
            # Check calendar placeholder fields (3b requirement)
            external_calendar_provider = meeting_data.get('external_calendar_provider')
            external_event_id = meeting_data.get('external_event_id')
            calendar_sync_status = meeting_data.get('calendar_sync_status')
            
            self.log(f"   Meeting ID: {self.meeting_id}", "INFO")
            self.log(f"   Title: {title}", "INFO")
            self.log(f"   Status: {status}", "INFO")
            self.log(f"   external_calendar_provider: {external_calendar_provider}", "INFO")
            self.log(f"   external_event_id: {external_event_id}", "INFO")
            self.log(f"   calendar_sync_status: {calendar_sync_status}", "INFO")
            
            # Verify placeholder fields exist and are null (3b)
            if (external_calendar_provider is None and 
                external_event_id is None and 
                calendar_sync_status is None):
                self.log(f"   ✓ Calendar placeholder fields present (all null as expected)", "PASS")
            else:
                self.log(f"   ⚠ Calendar placeholder fields not as expected", "WARN")
        
        return True

    def test_ir16_timeline(self):
        """Test IR1.6 Unified Timeline - GET with all event types"""
        self.log("\n" + "="*80)
        self.log("IR1.6 - UNIFIED TIMELINE")
        self.log("="*80)
        
        if not self.lead_id:
            self.log("❌ No lead_id - skipping timeline tests", "FAIL")
            return False
        
        # GET - Timeline
        success, timeline_data = self.run_test(
            "IR1.6 - Get Unified Timeline",
            "GET",
            f"/api/admin/ir/leads/{self.lead_id}/timeline",
            200
        )
        
        if success and timeline_data:
            timeline = timeline_data.get('timeline', [])
            count = timeline_data.get('count', 0)
            
            self.log(f"   Timeline events count: {count}", "INFO")
            
            # Check for expected event kinds
            event_kinds = set(event.get('kind') for event in timeline)
            self.log(f"   Event kinds found: {event_kinds}", "INFO")
            
            expected_kinds = {
                'lead_created',
                'note',
                'task_created',
                'task_completed',
                'meeting_scheduled'
            }
            
            found_kinds = expected_kinds & event_kinds
            self.log(f"   Expected kinds found: {found_kinds}", "INFO")
            
            # Verify timeline is sorted by 'at' desc
            if len(timeline) > 1:
                is_sorted = all(
                    timeline[i].get('at', '') >= timeline[i+1].get('at', '')
                    for i in range(len(timeline)-1)
                )
                if is_sorted:
                    self.log(f"   ✓ Timeline is sorted by 'at' desc", "PASS")
                else:
                    self.log(f"   ⚠ Timeline is NOT sorted correctly", "WARN")
            
            if len(found_kinds) >= 3:
                self.log(f"   ✓ Timeline includes multiple event types", "PASS")
        
        return True

    def test_ir18_health(self):
        """Test IR1.8 Investor Health - GET with color/reasons logic"""
        self.log("\n" + "="*80)
        self.log("IR1.8 - INVESTOR HEALTH")
        self.log("="*80)
        
        if not self.lead_id:
            self.log("❌ No lead_id - skipping health tests", "FAIL")
            return False
        
        # GET - Health
        success, health_data = self.run_test(
            "IR1.8 - Get Investor Health",
            "GET",
            f"/api/admin/ir/leads/{self.lead_id}/health",
            200
        )
        
        if success and health_data:
            color = health_data.get('color')
            reasons = health_data.get('reasons', [])
            open_tasks = health_data.get('open_tasks')
            overdue_task = health_data.get('overdue_task')
            last_interaction_at = health_data.get('last_interaction_at')
            last_interaction_days = health_data.get('last_interaction_days')
            
            self.log(f"   Color: {color}", "INFO")
            self.log(f"   Reasons: {reasons}", "INFO")
            self.log(f"   Open tasks: {open_tasks}", "INFO")
            self.log(f"   Overdue task: {overdue_task}", "INFO")
            self.log(f"   Last interaction at: {last_interaction_at}", "INFO")
            self.log(f"   Last interaction days: {last_interaction_days}", "INFO")
            
            # Verify health logic (4a)
            # Brand-new lead with no linked user → should be RED (KYC missing)
            if color == 'red' and any('KYC' in str(r) for r in reasons):
                self.log(f"   ✓ Health is RED due to missing KYC (correct for new lead)", "PASS")
            
            # Verify last_interaction_at is present
            if last_interaction_at:
                self.log(f"   ✓ last_interaction_at is present", "PASS")
            
            # Verify open_tasks count
            if open_tasks >= 0:
                self.log(f"   ✓ open_tasks count is valid", "PASS")
        
        return True

    def test_negative_late_stage(self):
        """Test negative path: POST stage with LATE stage should return 400"""
        self.log("\n" + "="*80)
        self.log("NEGATIVE TEST - LATE STAGE MANUAL OVERRIDE")
        self.log("="*80)
        
        if not self.lead_id:
            self.log("❌ No lead_id - skipping negative test", "FAIL")
            return False
        
        late_stages = ["kyc", "accredited", "funding_pending", "funded", "active"]
        
        for stage in late_stages:
            success, data = self.run_test(
                f"Negative - Set Late Stage '{stage}' (expect 400)",
                "POST",
                f"/api/admin/ir/leads/{self.lead_id}/stage",
                400,
                data={"stage": stage, "note": "Attempting manual override of derived stage"}
            )
            
            if success:
                self.log(f"   ✓ Late stage '{stage}' correctly rejected with 400", "PASS")
        
        return True

    def test_auth_negative(self):
        """Test auth: anonymous and non-admin should be rejected"""
        self.log("\n" + "="*80)
        self.log("AUTH NEGATIVE TESTS")
        self.log("="*80)
        
        # Test 1: Anonymous request (no cookie) → 401
        anon_session = requests.Session()
        url = f"{self.base_url}/api/admin/ir/leads"
        
        self.tests_run += 1
        self.log(f"\n🔍 Test #{self.tests_run}: Anonymous Request (expect 401)")
        
        try:
            response = anon_session.get(url, timeout=10)
            if response.status_code == 401:
                self.tests_passed += 1
                self.log(f"✅ PASSED - Anonymous request rejected with 401", "PASS")
            else:
                self.tests_failed += 1
                self.log(f"❌ FAILED - Expected 401, got {response.status_code}", "FAIL")
        except Exception as e:
            self.tests_failed += 1
            self.log(f"❌ FAILED - Error: {str(e)}", "FAIL")
        
        # Note: Testing non-admin (403) would require a non-admin user account
        # which is not provided in the test credentials
        
        return True

    def print_summary(self):
        """Print test summary"""
        self.log("\n" + "="*80)
        self.log("TEST SUMMARY")
        self.log("="*80)
        
        total = self.tests_run
        passed = self.tests_passed
        failed = self.tests_failed
        pass_rate = (passed / total * 100) if total > 0 else 0
        
        self.log(f"Total Tests: {total}")
        self.log(f"Passed: {passed} ({pass_rate:.1f}%)", "PASS" if pass_rate >= 80 else "WARN")
        self.log(f"Failed: {failed}", "FAIL" if failed > 0 else "INFO")
        
        if self.failures:
            self.log("\n" + "="*80)
            self.log("FAILED TESTS DETAILS")
            self.log("="*80)
            for i, failure in enumerate(self.failures, 1):
                self.log(f"\n{i}. {failure.get('test', 'Unknown')}")
                self.log(f"   Endpoint: {failure.get('endpoint', 'N/A')}")
                if 'error' in failure:
                    self.log(f"   Error: {failure['error']}")
                else:
                    self.log(f"   Expected: {failure.get('expected', 'N/A')}")
                    self.log(f"   Actual: {failure.get('actual', 'N/A')}")
                    self.log(f"   Response: {failure.get('response', 'N/A')}")
        
        return 0 if failed == 0 else 1

def main():
    """Main test runner"""
    print("\n" + "="*80)
    print("LUMEN IR1 SLICE 2 - BACKEND TEST SUITE")
    print("Testing: IR1.3 Notes + IR1.4 Tasks + IR1.5 Meetings")
    print("         IR1.6 Timeline + IR1.8 Health")
    print("="*80)
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Test Time: {datetime.now().isoformat()}")
    print("="*80)
    
    tester = IR1Slice2Tester(BACKEND_URL)
    
    # Authentication
    if not tester.test_login():
        print("\n❌ Login failed - cannot proceed with tests")
        return 1
    
    # Create test lead
    if not tester.test_create_lead():
        print("\n❌ Lead creation failed - cannot proceed with tests")
        return 1
    
    # IR1.3 Notes
    tester.test_ir13_notes()
    
    # IR1.4 Tasks
    tester.test_ir14_tasks()
    
    # IR1.5 Meetings
    tester.test_ir15_meetings()
    
    # IR1.6 Timeline
    tester.test_ir16_timeline()
    
    # IR1.8 Health
    tester.test_ir18_health()
    
    # Negative tests
    tester.test_negative_late_stage()
    tester.test_auth_negative()
    
    # Print summary and return exit code
    return tester.print_summary()

if __name__ == "__main__":
    sys.exit(main())
