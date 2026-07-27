from django.urls import path

from . import views

app_name = "tournaments"

urlpatterns = [
    path("", views.TournamentListView.as_view(), name="list"),
    path("tournaments/add/", views.TournamentCreateView.as_view(), name="create"),
    path("tournaments/<int:pk>/", views.TournamentUpdateView.as_view(), name="detail"),
    path("tournaments/<int:pk>/delete/", views.TournamentDeleteView.as_view(), name="delete"),
    path("teams/", views.TeamListView.as_view(), name="team-list"),
    path("teams/add/", views.TeamCreateView.as_view(), name="team-create"),
    path("teams/<int:pk>/", views.TeamUpdateView.as_view(), name="team-update"),
]
