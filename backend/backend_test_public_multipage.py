#!/usr/bin/env python3
"""
Backend test for LUMEN public multi-page site restructure.
Tests the two new public endpoints:
  - POST /api/public/contact
  - POST /api/public/newsletter/subscribe
"""
import sys
import requests

BASE_URL = "https://web-expo-app.preview.emergentagent.com"


class PublicSiteBackendTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0

    def run_test(self, name, method, endpoint, expected_status, data=None, check_response=None):
        """Run a single API test"""
        url = f"{BASE_URL}{endpoint}"
        headers = {'Content-Type': 'application/json'}

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")

        try:
            if method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=10)
            elif method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            else:
                print(f"❌ Failed - Unsupported method {method}")
                return False

            success = response.status_code == expected_status
            if success:
                # Additional response checks
                if check_response:
                    try:
                        json_data = response.json()
                        if not check_response(json_data):
                            print(f"❌ Failed - Response validation failed")
                            print(f"   Response: {json_data}")
                            return False
                    except Exception as e:
                        print(f"❌ Failed - Response check error: {e}")
                        return False

                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    print(f"   Response: {response.json()}")
                except:
                    pass
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    print(f"   Response: {response.json()}")
                except:
                    print(f"   Response: {response.text}")

            return success

        except requests.exceptions.Timeout:
            print(f"❌ Failed - Request timeout")
            return False
        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False

    def test_contact_form_valid(self):
        """Test contact form with valid data"""
        return self.run_test(
            "Contact form - valid submission",
            "POST",
            "/api/public/contact",
            200,
            data={
                "name": "Тестовий Користувач",
                "phone": "+380501234567",
                "topic": "Інвестиції в нерухомість",
                "message": "Хочу дізнатися більше про активи",
                "source": "contacts_page"
            },
            check_response=lambda r: r.get("ok") is True and "id" in r
        )

    def test_contact_form_minimal(self):
        """Test contact form with minimal required fields"""
        return self.run_test(
            "Contact form - minimal fields (name + phone)",
            "POST",
            "/api/public/contact",
            200,
            data={
                "name": "Мінімальний Тест",
                "phone": "+380671234567"
            },
            check_response=lambda r: r.get("ok") is True
        )

    def test_contact_form_header_source(self):
        """Test contact form from header callback button"""
        return self.run_test(
            "Contact form - header callback source",
            "POST",
            "/api/public/contact",
            200,
            data={
                "name": "Дзвінок Тест",
                "phone": "+380931234567",
                "source": "header"
            },
            check_response=lambda r: r.get("ok") is True
        )

    def test_newsletter_valid_email(self):
        """Test newsletter subscription with valid email"""
        return self.run_test(
            "Newsletter - valid email",
            "POST",
            "/api/public/newsletter/subscribe",
            200,
            data={
                "email": "test@example.com",
                "source": "footer"
            },
            check_response=lambda r: r.get("ok") is True
        )

    def test_newsletter_invalid_email(self):
        """Test newsletter subscription with invalid email"""
        return self.run_test(
            "Newsletter - invalid email format",
            "POST",
            "/api/public/newsletter/subscribe",
            200,
            data={
                "email": "not-an-email",
                "source": "footer"
            },
            check_response=lambda r: r.get("ok") is False
        )

    def test_newsletter_idempotent(self):
        """Test newsletter subscription is idempotent (same email twice)"""
        email = "idempotent@test.com"
        # First subscription
        success1 = self.run_test(
            "Newsletter - first subscription",
            "POST",
            "/api/public/newsletter/subscribe",
            200,
            data={"email": email, "source": "footer"},
            check_response=lambda r: r.get("ok") is True
        )
        # Second subscription (should still succeed)
        success2 = self.run_test(
            "Newsletter - duplicate subscription (idempotent)",
            "POST",
            "/api/public/newsletter/subscribe",
            200,
            data={"email": email, "source": "footer"},
            check_response=lambda r: r.get("ok") is True
        )
        return success1 and success2

    def run_all_tests(self):
        """Run all backend tests"""
        print("=" * 60)
        print("LUMEN Public Multi-Page Site - Backend API Tests")
        print("=" * 60)

        # Contact form tests
        self.test_contact_form_valid()
        self.test_contact_form_minimal()
        self.test_contact_form_header_source()

        # Newsletter tests
        self.test_newsletter_valid_email()
        self.test_newsletter_invalid_email()
        self.test_newsletter_idempotent()

        # Print results
        print("\n" + "=" * 60)
        print(f"📊 Tests passed: {self.tests_passed}/{self.tests_run}")
        print("=" * 60)

        return 0 if self.tests_passed == self.tests_run else 1


def main():
    tester = PublicSiteBackendTester()
    return tester.run_all_tests()


if __name__ == "__main__":
    sys.exit(main())
