from django.contrib import admin
from django.urls import include, path
from apps.audit.views import HomeView

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls", namespace="accounts")),
    path("audit/", include("apps.audit.urls", namespace="audit")),
    path("beneficiaries/", include("apps.beneficiaries.urls", namespace="beneficiaries")),
    path("programs/", include("apps.programs.urls", namespace="programs")),
    path("dashboard/", include("apps.dashboard.urls", namespace="dashboard")),
    path("billing/", include("apps.billing.urls", namespace="billing")),
]
