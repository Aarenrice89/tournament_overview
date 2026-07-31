from datetime import date

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
)

from .forms import (
    AdditionalWorkForm,
    CoachAuthenticationForm,
    CoachEditForm,
    CoachInvitationForm,
    CoachRegistrationForm,
    PrivateLessonFormSet,
    StaffAdditionalWorkForm,
)
from .mixins import CoachRequiredMixin, StaffRequiredMixin
from .models import (
    AdditionalWork,
    CoachInvitation,
    CoachMonthlyPayroll,
    CoachProfile,
    PayrollMonth,
)
from .services import (
    central_today,
    initialize_payroll_month,
    is_month_paid,
    recalculate_private_lesson_payment,
    send_invitation_email,
)


def requested_month(value, allow_future=False):
    if not value:
        today = central_today()
        return date(today.year, today.month, 1)
    try:
        parsed = date.fromisoformat(f"{value}-01")
    except ValueError as error:
        raise Http404("Invalid month.") from error
    if not allow_future and parsed > date(central_today().year, central_today().month, 1):
        raise Http404("Future months are unavailable.")
    return parsed


class CoachLoginView(LoginView):
    authentication_form = CoachAuthenticationForm
    template_name = "coaches/login.html"

    def get_success_url(self):
        if redirect_url := self.get_redirect_url():
            return redirect_url
        return reverse("landing")


class CoachLogoutView(LogoutView):
    next_page = reverse_lazy("coaches:login")


class CoachRegistrationView(FormView):
    form_class = CoachRegistrationForm
    template_name = "coaches/register.html"

    def get_invitation(self):
        invitation = get_object_or_404(CoachInvitation, token=self.kwargs["token"])
        if not invitation.is_valid:
            raise Http404("This invitation is no longer valid.")
        return invitation

    def dispatch(self, request, *args, **kwargs):
        self.invitation = self.get_invitation()
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["invitation"] = self.invitation
        return kwargs

    def form_valid(self, form):
        User = CoachProfile._meta.get_field("user").remote_field.model
        try:
            with transaction.atomic():
                invitation = CoachInvitation.objects.select_for_update().get(pk=self.invitation.pk)
                if not invitation.is_valid:
                    form.add_error(None, "This invitation is no longer valid.")
                    return self.form_invalid(form)
                if User.objects.filter(email__iexact=invitation.email).exists():
                    form.add_error("email", "An account already uses this email address.")
                    return self.form_invalid(form)
                user = User.objects.create_user(
                    username=form.cleaned_data["username"],
                    email=invitation.email,
                    first_name=form.cleaned_data["first_name"],
                    last_name=form.cleaned_data["last_name"],
                    password=form.cleaned_data["password1"],
                )
                CoachProfile.objects.create(user=user)
                invitation.accepted_at = timezone.now()
                invitation.save(update_fields=["accepted_at"])
        except IntegrityError:
            form.add_error("username", "This username is already in use.")
            return self.form_invalid(form)
        login(self.request, user)
        messages.success(self.request, "Your coach account is ready. An administrator will configure your pay rates.")
        return redirect("coaches:dashboard")


class CoachDashboardView(CoachRequiredMixin, ListView):
    context_object_name = "work_items"
    template_name = "coaches/dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        self.month = requested_month(request.GET.get("month"), allow_future=True)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return AdditionalWork.objects.filter(coach=self.coach, payroll_month__month=self.month).prefetch_related(
            "private_lessons"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        payroll_month = PayrollMonth.objects.filter(month=self.month).first()
        current_month = date(central_today().year, central_today().month, 1)
        payroll = (
            CoachMonthlyPayroll.objects.filter(coach=self.coach, month=self.month)
            .prefetch_related("work_items")
            .first()
        )
        context.update(
            {
                "month": self.month,
                "payroll": payroll,
                "month_is_paid": payroll_month.is_paid if payroll_month else False,
                "month_is_future": self.month > current_month,
                "month_is_uninitialized_past": self.month < current_month
                and not (payroll_month and payroll_month.is_initialized),
                "compensation_configured": self.coach.compensation_configured,
            }
        )
        return context


