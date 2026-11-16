from django.contrib import admin
from .models import Program, DisbursementRound, Payout

@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ("name", "donor", "start_date", "end_date")

@admin.register(DisbursementRound)
class DisbursementRoundAdmin(admin.ModelAdmin):
    list_display = ("program", "amount", "status", "created_at")

@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ("round", "beneficiary", "amount", "paid_at")
