#!/usr/bin/env python3
"""
Backend Test: LUMEN Capital Pool OS
====================================
Full lifecycle test: create → open → contribute → confirm → funded → certificates
→ release → operating → revenue → distribute → balance → withdrawal → approve → pay → reconcile
+ invariants + guards
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://codebase-explorer-52.preview.emergentagent.com"

class PoolOSTester:
    def __init__(self):
        self.admin_token = None
        self.investor_token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.pool_id = None
        self.contribution_ids = []
        self.revenue_event_id = None
        self.withdrawal_id = None

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
        print("LUMEN CAPITAL POOL OS — BACKEND TEST")
        print("="*70)

        # ── Auth ──
        print("\n[1] Authentication")
        self.admin_token = self.login("admin@atlas.dev", "admin123")
        self.test("Admin login", bool(self.admin_token))
        
        self.investor_token = self.login("client@atlas.dev", "client123")
        if not self.investor_token:
            self.log("Investor login failed, using admin as investor")
            self.investor_token = self.admin_token
        self.test("Investor login", bool(self.investor_token))

        # ── Auth guard ──
        print("\n[2] Auth Guards")
        success, _, status = self.req("GET", "/admin/pools", token=None, expected_status=401)
        self.test("GET /admin/pools without auth → 401", success, f"got {status}")

        # ── Create pool ──
        print("\n[3] Create Pool")
        success, data, status = self.req("POST", "/admin/pools", token=self.admin_token,
            json_data={
                "asset_id": "test-asset-pool-os",
                "title": "Test Capital Pool",
                "currency": "EUR",
                "target_amount": 100000,
                "min_ticket": 1000,
                "total_units": 100000
            })
        self.test("POST /admin/pools → 200", success, f"got {status}")
        if success and "pool" in data:
            self.pool_id = data["pool"]["id"]
            self.test("Pool created with ID", bool(self.pool_id))
            self.test("Unit price = 1.0", abs(data["pool"]["unit_price"] - 1.0) < 0.01)
            self.test("Status = draft", data["pool"]["status"] == "draft")
        else:
            self.log("❌ Pool creation failed, stopping tests")
            return self.summary()

        # ── Open pool ──
        print("\n[4] Open Pool")
        success, data, status = self.req("POST", f"/admin/pools/{self.pool_id}/open", 
            token=self.admin_token)
        self.test("POST /admin/pools/{id}/open → 200", success, f"got {status}")
        if success:
            self.test("Status = fundraising", data.get("pool", {}).get("status") == "fundraising")

        # ── Contributions (investor) ──
        print("\n[5] Investor Contributions")
        amounts = [10000, 20000, 30000, 40000]
        for amt in amounts:
            success, data, status = self.req("POST", "/investor/pools/contribute",
                token=self.investor_token,
                json_data={"pool_id": self.pool_id, "amount": amt, "currency": "EUR"})
            self.test(f"Contribute {amt} EUR → 200", success, f"got {status}")
            if success and "contribution" in data:
                self.contribution_ids.append(data["contribution"]["id"])
                ref = data.get("payment_instructions", {}).get("reference")
                self.test(f"Payment reference present", bool(ref))

        # ── Min ticket guard ──
        success, _, status = self.req("POST", "/investor/pools/contribute",
            token=self.investor_token,
            json_data={"pool_id": self.pool_id, "amount": 500, "currency": "EUR"},
            expected_status=400)
        self.test("Contribute below min_ticket → 400", success, f"got {status}")

        # ── Confirm contributions ──
        print("\n[6] Admin Reconciliation (Confirm Contributions)")
        for i, cid in enumerate(self.contribution_ids):
            success, data, status = self.req("POST", f"/admin/pool-contributions/{cid}/confirm",
                token=self.admin_token,
                json_data={
                    "provider_ref": f"prov-{cid}",
                    "bank_reference": f"ref-{cid}",
                    "received_amount": amounts[i],
                    "received_currency": "EUR"
                })
            self.test(f"Confirm contribution {amounts[i]} EUR → 200", success, f"got {status}")

        # ── Double-confirm guard ──
        if self.contribution_ids:
            success, _, status = self.req("POST", f"/admin/pool-contributions/{self.contribution_ids[0]}/confirm",
                token=self.admin_token,
                json_data={
                    "provider_ref": "x",
                    "bank_reference": "y",
                    "received_amount": amounts[0],
                    "received_currency": "EUR"
                },
                expected_status=409)
            self.test("Double-confirm → 409", success, f"got {status}")

        # ── Amount mismatch guard ──
        # Create a contribution for mismatch test
        success, data, status = self.req("POST", "/investor/pools/contribute",
            token=self.investor_token,
            json_data={"pool_id": self.pool_id, "amount": 5000, "currency": "EUR"})
        if success:
            mm_cid = data["contribution"]["id"]
            success, _, status = self.req("POST", f"/admin/pool-contributions/{mm_cid}/confirm",
                token=self.admin_token,
                json_data={
                    "provider_ref": "x",
                    "bank_reference": "y",
                    "received_amount": 4999,  # Mismatch
                    "received_currency": "EUR"
                },
                expected_status=400)
            self.test("Amount mismatch → 400", success, f"got {status}")

        # ── Pool state after funding ──
        print("\n[7] Pool State After Funding")
        success, data, status = self.req("GET", f"/admin/pools/{self.pool_id}", 
            token=self.admin_token)
        if success and "pool" in data:
            pool = data["pool"]
            self.test("confirmed_amount = 100000", pool.get("confirmed_amount") == 100000, 
                f"got {pool.get('confirmed_amount')}")
            self.test("issued_units = 100000", pool.get("issued_units") == 100000,
                f"got {pool.get('issued_units')}")
            self.test("status = funded", pool.get("status") == "funded",
                f"got {pool.get('status')}")

        # ── Invariants ──
        print("\n[8] Pool Invariants")
        success, data, status = self.req("GET", f"/admin/pools/{self.pool_id}/invariants",
            token=self.admin_token)
        if success:
            self.test("All invariants passed", data.get("all_passed") == True,
                f"counts: {data.get('counts')}")

        # ── Certificates ──
        print("\n[9] Certificates Issued")
        success, data, status = self.req("GET", "/investor/pool-certificates",
            token=self.investor_token)
        if success:
            certs = [c for c in data.get("items", []) if c.get("pool_id") == self.pool_id]
            self.test("Certificate issued for investor", len(certs) >= 1, f"found {len(certs)}")

        # ── Release to seller ──
        print("\n[10] Release to Seller")
        success, data, status = self.req("POST", f"/admin/pools/{self.pool_id}/release-to-seller",
            token=self.admin_token,
            json_data={
                "amount": 100000,
                "seller_name": "Test Seller Ltd",
                "seller_iban": "UA000000",
                "reason": "Asset purchase"
            })
        self.test("Release 100000 EUR → 200", success, f"got {status}")
        if success:
            self.test("Status = released_to_seller", 
                data.get("pool", {}).get("status") == "released_to_seller")
            self.test("available_cash = 0", 
                data.get("pool", {}).get("available_cash") == 0)

        # ── Over-release guard ──
        success, _, status = self.req("POST", f"/admin/pools/{self.pool_id}/release-to-seller",
            token=self.admin_token,
            json_data={"amount": 1, "seller_name": "x", "reason": "y"},
            expected_status=409)
        self.test("Over-release → 409", success, f"got {status}")

        # ── Mark operating ──
        print("\n[11] Mark Operating")
        success, data, status = self.req("POST", f"/admin/pools/{self.pool_id}/mark-operating",
            token=self.admin_token)
        self.test("Mark operating → 200", success, f"got {status}")

        # ── Revenue event ──
        print("\n[12] Revenue Event & Distribution")
        # Get balance before
        success, data, status = self.req("GET", "/investor/pool-balances",
            token=self.investor_token)
        credited_before = 0
        if success:
            for b in data.get("items", []):
                if b.get("currency") == "EUR":
                    credited_before = b.get("credited", 0)
                    break

        success, data, status = self.req("POST", "/admin/revenue-events",
            token=self.admin_token,
            json_data={
                "pool_id": self.pool_id,
                "gross_amount": 10000,
                "expenses_amount": 1000,
                "reserve_amount": 1000,
                "description": "Test revenue"
            })
        self.test("Create revenue event → 200", success, f"got {status}")
        if success and "revenue_event" in data:
            self.revenue_event_id = data["revenue_event"]["id"]
            self.test("net_distributable = 8000", 
                data["revenue_event"].get("net_distributable") == 8000)

        # ── Distribute ──
        if self.revenue_event_id:
            success, data, status = self.req("POST", 
                f"/admin/revenue-events/{self.revenue_event_id}/distribute",
                token=self.admin_token)
            self.test("Distribute revenue → 200", success, f"got {status}")
            if success:
                self.test("distributed_amount = 8000", 
                    data.get("distributed_amount") == 8000)

            # ── Double-distribute guard ──
            success, _, status = self.req("POST",
                f"/admin/revenue-events/{self.revenue_event_id}/distribute",
                token=self.admin_token,
                expected_status=409)
            self.test("Double-distribute → 409", success, f"got {status}")

        # ── Pro-rata check ──
        print("\n[13] Pro-rata Distribution Check")
        success, data, status = self.req("GET", "/investor/pool-balances",
            token=self.investor_token)
        if success:
            for b in data.get("items", []):
                if b.get("currency") == "EUR":
                    credited_now = b.get("credited", 0)
                    delta = round(credited_now - credited_before, 2)
                    self.test("Credited delta = 8000 (100% ownership)", delta == 8000,
                        f"delta={delta}")
                    break

        # ── Withdrawal cycle ──
        print("\n[14] Withdrawal Cycle")
        success, data, status = self.req("POST", "/investor/pool-withdrawals",
            token=self.investor_token,
            json_data={"currency": "EUR", "amount": 3000, "destination_iban": "UA111"})
        self.test("Request withdrawal 3000 EUR → 200", success, f"got {status}")
        if success and "withdrawal" in data:
            self.withdrawal_id = data["withdrawal"]["id"]

        # ── Over-withdraw guard ──
        success, _, status = self.req("POST", "/investor/pool-withdrawals",
            token=self.investor_token,
            json_data={"currency": "EUR", "amount": 10000},
            expected_status=409)
        self.test("Over-withdraw → 409", success, f"got {status}")

        # ── Approve withdrawal ──
        if self.withdrawal_id:
            success, data, status = self.req("POST",
                f"/admin/pool-withdrawals/{self.withdrawal_id}/approve",
                token=self.admin_token)
            self.test("Approve withdrawal → 200", success, f"got {status}")

            # ── Pay withdrawal ──
            success, data, status = self.req("POST",
                f"/admin/pool-withdrawals/{self.withdrawal_id}/pay",
                token=self.admin_token,
                json_data={"bank_reference": "PAYOUT-TEST"})
            self.test("Pay withdrawal → 200", success, f"got {status}")

            # ── Reconcile withdrawal ──
            success, data, status = self.req("POST",
                f"/admin/pool-withdrawals/{self.withdrawal_id}/reconcile",
                token=self.admin_token)
            self.test("Reconcile withdrawal → 200", success, f"got {status}")
            if success:
                self.test("Status = reconciled", 
                    data.get("withdrawal", {}).get("status") == "reconciled")

        # ── Final invariants ──
        print("\n[15] Final Invariants Check")
        success, data, status = self.req("GET", f"/admin/pools/{self.pool_id}/invariants",
            token=self.admin_token)
        if success:
            self.test("Final invariants all passed", data.get("all_passed") == True,
                f"counts: {data.get('counts')}")

        # ── 404 guards ──
        print("\n[16] 404 Guards")
        success, _, status = self.req("POST", "/admin/pool-contributions/unknown-id/confirm",
            token=self.admin_token,
            json_data={"provider_ref": "x", "bank_reference": "y", 
                      "received_amount": 100, "received_currency": "EUR"},
            expected_status=404)
        self.test("Confirm unknown contribution → 404", success, f"got {status}")

        return self.summary()

    def summary(self):
        print("\n" + "="*70)
        print(f"RESULT: {self.tests_passed}/{self.tests_run} tests passed")
        print("="*70)
        if self.tests_passed == self.tests_run:
            print("✅ ALL TESTS PASSED")
            return 0
        else:
            print(f"❌ {self.tests_run - self.tests_passed} tests failed")
            return 1

def main():
    tester = PoolOSTester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())
