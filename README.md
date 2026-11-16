# GhostGuard

Detects fake, duplicated and unverifiable beneficiaries in aid programs,
and produces a tamper-evident audit trail for every payout.

**.** Django 5.2 - PostgreSQL/SQLite - Python 3.12 - RapidFuzz - WeasyPrint - Chart.js.

## Problem

Aid programs in Kenya register beneficiaries in Excel or Google Sheets. There is no identity check, no duplicate detection, and no history of who changed what. A fraudulent entry costs nothing to add, and an auditor cannot tell whether a list was edited after approval.

## Solution

GhostGuard combines three techniques:

1. Layered duplicate detection - exact (phone + hashed ID), fuzzy (name similarity), and image (perceptual hash, planned) - with tunable risk scoring.
2. Rule-based anomaly flags - one phone across many households, bulk registrations from one device, repeat beneficiaries across unrelated programs.
3. HMAC-signed, hash-chained audit log - every important event (registration, approval, payout) is hashed with the previous entry hash. Any later edit, deletion or insertion breaks the chain; the Verify integrity button reports the first broken sequence.

Donors get a read-only transparency dashboard with one-click chain verification.

## Status

| Sprint | Deliverable | Status |
|---|---|---|
| 0 | Project scaffold, custom User model, env, Docker | Done |
| 1 | HMAC hash-chained audit log + integrity verifier + tests | Done |
| 2 | Programs, Beneficiaries, SHA-256 ID hashing | Done |
| 3 | Exact + Fuzzy duplicate detection + risk flags | Done |
| 4 | Approval workflow, round locking, audit hooks | Done |
| 5 | Donor dashboard, public transparency, PDF report | Done |
| 6 | Synthetic dataset (5,000 records) + precision/recall evaluation | Done |
| 7 | Image hashing (perceptual), context anomaly rules, ML | Future work |

## Quick Start

    python -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    cp .env.example .env
    python manage.py migrate
    python manage.py shell -c "from apps.accounts.models import User; User.objects.create_superuser('admin','a@a.com','change-me', role='SYSTEM_ADMIN')"
    python manage.py generate_synthetic_data --count 5000
    python manage.py evaluate_layers
    python manage.py runserver

Then open http://127.0.0.1:8000/

## Evaluation Results

Synthetic dataset: 5,000 records, 15 percent fraud rate (750 injected frauds).
Fraud mix: exact phone duplication, shared phone across records, reversed-name similarity.

### Table 1 - Layer performance

| Configuration | TP | FP | FN | TN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|
| EXACT only (phone + SHA-256 hashed ID) | 605 | 557 | 145 | 3,693 | 0.521 | 0.807 | 0.633 |
| EXACT + FUZZY (raw flags, all advisory) | 750 | 2,771 | 0 | 1,479 | 0.213 | 1.000 | 0.351 |

The EXACT layer catches 81 percent of injected fraud with 52 percent precision (each blocked record is roughly as likely to be a false positive as a true positive - human review is essential). The FUZZY layer catches the remaining 19 percent (all 145 remaining frauds), but generates 2,214 additional advisory flags that a field officer must triage manually.

### Table 2 - Trade-off

| Metric | EXACT only | EXACT + FUZZY |
|---|---|---|
| Fraud caught (of 750) | 605 (80.7 percent) | 750 (100 percent) |
| False auto-blocks | 557 | 557 |
| Advisory review flags | 0 | +2,214 |
| Estimated officer time at 2 min per review | 1,162 x 2 min = 38.7 h | 3,376 x 2 min = 112.5 h |
| Marginal cost per additional fraud caught | - | about 0.24 h per fraud |

### Table 3 - Tamper detection

| Action | Result |
|---|---|
| Edit a past audit entry (via raw SQL) | Tamper detected at sequence N |
| Delete a past audit entry | Missing entry at sequence N |
| Insert a forged entry | Sequence mismatch at N |
| Clean chain | Chain intact - N entries verified |

The tamper test is a live demo: modify the SQLite DB with psql or sqlite3, click Verify integrity, and the system reports the exact broken sequence.

## Architecture

    Browser --> Django app --> Database (Postgres or SQLite)
                   |
                   +--> Detection Engine
                   +--> Audit log (HMAC chain, key in .env)
                   +--> Dashboard

## Technology

| Layer | Tool |
|---|---|
| Backend | Django 5.2, Django REST Framework |
| Database | PostgreSQL (production), SQLite (development) |
| Detection | RapidFuzz (fuzzy names), Pillow + ImageHash (perceptual photos) |
| Background | Celery + Redis (scaffolded) |
| Audit chain | Python hmac, hashlib (HMAC-SHA256) |
| Reports | WeasyPrint (PDF), Chart.js (dashboard) |
| Packaging | Docker Compose |

## Ethics and Data Protection

Following Kenya Data Protection Act, 2019:

- No real personal data. All development and defense use synthetic records.
- Data minimization. Only phone, ID reference hash, photo hash, and village are stored.
- ID reference hashing. Salted SHA-256 (per record). Not PBKDF2 - PBKDF2 is for password storage, not equality checks (documented rationale in THREAT_MODEL.md).
- Role-based access. Field officers see their own registrations; donors see aggregates.
- Human decision. The system flags; a person decides. No beneficiary is removed automatically.

## License

Academic project. Not licensed for production use without review.

# ghostguard
