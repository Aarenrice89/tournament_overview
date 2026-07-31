from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from coaches.models import CoachProfile


class PortalLandingTests(TestCase):
    def test_anonymous_user_sees_both_login_options(self):
        response = self.client.get(reverse("landing"))

        self.assertContains(response, "Mid TN VB Club Portal")
        self.assertContains(response, "tournament_overview/images/mtnvbc-logo.png")
        self.assertContains(response, "Coach login")
        self.assertContains(response, "Staff login")
        self.assertNotContains(response, "Tournament Overview")

    def test_staff_sees_administrative_applications(self):
        staff = get_user_model().objects.create_user(username="staff", password="password", is_staff=True)
        self.client.force_login(staff)

        response = self.client.get(reverse("landing"))

        self.assertContains(response, "Tournament Overview")
        self.assertContains(response, "Payroll Admin")
        self.assertNotContains(response, "Coach Payroll")
        self.assertContains(response, "portal-header--admin")

    def test_coach_sees_coach_payroll(self):
        user = get_user_model().objects.create_user(username="coach", password="password")
        CoachProfile.objects.create(
            user=user,
            monthly_base_rate=Decimal("1000.00"),
            additional_hourly_rate=Decimal("50.00"),
        )
        self.client.force_login(user)

        response = self.client.get(reverse("landing"))

        self.assertContains(response, "Coach Payroll")
        self.assertNotContains(response, "Tournament Overview")
        self.assertContains(response, "portal-header--coach")

    def test_staff_coach_sees_all_applications(self):
        user = get_user_model().objects.create_user(username="staff-coach", password="password", is_staff=True)
        CoachProfile.objects.create(
            user=user,
            monthly_base_rate=Decimal("1000.00"),
            additional_hourly_rate=Decimal("50.00"),
        )
        self.client.force_login(user)

        response = self.client.get(reverse("landing"))

        self.assertContains(response, "Tournament Overview")
        self.assertContains(response, "Payroll Admin")
        self.assertContains(response, "Coach Payroll")
        self.assertContains(response, "portal-header--admin")
