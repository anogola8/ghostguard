from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    FIELD_OFFICER = "FIELD_OFFICER", "Field Officer"
    PROGRAM_MANAGER = "PROGRAM_MANAGER", "Program Manager"
    DONOR_AUDITOR = "DONOR_AUDITOR", "Donor / Auditor"
    SYSTEM_ADMIN = "SYSTEM_ADMIN", "System Admin"


class User(AbstractUser):
    """Custom user with a role field. Defined before the first migration."""

    organization = models.ForeignKey("accounts.Organization", on_delete=models.SET_NULL, null=True, blank=True)
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.FIELD_OFFICER,
        help_text="Determines the user's permissions within the platform.",
    )

    def __str__(self) -> str:
        return f"{self.username} ({self.get_role_display()})"

class LoginAttempt(models.Model):
    """Tracks failed login attempts for brute-force defense."""
    username = models.CharField(max_length=150, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    successful = models.BooleanField(default=False)
    attempted_at = models.DateTimeField(auto_now_add=True)
    penalty_level = models.IntegerField(default=0)

    class Meta:
        indexes = [models.Index(fields=["username", "attempted_at"])]

    def __str__(self):
        status = "OK" if self.successful else "FAIL"
        return f"{self.username} [{status}] at {self.attempted_at}"


class UserSession(models.Model):
    """Tracks active sessions for a user to allow 'Logout Everywhere'."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sessions")
    session_key = models.CharField(max_length=40, unique=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    last_activity = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} @ {self.ip_address} ({self.session_key[:8]})"


class Organization(models.Model):
    class Tier(models.TextChoices):
        FREE = "FREE", "Free (Up to 1,000)"
        PRO = "PRO", "Pro (Up to 10,000)"
        ENTERPRISE = "ENTERPRISE", "Enterprise (Unlimited)"

    name = models.CharField(max_length=255, unique=True)
    tier = models.CharField(max_length=20, choices=Tier.choices, default=Tier.FREE)
    api_key = models.CharField(max_length=64, unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        import secrets
        if not self.api_key:
            self.api_key = f"gg_{secrets.token_hex(24)}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.tier})"
