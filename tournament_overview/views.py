from django.urls import reverse
from django.views.generic import TemplateView


class PortalLandingView(TemplateView):
    template_name = "tournament_overview/landing.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        applications = []
        if self.request.user.is_authenticated:
            if self.request.user.is_staff:
                applications.extend(
                    [
                        {
                            "title": "Tournament Overview",
                            "description": "Manage tournaments, teams, and registrations.",
                            "url": reverse("tournaments:list"),
                        },
                        {
                            "title": "Payroll Admin",
                            "description": "Manage coach invitations, rates, and monthly payroll.",
                            "url": reverse("coaches:admin-payroll"),
                        },
                    ]
                )
            if hasattr(self.request.user, "coach_profile"):
                applications.append(
                    {
                        "title": "Coach Payroll",
                        "description": "Record and review your additional work.",
                        "url": reverse("coaches:dashboard"),
                    }
                )
        context["applications"] = applications
        return context
