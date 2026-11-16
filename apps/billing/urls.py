from django.urls import path
from . import views

app_name = "billing"
urlpatterns = [
    path("pricing/", views.PricingView.as_view(), name="pricing"),
    path("upgrade/", views.UpgradeView.as_view(), name="upgrade"),
    path("api/audit/<str:api_key>/", views.donor_api_audit, name="donor_api"),
]
