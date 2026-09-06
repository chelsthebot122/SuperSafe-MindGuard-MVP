"""
Stream A backend — interactive chat redaction.

This wraps Presidio's two engines:
  - AnalyzerEngine: finds PII in text and returns a list of RecognizerResult
                    (entity type, start/end position, confidence score)
  - AnonymizerEngine: takes that list and actually replaces the text
                      (e.g. "Alex" -> "[PERSON]")

Both engines are expensive to build (they load a spaCy model under the
hood), so get_engines() is wrapped in st.cache_resource — Streamlit will
build them exactly once per session instead of on every rerun/click.
"""

import re

import spacy
import streamlit as st
from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider

from backend.recognizers import get_custom_recognizers

# Preference order for the spaCy model. Locally, en_core_web_lg is
# installed (better accuracy). On Streamlit Community Cloud, only
# en_core_web_sm is installed (via requirements.txt) — the large model
# risks pushing the app over the platform's free-tier memory limit
# (~2.7GB max). This tries each in order and uses whichever one is
# actually present, so the exact same code runs correctly in both
# environments without needing separate config per environment.
_SPACY_MODEL_PREFERENCE = ["en_core_web_lg", "en_core_web_sm"]


def _build_analyzer_engine() -> AnalyzerEngine:
    last_error = None
    for model_name in _SPACY_MODEL_PREFERENCE:
        # Check whether the model is actually installed BEFORE ever
        # trying to load it. spacy.util.is_package() is a safe,
        # side-effect-free check (just inspects installed package
        # metadata, no network/pip involved) — it cannot trigger any
        # download attempt. Skipping straight past a missing model
        # this way is what actually matters here: on a deployed
        # environment where only en_core_web_sm is installed, trying
        # to load en_core_web_lg without this check first was
        # triggering an automatic live pip-install attempt somewhere
        # in Presidio/spaCy's own model-loading path, which then
        # failed in an infinite retry loop (Streamlit Cloud's live
        # container filesystem is read-only, so that install could
        # never succeed) — never attempting to load a model that
        # isn't there avoids that path entirely.
        if not spacy.util.is_package(model_name):
            continue
        try:
            provider = NlpEngineProvider(nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": model_name}],
            })
            nlp_engine = provider.create_engine()
            return AnalyzerEngine(nlp_engine=nlp_engine)
        except Exception as e:
            # Deliberately broad, not just OSError: repeated failed
            # install attempts on a read-only deployed filesystem can
            # leave a model's package directory in a partial/corrupted
            # state (pip errors out mid-extraction), which can fool
            # is_package() into reporting the model as present when
            # it's actually broken — and whatever failure that produces
            # further down isn't guaranteed to surface as a plain
            # OSError. Catching broadly here means any such failure
            # still falls through to trying the next model in the
            # preference list, instead of crashing the whole app.
            last_error = e
            continue
    raise RuntimeError(
        "No spaCy English model found — tried: "
        f"{', '.join(_SPACY_MODEL_PREFERENCE)}. "
        "Run `python -m spacy download en_core_web_lg` (or _sm) locally, "
        "or add the model's wheel URL to requirements.txt for deployment."
    ) from last_error


@st.cache_resource(show_spinner=False)
def get_engines():
    analyzer = _build_analyzer_engine()

    # Register MindGuard's custom recognizers (device IDs, UUIDs, fine
    # timestamps) alongside Presidio's built-in ones (PERSON,
    # PHONE_NUMBER, EMAIL_ADDRESS, etc.)
    for recognizer in get_custom_recognizers():
        analyzer.registry.add_recognizer(recognizer)

    from presidio_anonymizer import AnonymizerEngine
    anonymizer = AnonymizerEngine()
    return analyzer, anonymizer


# ---------------------------------------------------------------------
# False-positive filtering
# ---------------------------------------------------------------------
# Common short function words that spaCy's general-purpose NER model
# occasionally mis-tags as PERSON, especially in short or unusually
# punctuated inputs (e.g. "call me at 8668865" catching "at"). This is
# a known limitation of general NER, not something tunable via
# Presidio's config — real names essentially never overlap with this
# list, so filtering by it is a safe way to cut false positives without
# risking real names.
PERSON_FALSE_POSITIVE_WORDS = {
    "a", "an", "the", "at", "is", "am", "are", "was", "were", "be", "been",
    "being", "to", "of", "in", "on", "for", "with", "by", "this", "that",
    "it", "he", "she", "we", "you", "i", "me", "my", "your", "and", "or",
    "but", "so", "if", "as", "than", "then", "there", "here", "not", "no",
}

_HAS_DIGIT = re.compile(r"\d")

# Phrases that justify allowing a LOWERCASE PERSON match through (see
# the exemption below) — these are the exact same intro phrases the
# custom name-introduction patterns in recognizers.py key off of, so a
# lowercase name is only ever allowed through when it's backed by this
# specific, deliberate context.
_NAME_INTRO_PRECEDING_PHRASES = [
    "name is ", "i'm ", "i am ", "call me ", "this is ", "it's ",
]


