import json
from pathlib import Path
from django.core.management.base import BaseCommand
from apps.beneficiaries.models import Beneficiary
from apps.detection.engine import detect_duplicates


class Command(BaseCommand):
    help = "Evaluate detection precision and recall against ground truth"

    def add_arguments(self, parser):
        parser.add_argument("--truth", type=str, default="datasets/ground_truth.json")

    def handle(self, *args, **options):
        truth_path = Path(options["truth"])
        if not truth_path.exists():
            self.stdout.write(self.style.ERROR(f"Ground truth not found: {truth_path}"))
            return

        truth = json.loads(truth_path.read_text())
        fraud_ids = set(truth["fraud_ids"])

        candidates = list(Beneficiary.objects.all())
        self.stdout.write(f"Loaded {len(candidates)} beneficiaries…")

        tp = fp = fn = tn = 0
        for b in candidates:
            # Exclude self: pass only the OTHER candidates
            others = [c for c in candidates if c.id != b.id]

            flags = detect_duplicates(
                new_name=b.full_name,
                new_phone=b.phone,
                new_id_hash=b.id_reference_hash,
                program_id=b.program_id,
                candidates=others,
            )

            # A "detected fraud" = this record has at least one EXACT flag
            # (fuzzy-only flags are advisory, not conclusive)
            exact_hit = any(f["layer"] == "EXACT" for f in flags)
            actual = b.id in fraud_ids

            if exact_hit and actual:        tp += 1
            elif exact_hit and not actual:  fp += 1
            elif not exact_hit and actual:  fn += 1
            else:                           tn += 1

        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall    = tp / (tp + fn) if (tp + fn) else 0.0
        f1        = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

        self.stdout.write("")
        self.stdout.write("=" * 60)
        self.stdout.write("EVALUATION RESULTS (EXACT layer only)")
        self.stdout.write("=" * 60)
        self.stdout.write(f"True Positives:  {tp}")
        self.stdout.write(f"False Positives: {fp}")
        self.stdout.write(f"False Negatives: {fn}")
        self.stdout.write(f"True Negatives:  {tn}")
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Precision: {precision:.3f}"))
        self.stdout.write(self.style.SUCCESS(f"Recall:    {recall:.3f}"))
        self.stdout.write(self.style.SUCCESS(f"F1 Score:  {f1:.3f}"))
        self.stdout.write("=" * 60)
