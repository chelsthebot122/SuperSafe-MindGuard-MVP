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
# to work with, and can also mislabel a real name as something else
# entirely (e.g. ORGANIZATION) rather than just missing it. This adds
# explicit backup patterns for the specific, very common phrasing of
# someone introducing themselves — "my name is X", "I'm X", "I am X",
# "call me X" — which won't catch every name in every context, but
# reliably catches this one very common case. Each pattern uses a
# fixed-width lookbehind (Python's re module requires that) so the
# match is just the name itself, not the whole phrase — meaning the
# sentence structure survives redaction (e.g. "my name is [PERSON]"
# rather than losing "my name is" entirely).
#
# Scores here are set slightly ABOVE spaCy's typical default NER
# confidence (~0.85) on purpose: when both a spaCy guess and one of
# these patterns match the same span with different entity types,
# Presidio keeps only the higher-scoring one. Without this, an
# incorrect spaCy guess (e.g. tagging "Chelsea Estrada" as
# ORGANIZATION instead of PERSON) could outrank our correct,
# context-based match.
NAME_INTRO_PATTERNS = [
    # Each lookbehind uses (?<=(?i:...)) — case-insensitivity applies
    # ONLY inside the zero-width lookbehind itself (so "Name is",
    # "NAME IS", and "name is" all match equally), while the actual
    # captured name portion outside it stays case-sensitive and still
    # requires real capitalization. Without this, a phrase at the very
    # start of a sentence ("It's Sarah...") would fail to match at all,
    # since the literal lowercase text "it's " wouldn't be found where
    # the sentence actually has "It's ".
    Pattern(name="name_is_intro", regex=r"(?<=(?i:name is ))[A-Z][a-z]+(?:\s[A-Z][a-z]+)?", score=0.9),
    Pattern(name="im_intro", regex=r"(?<=(?i:I'm ))[A-Z][a-z]+(?:\s[A-Z][a-z]+)?", score=0.88),
    Pattern(name="i_am_intro", regex=r"(?<=(?i:I am ))[A-Z][a-z]+(?:\s[A-Z][a-z]+)?", score=0.88),
    Pattern(name="call_me_intro", regex=r"(?<=(?i:call me ))[A-Z][a-z]+(?:\s[A-Z][a-z]+)?", score=0.88),
    Pattern(name="this_is_intro", regex=r"(?<=(?i:this is ))[A-Z][a-z]+(?:\s[A-Z][a-z]+)?", score=0.86),
    # "it's X" REQUIRES capitalization, same as every pattern above —
    # unlike "my name is X" (almost always followed by an actual
    # name), "it's" is used constantly as an ordinary sentence filler
    # ("it's raining", "it's fine", "it's cold"), far more often than
    # as a name introduction. An earlier version of this pattern
    # allowed lowercase through and it correctly caught "hey it's
    # alex" — but it also caught "raining"/"going"/"fine" as PERSON in
    # completely ordinary sentences, which is a much worse problem
    # than the narrow benefit. Requiring capitalization sacrifices
    # catching a genuinely lowercase-typed name after "it's"
    # specifically, which is the right tradeoff here.
    Pattern(name="its_intro", regex=r"(?<=(?i:it's ))[A-Z][a-z]+(?:\s[A-Z][a-z]+)?", score=0.85),
]

NAME_INTRO_RECOGNIZER = PatternRecognizer(
    supported_entity="PERSON",
    patterns=NAME_INTRO_PATTERNS,
)


# ---------------------------------------------------------------------
# US state abbreviations
# ---------------------------------------------------------------------
# spaCy's NER (especially the smaller model used in production —
# see backend/redactor.py's model fallback) can misclassify a bare
# two-letter state code (e.g. "NJ") as ORGANIZATION instead of
# LOCATION. Rather than depend on the NER model's judgment call at
# all for this specific, small, well-defined set of tokens, this
# matches them directly. Case-SENSITIVE on purpose (no re.IGNORECASE):
# state codes are conventionally written in full caps ("NJ", "CA"),
# while common English words that happen to share two letters ("or",
# "in", "me", "hi", "ok") are essentially never written in full caps
# in ordinary sentence-case prose — keeping this case-sensitive is
# what keeps it from flagging those constantly.
_US_STATE_ABBREVIATIONS = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC",
]

