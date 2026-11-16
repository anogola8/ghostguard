"""
Behavioural tests for the audit chain.

These tests are the *specification* of the tamper-evidence property:
any edit, delete, or insert to a past row must be detected, and the
first broken sequence must be reported exactly.
"""
import pytest
from django.db import connection

from apps.audit.models import AuditEntry, EventType
from apps.audit.services import (
    GENESIS_HASH,
    AuditChainError,
    append,
    canonicalize,
    verify_integrity,
)


def _seed(n: int = 5) -> None:
    for i in range(n):
        append(
            EventType.BENEFICIARY_REGISTERED,
            payload={"i": i, "name": f"person-{i}"},
            actor_username="tester",
        )


pytestmark = pytest.mark.django_db


def test_first_entry_links_to_genesis():
    e = append(EventType.USER_CREATED, {"username": "alice"})
    assert e.sequence == 1
    assert e.previous_hash == GENESIS_HASH
    assert len(e.entry_hash) == 64


def test_clean_chain_verifies():
    _seed(5)
    result = verify_integrity()
    assert result.ok is True
    assert result.entries_checked == 5
    assert result.first_broken_sequence is None


def test_tampered_payload_is_detected_at_exact_sequence():
    _seed(5)
    with connection.cursor() as cur:
        cur.execute(
            "UPDATE audit_auditentry SET payload = %s WHERE sequence = %s",
            ['{"i": 999, "name": "evil"}', 3],
        )
    result = verify_integrity()
    assert result.ok is False
    assert result.first_broken_sequence == 3


def test_deleted_entry_is_detected():
    _seed(5)
    with connection.cursor() as cur:
        cur.execute("DELETE FROM audit_auditentry WHERE sequence = %s", [3])
    result = verify_integrity()
    assert result.ok is False
    assert result.first_broken_sequence == 3


def test_inserted_entry_breaks_sequence():
    _seed(5)
    # Insert a forged row between 2 and 3 by shifting sequences with raw SQL.
    with connection.cursor() as cur:
        cur.execute(
            "UPDATE audit_auditentry SET sequence = sequence + 1 WHERE sequence >= 3"
        )
        cur.execute(
            """
            INSERT INTO audit_auditentry
              (sequence, event_type, payload, actor_username,
               previous_hash, entry_hash, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """,
            [3, "BENEFICIARY_REGISTERED", '{"forged": true}', "attacker",
             "0" * 64, "f" * 64],
        )
    result = verify_integrity()
    assert result.ok is False
    assert result.first_broken_sequence == 3


def test_tampered_hash_is_detected():
    _seed(3)
    with connection.cursor() as cur:
        cur.execute(
            "UPDATE audit_auditentry SET entry_hash = %s WHERE sequence = %s",
            ["0" * 64, 2],
        )
    result = verify_integrity()
    assert result.ok is False
    assert result.first_broken_sequence == 2


def test_orm_update_is_blocked():
    e = append(EventType.USER_CREATED, {"username": "bob"})
    e.actor_username = "evil"
    with pytest.raises(RuntimeError):
        e.save()


def test_orm_delete_is_blocked():
    e = append(EventType.USER_CREATED, {"username": "carol"})
    with pytest.raises(RuntimeError):
        e.delete()


def test_canonicalize_is_order_independent():
    a = canonicalize({"a": 1, "b": [2, 3], "c": "x"})
    b = canonicalize({"c": "x", "b": [2, 3], "a": 1})
    assert a == b


def test_unknown_event_type_rejected():
    with pytest.raises(AuditChainError):
        append("NOT_A_REAL_EVENT", {})


def test_concurrent_appends_keep_sequence_contiguous(transactional_db):
    """Two appends in the same request should still produce contiguous sequences."""
    append(EventType.USER_CREATED, {"username": "x"})
    append(EventType.USER_CREATED, {"username": "y"})
    seqs = list(AuditEntry.objects.values_list("sequence", flat=True))
    assert seqs == [1, 2]
    assert verify_integrity().ok is True