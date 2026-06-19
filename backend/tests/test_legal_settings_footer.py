"""
Tests for the Legal Settings + Cookie Consent module.
Covers:
  • Public reads: /api/public/legal-settings, /api/public/legal-document/{kind}
  • Cookie consent POST + validation
  • Admin RBAC (401/403/200) for /api/admin/legal-settings
  • Admin update + persistence via subsequent GET
  • Validation on unsupported social / unsupported legal doc
  • Admin /api/admin/cookie-consents/stats
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests


BASE_URL = "http://localhost:8001"
LOGIN = f"{BASE_URL}/api/auth/login"
ADMIN = {"email": "admin@atlas.dev", "password": "admin123"}
CLIENT = {"email": "client@atlas.dev", "password": "client123"}


def _login_session(creds):
    s = requests.Session()
    r = s.post(LOGIN, json=creds, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    assert "session_token" in s.cookies, f"no session_token cookie set: {dict(s.cookies)}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login_session(ADMIN)


@pytest.fixture(scope="module")
def client_session():
    return _login_session(CLIENT)


# ── Public endpoints ────────────────────────────────────────────────────────

class TestPublicEndpoints:
    def test_public_legal_settings(self):
        r = requests.get(f"{BASE_URL}/api/public/legal-settings", timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "socials" in data and isinstance(data["socials"], list)
        assert "legal" in data and isinstance(data["legal"], list)
        kinds = {entry.get("kind") for entry in data["legal"]}
        assert {"terms", "privacy", "cookies"} <= kinds

    @pytest.mark.parametrize("kind", ["terms", "privacy", "cookies"])
    def test_public_legal_document_known(self, kind):
        r = requests.get(f"{BASE_URL}/api/public/legal-document/{kind}", timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["kind"] == kind
        assert isinstance(data.get("title"), str) and data["title"]
        assert isinstance(data.get("body"), str) and len(data["body"]) > 0

    def test_public_legal_document_unknown_returns_404(self):
        r = requests.get(f"{BASE_URL}/api/public/legal-document/sla", timeout=10)
        assert r.status_code == 404


# ── Cookie consent ──────────────────────────────────────────────────────────

class TestCookieConsent:
    @pytest.mark.parametrize("choice", ["all", "essential", "rejected"])
    def test_consent_accepts_valid_choices(self, choice):
        r = requests.post(
            f"{BASE_URL}/api/cookie-consent",
            json={"choice": choice, "categories": ["essential"]},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        # fingerprint should be hashed (16 hex chars), never raw IP/UA
        fp = data.get("fingerprint")
        assert isinstance(fp, str) and len(fp) == 16
        assert all(c in "0123456789abcdef" for c in fp)
        assert "at" in data

    def test_consent_rejects_invalid_choice(self):
        r = requests.post(
            f"{BASE_URL}/api/cookie-consent",
            json={"choice": "foobar"},
            timeout=10,
        )
        assert r.status_code == 422


# ── Admin RBAC ──────────────────────────────────────────────────────────────

class TestAdminRBAC:
    def test_admin_legal_settings_unauthenticated_401(self):
        r = requests.get(f"{BASE_URL}/api/admin/legal-settings", timeout=10)
        # Accept 401 or 403 depending on dependency wiring
        assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"

    def test_admin_legal_settings_client_forbidden(self, client_session):
        r = requests.get(f"{BASE_URL}/api/admin/legal-settings", cookies=client_session.cookies.get_dict(), timeout=10)
        assert r.status_code == 403, r.text

    def test_admin_legal_settings_admin_ok(self, admin_session):
        r = requests.get(f"{BASE_URL}/api/admin/legal-settings", cookies=admin_session.cookies.get_dict(), timeout=10)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc.get("key") == "default"
        assert "socials" in doc and "legal" in doc
        for k in ["telegram", "tiktok", "instagram", "youtube", "facebook", "github"]:
            assert k in doc["socials"]
        for k in ["terms", "privacy", "cookies"]:
            assert k in doc["legal"]


# ── Admin updates ───────────────────────────────────────────────────────────

class TestAdminUpdates:
    def test_update_socials_persists_to_public(self, admin_session):
        unique_url = f"https://t.me/test_{uuid.uuid4().hex[:6]}"
        payload = {
            "socials": {
                "telegram":  {"url": unique_url, "enabled": True},
                "instagram": {"url": "https://instagram.com/atlas_eva", "enabled": True},
                "github":    {"url": "https://github.com/atlas-evax", "enabled": True},
                "facebook":  {"url": "", "enabled": False},
            }
        }
        r = requests.put(
            f"{BASE_URL}/api/admin/legal-settings",
            cookies=admin_session.cookies.get_dict(),
            json=payload,
            timeout=10,
        )
        assert r.status_code == 200, r.text
        # Verify via public GET
        r2 = requests.get(f"{BASE_URL}/api/public/legal-settings", timeout=10)
        assert r2.status_code == 200
        socials = r2.json()["socials"]
        keys = {s["key"]: s["url"] for s in socials}
        assert keys.get("telegram") == unique_url
        assert keys.get("github") == "https://github.com/atlas-evax"
        assert "facebook" not in keys  # disabled or empty URL filtered

    def test_update_unknown_social_returns_400(self, admin_session):
        r = requests.put(
            f"{BASE_URL}/api/admin/legal-settings",
            cookies=admin_session.cookies.get_dict(),
            json={"socials": {"twitter": {"url": "https://x.com/atlas", "enabled": True}}},
            timeout=10,
        )
        assert r.status_code == 400, r.text

    def test_update_unknown_legal_doc_returns_400(self, admin_session):
        r = requests.put(
            f"{BASE_URL}/api/admin/legal-settings",
            cookies=admin_session.cookies.get_dict(),
            json={"legal": {"sla": {"title": "SLA", "body": "..."}}},
            timeout=10,
        )
        assert r.status_code == 400, r.text

    def test_update_legal_terms_persists(self, admin_session):
        unique_title = f"TEST Terms {uuid.uuid4().hex[:6]}"
        unique_body = f"Test body lorem ipsum {uuid.uuid4().hex[:8]}"
        r = requests.put(
            f"{BASE_URL}/api/admin/legal-settings",
            cookies=admin_session.cookies.get_dict(),
            json={"legal": {"terms": {"title": unique_title, "body": unique_body}}},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        # Verify via public document GET
        r2 = requests.get(f"{BASE_URL}/api/public/legal-document/terms", timeout=10)
        assert r2.status_code == 200
        doc = r2.json()
        assert doc["title"] == unique_title
        assert doc["body"] == unique_body


# ── Admin stats ─────────────────────────────────────────────────────────────

class TestAdminStats:
    def test_consent_stats(self, admin_session):
        # Post a known consent first to ensure non-empty
        requests.post(f"{BASE_URL}/api/cookie-consent", json={"choice": "all"}, timeout=10)
        r = requests.get(f"{BASE_URL}/api/admin/cookie-consents/stats", cookies=admin_session.cookies.get_dict(), timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "total" in data and isinstance(data["total"], int)
        assert "by_choice" in data
        assert set(data["by_choice"].keys()) >= {"all", "essential", "rejected"}
        assert "computed_at" in data
