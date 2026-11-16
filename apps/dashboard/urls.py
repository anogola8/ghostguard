from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.DonorDashboardView.as_view(), name="index"),
    path("flags/", views.FlagQueueView.as_view(), name="flag_queue"),
    path("disputes/", views.DisputeQueueView.as_view(), name="disputes"),
    path("settings/", views.SystemSettingsView.as_view(), name="settings"),
    path("security/", views.SecurityDashboardView.as_view(), name="security"),
    path("attack-log/", views.AttackLogView.as_view(), name="attack_log"),
    path("directory/", views.BeneficiaryDirectoryView.as_view(), name="directory"),
    path("public/", views.PublicTransparencyView.as_view(), name="public"),
    path("report/", views.PDFReportView.as_view(), name="report"),
    path("report/pdf/", views.download_pdf, name="download_pdf"),
]
