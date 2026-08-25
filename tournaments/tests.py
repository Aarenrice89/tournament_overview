from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import Team, Tournament, TournamentRegistration


class TournamentModelTests(TestCase):
    def tournament(self, **overrides):
        values = {
            "name": "Spring Classic",
            "start_date": date(2026, 4, 10),
            "end_date": date(2026, 4, 12),
            "location": "Austin, TX",
            "registration_opens_date": date(2026, 1, 10),
            "registration_closes_date": date(2026, 3, 10),
        }
        values.update(overrides)
        return Tournament(**values)

    def test_tournament_dates_are_validated(self):
        tournament = self.tournament(end_date=date(2026, 4, 9))

        with self.assertRaises(ValidationError):
            tournament.full_clean()

    def test_registration_progression_is_validated(self):
        tournament = self.tournament()
        tournament.save()
        team = Team.objects.create(name="Thunder 16U")
        registration = TournamentRegistration(tournament=tournament, team=team, is_paid=True)

        with self.assertRaises(ValidationError):
            registration.full_clean()

    def test_registration_status_defaults_to_pending(self):
        tournament = self.tournament()
        tournament.save()
        team = Team.objects.create(name="Thunder 16U")

        registration = TournamentRegistration.objects.create(tournament=tournament, team=team)

        self.assertEqual(registration.registration_status, TournamentRegistration.RegistrationStatus.PENDING)
        self.assertEqual(registration.get_registration_status_display(), "Pending")


