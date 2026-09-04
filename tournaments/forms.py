from django import forms
from django.forms import inlineformset_factory

from .models import Team, Tournament, TournamentRegistration


class BootstrapFormMixin:
    def apply_bootstrap_classes(self):
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "form-check-input"
            elif isinstance(field.widget, forms.RadioSelect):
                field.widget.attrs["class"] = "btn-check"
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = "form-select"
            else:
                field.widget.attrs["class"] = "form-control"


class TournamentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Tournament
        fields = [
            "name",
            "start_date",
            "end_date",
            "location",
            "registration_opens_date",
            "registration_closes_date",
            "registration_link",
            "cost_per_team",
            "organizing_company",
            "team_minimum",
            "stay_to_play",
            "stay_to_play_link",
            "stay_to_play_notes",
            "coach_hotel",
            "hotel_location",
            "hotel_open_date",
            "hotel_close_date",
            "number_of_rooms",
            "cost_per_room",
            "coaches_notes",
            "travel",
            "flight_number",
            "number_of_coaches",
            "travel_notes",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "registration_opens_date": forms.DateInput(attrs={"type": "date"}),
            "registration_closes_date": forms.DateInput(attrs={"type": "date"}),
            "hotel_open_date": forms.DateInput(attrs={"type": "date"}),
            "hotel_close_date": forms.DateInput(attrs={"type": "date"}),
            "cost_per_team": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "cost_per_room": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class TeamForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Team
        fields = ["name"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class TournamentRegistrationForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = TournamentRegistration
        fields = [
            "team",
            "is_registered",
            "is_paid",
            "rosters_entered",
            "hotel_compliant",
            "number_of_rooms_required",
            "registration_status",
        ]
        widgets = {
            "registration_status": forms.RadioSelect(attrs={"class": "btn-check"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


TournamentRegistrationFormSet = inlineformset_factory(
    Tournament,
    TournamentRegistration,
    form=TournamentRegistrationForm,
    extra=1,
    can_delete=True,
)
