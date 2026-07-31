from django.urls import path

from . import views

app_name = "coaches"

urlpatterns = [
    path("", views.CoachDashboardView.as_view(), name="dashboard"),
    path("login/", views.CoachLoginView.as_view(), name="login"),
    path("logout/", views.CoachLogoutView.as_view(), name="logout"),
    path("invitations/<uuid:token>/register/", views.CoachRegistrationView.as_view(), name="register"),
    path("work/add/", views.CoachWorkCreateView.as_view(), name="work-add"),
    path("work/<int:pk>/", views.CoachWorkDetailView.as_view(), name="work-detail"),
    path("work/<int:pk>/edit/", views.CoachWorkUpdateView.as_view(), name="work-edit"),
    path("work/<int:pk>/delete/", views.CoachWorkDeleteView.as_view(), name="work-delete"),
    path("admin/", views.StaffPayrollSummaryView.as_view(), name="admin-payroll"),
    path("admin/months/initialize/", views.StaffPayrollInitializeView.as_view(), name="admin-payroll-initialize"),
    path("admin/months/mark-paid/", views.StaffPayrollMarkPaidView.as_view(), name="admin-payroll-mark-paid"),
    path("admin/months/reopen/", views.StaffPayrollReopenView.as_view(), name="admin-payroll-reopen"),
    path("admin/coaches/", views.StaffCoachListView.as_view(), name="admin-coaches"),
    path("admin/coaches/<int:pk>/edit/", views.StaffCoachEditView.as_view(), name="admin-coach-edit"),
    path(
        "admin/coaches/<int:pk>/<str:month>/",
        views.StaffCoachPayrollDetailView.as_view(),
        name="admin-coach-payroll",
    ),
    path("admin/invitations/", views.StaffInvitationListView.as_view(), name="admin-invitations"),
    path("admin/invitations/add/", views.StaffInvitationCreateView.as_view(), name="admin-invitation-add"),
    path(
        "admin/invitations/<int:pk>/resend/", views.StaffInvitationResendView.as_view(), name="admin-invitation-resend"
    ),
    path(
        "admin/invitations/<int:pk>/revoke/", views.StaffInvitationRevokeView.as_view(), name="admin-invitation-revoke"
    ),
    path("admin/work/add/", views.StaffWorkCreateView.as_view(), name="admin-work-add"),
    path("admin/work/<int:pk>/", views.StaffWorkDetailView.as_view(), name="admin-work-detail"),
    path("admin/work/<int:pk>/edit/", views.StaffWorkUpdateView.as_view(), name="admin-work-edit"),
    path("admin/work/<int:pk>/delete/", views.StaffWorkDeleteView.as_view(), name="admin-work-delete"),
]
