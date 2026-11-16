"""
AuditEntry: one link in the tamper-evident HMAC hash chain.

Design notes
------------
* ``sequence`` is a contiguous integer starting at 1. It lets the verifier
  report the *first broken entry* cleanly, matching the proposal's promise.
* ``entry_hash`` = HMAC_K(previous_hash || canonical(payload_fields)).
  ``payload`` is stored as deterministic JSON so verification can recompute it.
* The chain is append-only. ORM-level guards (see services) prevent
  update/delete on this model outside the sanctioned ``append()`` function.
"""
from django.conf import settings
from django.db import models


class EventType(models.TextChoices):
    USER_CREATED = "USER_CREATED", "User created"
    USER_ROLE_CHANGED = "USER_ROLE_CHANGED", "User role changed"
    BENEFICIARY_REGISTERED = "BENEFICIARY_REGISTERED", "Beneficiary registered"
    BENEFICIARY_UPDATED = "BENEFICIARY_UPDATED", "Beneficiary updated"
    ROUND_APPROVED = "ROUND_APPROVED", "Disbursement round approved"
    ROUND_LOCKED = "ROUND_LOCKED", "Disbursement round locked"
    PAYOUT_RECORDED = "PAYOUT_RECORDED", "Payout recorded"
    FLAG_RESOLVED = "FLAG_RESOLVED", "Flag resolved"
    INTEGRITY_CHECKED = "INTEGRITY_CHECKED", "Integrity check performed"


class AuditEntry(models.Model):
    sequence = models.BigIntegerField(unique=True, editable=False)
    event_type = models.CharField(max_length=64, choices=EventType.choices)
    payload = models.JSONField(help_text="Deterministic JSON snapshot of the event.")
    actor_username = models.CharField(
        max_length=150,
        blank=True,
        help_text="Username of the actor at the time of the event; blank for system events.",
    )
    previous_hash = models.CharField(max_length=64, editable=False)
    entry_hash = models.CharField(max_length=64, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        ordering = ["sequence"]
        indexes = [models.Index(fields=["event_type", "created_at"])]

    def __str__(self) -> str:
        return f"#{self.sequence} {self.event_type} {self.entry_hash[:12]}…"


class SystemSettings(models.Model):
    fuzzy_threshold = models.FloatField(
        default=0.90,
        help_text="Fuzzy match threshold (0.0 to 1.0). Default 0.90.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_settings(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return f"System Settings (threshold={self.fuzzy_threshold})"


class SystemHealth(models.Model):
    """Global system health state. Set to QUARANTINED when tampering is detected."""
    class Status(models.TextChoices):
        HEALTHY = "HEALTHY", "Healthy"
        QUARANTINED = "QUARANTINED", "Quarantined — Tamper Detected"
        RESTORING = "RESTORING", "Restoring from Backup"

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.HEALTHY)
    tamper_sequence = models.IntegerField(null=True, blank=True)
    tamper_reason = models.TextField(blank=True)
    detected_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.CharField(max_length=150, blank=True)

    @classmethod
    def get_health(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @classmethod
    def quarantine(cls, sequence, reason):
        obj = cls.get_health()
        obj.status = cls.Status.QUARANTINED
        obj.tamper_sequence = sequence
        obj.tamper_reason = reason
        from django.utils import timezone
        obj.detected_at = timezone.now()
        obj.save()
        return obj

    def __str__(self):
        return f"System Health: {self.status}"


class AttackLog(models.Model):
    class AttackType(models.TextChoices):
        API_ENUM = "API_ENUM", "API Key Enumeration"
        SQL_INJECTION = "SQL_INJECTION", "SQL Injection Attempt"
        SESSION_HIJACK = "SESSION_HIJACK", "Session Hijack Attempt"
        TAMPER_DETECTED = "TAMPER_DETECTED", "Audit Chain Tamper"
        RATE_LIMIT = "RATE_LIMIT", "Rate Limit Triggered"
        CSRF_FAILURE = "CSRF_FAILURE", "CSRF Token Failure"
        XSS_ATTEMPT = "XSS_ATTEMPT", "XSS Payload Detected"
        UNAUTHORIZED = "UNAUTHORIZED", "Unauthorized Access"

    attack_type = models.CharField(max_length=30, choices=AttackType.choices)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    forwarded_for = models.CharField(max_length=255, blank=True)
    user_agent = models.TextField(blank=True)
    request_path = models.CharField(max_length=500, blank=True)
    request_method = models.CharField(max_length=10, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    blocked = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["attack_type", "-created_at"]),
            models.Index(fields=["ip_address", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.attack_type} from {self.ip_address} at {self.created_at}"
