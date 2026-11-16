"""Synthetic data generator with realistic Kenyan name diversity."""
import json
import random
import hashlib
import secrets
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.programs.models import Program
from apps.beneficiaries.models import Beneficiary, normalize_phone

FIRST = (
    "John Mary Peter Grace David Esther James Jane Samuel Faith Brian Mercy "
    "Kevin Cynthia Dennis Josephine Michael Anne Joseph Anthony Paul Sarah "
    "Daniel Patricia Stephen Margaret Christopher Elizabeth Andrew Helen "
    "William Florence Richard Beatrice Thomas Lydiah George Wanjiru Edward "
    "Akinyi Robert Nyambura Alice Kiprono Bernard Chebet Francis Kiptoo "
    "Ronald Karanja Patrick Mwangi Martin Wambui Philip Atieno Elijah Achieng "
    "Isaac Chepkemoi Jacob Kipchoge Henry Moraa Benjamin Kerubo Nicholas "
    "Muthoni Wycliffe Wairimu Vincent Cheruiyot Julius Chelagat Agnes Winnie "
    "Lydia Caroline Jackline Everlyne Reuben Timothy Moses Steven Aggrey "
    "Harun Zachariah Boniface Linet Purity Naomi Doreen Eunice Jacinta"
).split()

LAST = (
    "Otieno Ochieng Kariuki Wanjiku Mwangi Akinyi Njoroge Wambui Omondi "
    "Kiprop Mutua Wafula Barasa Njoki Karanja Kamau Njuguna Maina Macharia "
    "Muchiri Ndungu Waweru Mbugua Gitau Kibe Muthoni Nyambura Moraa Kemunto "
    "Chebet Kiptoo Kipchoge Kiptum Kiprotich Kemboi Rotich Sang Cheruiyot "
    "Kosgei Koech Yego Cherono Chepkemoi Wekesa Wanyonyi Simiyu Masinde "
    "Namulanda Ouma Okoth Oduor Owino Apiyo Anyango Atieno Achieng Adhiambo "
    "Awuor Akoth Odhiambo Ondiek Nyagah Ngugi Kihara Mugo Githinji Gitonga "
    "Mureithi Kimani Gichuru Weru Mworia Muriithi Mutethia Njiru Njue "
    "Mutiso Kilonzo Musyoka Mbithi Nzioka Muli Mutisya Ndambuki Munyao "
    "Mutinda Ngethe Kimuyu Kimeu Kisilu Musau Kioko Musembi Mwendwa Mutunga "
    "Mbugua Ndegwa Kagai Njoroge Ngethe Muigai Waweru Kamande Ndichu"
).split()

VILLAGES = ["Kibera", "Mathare", "Kawangware", "Korogocho", "Dandora",
            "Kasarani", "Ruiru", "Thika", "Nakuru", "Eldoret",
            "Kisumu", "Nyeri", "Machakos", "Kakamega", "Meru"]


def make_hash(id_ref: str):
    salt = secrets.token_hex(16)
    return hashlib.sha256((salt + id_ref).encode()).hexdigest(), salt


class Command(BaseCommand):
    help = "Generate synthetic dataset with injected fraud"

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=5000)
        parser.add_argument("--fraud-rate", type=float, default=0.15)
        parser.add_argument("--out", type=str, default="datasets/ground_truth.json")

    def handle(self, *args, **options):
        count = options["count"]
        fraud_rate = options["fraud_rate"]
        out_path = Path(options["out"])
        out_path.parent.mkdir(parents=True, exist_ok=True)

        rng = random.Random(42)
        program, _ = Program.objects.get_or_create(
            name="Synthetic Relief Program",
            defaults={"donor": "Synthetic Donor",
                      "start_date": "2026-01-01", "end_date": "2026-12-31"},
        )

        n_fraud = int(count * fraud_rate)
        n_clean = count - n_fraud
        to_create = []
        clean_pool = []

        self.stdout.write(f"Generating {n_clean} clean ({len(FIRST)*len(LAST)} possible names)…")
        for i in range(n_clean):
            first, last = rng.choice(FIRST), rng.choice(LAST)
            phone = normalize_phone(f"07{rng.randint(10000000, 99999999)}")
            id_ref = f"{rng.randint(10000000, 99999999)}"
            h, s = make_hash(id_ref)
            b = Beneficiary(
                program=program, full_name=f"{first} {last}",
                phone=phone, id_reference_hash=h, id_reference_salt=s,
                village=rng.choice(VILLAGES),
                device_id=f"device-{rng.randint(1, 20)}",
            )
            to_create.append(b)
            clean_pool.append((first, last, phone, id_ref))

        self.stdout.write(f"Injecting {n_fraud} fraud…")
        ground_truth = {"total": count, "clean": n_clean, "fraud": n_fraud, "fraud_ids": []}

        fraud_objs = []
        for i in range(n_fraud):
            kind = rng.choice(["EXACT_PHONE"]*3 + ["SHARED_PHONE"] + ["FUZZY_NAME"])
            df, dl, dphone, _did = rng.choice(clean_pool)

            if kind == "EXACT_PHONE":
                fname = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
                fphone = dphone
            elif kind == "FUZZY_NAME":
                fname = f"{dl} {df}"
                fphone = normalize_phone(f"07{rng.randint(10000000, 99999999)}")
            else:
                fname = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
                fphone = dphone

            h, s = make_hash(f"{rng.randint(10000000, 99999999)}")
            fraud_objs.append(Beneficiary(
                program=program, full_name=fname, phone=fphone,
                id_reference_hash=h, id_reference_salt=s,
                village=rng.choice(VILLAGES), device_id="device-fraud",
            ))

        with transaction.atomic():
            Beneficiary.objects.bulk_create(to_create, batch_size=500)
            Beneficiary.objects.bulk_create(fraud_objs, batch_size=500)
            fraud_ids = list(Beneficiary.objects.filter(device_id="device-fraud").values_list("id", flat=True))
            ground_truth["fraud_ids"] = fraud_ids

        out_path.write_text(json.dumps(ground_truth, indent=2))
        self.stdout.write(self.style.SUCCESS(
            f"Done. {count} total ({n_clean} clean + {n_fraud} fraud). Truth: {out_path}"
        ))
