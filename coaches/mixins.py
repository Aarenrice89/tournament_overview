from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


class CoachRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = "coaches:login"

    def test_func(self):
        return hasattr(self.request.user, "coach_profile")

    @property
    def coach(self):
        return self.request.user.coach_profile


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = "coaches:login"

    def test_func(self):
        return self.request.user.is_staff
