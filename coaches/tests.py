from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from resend.exceptions import ResendError

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
    InvitationEmailDeliveryError,
    central_today,
    payroll_month_for,
    recalculate_private_lesson_payment,
    send_invitation_email,
)


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False)
class CoachInvitationTests(TestCase):
    @override_settings(
        DEFAULT_FROM_EMAIL="Mid TN VBC <coaches@club.example>",
        RESEND_API_KEY="re_test",
        SITE_URL="https://club.example",
    )
    def test_staff_can_create_and_email_an_invitation(self):
        staff = get_user_model().objects.create_user(username="admin", password="password", is_staff=True)
        self.client.force_login(staff)

        with patch("coaches.services.resend.Emails.send") as send:
            response = self.client.post(reverse("coaches:admin-invitation-add"), {"email": "coach@example.com"})

        invitation = CoachInvitation.objects.get()
        self.assertRedirects(response, reverse("coaches:admin-invitations"))
        self.assertEqual(invitation.email, "coach@example.com")
        send.assert_called_once_with(
            {
                "from": "Mid TN VBC <coaches@club.example>",
                "to": ["coach@example.com"],
                "subject": "Complete your coach portal registration",
                "text": (
                    "You have been invited to the Mid TN VBC coaches portal. "
                    "Complete your registration within seven days:\n\n"
                    f"https://club.example/coaches/invitations/{invitation.token}/register/"
                ),
            }
        )

    @override_settings(RESEND_API_KEY="", SITE_URL="https://club.example")
    def test_invitation_email_requires_a_resend_api_key(self):
        invitation = CoachInvitation.objects.create(email="coach@example.com")

        with self.assertRaisesRegex(InvitationEmailDeliveryError, "RESEND_API_KEY is not configured"):
            send_invitation_email(invitation)

    @override_settings(
        DEFAULT_FROM_EMAIL="Mid TN VBC <coaches@club.example>",
        RESEND_API_KEY="re_test",
        SITE_URL="https://club.example",
    )
    def test_invitation_email_translates_resend_errors(self):
        invitation = CoachInvitation.objects.create(email="coach@example.com")

        with patch(
            "coaches.services.resend.Emails.send",
            side_effect=ResendError("validation_error", "validation_error", "Resend unavailable", "Retry later"),
        ):
            with self.assertRaisesRegex(InvitationEmailDeliveryError, "not accepted for delivery"):
                send_invitation_email(invitation)

    def test_staff_invitation_is_not_created_when_email_delivery_fails(self):
        staff = get_user_model().objects.create_user(username="admin", password="password", is_staff=True)
        self.client.force_login(staff)

        with patch(
            "coaches.views.send_invitation_email",
            side_effect=InvitationEmailDeliveryError("Resend unavailable"),
        ):
            response = self.client.post(reverse("coaches:admin-invitation-add"), {"email": "coach@example.com"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The invitation email could not be delivered. No invitation was created.")
        self.assertFalse(CoachInvitation.objects.exists())

    def test_staff_can_retry_an_existing_invitation_after_email_delivery_failure(self):
        staff = get_user_model().objects.create_user(username="admin", password="password", is_staff=True)
        invitation = CoachInvitation.objects.create(email="coach@example.com", created_by=staff)
        self.client.force_login(staff)

        with patch(
            "coaches.views.send_invitation_email",
            side_effect=InvitationEmailDeliveryError("Resend unavailable"),
        ):
            response = self.client.post(
                reverse("coaches:admin-invitation-resend", kwargs={"pk": invitation.pk}), follow=True
            )

        self.assertRedirects(response, reverse("coaches:admin-invitations"))
        self.assertContains(response, "The invitation email could not be delivered. Please try again later.")
        self.assertTrue(CoachInvitation.objects.filter(pk=invitation.pk).exists())

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


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    AXES_CACHE="default",
    SECURE_SSL_REDIRECT=False,
)
class LoginThrottlingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username=f"coach-{uuid4().hex}", password="correct-password")

    def tearDown(self):
        cache.clear()

    def test_coach_login_locks_after_five_failed_attempts(self):
        url = reverse("coaches:login")

        for _ in range(4):
            response = self.client.post(url, {"username": self.user.username, "password": "wrong-password"})
            self.assertEqual(response.status_code, 200)

        response = self.client.post(url, {"username": self.user.username, "password": "wrong-password"})

        self.assertEqual(response.status_code, 429)

    def test_admin_login_is_throttled(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        url = reverse("admin:login")

        for _ in range(4):
            response = self.client.post(url, {"username": self.user.username, "password": "wrong-password"})
            self.assertEqual(response.status_code, 200)

        response = self.client.post(url, {"username": self.user.username, "password": "wrong-password"})

        self.assertEqual(response.status_code, 429)

    def test_successful_login_resets_failed_attempts(self):
        url = reverse("coaches:login")

        for _ in range(4):
            self.client.post(url, {"username": self.user.username, "password": "wrong-password"})

        response = self.client.post(url, {"username": self.user.username, "password": "correct-password"})
        self.assertRedirects(response, reverse("landing"))

        self.client.logout()
        for _ in range(4):
            response = self.client.post(url, {"username": self.user.username, "password": "wrong-password"})
            self.assertEqual(response.status_code, 200)


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False)
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

    def test_coach_can_submit_hourly_work_with_a_blank_tournament_length(self):
        self.client.force_login(self.coach.user)
        form = AdditionalWorkForm(coach=self.coach)

        self.assertEqual(form.fields["tournament_days"].widget.choices[0], ("", "Select days"))

        response = self.client.post(
            reverse("coaches:work-add"),
            {
                "activity": AdditionalWork.Activity.ACADEMY,
                "work_date": central_today().isoformat(),
                "hours_worked": "2.5",
                "tournament_days": "",
                "notes": "Practice",
            },
        )

        work = AdditionalWork.objects.get(activity=AdditionalWork.Activity.ACADEMY)
        self.assertRedirects(response, reverse("coaches:work-detail", kwargs={"pk": work.pk}))
        self.assertEqual(work.hours_worked, Decimal("2.5"))
        self.assertIsNone(work.tournament_days)

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


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False)
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
        self.assertContains(response, "Payroll Admin")
        self.assertContains(response, "Coaches")
        self.assertContains(response, "Invitations")
        self.assertContains(response, 'class="btn btn-outline-light" type="submit">Log out</button>')

    def test_staff_payroll_page_explains_missing_base_pay_snapshots(self):
        staff = get_user_model().objects.create_user(username="admin", password="password", is_staff=True)
        month = payroll_month_for(central_today())
        PayrollMonth.objects.create(month=month, initialized_at=timezone.now())
        CoachProfile.objects.create(user=get_user_model().objects.create_user(username="no-base-rate"))
        CoachProfile.objects.create(
            user=get_user_model().objects.create_user(username="missing-snapshot"),
            monthly_base_rate=Decimal("1000.00"),
            additional_hourly_rate=Decimal("50.00"),
        )
        self.client.force_login(staff)

        response = self.client.get(reverse("coaches:admin-payroll"))

        self.assertContains(response, "Initialized")
        self.assertContains(response, "Base pay not set")
        self.assertContains(response, "Base pay not initialized for this month")


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False)
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
