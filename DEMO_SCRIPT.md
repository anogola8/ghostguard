# GhostGuard - Defense Demo Script

Duration: 10 minutes.
Setup: Server running (`python manage.py runserver`), browser open at http://127.0.0.1:8000/, logged in as admin, Terminal 2 available.

## Minute 0-1: The Problem

Say: Kenya loses billions annually to ghost beneficiaries - fabricated names, duplicated records, lists edited after approval. Most small aid programs manage beneficiaries in Excel, where nobody can tell if a name is real, whether the same person appears twice, or whether a list was altered after approval. GhostGuard solves exactly this.

Open / and show the landing page.

## Minute 1-3: Registration with Live Detection

Go to Beneficiaries -> Register Beneficiary.

Fill in:
- Program: Synthetic Relief Program
- Full Name: John Otieno
- Phone: 0712345678
- Village: Kibera
- National ID Reference: 12345678

Say: Every registration goes through the detection pipeline before the record is saved.

Click Register.

Say: Recorded. Now watch what happens if someone tries to register the same person again.

Register again:
- Full Name: Otieno John (reversed)
- Phone: 0712345678 (same)

Click Register.

Say: The phone match triggers the EXACT layer. The record is saved as FLAGGED, and the field officer sees a warning. This is the first line of defense.

Go to /admin/beneficiaries/beneficiary/ and show the flagged record with detection_flags JSON in the admin.

Say: Look at the flags JSON - it says exactly which layer caught it, matched against which record, and the score. Everything is auditable.

## Minute 3-5: The Dashboard

Open /dashboard/.

Say: Field officers register. Program managers approve. Donors see this.

Point at the three cards:
- Total Beneficiaries: about 5,000
- Flagged for Review: about 2,700
- Audit Entries: grows as you interact

Point at the bar chart.

Say: This is what the donors see. Every flagged record is visible. Every program is auditable.

## Minute 5-7: The Audit Trail - THE MONEY MOMENT

Open /audit/integrity/.

Say: This is the piece that makes GhostGuard more than just a database.

Click Verify integrity.

Expected: Chain intact - N entries verified (in green).

Say: Every registration, approval, payout, and flag resolution is written to a tamper-evident log. Each entry is HMAC-hashed with the previous entry hash. If anyone edits, deletes or inserts a past row, the chain breaks.

Open Terminal 2, show the DB directly:

    python manage.py dbshell

In the SQLite prompt:

    UPDATE audit_auditentry SET payload = '"'"'{"username":"evil"}'"'"' WHERE sequence = 3;
    .quit

Reload the page, click Verify integrity again.

Expected: Tamper detected at sequence 3 (in red).

Say: I just edited the audit log via raw SQL - bypassing the ORM entirely, simulating a database-level attacker. The HMAC key lives outside the database, so the attacker cannot forge a valid chain without also stealing the key. And the system reports the exact broken sequence, not just something is wrong.

Pause here. This is the moment examiners remember.

Restore:

    python manage.py shell -c "from apps.audit.services import verify_integrity; print(verify_integrity())"

If you need to reset for the next demo, delete the DB and re-migrate (5 seconds).

## Minute 7-9: The Evaluation

Open a terminal, show the evaluation command:

    python manage.py evaluate_layers

Say: We ran GhostGuard against a synthetic dataset of 5,000 beneficiaries with 750 injected frauds. Precision of the exact layer alone is 0.52; recall is 0.81. Adding the fuzzy layer brings recall to 100 percent, catching all 750 injected frauds, at the cost of about 2,200 additional advisory flags for human review - roughly 0.24 hours of officer review per extra fraud caught.

Point at the table:

| Config | TP | FP | FN | TN | Prec | Rec | F1 |
|---|---|---|---|---|---|---|---|
| EXACT | 605 | 557 | 145 | 3,693 | 0.521 | 0.807 | 0.633 |
| EXACT+FUZZY | 750 | 2,771 | 0 | 1,479 | 0.213 | 1.000 | 0.351 |

Say: The trade-off is measurable and defensible. For small programs with limited staff, EXACT alone is a reasonable default. For programs with donor-funded review capacity, the layered pipeline eliminates the fraud gap entirely.

## Minute 9-10: The PDF Report

Open /dashboard/report/pdf/.

Say: Every donor gets a signed PDF audit report - chain integrity status, per-program totals, and the last 20 audit entries. It downloads in one click.

Show the downloaded PDF.

Say: The system is live. It is tested. It is documented. It runs on free infrastructure. Thank you.

## Q&A - Pre-prepared answers

Q: How do you know this works on real data?
A: We cannot ethically use real beneficiary data, so we built a synthetic dataset with known injected fraud. That lets us measure precision and recall exactly, which would be impossible on real data without ground truth. The synthetic dataset is realistic - Kenyan names, +254 phone formats, plausible village distributions - and the fraud injection matches reported patterns of ghost-beneficiary fraud.

Q: What stops someone from stealing the HMAC key?
A: The key lives in an environment variable on the server, not in the database. An attacker with database-only access - which is the realistic threat model for a stolen backup - cannot forge a valid chain. An attacker with shell access to the server can steal the key, but then they can do anything anyway. The value of the audit log is against internal attackers who have DB access but not root.

Q: Why SHA-256 instead of PBKDF2 for the ID reference?
A: PBKDF2 is for passwords - high-value, low-entropy secrets. An 8-digit national ID reference has the same entropy as an 8-digit password, so PBKDF2 would seem to apply. But we only ever compare hashes for equality, and the reference itself is a public identifier (not a secret). SHA-256 with a per-record salt is exactly the right choice for that: fast, deterministic, resistant to rainbow tables. PBKDF2 would be 100 times slower for no security gain.

Q: How does this scale?
A: Per-registration detection is O(program_size), which is about 500 records in a typical village program - about 5 milliseconds. Batch evaluation over 5,000 records is O(n squared) - 25 million comparisons - which takes about 2.5 minutes in Python. That is an offline evaluation job, not a per-user action. At 50,000 records we would add a trigram index in Postgres or use rapidfuzz.process.cdist.

Q: Why not biometrics?
A: Biometrics are out of scope for a small-program tool. The proposal explicitly excludes them, and adding them would require hardware we do not have and trigger additional Kenya DPA consent requirements. Photo perceptual hashing catches photo reuse - the same image re-uploaded under a different name - which is the actual fraud pattern. Face matching is future work.

Q: What about false positives?
A: The EXACT layer precision of 0.52 means half of auto-blocks are false positives. But note: the system does not reject beneficiaries - it flags them for human review. A field officer looks at the flag, sees the matched record side-by-side, and decides. That is why the human-decision principle is in the ethics section.

## Contingency - if something breaks

- Server will not start: run `python manage.py check` then `python manage.py runserver`
- Tamper demo shows green: you did not edit sequence 3. Re-run the SQL.
- Dashboard empty: run `python manage.py generate_synthetic_data --count 5000`
- Everything is broken: close, restart runserver, `python manage.py test` - if that passes, the code is fine.
