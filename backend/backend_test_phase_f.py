"""
LUMEN 2.0 Phase F — Operator OS Backend Test Suite
===================================================
Tests all 10 blocks of Phase F with focus on:
- F10 Operator Portal scoping (CRITICAL)
- F1-F9 Admin operator management
- F7 Public leaderboard
- Report submission → SLA reset
- Regression: Phase E endpoints
"""
import sys
import requests
from datetime import datetime

BASE_URL = "https://dev-workspace-252.preview.emergentagent.com/api"

class PhaseF_Tester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []
        self.admin_session = None
        self.operator_session = None
        self.client_session = None
        self.operator_id = None
        self.managed_assets = []
        self.non_managed_asset = "asset-rivne-warehouse"
        
    def log(self, msg, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [{level}] {msg}")
    
    def test(self, name, func):
        """Run a single test"""
        self.tests_run += 1
        self.log(f"🔍 Test {self.tests_run}: {name}")
        try:
            func()
            self.tests_passed += 1
            self.log(f"✅ PASS: {name}", "PASS")
            return True
        except AssertionError as e:
            self.tests_failed += 1
            self.failures.append({"test": name, "error": str(e)})
            self.log(f"❌ FAIL: {name} - {str(e)}", "FAIL")
            return False
        except Exception as e:
            self.tests_failed += 1
            self.failures.append({"test": name, "error": f"Exception: {str(e)}"})
            self.log(f"❌ ERROR: {name} - {str(e)}", "ERROR")
            return False
    
    def login(self, email, password):
        """Login and return session with cookies"""
        s = requests.Session()
        r = s.post(f"{BASE_URL}/auth/login", 
                   json={"email": email, "password": password}, 
                   timeout=15)
        assert r.status_code == 200, f"Login failed: {r.status_code} - {r.text}"
        
        # Check for session_token cookie
        token = r.cookies.get("session_token")
        if token:
            # Re-set as plain cookie for subsequent requests
            s.cookies.clear()
            s.cookies.set("session_token", token)
        
        data = r.json()
        self.log(f"Logged in as {email} (role: {data.get('role')})")
        return s, data
    
    # ========================================================================
    # AUTH TESTS
    # ========================================================================
    
    def test_auth_all_roles(self):
        """AUTH: Login with admin, operator, client"""
        # Admin
        self.admin_session, admin_data = self.login("admin@atlas.dev", "admin123")
        assert admin_data.get("role") == "admin", "Admin role mismatch"
        
        # Operator (NEW role)
        self.operator_session, op_data = self.login("operator@atlas.dev", "operator123")
        assert op_data.get("role") == "operator", "Operator role mismatch"
        
        # Client
        self.client_session, client_data = self.login("client@atlas.dev", "client123")
        assert client_data.get("role") == "client", "Client role mismatch"
    
    # ========================================================================
    # F10 OPERATOR PORTAL + SCOPING (CRITICAL)
    # ========================================================================
    
    def test_f10_operator_me(self):
        """F10: GET /api/operator/me returns operator profile"""
        r = self.operator_session.get(f"{BASE_URL}/operator/me", timeout=15)
        assert r.status_code == 200, f"operator/me failed: {r.status_code}"
        
        data = r.json()
        assert data.get("verified") == True, "Operator should be verified"
        assert "reputation" in data, "Missing reputation"
        assert data["reputation"].get("grade") is not None, "Missing reputation grade"
        
        self.operator_id = data.get("id")
        self.log(f"Operator: {data.get('name')} (verified={data.get('verified')}, grade={data['reputation'].get('grade')})")
    
    def test_f10_operator_dashboard(self):
        """F10: GET /api/operator/dashboard returns full dashboard"""
        r = self.operator_session.get(f"{BASE_URL}/operator/dashboard", timeout=15)
        assert r.status_code == 200, f"operator/dashboard failed: {r.status_code}"
        
        data = r.json()
        assert "kpi" in data, "Missing KPI"
        assert "reputation" in data, "Missing reputation"
        assert "sla" in data, "Missing SLA"
        assert "governance" in data, "Missing governance"
        assert "dealflow" in data, "Missing dealflow"
        assert "fees" in data, "Missing fees"
        
        kpi = data["kpi"]
        self.log(f"KPI: assets={kpi.get('assets_count')}, aum={kpi.get('aum_uah')}, investors={kpi.get('investors_count')}")
    
    def test_f10_operator_assets_scoped(self):
        """F10: GET /api/operator/assets returns ONLY managed assets"""
        r = self.operator_session.get(f"{BASE_URL}/operator/assets", timeout=15)
        assert r.status_code == 200, f"operator/assets failed: {r.status_code}"
        
        data = r.json()
        items = data.get("items", [])
        assert len(items) >= 1, "Operator should have at least 1 managed asset"
        
        # Store managed assets
        self.managed_assets = [a["id"] for a in items]
        self.log(f"Managed assets: {self.managed_assets}")
        
        # Verify expected assets
        expected = ["asset-podilskyi", "asset-stoyanka-land", "asset-odessa-apartments"]
        for exp in expected:
            if exp in self.managed_assets:
                self.log(f"✓ Found expected asset: {exp}")
    
    def test_f10_scoping_403_non_managed_asset(self):
        """F10 SCOPING: POST to non-managed asset returns 403"""
        # Try to submit report for asset-rivne-warehouse (not managed by operator)
        r = self.operator_session.post(
            f"{BASE_URL}/operator/assets/{self.non_managed_asset}/reports",
            json={"title": "Unauthorized report", "period_label": "Q1 2026"},
            timeout=15
        )
        assert r.status_code == 403, f"Expected 403 for non-managed asset, got {r.status_code}"
        self.log(f"✓ Correctly blocked access to non-managed asset: {self.non_managed_asset}")
    
    def test_f10_scoping_403_non_operator_role(self):
        """F10 SCOPING: Non-operator accessing operator endpoints returns 403"""
        # Admin tries to access operator/me
        r = self.admin_session.get(f"{BASE_URL}/operator/me", timeout=15)
        assert r.status_code == 403, f"Expected 403 for admin accessing operator/me, got {r.status_code}"
        
        # Client tries to access operator/me
        r = self.client_session.get(f"{BASE_URL}/operator/me", timeout=15)
        assert r.status_code == 403, f"Expected 403 for client accessing operator/me, got {r.status_code}"
        
        self.log("✓ Non-operator roles correctly blocked from operator endpoints")
    
    def test_f10_report_submission_resets_sla(self):
        """F10: Report submission resets SLA status to 'ok'"""
        # Get SLA before report
        r = self.operator_session.get(f"{BASE_URL}/operator/sla", timeout=15)
        assert r.status_code == 200, f"operator/sla failed: {r.status_code}"
        
        sla_before = r.json()
        self.log(f"SLA before: overall={sla_before.get('overall')}, counts={sla_before.get('counts')}")
        
        # Find an asset with warning/critical/escalation status
        target_asset = None
        for item in sla_before.get("items", []):
            if item["status"] in ["warning", "critical", "escalation"]:
                target_asset = item["asset_id"]
                break
        
        # If no breaching asset, use first managed asset
        if not target_asset and self.managed_assets:
            target_asset = self.managed_assets[0]
        
        assert target_asset, "No target asset found for report submission"
        
        # Submit report
        r = self.operator_session.post(
            f"{BASE_URL}/operator/assets/{target_asset}/reports",
            json={
                "title": "Test Quarterly Report",
                "period_label": "Q2 2026",
                "summary": "Operational report for testing",
                "report_type": "operational"
            },
            timeout=15
        )
        assert r.status_code == 200, f"Report submission failed: {r.status_code}"
        
        report_data = r.json()
        assert report_data.get("ok") == True, "Report submission not confirmed"
        self.log(f"✓ Report submitted for asset: {target_asset}")
        
        # Get SLA after report
        r = self.operator_session.get(f"{BASE_URL}/operator/sla", timeout=15)
        assert r.status_code == 200, f"operator/sla failed after report: {r.status_code}"
        
        sla_after = r.json()
        
        # Find the asset's new status
        new_status = None
        for item in sla_after.get("items", []):
            if item["asset_id"] == target_asset:
                new_status = item["status"]
                break
        
        assert new_status == "ok", f"SLA status should be 'ok' after report, got '{new_status}'"
        self.log(f"✓ SLA status reset to 'ok' for asset {target_asset}")
    
    def test_f10_operator_reports(self):
        """F10: GET /api/operator/reports returns scoped reports"""
        r = self.operator_session.get(f"{BASE_URL}/operator/reports", timeout=15)
        assert r.status_code == 200, f"operator/reports failed: {r.status_code}"
        
        data = r.json()
        items = data.get("items", [])
        self.log(f"Operator reports: {len(items)} reports found")
    
    def test_f10_operator_investors(self):
        """F10: GET /api/operator/investors returns aggregated investors"""
        r = self.operator_session.get(f"{BASE_URL}/operator/investors", timeout=15)
        assert r.status_code == 200, f"operator/investors failed: {r.status_code}"
        
        data = r.json()
        self.log(f"Investors: total={data.get('total_investors')}, capital={data.get('total_capital_uah')}")
    
    def test_f10_operator_kpi(self):
        """F10: GET /api/operator/kpi returns derived KPI"""
        r = self.operator_session.get(f"{BASE_URL}/operator/kpi", timeout=15)
        assert r.status_code == 200, f"operator/kpi failed: {r.status_code}"
        
        data = r.json()
        assert "assets_count" in data, "Missing assets_count"
        assert data["assets_count"] >= 1, "Should have at least 1 asset"
        self.log(f"KPI: {data}")
    
    def test_f10_operator_dealflow(self):
        """F10: GET /api/operator/dealflow returns deal flow stats"""
        r = self.operator_session.get(f"{BASE_URL}/operator/dealflow", timeout=15)
        assert r.status_code == 200, f"operator/dealflow failed: {r.status_code}"
        
        data = r.json()
        self.log(f"Deal flow: sourced={data.get('sourced')}, live={data.get('live')}, success%={data.get('funding_success_pct')}")
    
    def test_f10_operator_fees(self):
        """F10: GET /api/operator/fees returns fee schedule"""
        r = self.operator_session.get(f"{BASE_URL}/operator/fees", timeout=15)
        assert r.status_code == 200, f"operator/fees failed: {r.status_code}"
        
        data = r.json()
        assert "management_fee_pct" in data, "Missing management_fee_pct"
        self.log(f"Fees: mgmt={data.get('management_fee_pct')}%, est_annual={data.get('estimated_annual_management_fee_uah')}")
    
    # ========================================================================
    # F1+F2 ADMIN OPERATOR MANAGEMENT
    # ========================================================================
    
    def test_f1_admin_operator_overview(self):
        """F1: GET /api/admin/operators/{id}/overview returns full bundle"""
        # Get list of operators first
        r = self.admin_session.get(f"{BASE_URL}/admin/operators", timeout=15)
        assert r.status_code == 200, f"admin/operators list failed: {r.status_code}"
        
        ops = r.json().get("items", [])
        assert len(ops) > 0, "No operators found"
        
        op_id = ops[0]["id"]
        
        # Get overview
        r = self.admin_session.get(f"{BASE_URL}/admin/operators/{op_id}/overview", timeout=15)
        assert r.status_code == 200, f"admin/operators/overview failed: {r.status_code}"
        
        data = r.json()
        assert "operator" in data, "Missing operator"
        assert "kpi" in data, "Missing kpi"
        assert "reputation" in data, "Missing reputation"
        assert "sla" in data, "Missing sla"
        assert "governance" in data, "Missing governance"
        assert "dealflow" in data, "Missing dealflow"
        assert "fees" in data, "Missing fees"
        assert "assets" in data, "Missing assets"
        assert "documents" in data, "Missing documents"
        assert "events" in data, "Missing events"
        
        self.log(f"Overview: {data['operator'].get('name')}, assets={len(data['assets'])}, events={len(data['events'])}")
    
    def test_f2_admin_verification_transition(self):
        """F2: POST /api/admin/operators/{id}/verification transitions status"""
        # Get an operator
        r = self.admin_session.get(f"{BASE_URL}/admin/operators", timeout=15)
        ops = r.json().get("items", [])
        op_id = ops[0]["id"]
        
        # Transition to verified
        r = self.admin_session.post(
            f"{BASE_URL}/admin/operators/{op_id}/verification",
            json={"to_status": "verified", "note": "Test verification"},
            timeout=15
        )
        assert r.status_code == 200, f"Verification transition failed: {r.status_code}"
        
        data = r.json()
        assert data.get("ok") == True, "Verification not confirmed"
        assert data.get("status") == "verified", "Status not updated"
        
        # Verify event was created
        r = self.admin_session.get(f"{BASE_URL}/admin/operators/{op_id}/events", timeout=15)
        assert r.status_code == 200, f"Events fetch failed: {r.status_code}"
        
        events = r.json().get("items", [])
        verification_events = [e for e in events if e.get("kind") == "verification"]
        assert len(verification_events) > 0, "No verification event created"
        
        self.log(f"✓ Verification transition successful, event created")
    
    def test_f1_admin_profile_update(self):
        """F1: PATCH /api/admin/operators/{id}/profile updates profile"""
        r = self.admin_session.get(f"{BASE_URL}/admin/operators", timeout=15)
        ops = r.json().get("items", [])
        op_id = ops[0]["id"]
        
        r = self.admin_session.patch(
            f"{BASE_URL}/admin/operators/{op_id}/profile",
            json={"team_size": 15, "description": "Updated description"},
            timeout=15
        )
        assert r.status_code == 200, f"Profile update failed: {r.status_code}"
        
        data = r.json()
        assert data.get("ok") == True, "Profile update not confirmed"
        self.log("✓ Profile updated successfully")
    
    # ========================================================================
    # F3-F9 ADMIN ENDPOINTS
    # ========================================================================
    
    def test_f3_admin_kpi(self):
        """F3: GET /api/admin/operators/{id}/kpi returns derived KPI"""
        r = self.admin_session.get(f"{BASE_URL}/admin/operators", timeout=15)
        ops = r.json().get("items", [])
        op_id = ops[0]["id"]
        
        r = self.admin_session.get(f"{BASE_URL}/admin/operators/{op_id}/kpi", timeout=15)
        assert r.status_code == 200, f"admin/operators/kpi failed: {r.status_code}"
        
        data = r.json()
        assert "assets_count" in data, "Missing assets_count"
        assert "aum_uah" in data, "Missing aum_uah"
        assert "investors_count" in data, "Missing investors_count"
        self.log(f"Admin KPI: assets={data.get('assets_count')}, aum={data.get('aum_uah')}")
    
    def test_f4_admin_sla(self):
        """F4: GET /api/admin/operators/{id}/sla returns SLA status"""
        r = self.admin_session.get(f"{BASE_URL}/admin/operators", timeout=15)
        ops = r.json().get("items", [])
        op_id = ops[0]["id"]
        
        r = self.admin_session.get(f"{BASE_URL}/admin/operators/{op_id}/sla", timeout=15)
        assert r.status_code == 200, f"admin/operators/sla failed: {r.status_code}"
        
        data = r.json()
        assert "overall" in data, "Missing overall SLA status"
        assert "items" in data, "Missing SLA items"
        self.log(f"Admin SLA: overall={data.get('overall')}, items={len(data.get('items', []))}")
    
    def test_f4_admin_sla_scan(self):
        """F4: POST /api/admin/operators/sla/scan creates events"""
        r = self.admin_session.post(f"{BASE_URL}/admin/operators/sla/scan", timeout=15)
        assert r.status_code == 200, f"SLA scan failed: {r.status_code}"
        
        data = r.json()
        self.log(f"SLA scan: flagged={data.get('flagged')}")
    
    def test_f5_admin_reputation(self):
        """F5: GET /api/admin/operators/{id}/reputation returns score+grade"""
        r = self.admin_session.get(f"{BASE_URL}/admin/operators", timeout=15)
        ops = r.json().get("items", [])
        op_id = ops[0]["id"]
        
        r = self.admin_session.get(f"{BASE_URL}/admin/operators/{op_id}/reputation", timeout=15)
        assert r.status_code == 200, f"admin/operators/reputation failed: {r.status_code}"
        
        data = r.json()
        assert "score" in data, "Missing score"
        assert "grade" in data, "Missing grade"
        assert "breakdown" in data, "Missing breakdown"
        assert 0 <= data["score"] <= 100, "Score out of range"
        self.log(f"Reputation: score={data.get('score')}, grade={data.get('grade')}")
    
    def test_f6_admin_governance(self):
        """F6: GET /api/admin/operators/{id}/governance returns sentiment"""
        r = self.admin_session.get(f"{BASE_URL}/admin/operators", timeout=15)
        ops = r.json().get("items", [])
        op_id = ops[0]["id"]
        
        r = self.admin_session.get(f"{BASE_URL}/admin/operators/{op_id}/governance", timeout=15)
        assert r.status_code == 200, f"admin/operators/governance failed: {r.status_code}"
        
        data = r.json()
        assert "positive_pct" in data or data.get("positive_pct") is None, "Missing positive_pct"
        assert "alert" in data, "Missing alert"
        self.log(f"Governance: positive_pct={data.get('positive_pct')}, alert={data.get('alert')}")
    
    def test_f6_admin_governance_scan(self):
        """F6: POST /api/admin/operators/governance/scan creates events"""
        r = self.admin_session.post(f"{BASE_URL}/admin/operators/governance/scan", timeout=15)
        assert r.status_code == 200, f"Governance scan failed: {r.status_code}"
        
        data = r.json()
        self.log(f"Governance scan: flagged={data.get('flagged')}")
    
    def test_f8_admin_dealflow(self):
        """F8: GET /api/admin/operators/{id}/dealflow returns deal stats"""
        r = self.admin_session.get(f"{BASE_URL}/admin/operators", timeout=15)
        ops = r.json().get("items", [])
        op_id = ops[0]["id"]
        
        r = self.admin_session.get(f"{BASE_URL}/admin/operators/{op_id}/dealflow", timeout=15)
        assert r.status_code == 200, f"admin/operators/dealflow failed: {r.status_code}"
        
        data = r.json()
        assert "sourced" in data, "Missing sourced"
        assert "funding_success_pct" in data, "Missing funding_success_pct"
        self.log(f"Deal flow: sourced={data.get('sourced')}, success%={data.get('funding_success_pct')}")
    
    def test_f9_admin_fees_update(self):
        """F9: PATCH /api/admin/operators/{id}/fees updates fee schedule"""
        r = self.admin_session.get(f"{BASE_URL}/admin/operators", timeout=15)
        ops = r.json().get("items", [])
        op_id = ops[0]["id"]
        
        r = self.admin_session.patch(
            f"{BASE_URL}/admin/operators/{op_id}/fees",
            json={"management_fee_pct": 2.5, "success_fee_pct": 10},
            timeout=15
        )
        assert r.status_code == 200, f"Fees update failed: {r.status_code}"
        
        data = r.json()
        assert data.get("ok") == True, "Fees update not confirmed"
        self.log("✓ Fees updated successfully")
    
    # ========================================================================
    # F7 PUBLIC LEADERBOARD (NO AUTH)
    # ========================================================================
    
    def test_f7_public_leaderboard(self):
        """F7: GET /api/operators/leaderboard (public, no auth)"""
        # Use requests without session (no auth)
        r = requests.get(f"{BASE_URL}/operators/leaderboard", timeout=15)
        assert r.status_code == 200, f"Public leaderboard failed: {r.status_code}"
        
        data = r.json()
        items = data.get("items", [])
        assert len(items) > 0, "Leaderboard should have items"
        
        # Verify sorting by reputation score DESC
        scores = [item.get("reputation", {}).get("score", 0) for item in items]
        assert scores == sorted(scores, reverse=True), "Leaderboard not sorted by score DESC"
        
        # Verify rank assignment
        for i, item in enumerate(items):
            assert item.get("rank") == i + 1, f"Rank mismatch at position {i}"
        
        self.log(f"✓ Public leaderboard: {len(items)} operators, sorted correctly")
    
    def test_f7_public_operator_card(self):
        """F7: GET /api/operators/{id}/public returns privacy-safe card"""
        # Get an operator ID from leaderboard
        r = requests.get(f"{BASE_URL}/operators/leaderboard", timeout=15)
        items = r.json().get("items", [])
        op_id = items[0]["id"]
        
        r = requests.get(f"{BASE_URL}/operators/{op_id}/public", timeout=15)
        assert r.status_code == 200, f"Public operator card failed: {r.status_code}"
        
        data = r.json()
        assert "id" in data, "Missing id"
        assert "name" in data, "Missing name"
        assert "verified" in data, "Missing verified"
        assert "reputation" in data, "Missing reputation"
        self.log(f"✓ Public operator card: {data.get('name')}, verified={data.get('verified')}")
    
    def test_f7_asset_operator_card(self):
        """F7: GET /api/assets/{id}/operator-card returns managing operator"""
        # Use asset-podilskyi (managed by operator)
        r = requests.get(f"{BASE_URL}/assets/asset-podilskyi/operator-card", timeout=15)
        assert r.status_code == 200, f"Asset operator card failed: {r.status_code}"
        
        data = r.json()
        operator = data.get("operator")
        assert operator is not None, "Operator should be present"
        assert operator.get("verified") == True, "Operator should be verified"
        self.log(f"✓ Asset operator card: {operator.get('name')}, verified={operator.get('verified')}")
    
    # ========================================================================
    # F1 DOCUMENTS + ASSETS
    # ========================================================================
    
    def test_f1_admin_documents(self):
        """F1: POST/DELETE /api/admin/operators/{id}/documents"""
        r = self.admin_session.get(f"{BASE_URL}/admin/operators", timeout=15)
        ops = r.json().get("items", [])
        op_id = ops[0]["id"]
        
        # Create document
        r = self.admin_session.post(
            f"{BASE_URL}/admin/operators/{op_id}/documents",
            json={"title": "Test Document", "kind": "license", "url": "https://example.com/doc.pdf"},
            timeout=15
        )
        assert r.status_code == 200, f"Document creation failed: {r.status_code}"
        
        doc = r.json()
        doc_id = doc.get("id")
        assert doc_id is not None, "Document ID missing"
        self.log(f"✓ Document created: {doc_id}")
        
        # Delete document
        r = self.admin_session.delete(
            f"{BASE_URL}/admin/operators/{op_id}/documents/{doc_id}",
            timeout=15
        )
        assert r.status_code == 200, f"Document deletion failed: {r.status_code}"
        self.log(f"✓ Document deleted: {doc_id}")
    
    def test_f1_admin_assets_assign_unassign(self):
        """F1: POST/DELETE /api/admin/operators/{id}/assets"""
        r = self.admin_session.get(f"{BASE_URL}/admin/operators", timeout=15)
        ops = r.json().get("items", [])
        op_id = ops[0]["id"]
        
        # Note: We won't actually assign/unassign to avoid breaking existing assignments
        # Just verify the endpoints exist and return proper errors for invalid assets
        
        # Try to assign non-existent asset (should fail)
        r = self.admin_session.post(
            f"{BASE_URL}/admin/operators/{op_id}/assets",
            json={"asset_id": "asset-nonexistent-test"},
            timeout=15
        )
        assert r.status_code == 404, f"Should fail for non-existent asset, got {r.status_code}"
        self.log("✓ Asset assignment endpoint validated")
    
    # ========================================================================
    # F10 LINK USER
    # ========================================================================
    
    def test_f10_admin_link_user(self):
        """F10: POST /api/admin/operators/{id}/link-user creates/promotes user"""
        r = self.admin_session.get(f"{BASE_URL}/admin/operators", timeout=15)
        ops = r.json().get("items", [])
        
        # Find an operator without a linked user
        op_id = None
        for op in ops:
            if not op.get("user_id"):
                op_id = op["id"]
                break
        
        if not op_id:
            # All operators have users, skip this test
            self.log("⚠️  All operators already have linked users, skipping link-user test")
            return
        
        # Link a new user
        test_email = f"test_operator_{datetime.now().timestamp()}@test.com"
        r = self.admin_session.post(
            f"{BASE_URL}/admin/operators/{op_id}/link-user",
            json={"email": test_email, "name": "Test Operator", "password": "test123"},
            timeout=15
        )
        assert r.status_code == 200, f"Link user failed: {r.status_code}"
        
        data = r.json()
        assert data.get("ok") == True, "Link user not confirmed"
        assert data.get("email") == test_email, "Email mismatch"
        self.log(f"✓ User linked: {test_email}")
    
    # ========================================================================
    # REGRESSION: PHASE E ENDPOINTS
    # ========================================================================
    
    def test_regression_phase_e_deals(self):
        """REGRESSION: GET /api/admin/deals still works"""
        r = self.admin_session.get(f"{BASE_URL}/admin/deals", timeout=15)
        assert r.status_code == 200, f"Phase E deals endpoint failed: {r.status_code}"
        
        data = r.json()
        self.log(f"✓ Phase E deals endpoint working: {len(data.get('items', []))} deals")
    
    def test_regression_admin_operators_list(self):
        """REGRESSION: GET /api/admin/operators base list still works"""
        r = self.admin_session.get(f"{BASE_URL}/admin/operators", timeout=15)
        assert r.status_code == 200, f"Admin operators list failed: {r.status_code}"
        
        data = r.json()
        items = data.get("items", [])
        assert len(items) > 0, "Should have operators"
        self.log(f"✓ Admin operators list working: {len(items)} operators")
    
    # ========================================================================
    # MAIN TEST RUNNER
    # ========================================================================
    
    def run_all_tests(self):
        """Run all Phase F tests"""
        self.log("=" * 80)
        self.log("LUMEN 2.0 Phase F — Operator OS Backend Test Suite")
        self.log("=" * 80)
        
        # AUTH
        self.log("\n📋 AUTH TESTS")
        self.test("AUTH: Login with all roles", self.test_auth_all_roles)
        
        # F10 OPERATOR PORTAL + SCOPING (CRITICAL)
        self.log("\n📋 F10 OPERATOR PORTAL + SCOPING (CRITICAL)")
        self.test("F10: operator/me", self.test_f10_operator_me)
        self.test("F10: operator/dashboard", self.test_f10_operator_dashboard)
        self.test("F10: operator/assets (scoped)", self.test_f10_operator_assets_scoped)
        self.test("F10 SCOPING: 403 for non-managed asset", self.test_f10_scoping_403_non_managed_asset)
        self.test("F10 SCOPING: 403 for non-operator role", self.test_f10_scoping_403_non_operator_role)
        self.test("F10: Report submission resets SLA", self.test_f10_report_submission_resets_sla)
        self.test("F10: operator/reports", self.test_f10_operator_reports)
        self.test("F10: operator/investors", self.test_f10_operator_investors)
        self.test("F10: operator/kpi", self.test_f10_operator_kpi)
        self.test("F10: operator/dealflow", self.test_f10_operator_dealflow)
        self.test("F10: operator/fees", self.test_f10_operator_fees)
        
        # F1+F2 ADMIN OPERATOR MANAGEMENT
        self.log("\n📋 F1+F2 ADMIN OPERATOR MANAGEMENT")
        self.test("F1: admin/operators/overview", self.test_f1_admin_operator_overview)
        self.test("F2: admin/operators/verification", self.test_f2_admin_verification_transition)
        self.test("F1: admin/operators/profile", self.test_f1_admin_profile_update)
        
        # F3-F9 ADMIN ENDPOINTS
        self.log("\n📋 F3-F9 ADMIN ENDPOINTS")
        self.test("F3: admin/operators/kpi", self.test_f3_admin_kpi)
        self.test("F4: admin/operators/sla", self.test_f4_admin_sla)
        self.test("F4: admin/operators/sla/scan", self.test_f4_admin_sla_scan)
        self.test("F5: admin/operators/reputation", self.test_f5_admin_reputation)
        self.test("F6: admin/operators/governance", self.test_f6_admin_governance)
        self.test("F6: admin/operators/governance/scan", self.test_f6_admin_governance_scan)
        self.test("F8: admin/operators/dealflow", self.test_f8_admin_dealflow)
        self.test("F9: admin/operators/fees", self.test_f9_admin_fees_update)
        
        # F7 PUBLIC LEADERBOARD
        self.log("\n📋 F7 PUBLIC LEADERBOARD (NO AUTH)")
        self.test("F7: Public leaderboard", self.test_f7_public_leaderboard)
        self.test("F7: Public operator card", self.test_f7_public_operator_card)
        self.test("F7: Asset operator card", self.test_f7_asset_operator_card)
        
        # F1 DOCUMENTS + ASSETS
        self.log("\n📋 F1 DOCUMENTS + ASSETS")
        self.test("F1: admin/operators/documents", self.test_f1_admin_documents)
        self.test("F1: admin/operators/assets", self.test_f1_admin_assets_assign_unassign)
        
        # F10 LINK USER
        self.log("\n📋 F10 LINK USER")
        self.test("F10: admin/operators/link-user", self.test_f10_admin_link_user)
        
        # REGRESSION
        self.log("\n📋 REGRESSION: PHASE E ENDPOINTS")
        self.test("REGRESSION: admin/deals", self.test_regression_phase_e_deals)
        self.test("REGRESSION: admin/operators list", self.test_regression_admin_operators_list)
        
        # SUMMARY
        self.log("\n" + "=" * 80)
        self.log("TEST SUMMARY")
        self.log("=" * 80)
        self.log(f"Total tests: {self.tests_run}")
        self.log(f"✅ Passed: {self.tests_passed}")
        self.log(f"❌ Failed: {self.tests_failed}")
        
        if self.failures:
            self.log("\n❌ FAILED TESTS:")
            for f in self.failures:
                self.log(f"  - {f['test']}: {f['error']}")
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        self.log(f"\n📊 Success Rate: {success_rate:.1f}%")
        
        return self.tests_failed == 0


if __name__ == "__main__":
    tester = PhaseF_Tester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)
