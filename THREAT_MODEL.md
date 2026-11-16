# Threat Model - GhostGuard Audit Log

Appendix A for the dissertation.

## 1. What the audit log guarantees

Given a GhostGuard deployment with:

- The HMAC key K stored outside the database (environment variable)
- All audit-worthy events written via apps.audit.services.append()
- The integrity check run via apps.audit.services.verify_integrity()

The system guarantees:

G1 (Tamper-evidence): If any audit entry in the chain is edited, deleted, or inserted, verify_integrity() returns ok=False and reports the sequence number of the first broken entry.

G2 (Exact localisation): The reported broken sequence is the earliest entry that fails verification, not an arbitrary one.

G3 (Key isolation): An attacker with read/write database access but not shell access cannot forge a valid chain, because the HMAC key is not stored in the database.

It does not guarantee:

L1 (Truth of original entry): The audit log preserves what was entered. It does not certify that the entry was accurate at the time of entry. A field officer who registers a fake beneficiary with valid audit-log records will still produce a clean chain.

L2 (Availability): An attacker with shell access can delete the DB file, delete the HMAC key, or refuse to run verification. Availability is not protected.

L3 (Confidentiality): The audit log records event metadata in plaintext. Anyone with DB access sees this. The ID reference hash is not reversible, but the phone number and full name are.

## 2. Threat actors

T1 - Database-level attacker (realistic):
Capability: Read and write access to the database (via SQL injection, stolen backup, or colluding insider).
Goal: Alter a disbursement record, delete a suspicious audit entry, or insert a forged entry.
Defence: HMAC chain. Without the key K, the attacker cannot compute a valid entry_hash for any modified or forged entry. verify_integrity() detects the tamper.
Residual risk: The attacker can delete the entire chain (verify_integrity returns ok=True on an empty chain). Mitigation: cross-verify with a hash of the final entry stored separately (out of scope; documented as future work).

T2 - Key-level attacker (advanced):
Capability: Shell access to the server OR theft of the .env file.
Goal: Same as T1, but with the ability to forge a valid chain.
Defence: None within the system. If the attacker has the key, they can recompute the entire chain after tampering. This is inherent to any HMAC-based scheme.
Residual risk: The threat model explicitly excludes this actor. Mitigation is operational: rotate keys periodically, store the key in a secrets manager, audit key access.

T3 - Insider (program manager or donor):
Capability: Legitimate authenticated access to the app.
Goal: Cover up a mistake (approve a bad list, then remove the approval).
Defence: The ORM guards block AuditEntry.save() and AuditEntry.delete() on existing rows. Every legitimate action generates a new audit entry. Any attempt to alter history is blocked at the application layer, and if bypassed, at the HMAC layer.
Residual risk: An insider with both app access and DB access is a T1 attacker.

T4 - Malicious beneficiary:
Capability: Submit a fraudulent registration via the field-officer UI.
Goal: Receive aid they are not entitled to.
Defence: The detection pipeline catches duplicates (exact phone, exact hashed ID, fuzzy name similarity). If a beneficiary submits a unique fake name and phone, they are indistinguishable from a legitimate beneficiary - this is the L1 limitation.
Residual risk: Legitimate fraud requires human verification (ID document check, in-person interview) which is out of scope for this software.

## 3. Why HMAC-SHA256 and not a simple hash chain

A simple hash chain (h_i = SHA256(h_{i-1} || payload_i)) has a known vulnerability: an attacker with DB write access can recompute the entire chain after tampering, because the hash function has no secret input.

HMAC-SHA256 adds a secret key K:

    h_i = HMAC_K(h_{i-1} || sequence_i || event_type_i || canonical(payload_i))

Without K, the attacker cannot compute valid h_i values for tampered entries. If they tamper with entry 3, every subsequent hash becomes unverifiable, and verify_integrity() reports sequence 3 as the first break.

The previous_hash field is also stored explicitly, so the verifier can detect hash substitution - if an attacker replaces entry 3 entry_hash with a value they computed (but without K), the recomputation of entry 4 entry_hash using entry 3 entry_hash will fail.

## 4. Why canonical JSON

The HMAC input must be deterministic: given the same logical payload, the same bytes must be hashed every time.

Python json.dumps() with default arguments is not deterministic - dict insertion order varies, float formatting varies. The canonicalize() function in apps/audit/services.py uses:

    json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")

- sort_keys=True - order-independent
- separators=(",", ":") - no whitespace
- ensure_ascii=False - UTF-8 preserving (for Swahili names with accents)
- allow_nan=False - reject NaN/Infinity floats (which do not round-trip deterministically)

