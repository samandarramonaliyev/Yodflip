from django.urls import path

from . import views

urlpatterns = [
    path("events/", views.ShareEventView.as_view(), name="share-events"),
    path("upload/", views.UploadView.as_view(), name="share-upload"),
    path("render/", views.RenderView.as_view(), name="share-render"),
]
