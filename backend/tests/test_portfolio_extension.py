"""
Backend tests for the extended Portfolio feature.

Covers:
- Public list/detail/featured endpoints
- Lead-capture inquiry endpoint (validation + 3 intents + null case_id)
- Admin inquiry list/filter/patch/delete (ROUTING FIX: must not be shadowed by /{case_id})
- Admin case GET/PATCH still work after routing reorder
- Auth gating for public vs admin endpoints
"""
import os
import pytest
import requests

BASE_URL = "http://localhost:8001"
ADMIN_EMAIL = "admin@atlas.dev"
ADMIN_PASSWORD = "admin123"
CLIENT_EMAIL = "client@atlas.dev"
CLIENT_PASSWORD = "client123"


# ---------- fixtures ----------

def _login(email, password):
    """Login and return a session that forwards the session_token cookie
    even over plain HTTP (the backend issues Secure cookies which `requests`
    refuses to re-send over http://). We grab the raw Set-Cookie token and
    register it via cookies.set() without the Secure flag.
    """
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        return None, r
    raw = r.headers.get("set-cookie", "")
    token = None
    for part in raw.split(";"):
        part = part.strip()
        if part.startswith("session_token="):
            token = part.split("=", 1)[1]
            break
    if token:
        s.cookies.set("session_token", token)
    return s, r


@pytest.fixture(scope="session")
def admin_session():
    s, r = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    assert s is not None, f"Admin login failed: {r.status_code} {r.text}"
    # sanity: /me must return admin
    me = s.get(f"{BASE_URL}/api/auth/me")
    assert me.status_code == 200, f"/auth/me failed after login: {me.status_code} {me.text}"
    return s


@pytest.fixture(scope="session")
def client_session():
    s, r = _login(CLIENT_EMAIL, CLIENT_PASSWORD)
    if s is None:
        pytest.skip(f"Client login failed: {r.status_code}")
    return s


@pytest.fixture(scope="session")
def cases(admin_session):
    """Fetch all cases via admin endpoint (includes unpublished too)."""
    r = admin_session.get(f"{BASE_URL}/api/admin/portfolio")
    assert r.status_code == 200
    return r.json()


# ---------- public listing & detail ----------

class TestPublicCases:
    def test_list_cases_returns_array_with_enriched_fields(self):
        r = requests.get(f"{BASE_URL}/api/portfolio/cases")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1, "Expected at least 1 published portfolio case"
        # validate enrichment on at least one case
        enriched = [
            c for c in data
            if c.get("case_study") and c.get("hours_spent") and c.get("team_size")
            and c.get("tags") and c.get("starting_from")
        ]
        assert len(enriched) >= 1, (
            f"Expected at least one case with full deep-case enrichment. "
            f"Got: { [(c.get('title'), c.get('case_study') and len(c['case_study']), c.get('hours_spent'), c.get('team_size'), c.get('tags'), c.get('starting_from')) for c in data] }"
        )

    def test_list_cases_count_is_five(self):
        """The seed should have ~5 demo cases; soft check."""
        r = requests.get(f"{BASE_URL}/api/portfolio/cases")
        assert r.status_code == 200
        data = r.json()
        # at minimum 5 — flag if less
        assert len(data) == 5, f"Expected 5 seeded cases, got {len(data)}"

    def test_get_case_detail_returns_all_deep_fields(self):
        r_list = requests.get(f"{BASE_URL}/api/portfolio/cases")
        assert r_list.status_code == 200
        case_id = r_list.json()[0]["case_id"]

        r = requests.get(f"{BASE_URL}/api/portfolio/cases/{case_id}")
        assert r.status_code == 200
        doc = r.json()
        # all extended keys must be present in response model
        for key in [
            "gallery", "external_url", "case_study", "hours_spent",
            "team_size", "start_date", "end_date", "tags",
            "challenge", "solution", "cta_headline", "starting_from",
        ]:
            assert key in doc, f"Missing deep field: {key}"

    def test_get_case_detail_404_for_invalid_id(self):
        r = requests.get(f"{BASE_URL}/api/portfolio/cases/does_not_exist_xyz")
        assert r.status_code == 404

    def test_featured_endpoint_returns_only_featured(self):
        r = requests.get(f"{BASE_URL}/api/portfolio/featured")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        for c in data:
            assert c.get("featured") is True
            assert c.get("published") is True


# ---------- inquiry creation (public) ----------

