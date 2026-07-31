from django.contrib import admin

from .models import (
    AdditionalWork,
    CoachInvitation,
    CoachMonthlyPayroll,
    CoachProfile,
    PayrollMonth,
    PrivateLesson,
)


class PrivateLessonInline(admin.TabularInline):
    model = PrivateLesson
    extra = 0
    readonly_fields = ("payment_amount",)


@admin.register(CoachProfile)
class CoachProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "monthly_base_rate", "additional_hourly_rate")
    search_fields = ("user__username", "user__first_name", "user__last_name", "user__email")


@admin.register(CoachInvitation)
class CoachInvitationAdmin(admin.ModelAdmin):
    list_display = ("email", "created_at", "expires_at", "accepted_at", "revoked_at")
    search_fields = ("email",)
    readonly_fields = ("token", "created_at", "expires_at", "accepted_at", "revoked_at")


@admin.register(CoachMonthlyPayroll)
class CoachMonthlyPayrollAdmin(admin.ModelAdmin):
    list_display = ("coach", "month", "base_rate_snapshot")
    list_filter = ("month",)
    search_fields = ("coach__user__username", "coach__user__first_name", "coach__user__last_name")


@admin.register(PayrollMonth)
class PayrollMonthAdmin(admin.ModelAdmin):
    list_display = ("month", "initialized_at", "initialized_by", "paid_at", "paid_by")
    list_filter = ("paid_at",)


@admin.register(AdditionalWork)
class AdditionalWorkAdmin(admin.ModelAdmin):
    list_display = ("coach", "work_date", "activity", "payment_amount")
    list_filter = ("activity", "payroll_month__month")
    search_fields = ("coach__user__username", "coach__user__first_name", "coach__user__last_name")
    readonly_fields = ("hourly_rate_snapshot", "payment_amount")
    inlines = [PrivateLessonInline]
