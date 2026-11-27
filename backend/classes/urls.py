from django.urls import path

from . import views

urlpatterns = [
    path("", views.ClassListView.as_view(), name="classes"),
    path("join/<str:code>/", views.JoinView.as_view(), name="class-join"),
    path("teach/<str:code>/", views.TeachJoinView.as_view(), name="class-teach"),
    path("<int:pk>/", views.ClassDetailView.as_view(), name="class-detail"),
    path("<int:pk>/students/<int:user_id>/", views.StudentDetailView.as_view(), name="class-student"),
    path("<int:pk>/members/<int:user_id>/<str:action>/", views.MemberView.as_view(), name="class-member"),
    path("<int:pk>/assignments/", views.AssignmentsView.as_view(), name="class-assignments"),
    path("<int:pk>/assignments/<int:aid>/", views.AssignmentDetailView.as_view(), name="class-assignment"),
    path("<int:pk>/hardest/", views.HardestView.as_view(), name="class-hardest"),
    path("<int:pk>/leaderboard/", views.LeaderboardView.as_view(), name="class-leaderboard"),
    path("<int:pk>/announce/", views.AnnounceView.as_view(), name="class-announce"),
    path("<int:pk>/export.csv", views.ExportView.as_view(), name="class-export"),
    path("<int:pk>/<str:action>/", views.ClassActionView.as_view(), name="class-action"),
]