def _preceded_by_name_intro(text: str, start: int) -> bool:
    prefix = text[:start].lower()
    return any(prefix.endswith(phrase) for phrase in _NAME_INTRO_PRECEDING_PHRASES)


def _is_false_positive(entity, text: str) -> bool:
    matched = text[entity.start:entity.end].strip()

    if entity.entity_type == "DATE_TIME":
        # Presidio's DATE_TIME recognizer is deliberately broad — it's
        # built to catch ANY temporal reference, vague or specific,
        # which is exactly why "the day", "a good day", and "the
        # evening" get flagged. A genuinely identifying date (e.g.
        # "March 15, 2024") almost always contains a digit; a vague
        # phrase almost never does. Filtering on that keeps real dates
        # while dropping the noise, rather than disabling DATE_TIME
        # entirely and losing real dates too.
        if not _HAS_DIGIT.search(matched):
            return True

    if entity.entity_type == "PERSON":
        if matched.lower() in PERSON_FALSE_POSITIVE_WORDS:
            return True
        if len(matched) <= 2:
            # Real first names are essentially never this short — a
            # general backstop against other short misfires beyond the
            # curated word list above.
            return True
        if not matched[0].isupper():
            # Real names are essentially never written in all-lowercase
            # in properly-cased text — this catches phrase-level
            # misfires like "going to" getting tagged PERSON. But a
            # genuinely casual/lowercase message ("hey it's alex") is
            # real too, so this isn't a blanket rejection: a lowercase
            # match is still allowed through if it's BOTH a single
            # word (no internal space — "going to" has one, "alex"
            # doesn't) AND immediately preceded by one of the exact
            # intro phrases above. That combination is deliberately
            # narrow — it's what lets "it's alex" through while still
            # catching "going to" right after "I'm " in the same
            # sentence, since "going to" fails the single-word check.
            is_single_word = " " not in matched
            if not (is_single_word and _preceded_by_name_intro(text, entity.start)):
                return True

    return False


def _resolve_overlaps(entities):
    """When multiple recognizers match the same or overlapping text
    span with different entity types (e.g. a bare 9-digit number
    simultaneously matching BANK_ACCOUNT_NUMBER, DATE_TIME,
    US_PASSPORT, and US_DRIVER_LICENSE all at once), keep only the
    single highest-scoring match per span and discard the rest.

    Presidio's own AnonymizerEngine already effectively does this when
    it applies replacements to text — that's why the redacted OUTPUT
    text was already coming out clean even before this existed. But it
    doesn't change the returned entity LIST itself, which is what the
    'Identified Entities' card and the PRI score both read — so
    without this, they were double/triple/quadruple-counting the same
    underlying piece of data under multiple labels.
    """
    if not entities:
        return entities

    # Highest-scoring match wins each overlapping cluster.
    by_score_desc = sorted(entities, key=lambda e: e.score, reverse=True)
    kept = []
    for entity in by_score_desc:
        overlaps_kept = any(
            entity.start < k.end and entity.end > k.start
            for k in kept
        )
        if not overlaps_kept:
            kept.append(entity)

    # Return in the order they appear in the text, not score order —
    # reads naturally in the UI.
    return sorted(kept, key=lambda e: e.start)


def analyze_text(text: str, language: str = "en"):
    """Run detection only — returns the list of RecognizerResult after
    both false-positive filtering AND overlap resolution (see
    _resolve_overlaps above), so this is already the clean, final list
    — one entry per actual piece of data, no duplicates. Useful when
    you want to show *what* was found before deciding how to redact it
    (e.g. for the PRI score or the 'Identified Entities' card in
    Stream A). Stream B's content-based column scanner also calls
    this, so the same filtering benefits both streams."""
    analyzer, _ = get_engines()
    results = analyzer.analyze(text=text, language=language)
    filtered = [e for e in results if not _is_false_positive(e, text)]
    return _resolve_overlaps(filtered)


def redact_text(text: str, language: str = "en"):
    """Full pipeline: detect entities (via analyze_text, so the same
    false-positive filtering applies here too), then anonymize the text.

    Returns a tuple of (anonymized_text, entities_found) so the caller
    has both the sanitized output and the raw detections (e.g. to
    render the 'Identified Entities' list and compute the PRI without
    re-running analysis a second time).
    """
    analyzer, anonymizer = get_engines()
    results = analyze_text(text, language)
    anonymized = anonymizer.anonymize(text=text, analyzer_results=results)
    return anonymized.text, results


if __name__ == "__main__":
    # Quick manual test — run `python -m backend.redactor` from the
    # project root to sanity-check the pipeline without touching
    # Streamlit at all.
    sample = "Hi, my name is Alex. You can call me at (222) 222-2222."
    output, entities = redact_text(sample)
    print("Input: ", sample)
    print("Output:", output)
    print("Found: ", [(e.entity_type, e.score) for e in entities])