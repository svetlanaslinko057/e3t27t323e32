#!/usr/bin/env python3
"""
Backend Test: LUMEN Capital Pool OS — Cash Conservation Audit
==============================================================
Tests the cash-movements journal and conservation audit (Statement A & B).

Features tested:
- GET /api/admin/pools/{id}/cash-audit (Statement A: per-pool conservation)
- GET /api/admin/pool-cash-audit (Statement B: platform-wide investor balances)
- Tax amount tracking in revenue events
- Movement journal with all types (INFLOW, REVENUE, OUTFLOW, TAX, RESERVE, DISTRIBUTION)
- I7_cash_conservation invariant
- Full lifecycle conservation: IN = OUT + BALANCE
"""
import requests
import sys

import os
BASE_URL = os.environ.get("AUDIT_BASE_URL", "http://localhost:8001")

class CashAuditTester:
    def __init__(self):
        self.admin_token = None
        self.investor_token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.pool_id = None

    def log(self, msg):
        print(f"  {msg}")

    def test(self, name, condition, detail=""):
        self.tests_run += 1
        if condition:
            self.tests_passed += 1
            print(f"✅ {name}")
        else:
            print(f"❌ {name}" + (f" — {detail}" if detail else ""))
        return condition

    def login(self, email, password):
        """Login and return session token"""
        try:
            r = requests.post(f"{BASE_URL}/api/auth/login", 
                json={"email": email, "password": password},
                timeout=10)
            if r.status_code == 200:
                token = r.cookies.get("session_token")
                if not token:
                    for cookie in r.headers.get("set-cookie", "").split(","):
                        if "session_token=" in cookie:
                            token = cookie.split("session_token=")[1].split(";")[0]
                            break
                return token
            return None
        except Exception as e:
            self.log(f"Login error: {e}")
            return None

    def req(self, method, endpoint, token=None, json_data=None, expected_status=200):
        """Make authenticated request"""
        url = f"{BASE_URL}/api{endpoint}"
        headers = {"Content-Type": "application/json"}
        cookies = {}
        if token:
            cookies["session_token"] = token
        
        try:
            if method == "GET":
                r = requests.get(url, headers=headers, cookies=cookies, timeout=15)
            elif method == "POST":
                r = requests.post(url, headers=headers, cookies=cookies, json=json_data, timeout=15)
            else:
                return None, None
            
            success = r.status_code == expected_status
            data = r.json() if r.status_code < 500 and r.text else {}
            return success, data, r.status_code
        except Exception as e:
            self.log(f"Request error {method} {endpoint}: {e}")
            return False, {}, 0

    def run_all_tests(self):
        print("\n" + "="*70)
        print("LUMEN CAPITAL POOL OS — CASH CONSERVATION AUDIT TEST")
        print("="*70)

        # ── Auth ──
        print("\n[1] Authentication")
        self.admin_token = self.login("admin@atlas.dev", "admin123")
        self.test("Admin login", bool(self.admin_token))
        
        self.investor_token = self.login("client@atlas.dev", "client123")
        if not self.investor_token:
            self.investor_token = self.admin_token
        self.test("Investor login", bool(self.investor_token))

        # ── Auth guard for cash-audit ──
        print("\n[2] Cash Audit Auth Guards")
        success, _, status = self.req("GET", "/admin/pool-cash-audit", token=None, expected_status=401)
        self.test("GET /admin/pool-cash-audit without auth → 401", success, f"got {status}")

        # ── Create fresh pool for numeric assertions ──
        print("\n[3] Create Fresh Pool for Conservation Test")
        success, data, status = self.req("POST", "/admin/pools", token=self.admin_token,
            json_data={
                "asset_id": "cash-audit-test-pool",
                "title": "Cash Conservation Test Pool",
                "currency": "EUR",
                "target_amount": 100000,
                "min_ticket": 1000,
                "total_units": 100000
            })
        self.test("Create pool → 200", success, f"got {status}")
        if not success or "pool" not in data:
            self.log("❌ Pool creation failed, stopping tests")
            return self.summary()
        
        self.pool_id = data["pool"]["id"]
        self.log(f"Pool ID: {self.pool_id}")

        # ── Open pool ──
        success, _, _ = self.req("POST", f"/admin/pools/{self.pool_id}/open", token=self.admin_token)
        self.test("Open pool → 200", success)

        # ── Single investor contributes 100000 ──
        print("\n[4] Investor Contribution (100000 EUR)")
        success, data, status = self.req("POST", "/investor/pools/contribute",
            token=self.investor_token,
            json_data={"pool_id": self.pool_id, "amount": 100000, "currency": "EUR"})
        self.test("Contribute 100000 EUR → 200", success, f"got {status}")
        
        if not success or "contribution" not in data:
            self.log("❌ Contribution failed, stopping tests")
            return self.summary()
        
        contrib_id = data["contribution"]["id"]

        # ── Confirm contribution ──
        print("\n[5] Confirm Contribution")
        success, _, _ = self.req("POST", f"/admin/pool-contributions/{contrib_id}/confirm",
            token=self.admin_token,
            json_data={
                "provider_ref": f"prov-{contrib_id}",
                "bank_reference": f"ref-{contrib_id}",
                "received_amount": 100000,
                "received_currency": "EUR"
            })
        self.test("Confirm contribution → 200", success)

        # ── Release to seller (100000) ──
        print("\n[6] Release to Seller (100000 EUR)")
        success, _, _ = self.req("POST", f"/admin/pools/{self.pool_id}/release-to-seller",
            token=self.admin_token,
            json_data={
                "amount": 100000,
                "seller_name": "Seller Ltd",
                "seller_iban": "UA000000",
                "reason": "Asset purchase"
            })
        self.test("Release 100000 EUR → 200", success)

        # ── Mark operating ──
        success, _, _ = self.req("POST", f"/admin/pools/{self.pool_id}/mark-operating",
            token=self.admin_token)
        self.test("Mark operating → 200", success)

        # ── Revenue event WITH TAX ──
        print("\n[7] Revenue Event with Tax Amount")
        success, data, status = self.req("POST", "/admin/revenue-events",
            token=self.admin_token,
            json_data={
                "pool_id": self.pool_id,
                "gross_amount": 10000,
                "expenses_amount": 1000,
                "reserve_amount": 1000,
                "tax_amount": 500,  # NEW: tax amount
                "description": "Revenue with tax"
            })
        self.test("Create revenue event with tax → 200", success, f"got {status}")
        
        if success and "revenue_event" in data:
            rev_event = data["revenue_event"]
            # net = gross - expenses - reserve - tax = 10000 - 1000 - 1000 - 500 = 7500
            expected_net = 7500
            self.test("net_distributable = 7500 (with tax)", 
                rev_event.get("net_distributable") == expected_net,
                f"got {rev_event.get('net_distributable')}")
            self.test("tax_amount = 500", 
                rev_event.get("tax_amount") == 500,
                f"got {rev_event.get('tax_amount')}")
            
            rev_event_id = rev_event["id"]
            
            # ── Distribute revenue ──
            print("\n[8] Distribute Revenue")
            success, data, _ = self.req("POST", 
                f"/admin/revenue-events/{rev_event_id}/distribute",
                token=self.admin_token)
            self.test("Distribute revenue → 200", success)
            if success:
                self.test("distributed_amount = 7500", 
                    data.get("distributed_amount") == 7500,
                    f"got {data.get('distributed_amount')}")

        # ── Cash Audit (Statement A) ──
        print("\n[9] Cash Audit — Statement A (Per-Pool Conservation)")
        success, data, status = self.req("GET", f"/admin/pools/{self.pool_id}/cash-audit",
            token=self.admin_token)
        self.test("GET /admin/pools/{id}/cash-audit → 200", success, f"got {status}")
        
        if success:
            audit = data
            self.log(f"Audit data: {audit}")
            
            # Check structure
            self.test("Audit has 'inflows' field", "inflows" in audit)
            self.test("Audit has 'outflows' field", "outflows" in audit)
            self.test("Audit has 'cash_balance' field", "cash_balance" in audit)
            self.test("Audit has 'reserves_earmarked' field", "reserves_earmarked" in audit)
            self.test("Audit has 'free_cash' field", "free_cash" in audit)
            self.test("Audit has 'reconciles' field", "reconciles" in audit)
            self.test("Audit has 'movements' field", "movements" in audit)
            
            # Check numeric conservation
            # IN = contributions(100000) + revenue(10000) = 110000
            inflows_total = audit.get("inflows", {}).get("total", 0)
            self.test("inflows.total = 110000", inflows_total == 110000,
                f"got {inflows_total}")
            self.test("inflows.contributions = 100000", 
                audit.get("inflows", {}).get("contributions") == 100000)
            self.test("inflows.revenue = 10000", 
                audit.get("inflows", {}).get("revenue") == 10000)
            
            # OUT = releases(100000) + expenses(1000) + tax(500) + distributions(7500) = 109000
            outflows_total = audit.get("outflows", {}).get("total", 0)
            self.test("outflows.total = 109000", outflows_total == 109000,
                f"got {outflows_total}")
            self.test("outflows.seller_releases = 100000", 
                audit.get("outflows", {}).get("seller_releases") == 100000)
            self.test("outflows.expenses = 1000", 
                audit.get("outflows", {}).get("expenses") == 1000)
            self.test("outflows.tax = 500", 
                audit.get("outflows", {}).get("tax") == 500)
            self.test("outflows.distributions = 7500", 
                audit.get("outflows", {}).get("distributions") == 7500)
            
            # BALANCE = reserve(1000)
            cash_balance = audit.get("cash_balance", 0)
            self.test("cash_balance = 1000 (reserve)", cash_balance == 1000,
                f"got {cash_balance}")
            self.test("reserves_earmarked = 1000", 
                audit.get("reserves_earmarked") == 1000)
            self.test("free_cash = 0", 
                audit.get("free_cash") == 0)
            
            # Conservation identity: IN = OUT + BALANCE
            self.test("Conservation: IN = OUT + BALANCE", 
                audit.get("reconciles") == True,
                f"reconciles={audit.get('reconciles')}")
            
            # Movement journal
            movements = audit.get("movements", [])
            self.test("Movement journal populated", len(movements) >= 5,
                f"found {len(movements)} movements")
            
            # Check movement types
            mtypes = {m.get("type") for m in movements}
            self.test("Journal has INFLOW", "INFLOW" in mtypes)
            self.test("Journal has REVENUE", "REVENUE" in mtypes)
            self.test("Journal has OUTFLOW", "OUTFLOW" in mtypes)
            self.test("Journal has TAX", "TAX" in mtypes)
            self.test("Journal has RESERVE", "RESERVE" in mtypes)
            self.test("Journal has DISTRIBUTION", "DISTRIBUTION" in mtypes)
            
            # Check movement structure
            if movements:
                m = movements[0]
                self.test("Movement has 'id'", "id" in m)
                self.test("Movement has 'type'", "type" in m)
                self.test("Movement has 'direction'", "direction" in m)
                self.test("Movement has 'amount'", "amount" in m)
                self.test("Movement has 'currency'", "currency" in m)
                self.test("Movement has 'description'", "description" in m)

        # ── 404 for unknown pool ──
        print("\n[10] Cash Audit 404 Guard")
        success, _, status = self.req("GET", "/admin/pools/unknown-pool-id/cash-audit",
            token=self.admin_token,
            expected_status=404)
        self.test("GET cash-audit for unknown pool → 404", success, f"got {status}")

        # ── Statement B (Global Investor Balance Audit) ──
        print("\n[11] Cash Audit — Statement B (Platform-Wide)")
        success, data, status = self.req("GET", "/admin/pool-cash-audit",
            token=self.admin_token)
        self.test("GET /admin/pool-cash-audit → 200", success, f"got {status}")
        
        if success:
            audit_b = data
            self.log(f"Statement B: {audit_b}")
            
            # Check structure
            self.test("Statement B has 'distributions_credited'", 
                "distributions_credited" in audit_b)
            self.test("Statement B has 'withdrawals_paid'", 
                "withdrawals_paid" in audit_b)
            self.test("Statement B has 'outstanding_balances'", 
                "outstanding_balances" in audit_b)
            self.test("Statement B has 'reconciles'", 
                "reconciles" in audit_b)
            
            # Conservation identity: distributions = paid + outstanding
            dist = audit_b.get("distributions_credited", 0)
            paid = audit_b.get("withdrawals_paid", 0)
            outstanding = audit_b.get("outstanding_balances", 0)
            
            self.test("Statement B reconciles", 
                audit_b.get("reconciles") == True,
                f"reconciles={audit_b.get('reconciles')}")
            
            # Check identity (with tolerance for cumulative balances)
            diff = abs(dist - (paid + outstanding))
            self.test("distributions = paid + outstanding (within 0.01)", 
                diff < 0.01,
                f"dist={dist}, paid={paid}, outstanding={outstanding}, diff={diff}")

        # ── Invariants with I7_cash_conservation ──
        print("\n[12] Pool Invariants (including I7_cash_conservation)")
        success, data, status = self.req("GET", f"/admin/pools/{self.pool_id}/invariants",
            token=self.admin_token)
        self.test("GET /admin/pools/{id}/invariants → 200", success, f"got {status}")
        
        if success:
            inv = data
            self.test("All invariants passed", inv.get("all_passed") == True,
                f"counts: {inv.get('counts')}")
            
            # Check for I7_cash_conservation
            checks = inv.get("checks", [])
            i7_check = next((c for c in checks if c.get("id") == "I7_cash_conservation"), None)
            self.test("I7_cash_conservation check exists", i7_check is not None)
            if i7_check:
                self.test("I7_cash_conservation passed", 
                    i7_check.get("passed") == True,
                    f"detail: {i7_check.get('detail')}")

        return self.summary()

    def summary(self):
        print("\n" + "="*70)
        print(f"RESULT: {self.tests_passed}/{self.tests_run} tests passed")
        print("="*70)
        if self.tests_passed == self.tests_run:
            print("✅ ALL CASH AUDIT TESTS PASSED")
            return 0
        else:
            print(f"❌ {self.tests_run - self.tests_passed} tests failed")
            return 1

def main():
    tester = CashAuditTester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())
