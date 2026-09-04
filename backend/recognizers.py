"""
Custom Presidio recognizers for MindGuard.

Presidio's built-in recognizers know about common PII (names, emails,
phone numbers, credit cards, etc.) but have no idea what an Apple Health
export looks like. A PatternRecognizer is the simplest way to teach it
about a new entity type: give it a name, a regex (or a keyword list),
and Presidio treats matches exactly like any other entity from then on
— they show up in analyzer results, get anonymized, and count toward
the Privacy Risk Index just like PERSON or PHONE_NUMBER do.

Add new recognizers here as you find more Apple-Health-specific fields
that need catching. Each one is intentionally small and single-purpose
so you can test/tune them independently.
"""

from presidio_analyzer import Pattern, PatternRecognizer


# ---------------------------------------------------------------------
# Device identifiers
# ---------------------------------------------------------------------
# Apple Health exports include fields like:
#   sourceName = "Alex's Apple Watch"
#   device = "<<HKDevice: 0x...>, name:Apple Watch, manufacturer:Apple Inc., ...>"
# The "device" field especially is a long descriptive string that's
# effectively a fingerprint of a specific physical device — worth
# catching even though it's not a "name" or "phone number" in the
# traditional PII sense.
DEVICE_STRING_PATTERN = Pattern(
    name="apple_health_device_string",
    regex=r"<<HKDevice:.*?>>?",
    score=0.9,
)

DEVICE_ID_RECOGNIZER = PatternRecognizer(
    supported_entity="DEVICE_ID",
    patterns=[DEVICE_STRING_PATTERN],
    context=["device", "sourceName", "hardware"],
)


# ---------------------------------------------------------------------
# UUID-style identifiers
# ---------------------------------------------------------------------
# Health metadata often carries raw UUIDs (workout IDs, sync IDs, etc.)
# that can act as re-identification keys even with names stripped out.
UUID_PATTERN = Pattern(
    name="uuid_pattern",
    regex=r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
    score=0.85,
)

UUID_RECOGNIZER = PatternRecognizer(
    supported_entity="DEVICE_ID",
    patterns=[UUID_PATTERN],
)


# ---------------------------------------------------------------------
# Fine-grained ISO timestamps
# ---------------------------------------------------------------------
# A precise "2026-08-14 09:41:33 -0400" timestamp on a health event can
# be used to correlate someone's location/routine against other leaked
# data. We flag these as a distinct entity so the PRI/anonymizer can
# choose to generalize them (e.g. round to the day) instead of just
# masking outright.
FINE_TIMESTAMP_PATTERN = Pattern(
    name="fine_grained_timestamp",
    regex=r"\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\s?[+-]\d{4}",
    score=0.75,
)

TIMESTAMP_RECOGNIZER = PatternRecognizer(
    supported_entity="FINE_TIMESTAMP",
    patterns=[FINE_TIMESTAMP_PATTERN],
)


# ---------------------------------------------------------------------
# Supplementary phone number patterns
# ---------------------------------------------------------------------
# Presidio's built-in phone recognizer (backed by Google's libphonenumber
# via the `phonenumbers` package) is stricter than you'd expect — plain
# US-style numbers without a country code, or written with unusual
# spacing/punctuation, sometimes come back with low confidence or get
# missed outright. This adds a plain-regex safety net for the common
# US formats so a number doesn't slip through just because of
# formatting. It uses the SAME entity type ("PHONE_NUMBER") as
# Presidio's built-in recognizer, so it slots into the existing PRI
# weighting and anonymizer replacement with no other code changes.
PHONE_PATTERN = Pattern(
    name="us_phone_number_permissive",
    regex=r"(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    score=0.7,
)

PHONE_RECOGNIZER = PatternRecognizer(
    supported_entity="PHONE_NUMBER",
    patterns=[PHONE_PATTERN],
)


# ---------------------------------------------------------------------
# Self-introduction name patterns
# ---------------------------------------------------------------------
# spaCy's general-purpose NER model (the one behind Presidio's built-in
# PERSON recognizer) is genuinely probabilistic — it can miss short
# inputs, uncommon names, or names with no surrounding sentence context
# to work with. This adds explicit backup patterns for the specific,
# very common phrasing of someone introducing themselves — "my name is
# X", "I'm X", "I am X", "call me X" — which won't catch every name in
# every context, but reliably catches this one very common case that
# spaCy sometimes misses. Each pattern uses a fixed-width lookbehind
# (Python's re module requires that) so the match is just the name
# itself, not the whole phrase — meaning the sentence structure survives
# redaction (e.g. "my name is [PERSON]" rather than losing "my name is"
# entirely).
NAME_INTRO_PATTERNS = [
    Pattern(name="name_is_intro", regex=r"(?<=name is )[A-Z][a-z]+(?:\s[A-Z][a-z]+)?", score=0.8),
    Pattern(name="im_intro", regex=r"(?<=I'm )[A-Z][a-z]+(?:\s[A-Z][a-z]+)?", score=0.75),
    Pattern(name="i_am_intro", regex=r"(?<=I am )[A-Z][a-z]+(?:\s[A-Z][a-z]+)?", score=0.75),
    Pattern(name="call_me_intro", regex=r"(?<=call me )[A-Z][a-z]+(?:\s[A-Z][a-z]+)?", score=0.75),
    Pattern(name="this_is_intro", regex=r"(?<=[Tt]his is )[A-Z][a-z]+(?:\s[A-Z][a-z]+)?", score=0.7),
]

NAME_INTRO_RECOGNIZER = PatternRecognizer(
    supported_entity="PERSON",
    patterns=NAME_INTRO_PATTERNS,
)


def get_custom_recognizers():
    """Return every custom recognizer MindGuard registers with Presidio.

    Import this list from redactor.py and add each one to the
    AnalyzerEngine's registry. Keeping the list-building here means
    adding a new recognizer later is a one-line change in this file
    only — nothing else needs to know about it.
    """
    return [
        DEVICE_ID_RECOGNIZER,
        UUID_RECOGNIZER,
        TIMESTAMP_RECOGNIZER,
        PHONE_RECOGNIZER,
        NAME_INTRO_RECOGNIZER,
    ]