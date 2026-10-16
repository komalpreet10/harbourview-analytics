"""Local screening for structured identifiers; not comprehensive PHI detection."""

import re
from functools import lru_cache

PATTERNS = {
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    "resident_id": re.compile(r"\b(?:HV|TEST)[-\s]?\d{4,}\b", re.I),
    "phone": re.compile(r"(?<!\w)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?!\w)|(?<!\w)\d{10}(?!\w)"),
    "labelled_identifier": re.compile(
        r"\b(?:health[ -]?card|medical record|patient id|resident id|SIN)"
        r"\s*(?:number|no\.?|#|:)?\s*[:#]?\s*[A-Z0-9][A-Z0-9 -]{5,}", re.I
    ),
}


@lru_cache(maxsize=1)
def get_analyzer():
    """Load the installed model once; never download models during a request."""
    import spacy
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    if not spacy.util.is_package("en_core_web_sm"):
        raise RuntimeError("Install the local privacy model: python -m spacy download en_core_web_sm")
    engine = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
    }).create_engine()
    return AnalyzerEngine(nlp_engine=engine, supported_languages=["en"])


def contains_identifiers(text: str) -> bool:
    """Screen locally; detector errors block processing rather than bypass it."""
    if any(pattern.search(text) for pattern in PATTERNS.values()):
        return True
    try:
        return bool(get_analyzer().analyze(
            text=text, language="en",
            entities=["PERSON", "LOCATION", "EMAIL_ADDRESS", "PHONE_NUMBER"],
            score_threshold=0.5,
        ))
    except Exception:
        raise RuntimeError(
            "Local privacy screening is unavailable. Check Presidio and the installed language model; no question was sent."
        ) from None