class TestInquiryCreate:
    @pytest.mark.parametrize("intent", ["order_similar", "consultation", "calculate"])
    def test_create_inquiry_each_intent(self, intent):
        payload = {
            "intent": intent,
            "full_name": "TEST_Inquiry User",
            "email": f"TEST_{intent}@example.com",
            "message": f"Hi, I'd like to {intent}.",
            "phone": "+1234567890",
            "company": "TEST Corp",
            "budget_range": "15-50k",
            "timeline": "1-3m",
        }
        r = requests.post(f"{BASE_URL}/api/portfolio/inquiry", json=payload)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["inquiry_id"].startswith("inq_")
        assert doc["status"] == "new"
        assert doc["intent"] == intent
        assert doc["email"] == payload["email"].lower()
        assert "created_at" in doc

    def test_inquiry_missing_required_rejected(self):
        # missing full_name
        r = requests.post(f"{BASE_URL}/api/portfolio/inquiry", json={
            "intent": "consultation",
            "email": "x@y.com",
            "message": "hi"
        })
        assert r.status_code in (400, 422), f"Expected 400/422 for missing full_name, got {r.status_code}"

        # missing email
        r = requests.post(f"{BASE_URL}/api/portfolio/inquiry", json={
            "intent": "consultation",
            "full_name": "x",
            "message": "hi"
        })
        assert r.status_code in (400, 422)

        # missing message
        r = requests.post(f"{BASE_URL}/api/portfolio/inquiry", json={
            "intent": "consultation",
            "full_name": "x",
            "email": "x@y.com"
        })
        assert r.status_code in (400, 422)

    def test_inquiry_invalid_intent_rejected(self):
        """Spec: invalid intent should reject with 400.
        NOTE: current backend silently coerces invalid intent → 'order_similar'.
        """
        r = requests.post(f"{BASE_URL}/api/portfolio/inquiry", json={
            "intent": "bogus_intent",
            "full_name": "TEST_user",
            "email": "test@example.com",
            "message": "hello",
        })
        assert r.status_code == 400, (
            f"Expected 400 rejection for invalid intent. "
            f"Got status={r.status_code}, body={r.text}"
        )

    def test_inquiry_with_null_case_id(self):
        r = requests.post(f"{BASE_URL}/api/portfolio/inquiry", json={
            "case_id": None,
            "intent": "consultation",
            "full_name": "TEST_GeneralInquiry",
            "email": "test_general@example.com",
            "message": "general inquiry",
        })
        assert r.status_code == 200
        doc = r.json()
        assert doc["case_id"] is None
        assert doc["case_title"] is None

    def test_inquiry_public_no_auth_required(self):
        """Public surface must work with NO cookies/headers."""
        s = requests.Session()  # no auth
        r = s.post(f"{BASE_URL}/api/portfolio/inquiry", json={
            "intent": "consultation",
            "full_name": "TEST_NoAuth",
            "email": "noauth@example.com",
            "message": "anonymous lead",
        })
        assert r.status_code == 200


# ---------- admin inquiries (ROUTING FIX) ----------

