"""
Prevent accidental mutation of AuditEntry rows outside sanctioned code.

This is defence-in-depth: verify_integrity() will still *detect* a tamper,
but we also want to make tampering harder to trigger by a stray .save() or
.delete() in application code. The Django admin and shell remain able to
prove tamper-detection in the live demo.
"""
from django.db.models.signals import pre_delete, pre_save
from django.dispatch import receiver

from .models import AuditEntry


@receiver(pre_save, sender=AuditEntry)
def _block_audit_update(sender, instance: AuditEntry, **kwargs):
    if instance.pk and AuditEntry.objects.filter(pk=instance.pk).exists():
        raise RuntimeError(
            "AuditEntry rows are append-only; updates are forbidden. "
            "Use apps.audit.services.append() for new events."
        )


@receiver(pre_delete, sender=AuditEntry)
def _block_audit_delete(sender, instance: AuditEntry, **kwargs):
    raise RuntimeError(
        "AuditEntry rows are append-only; deletes are forbidden. "
        "The live tamper test must use raw SQL against the DB."
    )