class WorkFormMixin:
    template_name = "coaches/work_form.html"
    form_class = AdditionalWorkForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["allow_future"] = self.request.user.is_staff
        if not self.request.user.is_staff:
            kwargs["coach"] = self.get_coach()
        return kwargs

    def get_coach(self):
        raise NotImplementedError

    def get_formset(self, data=None, instance=None):
        return PrivateLessonFormSet(data=data, instance=instance or AdditionalWork(), prefix="lessons")

    def form_and_formset_valid(self, form, formset):
        try:
            work = form.save_for_coach(
                self.get_coach(),
                allow_paid=self.request.user.is_staff,
                allow_future=self.request.user.is_staff,
            )
        except ValidationError as error:
            form.add_error(None, error)
            return self.render_to_response(self.get_context_data(form=form, lesson_formset=formset))

        if work.activity == AdditionalWork.Activity.PRIVATE_LESSON:
            formset.instance = work
            formset.save()
            try:
                recalculate_private_lesson_payment(work)
            except ValidationError as error:
                form.add_error(None, error)
                return self.render_to_response(self.get_context_data(form=form, lesson_formset=formset))
        else:
            work.private_lessons.all().delete()
        messages.success(self.request, "Additional work was saved.")
        return redirect(self.success_url(work))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("lesson_formset", self.get_formset(instance=getattr(self, "object", None)))
        context["is_staff_portal"] = self.request.user.is_staff
        return context


class CoachWorkCreateView(CoachRequiredMixin, WorkFormMixin, CreateView):
    def get_coach(self):
        return self.coach

    def post(self, request, *args, **kwargs):
        self.object = None
        form = self.get_form()
        if not form.is_valid():
            return self.form_invalid(form)
        formset = self.get_formset(data=request.POST)
        if form.cleaned_data["activity"] == AdditionalWork.Activity.PRIVATE_LESSON and not formset.is_valid():
            return self.render_to_response(self.get_context_data(form=form, lesson_formset=formset))
        return self.form_and_formset_valid(form, formset)

    def success_url(self, work):
        return reverse("coaches:work-detail", kwargs={"pk": work.pk})


class CoachWorkUpdateView(CoachRequiredMixin, WorkFormMixin, UpdateView):
    def get_queryset(self):
        return AdditionalWork.objects.filter(coach=self.coach)

    def get_object(self, queryset=None):
        work = super().get_object(queryset)
        if not self.request.user.is_staff:
            if is_month_paid(work.payroll_month.month):
                raise PermissionDenied("This payroll month has been paid and cannot be changed.")
            if work.work_date > central_today():
                raise PermissionDenied("Future work can only be changed by an administrator.")
        return work

    def get_coach(self):
        return self.coach

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        if not form.is_valid():
            return self.form_invalid(form)
        formset = self.get_formset(data=request.POST, instance=self.object)
        if form.cleaned_data["activity"] == AdditionalWork.Activity.PRIVATE_LESSON and not formset.is_valid():
            return self.render_to_response(self.get_context_data(form=form, lesson_formset=formset))
        return self.form_and_formset_valid(form, formset)

    def success_url(self, work):
        return reverse("coaches:work-detail", kwargs={"pk": work.pk})


class CoachWorkDetailView(CoachRequiredMixin, DetailView):
    template_name = "coaches/work_detail.html"

    def get_queryset(self):
        return AdditionalWork.objects.filter(coach=self.coach).prefetch_related("private_lessons")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["work_month_is_paid"] = is_month_paid(self.object.payroll_month.month)
        context["work_date_is_future"] = self.object.work_date > central_today()
        return context


class CoachWorkDeleteView(CoachRequiredMixin, DeleteView):
    template_name = "coaches/work_confirm_delete.html"

    def get_queryset(self):
        return AdditionalWork.objects.filter(coach=self.coach)

    def get_object(self, queryset=None):
        work = super().get_object(queryset)
        if not self.request.user.is_staff:
            if is_month_paid(work.payroll_month.month):
                raise PermissionDenied("This payroll month has been paid and cannot be changed.")
            if work.work_date > central_today():
                raise PermissionDenied("Future work can only be changed by an administrator.")
        return work

    def get_success_url(self):
        return reverse("coaches:dashboard")


