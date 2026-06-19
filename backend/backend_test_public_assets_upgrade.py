"""
Backend test for Public Assets Upgrade (Phase B):
- Search suggestions + validation
- Comprehensive sorting (yield, price/min_ticket, progress, newest)
- Pagination (6 default, +6 more)
- Capital Stack: real crypto vs fiat raised from confirmed pool contributions
- Asset detail Location: interactive Leaflet+OSM map with marker + route button
"""
import requests
import sys
from typing import Dict, Any

BASE_URL = "https://admin-logic-test-1.preview.emergentagent.com"

class PublicAssetsUpgradeTest:
    def __init__(self):
        self.base_url = BASE_URL
        self.tests_run = 0
        self.tests_passed = 0
        self.failures = []

    def log(self, msg: str, status: str = "info"):
        prefix = {
            "pass": "✅",
            "fail": "❌",
            "info": "🔍",
            "warn": "⚠️"
        }.get(status, "ℹ️")
        print(f"{prefix} {msg}")

    def test(self, name: str, condition: bool, details: str = ""):
        self.tests_run += 1
        if condition:
            self.tests_passed += 1
            self.log(f"PASS: {name}", "pass")
            if details:
                print(f"   └─ {details}")
        else:
            self.failures.append({"test": name, "details": details})
            self.log(f"FAIL: {name}", "fail")
            if details:
                print(f"   └─ {details}")

    def get(self, endpoint: str, params: Dict = None) -> Dict[str, Any]:
        """Make GET request and return JSON response."""
        url = f"{self.base_url}{endpoint}"
        try:
            resp = requests.get(url, params=params, timeout=10)
            self.log(f"GET {endpoint} → {resp.status_code}", "info")
            if resp.status_code == 200:
                return {"ok": True, "status": resp.status_code, "data": resp.json()}
            else:
                return {"ok": False, "status": resp.status_code, "error": resp.text[:200]}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def test_assets_list_total(self):
        """Test GET /api/assets?limit=60 returns total 15 assets (~12 with status 'open')."""
        self.log("\n=== TEST: Assets List Total ===", "info")
        
        result = self.get("/api/assets", params={"limit": 60})
        
        if not result.get("ok"):
            self.test("GET /api/assets?limit=60", False, f"Request failed: {result.get('error')}")
            return
        
        data = result.get("data", {})
        items = data if isinstance(data, list) else data.get("items", [])
        
        total = len(items)
        open_count = sum(1 for a in items if a.get("status") == "open")
        
        self.test(
            "Total assets count",
            total == 15,
            f"Expected 15 assets, got {total}"
        )
        
        self.test(
            "Open assets count",
            10 <= open_count <= 14,
            f"Expected ~12 open assets, got {open_count}"
        )
        
        # Check that assets have required fields for sorting/filtering
        if items:
            sample = items[0]
            has_fields = all(k in sample for k in ["id", "title", "category", "target_yield", "min_ticket"])
            self.test(
                "Assets have required fields",
                has_fields,
                f"Sample asset keys: {list(sample.keys())[:10]}"
            )

    def test_capital_stack_crypto_fiat_split(self):
        """Test GET /api/assets/asset-podilskyi/capital-stack returns crypto_raised>0, fiat_raised>0, NO 'debt' layer."""
        self.log("\n=== TEST: Capital Stack Crypto/Fiat Split ===", "info")
        
        result = self.get("/api/assets/asset-podilskyi/capital-stack")
        
        if not result.get("ok"):
            self.test("GET /api/assets/asset-podilskyi/capital-stack", False, f"Request failed: {result.get('error')}")
            return
        
        data = result.get("data", {})
        
        crypto_raised = data.get("crypto_raised", 0)
        fiat_raised = data.get("fiat_raised", 0)
        layers = data.get("layers", [])
        
        self.test(
            "crypto_raised > 0",
            crypto_raised > 0,
            f"crypto_raised = {crypto_raised}"
        )
        
        self.test(
            "fiat_raised > 0",
            fiat_raised > 0,
            f"fiat_raised = {fiat_raised}"
        )
        
        # Check that NO layer has key 'debt'
        layer_keys = [layer.get("key") for layer in layers]
        has_debt = "debt" in layer_keys
        
        self.test(
            "NO 'debt' layer in capital stack",
            not has_debt,
            f"Layer keys: {layer_keys}"
        )
        
        # Check that we have investors_crypto and investors_fiat layers
        has_crypto_layer = "investors_crypto" in layer_keys
        has_fiat_layer = "investors_fiat" in layer_keys
        
        self.test(
            "Has 'investors_crypto' layer",
            has_crypto_layer,
            f"Layer keys: {layer_keys}"
        )
        
        self.test(
            "Has 'investors_fiat' layer",
            has_fiat_layer,
            f"Layer keys: {layer_keys}"
        )
        
        # Verify layer structure
        if layers:
            sample_layer = layers[0]
            required_keys = ["key", "label", "amount", "percent", "color"]
            has_structure = all(k in sample_layer for k in required_keys)
            self.test(
                "Layers have correct structure",
                has_structure,
                f"Sample layer keys: {list(sample_layer.keys())}"
            )

    def test_intelligence_capital_stack(self):
        """Test GET /api/assets/asset-kharkiv-bc/intelligence has capital_stack with crypto/fiat split."""
        self.log("\n=== TEST: Intelligence Capital Stack ===", "info")
        
        result = self.get("/api/assets/asset-kharkiv-bc/intelligence")
        
        if not result.get("ok"):
            self.test("GET /api/assets/asset-kharkiv-bc/intelligence", False, f"Request failed: {result.get('error')}")
            return
        
        data = result.get("data", {})
        capital_stack = data.get("capital_stack", {})
        
        crypto_raised = capital_stack.get("crypto_raised", 0)
        fiat_raised = capital_stack.get("fiat_raised", 0)
        
        self.test(
            "Intelligence has capital_stack",
            bool(capital_stack),
            f"capital_stack keys: {list(capital_stack.keys())}"
        )
        
        self.test(
            "capital_stack.crypto_raised present",
            "crypto_raised" in capital_stack,
            f"crypto_raised = {crypto_raised}"
        )
        
        self.test(
            "capital_stack.fiat_raised present",
            "fiat_raised" in capital_stack,
            f"fiat_raised = {fiat_raised}"
        )
        
        # Check layers
        layers = capital_stack.get("layers", [])
        layer_keys = [layer.get("key") for layer in layers]
        
        self.test(
            "capital_stack has layers",
            len(layers) > 0,
            f"Found {len(layers)} layers: {layer_keys}"
        )

    def test_asset_geo_coordinates(self):
        """Test that assets have geo coordinates for map rendering."""
        self.log("\n=== TEST: Asset Geo Coordinates ===", "info")
        
        # Test a few known assets
        test_assets = ["asset-podilskyi", "asset-kharkiv-bc", "asset-dnipro-resi"]
        
        for asset_id in test_assets:
            result = self.get(f"/api/assets/{asset_id}/intelligence")
            
            if not result.get("ok"):
                self.test(f"GET /api/assets/{asset_id}/intelligence", False, f"Request failed")
                continue
            
            # Check if we can get the full asset detail via public marketplace
            marketplace_result = self.get(f"/public/marketplace/{asset_id}")
            
            if marketplace_result.get("ok"):
                data = marketplace_result.get("data", {})
                sections = data.get("sections", {})
                map_data = sections.get("map", {})
                
                has_coords = map_data.get("lat") is not None and map_data.get("lng") is not None
                
                self.test(
                    f"Asset {asset_id} has geo coordinates",
                    has_coords,
                    f"lat={map_data.get('lat')}, lng={map_data.get('lng')}"
                )

    def test_sorting_fields_present(self):
        """Test that assets have all fields needed for sorting."""
        self.log("\n=== TEST: Sorting Fields Present ===", "info")
        
        result = self.get("/api/assets", params={"limit": 60})
        
        if not result.get("ok"):
            self.test("GET /api/assets", False, "Request failed")
            return
        
        data = result.get("data", {})
        items = data if isinstance(data, list) else data.get("items", [])
        
        if not items:
            self.test("Assets list not empty", False, "No assets returned")
            return
        
        # Check first few assets for required sorting fields
        required_fields = ["target_yield", "min_ticket", "created_at", "featured"]
        
        for i, asset in enumerate(items[:3]):
            asset_id = asset.get("id", f"asset-{i}")
            
            for field in required_fields:
                has_field = field in asset
                self.test(
                    f"Asset {asset_id} has '{field}' field",
                    has_field,
                    f"Value: {asset.get(field)}"
                )
            
            # Check progress calculation fields
            has_progress_fields = ("progress_percent" in asset) or (
                ("round_target" in asset or "target_amount" in asset) and
                ("raised" in asset or "raised_amount" in asset)
            )
            
            self.test(
                f"Asset {asset_id} has progress fields",
                has_progress_fields,
                f"progress_percent={asset.get('progress_percent')}, target={asset.get('round_target')}, raised={asset.get('raised')}"
            )

    def run_all_tests(self):
        """Run all backend tests."""
        self.log("\n" + "="*60, "info")
        self.log("PUBLIC ASSETS UPGRADE - BACKEND TESTS", "info")
        self.log("="*60 + "\n", "info")
        
        self.test_assets_list_total()
        self.test_capital_stack_crypto_fiat_split()
        self.test_intelligence_capital_stack()
        self.test_asset_geo_coordinates()
        self.test_sorting_fields_present()
        
        # Summary
        self.log("\n" + "="*60, "info")
        self.log(f"TESTS COMPLETED: {self.tests_passed}/{self.tests_run} passed", "info")
        self.log("="*60 + "\n", "info")
        
        if self.failures:
            self.log("FAILURES:", "fail")
            for failure in self.failures:
                self.log(f"  • {failure['test']}", "fail")
                if failure['details']:
                    print(f"    └─ {failure['details']}")
        
        return 0 if self.tests_passed == self.tests_run else 1


def main():
    tester = PublicAssetsUpgradeTest()
    return tester.run_all_tests()


if __name__ == "__main__":
    sys.exit(main())
