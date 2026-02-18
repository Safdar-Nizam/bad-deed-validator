"""
Extraction router.

If an OpenAI API key is available, the real LLM client is used.
Otherwise a deterministic JSON fixture is loaded so that the full pipeline
can be demonstrated and tested without any network calls.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from deed_validator import config as _cfg
from deed_validator.models import ExtractedDeed, LLMMeta

logger = logging.getLogger(__name__)

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "extracted_deed.json"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def extract(text: str) -> ExtractedDeed:
    """
    Extract structured fields from raw OCR text.

    Uses the real LLM when ``OPENAI_API_KEY`` is set, otherwise falls back
    to a static fixture file for demo / CI usage.

    Note: reads the API key via module attribute (not a cached import) so
    that test fixtures can safely clear it at runtime.
    """
    if _cfg.OPENAI_API_KEY:
        from deed_validator.llm_client import extract_deed_fields

        logger.info("Using live LLM extraction (model from config)")
        return extract_deed_fields(text)

    logger.warning(
        "OPENAI_API_KEY not set — falling back to fixture extraction (demo/test mode)"
    )
    return _load_fixture(text)


def _load_fixture(text: str) -> ExtractedDeed:
    """Load the pre-built fixture JSON and attach the real source text hash."""
    with open(FIXTURE_PATH) as fh:
        data: dict = json.load(fh)

    # The hash must always reflect the actual input, not the fixture placeholder.
    data["source_text_hash"] = _sha256(text)

    meta_raw = data.pop("llm_meta")
    return ExtractedDeed(**data, llm_meta=LLMMeta(**meta_raw))