class StaffInvitationListView(StaffRequiredMixin, ListView):
    model = CoachInvitation
    context_object_name = "invitations"
    template_name = "coaches/admin_invitation_list.html"


class StaffInvitationCreateView(StaffRequiredMixin, CreateView):
    form_class = CoachInvitationForm
    template_name = "coaches/admin_invitation_form.html"
    success_url = reverse_lazy("coaches:admin-invitations")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        send_invitation_email(self.object)
        messages.success(self.request, f"Invitation created and emailed to {self.object.email}.")
        return response


class StaffInvitationResendView(StaffRequiredMixin, View):
    def post(self, request, pk):
        invitation = get_object_or_404(CoachInvitation, pk=pk)
        if invitation.is_valid:
            send_invitation_email(invitation)
            messages.success(request, f"Invitation emailed to {invitation.email}.")
        else:
            messages.error(request, "Only active invitations can be resent.")
        return redirect("coaches:admin-invitations")


class StaffInvitationRevokeView(StaffRequiredMixin, View):
    def post(self, request, pk):
        invitation = get_object_or_404(CoachInvitation, pk=pk)
        if invitation.is_valid:
            invitation.revoked_at = timezone.now()
            invitation.save(update_fields=["revoked_at"])
            messages.success(request, "Invitation revoked.")
        return redirect("coaches:admin-invitations")


class StaffCoachListView(StaffRequiredMixin, ListView):
    queryset = CoachProfile.objects.select_related("user")
    context_object_name = "coaches"
    template_name = "coaches/admin_coach_list.html"


class StaffCoachEditView(StaffRequiredMixin, FormView):
    form_class = CoachEditForm
    template_name = "coaches/admin_coach_rate_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.coach = get_object_or_404(CoachProfile.objects.select_related("user"), pk=kwargs["pk"])
        month = request.POST.get("month") or request.GET.get("month")
        self.month = requested_month(month, allow_future=True) if month else None
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["coach"] = self.coach
        return kwargs

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Coach profile updated.")
        return redirect(self.get_success_url())

    def get_success_url(self):
        if self.month:
            return reverse(
                "coaches:admin-coach-payroll",
                kwargs={"pk": self.coach.pk, "month": self.month.strftime("%Y-%m")},
            )
        return reverse("coaches:admin-coaches")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"coach": self.coach, "month": self.month})
        return context


class StaffPayrollSummaryView(StaffRequiredMixin, TemplateView):
    template_name = "coaches/admin_payroll_summary.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        month = requested_month(self.request.GET.get("month"), allow_future=True)
        payrolls = {
            payroll.coach_id: payroll
            for payroll in CoachMonthlyPayroll.objects.filter(month=month)
            .select_related("coach__user")
            .prefetch_related("work_items")
        }
        rows = [
            {"coach": coach, "payroll": payrolls.get(coach.pk)}
            for coach in CoachProfile.objects.select_related("user")
        ]
        context.update(
            {
                "month": month,
                "rows": rows,
                "payroll_month": PayrollMonth.objects.filter(month=month).first(),
                "month_is_future": month > date(central_today().year, central_today().month, 1),
            }
        )
        return context


class StaffPayrollInitializeView(StaffRequiredMixin, View):
    def post(self, request):
        month = requested_month(request.POST.get("month"), allow_future=True)
        initialize_payroll_month(month, initialized_by=request.user)
        messages.success(request, f"Initialized payroll for {month:%B %Y}.")
        return redirect(f"{reverse('coaches:admin-payroll')}?month={month:%Y-%m}")


class StaffPayrollMarkPaidView(StaffRequiredMixin, View):
    def post(self, request):
        month = requested_month(request.POST.get("month"))
        with transaction.atomic():
            payroll_month, _ = PayrollMonth.objects.select_for_update().get_or_create(month=month)
            if not payroll_month.is_paid:
                payroll_month.paid_at = timezone.now()
                payroll_month.paid_by = request.user
                payroll_month.save(update_fields=["paid_at", "paid_by"])
        messages.success(request, f"Marked {month:%B %Y} as paid.")
        return redirect(f"{reverse('coaches:admin-payroll')}?month={month:%Y-%m}")