class TournamentViewTests(TestCase):
    def setUp(self):
        self.staff_user = get_user_model().objects.create_user(
            username="staff", password="test-password", is_staff=True
        )
        self.tournament = Tournament.objects.create(
            name="Spring Classic",
            start_date=date(2026, 4, 10),
            end_date=date(2026, 4, 12),
            location="Austin, TX",
            registration_opens_date=date(2026, 1, 10),
            registration_closes_date=date(2026, 3, 10),
        )

    def test_overview_requires_staff_login(self):
        response = self.client.get(reverse("tournaments:list"))

        self.assertRedirects(response, f"{reverse('coaches:login')}?next=/tournaments/")

    def test_overview_displays_team_status(self):
        team = Team.objects.create(name="Thunder 16U")
        TournamentRegistration.objects.create(
            tournament=self.tournament,
            team=team,
            is_registered=True,
            is_paid=True,
            rosters_entered=True,
        )
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("tournaments:list"))

        self.assertContains(response, "Spring Classic")
        self.assertContains(response, "Thunder 16U")
        self.assertContains(response, "Registered + paid + rosters")
        self.assertContains(response, "Registration status")
        self.assertContains(response, "Pending")
        self.assertContains(response, reverse("landing"))
        self.assertContains(response, "portal-header--admin")
        self.assertContains(response, "Tournament Overview")
        self.assertContains(response, "Teams")
        self.assertNotContains(response, f'href="{reverse("admin:index")}"')
        self.assertContains(response, 'class="btn btn-outline-light" type="submit">Log out</button>')

    def test_overview_sorts_pending_before_accepted_then_by_team_name(self):
        registrations = [
            ("Zulu 16U", TournamentRegistration.RegistrationStatus.PENDING),
            ("Bravo 16U", TournamentRegistration.RegistrationStatus.ACCEPTED),
            ("Alpha 16U", TournamentRegistration.RegistrationStatus.PENDING),
            ("Able 16U", TournamentRegistration.RegistrationStatus.ACCEPTED),
        ]
        for team_name, registration_status in registrations:
            TournamentRegistration.objects.create(
                tournament=self.tournament,
                team=Team.objects.create(name=team_name),
                registration_status=registration_status,
            )
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("tournaments:list"))

        content = response.content.decode()
        positions = [content.index(team_name) for team_name in ["Alpha 16U", "Zulu 16U", "Able 16U", "Bravo 16U"]]
        self.assertEqual(positions, sorted(positions))

    def test_overview_keeps_readiness_as_the_primary_registration_sort(self):
        accepted_team = Team.objects.create(name="Accepted 16U")
        pending_team = Team.objects.create(name="Pending 16U")
        TournamentRegistration.objects.create(
            tournament=self.tournament,
            team=accepted_team,
            registration_status=TournamentRegistration.RegistrationStatus.ACCEPTED,
        )
        TournamentRegistration.objects.create(
            tournament=self.tournament,
            team=pending_team,
            is_registered=True,
            registration_status=TournamentRegistration.RegistrationStatus.PENDING,
        )
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("tournaments:list"))

        content = response.content.decode()
        self.assertLess(content.index("Accepted 16U"), content.index("Pending 16U"))

    def test_staff_can_change_registration_status_from_tournament_form(self):
        team = Team.objects.create(name="Thunder 16U")
        registration = TournamentRegistration.objects.create(tournament=self.tournament, team=team)
        self.client.force_login(self.staff_user)

        detail_response = self.client.get(reverse("tournaments:detail", kwargs={"pk": self.tournament.pk}))

        self.assertContains(detail_response, "Registration status")
        self.assertContains(detail_response, 'name="registrations-0-registration_status"', count=2)
        self.assertContains(detail_response, 'class="btn-check"')

        response = self.client.post(
            reverse("tournaments:detail", kwargs={"pk": self.tournament.pk}),
            {
                "name": self.tournament.name,
                "start_date": self.tournament.start_date.isoformat(),
                "end_date": self.tournament.end_date.isoformat(),
                "location": self.tournament.location,
                "registration_opens_date": self.tournament.registration_opens_date.isoformat(),
                "registration_closes_date": self.tournament.registration_closes_date.isoformat(),
                "registration_link": "",
                "cost_per_team": "0.00",
                "organizing_company": "",
                "team_minimum": "0",
                "stay_to_play_link": "",
                "stay_to_play_notes": "",
                "coach_hotel": "",
                "hotel_location": "",
                "number_of_rooms": "0",
                "cost_per_room": "0.00",
                "coaches_notes": "",
                "travel": "",
                "flight_number": "",
                "number_of_coaches": "0",
                "travel_notes": "",
                "registrations-TOTAL_FORMS": "1",
                "registrations-INITIAL_FORMS": "1",
                "registrations-MIN_NUM_FORMS": "0",
                "registrations-MAX_NUM_FORMS": "1000",
                "registrations-0-id": str(registration.pk),
                "registrations-0-team": str(team.pk),
                "registrations-0-registration_status": TournamentRegistration.RegistrationStatus.ACCEPTED,
            },
        )

        self.assertRedirects(response, reverse("tournaments:list"))
        registration.refresh_from_db()
        self.assertEqual(registration.registration_status, TournamentRegistration.RegistrationStatus.ACCEPTED)

    def test_overview_filters_tournaments_by_search_query(self):
        Tournament.objects.create(
            name="Summer Open",
            start_date=date(2026, 6, 10),
            end_date=date(2026, 6, 12),
            location="Dallas, TX",
            registration_opens_date=date(2026, 2, 10),
            registration_closes_date=date(2026, 5, 10),
        )
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("tournaments:list"), {"q": "summer"})

        self.assertContains(response, "Summer Open")
        self.assertNotContains(response, "Spring Classic")

    def test_overview_returns_results_fragment_for_async_search(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(
            reverse("tournaments:list"), {"q": "spring"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )

        self.assertContains(response, "Spring Classic")
        self.assertNotContains(response, "Tournament overview")

    def test_staff_can_create_a_tournament(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("tournaments:create"),
            {
                "name": "Summer Open",
                "start_date": "2026-06-10",
                "end_date": "2026-06-12",
                "location": "Dallas, TX",
                "registration_opens_date": "2026-02-10",
                "registration_closes_date": "2026-05-10",
                "registration_link": "",
                "cost_per_team": "450.00",
                "organizing_company": "Tournament Co",
                "team_minimum": "8",
                "stay_to_play": "",
                "stay_to_play_link": "",
                "stay_to_play_notes": "",
                "coach_hotel": "",
                "hotel_location": "",
                "number_of_rooms": "0",
                "cost_per_room": "0.00",
                "coaches_notes": "",
                "travel": "",
                "flight_number": "",
                "number_of_coaches": "0",
                "travel_notes": "",
            },
        )

        tournament = Tournament.objects.get(name="Summer Open")
        self.assertRedirects(response, reverse("tournaments:detail", kwargs={"pk": tournament.pk}))


class ApiDocumentationTests(TestCase):
    def test_schema_is_public_and_returns_openapi_document(self):
        response = self.client.get(reverse("api-schema"), HTTP_ACCEPT="application/vnd.oai.openapi+json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["openapi"].startswith("3."))

    def test_swagger_ui_is_public_and_uses_schema_route(self):
        response = self.client.get(reverse("api-docs"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("api-schema"))
