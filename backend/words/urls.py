from django.urls import path

from . import views

urlpatterns = [
    path("levels/", views.LevelsView.as_view(), name="levels"),
    path("levels/<str:level>/", views.LevelWordsView.as_view(), name="level-words"),
    path("search/", views.SearchView.as_view(), name="word-search"),
    path("lists/want/add/", views.WantView.as_view(), name="want-add"),
    path("lists/want/bulk/", views.BulkWantView.as_view(), name="want-bulk"),
    path("lists/<str:which>/", views.ListView.as_view(), name="word-list"),
    path("mine/<int:pk>/", views.UserWordDetailView.as_view(), name="userword-detail"),
]
