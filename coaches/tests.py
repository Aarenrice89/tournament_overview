from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import AdditionalWorkForm
from .models import (
    AdditionalWork,
    CoachInvitation,
    CoachMonthlyPayroll,
    CoachProfile,
    PayrollMonth,
    PrivateLesson,
)
from .services import (
    central_today,
    payroll_month_for,
    recalculate_private_lesson_payment,
)


class CoachInvitationTests(TestCase):
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", SITE_URL="https://club.example")
    def test_staff_can_create_and_email_an_invitation(self):
        staff = get_user_model().objects.create_user(username="admin", password="password", is_staff=True)
        self.client.force_login(staff)

        response = self.client.post(reverse("coaches:admin-invitation-add"), {"email": "coach@example.com"})

        invitation = CoachInvitation.objects.get()
        self.assertRedirects(response, reverse("coaches:admin-invitations"))
        self.assertEqual(invitation.email, "coach@example.com")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(
            f"https://club.example/coaches/invitations/{invitation.token}/register/",
            mail.outbox[0].body,
        )

    def test_registration_consumes_invitation_and_creates_coach_profile(self):
        invitation = CoachInvitation.objects.create(email="coach@example.com")
        url = reverse("coaches:register", kwargs={"token": invitation.token})

        response = self.client.post(
            url,
            {
                "email": invitation.email,
                "first_name": "Casey",
                "last_name": "Coach",
                "username": "casey",
                "password1": "a-strong-password",
                "password2": "a-strong-password",
            },
        )

        invitation.refresh_from_db()
        user = get_user_model().objects.get(username="casey")
        self.assertRedirects(response, reverse("coaches:dashboard"))
        self.assertIsNotNone(invitation.accepted_at)
        self.assertTrue(hasattr(user, "coach_profile"))
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_expired_invitation_is_unavailable(self):
        invitation = CoachInvitation.objects.create(
            email="coach@example.com", expires_at=timezone.now() - timedelta(seconds=1)
        )

        response = self.client.get(reverse("coaches:register", kwargs={"token": invitation.token}))

        self.assertEqual(response.status_code, 404)


class CompensationTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="coach", password="password")
        self.coach = CoachProfile.objects.create(
            user=user,
            monthly_base_rate=Decimal("1000.00"),
            additional_hourly_rate=Decimal("50.00"),
        )

    def save_work(self, activity, work_date, **extra):
        form = AdditionalWorkForm(
            data={"activity": activity, "work_date": work_date.isoformat(), "notes": "", **extra}, coach=self.coach
        )
        self.assertTrue(form.is_valid(), form.errors)
        return form.save_for_coach(self.coach)

    def test_hourly_work_captures_rate_and_monthly_base_snapshots(self):
        work = self.save_work(AdditionalWork.Activity.CLUB_PRACTICE, timezone.localdate(), hours_worked="2.5")
        self.coach.monthly_base_rate = Decimal("1200.00")
        self.coach.additional_hourly_rate = Decimal("60.00")
        self.coach.save()

        edit_form = AdditionalWorkForm(
            data={
                "activity": AdditionalWork.Activity.CLUB_PRACTICE,
                "work_date": work.work_date.isoformat(),
                "hours_worked": "3",
                "notes": "Updated hours",
            },
            instance=work,
            coach=self.coach,
        )
        self.assertTrue(edit_form.is_valid(), edit_form.errors)
        work = edit_form.save_for_coach(self.coach)

        self.assertEqual(work.payment_amount, Decimal("150.00"))
        self.assertEqual(work.hourly_rate_snapshot, Decimal("50.00"))
        self.assertEqual(work.payroll_month.base_rate_snapshot, Decimal("1000.00"))

    def test_tournament_and_private_lesson_payments(self):
        tournament = self.save_work(AdditionalWork.Activity.TOURNAMENT, timezone.localdate(), tournament_days="3")
        lesson_work = self.save_work(AdditionalWork.Activity.PRIVATE_LESSON, timezone.localdate())
        PrivateLesson.objects.create(additional_work=lesson_work, children_coached=1, payment_amount=Decimal("0"))
        PrivateLesson.objects.create(additional_work=lesson_work, children_coached=5, payment_amount=Decimal("0"))
        recalculate_private_lesson_payment(lesson_work)
        lesson_work.refresh_from_db()

        self.assertEqual(tournament.payment_amount, Decimal("450.00"))
        self.assertEqual(lesson_work.payment_amount, Decimal("175.00"))

    def test_half_hour_validation_and_owner_access(self):
        form = AdditionalWorkForm(
            data={
                "activity": AdditionalWork.Activity.ACADEMY,
                "work_date": timezone.localdate().isoformat(),
                "hours_worked": "1.2",
                "notes": "",
            },
            coach=self.coach,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("hours_worked", form.errors)

        work = self.save_work(AdditionalWork.Activity.OTHER, timezone.localdate(), hours_worked="1")
        other_user = get_user_model().objects.create_user(username="other", password="password")
        CoachProfile.objects.create(
            user=other_user,
            monthly_base_rate=Decimal("1000.00"),
            additional_hourly_rate=Decimal("50.00"),
        )
        self.client.force_login(other_user)

        response = self.client.get(reverse("coaches:work-edit", kwargs={"pk": work.pk}))

        self.assertEqual(response.status_code, 404)

    def test_coach_can_submit_multiple_private_lessons(self):
        self.client.force_login(self.coach.user)

        response = self.client.post(
            reverse("coaches:work-add"),
            {
                "activity": AdditionalWork.Activity.PRIVATE_LESSON,
                "work_date": timezone.localdate().isoformat(),
                "notes": "After school",
                "lessons-TOTAL_FORMS": "2",
                "lessons-INITIAL_FORMS": "0",
                "lessons-MIN_NUM_FORMS": "0",
                "lessons-MAX_NUM_FORMS": "1000",
                "lessons-0-children_coached": "2",
                "lessons-1-children_coached": "3",
            },
        )

        work = AdditionalWork.objects.get(activity=AdditionalWork.Activity.PRIVATE_LESSON)
        self.assertRedirects(response, reverse("coaches:work-detail", kwargs={"pk": work.pk}))
        self.assertEqual(work.private_lessons.count(), 2)
        self.assertEqual(work.payment_amount, Decimal("180.00"))


class PortalRenderingTests(TestCase):
    def test_staff_payroll_page_renders(self):
        staff = get_user_model().objects.create_user(username="admin", password="password", is_staff=True)
        coach_user = get_user_model().objects.create_user(username="coach", password="password")
        CoachProfile.objects.create(
            user=coach_user,
            monthly_base_rate=Decimal("1000.00"),
            additional_hourly_rate=Decimal("50.00"),
        )
        self.client.force_login(staff)

        response = self.client.get(reverse("coaches:admin-payroll"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Monthly coach payroll")
        self.assertContains(response, reverse("landing"))
        self.assertContains(response, "portal-header--admin")


class StaffCoachEditTests(TestCase):
    def test_staff_can_edit_a_coach_and_return_to_the_payroll_month(self):
        staff = get_user_model().objects.create_user(username="admin", password="password", is_staff=True)
        coach_user = get_user_model().objects.create_user(
            username="coach", first_name="Old", last_name="Name", email="old@example.com", password="password"
        )
        coach = CoachProfile.objects.create(
            user=coach_user,
            monthly_base_rate=Decimal("1000.00"),
            additional_hourly_rate=Decimal("50.00"),
        )
        month = timezone.localdate().replace(day=1)
        detail_url = reverse("coaches:admin-coach-payroll", kwargs={"pk": coach.pk, "month": month.strftime("%Y-%m")})
        edit_url = reverse("coaches:admin-coach-edit", kwargs={"pk": coach.pk})
        self.client.force_login(staff)

        response = self.client.get(detail_url)
        self.assertContains(response, f"{edit_url}?month={month:%Y-%m}")

        response = self.client.post(
            edit_url,
            {
                "month": month.strftime("%Y-%m"),
                "first_name": "New",
                "last_name": "Coach",
                "email": "new@example.com",
                "monthly_base_rate": "1200.00",
                "additional_hourly_rate": "60.00",
            },
        )

        coach.refresh_from_db()
        coach.user.refresh_from_db()
        self.assertRedirects(response, detail_url)
        self.assertEqual(coach.user.first_name, "New")
        self.assertEqual(coach.user.last_name, "Coach")
        self.assertEqual(coach.user.email, "new@example.com")
        self.assertEqual(coach.monthly_base_rate, Decimal("1200.00"))
        self.assertEqual(coach.additional_hourly_rate, Decimal("60.00"))

    def test_editing_rates_initializes_current_and_future_months_only(self):
        staff = get_user_model().objects.create_user(username="admin", password="password", is_staff=True)
        coach = CoachProfile.objects.create(
            user=get_user_model().objects.create_user(username="coach", password="password")
        )
        current_month = payroll_month_for(central_today())
        previous_month = (current_month - timedelta(days=1)).replace(day=1)
        future_month = (current_month + timedelta(days=32)).replace(day=1)
        for month in [previous_month, current_month, future_month]:
            PayrollMonth.objects.create(month=month, initialized_at=timezone.now())
        self.client.force_login(staff)

        response = self.client.post(
            reverse("coaches:admin-coach-edit", kwargs={"pk": coach.pk}),
            {
                "first_name": "New",
                "last_name": "Coach",
                "email": "new@example.com",
                "monthly_base_rate": "1200.00",
                "additional_hourly_rate": "60.00",
            },
        )

        self.assertRedirects(response, reverse("coaches:admin-coaches"))
        self.assertFalse(CoachMonthlyPayroll.objects.filter(coach=coach, month=previous_month).exists())
        self.assertEqual(
            list(
                CoachMonthlyPayroll.objects.filter(coach=coach)
                .order_by("month")
                .values_list("month", "base_rate_snapshot")
            ),
            [(current_month, Decimal("1200.00")), (future_month, Decimal("1200.00"))],
        )
