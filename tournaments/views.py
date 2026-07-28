from urllib.parse import urlencode

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.db.models import Case, F, IntegerField, Prefetch, Value, When
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from .forms import TeamForm, TournamentForm, TournamentRegistrationFormSet
from .models import Team, Tournament, TournamentRegistration


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = "admin:login"

    def test_func(self):
        return self.request.user.is_staff


class TournamentListView(StaffRequiredMixin, ListView):
    model = Tournament
    context_object_name = "tournaments"
    template_name = "tournaments/tournament_list.html"

    def get_queryset(self):
        registrations = (
            TournamentRegistration.objects.select_related("team")
            .annotate(
                status_order=Case(
                    When(rosters_entered=True, then=Value(3)),
                    When(is_paid=True, then=Value(2)),
                    When(is_registered=True, then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            )
            .order_by("status_order", "team__name")
        )
        tournaments = Tournament.objects.prefetch_related(Prefetch("registrations", queryset=registrations))
        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            tournaments = tournaments.filter(name__icontains=search_query)
        sort = self.request.GET.get("sort")
        if sort == "date":
            return tournaments.order_by(F("start_date").asc(nulls_last=True), "name")
        if sort == "-date":
            return tournaments.order_by(F("start_date").desc(nulls_last=True), "name")
        if sort == "registration_opens":
            return tournaments.order_by(F("registration_opens_date").asc(nulls_last=True), "name")
        if sort == "-registration_opens":
            return tournaments.order_by(F("registration_opens_date").desc(nulls_last=True), "name")
        return tournaments

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        current_sort = self.request.GET.get("sort")
        search_query = self.request.GET.get("q", "").strip()
        context["current_sort"] = current_sort
        context["search_query"] = search_query
        context["sort_query_prefix"] = f"{urlencode({'q': search_query})}&" if search_query else ""
        context["date_sort"] = "-date" if current_sort == "date" else "date"
        context["registration_opens_sort"] = (
            "-registration_opens" if current_sort == "registration_opens" else "registration_opens"
        )
        return context


class TournamentCreateView(StaffRequiredMixin, CreateView):
    model = Tournament
    form_class = TournamentForm
    template_name = "tournaments/tournament_form.html"

    def get_success_url(self):
        return reverse_lazy("tournaments:detail", kwargs={"pk": self.object.pk})


class TournamentUpdateView(StaffRequiredMixin, UpdateView):
    model = Tournament
    form_class = TournamentForm
    template_name = "tournaments/tournament_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["formset"] = kwargs.get("formset") or TournamentRegistrationFormSet(instance=self.object)
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        formset = TournamentRegistrationFormSet(request.POST, instance=self.object)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                self.object = form.save()
                formset.save()
            return self.form_valid(form)
        return self.render_to_response(self.get_context_data(form=form, formset=formset))

    def get_success_url(self):
        return reverse_lazy("tournaments:list")


class TournamentDeleteView(StaffRequiredMixin, DeleteView):
    model = Tournament
    template_name = "tournaments/tournament_confirm_delete.html"
    success_url = reverse_lazy("tournaments:list")


class TeamListView(StaffRequiredMixin, ListView):
    model = Team
    context_object_name = "teams"
    template_name = "tournaments/team_list.html"


class TeamCreateView(StaffRequiredMixin, CreateView):
    model = Team
    form_class = TeamForm
    template_name = "tournaments/team_form.html"
    success_url = reverse_lazy("tournaments:team-list")


class TeamTournamentListView(StaffRequiredMixin, DetailView):
    model = Team
    context_object_name = "team"
    template_name = "tournaments/team_tournament_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["registrations"] = self.object.tournament_registrations.select_related("tournament").order_by(
            "tournament__start_date", "tournament__name"
        )
        return context


class TeamUpdateView(StaffRequiredMixin, UpdateView):
    model = Team
    form_class = TeamForm
    template_name = "tournaments/team_form.html"
    success_url = reverse_lazy("tournaments:team-list")
