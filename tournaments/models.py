from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Team(models.Model):
    name = models.CharField(max_length=150, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Tournament(models.Model):
    name = models.CharField(max_length=200)
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    location = models.CharField(max_length=255)
    registration_opens_date = models.DateField(blank=True, null=True)
    registration_closes_date = models.DateField(blank=True, null=True)
    registration_link = models.URLField(blank=True)
    cost_per_team = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    organizing_company = models.CharField(max_length=200, blank=True)
    team_minimum = models.PositiveIntegerField(default=0)
    stay_to_play = models.BooleanField(default=False)
    stay_to_play_link = models.URLField(blank=True)
    stay_to_play_notes = models.TextField(blank=True)
    coach_hotel = models.CharField(max_length=200, blank=True)
    hotel_location = models.CharField(max_length=255, blank=True)
    hotel_open_date = models.DateField(blank=True, null=True)
    hotel_close_date = models.DateField(blank=True, null=True)
    number_of_rooms = models.PositiveIntegerField(default=0)
    cost_per_room = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    coaches_notes = models.TextField(blank=True)
    travel = models.CharField(max_length=200, blank=True)
    flight_number = models.CharField(max_length=100, blank=True)
    number_of_coaches = models.PositiveIntegerField(default=0)
    travel_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_date", "name"]

    def __str__(self):
        return self.name

    def clean(self):
        errors = {}
        if self.end_date and self.start_date and self.end_date < self.start_date:
            errors["end_date"] = "The end date cannot be before the start date."
        if (
            self.registration_opens_date
            and self.registration_closes_date
            and self.registration_closes_date < self.registration_opens_date
        ):
            errors["registration_closes_date"] = "Registration cannot close before it opens."
        if self.hotel_open_date and self.hotel_close_date and self.hotel_close_date < self.hotel_open_date:
            errors["hotel_close_date"] = "Hotel dates cannot close before they open."
        if errors:
            raise ValidationError(errors)


class TournamentRegistration(models.Model):
    class RegistrationStatus(models.TextChoices):
        NOT_APPLICABLE = "na", "N/A"
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"

    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name="registrations")
    team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name="tournament_registrations")
    is_registered = models.BooleanField(default=False)
    is_paid = models.BooleanField(default=False)
    rosters_entered = models.BooleanField(default=False)
    hotel_compliant = models.BooleanField(default=False)
    number_of_rooms_required = models.PositiveIntegerField(default=0)
    registration_status = models.CharField(
        max_length=8,
        choices=RegistrationStatus.choices,
        default=RegistrationStatus.NOT_APPLICABLE,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tournament", "team"], name="unique_tournament_team"),
            models.CheckConstraint(
                condition=~Q(is_paid=True) | Q(is_registered=True),
                name="payment_requires_registration",
            ),
            models.CheckConstraint(
                condition=~Q(rosters_entered=True) | (Q(is_registered=True) & Q(is_paid=True)),
                name="rosters_require_registration_and_payment",
            ),
            models.CheckConstraint(
                condition=(
                    Q(is_registered=False, registration_status="na")
                    | (Q(is_registered=True) & ~Q(registration_status="na"))
                ),
                name="registration_status_matches_registered",
            ),
        ]

    def __str__(self):
        return f"{self.team} - {self.tournament}"

    def clean(self):
        self._synchronize_registration_status()
        errors = {}
        if self.is_paid and not self.is_registered:
            errors["is_paid"] = "A team must be registered before it can be marked paid."
        if self.rosters_entered and not self.is_paid:
            errors["rosters_entered"] = "A team must be paid before rosters can be marked entered."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        previous_status = self.registration_status
        self._synchronize_registration_status()
        if kwargs.get("update_fields") is not None:
            update_fields = set(kwargs["update_fields"])
            if "is_registered" in update_fields or self.registration_status != previous_status:
                update_fields.add("registration_status")
            kwargs["update_fields"] = update_fields
        super().save(*args, **kwargs)

    def _synchronize_registration_status(self):
        if not self.is_registered:
            self.registration_status = self.RegistrationStatus.NOT_APPLICABLE
        elif self.registration_status == self.RegistrationStatus.NOT_APPLICABLE:
            self.registration_status = self.RegistrationStatus.PENDING

    @property
    def status_label(self):
        if self.rosters_entered:
            return "Registered + paid + rosters"
        if self.is_paid:
            return "Registered + paid"
        if self.is_registered:
            return "Registered"
        return "Not registered"

    @property
    def status_key(self):
        if self.rosters_entered:
            return "complete"
        if self.is_paid:
            return "paid"
        if self.is_registered:
            return "registered"
        return "pending"