STATE_ABBREVIATION_PATTERN = Pattern(
    name="us_state_abbreviation",
    regex=r"\b(?:" + "|".join(_US_STATE_ABBREVIATIONS) + r")\b",
    score=0.88,
)

STATE_ABBREVIATION_RECOGNIZER = PatternRecognizer(
    supported_entity="LOCATION",
    patterns=[STATE_ABBREVIATION_PATTERN],
)


# ---------------------------------------------------------------------
# City names immediately before a state abbreviation
# ---------------------------------------------------------------------
# Some city names (Austin, Madison, Charlotte...) are ALSO extremely
# common first names — a genuinely hard, well-documented NER ambiguity
# that no general-purpose model resolves perfectly. But "Austin, TX" or
# "Reno, NV" carries strong context we can use directly: a capitalized
# word immediately followed by ", <state abbreviation>" is a city, not
# a person, essentially every time this exact pattern appears. Uses a
# lookahead (not a lookbehind, so no fixed-width restriction applies)
# to match just the city name itself.
CITY_BEFORE_STATE_PATTERN = Pattern(
    name="city_before_state_abbreviation",
    regex=r"[A-Z][a-zA-Z]+(?=,\s(?:" + "|".join(_US_STATE_ABBREVIATIONS) + r")\b)",
    score=0.9,
)

CITY_BEFORE_STATE_RECOGNIZER = PatternRecognizer(
    supported_entity="LOCATION",
    patterns=[CITY_BEFORE_STATE_PATTERN],
)


# ---------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------
# Presidio has no built-in concept of "password" at all — it's not a
# standard PII category the way an email or SSN is, so nothing was
# ever going to catch one without an explicit recognizer for it. This
# uses the same "catch it right after common introductory phrasing"
# approach as the name patterns above: "password is X", "password: X".
# The (?i) makes each pattern case-insensitive (matches "Password is",
# "PASSWORD:", etc. too) — this doesn't affect the fixed-width
# lookbehind requirement, since inline flags are zero-width themselves.
PASSWORD_PATTERNS = [
    Pattern(name="password_is_intro", regex=r"(?i)(?<=password is )\S+", score=0.9),
    Pattern(name="password_colon_intro", regex=r"(?i)(?<=password:\s)\S+", score=0.9),
]

PASSWORD_RECOGNIZER = PatternRecognizer(
    supported_entity="PASSWORD",
    patterns=PASSWORD_PATTERNS,
)


# ---------------------------------------------------------------------
# Account numbers
# ---------------------------------------------------------------------
# A bare digit string (e.g. a 9-digit number) can simultaneously match
# several of Presidio's generic built-in recognizers at once (DATE_TIME,
# US_PASSPORT, US_DRIVER_LICENSE all use fairly generic digit-count
# patterns without strong disambiguation) — the number likely still
# gets redacted either way, but under a confusing/wrong label. Explicit
# context ("account number is X") is a strong, unambiguous signal this
# pattern-matches directly, so it gets labeled correctly instead of
# leaving it to whichever generic recognizer happens to win. Labeled
# generically as ACCOUNT_NUMBER rather than assuming it's specifically
# a BANK account — the phrase "account number" alone doesn't say what
# kind of account it is (could be a membership, utility, subscription
# account, etc.), so labeling it "bank" specifically would be an
# assumption the input never actually supports.
ACCOUNT_NUMBER_PATTERNS = [
    Pattern(name="account_number_intro", regex=r"(?i)(?<=account number is )\d{4,17}", score=0.9),
    Pattern(name="account_number_colon_intro", regex=r"(?i)(?<=account number:\s)\d{4,17}", score=0.9),
]

ACCOUNT_NUMBER_RECOGNIZER = PatternRecognizer(
    supported_entity="ACCOUNT_NUMBER",
    patterns=ACCOUNT_NUMBER_PATTERNS,
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
        STATE_ABBREVIATION_RECOGNIZER,
        CITY_BEFORE_STATE_RECOGNIZER,
        PASSWORD_RECOGNIZER,
        ACCOUNT_NUMBER_RECOGNIZER,
    ]