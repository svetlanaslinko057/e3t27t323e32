"""
LUMEN 2.0 / Phase A1 — Unit Registry & Ownership OS — Backend API Test

Tests the integer unit registry system:
- Admin registry endpoints (summary, invariants, asset detail, events, snapshots)
- Investor units endpoints (holdings, events)
- Secondary transfer conservation (CRITICAL: units conserved, events recorded, invariants OK)
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://code-setup-10.preview.emergentagent.com/api"

class PhaseA1Tester:
    def __init__(self):
        self.admin_token = None
        self.investor_token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_asset_id = "asset-stoyanka-land"  # Known asset from migration

    def run_test(self, name, method, endpoint, expected_status, data=None, token=None, check_fn=None):
        """Run a single API test"""
        url = f"{BASE_URL}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Cookie'] = f'session_token={token}'

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            if success:
                resp_data = response.json() if response.text else {}
                # Additional check function
                if check_fn:
                    check_result = check_fn(resp_data)
                    if not check_result:
                        print(f"❌ Failed - Check function returned False")
                        return False, resp_data
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                return True, resp_data
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                print(f"   Response: {response.text[:200]}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def login(self, email, password, role_name):
        """Login and get session token from cookies"""
        print(f"\n🔐 Logging in as {role_name} ({email})...")
        url = f"{BASE_URL}/auth/login"
        try:
            response = requests.post(url, json={"email": email, "password": password})
            if response.status_code == 200:
                # Extract session_token from cookies
                session_token = response.cookies.get('session_token')
                if session_token:
                    print(f"✅ {role_name} logged in successfully")
                    self.tests_run += 1
                    self.tests_passed += 1
                    return session_token
                else:
                    print(f"❌ {role_name} login failed - no session_token in cookies")
                    self.tests_run += 1
                    return None
            else:
                print(f"❌ {role_name} login failed - status {response.status_code}")
                self.tests_run += 1
                return None
        except Exception as e:
            print(f"❌ {role_name} login failed - {str(e)}")
            self.tests_run += 1
            return None

    def test_admin_registry_summary(self):
        """Test GET /api/admin/registry/summary"""
        success, data = self.run_test(
            "Admin Registry Summary",
            "GET",
            "admin/registry/summary",
            200,
            token=self.admin_token,
            check_fn=lambda d: (
                'totals' in d and
                'assets' in d and
                'total_units' in d['totals'] and
                'issued_units' in d['totals'] and
                'available_units' in d['totals'] and
                'listed_units' in d['totals'] and
                len(d['assets']) > 0
            )
        )
        if success:
            print(f"   Totals: {data['totals']['total_units']} total, {data['totals']['issued_units']} issued, {data['totals']['available_units']} available")
            print(f"   Assets: {len(data['assets'])} assets in registry")
        return success, data

    def test_admin_invariants(self):
        """Test GET /api/admin/registry/invariants"""
        success, data = self.run_test(
            "Admin Registry Invariants",
            "GET",
            "admin/registry/invariants",
            200,
            token=self.admin_token,
            check_fn=lambda d: (
                'all_ok' in d and
                'assets' in d and
                d['all_ok'] == True  # CRITICAL: must be True
            )
        )
        if success:
            print(f"   All OK: {data['all_ok']}")
            print(f"   Assets checked: {len(data['assets'])}")
            for asset in data['assets']:
                if not asset['ok']:
                    print(f"   ⚠️  Asset {asset['asset_id']} has invariant violation!")
        return success, data

    def test_admin_asset_detail(self):
        """Test GET /api/admin/registry/asset/{asset_id}"""
        success, data = self.run_test(
            f"Admin Asset Detail ({self.test_asset_id})",
            "GET",
            f"admin/registry/asset/{self.test_asset_id}",
            200,
            token=self.admin_token,
            check_fn=lambda d: (
                'asset_id' in d and
                'holders' in d and
                'recent_events' in d and
                'total_units' in d and
                'issued_units' in d
            )
        )
        if success:
            print(f"   Asset: {data.get('asset_title')}")
            print(f"   Holders: {len(data['holders'])} holders")
            print(f"   Events: {len(data['recent_events'])} recent events")
            if data['holders']:
                h = data['holders'][0]
                print(f"   Top holder: {h['investor_name']} - {h['units']} units ({h['percent']}%)")
        return success, data

    def test_admin_asset_events(self):
        """Test GET /api/admin/registry/asset/{asset_id}/events"""
        success, data = self.run_test(
            f"Admin Asset Events ({self.test_asset_id})",
            "GET",
            f"admin/registry/asset/{self.test_asset_id}/events",
            200,
            token=self.admin_token,
            check_fn=lambda d: 'items' in d and 'total' in d
        )
        if success:
            print(f"   Events: {data['total']} events")
            if data['items']:
                e = data['items'][0]
                print(f"   Latest: {e['event_type']} {e['delta_units']} units")
        return success, data

    def test_admin_snapshot(self):
        """Test POST /api/admin/registry/asset/{asset_id}/snapshot"""
        success, data = self.run_test(
            f"Admin Create Snapshot ({self.test_asset_id})",
            "POST",
            f"admin/registry/asset/{self.test_asset_id}/snapshot",
            200,
            token=self.admin_token,
            check_fn=lambda d: 'ok' in d and d['ok'] == True and 'snapshot' in d
        )
        if success:
            print(f"   Snapshot created: {data['snapshot']['id']}")
        return success, data

    def test_admin_recompute(self):
        """Test POST /api/admin/registry/asset/{asset_id}/recompute"""
        success, data = self.run_test(
            f"Admin Recompute ({self.test_asset_id})",
            "POST",
            f"admin/registry/asset/{self.test_asset_id}/recompute",
            200,
            token=self.admin_token,
            check_fn=lambda d: 'ok' in d and d['ok'] == True and 'result' in d
        )
        if success:
            print(f"   Recomputed: {data['result']['issued_units']} issued, {data['result']['holders']} holders")
        return success, data

    def test_investor_units(self):
        """Test GET /api/investor/units"""
        success, data = self.run_test(
            "Investor Units",
            "GET",
            "investor/units",
            200,
            token=self.investor_token,
            check_fn=lambda d: (
                'total_units' in d and
                'total_value_uah' in d and
                'holdings' in d
            )
        )
        if success:
            print(f"   Total units: {data['total_units']}")
            print(f"   Total value: {data['total_value_uah']} UAH")
            print(f"   Holdings: {len(data['holdings'])} assets")
            if data['holdings']:
                h = data['holdings'][0]
                print(f"   First holding: {h['asset_title']} - {h['units']} units ({h['percent']}%)")
        return success, data

    def test_investor_unit_events(self):
        """Test GET /api/investor/units/{asset_id}/events"""
        success, data = self.run_test(
            f"Investor Unit Events ({self.test_asset_id})",
            "GET",
            f"investor/units/{self.test_asset_id}/events",
            200,
            token=self.investor_token,
            check_fn=lambda d: 'items' in d and 'total' in d
        )
        if success:
            print(f"   Events: {data['total']} events for this investor")
        return success, data

    def test_secondary_conservation(self):
        """
        CRITICAL TEST: Perform a secondary trade and verify conservation
        1. Get initial invariants (must be all_ok=true)
        2. Get investor wallet balance
        3. Find a demo listing to buy
        4. Perform buy-now trade
        5. Verify invariants still all_ok=true
        6. Verify transfer events recorded (transfer_in/out pair)
        7. Verify units conserved at asset level
        """
        print("\n" + "="*80)
        print("🔥 CRITICAL TEST: Secondary Transfer Conservation")
        print("="*80)

        # Step 1: Get initial invariants
        print("\n📊 Step 1: Get initial invariants...")
        success, inv_before = self.run_test(
            "Invariants Before Trade",
            "GET",
            "admin/registry/invariants",
            200,
            token=self.admin_token
        )
        if not success or not inv_before.get('all_ok'):
            print("❌ CRITICAL: Invariants not OK before trade!")
            return False

        # Step 2: Get investor wallet
        print("\n💰 Step 2: Check investor wallet...")
        success, wallet_resp = self.run_test(
            "Investor Wallet",
            "GET",
            "investor/wallet",
            200,
            token=self.investor_token
        )
        if not success:
            print("❌ Failed to get wallet")
            return False
        wallet = wallet_resp.get('wallet', {})
        wallet_balance = wallet.get('settled_balance', 0)
        print(f"   Wallet balance: {wallet_balance} UAH")

        # Step 3: Find a demo listing
        print("\n🛒 Step 3: Find demo listing...")
        success, listings = self.run_test(
            "Public Listings",
            "GET",
            "secondary/listings",
            200
        )
        if not success or not listings.get('items'):
            print("❌ No listings available")
            return False
        
        # Find a small listing we can afford
        listing = None
        for l in listings['items']:
            remaining = l['units_uah'] - l.get('filled_units_uah', 0)
            # We can buy a portion of any listing, not the full amount
            if remaining > 0:
                listing = l
                break
        
        if not listing:
            print("❌ No affordable listing found")
            return False
        
        print(f"   Found listing: {listing['id']}")
        print(f"   Units: {listing['units_uah']} UAH @ {listing['price_per_unit']}")
        asset_id = listing['asset_id']

        # Get asset state before trade
        success, asset_before = self.run_test(
            "Asset Before Trade",
            "GET",
            f"admin/registry/asset/{asset_id}",
            200,
            token=self.admin_token
        )
        if not success:
            print("❌ Failed to get asset state")
            return False
        issued_before = asset_before['issued_units']
        print(f"   Asset issued units before: {issued_before}")

        # Step 4: Perform buy-now trade
        print("\n💸 Step 4: Perform buy-now trade...")
        # Buy a small affordable portion (10000 UAH worth)
        trade_amount = min(listing['units_uah'] - listing.get('filled_units_uah', 0), 10000)
        gross_cost = trade_amount * listing['price_per_unit']
        print(f"   Buying {trade_amount} UAH worth @ {listing['price_per_unit']} = {gross_cost:.2f} UAH total")
        
        if gross_cost > wallet_balance:
            print(f"❌ Cannot afford trade (need {gross_cost}, have {wallet_balance})")
            return False
        success, trade = self.run_test(
            "Buy Now Trade",
            "POST",
            "investor/secondary/bids",
            200,
            token=self.investor_token,
            data={
                "listing_id": listing['id'],
                "units_uah": trade_amount,
                "price_per_unit": None  # buy-now at listing price
            }
        )
        if not success:
            print("❌ Trade failed")
            return False
        
        trade_id = trade.get('trade', {}).get('id')
        print(f"   Trade completed: {trade_id}")
        print(f"   Amount: {trade_amount} UAH")

        # Step 5: Verify invariants still OK
        print("\n✅ Step 5: Verify invariants after trade...")
        success, inv_after = self.run_test(
            "Invariants After Trade",
            "GET",
            "admin/registry/invariants",
            200,
            token=self.admin_token
        )
        if not success:
            print("❌ Failed to get invariants after trade")
            return False
        
        if not inv_after.get('all_ok'):
            print("❌ CRITICAL: Invariants VIOLATED after trade!")
            return False
        print("   ✅ Invariants still OK")

        # Step 6: Verify transfer events recorded
        print("\n📝 Step 6: Verify transfer events...")
        success, events = self.run_test(
            "Asset Events After Trade",
            "GET",
            f"admin/registry/asset/{asset_id}/events?limit=10",
            200,
            token=self.admin_token
        )
        if not success:
            print("❌ Failed to get events")
            return False
        
        # Look for transfer_in and transfer_out events
        transfer_in = any(e['event_type'] == 'transfer_in' for e in events['items'][:5])
        transfer_out = any(e['event_type'] == 'transfer_out' for e in events['items'][:5])
        
        if not (transfer_in and transfer_out):
            print("❌ CRITICAL: Transfer events not recorded!")
            print(f"   transfer_in: {transfer_in}, transfer_out: {transfer_out}")
            return False
        print("   ✅ Transfer events recorded (transfer_in + transfer_out)")

        # Step 7: Verify units conserved
        print("\n🔒 Step 7: Verify units conserved...")
        success, asset_after = self.run_test(
            "Asset After Trade",
            "GET",
            f"admin/registry/asset/{asset_id}",
            200,
            token=self.admin_token
        )
        if not success:
            print("❌ Failed to get asset state after")
            return False
        
        issued_after = asset_after['issued_units']
        print(f"   Asset issued units after: {issued_after}")
        
        if issued_before != issued_after:
            print(f"❌ CRITICAL: Units NOT conserved! Before: {issued_before}, After: {issued_after}")
            return False
        print("   ✅ Units conserved (total issued unchanged)")

        print("\n" + "="*80)
        print("✅ SECONDARY TRANSFER CONSERVATION TEST PASSED")
        print("="*80)
        return True

    def run_all_tests(self):
        """Run all Phase A1 tests"""
        print("\n" + "="*80)
        print("LUMEN 2.0 / Phase A1 — Unit Registry & Ownership OS — Backend Test")
        print("="*80)

        # Login
        self.admin_token = self.login("admin@atlas.dev", "admin123", "Admin")
        if not self.admin_token:
            print("\n❌ Admin login failed, cannot continue")
            return 1

        self.investor_token = self.login("client@atlas.dev", "client123", "Investor")
        if not self.investor_token:
            print("\n❌ Investor login failed, cannot continue")
            return 1

        # Admin tests
        print("\n" + "="*80)
        print("ADMIN REGISTRY TESTS")
        print("="*80)
        self.test_admin_registry_summary()
        self.test_admin_invariants()
        self.test_admin_asset_detail()
        self.test_admin_asset_events()
        self.test_admin_snapshot()
        self.test_admin_recompute()

        # Investor tests
        print("\n" + "="*80)
        print("INVESTOR UNITS TESTS")
        print("="*80)
        self.test_investor_units()
        self.test_investor_unit_events()

        # Critical conservation test
        self.test_secondary_conservation()

        # Summary
        print("\n" + "="*80)
        print(f"📊 Tests passed: {self.tests_passed}/{self.tests_run}")
        print("="*80)
        
        return 0 if self.tests_passed == self.tests_run else 1

if __name__ == "__main__":
    tester = PhaseA1Tester()
    sys.exit(tester.run_all_tests())
