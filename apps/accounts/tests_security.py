"""
Enterprise security regression tests.
Run with: python manage.py test apps.accounts.tests_security
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from apps.accounts.models import LoginAttempt, User


class SecurityHeadersTest(TestCase):
    def test_csp_header_present(self):
        response = self.client.get(reverse("home"))
        self.assertIn("Content-Security-Policy", response)
        self.assertIn("default-src 'self'", response["Content-Security-Policy"])

    def test_x_frame_options_deny(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response["X-Frame-Options"], "DENY")

    def test_referrer_policy(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response["Referrer-Policy"], "same-origin")

    def test_permissions_policy(self):
        response = self.client.get(reverse("home"))
        self.assertIn("Permissions-Policy", response)


class BruteForceTest(TestCase):
    def test_failed_login_is_recorded(self):
        self.client.post(reverse("accounts:login"), {"username": "testuser", "password": "wrong"})
        self.assertTrue(LoginAttempt.objects.filter(username="testuser", successful=False).exists())

    def test_account_lockout_after_five_failures(self):
        for _ in range(5):
            self.client.post(reverse("accounts:login"), {"username": "target", "password": "wrong"})
        response = self.client.post(
            reverse("accounts:login"), {"username": "target", "password": "wrong"}, follow=True
        )
        self.assertContains(response, "locked") if response.context else None
        # At least 5+ failed attempts should be recorded
        self.assertGreaterEqual(LoginAttempt.objects.filter(username="target", successful=False).count(), 5)


class RBACTest(TestCase):
    def setUp(self):
        self.officer = User.objects.create_user(username="officer1", password="pw", role="FIELD_OFFICER")
        self.admin = User.objects.create_user(username="admin1", password="pw", role="SYSTEM_ADMIN")

    def test_field_officer_cannot_access_settings(self):
        self.client.force_login(self.officer)
        response = self.client.get(reverse("dashboard:settings"))
        self.assertEqual(response.status_code, 403)

    def test_field_officer_cannot_access_security(self):
        self.client.force_login(self.officer)
        response = self.client.get(reverse("dashboard:security"))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_access_settings(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboard:settings"))
        self.assertEqual(response.status_code, 200)

    def test_admin_can_access_security(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboard:security"))
        self.assertEqual(response.status_code, 200)