class StaffPayrollReopenView(StaffRequiredMixin, View):
    def post(self, request):
        month = requested_month(request.POST.get("month"))
        payroll_month = get_object_or_404(PayrollMonth, month=month)
        payroll_month.paid_at = None
        payroll_month.paid_by = None
        payroll_month.save(update_fields=["paid_at", "paid_by"])
        messages.success(request, f"Reopened {month:%B %Y} for coach work changes.")
        return redirect(f"{reverse('coaches:admin-payroll')}?month={month:%Y-%m}")


class StaffCoachPayrollDetailView(StaffRequiredMixin, TemplateView):
    template_name = "coaches/admin_coach_payroll_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        month = requested_month(self.kwargs["month"], allow_future=True)
        coach = get_object_or_404(CoachProfile.objects.select_related("user"), pk=self.kwargs["pk"])
        payroll = (
            CoachMonthlyPayroll.objects.filter(coach=coach, month=month)
            .prefetch_related("work_items__private_lessons")
            .first()
        )
        context.update(
            {
                "coach": coach,
                "month": month,
                "payroll": payroll,
                "payroll_month": PayrollMonth.objects.filter(month=month).first(),
            }
        )
        return context


class StaffWorkCreateView(StaffRequiredMixin, WorkFormMixin, CreateView):
    form_class = StaffAdditionalWorkForm

    def get_initial(self):
        initial = super().get_initial()
        month = self.request.GET.get("month")
        if month:
            initial["work_date"] = requested_month(month, allow_future=True)
        return initial

    def get_coach(self):
        return self.selected_coach

    def post(self, request, *args, **kwargs):
        self.object = None
        form = self.get_form()
        if not form.is_valid():
            return self.form_invalid(form)
        self.selected_coach = form.cleaned_data["coach"]
        formset = self.get_formset(data=request.POST)
        if form.cleaned_data["activity"] == AdditionalWork.Activity.PRIVATE_LESSON and not formset.is_valid():
            return self.render_to_response(self.get_context_data(form=form, lesson_formset=formset))
        return self.form_and_formset_valid(form, formset)

    def success_url(self, work):
        return reverse(
            "coaches:admin-coach-payroll",
            kwargs={"pk": work.coach_id, "month": work.payroll_month.month.strftime("%Y-%m")},
        )


class StaffWorkUpdateView(StaffRequiredMixin, WorkFormMixin, UpdateView):
    model = AdditionalWork
    form_class = StaffAdditionalWorkForm

    def get_coach(self):
        return self.selected_coach

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        if not form.is_valid():
            return self.form_invalid(form)
        self.selected_coach = form.cleaned_data["coach"]
        formset = self.get_formset(data=request.POST, instance=self.object)
        if form.cleaned_data["activity"] == AdditionalWork.Activity.PRIVATE_LESSON and not formset.is_valid():
            return self.render_to_response(self.get_context_data(form=form, lesson_formset=formset))
        return self.form_and_formset_valid(form, formset)

    def success_url(self, work):
        return reverse(
            "coaches:admin-coach-payroll",
            kwargs={"pk": work.coach_id, "month": work.payroll_month.month.strftime("%Y-%m")},
        )


class StaffWorkDetailView(StaffRequiredMixin, DetailView):
    model = AdditionalWork
    template_name = "coaches/admin_work_detail.html"

    def get_queryset(self):
        return AdditionalWork.objects.select_related("coach__user", "payroll_month").prefetch_related(
            "private_lessons"
        )


class StaffWorkDeleteView(StaffRequiredMixin, DeleteView):
    model = AdditionalWork
    template_name = "coaches/work_confirm_delete.html"

    def get_success_url(self):
        work = self.object
        return reverse(
            "coaches:admin-coach-payroll",
            kwargs={"pk": work.coach_id, "month": work.payroll_month.month.strftime("%Y-%m")},
        )
