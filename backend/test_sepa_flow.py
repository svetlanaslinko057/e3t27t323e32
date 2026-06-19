"""
Test SEPA transfer flow after rate-limit window reset
"""
import requests
import time

BACKEND_URL = "https://arch-review-26.preview.emergentagent.com"
ADMIN_EMAIL = "admin@devos.io"
ADMIN_PASSWORD = "admin123"

def test_sepa_flow():
    session = requests.Session()
    
    # Login
    print("1. Logging in as admin...")
    response = session.post(
        f"{BACKEND_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30
    )
    print(f"   Login status: {response.status_code}")
    
    if response.status_code != 200:
        print("   ❌ Login failed")
        return False
    
    # Create SEPA transfer
    print("\n2. Creating SEPA transfer...")
    unique_ref = f"TEST-SEPA-{int(time.time())}"
    response = session.post(
        f"{BACKEND_URL}/api/lumen/institutional/rails/sepa/transfers",
        json={
            "direction": "inbound",
            "amount": 50000,
            "currency": "EUR",
            "beneficiary_name": "Test SPV",
            "beneficiary_iban": "DE89370400440532013000",
            "reference": unique_ref
        },
        timeout=30
    )
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 429:
        print("   ⚠ Still rate-limited, need to wait more")
        return False
    
    if response.status_code != 200:
        print(f"   ❌ Failed: {response.text[:200]}")
        return False
    
    data = response.json()
    transfer_id = data.get('id')
    print(f"   ✅ Transfer created: {transfer_id}")
    print(f"   Status: {data.get('status')}")
    print(f"   Rail: {data.get('rail')}")
    
    # Confirm transfer
    print(f"\n3. Confirming transfer {transfer_id}...")
    response = session.post(
        f"{BACKEND_URL}/api/admin/lumen/institutional/rails/transfers/{transfer_id}/confirm",
        json={"provider_ref": "BANK-STMT-001"},
        timeout=30
    )
    print(f"   Status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"   ❌ Failed: {response.text[:200]}")
        return False
    
    data = response.json()
    print(f"   ✅ Transfer confirmed")
    print(f"   Status: {data.get('status')}")
    print(f"   Settled at: {data.get('transfer', {}).get('settled_at')}")
    
    # Reconcile transfer
    print(f"\n4. Reconciling transfer {transfer_id}...")
    response = session.post(
        f"{BACKEND_URL}/api/admin/lumen/institutional/rails/transfers/{transfer_id}/reconcile",
        json={
            "bank_statement_ref": "STMT-001",
            "amount_observed": 50000,
            "currency_observed": "EUR"
        },
        timeout=30
    )
    print(f"   Status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"   ❌ Failed: {response.text[:200]}")
        return False
    
    data = response.json()
    recon = data.get('reconciliation', {})
    print(f"   ✅ Transfer reconciled")
    print(f"   Matched: {recon.get('matched')}")
    print(f"   Delta: {recon.get('delta_amount')}")
    
    # Test duplicate reference
    print(f"\n5. Testing duplicate reference (should fail with 409)...")
    response = session.post(
        f"{BACKEND_URL}/api/lumen/institutional/rails/sepa/transfers",
        json={
            "direction": "inbound",
            "amount": 50000,
            "currency": "EUR",
            "beneficiary_name": "Test SPV",
            "beneficiary_iban": "DE89370400440532013000",
            "reference": unique_ref
        },
        timeout=30
    )
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 409:
        print(f"   ✅ Duplicate reference rejected correctly")
    else:
        print(f"   ❌ Expected 409, got {response.status_code}")
        return False
    
    # Test USD currency (should fail with 400)
    print(f"\n6. Testing USD currency (should fail with 400)...")
    response = session.post(
        f"{BACKEND_URL}/api/lumen/institutional/rails/sepa/transfers",
        json={
            "direction": "inbound",
            "amount": 50000,
            "currency": "USD",
            "beneficiary_name": "Test SPV",
            "beneficiary_iban": "DE89370400440532013000",
            "reference": f"TEST-SEPA-USD-{int(time.time())}"
        },
        timeout=30
    )
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 400:
        print(f"   ✅ USD currency rejected correctly")
    else:
        print(f"   ❌ Expected 400, got {response.status_code}")
        return False
    
    # Test amount below minimum (should fail with 400)
    print(f"\n7. Testing amount below minimum (should fail with 400)...")
    response = session.post(
        f"{BACKEND_URL}/api/lumen/institutional/rails/sepa/transfers",
        json={
            "direction": "inbound",
            "amount": 50,
            "currency": "EUR",
            "beneficiary_name": "Test SPV",
            "beneficiary_iban": "DE89370400440532013000",
            "reference": f"TEST-SEPA-MIN-{int(time.time())}"
        },
        timeout=30
    )
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 400:
        print(f"   ✅ Amount below minimum rejected correctly")
    else:
        print(f"   ❌ Expected 400, got {response.status_code}")
        return False
    
    print("\n✅ All SEPA transfer flow tests passed!")
    return True

if __name__ == "__main__":
    success = test_sepa_flow()
    exit(0 if success else 1)
