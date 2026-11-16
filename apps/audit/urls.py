from django.urls import path

from . import views

app_name = "audit"

urlpatterns = [
    path("integrity/", views.IntegrityCheckView.as_view(), name="integrity"),
    path("acknowledge-tamper/", views.acknowledge_tamper, name="acknowledge_tamper"),
]