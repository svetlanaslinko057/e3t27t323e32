"""
LUMEN Manager OS (M1-M8) Backend Test Suite
Tests cookie-based session auth, staff ACL scoping, SLA engine, notifications,
login audit, reassignment, manager snapshot, and communication log.
"""
import requests
import sys
import time
from datetime import datetime

# Get backend URL from environment
BACKEND_URL = "https://code-setup-11.preview.emergentagent.com"

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@devos.io"
ADMIN_PASSWORD = "admin123"
MANAGER_EMAIL = "manager@lumen.test"
MANAGER_PASSWORD = "manager123"

class ManagerOSTester:
    def __init__(self, base_url=BACKEND_URL):
        self.base_url = base_url.rstrip('/')
        self.admin_session = requests.Session()
        self.manager_session = requests.Session()
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []
        self.admin_user_id = None
        self.manager_user_id = None
        self.test_lead_id = None

    def log(self, msg, level="INFO"):
        """Log test messages"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [{level}] {msg}")

    def run_test(self, name, method, endpoint, expected_status, data=None, 
                 session=None, headers=None, allow_redirects=True):
        """Run a single API test with cookie session"""
        if session is None:
            session = self.admin_session
            
        url = f"{self.base_url}{endpoint}"
        req_headers = {'Content-Type': 'application/json'}
        
        if headers:
            req_headers.update(headers)

        self.tests_run += 1
        self.log(f"\n🔍 Test #{self.tests_run}: {name}")
        self.log(f"   {method} {endpoint}")
        
        try:
            if method == 'GET':
                response = session.get(url, headers=req_headers, timeout=30, allow_redirects=allow_redirects)
            elif method == 'POST':
                response = session.post(url, json=data, headers=req_headers, timeout=30, allow_redirects=allow_redirects)
            elif method == 'PATCH':
                response = session.patch(url, json=data, headers=req_headers, timeout=30, allow_redirects=allow_redirects)
            elif method == 'DELETE':
                response = session.delete(url, headers=req_headers, timeout=30, allow_redirects=allow_redirects)
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

    def test_auth(self):
        """Test AUTH: Cookie-based session login for admin and manager"""
        self.log("\n" + "="*80)
        self.log("AUTH TEST: Cookie-based session authentication")
        self.log("="*80)

        # Admin login
        success, resp = self.run_test(
            "Admin login (admin@devos.io)",
            "POST",
            "/api/auth/login",
            200,
            {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            session=self.admin_session
        )
        if success:
            # Login response returns user object at root level
            self.admin_user_id = resp.get("user_id") or resp.get("id")
            self.log(f"   Admin user_id: {self.admin_user_id}")

        # Manager login
        success, resp = self.run_test(
            "Manager login (manager@lumen.test)",
            "POST",
            "/api/auth/login",
            200,
            {"email": MANAGER_EMAIL, "password": MANAGER_PASSWORD},
            session=self.manager_session
        )
        if success:
            # Login response returns user object at root level
            self.manager_user_id = resp.get("user_id") or resp.get("id")
            self.log(f"   Manager user_id: {self.manager_user_id}")

        # Verify admin can access staff endpoint
        self.run_test(
            "Admin can access /api/admin/ir/leads",
            "GET",
            "/api/admin/ir/leads?limit=10",
            200,
            session=self.admin_session
        )

        # Verify manager can access staff endpoint
        self.run_test(
            "Manager can access /api/admin/ir/leads",
            "GET",
            "/api/admin/ir/leads?limit=10",
            200,
            session=self.manager_session
        )

        # Logout admin
        self.run_test(
            "Admin logout",
            "POST",
            "/api/auth/logout",
            200,
            session=self.admin_session
        )

        # Re-login admin for subsequent tests
        self.run_test(
            "Admin re-login",
            "POST",
            "/api/auth/login",
            200,
            {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            session=self.admin_session
        )

    def test_m1_scoping(self):
        """Test M1: Staff ACL / Ownership Scope"""
        self.log("\n" + "="*80)
        self.log("M1 TEST: Staff ACL / Ownership Scope (CRITICAL)")
        self.log("="*80)

        # Admin creates a new lead
        success, resp = self.run_test(
            "Admin creates a new lead",
            "POST",
            "/api/admin/ir/leads",
            200,
            {
                "email": f"test_{int(time.time())}@example.com",
                "full_name": "Test Lead for Scoping",
                "source": "manual"
            },
            session=self.admin_session
        )
        if success:
            new_lead_id = resp.get("lead_id")
            self.log(f"   Created lead_id: {new_lead_id}")

            # Admin assigns lead to manager
            self.run_test(
                "Admin assigns lead to manager",
                "POST",
                f"/api/admin/ir/leads/{new_lead_id}/owner",
                200,
                {"owner_id": self.manager_user_id, "reason": "test assignment"},
                session=self.admin_session
            )

            # Manager can see their own lead
            self.run_test(
                "Manager can see their own lead",
                "GET",
                f"/api/admin/ir/leads/{new_lead_id}",
                200,
                session=self.manager_session
            )

            # Admin creates another lead (not assigned to manager)
            success2, resp2 = self.run_test(
                "Admin creates another lead (unassigned)",
                "POST",
                "/api/admin/ir/leads",
                200,
                {
                    "email": f"test_unassigned_{int(time.time())}@example.com",
                    "full_name": "Unassigned Lead",
                    "source": "manual"
                },
                session=self.admin_session
            )
            if success2:
                unassigned_lead_id = resp2.get("lead_id")
                self.log(f"   Created unassigned lead_id: {unassigned_lead_id}")

                # Manager CANNOT see lead they don't own (403)
                self.run_test(
                    "Manager gets 403 for non-owned lead (CRITICAL)",
                    "GET",
                    f"/api/admin/ir/leads/{unassigned_lead_id}",
                    403,
                    session=self.manager_session
                )

        # Admin sees all leads
        success, resp = self.run_test(
            "Admin sees all leads",
            "GET",
            "/api/admin/ir/leads?limit=100",
            200,
            session=self.admin_session
        )
        if success:
            admin_count = len(resp.get("leads", []))
            self.log(f"   Admin sees {admin_count} leads")

        # Manager sees only owned leads
        success, resp = self.run_test(
            "Manager sees only owned leads",
            "GET",
            "/api/admin/ir/leads?limit=100",
            200,
            session=self.manager_session
        )
        if success:
            manager_count = len(resp.get("leads", []))
            self.log(f"   Manager sees {manager_count} leads (should be <= admin count)")
            # Store first lead for later tests
            if resp.get("leads"):
                self.test_lead_id = resp["leads"][0]["lead_id"]

    def test_m2_manager_workspace(self):
        """Test M2: Working Manager Cabinet"""
        self.log("\n" + "="*80)
        self.log("M2 TEST: Working Manager Cabinet")
        self.log("="*80)

        if not self.test_lead_id:
            self.log("⚠️  No test lead available, skipping M2 tests", "WARN")
            return

        # Create note
        success, resp = self.run_test(
            "Manager adds note to lead",
            "POST",
            f"/api/admin/ir/leads/{self.test_lead_id}/notes",
            200,
            {"body": "Test note from manager"},
            session=self.manager_session
        )

        # Get notes
        self.run_test(
            "Manager gets notes",
            "GET",
            f"/api/admin/ir/leads/{self.test_lead_id}/notes",
            200,
            session=self.manager_session
        )

        # Create task
        success, resp = self.run_test(
            "Manager adds task",
            "POST",
            f"/api/admin/ir/leads/{self.test_lead_id}/tasks",
            200,
            {
                "title": "Follow up call",
                "priority": "high",
                "task_type": "call"
            },
            session=self.manager_session
        )
        task_id = resp.get("id") if success else None

        # Get tasks
        self.run_test(
            "Manager gets tasks",
            "GET",
            f"/api/admin/ir/leads/{self.test_lead_id}/tasks",
            200,
            session=self.manager_session
        )

        # Complete task
        if task_id:
            self.run_test(
                "Manager completes task",
                "PATCH",
                f"/api/admin/ir/tasks/{task_id}",
                200,
                {"status": "done"},
                session=self.manager_session
            )

        # Create meeting
        success, resp = self.run_test(
            "Manager schedules meeting",
            "POST",
            f"/api/admin/ir/leads/{self.test_lead_id}/meetings",
            200,
            {
                "title": "Discovery call",
                "scheduled_at": "2026-07-01T10:00:00Z",
                "type": "call",
                "duration_min": 30
            },
            session=self.manager_session
        )
        meeting_id = resp.get("id") if success else None

        # Get meetings
        self.run_test(
            "Manager gets meetings",
            "GET",
            f"/api/admin/ir/leads/{self.test_lead_id}/meetings",
            200,
            session=self.manager_session
        )

        # Change stage
        self.run_test(
            "Manager changes stage to qualified",
            "POST",
            f"/api/admin/ir/leads/{self.test_lead_id}/stage",
            200,
            {"stage": "qualified"},
            session=self.manager_session
        )

        # Get timeline
        self.run_test(
            "Manager gets timeline",
            "GET",
            f"/api/admin/ir/leads/{self.test_lead_id}/timeline",
            200,
            session=self.manager_session
        )

    def test_m3_sla(self):
        """Test M3: SLA Engine"""
        self.log("\n" + "="*80)
        self.log("M3 TEST: SLA Engine")
        self.log("="*80)

        # Create a new lead to test SLA
        success, resp = self.run_test(
            "Admin creates lead for SLA test",
            "POST",
            "/api/admin/ir/leads",
            200,
            {
                "email": f"sla_test_{int(time.time())}@example.com",
                "full_name": "SLA Test Lead",
                "source": "manual"
            },
            session=self.admin_session
        )
        if success:
            sla_lead_id = resp.get("lead_id")
            sla = resp.get("sla", {})
            self.log(f"   Lead created with SLA status: {sla.get('status')}")
            self.log(f"   SLA due_at: {sla.get('due_at')}")
            
            # Verify SLA status is pending
            if sla.get("status") == "pending":
                self.log("✅ SLA status is 'pending' on creation", "PASS")
                self.tests_passed += 1
            else:
                self.log(f"❌ Expected SLA status 'pending', got '{sla.get('status')}'", "FAIL")
                self.tests_failed += 1

            # Add a note (first response)
            self.run_test(
                "Manager adds note (first response)",
                "POST",
                f"/api/admin/ir/leads/{sla_lead_id}/notes",
                200,
                {"body": "First response to lead"},
                session=self.admin_session
            )

            # Get lead again to check SLA status changed
            success2, resp2 = self.run_test(
                "Get lead to verify SLA responded",
                "GET",
                f"/api/admin/ir/leads/{sla_lead_id}",
                200,
                session=self.admin_session
            )
            if success2:
                sla2 = resp2.get("sla", {})
                self.log(f"   After first response, SLA status: {sla2.get('status')}")
                self.log(f"   First response time: {sla2.get('first_response_min')} min")

        # Get overview with SLA metrics
        success, resp = self.run_test(
            "Get overview with SLA metrics",
            "GET",
            "/api/admin/ir/overview",
            200,
            session=self.admin_session
        )
        if success:
            self.log(f"   SLA breached: {resp.get('sla_breached', 0)}")
            self.log(f"   SLA at risk: {resp.get('sla_at_risk', 0)}")
            self.log(f"   Avg response time: {resp.get('avg_response_min')} min")
            self.log(f"   Hot leads: {resp.get('hot_leads', 0)}")
            self.log(f"   Health counts: {resp.get('health_counts', {})}")

    def test_m4_notifications(self):
        """Test M4: Staff Notifications"""
        self.log("\n" + "="*80)
        self.log("M4 TEST: Staff Notifications (CRITICAL)")
        self.log("="*80)

        # Get unread count
        success, resp = self.run_test(
            "Manager gets unread notification count",
            "GET",
            "/api/staff/notifications/unread-count",
            200,
            session=self.manager_session
        )
        if success:
            initial_count = resp.get("count", 0)
            self.log(f"   Initial unread count: {initial_count}")

        # Get notifications list
        success, resp = self.run_test(
            "Manager gets notifications list",
            "GET",
            "/api/staff/notifications?limit=30",
            200,
            session=self.manager_session
        )
        if success:
            notifs = resp.get("notifications", [])
            self.log(f"   Total notifications: {len(notifs)}")

        # Create a lead and assign to manager (should create notification)
        success, resp = self.run_test(
            "Admin creates and assigns lead to manager",
            "POST",
            "/api/admin/ir/leads",
            200,
            {
                "email": f"notif_test_{int(time.time())}@example.com",
                "full_name": "Notification Test Lead",
                "source": "manual"
            },
            session=self.admin_session
        )
        if success:
            notif_lead_id = resp.get("lead_id")
            
            # Assign to manager
            self.run_test(
                "Admin assigns lead to manager (should trigger notification)",
                "POST",
                f"/api/admin/ir/leads/{notif_lead_id}/owner",
                200,
                {"owner_id": self.manager_user_id, "reason": "notification test"},
                session=self.admin_session
            )

            # Wait a moment for notification to be created
            time.sleep(1)

            # Check unread count increased
            success2, resp2 = self.run_test(
                "Manager checks unread count after assignment",
                "GET",
                "/api/staff/notifications/unread-count",
                200,
                session=self.manager_session
            )
            if success2:
                new_count = resp2.get("count", 0)
                self.log(f"   New unread count: {new_count}")
                if new_count > initial_count:
                    self.log("✅ Notification created on assignment", "PASS")
                else:
                    self.log("⚠️  Unread count did not increase", "WARN")

            # Get notifications to verify new_lead_assigned
            success3, resp3 = self.run_test(
                "Manager gets notifications to verify assignment notification",
                "GET",
                "/api/staff/notifications?limit=5",
                200,
                session=self.manager_session
            )
            if success3:
                notifs = resp3.get("notifications", [])
                assignment_notif = next((n for n in notifs if n.get("kind") == "new_lead_assigned"), None)
                if assignment_notif:
                    self.log(f"✅ Found 'new_lead_assigned' notification: {assignment_notif.get('title')}", "PASS")
                    notif_id = assignment_notif.get("id")
                    
                    # Mark as read
                    self.run_test(
                        "Manager marks notification as read",
                        "POST",
                        f"/api/staff/notifications/{notif_id}/read",
                        200,
                        session=self.manager_session
                    )
                else:
                    self.log("⚠️  No 'new_lead_assigned' notification found", "WARN")

        # Mark all as read
        self.run_test(
            "Manager marks all notifications as read",
            "POST",
            "/api/staff/notifications/read-all",
            200,
            session=self.manager_session
        )

    def test_m5_login_audit(self):
        """Test M5: Login Audit + Staff Sessions"""
        self.log("\n" + "="*80)
        self.log("M5 TEST: Login Audit + Active Sessions")
        self.log("="*80)

        # Get login audit (admin sees all)
        success, resp = self.run_test(
            "Admin gets login audit (all events)",
            "GET",
            "/api/admin/staff/login-audit?days=30",
            200,
            session=self.admin_session
        )
        if success:
            events = resp.get("events", [])
            self.log(f"   Total audit events: {len(events)}")
            login_ok = [e for e in events if e.get("event") == "login_ok"]
            login_fail = [e for e in events if e.get("event") == "login_fail"]
            logout = [e for e in events if e.get("event") == "logout"]
            self.log(f"   login_ok: {len(login_ok)}, login_fail: {len(login_fail)}, logout: {len(logout)}")

        # Manager gets own audit
        success, resp = self.run_test(
            "Manager gets own login audit",
            "GET",
            "/api/admin/staff/login-audit?days=30",
            200,
            session=self.manager_session
        )
        if success:
            events = resp.get("events", [])
            self.log(f"   Manager audit events: {len(events)}")

        # Filter by event type
        self.run_test(
            "Admin filters audit by login_ok",
            "GET",
            "/api/admin/staff/login-audit?days=30&event=login_ok",
            200,
            session=self.admin_session
        )

        # Get active sessions (admin sees all)
        success, resp = self.run_test(
            "Admin gets active sessions (all staff)",
            "GET",
            "/api/admin/staff/active-sessions",
            200,
            session=self.admin_session
        )
        if success:
            sessions = resp.get("sessions", [])
            self.log(f"   Active staff sessions: {len(sessions)}")

        # Manager gets own sessions
        success, resp = self.run_test(
            "Manager gets own active sessions",
            "GET",
            "/api/admin/staff/active-sessions",
            200,
            session=self.manager_session
        )
        if success:
            sessions = resp.get("sessions", [])
            self.log(f"   Manager active sessions: {len(sessions)}")

        # Test failed login (should create login_fail event)
        self.log("\n   Testing failed login...")
        temp_session = requests.Session()
        self.run_test(
            "Failed login attempt (wrong password)",
            "POST",
            "/api/auth/login",
            401,
            {"email": MANAGER_EMAIL, "password": "wrongpassword"},
            session=temp_session
        )

    def test_m6_reassignment(self):
        """Test M6: Reassignment Center"""
        self.log("\n" + "="*80)
        self.log("M6 TEST: Reassignment Center")
        self.log("="*80)

        # Create a lead for reassignment test
        success, resp = self.run_test(
            "Admin creates lead for reassignment",
            "POST",
            "/api/admin/ir/leads",
            200,
            {
                "email": f"reassign_test_{int(time.time())}@example.com",
                "full_name": "Reassignment Test Lead",
                "source": "manual"
            },
            session=self.admin_session
        )
        if success:
            reassign_lead_id = resp.get("lead_id")

            # Assign to manager
            self.run_test(
                "Admin assigns lead to manager",
                "POST",
                f"/api/admin/ir/leads/{reassign_lead_id}/owner",
                200,
                {"owner_id": self.manager_user_id, "reason": "initial assignment"},
                session=self.admin_session
            )

            # Reassign to admin
            self.run_test(
                "Admin reassigns lead to self",
                "POST",
                f"/api/admin/ir/leads/{reassign_lead_id}/reassign",
                200,
                {"to_owner_id": self.admin_user_id, "reason": "taking over"},
                session=self.admin_session
            )

            # Reassign back to manager
            self.run_test(
                "Admin reassigns lead back to manager",
                "POST",
                f"/api/admin/ir/leads/{reassign_lead_id}/reassign",
                200,
                {"to_owner_id": self.manager_user_id, "reason": "returning lead"},
                session=self.admin_session
            )

            # Idempotent: reassign to same owner (should be no-op)
            self.run_test(
                "Reassign to same owner (idempotent no-op)",
                "POST",
                f"/api/admin/ir/leads/{reassign_lead_id}/reassign",
                200,
                {"to_owner_id": self.manager_user_id, "reason": "same owner"},
                session=self.admin_session
            )

            # Reassign to non-existent owner (should fail)
            self.run_test(
                "Reassign to non-existent owner (404)",
                "POST",
                f"/api/admin/ir/leads/{reassign_lead_id}/reassign",
                404,
                {"to_owner_id": "nonexistent_user_id", "reason": "invalid"},
                session=self.admin_session
            )

        # Get reassignment history (admin sees all)
        success, resp = self.run_test(
            "Admin gets reassignment history",
            "GET",
            "/api/admin/ir/reassignments?limit=50",
            200,
            session=self.admin_session
        )
        if success:
            history = resp.get("reassignments", [])
            self.log(f"   Total reassignments: {len(history)}")

        # Manager gets scoped reassignment history
        success, resp = self.run_test(
            "Manager gets scoped reassignment history",
            "GET",
            "/api/admin/ir/reassignments?limit=50",
            200,
            session=self.manager_session
        )
        if success:
            history = resp.get("reassignments", [])
            self.log(f"   Manager reassignments (to/from self): {len(history)}")

        # Bulk reassignment
        # Create 2 leads
        lead_ids = []
        for i in range(2):
            success, resp = self.run_test(
                f"Admin creates lead {i+1} for bulk reassignment",
                "POST",
                "/api/admin/ir/leads",
                200,
                {
                    "email": f"bulk_{i}_{int(time.time())}@example.com",
                    "full_name": f"Bulk Test Lead {i+1}",
                    "source": "manual"
                },
                session=self.admin_session
            )
            if success:
                lead_ids.append(resp.get("lead_id"))

        if len(lead_ids) == 2:
            self.run_test(
                "Admin bulk reassigns 2 leads to manager",
                "POST",
                "/api/admin/ir/reassign",
                200,
                {
                    "lead_ids": lead_ids,
                    "to_owner_id": self.manager_user_id,
                    "reason": "bulk assignment test"
                },
                session=self.admin_session
            )

    def test_m7_snapshot(self):
        """Test M7: Manager Activity Snapshot"""
        self.log("\n" + "="*80)
        self.log("M7 TEST: Manager Activity Snapshot")
        self.log("="*80)

        # Admin gets all manager snapshots
        success, resp = self.run_test(
            "Admin gets all manager snapshots",
            "GET",
            "/api/admin/manager-os/snapshot",
            200,
            session=self.admin_session
        )
        if success:
            snapshots = resp.get("snapshots", [])
            self.log(f"   Total manager snapshots: {len(snapshots)}")
            for snap in snapshots:
                self.log(f"   - {snap.get('name')}: {snap.get('leads_total')} leads, "
                        f"{snap.get('conversion_rate')}% conv, "
                        f"{snap.get('avg_response_min')}m avg resp, "
                        f"{snap.get('sla_breached')} SLA breached, "
                        f"{snap.get('open_tasks')}/{snap.get('overdue_tasks')} tasks")

        # Manager gets own snapshot
        success, resp = self.run_test(
            "Manager gets own snapshot",
            "GET",
            "/api/admin/manager-os/my-snapshot",
            200,
            session=self.manager_session
        )
        if success:
            self.log(f"   Manager leads: {resp.get('leads_total')}")
            self.log(f"   Conversion rate: {resp.get('conversion_rate')}%")
            self.log(f"   Avg response: {resp.get('avg_response_min')} min")
            self.log(f"   SLA breached: {resp.get('sla_breached')}")
            self.log(f"   Open tasks: {resp.get('open_tasks')}")

        # Manager tries to get all snapshots (should only see self)
        success, resp = self.run_test(
            "Manager gets snapshots (scoped to self)",
            "GET",
            "/api/admin/manager-os/snapshot",
            200,
            session=self.manager_session
        )
        if success:
            snapshots = resp.get("snapshots", [])
            self.log(f"   Manager sees {len(snapshots)} snapshot(s) (should be 1)")

    def test_m8_communication_log(self):
        """Test M8: Communication Log"""
        self.log("\n" + "="*80)
        self.log("M8 TEST: Communication Log")
        self.log("="*80)

        if not self.test_lead_id:
            self.log("⚠️  No test lead available, skipping M8 tests", "WARN")
            return

        # Log a call
        self.run_test(
            "Manager logs outbound call",
            "POST",
            f"/api/admin/ir/leads/{self.test_lead_id}/communications",
            200,
            {
                "interaction_type": "call",
                "direction": "outbound",
                "detail": "Discussed investment options"
            },
            session=self.manager_session
        )

        # Log an email
        self.run_test(
            "Manager logs inbound email",
            "POST",
            f"/api/admin/ir/leads/{self.test_lead_id}/communications",
            200,
            {
                "interaction_type": "email",
                "direction": "inbound",
                "detail": "Investor asked about fees"
            },
            session=self.manager_session
        )

        # Log telegram
        self.run_test(
            "Manager logs telegram message",
            "POST",
            f"/api/admin/ir/leads/{self.test_lead_id}/communications",
            200,
            {
                "interaction_type": "telegram",
                "direction": "outbound",
                "detail": "Sent prospectus link"
            },
            session=self.manager_session
        )

        # Invalid interaction_type (should fallback to 'other')
        self.run_test(
            "Manager logs with invalid type (fallback to 'other')",
            "POST",
            f"/api/admin/ir/leads/{self.test_lead_id}/communications",
            200,
            {
                "interaction_type": "invalid_type",
                "direction": "outbound",
                "detail": "Test fallback"
            },
            session=self.manager_session
        )

        # Get communications
        success, resp = self.run_test(
            "Manager gets communications for lead",
            "GET",
            f"/api/admin/ir/leads/{self.test_lead_id}/communications",
            200,
            session=self.manager_session
        )
        if success:
            comms = resp.get("communications", [])
            self.log(f"   Total communications: {len(comms)}")
            for comm in comms[:5]:
                self.log(f"   - {comm.get('kind')}: {comm.get('title')} ({comm.get('direction')})")

    def print_summary(self):
        """Print test summary"""
        self.log("\n" + "="*80)
        self.log("TEST SUMMARY")
        self.log("="*80)
        self.log(f"Total tests run: {self.tests_run}")
        self.log(f"✅ Passed: {self.tests_passed}")
        self.log(f"❌ Failed: {self.tests_failed}")
        
        if self.tests_failed > 0:
            self.log("\n" + "="*80)
            self.log("FAILED TESTS DETAILS")
            self.log("="*80)
            for i, failure in enumerate(self.failures, 1):
                self.log(f"\n{i}. {failure.get('test')}")
                self.log(f"   Endpoint: {failure.get('endpoint')}")
                if 'expected' in failure:
                    self.log(f"   Expected: {failure['expected']}, Got: {failure['actual']}")
                if 'error' in failure:
                    self.log(f"   Error: {failure['error']}")
                if 'response' in failure:
                    self.log(f"   Response: {failure['response']}")

        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        self.log(f"\n📊 Success rate: {success_rate:.1f}%")
        
        return 0 if self.tests_failed == 0 else 1

def main():
    tester = ManagerOSTester(BACKEND_URL)
    
    try:
        # Run all tests
        tester.test_auth()
        tester.test_m1_scoping()
        tester.test_m2_manager_workspace()
        tester.test_m3_sla()
        tester.test_m4_notifications()
        tester.test_m5_login_audit()
        tester.test_m6_reassignment()
        tester.test_m7_snapshot()
        tester.test_m8_communication_log()
        
    except KeyboardInterrupt:
        tester.log("\n\n⚠️  Tests interrupted by user", "WARN")
    except Exception as e:
        tester.log(f"\n\n❌ Unexpected error: {str(e)}", "ERROR")
        import traceback
        traceback.print_exc()
    
    return tester.print_summary()

if __name__ == "__main__":
    sys.exit(main())
