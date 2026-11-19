from django.urls import path

from . import views

urlpatterns = [
    path("scan/", views.ScanView.as_view(), name="ocr-scan"),
    path("quota/", views.ScanQuotaView.as_view(), name="ocr-quota"),
]
