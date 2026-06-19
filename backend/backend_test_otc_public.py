"""
OTC Public Marketplace Backend Test
====================================
Tests the new standalone public OTC marketplace APIs:
  - GET /api/public/otc/listings (active lots)
  - GET /api/public/otc/listings/{id} (lot detail with payout history)
  - POST /api/public/otc/reserve (guest reservation with wallet/internal)
  - POST /api/investor/otc/claim (authenticated claim)
  - GET /api/investor/otc/reservations (authenticated reservations)
"""
import requests
import sys
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://expo-dev-deploy.preview.emergentagent.com')

class OtcPublicTester:
    def __init__(self):
        self.base = BASE_URL
        self.tests_run = 0
        self.tests_passed = 0
        self.session = requests.Session()
        self.demo_cookie = None
        
    def log(self, msg, status='info'):
        prefix = {'info': '🔍', 'pass': '✅', 'fail': '❌', 'warn': '⚠️'}
        print(f"{prefix.get(status, '•')} {msg}")
    
    def test(self, name, method, endpoint, expected_status, data=None, headers=None, cookies=None):
        """Run a single API test"""
        url = f"{self.base}{endpoint}"
        self.tests_run += 1
        self.log(f"Testing {name}...", 'info')
        
        try:
            h = headers or {}
            c = cookies or {}
            if method == 'GET':
                resp = self.session.get(url, headers=h, cookies=c, timeout=10)
            elif method == 'POST':
                h.setdefault('Content-Type', 'application/json')
                resp = self.session.post(url, json=data, headers=h, cookies=c, timeout=10)
            elif method == 'DELETE':
                resp = self.session.delete(url, headers=h, cookies=c, timeout=10)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            success = resp.status_code == expected_status
            if success:
                self.tests_passed += 1
                self.log(f"PASSED - Status: {resp.status_code}", 'pass')
                try:
                    return True, resp.json()
                except:
                    return True, {}
            else:
                self.log(f"FAILED - Expected {expected_status}, got {resp.status_code}", 'fail')
                try:
                    self.log(f"Response: {resp.text[:200]}", 'warn')
                except:
                    pass
                return False, {}
        except Exception as e:
            self.log(f"FAILED - Error: {str(e)}", 'fail')
            return False, {}
    
    def demo_auth(self):
        """Authenticate via POST /api/auth/demo to get session cookie"""
        self.log("Authenticating via demo auth...", 'info')
        success, data = self.test(
            "Demo Auth",
            "POST",
            "/api/auth/demo",
            200,
            data={}
        )
        if success:
            # Session cookie should be set automatically by requests.Session
            self.log("Demo auth successful - session cookie set", 'pass')
            return True
        else:
            self.log("Demo auth failed - cannot proceed with authenticated tests", 'fail')
            return False
    
    def run_all(self):
        """Run all OTC public marketplace tests"""
        self.log("=" * 60, 'info')
        self.log("OTC PUBLIC MARKETPLACE BACKEND TEST", 'info')
        self.log("=" * 60, 'info')
        
        # ── 1. Test public listings endpoint ──
        self.log("\n[1] Testing GET /api/public/otc/listings", 'info')
        success, listings_data = self.test(
            "Get public OTC listings",
            "GET",
            "/api/public/otc/listings",
            200
        )
        
        listings = listings_data.get('listings', [])
        if success:
            self.log(f"Found {len(listings)} active listings", 'info')
            if len(listings) == 0:
                self.log("WARNING: No active listings found - some tests may be skipped", 'warn')
        
        # ── 2. Test listing detail endpoint ──
        listing_id = None
        if listings:
            listing_id = listings[0].get('id')
            self.log(f"\n[2] Testing GET /api/public/otc/listings/{listing_id}", 'info')
            success, detail_data = self.test(
                "Get listing detail",
                "GET",
                f"/api/public/otc/listings/{listing_id}",
                200
            )
            
            if success:
                listing = detail_data.get('listing', {})
                # Check for required fields
                has_asset = 'asset' in listing
                has_metrics = 'metrics' in listing
                has_payout_history = 'payout_history' in listing
                
                self.log(f"Listing has asset: {has_asset}", 'pass' if has_asset else 'fail')
                self.log(f"Listing has metrics: {has_metrics}", 'pass' if has_metrics else 'fail')
                self.log(f"Listing has payout_history: {has_payout_history}", 'pass' if has_payout_history else 'fail')
                
                if has_payout_history:
                    payout_count = len(listing.get('payout_history', []))
                    self.log(f"Payout history entries: {payout_count}", 'info')
        else:
            self.log("\n[2] SKIPPED - No listings available for detail test", 'warn')
        
        # ── 3. Test guest reservation with wallet ──
        claim_token = None
        reservation_id = None
        if listing_id:
            self.log("\n[3] Testing POST /api/public/otc/reserve (wallet method)", 'info')
            success, reserve_data = self.test(
                "Reserve listing as guest with wallet",
                "POST",
                "/api/public/otc/reserve",
                200,
                data={
                    "listing_id": listing_id,
                    "payment_method": "wallet",
                    "wallet_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
                    "email": "test@example.com",
                    "name": "Test User"
                }
            )
            
            if success:
                claim_token = reserve_data.get('claim_token')
                reservation_id = reserve_data.get('reservation_id')
                payment_method = reserve_data.get('payment_method')
                
                self.log(f"Reservation ID: {reservation_id}", 'info')
                self.log(f"Claim token: {claim_token[:20]}..." if claim_token else "No claim token", 'info')
                self.log(f"Payment method: {payment_method}", 'info')
                
                if not claim_token:
                    self.log("ERROR: No claim_token returned", 'fail')
        else:
            self.log("\n[3] SKIPPED - No listing available for reservation test", 'warn')
        
        # ── 4. Test guest reservation with internal (should work but require auth later) ──
        if listing_id:
            self.log("\n[4] Testing POST /api/public/otc/reserve (internal method)", 'info')
            success, reserve_data = self.test(
                "Reserve listing as guest with internal payment",
                "POST",
                "/api/public/otc/reserve",
                200,
                data={
                    "listing_id": listing_id,
                    "payment_method": "internal",
                    "email": "test2@example.com",
                    "name": "Test User 2"
                }
            )
            
            if success:
                internal_claim_token = reserve_data.get('claim_token')
                self.log(f"Internal reservation claim token: {internal_claim_token[:20]}..." if internal_claim_token else "No token", 'info')
        else:
            self.log("\n[4] SKIPPED - No listing available", 'warn')
        
        # ── 5. Test demo authentication ──
        self.log("\n[5] Testing POST /api/auth/demo", 'info')
        auth_success = self.demo_auth()
        
        if not auth_success:
            self.log("Cannot proceed with authenticated tests", 'fail')
            self.print_summary()
            return 1
        
        # ── 6. Test claim reservation (authenticated) ──
        if claim_token:
            self.log("\n[6] Testing POST /api/investor/otc/claim", 'info')
            success, claim_data = self.test(
                "Claim reservation as authenticated user",
                "POST",
                "/api/investor/otc/claim",
                200,
                data={"claim_token": claim_token}
            )
            
            if success:
                reservation = claim_data.get('reservation', {})
                status = reservation.get('status')
                user_id = reservation.get('user_id')
                
                self.log(f"Claimed reservation status: {status}", 'pass' if status == 'claimed' else 'fail')
                self.log(f"Reservation user_id: {user_id}", 'info')
        else:
            self.log("\n[6] SKIPPED - No claim token available", 'warn')
        
        # ── 7. Test get reservations (authenticated) ──
        self.log("\n[7] Testing GET /api/investor/otc/reservations", 'info')
        success, reservations_data = self.test(
            "Get user reservations",
            "GET",
            "/api/investor/otc/reservations",
            200
        )
        
        if success:
            reservations = reservations_data.get('reservations', [])
            self.log(f"Found {len(reservations)} reservations for authenticated user", 'info')
            
            if reservations:
                for i, res in enumerate(reservations[:3]):  # Show first 3
                    self.log(f"  Reservation {i+1}: status={res.get('status')}, payment_method={res.get('payment_method')}", 'info')
        
        # ── 8. Test invalid scenarios ──
        self.log("\n[8] Testing error scenarios", 'info')
        
        # Invalid listing ID
        self.test(
            "Get non-existent listing (should 404)",
            "GET",
            "/api/public/otc/listings/invalid-id-12345",
            404
        )
        
        # Reserve without wallet_address when method=wallet
        self.test(
            "Reserve with wallet method but no address (should 400)",
            "POST",
            "/api/public/otc/reserve",
            400,
            data={
                "listing_id": listing_id or "any-id",
                "payment_method": "wallet"
            }
        )
        
        # Invalid payment method
        self.test(
            "Reserve with invalid payment method (should 400)",
            "POST",
            "/api/public/otc/reserve",
            400,
            data={
                "listing_id": listing_id or "any-id",
                "payment_method": "invalid_method"
            }
        )
        
        # Claim with invalid token
        self.test(
            "Claim with invalid token (should 404)",
            "POST",
            "/api/investor/otc/claim",
            404,
            data={"claim_token": "invalid-token-12345"}
        )
        
        self.print_summary()
        return 0 if self.tests_passed == self.tests_run else 1
    
    def print_summary(self):
        """Print test summary"""
        self.log("\n" + "=" * 60, 'info')
        self.log(f"TESTS PASSED: {self.tests_passed}/{self.tests_run}", 'pass' if self.tests_passed == self.tests_run else 'fail')
        self.log("=" * 60, 'info')
        
        if self.tests_passed == self.tests_run:
            self.log("✨ All OTC public marketplace tests passed!", 'pass')
        else:
            self.log(f"⚠️  {self.tests_run - self.tests_passed} test(s) failed", 'fail')

def main():
    tester = OtcPublicTester()
    return tester.run_all()

if __name__ == "__main__":
    sys.exit(main())
