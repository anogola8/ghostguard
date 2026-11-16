import json
from pathlib import Path
from django.core.management.base import BaseCommand
from apps.beneficiaries.models import Beneficiary
from apps.detection.engine import detect_duplicates, normalize_name
from rapidfuzz import fuzz


class Command(BaseCommand):
    help = "Compare EXACT-only vs EXACT+FUZZY detection"

    def add_arguments(self, parser):
        parser.add_argument("--truth", type=str, default="datasets/ground_truth.json")
        parser.add_argument("--threshold", type=float, default=0.85)

    def handle(self, *args, **options):
        truth = json.loads(Path(options["truth"]).read_text())
        fraud_ids = set(truth["fraud_ids"])
        candidates = list(Beneficiary.objects.all())
        threshold = options["threshold"]

        results = {"EXACT": [0, 0, 0, 0], "EXACT+FUZZY": [0, 0, 0, 0]}

        for b in candidates:
            others = [c for c in candidates if c.id != b.id]
            norm_new = normalize_name(b.full_name)

            exact_hit = False
            fuzzy_hit = False

            for c in others:
                if (b.phone and c.phone == b.phone) or \
                   (b.id_reference_hash and c.id_reference_hash == b.id_reference_hash):
                    exact_hit = True
                    break

            if not exact_hit:
                for c in others:
                    if c.program_id == b.program_id and c.phone != b.phone:
                        score = fuzz.token_sort_ratio(
                            norm_new, normalize_name(c.full_name)
                        ) / 100.0
                        if score > threshold:
                            fuzzy_hit = True
                            break

            actual = b.id in fraud_ids
            for label, hit in [("EXACT", exact_hit), ("EXACT+FUZZY", exact_hit or fuzzy_hit)]:
                idx = results[label]
                if hit and actual:      idx[0] += 1
                elif hit and not actual: idx[1] += 1
                elif not hit and actual: idx[2] += 1
                else:                    idx[3] += 1

        self.stdout.write("")
        self.stdout.write("=" * 78)
        self.stdout.write("LAYER-BY-LAYER COMPARISON (for dissertation Table X)")
        self.stdout.write("=" * 78)
        self.stdout.write(f"{'Config':<15} {'TP':>5} {'FP':>5} {'FN':>5} {'TN':>5} {'Prec':>7} {'Rec':>7} {'F1':>7}")
        self.stdout.write("-" * 78)
        for label, (tp, fp, fn, tn) in results.items():
            prec = tp / (tp + fp) if (tp + fp) else 0.0
            rec = tp / (tp + fn) if (tp + fn) else 0.0
            f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
            self.stdout.write(f"{label:<15} {tp:>5} {fp:>5} {fn:>5} {tn:>5} {prec:>7.3f} {rec:>7.3f} {f1:>7.3f}")
        self.stdout.write("=" * 78)
