"""
Stream B backend — Apple Health CSV batch scrubbing.

Column identification is now a TWO-PASS scanner:

  Pass 1 (fast, header-name based): match column headers against
  keyword patterns (device/source/hardware, time/date, lat/lon,
  name/email/phone/etc.). Cheap and catches the common case instantly.

  Pass 2 (content-based): for any column the name scan didn't already
  confidently classify, sample a handful of its ACTUAL VALUES and run
  them through the full Presidio pipeline (every built-in recognizer
  plus MindGuard's custom device/UUID/timestamp/phone/name recognizers
  from backend/recognizers.py). If enough of the sampled values come
  back as, say, PHONE_NUMBER or PERSON, the column gets flagged —
  regardless of what it's named. A separate numeric range/precision
  heuristic handles raw GPS coordinates specifically, since spaCy's
  NER doesn't tag bare decimal numbers as a location.

This is what lets MindGuard handle a health export with renamed,
unfamiliar, or generic column headers (like "col_12") instead of only
working on the exact column names in the project brief's example.
"""

import re
from collections import Counter

import pandas as pd

from backend.redactor import redact_text, analyze_text


# File upload size guardrail — checked in the frontend before this
# module ever touches the file, but the constant lives here so it's
# defined in exactly one place.
MAX_UPLOAD_SIZE_MB = 200
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024


# ---------------------------------------------------------------------
# Pass 1: column identification by HEADER NAME
# ---------------------------------------------------------------------
# Order matters: each column is tested in order and assigned to the
# FIRST category that matches — that's what stops "sourceName" from
# being misclassified as "personal" just because it contains "name":
# it matches "device_id" (via "source") first and stops there.
COLUMN_NAME_PATTERNS = {
    "device_id": re.compile(r"(device|source|hardware|serial|uuid)", re.IGNORECASE),
    "timestamp": re.compile(r"(time|date)", re.IGNORECASE),
    "gps": re.compile(r"(lat|lon|gps|coord|location)", re.IGNORECASE),
    "personal": re.compile(r"(name|email|phone|address|ssn|dob|birth)", re.IGNORECASE),
}


def classify_columns_by_name(columns) -> dict:
    """Bucket columns into risk categories using keyword patterns on
    their HEADER TEXT. Fast, and handles the common case where headers
    are reasonably descriptive."""
    classified = {category: [] for category in COLUMN_NAME_PATTERNS}
    for col in columns:
        for category, pattern in COLUMN_NAME_PATTERNS.items():
            if pattern.search(str(col)):
                classified[category].append(col)
                break  # first matching category wins
    return classified


# ---------------------------------------------------------------------
# Pass 2: column identification by VALUE CONTENT
# ---------------------------------------------------------------------
# Which of Presidio's entity types (built-in + our custom ones) maps to
# which of MindGuard's scrubbing categories.
ENTITY_TO_CATEGORY = {
    "PERSON": "personal",
    "EMAIL_ADDRESS": "personal",
    "PHONE_NUMBER": "personal",
    "US_SSN": "personal",
    "LOCATION": "personal",       # spaCy-detected place names/addresses
    "DEVICE_ID": "device_id",     # our custom recognizer (HKDevice strings, UUIDs)
    "FINE_TIMESTAMP": "timestamp",  # our custom recognizer
    "DATE_TIME": "timestamp",
}

CONTENT_SAMPLE_SIZE = 30          # values sampled per unclassified column
CONTENT_MATCH_THRESHOLD = 0.2     # fraction of sampled values that must hit


def classify_columns_by_content(df: pd.DataFrame, already_classified: set) -> dict:
    """Sample each not-yet-classified column's actual values and run
    them through the full Presidio analyzer. A column gets flagged if
    a large-enough fraction of its sampled values match a known entity
    type — this is what catches PII sitting in an oddly- or generically-
    named column.

    Only samples up to CONTENT_SAMPLE_SIZE values per column (not the
    whole column) — with an 800,000-row file, scanning every cell with
    a full NLP pass would be far too slow for interactive use. If PII
    shows up in the sample, the WHOLE column still gets scrubbed in the
    actual transformation step, not just the sampled rows.
    """
    content_classified = {category: [] for category in COLUMN_NAME_PATTERNS}

    for col in df.columns:
        if col in already_classified:
            continue

        series = df[col].dropna()
        if series.empty:
            continue

        sample = series.astype(str).unique()[:CONTENT_SAMPLE_SIZE]
        if len(sample) == 0:
            continue

        hits = Counter()
        for value in sample:
            entities = analyze_text(value)
            matched_categories = {
                ENTITY_TO_CATEGORY[e.entity_type]
                for e in entities
                if e.entity_type in ENTITY_TO_CATEGORY
            }
            for category in matched_categories:
                hits[category] += 1

        if hits:
            top_category, top_count = hits.most_common(1)[0]
            if (top_count / len(sample)) >= CONTENT_MATCH_THRESHOLD:
                content_classified[top_category].append(col)

    return content_classified


