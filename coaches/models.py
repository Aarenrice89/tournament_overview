from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .services import central_today


def invitation_expiry():
    return timezone.now() + timedelta(days=7)


class CoachProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="coach_profile")
    monthly_base_rate = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    additional_hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__last_name", "user__first_name", "user__username"]

    def __str__(self):
        return self.user.get_full_name() or self.user.username

    @property
    def compensation_configured(self):
        return self.monthly_base_rate is not None and self.additional_hourly_rate is not None


class CoachInvitation(models.Model):
    email = models.EmailField()
    token = models.UUIDField(default=uuid4, unique=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="created_coach_invitations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=invitation_expiry)
    accepted_at = models.DateTimeField(blank=True, null=True)
    revoked_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.email

    @property
    def is_valid(self):
        return self.accepted_at is None and self.revoked_at is None and timezone.now() < self.expires_at


class PayrollMonth(models.Model):
    month = models.DateField(unique=True)
    initialized_at = models.DateTimeField(blank=True, null=True)
    initialized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="initialized_coach_payroll_months",
    )
    paid_at = models.DateTimeField(blank=True, null=True)
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="paid_coach_payroll_months",
    )

    class Meta:
        ordering = ["-month"]

    def __str__(self):
        return f"{self.month:%B %Y}"

    @property
    def is_paid(self):
        return self.paid_at is not None

    @property
    def is_initialized(self):
        return self.initialized_at is not None

    def clean(self):
        if self.month and self.month.day != 1:
            raise ValidationError({"month": "Payroll months must use the first day of the month."})


class CoachMonthlyPayroll(models.Model):
    coach = models.ForeignKey(CoachProfile, on_delete=models.CASCADE, related_name="monthly_payrolls")
    month = models.DateField()
    base_rate_snapshot = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-month", "coach__user__last_name", "coach__user__first_name"]
        constraints = [models.UniqueConstraint(fields=["coach", "month"], name="unique_coach_payroll_month")]

    def __str__(self):
        return f"{self.coach} - {self.month:%B %Y}"

    def clean(self):
        if self.month and self.month.day != 1:
            raise ValidationError({"month": "Payroll months must use the first day of the month."})

    @property
    def additional_work_total(self):
        return sum((work.payment_amount for work in self.work_items.all()), Decimal("0.00"))

    @property
    def total_compensation(self):
        return self.base_rate_snapshot + self.additional_work_total


class AdditionalWork(models.Model):
    class Activity(models.TextChoices):
        CLUB_PRACTICE = "club_practice", "Club practice"
        ACADEMY = "academy", "Academy"
        VOLLEY_TOTS = "volley_tots", "Volley Tots"
        VOLLEY_JRS = "volley_jrs", "Volley Jrs"
        CAMP_CLINIC = "camp_clinic", "Camp/Clinic"
        PRIVATE_LESSON = "private_lesson", "Private Lesson"
        TOURNAMENT = "tournament", "Tournament"
        OTHER = "other", "Other"

    HOURLY_ACTIVITIES = {
        Activity.CLUB_PRACTICE,
        Activity.ACADEMY,
        Activity.VOLLEY_TOTS,
        Activity.VOLLEY_JRS,
        Activity.CAMP_CLINIC,
        Activity.OTHER,
    }

    coach = models.ForeignKey(CoachProfile, on_delete=models.CASCADE, related_name="work_items")
    payroll_month = models.ForeignKey(CoachMonthlyPayroll, on_delete=models.CASCADE, related_name="work_items")
    activity = models.CharField(max_length=30, choices=Activity.choices)
    work_date = models.DateField(default=central_today)
    hours_worked = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.5")), MaxValueValidator(Decimal("12"))],
    )
    tournament_days = models.PositiveSmallIntegerField(
        blank=True, null=True, validators=[MinValueValidator(1), MaxValueValidator(4)]
    )
    notes = models.TextField(blank=True)
    hourly_rate_snapshot = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    payment_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-work_date", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(hours_worked__isnull=True)
                | (Q(hours_worked__gte=Decimal("0.5")) & Q(hours_worked__lte=12)),
                name="additional_work_hours_in_range",
            ),
            models.CheckConstraint(
                condition=Q(tournament_days__isnull=True) | (Q(tournament_days__gte=1) & Q(tournament_days__lte=4)),
                name="additional_work_tournament_days_in_range",
            ),
        ]

    def __str__(self):
        return f"{self.coach} - {self.get_activity_display()} on {self.work_date}"

    def clean(self):
        errors = {}
        if self.payroll_month_id:
            if self.payroll_month.coach_id != self.coach_id:
                errors["payroll_month"] = "The payroll month must belong to the selected coach."

        if self.activity in self.HOURLY_ACTIVITIES:
            if self.hours_worked is None:
                errors["hours_worked"] = "Hourly work requires total hours worked."
            elif (self.hours_worked * 2) % 1:
                errors["hours_worked"] = "Hours must be in half-hour increments."
            if self.tournament_days is not None:
                errors["tournament_days"] = "Hourly work cannot include tournament days."
        elif self.activity == self.Activity.TOURNAMENT:
            if self.tournament_days is None:
                errors["tournament_days"] = "Tournament work requires the number of days."
            if self.hours_worked is not None:
                errors["hours_worked"] = "Tournament work cannot include hourly work."
        elif self.activity == self.Activity.PRIVATE_LESSON:
            if self.hours_worked is not None:
                errors["hours_worked"] = "Private lessons cannot include hourly work."
            if self.tournament_days is not None:
                errors["tournament_days"] = "Private lessons cannot include tournament days."
        if errors:
            raise ValidationError(errors)


class PrivateLesson(models.Model):
    additional_work = models.ForeignKey(AdditionalWork, on_delete=models.CASCADE, related_name="private_lessons")
    children_coached = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    payment_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, editable=False)

    class Meta:
        ordering = ["pk"]

    def __str__(self):
        return f"{self.children_coached} children - {self.payment_amount}"

    def clean(self):
        if self.additional_work_id and self.additional_work.activity != AdditionalWork.Activity.PRIVATE_LESSON:
            raise ValidationError("Lesson rows are only allowed for private lesson work.")
