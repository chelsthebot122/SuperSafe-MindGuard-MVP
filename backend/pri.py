"""
Privacy Risk Index (PRI) — the MVP success metric from your project
brief: "calculating the reduction in data sensitivity after
anonymization."

Formula (per spec):
    Raw PRI            = min(100, sum(weight(entity) * confidence(entity)))
    Redacted Reduction  = amount of that raw risk actually eliminated by
                          the anonymizer's replacements
    Post-Redaction PRI  = max(0, Raw PRI - Redacted Reduction)

"Redacted Reduction" isn't simply equal to the Raw PRI (which would
always force Post-Redaction to exactly 0) — a placeholder token like
"[PERSON]" still reveals structural information (that a name WAS
there, just not which one), so masking is modeled as removing
REDACTION_EFFECTIVENESS of the raw risk rather than all of it. That
constant is a tunable assumption, not a measured fact — adjust it if
you want redaction to be modeled as more/less effective.

This only needs ONE Presidio analysis pass (on the raw text) rather
than analyzing both the raw and redacted text separately, since the
reduction is computed directly from what was detected and replaced.
"""

from presidio_analyzer import RecognizerResult

# How much each entity type contributes to risk on its own. Higher =
# more identifying. Anything not listed falls back to DEFAULT_WEIGHT.
ENTITY_WEIGHTS = {
    "PERSON": 30,
    "PHONE_NUMBER": 25,
    "EMAIL_ADDRESS": 25,
    "LOCATION": 20,
    "DEVICE_ID": 22,
    "FINE_TIMESTAMP": 12,
    "US_SSN": 40,
    "CREDIT_CARD": 35,
    "DATE_TIME": 8,
    "PASSWORD": 45,             # highest weight — grants direct account access
    "BANK_ACCOUNT_NUMBER": 38,
    "ORGANIZATION": 15,         # backstop in case a name still occasionally gets misclassified here
}
DEFAULT_WEIGHT = 10
MAX_SCORE = 100.0

# Fraction of raw risk eliminated by masking a detected entity. Less
# than 1.0 because a redaction placeholder still leaks that *something*
# of that type was present.
REDACTION_EFFECTIVENESS = 0.85


def calculate_pri(entities: list[RecognizerResult]) -> float:
    """Turn a list of Presidio detections into a single 0-100 score."""
    if not entities:
        return 0.0

    total = 0.0
    for entity in entities:
        weight = ENTITY_WEIGHTS.get(entity.entity_type, DEFAULT_WEIGHT)
        total += weight * entity.score  # entity.score is Presidio's 0–1 confidence

    return round(min(total, MAX_SCORE), 1)


def calculate_redacted_reduction(entities: list[RecognizerResult]) -> float:
    """How much risk was actually removed by redacting these entities."""
    raw = calculate_pri(entities)
    return round(raw * REDACTION_EFFECTIVENESS, 1)


def calculate_pri_reduction(entities: list[RecognizerResult]) -> dict:
    """Single source of truth for Stream A/B's PRI meter pair.

    Takes ONLY the raw-text entity detections (no second analysis pass
    needed) and returns the raw score, the post-redaction score per the
    spec's max(0, raw - reduction) formula, and the percentage drop —
    exactly what the two meter bars in the UI need.
    """
    raw_score = calculate_pri(entities)
    reduction = calculate_redacted_reduction(entities)
    redacted_score = max(0.0, round(raw_score - reduction, 1))

    if raw_score == 0:
        reduction_pct = 0.0
    else:
        reduction_pct = round((reduction / raw_score) * 100, 1)

    return {
        "raw_pri": raw_score,
        "redacted_pri": redacted_score,
        "reduction_pct": reduction_pct,
    }


# ---------------------------------------------------------------------
# Batch/CSV scoring (Stream B)
# ---------------------------------------------------------------------
# Stream B's risk isn't a list of NLP-detected entities — it's a set of
# flagged COLUMNS (device IDs, timestamps, GPS, personal attributes).
# Same max(0, raw - reduction) shape as the text formula above, but
# weighted per column category, and with a category-specific
# effectiveness: GPS is fully STRIPPED (100% removed), device/personal
# columns are MASKED (placeholder still reveals the category, same
# 0.85 assumption as Stream A), and timestamps are GENERALIZED to
# year-month, which removes most but not all temporal signal.
COLUMN_RISK_WEIGHTS = {
    "device_id": 25,
    "personal": 30,
    "gps": 28,
    "timestamp": 15,
}
COLUMN_CATEGORY_EFFECTIVENESS = {
    "device_id": REDACTION_EFFECTIVENESS,  # masked
    "personal": REDACTION_EFFECTIVENESS,   # masked
    "gps": 1.0,                            # stripped entirely
    "timestamp": 0.70,                     # generalized, not fully removed
}


def calculate_csv_pri_reduction(classified_columns: dict) -> dict:
    """classified_columns is the dict returned by
    backend.csv_scrubber.classify_columns(): category name -> list of
    matching column names. Returns the same raw/redacted/reduction_pct
    shape as calculate_pri_reduction() so both streams' meter bars can
    be driven the same way.
    """
    raw = 0.0
    reduction = 0.0

    for category, cols in classified_columns.items():
        if not cols:
            continue
        weight = COLUMN_RISK_WEIGHTS.get(category, DEFAULT_WEIGHT) * len(cols)
        raw += weight
        reduction += weight * COLUMN_CATEGORY_EFFECTIVENESS.get(category, REDACTION_EFFECTIVENESS)

    raw_score = round(min(raw, MAX_SCORE), 1)
    # Scale reduction down proportionally if raw got capped at 100, so
    # reduction never ends up larger than the (capped) raw score.
    reduction_score = round(min(reduction, raw), 1)
    if raw > MAX_SCORE and raw > 0:
        reduction_score = round(reduction_score * (raw_score / raw), 1)
    redacted_score = max(0.0, round(raw_score - reduction_score, 1))

    if raw_score == 0:
        reduction_pct = 0.0
    else:
        reduction_pct = round((reduction_score / raw_score) * 100, 1)

    return {
        "raw_pri": raw_score,
        "redacted_pri": redacted_score,
        "reduction_pct": reduction_pct,
    }


if __name__ == "__main__":
    from backend.redactor import analyze_text

    raw_text = "Hi, my name is Alex. You can call me at (222) 222-2222."
    entities = analyze_text(raw_text)

    print(calculate_pri_reduction(entities))