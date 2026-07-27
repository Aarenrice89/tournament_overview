from django.contrib import admin

from .models import Team, Tournament, TournamentRegistration


class TournamentRegistrationInline(admin.TabularInline):
    model = TournamentRegistration
    extra = 0


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "end_date", "location", "registration_opens_date")
    list_filter = ("stay_to_play", "start_date")
    search_fields = ("name", "location", "organizing_company")
    inlines = [TournamentRegistrationInline]


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    search_fields = ("name",)
