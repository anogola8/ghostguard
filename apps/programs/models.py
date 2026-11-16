from django.db import models
from django.conf import settings

class Program(models.Model):
    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=255)
    donor = models.CharField(max_length=255, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class DisbursementRound(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        APPROVED = "APPROVED", "Approved"
        LOCKED = "LOCKED", "Locked"

    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="rounds")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.program.name} - {self.amount} ({self.status})"

class Payout(models.Model):
    round = models.ForeignKey(DisbursementRound, on_delete=models.PROTECT, related_name="payouts")
    beneficiary = models.ForeignKey("beneficiaries.Beneficiary", on_delete=models.PROTECT, related_name="payouts")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_at = models.DateTimeField(auto_now_add=True)
    reference = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"Payout {self.amount} to {self.beneficiary}"