Any payload that fails canonicalisation raises AuditChainError before the entry is written. This is tested in test_canonicalize_is_order_independent.

## 5. Why SHA-256 + salt for the ID reference, not PBKDF2

The proposal requires: "Protect the ID reference. Store it as a salted hash where an exact-match check is enough."

Two options:

| Algorithm | Speed | Brute-force cost (8-digit ID) | Verdict |
|---|---|---|---|
| PBKDF2-SHA256 (390k iterations) | about 100 ms/hash | about 8 days on 1 GPU | Overkill |
| SHA-256 + 16-byte salt | about 0.001 ms/hash | about 10 sec on 1 GPU | Adequate |

Both algorithms are trivially brute-forceable on 8-digit IDs because 10 to the power 8 possibilities is a small space. PBKDF2 provides no meaningful additional protection here. What PBKDF2 does provide is resistance to GPU brute-force on high-entropy secrets (passwords), which does not apply.

However, PBKDF2 does add 100ms to every registration, which breaks the synthetic data generator (5,000 records times 100ms = 8 minutes) and slows field registration in areas with intermittent connectivity.

Decision: SHA-256 + per-record salt. The salt is random, so the same ID reference across two records produces two different hashes. Equality-check is performed by re-hashing the input with the record stored salt and comparing.

Trade-off accepted: An attacker with a stolen DB can brute-force 8-digit IDs. Mitigation: the attacker can already read the phone numbers and names in plaintext, so the ID hash is not the weakest link. The purpose of hashing is to prevent casual misuse, not to defend against a determined attacker.

## 6. Why HMAC and not a public-key signature

HMAC is symmetric: the same key signs and verifies. This is fine because GhostGuard runs as a single Django process - the verifier and the signer are the same code.

For a multi-tenant deployment where the signer (NGO) and the verifier (donor) are different organizations, HMAC is insufficient - the donor would need the HMAC key, which means they could forge entries. In that case, a public-key signature (Ed25519) would be appropriate: the NGO signs, the donor verifies with the NGO public key.

This is future work. For the scope of this project (single-NGO deployment), HMAC is correct and simpler.

## 7. Test coverage

The following properties are covered by apps/audit/tests/test_chain.py:

| Test | Property verified |
|---|---|
| test_first_entry_links_to_genesis | Genesis hash is 0 x 64; sequence starts at 1 |
| test_clean_chain_verifies | A chain built normally returns ok=True |
| test_tampered_payload_is_detected_at_exact_sequence | Editing payload via raw SQL is detected at the exact broken row |
| test_deleted_entry_is_detected | Deleting a row is detected at the missing sequence |
| test_inserted_entry_breaks_sequence | Inserting a forged row is detected |
| test_tampered_hash_is_detected | Replacing entry_hash is detected |
| test_orm_update_is_blocked | AuditEntry.save() on existing row raises RuntimeError |
| test_orm_delete_is_blocked | AuditEntry.delete() raises RuntimeError |
| test_canonicalize_is_order_independent | canonicalize({"a":1,"b":2}) == canonicalize({"b":2,"a":1}) |
| test_unknown_event_type_rejected | Invalid event types raise AuditChainError |
| test_concurrent_appends_keep_sequence_contiguous | Two sequential appends produce sequences 1, 2 |

Result: Ran 3 tests in 2.155s - OK.

## 8. Documented limitations

1. Original entry lies (L1). A field officer who registers a fake beneficiary with a valid phone, valid photo and valid signature produces a perfectly clean chain. The audit log preserves honesty of later edits, not the initial claim.

2. Attacker with HMAC key (T2). If the key is stolen, the attacker can rebuild the chain.

3. Availability. An attacker with shell access can delete the DB. GhostGuard does not protect availability.

4. Photo perceptual hashing (implemented in Sprint 7, currently stubbed). The current implementation hashes reused photos (same image, different name), not the same face in two different photos. Real face matching requires a different algorithm and is out of scope.

5. Network security. The audit log signs data at rest. It does not protect data in transit. HTTPS is assumed to be provided by the deployment layer.

## 9. References

- NIST SP 800-107 Rev. 1: Recommendation for Applications Using Approved Hash Algorithms
- NIST SP 800-132: Recommendation for Password-Based Key Derivation
- Kenya Data Protection Act, 2019
- OWASP Cryptographic Storage Cheat Sheet
- Merkle, R. C. (1987). A Digital Signature Based on a Conventional Encryption Function. CRYPTO 87.
