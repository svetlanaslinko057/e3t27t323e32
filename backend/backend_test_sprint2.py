"""
LUMEN Sprint 2 Investment Core - Independent Verification Test
Tests all endpoints via PUBLIC URL with proper auth and cleanup.
"""
import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

# Use PUBLIC endpoint for testing
BASE = "https://lumen-staging.preview.emergentagent.com"
ASSET_PODILSKYI = "asset-podilskyi"  # open, min_ticket=75000
ASSET_VYSHNEVE = "asset-vyshneve-cottage"  # draft status
TEST_AMOUNT = 100_000.0

class TestRunner:
    def __init__(self):
        self.failures = []
        self.passes = 0
        self.client_http = None
        self.admin_http = None
        self.mongo_client = None
        self.db = None
        self.cleanup_ids = []
        
    def check(self, name, condition, extra=""):
        status = "✅ PASS" if condition else "❌ FAIL"
        print(f"{status} | {name} {extra}")
        if condition:
            self.passes += 1
        else:
            self.failures.append(name)
    
    async def login(self, client: httpx.AsyncClient, email: str):
        """Quick login and set session cookie"""
        try:
            r = await client.post(f"{BASE}/api/auth/quick", json={"email": email})
            if r.status_code != 200:
                print(f"❌ Login failed for {email}: {r.status_code}")
                return False
            token = r.cookies.get("session_token")
            if not token:
                print(f"❌ No session_token for {email}")
                return False
            client.cookies.set("session_token", token)
            return True
        except Exception as e:
            print(f"❌ Login exception for {email}: {e}")
            return False
    
    async def setup(self):
        """Initialize HTTP clients and MongoDB connection"""
        print("\n🔧 Setting up test environment...")
        
        # HTTP clients
        self.client_http = httpx.AsyncClient(timeout=30, follow_redirects=True)
        self.admin_http = httpx.AsyncClient(timeout=30, follow_redirects=True)
        
        # Login
        client_ok = await self.login(self.client_http, "client@atlas.dev")
        admin_ok = await self.login(self.admin_http, "admin@atlas.dev")
        
        if not client_ok or not admin_ok:
            print("❌ Failed to authenticate users")
            return False
        
        # MongoDB for cleanup and verification
        self.mongo_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        self.db = self.mongo_client[os.environ["DB_NAME"]]
        
        # Get investor ID
        r = await self.client_http.get(f"{BASE}/api/auth/me")
        if r.status_code == 200:
            me = r.json()
            self.investor_id = me.get("user_id") or me.get("id")
            print(f"✅ Authenticated as investor: {self.investor_id}")
        else:
            print(f"❌ Failed to get investor ID: {r.status_code}")
            return False
        
        return True
    
    async def cleanup(self):
        """Clean up test data"""
        print("\n🧹 Cleaning up test data...")
        try:
            if self.cleanup_ids:
                # Delete test intents
                for intent_id in self.cleanup_ids:
                    await self.db.lumen_investor_intents.delete_one({"id": intent_id})
                
                # Delete test investments
                await self.db.lumen_investments.delete_many({
                    "intent_id": {"$in": self.cleanup_ids}
                })
                
                # Recompute funding for affected assets
                from lumen_investment_core import _upsert_ownership, _recompute_asset_funding
                await _upsert_ownership(self.investor_id, ASSET_PODILSKYI, None)
                await _recompute_asset_funding(ASSET_PODILSKYI)
                
                print(f"✅ Cleaned up {len(self.cleanup_ids)} test records")
        except Exception as e:
            print(f"⚠️  Cleanup warning: {e}")
        
        if self.client_http:
            await self.client_http.aclose()
        if self.admin_http:
            await self.admin_http.aclose()
    
    async def test_intent_submission(self):
        """Test 1: Submit intent with validation"""
        print("\n📝 Test 1: Intent Submission & Validation")
        
        # Valid intent
        r = await self.client_http.post(
            f"{BASE}/api/investor/intents",
            json={"asset_id": ASSET_PODILSKYI, "amount": TEST_AMOUNT, "note": "test-intent"}
        )
        self.check("POST /api/investor/intents returns 200", r.status_code == 200, f"[{r.status_code}]")
        
        if r.status_code == 200:
            intent = r.json()
            self.intent_id = intent.get("id")
            self.cleanup_ids.append(self.intent_id)
            
            self.check("Intent status is 'submitted'", intent.get("status") == "submitted")
            self.check("Intent has status_label in Ukrainian", intent.get("status_label") == "подано")
            self.check("Intent auto-attached to round", bool(intent.get("round_id")))
            self.round_id = intent.get("round_id")
        
        # Validation: amount below min_ticket
        r = await self.client_http.post(
            f"{BASE}/api/investor/intents",
            json={"asset_id": ASSET_PODILSKYI, "amount": 10000}
        )
        self.check("Amount below min_ticket returns 400", r.status_code == 400, f"[{r.status_code}]")
        
        # Validation: unknown asset
        r = await self.client_http.post(
            f"{BASE}/api/investor/intents",
            json={"asset_id": "asset-nonexistent", "amount": TEST_AMOUNT}
        )
        self.check("Unknown asset_id returns 404", r.status_code == 404, f"[{r.status_code}]")
        
        # Validation: draft asset (not open)
        r = await self.client_http.post(
            f"{BASE}/api/investor/intents",
            json={"asset_id": ASSET_VYSHNEVE, "amount": 200000}
        )
        self.check("Draft asset (status!=open) returns 400", r.status_code == 400, f"[{r.status_code}]")
    
    async def test_legacy_intent_alias(self):
        """Test 2: Legacy intent alias"""
        print("\n📝 Test 2: Legacy Intent Alias")
        
        r = await self.client_http.post(
            f"{BASE}/api/investor/intent",
            json={"asset_id": ASSET_PODILSKYI, "amount": TEST_AMOUNT}
        )
        self.check("POST /api/investor/intent (legacy) returns 200", r.status_code == 200, f"[{r.status_code}]")
        
        if r.status_code == 200:
            legacy_intent = r.json()
            legacy_id = legacy_intent.get("id")
            self.cleanup_ids.append(legacy_id)
            
            # Verify it lands in canonical collection
            doc = await self.db.lumen_investor_intents.find_one({"id": legacy_id})
            self.check("Legacy intent in lumen_investor_intents collection", bool(doc))
            self.check("Legacy intent has status 'submitted'", doc.get("status") == "submitted" if doc else False)
    
    async def test_list_intents(self):
        """Test 3: List investor intents"""
        print("\n📝 Test 3: List Investor Intents")
        
        r = await self.client_http.get(f"{BASE}/api/investor/intents")
        self.check("GET /api/investor/intents returns 200", r.status_code == 200, f"[{r.status_code}]")
        
        if r.status_code == 200:
            data = r.json()
            items = data.get("items", [])
            self.check("Response has 'items' array", isinstance(items, list))
            
            # Check if our test intent is in the list
            test_intent = next((i for i in items if i.get("id") == self.intent_id), None)
            self.check("Test intent appears in list", bool(test_intent))
            
            if test_intent:
                self.check("Intent has status_label", bool(test_intent.get("status_label")))
    
    async def test_admin_intents_auth(self):
        """Test 4: Admin intents with auth guards"""
        print("\n📝 Test 4: Admin Intents & Auth Guards")
        
        # Admin can access
        r = await self.admin_http.get(f"{BASE}/api/admin/intents?status=submitted")
        self.check("GET /api/admin/intents (admin) returns 200", r.status_code == 200, f"[{r.status_code}]")
        
        if r.status_code == 200:
            data = r.json()
            self.check("Admin response has 'items'", "items" in data)
            self.check("Admin response has 'counts' dict", "counts" in data)
            
            items = data.get("items", [])
            test_intent = next((i for i in items if i.get("id") == self.intent_id), None)
            self.check("Admin can see test intent", bool(test_intent))
        
        # Client cannot access admin endpoint
        r = await self.client_http.get(f"{BASE}/api/admin/intents")
        self.check("GET /api/admin/intents (client) returns 403", r.status_code == 403, f"[{r.status_code}]")
        
        # Unauthenticated cannot access
        anon_client = httpx.AsyncClient(timeout=30)
        r = await anon_client.get(f"{BASE}/api/admin/intents")
        self.check("GET /api/admin/intents (no auth) returns 401", r.status_code == 401, f"[{r.status_code}]")
        await anon_client.aclose()
    
    async def test_approve_intent(self):
        """Test 5: Approve intent - full chain"""
        print("\n📝 Test 5: Approve Intent - Investment Chain")
        
        # Get baseline state
        asset_before = await self.db.lumen_assets.find_one({"id": ASSET_PODILSKYI})
        raised_before = float(asset_before.get("raised_amount") or asset_before.get("raised") or 0)
        
        own_before = await self.db.lumen_ownerships.find_one({
            "investor_id": self.investor_id,
            "asset_id": ASSET_PODILSKYI
        }) or {}
        units_before = float(own_before.get("units") or 0)
        
        # Approve
        r = await self.admin_http.post(
            f"{BASE}/api/admin/intents/{self.intent_id}/approve",
            json={"note": "test approval"}
        )
        self.check("POST /api/admin/intents/{id}/approve returns 200", r.status_code == 200, f"[{r.status_code}]")
        
        if r.status_code == 200:
            response = r.json()
            
            # Check investment
            investment = response.get("investment", {})
            self.investment_id = investment.get("id")
            self.check("Response contains 'investment'", bool(investment))
            self.check("Investment status is 'active'", investment.get("status") == "active")
            self.check("Investment has status_label", investment.get("status_label") == "активна")
            self.check("Investment has history array", isinstance(investment.get("history"), list))
            self.check("Investment history is non-empty", len(investment.get("history", [])) > 0)
            
            # Check ownership
            ownership = response.get("ownership", {})
            self.check("Response contains 'ownership'", bool(ownership))
            units_after = float(ownership.get("units", 0))
            self.check("Ownership units increased", units_after >= units_before + TEST_AMOUNT - 0.01)
            
            # Check asset funding
            funding = response.get("asset_funding", {})
            self.check("Response contains 'asset_funding'", bool(funding))
            
            # Verify in MongoDB
            intent_doc = await self.db.lumen_investor_intents.find_one({"id": self.intent_id})
            self.check("Intent status changed to 'converted'", intent_doc.get("status") == "converted")
            self.check("Intent has converted_investment_id", bool(intent_doc.get("converted_investment_id")))
            
            inv_doc = await self.db.lumen_investments.find_one({"id": self.investment_id})
            self.check("Investment doc exists in lumen_investments", bool(inv_doc))
            self.check("Investment has intent_id link", inv_doc.get("intent_id") == self.intent_id if inv_doc else False)
            
            # Check asset raised_amount
            asset_after = await self.db.lumen_assets.find_one({"id": ASSET_PODILSKYI})
            raised_after = float(asset_after.get("raised_amount") or 0)
            self.check("Asset raised_amount increased", 
                      abs(raised_after - (raised_before + TEST_AMOUNT)) < 0.01,
                      f"({raised_before} → {raised_after})")
            
            # Check legacy mirror
            legacy_raised = float(asset_after.get("raised") or 0)
            self.check("Legacy 'raised' field synced", abs(legacy_raised - raised_after) < 0.01)
            
            # Check round raised_amount
            if self.round_id:
                round_doc = await self.db.lumen_investment_rounds.find_one({"id": self.round_id})
                if round_doc:
                    round_raised = float(round_doc.get("raised_amount") or 0)
                    self.check("Round raised_amount updated", round_raised >= TEST_AMOUNT)
            
            # Check ownership registry
            own_doc = await self.db.lumen_ownerships.find_one({
                "investor_id": self.investor_id,
                "asset_id": ASSET_PODILSKYI
            })
            self.check("Ownership doc upserted in lumen_ownerships", bool(own_doc))
            if own_doc:
                self.check("Ownership has ownership_percent", float(own_doc.get("ownership_percent", 0)) > 0)
    
    async def test_double_approve(self):
        """Test 6: Double approve returns 409"""
        print("\n📝 Test 6: Double Approve Idempotency")
        
        r = await self.admin_http.post(
            f"{BASE}/api/admin/intents/{self.intent_id}/approve",
            json={}
        )
        self.check("Double approve returns 409", r.status_code == 409, f"[{r.status_code}]")
    
    async def test_reject_intent(self):
        """Test 7: Reject intent"""
        print("\n📝 Test 7: Reject Intent")
        
        # Create a new intent to reject
        r = await self.client_http.post(
            f"{BASE}/api/investor/intents",
            json={"asset_id": ASSET_PODILSKYI, "amount": TEST_AMOUNT}
        )
        if r.status_code == 200:
            reject_intent_id = r.json().get("id")
            self.cleanup_ids.append(reject_intent_id)
            
            # Reject it
            r = await self.admin_http.post(
                f"{BASE}/api/admin/intents/{reject_intent_id}/reject",
                json={"note": "test rejection"}
            )
            self.check("POST /api/admin/intents/{id}/reject returns 200", r.status_code == 200, f"[{r.status_code}]")
            
            if r.status_code == 200:
                response = r.json()
                self.check("Reject response has status 'rejected'", response.get("status") == "rejected")
                
                # Verify in DB
                doc = await self.db.lumen_investor_intents.find_one({"id": reject_intent_id})
                self.check("Intent status is 'rejected' in DB", doc.get("status") == "rejected" if doc else False)
                self.check("Intent has admin_note", bool(doc.get("admin_note")) if doc else False)
        
        # Test reject non-existent intent
        r = await self.admin_http.post(
            f"{BASE}/api/admin/intents/nonexistent-id/reject",
            json={"note": "test"}
        )
        self.check("Reject non-existent intent returns 404", r.status_code == 404, f"[{r.status_code}]")
    
    async def test_investment_detail(self):
        """Test 8: Get investment detail with history"""
        print("\n📝 Test 8: Investment Detail & History")
        
        if not hasattr(self, 'investment_id'):
            print("⚠️  Skipping - no investment_id from approve test")
            return
        
        # Investor can access own investment
        r = await self.client_http.get(f"{BASE}/api/investor/investments/{self.investment_id}")
        self.check("GET /api/investor/investments/{id} returns 200", r.status_code == 200, f"[{r.status_code}]")
        
        if r.status_code == 200:
            inv = r.json()
            self.check("Investment has 'history' array", isinstance(inv.get("history"), list))
            self.check("Investment history is non-empty", len(inv.get("history", [])) > 0)
            
            # Check history structure
            if inv.get("history"):
                hist = inv["history"][0]
                self.check("History entry has 'status'", "status" in hist)
                self.check("History entry has 'at' timestamp", "at" in hist)
        
        # Admin can access any investment
        r = await self.admin_http.get(f"{BASE}/api/investor/investments/{self.investment_id}")
        self.check("Admin can access any investment", r.status_code == 200, f"[{r.status_code}]")
    
    async def test_ownerships(self):
        """Test 9: Ownership endpoints"""
        print("\n📝 Test 9: Ownership Endpoints")
        
        # Investor ownerships
        r = await self.client_http.get(f"{BASE}/api/investor/ownerships")
        self.check("GET /api/investor/ownerships returns 200", r.status_code == 200, f"[{r.status_code}]")
        
        if r.status_code == 200:
            data = r.json()
            items = data.get("items", [])
            self.check("Ownerships response has 'items'", isinstance(items, list))
            self.check("Ownerships list is non-empty", len(items) > 0)
            
            if items:
                own = items[0]
                self.check("Ownership has 'asset_title' enrichment", bool(own.get("asset_title")))
                self.check("Ownership has 'units'", "units" in own)
                self.check("Ownership has 'ownership_percent'", "ownership_percent" in own)
        
        # Admin ownerships with filter
        r = await self.admin_http.get(f"{BASE}/api/admin/ownerships?asset_id={ASSET_PODILSKYI}")
        self.check("GET /api/admin/ownerships returns 200", r.status_code == 200, f"[{r.status_code}]")
        
        if r.status_code == 200:
            data = r.json()
            items = data.get("items", [])
            self.check("Admin ownerships has items", isinstance(items, list))
            
            if items:
                own = items[0]
                self.check("Admin ownership has 'investor_name'", "investor_name" in own)
                self.check("Admin ownership has 'investor_email'", "investor_email" in own)
    
    async def test_portfolio(self):
        """Test 10: Portfolio from real registry"""
        print("\n📝 Test 10: Portfolio Engine (Real Registry)")
        
        r = await self.client_http.get(f"{BASE}/api/investor/portfolio")
        self.check("GET /api/investor/portfolio returns 200", r.status_code == 200, f"[{r.status_code}]")
        
        if r.status_code == 200:
            portfolio = r.json()
            
            # Check summary
            summary = portfolio.get("summary", {})
            self.check("Portfolio has 'summary'", bool(summary))
            self.check("Summary has 'total_value'", "total_value" in summary)
            self.check("Summary has 'average_yield'", "average_yield" in summary)
            self.check("Summary has 'active_count'", "active_count" in summary)
            self.check("Summary has 'paid_this_year'", "paid_this_year" in summary)
            
            # Check investments array
            investments = portfolio.get("investments", [])
            self.check("Portfolio has 'investments' array", isinstance(investments, list))
            
            if hasattr(self, 'investment_id'):
                test_inv = next((i for i in investments if i.get("id") == self.investment_id), None)
                self.check("New investment visible in portfolio", bool(test_inv))
                
                if test_inv:
                    self.check("Investment has 'share_percent' from ownership", 
                              float(test_inv.get("share_percent", 0)) > 0)
                    self.check("Investment has 'amount'", "amount" in test_inv)
            
            # Check ownerships array
            ownerships = portfolio.get("ownerships", [])
            self.check("Portfolio has 'ownerships' array", isinstance(ownerships, list))
            self.check("Ownerships array is non-empty", len(ownerships) > 0)
            
            # Check upcoming payouts
            upcoming = portfolio.get("upcoming_payouts", [])
            self.check("Portfolio has 'upcoming_payouts' array", isinstance(upcoming, list))
            
            # Verify data comes from real registry (not mock)
            if investments:
                # Check that amounts match MongoDB
                for inv in investments[:3]:  # Check first 3
                    inv_id = inv.get("id")
                    if inv_id:
                        db_inv = await self.db.lumen_investments.find_one({"id": inv_id})
                        if db_inv:
                            db_amount = float(db_inv.get("amount") or db_inv.get("invested_amount") or 0)
                            api_amount = float(inv.get("amount") or inv.get("invested_amount") or 0)
                            match = abs(db_amount - api_amount) < 0.01
                            if not match:
                                self.check(f"Investment {inv_id[:8]} amount matches DB", match,
                                          f"(API: {api_amount}, DB: {db_amount})")
                                break
                else:
                    self.check("Portfolio amounts match lumen_investments registry", True)
    
    async def test_admin_rounds(self):
        """Test 11: Admin rounds endpoint"""
        print("\n📝 Test 11: Admin Rounds Registry")
        
        r = await self.admin_http.get(f"{BASE}/api/admin/rounds")
        self.check("GET /api/admin/rounds returns 200", r.status_code == 200, f"[{r.status_code}]")
        
        if r.status_code == 200:
            data = r.json()
            items = data.get("items", [])
            self.check("Rounds response has 'items'", isinstance(items, list))
            self.check("Rounds list is non-empty", len(items) > 0)
            
            if items:
                rnd = items[0]
                self.check("Round has 'round_name'", bool(rnd.get("round_name")))
                self.check("Round has 'minimum_ticket' field", "minimum_ticket" in rnd)
                self.check("Round has 'asset_title'", bool(rnd.get("asset_title")))
                
                # Check if data comes from lumen_investment_rounds
                round_id = rnd.get("id")
                if round_id:
                    db_round = await self.db.lumen_investment_rounds.find_one({"id": round_id})
                    self.check("Round data from lumen_investment_rounds registry", bool(db_round))
    
    async def test_regression(self):
        """Test 12: Regression checks"""
        print("\n📝 Test 12: Regression Tests")
        
        # Assets endpoint still works
        r = await self.client_http.get(f"{BASE}/api/assets")
        self.check("GET /api/assets returns 200", r.status_code == 200, f"[{r.status_code}]")
        
        if r.status_code == 200:
            data = r.json()
            items = data.get("items", [])
            self.check("Assets list has 6 items", len(items) == 6, f"(found {len(items)})")
        
        # Domain lock check
        r = await self.admin_http.get(f"{BASE}/api/admin/system/domain")
        if r.status_code == 200:
            data = r.json()
            self.check("LUMEN_ONLY domain lock active", data.get("lumen_only") == True)
            self.check("Domain lock has skipped_count", "skipped_count" in data)
    
    async def run_all_tests(self):
        """Run all tests in sequence"""
        print("\n" + "="*70)
        print("🧪 LUMEN Sprint 2 Investment Core - Independent Verification")
        print("="*70)
        
        if not await self.setup():
            print("\n❌ Setup failed, aborting tests")
            return 1
        
        try:
            await self.test_intent_submission()
            await self.test_legacy_intent_alias()
            await self.test_list_intents()
            await self.test_admin_intents_auth()
            await self.test_approve_intent()
            await self.test_double_approve()
            await self.test_reject_intent()
            await self.test_investment_detail()
            await self.test_ownerships()
            await self.test_portfolio()
            await self.test_admin_rounds()
            await self.test_regression()
            
        finally:
            await self.cleanup()
        
        # Summary
        print("\n" + "="*70)
        print("📊 TEST SUMMARY")
        print("="*70)
        total = self.passes + len(self.failures)
        print(f"Total Tests: {total}")
        print(f"✅ Passed: {self.passes}")
        print(f"❌ Failed: {len(self.failures)}")
        
        if self.failures:
            print(f"\n❌ Failed Tests:")
            for f in self.failures:
                print(f"  - {f}")
            return 1
        else:
            print("\n🎉 ALL TESTS PASSED!")
            return 0

async def main():
    runner = TestRunner()
    return await runner.run_all_tests()

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
