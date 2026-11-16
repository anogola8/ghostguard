from django.contrib import admin
from .models import Beneficiary

@admin.register(Beneficiary)
class BeneficiaryAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone", "village", "status", "registered_at")
    list_filter = ("status", "program")
    search_fields = ("full_name", "phone", "village")