def classify_gps_by_value_range(df: pd.DataFrame, already_classified: set) -> list:
    """Flag purely numeric columns as GPS coordinates based on their
    VALUE RANGE and decimal precision, not their name — this is what
    catches latitude/longitude data even in columns called something
    generic. Real coordinates are almost always written with several
    decimal places (e.g. 39.952583); most ordinary health metrics
    (heart rate, step count) aren't, which keeps false positives low.
    """
    gps_cols = []
    for col in df.columns:
        if col in already_classified:
            continue

        numeric = pd.to_numeric(df[col], errors="coerce").dropna()
        if numeric.empty:
            continue

        in_lat_range = numeric.between(-90, 90).all()
        in_lon_range = numeric.between(-180, 180).all()
        if not (in_lat_range or in_lon_range):
            continue

        decimals = numeric.astype(str).str.extract(r"\.(\d+)")[0].dropna().str.len()
        looks_like_coordinates = not decimals.empty and decimals.mean() >= 4

        if looks_like_coordinates:
            gps_cols.append(col)

    return gps_cols


def classify_columns(df: pd.DataFrame) -> dict:
    """Full two-pass column classification. Returns e.g.:
        {
          "device_id": [...], "timestamp": [...],
          "gps": [...], "personal": [...],
        }
    """
    classified = classify_columns_by_name(list(df.columns))
    already = {c for cols in classified.values() for c in cols}

    content_classified = classify_columns_by_content(df, already)
    for category, cols in content_classified.items():
        classified[category].extend(cols)
        already.update(cols)

    gps_by_value = classify_gps_by_value_range(df, already)
    classified["gps"].extend(gps_by_value)

    return classified


# ---------------------------------------------------------------------
# Transformations
# ---------------------------------------------------------------------
def _mask_value(_value, placeholder: str):
    return placeholder


def _generalize_timestamp(value):
    """Collapse a precise timestamp down to year-month, e.g.
    "2026-08-14 09:41:33 -0400" -> "2026-08". Values that don't look
    like a date at all (e.g. a raw UTC-offset string) fall back to a
    redaction marker instead of being generalized into something
    misleading."""
    if pd.isna(value):
        return value
    match = re.match(r"(\d{4}-\d{2})", str(value))
    return match.group(1) if match else "[DATE_REDACTED]"


def scrub_dataframe(df: pd.DataFrame):
    """Apply the scanner's classification-driven scrubbing rules.

    Returns (scrubbed_df, classified_columns, actions_applied) where
    actions_applied is a list of (column_name, action_label) tuples for
    the "Actions Applied" UI card to render directly.
    """
    scrubbed = df.copy()
    classified = classify_columns(df)
    actions = []

    for col in classified["device_id"]:
        if col in scrubbed.columns:
            scrubbed[col] = scrubbed[col].apply(lambda v: _mask_value(v, "[DEVICE_REDACTED]"))
            actions.append((col, "MASKED"))

    for col in classified["personal"]:
        if col in scrubbed.columns:
            scrubbed[col] = scrubbed[col].apply(lambda v: _mask_value(v, "[PII_REDACTED]"))
            actions.append((col, "MASKED"))

    for col in classified["timestamp"]:
        if col in scrubbed.columns:
            scrubbed[col] = scrubbed[col].apply(_generalize_timestamp)
            actions.append((col, "GENERALIZED"))

    gps_cols = [c for c in classified["gps"] if c in scrubbed.columns]
    if gps_cols:
        scrubbed = scrubbed.drop(columns=gps_cols)
        actions.extend((col, "STRIPPED") for col in gps_cols)

    return scrubbed, classified, actions


def scrub_text_columns(df: pd.DataFrame, text_columns: list) -> pd.DataFrame:
    """Run the Stream A Presidio pipeline row-by-row on any columns that
    contain free-form text (e.g. a workout 'notes' field). Only pass
    columns you know are free text here — running NLP on every cell of
    an 800,000-row export will be slow, so keep this list narrow.
    """
    scrubbed = df.copy()
    for col in text_columns:
        if col in scrubbed.columns:
            scrubbed[col] = scrubbed[col].apply(
                lambda v: redact_text(str(v))[0] if pd.notna(v) else v
            )
    return scrubbed


def process_health_csv(df: pd.DataFrame, text_columns=None):
    """Full Stream B pipeline: two-pass scanner-driven column scrubbing,
    then an optional NLP pass over any specified free-text columns.

    Returns (scrubbed_df, classified_columns, actions_applied).
    """
    result_df, classified, actions = scrub_dataframe(df)
    if text_columns:
        result_df = scrub_text_columns(result_df, text_columns)
    return result_df, classified, actions


if __name__ == "__main__":
    # Deliberately uses GENERIC column names ("col_1", "col_2", etc.)
    # to prove the content-based pass works without any naming hints.
    sample = pd.DataFrame({
        "col_1": ["Alex's Apple Watch"],
        "col_2": ["<<HKDevice: 0x1234>, name:Apple Watch>"],
        "col_3": ["2026-08-14 09:41:33 -0400"],
        "col_4": [39.952583],
        "col_5": [-75.165222],
        "col_6": ["222-222-2222"],
        "value": [72],
    })
    scrubbed_df, classified, actions = process_health_csv(sample)
    print(scrubbed_df)
    print("Classified:", classified)
    print("Actions:", actions)