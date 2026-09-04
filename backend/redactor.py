"""
Stream A backend — interactive chat redaction.
"""

import streamlit as st
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

from backend.recognizers import get_custom_recognizers


@st.cache_resource
def get_engines():
    analyzer = AnalyzerEngine()

    for recognizer in get_custom_recognizers():
        analyzer.registry.add_recognizer(recognizer)

    anonymizer = AnonymizerEngine()
    return analyzer, anonymizer


def analyze_text(text: str, language: str = "en"):
    analyzer, _ = get_engines()
    return analyzer.analyze(text=text, language=language)


def redact_text(text: str, language: str = "en"):
    analyzer, anonymizer = get_engines()
    results = analyzer.analyze(text=text, language=language)
    anonymized = anonymizer.anonymize(text=text, analyzer_results=results)
    return anonymized.text, results


if __name__ == "__main__":
    sample = "Hi, my name is Alex. You can call me at (222) 222-2222."
    output, entities = redact_text(sample)
    print("Input: ", sample)
    print("Output:", output)
    print("Found: ", [(e.entity_type, e.score) for e in entities])