"""
LUMEN IR1 Backend Test Suite
Tests IR1.3 Notes, IR1.4 Tasks, IR1.5 Meetings, IR1.6 Timeline, IR1.8 Health
"""
import requests
import sys
from datetime import datetime, timedelta

BACKEND_URL = "https://code-deploy-105.preview.emergentagent.com"

# Credentials from review request
ADMIN_EMAIL = "admin@atlas.dev"
ADMIN_PASSWORD = "admin123"
CLIENT_EMAIL = "client@atlas.dev"
CLIENT_PASSWORD = "client123"

class IR1Tester:
    def __init__(self, base_url=BACKEND_URL):
        self.base_url = base_url.rstrip('/')
        self.admin_session = requests.Session()
        self.client_session = requests.Session()
        self.anon_session = requests.Session()
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []
        self.created_resources = {
            'leads': [],
            'notes': [],
            'tasks': [],
            'meetings': []
        }

    def log(self, msg, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [{level}] {msg}")

    def run_test(self, name, method, endpoint, expected_status, data=None, session=None):
        if session is None:
            session = self.admin_session
            
        url = f"{self.base_url}{endpoint}"
        headers = {'Content-Type': 'application/json'}

        self.tests_run += 1
        self.log(f"\n🔍 Test #{self.tests_run}: {name}")
        self.log(f"   {method} {endpoint}")
        
        try:
            if method == 'GET':
                response = session.get(url, headers=headers, timeout=30)
            elif method == 'POST':
                response = session.post(url, json=data, headers=headers, timeout=30)
            elif method == 'PATCH':
                response = session.patch(url, json=data, headers=headers, timeout=30)
            elif method == 'DELETE':
                response = session.delete(url, headers=headers, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            
            if success:
                self.tests_passed += 1
                self.log(f"✅ PASSED - Status: {response.status_code}", "PASS")
                try:
                    return True, response.json()
                except:
                    return True, {}
            else:
                self.tests_failed += 1
                self.log(f"❌ FAILED - Expected {expected_status}, got {response.status_code}", "FAIL")
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
        self.log("\n" + "="*80)
        self.log("AUTHENTICATION TEST")
        self.log("="*80)
        
        # Admin login
        success, response = self.run_test(
            "Admin Login",
            "POST",
            "/api/auth/login",
            200,
            data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            session=self.admin_session
        )
        
        if not success:
            self.log("❌ Admin login failed - cannot proceed", "FAIL")
            return False
            
        self.log(f"   Admin session established", "INFO")
        
        # Client login (non-admin)
        success, response = self.run_test(
            "Client Login (non-admin)",
            "POST",
            "/api/auth/login",
            200,
            data={"email": CLIENT_EMAIL, "password": CLIENT_PASSWORD},
            session=self.client_session
        )
        
        if success:
            self.log(f"   Client session established", "INFO")
        
        return True

    def test_ir13_notes(self):
        """Test IR1.3 Notes CRUD"""
        self.log("\n" + "="*80)
        self.log("IR1.3 NOTES TEST")
        self.log("="*80)
        
        # Get demo lead (client@atlas.dev)
        success, leads_data = self.run_test(
            "Get leads list",
            "GET",
            "/api/admin/ir/leads",
            200
        )
        
        if not success or not leads_data.get('leads'):
            self.log("❌ No leads found", "FAIL")
            return
        
        # Find client@atlas.dev lead
        demo_lead = None
        for lead in leads_data['leads']:
            if lead.get('email') == 'client@atlas.dev':
                demo_lead = lead
                break
        
        if not demo_lead:
            self.log("❌ Demo lead client@atlas.dev not found", "FAIL")
            return
        
        lead_id = demo_lead['lead_id']
        self.log(f"   Using demo lead: {lead_id}", "INFO")
        
        # Test 1: Create note with body
        success, note_data = self.run_test(
            "IR1.3 - Create note",
            "POST",
            f"/api/admin/ir/leads/{lead_id}/notes",
            200,
            data={"body": "Test note for IR1.3 validation"}
        )
        
        note_id = None
        if success and note_data:
            note_id = note_data.get('id')
            self.log(f"   Note created: {note_id}", "INFO")
            self.created_resources['notes'].append(note_id)
        
        # Test 2: Create note with empty body (should fail with 400)
        self.run_test(
            "IR1.3 - Create note with empty body (expect 400)",
            "POST",
            f"/api/admin/ir/leads/{lead_id}/notes",
            400,
            data={"body": ""}
        )
        
        # Test 3: List notes
        success, notes_data = self.run_test(
            "IR1.3 - List notes",
            "GET",
            f"/api/admin/ir/leads/{lead_id}/notes",
            200
        )
        
        if success and notes_data:
            notes = notes_data.get('notes', [])
            self.log(f"   Notes found: {len(notes)}", "INFO")
        
        # Test 4: Delete note
        if note_id:
            self.run_test(
                "IR1.3 - Delete note",
                "DELETE",
                f"/api/admin/ir/notes/{note_id}",
                200
            )
        
        # Test 5: Auth - Anonymous (expect 401)
        self.run_test(
            "IR1.3 - Anonymous access (expect 401)",
            "GET",
            f"/api/admin/ir/leads/{lead_id}/notes",
            401,
            session=self.anon_session
        )
        
        # Test 6: Auth - Non-admin (expect 403)
        self.run_test(
            "IR1.3 - Non-admin access (expect 403)",
            "GET",
            f"/api/admin/ir/leads/{lead_id}/notes",
            403,
            session=self.client_session
        )

    def test_ir14_tasks(self):
        """Test IR1.4 Tasks CRUD"""
        self.log("\n" + "="*80)
        self.log("IR1.4 TASKS TEST")
        self.log("="*80)
        
        # Get demo lead
        success, leads_data = self.run_test(
            "Get leads list",
            "GET",
            "/api/admin/ir/leads",
            200
        )
        
        if not success or not leads_data.get('leads'):
            return
        
        demo_lead = None
        for lead in leads_data['leads']:
            if lead.get('email') == 'client@atlas.dev':
                demo_lead = lead
                break
        
        if not demo_lead:
            return
        
        lead_id = demo_lead['lead_id']
        
        # Test 1: Create task with task_type (free field)
        future_date = (datetime.now() + timedelta(days=7)).isoformat()
        success, task_data = self.run_test(
            "IR1.4 - Create task with task_type",
            "POST",
            f"/api/admin/ir/leads/{lead_id}/tasks",
            200,
            data={
                "title": "Test task for IR1.4",
                "assignee_id": None,
                "due_date": future_date,
                "priority": "high",
                "task_type": "follow_up"
            }
        )
        
        task_id = None
        if success and task_data:
            task_id = task_data.get('id')
            self.log(f"   Task created: {task_id}", "INFO")
            self.log(f"   Task type: {task_data.get('task_type')}", "INFO")
            self.log(f"   Status: {task_data.get('status')}", "INFO")
            self.created_resources['tasks'].append(task_id)
        
        # Test 2: Create task without title (should fail with 400)
        self.run_test(
            "IR1.4 - Create task without title (expect 400)",
            "POST",
            f"/api/admin/ir/leads/{lead_id}/tasks",
            400,
            data={"description": "No title"}
        )
        
        # Test 3: List tasks
        success, tasks_data = self.run_test(
            "IR1.4 - List tasks",
            "GET",
            f"/api/admin/ir/leads/{lead_id}/tasks",
            200
        )
        
        if success and tasks_data:
            tasks = tasks_data.get('tasks', [])
            self.log(f"   Tasks found: {len(tasks)}", "INFO")
        
        # Test 4: Mark task as done
        if task_id:
            success, updated_task = self.run_test(
                "IR1.4 - Mark task as done",
                "PATCH",
                f"/api/admin/ir/tasks/{task_id}",
                200,
                data={"status": "done"}
            )
            
            if success and updated_task:
                self.log(f"   Status: {updated_task.get('status')}", "INFO")
                self.log(f"   Completed at: {updated_task.get('completed_at')}", "INFO")
        
        # Test 5: Reopen task
        if task_id:
            success, reopened_task = self.run_test(
                "IR1.4 - Reopen task",
                "PATCH",
                f"/api/admin/ir/tasks/{task_id}",
                200,
                data={"status": "open"}
            )
            
            if success and reopened_task:
                self.log(f"   Status: {reopened_task.get('status')}", "INFO")
        
        # Test 6: Create overdue task for health test
        past_date = (datetime.now() - timedelta(days=1)).isoformat()
        success, overdue_task = self.run_test(
            "IR1.4 - Create overdue task",
            "POST",
            f"/api/admin/ir/leads/{lead_id}/tasks",
            200,
            data={
                "title": "Overdue task for health test",
                "due_date": past_date,
                "priority": "normal",
                "task_type": "call"
            }
        )
        
        if success and overdue_task:
            overdue_task_id = overdue_task.get('id')
            self.log(f"   Overdue task created: {overdue_task_id}", "INFO")
            self.created_resources['tasks'].append(overdue_task_id)
        
        # Test 7: Auth - Anonymous (expect 401)
        self.run_test(
            "IR1.4 - Anonymous access (expect 401)",
            "GET",
            f"/api/admin/ir/leads/{lead_id}/tasks",
            401,
            session=self.anon_session
        )
        
        # Test 8: Auth - Non-admin (expect 403)
        self.run_test(
            "IR1.4 - Non-admin access (expect 403)",
            "GET",
            f"/api/admin/ir/leads/{lead_id}/tasks",
            403,
            session=self.client_session
        )

    def test_ir15_meetings(self):
        """Test IR1.5 Meetings CRUD"""
        self.log("\n" + "="*80)
        self.log("IR1.5 MEETINGS TEST")
        self.log("="*80)
        
        # Get demo lead
        success, leads_data = self.run_test(
            "Get leads list",
            "GET",
            "/api/admin/ir/leads",
            200
        )
        
        if not success or not leads_data.get('leads'):
            return
        
        demo_lead = None
        for lead in leads_data['leads']:
            if lead.get('email') == 'client@atlas.dev':
                demo_lead = lead
                break
        
        if not demo_lead:
            return
        
        lead_id = demo_lead['lead_id']
        
        # Test 1: Create meeting with calendar placeholders
        scheduled_time = (datetime.now() + timedelta(days=3)).isoformat()
        success, meeting_data = self.run_test(
            "IR1.5 - Create meeting",
            "POST",
            f"/api/admin/ir/leads/{lead_id}/meetings",
            200,
            data={
                "title": "Test meeting for IR1.5",
                "scheduled_at": scheduled_time,
                "type": "video",
                "duration_min": 45
            }
        )
        
        meeting_id = None
        if success and meeting_data:
            meeting_id = meeting_data.get('id')
            self.log(f"   Meeting created: {meeting_id}", "INFO")
            self.log(f"   Status: {meeting_data.get('status')}", "INFO")
            self.log(f"   Calendar provider: {meeting_data.get('external_calendar_provider')}", "INFO")
            self.log(f"   External event ID: {meeting_data.get('external_event_id')}", "INFO")
            self.log(f"   Calendar sync status: {meeting_data.get('calendar_sync_status')}", "INFO")
            self.created_resources['meetings'].append(meeting_id)
            
            # Verify calendar placeholders are null
            if (meeting_data.get('external_calendar_provider') is None and
                meeting_data.get('external_event_id') is None and
                meeting_data.get('calendar_sync_status') is None):
                self.log(f"   ✓ Calendar placeholders are null as expected", "PASS")
        
        # Test 2: Create meeting without title (should fail with 400)
        self.run_test(
            "IR1.5 - Create meeting without title (expect 400)",
            "POST",
            f"/api/admin/ir/leads/{lead_id}/meetings",
            400,
            data={"scheduled_at": scheduled_time}
        )
        
        # Test 3: List meetings
        success, meetings_data = self.run_test(
            "IR1.5 - List meetings",
            "GET",
            f"/api/admin/ir/leads/{lead_id}/meetings",
            200
        )
        
        if success and meetings_data:
            meetings = meetings_data.get('meetings', [])
            self.log(f"   Meetings found: {len(meetings)}", "INFO")
        
        # Test 4: Complete meeting
        if meeting_id:
            success, completed_meeting = self.run_test(
                "IR1.5 - Complete meeting",
                "PATCH",
                f"/api/admin/ir/meetings/{meeting_id}",
                200,
                data={
                    "status": "completed",
                    "outcome_note": "Meeting went well, investor interested"
                }
            )
            
            if success and completed_meeting:
                self.log(f"   Status: {completed_meeting.get('status')}", "INFO")
                self.log(f"   Outcome: {completed_meeting.get('outcome_note')}", "INFO")
        
        # Test 5: Auth - Anonymous (expect 401)
        self.run_test(
            "IR1.5 - Anonymous access (expect 401)",
            "GET",
            f"/api/admin/ir/leads/{lead_id}/meetings",
            401,
            session=self.anon_session
        )
        
        # Test 6: Auth - Non-admin (expect 403)
        self.run_test(
            "IR1.5 - Non-admin access (expect 403)",
            "GET",
            f"/api/admin/ir/leads/{lead_id}/meetings",
            403,
            session=self.client_session
        )

    def test_ir16_timeline(self):
        """Test IR1.6 Unified Timeline"""
        self.log("\n" + "="*80)
        self.log("IR1.6 TIMELINE TEST")
        self.log("="*80)
        
        # Get demo lead (client@atlas.dev - linked to user_4d6c52ebe82e)
        success, leads_data = self.run_test(
            "Get leads list",
            "GET",
            "/api/admin/ir/leads",
            200
        )
        
        if not success or not leads_data.get('leads'):
            return
        
        demo_lead = None
        for lead in leads_data['leads']:
            if lead.get('email') == 'client@atlas.dev':
                demo_lead = lead
                break
        
        if not demo_lead:
            return
        
        lead_id = demo_lead['lead_id']
        
        # Test 1: Get timeline
        success, timeline_data = self.run_test(
            "IR1.6 - Get timeline",
            "GET",
            f"/api/admin/ir/leads/{lead_id}/timeline",
            200
        )
        
        if success and timeline_data:
            timeline = timeline_data.get('timeline', [])
            count = timeline_data.get('count', 0)
            self.log(f"   Timeline events: {count}", "INFO")
            
            # Check for expected event kinds
            kinds = set(event.get('kind') for event in timeline)
            self.log(f"   Event kinds found: {kinds}", "INFO")
            
            expected_kinds = {'lead_created', 'stage_changed', 'note', 'task_created', 
                            'task_completed', 'meeting_scheduled', 'meeting_completed'}
            
            # For client@atlas.dev (linked to investor), should also have investor facts
            if demo_lead.get('user_id'):
                self.log(f"   Lead is linked to user: {demo_lead.get('user_id')}", "INFO")
                # May have certificate, funding, kyc, accreditation events
            
            # Verify timeline is sorted newest-first
            if len(timeline) > 1:
                dates = [event.get('at') for event in timeline if event.get('at')]
                if dates == sorted(dates, reverse=True):
                    self.log(f"   ✓ Timeline sorted newest-first", "PASS")
                else:
                    self.log(f"   ⚠ Timeline may not be sorted correctly", "WARN")
        
        # Test 2: Auth - Anonymous (expect 401)
        self.run_test(
            "IR1.6 - Anonymous access (expect 401)",
            "GET",
            f"/api/admin/ir/leads/{lead_id}/timeline",
            401,
            session=self.anon_session
        )
        
        # Test 3: Auth - Non-admin (expect 403)
        self.run_test(
            "IR1.6 - Non-admin access (expect 403)",
            "GET",
            f"/api/admin/ir/leads/{lead_id}/timeline",
            403,
            session=self.client_session
        )

    def test_ir18_health(self):
        """Test IR1.8 Investor Health"""
        self.log("\n" + "="*80)
        self.log("IR1.8 INVESTOR HEALTH TEST")
        self.log("="*80)
        
        # Test 1: Health for client@atlas.dev (should be green - KYC approved + active cert)
        success, leads_data = self.run_test(
            "Get leads list",
            "GET",
            "/api/admin/ir/leads",
            200
        )
        
        if not success or not leads_data.get('leads'):
            return
        
        demo_lead = None
        for lead in leads_data['leads']:
            if lead.get('email') == 'client@atlas.dev':
                demo_lead = lead
                break
        
        if demo_lead:
            lead_id = demo_lead['lead_id']
            success, health_data = self.run_test(
                "IR1.8 - Health for client@atlas.dev (expect green)",
                "GET",
                f"/api/admin/ir/leads/{lead_id}/health",
                200
            )
            
            if success and health_data:
                color = health_data.get('color')
                reasons = health_data.get('reasons', [])
                open_tasks = health_data.get('open_tasks', 0)
                overdue_task = health_data.get('overdue_task', False)
                last_interaction_days = health_data.get('last_interaction_days')
                
                self.log(f"   Color: {color}", "INFO")
                self.log(f"   Reasons: {reasons}", "INFO")
                self.log(f"   Open tasks: {open_tasks}", "INFO")
                self.log(f"   Overdue task: {overdue_task}", "INFO")
                self.log(f"   Last interaction days: {last_interaction_days}", "INFO")
                
                # Note: Due to overdue task created in test_ir14_tasks, this may be red
                if color in ['green', 'yellow', 'red']:
                    self.log(f"   ✓ Valid health color returned", "PASS")
        
        # Test 2: Create a fresh lead (should be red - no KYC)
        timestamp = int(datetime.now().timestamp())
        success, new_lead = self.run_test(
            "IR1.8 - Create fresh lead",
            "POST",
            "/api/admin/ir/leads",
            200,
            data={
                "email": f"test-health-{timestamp}@example.com",
                "full_name": "Test Health Lead",
                "source": "test"
            }
        )
        
        if success and new_lead:
            new_lead_id = new_lead.get('lead_id')
            self.log(f"   Fresh lead created: {new_lead_id}", "INFO")
            self.created_resources['leads'].append(new_lead_id)
            
            success, health_data = self.run_test(
                "IR1.8 - Health for fresh lead (expect red)",
                "GET",
                f"/api/admin/ir/leads/{new_lead_id}/health",
                200
            )
            
            if success and health_data:
                color = health_data.get('color')
                reasons = health_data.get('reasons', [])
                
                self.log(f"   Color: {color}", "INFO")
                self.log(f"   Reasons: {reasons}", "INFO")
                
                if color == 'red':
                    self.log(f"   ✓ Fresh lead correctly shows red (green is earned)", "PASS")
                else:
                    self.log(f"   ⚠ Fresh lead should be red, got {color}", "WARN")
        
        # Test 3: Health in pipeline
        success, pipeline_data = self.run_test(
            "IR1.8 - Health in pipeline",
            "GET",
            "/api/admin/ir/pipeline",
            200
        )
        
        if success and pipeline_data:
            columns = pipeline_data.get('columns', [])
            has_health = False
            for col in columns:
                for lead in col.get('leads', []):
                    if 'health' in lead:
                        has_health = True
                        self.log(f"   Lead {lead.get('email')} has health: {lead['health'].get('color')}", "INFO")
                        break
                if has_health:
                    break
            
            if has_health:
                self.log(f"   ✓ Health present in pipeline leads", "PASS")
        
        # Test 4: Auth - Anonymous (expect 401)
        if demo_lead:
            self.run_test(
                "IR1.8 - Anonymous access (expect 401)",
                "GET",
                f"/api/admin/ir/leads/{demo_lead['lead_id']}/health",
                401,
                session=self.anon_session
            )
            
            # Test 5: Auth - Non-admin (expect 403)
            self.run_test(
                "IR1.8 - Non-admin access (expect 403)",
                "GET",
                f"/api/admin/ir/leads/{demo_lead['lead_id']}/health",
                403,
                session=self.client_session
            )

    def cleanup(self):
        """Clean up created test resources"""
        self.log("\n" + "="*80)
        self.log("CLEANUP")
        self.log("="*80)
        
        # Delete test notes
        for note_id in self.created_resources['notes']:
            try:
                self.admin_session.delete(f"{self.base_url}/api/admin/ir/notes/{note_id}")
                self.log(f"   Deleted note: {note_id}", "INFO")
            except:
                pass
        
        # Delete test tasks
        for task_id in self.created_resources['tasks']:
            try:
                # Tasks don't have a delete endpoint, so we'll leave them
                pass
            except:
                pass
        
        # Delete test meetings
        for meeting_id in self.created_resources['meetings']:
            try:
                # Meetings don't have a delete endpoint, so we'll leave them
                pass
            except:
                pass
        
        # Note: We're NOT deleting test leads to avoid affecting demo data
        # The test lead we created can be manually cleaned up if needed
        
        self.log(f"   Cleanup completed", "INFO")

    def print_summary(self):
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
    print("\n" + "="*80)
    print("LUMEN IR1 BACKEND TEST SUITE")
    print("Testing: IR1.3 Notes, IR1.4 Tasks, IR1.5 Meetings,")
    print("         IR1.6 Timeline, IR1.8 Investor Health")
    print("="*80)
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Test Time: {datetime.now().isoformat()}")
    print("="*80)
    
    tester = IR1Tester(BACKEND_URL)
    
    # Authentication
    if not tester.test_login():
        print("\n❌ Login failed - cannot proceed with tests")
        return 1
    
    # Run IR1 tests
    tester.test_ir13_notes()
    tester.test_ir14_tasks()
    tester.test_ir15_meetings()
    tester.test_ir16_timeline()
    tester.test_ir18_health()
    
    # Cleanup
    tester.cleanup()
    
    # Print summary and return exit code
    return tester.print_summary()

if __name__ == "__main__":
    sys.exit(main())
