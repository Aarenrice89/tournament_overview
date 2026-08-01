from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

CENTRAL_TIME = ZoneInfo("America/Chicago")
TO_CENTS = Decimal("0.01")
TOURNAMENT_DAILY_RATE = Decimal("150.00")
PRIVATE_LESSON_RATES = {
    1: Decimal("40.00"),
    2: Decimal("75.00"),
    3: Decimal("105.00"),
    4: Decimal("115.00"),
    5: Decimal("135.00"),
}


def central_today():
    return timezone.now().astimezone(CENTRAL_TIME).date()


def payroll_month_for(work_date):
    return date(work_date.year, work_date.month, 1)


def _money(value):
    return value.quantize(TO_CENTS, rounding=ROUND_HALF_UP)


@transaction.atomic
def initialize_payroll_month(month, initialized_by=None):
    from .models import CoachMonthlyPayroll, CoachProfile, PayrollMonth

    payroll_month, _ = PayrollMonth.objects.get_or_create(month=month)
    payrolls = []
    for coach in CoachProfile.objects.filter(monthly_base_rate__isnull=False):
        payroll, _ = CoachMonthlyPayroll.objects.get_or_create(
            coach=coach,
            month=month,
            defaults={"base_rate_snapshot": coach.monthly_base_rate},
        )
        payrolls.append(payroll)
    if not payroll_month.is_initialized:
        payroll_month.initialized_at = timezone.now()
        payroll_month.initialized_by = initialized_by
        payroll_month.save(update_fields=["initialized_at", "initialized_by"])
    return payrolls


def initialize_current_and_future_payrolls_for_coach(coach):
    """Create missing rate snapshots for initialized months without altering existing payrolls."""
    from .models import CoachMonthlyPayroll, PayrollMonth

    if not coach.compensation_configured:
        return []

    current_month = payroll_month_for(central_today())
    payrolls = []
    for month in PayrollMonth.objects.filter(month__gte=current_month, initialized_at__isnull=False).values_list(
        "month", flat=True
    ):
        payroll, _ = CoachMonthlyPayroll.objects.get_or_create(
            coach=coach,
            month=month,
            defaults={"base_rate_snapshot": coach.monthly_base_rate},
        )
        payrolls.append(payroll)
    return payrolls


def is_month_paid(month):
    from .models import PayrollMonth

    return PayrollMonth.objects.filter(month=month, paid_at__isnull=False).exists()


def is_month_initialized(month):
    from .models import PayrollMonth

    return PayrollMonth.objects.filter(month=month, initialized_at__isnull=False).exists()


def payroll_for_work(coach, work_date, allow_paid=False, allow_future=False, require_initialized_past=False):
    from .models import CoachMonthlyPayroll

    month = payroll_month_for(work_date)
    if not coach.compensation_configured:
        raise ValidationError("An administrator must set both pay rates before work can be recorded.")
    if not allow_paid:
        if is_month_paid(month):
            raise ValidationError("This payroll month has been paid and cannot be changed.")
        if require_initialized_past and month < payroll_month_for(central_today()) and not is_month_initialized(month):
            raise ValidationError(
                "An administrator must initialize this prior payroll month before work can be added."
            )
    if month > payroll_month_for(central_today()):
        if not allow_future:
            raise ValidationError("Work dates cannot be in the future.")
        if not is_month_initialized(month):
            raise ValidationError(
                "An administrator must initialize this future payroll month before work can be added."
            )
    payroll, _ = CoachMonthlyPayroll.objects.get_or_create(
        coach=coach,
        month=month,
        defaults={"base_rate_snapshot": coach.monthly_base_rate},
    )
    return payroll


def prepare_work(work, hourly_rate_snapshot=None, allow_paid=False, allow_future=False):
    """Assign payroll ownership and immutable payment data before saving a work item."""
    from .models import AdditionalWork

    original_month = work.payroll_month.month if work.pk and work.payroll_month_id else None
    target_month = payroll_month_for(work.work_date)
    if not allow_paid and original_month and is_month_paid(original_month):
        raise ValidationError("This payroll month has been paid and cannot be changed.")
    work.payroll_month = payroll_for_work(
        work.coach,
        work.work_date,
        allow_paid=allow_paid,
        allow_future=allow_future,
        require_initialized_past=original_month is None or target_month != original_month,
    )
    if work.activity in AdditionalWork.HOURLY_ACTIVITIES:
        work.hourly_rate_snapshot = (
            hourly_rate_snapshot if hourly_rate_snapshot is not None else work.coach.additional_hourly_rate
        )
        work.payment_amount = _money(work.hours_worked * work.hourly_rate_snapshot)
    elif work.activity == AdditionalWork.Activity.TOURNAMENT:
        work.hourly_rate_snapshot = None
        work.payment_amount = _money(TOURNAMENT_DAILY_RATE * work.tournament_days)
    else:
        work.hourly_rate_snapshot = None
        work.payment_amount = Decimal("0.00")
    work.full_clean()
    return work


@transaction.atomic
def recalculate_private_lesson_payment(work):
    if work.activity != work.Activity.PRIVATE_LESSON:
        return work
    lessons = list(work.private_lessons.all())
    if not lessons:
        raise ValidationError("At least one private lesson is required.")
    for lesson in lessons:
        lesson.payment_amount = PRIVATE_LESSON_RATES[lesson.children_coached]
        lesson.full_clean()
        lesson.save(update_fields=["payment_amount"])
    work.payment_amount = _money(sum((lesson.payment_amount for lesson in lessons), Decimal("0.00")))
    work.save(update_fields=["payment_amount", "updated_at"])
    return work


def send_invitation_email(invitation):
    registration_path = reverse("coaches:register", kwargs={"token": invitation.token})
    registration_url = f"{settings.SITE_URL.rstrip('/')}{registration_path}"
    send_mail(
        subject="Complete your coach portal registration",
        message=(
            "You have been invited to the Mid TN VBC coaches portal. Complete your registration within seven days:\n\n"
            f"{registration_url}"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[invitation.email],
    )
