"""Backend tests for unified Manager (manager+operator merged) cabinet."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://code-review-hub-98.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def manager_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/quick", json={"email": "manager@atlas.dev"}, timeout=15)
    assert r.status_code == 200, f"quick login failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def manager_password_session():
    s = requests.Session()
    # Try common login endpoints
    for path in ["/api/auth/login", "/api/auth/password", "/api/auth/sign-in"]:
        r = s.post(f"{BASE_URL}{path}", json={"email": "manager@atlas.dev", "password": "manager123"}, timeout=15)
        if r.status_code == 200:
            return s
    pytest.skip("No password login endpoint accepting manager creds (200) - documented")


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/quick", json={"email": "admin@devos.io"}, timeout=15)
    if r.status_code != 200:
        r = s.post(f"{BASE_URL}/api/auth/quick", json={"email": "admin@atlas.dev"}, timeout=15)
    assert r.status_code == 200, f"admin quick login failed: {r.status_code}"
    return s


# IR (admin/ir) endpoints — now staff-gated, manager must access
IR_ENDPOINTS = [
    "/api/admin/ir/overview",
    "/api/admin/ir/leads",
    "/api/admin/ir/pipeline",
    "/api/admin/managers",
]


@pytest.mark.parametrize("path", IR_ENDPOINTS)
def test_manager_can_access_ir(manager_session, path):
    r = manager_session.get(f"{BASE_URL}{path}", timeout=15)
    assert r.status_code == 200, f"{path} returned {r.status_code}: {r.text[:200]}"


# Operator endpoints — manager linked to Podil operator
OPERATOR_ENDPOINTS = [
    "/api/operator/me",
    "/api/operator/dashboard",
    "/api/operator/assets",
    "/api/operator/reports",
    "/api/operator/sla",
    "/api/operator/fees",
    "/api/operator/investors",
]


@pytest.mark.parametrize("path", OPERATOR_ENDPOINTS)
def test_manager_can_access_operator(manager_session, path):
    r = manager_session.get(f"{BASE_URL}{path}", timeout=15)
    assert r.status_code == 200, f"{path} returned {r.status_code}: {r.text[:200]}"


def test_manager_quick_login_user_payload(manager_session):
    r = manager_session.get(f"{BASE_URL}/api/auth/me", timeout=15)
    if r.status_code == 404:
        pytest.skip("/api/auth/me not present")
    assert r.status_code == 200
    data = r.json()
    # Validate role contains manager
    role = data.get("role") or (data.get("user") or {}).get("role")
    assert role in ("manager", "admin"), f"unexpected role: {role}"


def test_admin_can_still_access_ir(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/admin/ir/overview", timeout=15)
    assert r.status_code == 200
