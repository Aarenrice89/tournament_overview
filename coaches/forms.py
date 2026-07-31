from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms import BaseInlineFormSet, inlineformset_factory

from .models import AdditionalWork, CoachInvitation, CoachProfile, PrivateLesson
from .services import PRIVATE_LESSON_RATES, central_today, prepare_work


class BootstrapFormMixin:
    def apply_bootstrap_classes(self):
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "form-check-input"
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = "form-select"
            else:
                field.widget.attrs["class"] = "form-control"


class CoachAuthenticationForm(BootstrapFormMixin, AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class CoachInvitationForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = CoachInvitation
        fields = ["email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class CoachRegistrationForm(BootstrapFormMixin, forms.Form):
    email = forms.EmailField(disabled=True)
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    username = forms.CharField(max_length=150)
    password1 = forms.CharField(label="Password", strip=False, widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm password", strip=False, widget=forms.PasswordInput)

    def __init__(self, *args, invitation, **kwargs):
        super().__init__(*args, **kwargs)
        self.invitation = invitation
        self.fields["email"].initial = invitation.email
        self.apply_bootstrap_classes()

    def clean_username(self):
        username = self.cleaned_data["username"]
        if get_user_model().objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is already in use.")
        return username

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "The passwords do not match.")
        return cleaned_data


class CoachEditForm(BootstrapFormMixin, forms.Form):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    monthly_base_rate = forms.DecimalField(required=False, min_value=0, decimal_places=2, max_digits=10)
    additional_hourly_rate = forms.DecimalField(required=False, min_value=0, decimal_places=2, max_digits=10)

    def __init__(self, *args, coach, **kwargs):
        super().__init__(*args, **kwargs)
        self.coach = coach
        self.fields["first_name"].initial = coach.user.first_name
        self.fields["last_name"].initial = coach.user.last_name
        self.fields["email"].initial = coach.user.email
        self.fields["monthly_base_rate"].initial = coach.monthly_base_rate
        self.fields["additional_hourly_rate"].initial = coach.additional_hourly_rate
        self.apply_bootstrap_classes()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if get_user_model().objects.filter(email__iexact=email).exclude(pk=self.coach.user_id).exists():
            raise forms.ValidationError("Another account already uses this email address.")
        return email

    @transaction.atomic
    def save(self):
        user = self.coach.user
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.email = self.cleaned_data["email"]
        user.save(update_fields=["first_name", "last_name", "email"])
        self.coach.monthly_base_rate = self.cleaned_data["monthly_base_rate"]
        self.coach.additional_hourly_rate = self.cleaned_data["additional_hourly_rate"]
        self.coach.save(update_fields=["monthly_base_rate", "additional_hourly_rate", "updated_at"])
        return self.coach


class AdditionalWorkForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = AdditionalWork
        fields = ["activity", "work_date", "hours_worked", "tournament_days", "notes"]
        widgets = {
            "work_date": forms.DateInput(attrs={"type": "date"}),
            "hours_worked": forms.NumberInput(attrs={"min": "0.5", "max": "12", "step": "0.5"}),
            "tournament_days": forms.Select(choices=[(day, day) for day in range(1, 5)]),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, coach=None, allow_future=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.coach = coach
        self.allow_future = allow_future
        self.existing_hourly_rate = (
            self.instance.hourly_rate_snapshot
            if self.instance.pk and self.instance.activity in AdditionalWork.HOURLY_ACTIVITIES
            else None
        )
        self.apply_bootstrap_classes()
        if not self.instance.pk and "work_date" not in self.initial:
            self.fields["work_date"].initial = central_today()
        if not self.allow_future:
            self.fields["work_date"].widget.attrs["max"] = central_today().isoformat()
        self.fields["tournament_days"].label = "Tournament length - days"

    def clean(self):
        cleaned_data = super().clean()
        activity = cleaned_data.get("activity")
        work_date = cleaned_data.get("work_date")
        hours_worked = cleaned_data.get("hours_worked")
        tournament_days = cleaned_data.get("tournament_days")

        if work_date and not self.allow_future and work_date > central_today():
            self.add_error("work_date", "Work dates cannot be in the future.")

        if activity in AdditionalWork.HOURLY_ACTIVITIES:
            if hours_worked is None:
                self.add_error("hours_worked", "Hourly work requires total hours worked.")
            elif (hours_worked * 2) % 1:
                self.add_error("hours_worked", "Hours must be in half-hour increments.")
            if tournament_days is not None:
                self.add_error("tournament_days", "Hourly work cannot include tournament days.")
        elif activity == AdditionalWork.Activity.TOURNAMENT:
            if tournament_days is None:
                self.add_error("tournament_days", "Tournament work requires the number of days.")
            if hours_worked is not None:
                self.add_error("hours_worked", "Tournament work cannot include hourly work.")
        elif activity == AdditionalWork.Activity.PRIVATE_LESSON:
            if hours_worked is not None:
                self.add_error("hours_worked", "Private lessons cannot include hourly work.")
            if tournament_days is not None:
                self.add_error("tournament_days", "Private lessons cannot include tournament days.")
        return cleaned_data

    def save_for_coach(self, coach, allow_paid=False, allow_future=False):
        work = super().save(commit=False)
        work.coach = coach
        try:
            prepare_work(
                work,
                hourly_rate_snapshot=self.existing_hourly_rate,
                allow_paid=allow_paid,
                allow_future=allow_future,
            )
        except ValidationError as error:
            raise forms.ValidationError(error) from error
        work.save()
        return work


class StaffAdditionalWorkForm(AdditionalWorkForm):
    coach = forms.ModelChoiceField(queryset=CoachProfile.objects.select_related("user"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["coach"].label_from_instance = lambda coach: str(coach)
        if self.instance.pk:
            self.fields["coach"].initial = self.instance.coach


class PrivateLessonForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = PrivateLesson
        fields = ["children_coached"]
        widgets = {"children_coached": forms.Select(choices=[(count, count) for count in range(1, 6)])}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()

    def save(self, commit=True):
        lesson = super().save(commit=False)
        lesson.payment_amount = PRIVATE_LESSON_RATES[lesson.children_coached]
        if commit:
            lesson.save()
        return lesson


class RequiredPrivateLessonInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        has_lesson = any(form.cleaned_data and not form.cleaned_data.get("DELETE", False) for form in self.forms)
        if not has_lesson:
            raise forms.ValidationError("Add at least one private lesson.")


PrivateLessonFormSet = inlineformset_factory(
    AdditionalWork,
    PrivateLesson,
    form=PrivateLessonForm,
    formset=RequiredPrivateLessonInlineFormSet,
    extra=1,
    can_delete=True,
)
