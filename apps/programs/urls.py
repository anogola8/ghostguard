from django.urls import path
from . import views

app_name = "programs"

urlpatterns = [
    path("rounds/", views.RoundListView.as_view(), name="round_list"),
    path("rounds/<int:pk>/", views.RoundDetailView.as_view(), name="round_detail"),
    path("rounds/<int:pk>/lock/", views.LockRoundView.as_view(), name="lock_round"),
    path("rounds/<int:pk>/pay/", views.ProcessPayoutsView.as_view(), name="process_payouts"),
]
