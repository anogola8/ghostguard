import re
from rapidfuzz import fuzz

def normalize_name(name: str) -> str:
    if not name:
        return ""
    clean = re.sub(r'[^\w\s]', '', name.lower())
    tokens = clean.split()
    tokens.sort()
    return " ".join(tokens)


def detect_duplicates(new_name, new_phone, new_id_hash, program_id, candidates=None):
    if candidates is None:
        from apps.beneficiaries.models import Beneficiary
        candidates = list(Beneficiary.objects.all())

    flags = []
    norm_new = normalize_name(new_name)

    for b in candidates:
        # Faster path: check cheap exact matches first
        if new_phone and b.phone == new_phone:
            flags.append({
                "layer": "EXACT",
                "matched_id": b.id,
                "score": 1.0,
                "reason": f"Phone matches {b.full_name}",
            })
            continue
        if new_id_hash and b.id_reference_hash == new_id_hash:
            flags.append({
                "layer": "EXACT",
                "matched_id": b.id,
                "score": 1.0,
                "reason": f"ID hash matches {b.full_name}",
            })
            continue
        if b.program_id == program_id and b.phone != new_phone:
            score = fuzz.token_sort_ratio(norm_new, normalize_name(b.full_name)) / 100.0
            if score > 0.85:
                flags.append({
                    "layer": "FUZZY",
                    "matched_id": b.id,
                    "score": score,
                    "reason": f"Name similarity ({int(score * 100)}%) with {b.full_name}",
                })
    return flags
