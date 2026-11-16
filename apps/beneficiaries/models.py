import hashlib
import re
import secrets
from django.db import models
from django.utils import timezone


def normalize_phone(phone: str) -> str:
    """Normalize Kenyan phone numbers to +254 format."""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("0"):
        return "+254" + digits[1:]
    if digits.startswith("254"):
        return "+" + digits
    if digits.startswith("+"):
        return digits
    return "+254" + digits


def hash_id_reference(id_ref: str) -> tuple[str, str]:
    """
    Salted SHA-256 for equality checks only (per proposal: exact match is enough).
    Not suitable for password storage — but exactly right for equality on
    a low-entropy national ID reference, and thousands of times faster than PBKDF2.
    """
    if not id_ref:
        return "", ""
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + id_ref).encode("utf-8")).hexdigest()
    return hashed, salt


class Beneficiary(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        FLAGGED = "FLAGGED", "Flagged for review"
        INACTIVE = "INACTIVE", "Inactive"

    program = models.ForeignKey("programs.Program", on_delete=models.CASCADE, related_name="beneficiaries")
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, help_text="Normalized to +254...")
    id_reference_hash = models.CharField(max_length=128, blank=True, help_text="Salted SHA-256")
    id_reference_salt = models.CharField(max_length=64, blank=True)
    photo_hash = models.CharField(max_length=64, blank=True)
    public_id = models.CharField(max_length=20, unique=True, blank=True, null=True)
    village = models.CharField(max_length=100, blank=True)
    device_id = models.CharField(max_length=255, blank=True)
    detection_flags = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    registered_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True)
    registered_at = models.DateTimeField(auto_now_add=True)

    def set_id_reference(self, raw_id: str) -> None:
        self.id_reference_hash, self.id_reference_salt = hash_id_reference(raw_id)

    def __str__(self):
        return f"{self.full_name} ({self.phone})"



class Dispute(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        RESOLVED = "RESOLVED", "Resolved - Cleared"
        REJECTED = "REJECTED", "Rejected - Fraud Confirmed"

    beneficiary = models.ForeignKey(Beneficiary, on_delete=models.CASCADE, related_name="disputes")
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"Dispute for {self.beneficiary.full_name} ({self.status})"
