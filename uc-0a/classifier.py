"""
UC-0A - Complaint Classifier

Reads a city complaint CSV and writes complaint_id, category, priority,
reason, and flag columns using the fixed UC-0A taxonomy.
"""

import argparse
import csv
import os
import sys


ALLOWED_CATEGORIES = (
    "Pothole",
    "Flooding",
    "Streetlight",
    "Waste",
    "Noise",
    "Road Damage",
    "Heritage Damage",
    "Heat Hazard",
    "Drain Blockage",
    "Other",
)

SEVERITY_KEYWORDS = (
    "injury",
    "child",
    "school",
    "hospital",
    "ambulance",
    "fire",
    "hazard",
    "fell",
    "collapse",
)

OUTPUT_FIELDS = ("complaint_id", "category", "priority", "reason", "flag")


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _find_phrase(description: str, phrases: tuple[str, ...]) -> str:
    """Return the first configured phrase that appears in the description."""
    lowered = description.lower()
    for phrase in phrases:
        if phrase in lowered:
            return phrase
    return ""


def _severity_phrase(description: str) -> str:
    return _find_phrase(description, SEVERITY_KEYWORDS)


def _has_any(description: str, phrases: tuple[str, ...]) -> bool:
    return bool(_find_phrase(description, phrases))


def _category_for_description(description: str) -> tuple[str, str]:
    lowered = description.lower()

    if not lowered or len(lowered.split()) < 3:
        return "Other", ""

    pothole_phrases = ("deep pothole", "large pothole", "pothole", "potholes")
    if _has_any(lowered, pothole_phrases):
        return "Pothole", _find_phrase(lowered, pothole_phrases)

    actual_flooding = (
        "underpass flooded",
        "bus stand flooded",
        "flooded",
        "floods",
        "standing in water",
        "rainwater",
        "knee-deep",
    )
    if _has_any(lowered, actual_flooding):
        return "Flooding", _find_phrase(lowered, actual_flooding)

    drain_phrases = (
        "drain completely blocked",
        "stormwater drain",
        "main drain blocked",
        "drain blocked",
        "blocked with construction debris",
        "manhole cover missing",
    )
    if _has_any(lowered, drain_phrases):
        return "Drain Blockage", _find_phrase(lowered, drain_phrases)

    waste_phrases = (
        "garbage",
        "waste",
        "bins overflowing",
        "overflowing garbage bins",
        "dead animal",
        "not cleared",
        "dumped",
    )
    if _has_any(lowered, waste_phrases):
        return "Waste", _find_phrase(lowered, waste_phrases)

    noise_phrases = (
        "music",
        "drilling",
        "idling",
        "amplifiers",
        "wedding band",
        "audible",
        "engines on",
    )
    if _has_any(lowered, noise_phrases):
        return "Noise", _find_phrase(lowered, noise_phrases)

    heat_phrases = (
        "heatwave",
        "dangerous temperatures",
        "temperature",
        "full sun",
        "burns",
        "melting",
        "bubbling",
        "footwear sticking",
        "44",
        "45",
        "52",
    )
    if _has_any(lowered, heat_phrases):
        return "Heat Hazard", _find_phrase(lowered, heat_phrases)

    streetlight_phrases = (
        "streetlight",
        "streetlights",
        "lights out",
        "unlit",
        "dark at night",
        "darkness",
        "substation tripped",
    )
    if _has_any(lowered, streetlight_phrases):
        return "Streetlight", _find_phrase(lowered, streetlight_phrases)

    heritage_terms = (
        "heritage lamp post",
        "historic tram",
        "heritage building",
        "heritage stone",
        "ancient step well",
        "cobblestones",
        "defaced",
        "tagore museum",
    )
    heritage_damage_terms = (
        "knocked over",
        "broken up",
        "defaced",
        "not replaced",
        "not restored",
        "subsidence",
    )
    if _has_any(lowered, heritage_terms) and _has_any(lowered, heritage_damage_terms):
        evidence = _find_phrase(lowered, heritage_terms)
        return "Heritage Damage", evidence

    road_damage_phrases = (
        "road surface cracked",
        "road surface buckled",
        "road collapsed",
        "road subsided",
        "road subsidence",
        "surface cracked",
        "cracked and sinking",
        "collapsed",
        "crater",
        "footpath tiles broken",
        "footpath broken",
        "upturned paving",
        "bridge approach",
        "structural concern",
        "sinking",
        "subsided",
    )
    if _has_any(lowered, road_damage_phrases):
        return "Road Damage", _find_phrase(lowered, road_damage_phrases)

    return "Other", ""


def _sentence_reason(category: str, evidence: str, severity: str, description: str) -> str:
    if category == "Other":
        sample = description[:80].rstrip()
        if severity:
            return (
                f'No allowed category matched "{sample}" confidently; '
                f'severity term "{severity}" makes priority Urgent.'
            )
        return f'No allowed category matched "{sample}" confidently.'

    if severity:
        return (
            f'Matched "{evidence}" for {category}; '
            f'severity term "{severity}" makes priority Urgent.'
        )
    return f'Matched "{evidence}" for {category}.'


def classify_complaint(row: dict) -> dict:
    """
    Classify a single complaint row.
    Returns dict with: complaint_id, category, priority, reason, flag.
    """
    complaint_id = _clean_text(row.get("complaint_id"))
    description = _clean_text(row.get("description"))
    category, evidence = _category_for_description(description)
    severity = _severity_phrase(description.lower())
    priority = "Urgent" if severity else "Standard"
    flag = "NEEDS_REVIEW" if category == "Other" else ""
    reason = _sentence_reason(category, evidence, severity, description)

    if category not in ALLOWED_CATEGORIES:
        category = "Other"
        flag = "NEEDS_REVIEW"

    return {
        "complaint_id": complaint_id,
        "category": category,
        "priority": priority,
        "reason": reason,
        "flag": flag,
    }


def _is_malformed(row: dict) -> bool:
    return not _clean_text(row.get("complaint_id")) or not _clean_text(row.get("description"))


def batch_classify(input_path: str, output_path: str) -> str:
    """Read input CSV, classify each valid row, and write results CSV."""
    results = []

    with open(input_path, newline="", encoding="utf-8-sig") as input_file:
        reader = csv.DictReader(input_file)
        for line_number, row in enumerate(reader, start=2):
            try:
                if _is_malformed(row):
                    print(f"Skipping malformed row {line_number}: missing complaint_id or description", file=sys.stderr)
                    continue
                results.append(classify_complaint(row))
            except Exception as exc:
                print(f"Skipping malformed row {line_number}: {exc}", file=sys.stderr)

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(results)

    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UC-0A Complaint Classifier")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    batch_classify(args.input, args.output)
    print(f"Done. Results written to {args.output}")
