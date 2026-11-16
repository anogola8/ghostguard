from django.urls import path
from . import views

app_name = "beneficiaries"

urlpatterns = [
    path("register/", views.RegisterBeneficiaryView.as_view(), name="register"),
    path("bulk/", views.BulkUploadView.as_view(), name="bulk_upload"),
    path("card/<str:public_id>/", views.PublicBeneficiaryCardView.as_view(), name="public_card"),
    path("receipt/<int:pk>/", views.PayoutReceiptView.as_view(), name="payout_receipt"),
]