class TestAdminInquiries:
    def test_list_inquiries_not_404(self, admin_session):
        """REGRESSION: /api/admin/portfolio/inquiries used to be shadowed by /{case_id}."""
        r = admin_session.get(f"{BASE_URL}/api/admin/portfolio/inquiries")
        assert r.status_code == 200, (
            f"Routing bug regression — inquiries endpoint returned {r.status_code}. "
            f"Body: {r.text[:200]}"
        )
        data = r.json()
        assert isinstance(data, list)

    def test_list_inquiries_latest_first(self, admin_session):
        # create two with known order
        r1 = requests.post(f"{BASE_URL}/api/portfolio/inquiry", json={
            "intent": "consultation",
            "full_name": "TEST_OrderA",
            "email": "ordera@example.com",
            "message": "first",
        })
        r2 = requests.post(f"{BASE_URL}/api/portfolio/inquiry", json={
            "intent": "consultation",
            "full_name": "TEST_OrderB",
            "email": "orderb@example.com",
            "message": "second",
        })
        assert r1.status_code == 200 and r2.status_code == 200
        id2 = r2.json()["inquiry_id"]

        r = admin_session.get(f"{BASE_URL}/api/admin/portfolio/inquiries")
        assert r.status_code == 200
        ids = [x["inquiry_id"] for x in r.json()]
        assert id2 in ids
        # latest should be at top
        assert ids[0] == id2 or ids.index(id2) < 3  # tolerate parallel inserts

    def test_list_filter_by_status_new(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/portfolio/inquiries", params={"status": "new"})
        assert r.status_code == 200
        for x in r.json():
            assert x["status"] == "new"

    def test_patch_inquiry_status_transition(self, admin_session):
        # create
        create = requests.post(f"{BASE_URL}/api/portfolio/inquiry", json={
            "intent": "order_similar",
            "full_name": "TEST_Patch",
            "email": "patch@example.com",
            "message": "to update",
        })
        assert create.status_code == 200
        inquiry_id = create.json()["inquiry_id"]

        # transitions
        for status_val in ["contacted", "qualified", "converted", "closed"]:
            r = admin_session.patch(
                f"{BASE_URL}/api/admin/portfolio/inquiries/{inquiry_id}",
                json={"status": status_val, "internal_notes": f"moved to {status_val}"},
            )
            assert r.status_code == 200, r.text
            assert r.json()["status"] == status_val

        # verify persisted via list
        r = admin_session.get(f"{BASE_URL}/api/admin/portfolio/inquiries")
        match = [x for x in r.json() if x["inquiry_id"] == inquiry_id]
        assert match and match[0]["status"] == "closed"

    def test_patch_inquiry_invalid_status_rejected(self, admin_session):
        create = requests.post(f"{BASE_URL}/api/portfolio/inquiry", json={
            "intent": "consultation",
            "full_name": "TEST_InvalidStatus",
            "email": "is@example.com",
            "message": "x",
        })
        inquiry_id = create.json()["inquiry_id"]
        r = admin_session.patch(
            f"{BASE_URL}/api/admin/portfolio/inquiries/{inquiry_id}",
            json={"status": "exploded"},
        )
        assert r.status_code == 400

    def test_delete_inquiry(self, admin_session):
        create = requests.post(f"{BASE_URL}/api/portfolio/inquiry", json={
            "intent": "consultation",
            "full_name": "TEST_Delete",
            "email": "del@example.com",
            "message": "delete me",
        })
        inquiry_id = create.json()["inquiry_id"]
        r = admin_session.delete(f"{BASE_URL}/api/admin/portfolio/inquiries/{inquiry_id}")
        assert r.status_code == 200
        # verify gone
        r2 = admin_session.delete(f"{BASE_URL}/api/admin/portfolio/inquiries/{inquiry_id}")
        assert r2.status_code == 404


# ---------- admin case CRUD still works after routing reorder ----------

class TestAdminCaseAfterReorder:
    def test_admin_get_case_by_id_works(self, admin_session, cases):
        case_id = cases[0]["case_id"]
        r = admin_session.get(f"{BASE_URL}/api/admin/portfolio/{case_id}")
        assert r.status_code == 200
        assert r.json()["case_id"] == case_id

    def test_admin_patch_case_toggle_flags(self, admin_session, cases):
        case_id = cases[0]["case_id"]
        original_published = cases[0].get("published", True)
        original_featured = cases[0].get("featured", False)

        # toggle
        r = admin_session.patch(
            f"{BASE_URL}/api/admin/portfolio/{case_id}",
            json={"published": not original_published, "featured": not original_featured},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["published"] == (not original_published)
        assert body["featured"] == (not original_featured)

        # revert
        r2 = admin_session.patch(
            f"{BASE_URL}/api/admin/portfolio/{case_id}",
            json={"published": original_published, "featured": original_featured},
        )
        assert r2.status_code == 200

    def test_admin_patch_case_title(self, admin_session, cases):
        case_id = cases[0]["case_id"]
        original_title = cases[0]["title"]
        new_title = original_title + " TEST_suffix"

        r = admin_session.patch(
            f"{BASE_URL}/api/admin/portfolio/{case_id}",
            json={"title": new_title},
        )
        assert r.status_code == 200
        assert r.json()["title"] == new_title

        # revert
        admin_session.patch(
            f"{BASE_URL}/api/admin/portfolio/{case_id}",
            json={"title": original_title},
        )


# ---------- auth gating ----------

class TestAuthGating:
    def test_public_list_no_auth(self):
        r = requests.get(f"{BASE_URL}/api/portfolio/cases")
        assert r.status_code == 200

    def test_public_detail_no_auth(self):
        r_list = requests.get(f"{BASE_URL}/api/portfolio/cases")
        case_id = r_list.json()[0]["case_id"]
        r = requests.get(f"{BASE_URL}/api/portfolio/cases/{case_id}")
        assert r.status_code == 200

    def test_admin_inquiries_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/admin/portfolio/inquiries")
        assert r.status_code in (401, 403), f"Expected auth rejection, got {r.status_code}"

    def test_admin_inquiries_rejects_non_admin(self, client_session):
        r = client_session.get(f"{BASE_URL}/api/admin/portfolio/inquiries")
        assert r.status_code in (401, 403)

    def test_admin_case_get_requires_auth(self):
        r_list = requests.get(f"{BASE_URL}/api/portfolio/cases")
        case_id = r_list.json()[0]["case_id"]
        r = requests.get(f"{BASE_URL}/api/admin/portfolio/{case_id}")
        assert r.status_code in (401, 403)

    def test_admin_case_patch_rejects_non_admin(self, client_session):
        r_list = requests.get(f"{BASE_URL}/api/portfolio/cases")
        case_id = r_list.json()[0]["case_id"]
        r = client_session.patch(
            f"{BASE_URL}/api/admin/portfolio/{case_id}",
            json={"title": "hacker"},
        )
        assert r.status_code in (401, 403)
