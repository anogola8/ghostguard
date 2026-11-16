"""
The hash chain: append() and verify_integrity().

Threat model
------------
* Attacker with DB-only access cannot forge a valid chain because the
  HMAC key lives in the environment, not the database.
* Attacker who edits/deletes/inserts a past row breaks every subsequent
  hash; verify_integrity() reports the first broken sequence.
* Attacker who also has the HMAC key can rebuild the chain; protecting the
  key is a deployment concern documented in the README.
* Concurrent appends are serialised with SELECT ... FOR UPDATE on the last row.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.db import transaction

from .models import AuditEntry, EventType, EventType

GENESIS_HASH = "0" * 64


class AuditChainError(Exception):
    """Raised when the chain cannot be appended to safely."""


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    first_broken_sequence: int | None
    reason: str
    entries_checked: int


def canonicalize(payload: dict[str, Any]) -> bytes:
    """
    Deterministic serialisation used to build the HMAC input.

    Rules:
    * keys sorted;
    * separators fixed (no whitespace);
    * UTF-8;
    * no floats — callers must pre-normalise money to strings/ints.
    """
    try:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AuditChainError(f"Payload not canonicalisable: {exc}") from exc


def _compute_entry_hash(
    previous_hash: str, sequence: int, event_type: str, canonical_payload: bytes
) -> str:
    key = settings.GHOSTGUARD_AUDIT_HMAC_KEY.encode("utf-8")
    if not key:
        raise AuditChainError("GHOSTGUARD_AUDIT_HMAC_KEY is not configured.")
    mac = hmac.new(key, digestmod=hashlib.sha256)
    mac.update(previous_hash.encode("ascii"))
    mac.update(b"|")
    mac.update(str(sequence).encode("ascii"))
    mac.update(b"|")
    mac.update(event_type.encode("utf-8"))
    mac.update(b"|")
    mac.update(canonical_payload)
    return mac.hexdigest()


@transaction.atomic
def append(
    event_type: str,
    payload: dict[str, Any],
    actor_username: str = "",
) -> AuditEntry:
    """Append one event to the chain. Serialised against concurrent appends."""
    if event_type not in EventType.values:
        raise AuditChainError(f"Unknown event_type: {event_type!r}")

    last = (
        AuditEntry.objects.select_for_update()
        .order_by("-sequence")
        .first()
    )
    if last is None:
        sequence = 1
        previous_hash = GENESIS_HASH
    else:
        sequence = last.sequence + 1
        previous_hash = last.entry_hash

    canonical = canonicalize(payload)
    entry_hash = _compute_entry_hash(
        previous_hash, sequence, event_type, canonical
    )

    return AuditEntry.objects.create(
        sequence=sequence,
        event_type=event_type,
        payload=payload,
        actor_username=actor_username,
        previous_hash=previous_hash,
        entry_hash=entry_hash,
    )


def verify_integrity() -> VerificationResult:
    """Verify the chain. If tamper detected, quarantine the system."""
    result = _verify_integrity_internal()
    if not result.ok:
        _quarantine_on_tamper(result)
    return result


def _quarantine_on_tamper(result):
    """Called when the chain is broken. Never heals — only quarantines."""
    from .models import SystemHealth, AttackLog, AttackLog
    from django.utils import timezone
    import json
    from pathlib import Path

    # 1. Set global health status
    health = SystemHealth.quarantine(
        sequence=result.first_broken_sequence,
        reason=result.reason,
    )

    # 2. Log the attack to the AttackLog
    try:
        AttackLog.objects.create(
            attack_type="TAMPER_DETECTED",
            ip_address=None,  # DB-level access, no HTTP request context
            payload={
                "sequence": result.first_broken_sequence,
                "reason": result.reason,
                "entries_checked": result.entries_checked,
            },
            blocked=True,
        )
    except Exception:
        pass

    # 3. Write a tamper alert file OUTSIDE the database (append-only, filesystem)
    try:
        alert_dir = Path("alerts")
        alert_dir.mkdir(exist_ok=True)
        alert_file = alert_dir / "tamper_alerts.jsonl"
        with open(alert_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "timestamp": timezone.now().isoformat(),
                "sequence": result.first_broken_sequence,
                "reason": result.reason,
                "entries_checked": result.entries_checked,
            }) + "\n")
    except Exception:
        pass  # Filesystem may be read-only in some deployments

    return health


def _verify_integrity_internal() -> VerificationResult:
    """
    Walk the chain from sequence 1 and verify every link.

    Returns a VerificationResult. On failure, first_broken_sequence is the
    sequence number of the earliest entry that fails verification.
    """
    expected_sequence = 1
    previous_hash = GENESIS_HASH
    checked = 0

    for entry in AuditEntry.objects.order_by("sequence").iterator():
        checked += 1
        if entry.sequence != expected_sequence:
            return VerificationResult(
                ok=False,
                first_broken_sequence=expected_sequence,
                reason=(
                    f"Missing entry: expected sequence {expected_sequence}, "
                    f"found {entry.sequence}."
                ),
                entries_checked=checked,
            )
        if entry.previous_hash != previous_hash:
            return VerificationResult(
                ok=False,
                first_broken_sequence=entry.sequence,
                reason=(
                    f"previous_hash mismatch at sequence {entry.sequence}: "
                    f"stored={entry.previous_hash[:12]}… "
                    f"expected={previous_hash[:12]}…"
                ),
                entries_checked=checked,
            )
        try:
            canonical = canonicalize(entry.payload)
        except AuditChainError as exc:
            return VerificationResult(
                ok=False,
                first_broken_sequence=entry.sequence,
                reason=f"Payload not canonicalisable at sequence {entry.sequence}: {exc}",
                entries_checked=checked,
            )
        recomputed = _compute_entry_hash(
            entry.previous_hash, entry.sequence, entry.event_type, canonical
        )
        if not hmac.compare_digest(recomputed, entry.entry_hash):
            return VerificationResult(
                ok=False,
                first_broken_sequence=entry.sequence,
                reason=f"entry_hash mismatch at sequence {entry.sequence}.",
                entries_checked=checked,
            )
        previous_hash = entry.entry_hash
        expected_sequence += 1

    return VerificationResult(
        ok=True,
        first_broken_sequence=None,
        reason="Chain intact.",
        entries_checked=checked,
    )




def log_attack(request, attack_type, payload=None, blocked=True):
    """Record a detected attack attempt with full forensic context."""
    from .models import AttackLog
    from .models import EventType

    ip = request.META.get("REMOTE_ADDR")
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")

    try:
        log = AttackLog.objects.create(
            attack_type=attack_type,
            ip_address=ip,
            forwarded_for=xff[:255],
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:2000],
            request_path=request.path[:500],
            request_method=request.method,
            payload=payload or {},
            blocked=blocked,
        )
        # Also append to the HMAC chain so it's tamper-evident
        append(
            EventType.USER_ROLE_CHANGED,
            {
                "security_event": "ATTACK_DETECTED",
                "attack_type": attack_type,
                "ip": ip,
                "path": request.path,
                "blocked": blocked,
            },
            actor_username="SECURITY_SYSTEM",
        )
        return log
    except Exception as e:
        # Never let logging failure crash the request
        import logging
        logging.getLogger(__name__).error(f"Attack logging failed: {e}")
        return None
