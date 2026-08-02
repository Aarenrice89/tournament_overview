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
        self.assertContains(response, reverse("landing"))
        self.assertContains(response, "portal-header--admin")
        self.assertContains(response, "Tournament Overview")
        self.assertContains(response, "Teams")
        self.assertNotContains(response, f'href="{reverse("admin:index")}"')
        self.assertContains(response, 'class="btn btn-outline-light" type="submit">Log out</button>')

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
