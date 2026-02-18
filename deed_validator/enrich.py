"""
Deterministic county enrichment using ``rapidfuzz``.

Maps an OCR county string (e.g. ``"S. Clara"``) to a canonical county name
from ``counties.json`` via normalisation + fuzzy token-sort similarity.

The enricher is **multi-state aware** — each county in ``counties.json``
carries a ``state`` field so that downstream validation can detect
state-county mismatches (e.g. a deed claiming "FL" with a CA county).

If the best match score is below ``COUNTY_MATCH_THRESHOLD`` the canonical
name is set to ``None`` and validation will later raise ``UnknownCountyError``.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from typing import Any, Optional

from rapidfuzz import fuzz

from deed_validator.config import COUNTIES_FILE
from deed_validator.constants import COUNTY_MATCH_THRESHOLD
from deed_validator.models import EnrichedDeed, ExtractedDeed

logger = logging.getLogger(__name__)

# Common abbreviation expansions.
_ABBREVIATIONS: list[tuple[str, str]] = [
    (r"\bs\.?\s*", "santa "),   # "S." or "S " → "santa "
    (r"\bst\.?\s*", "santa "),  # "St." or "St " → "santa "
    (r"\bsn\.?\s*", "san "),    # "Sn." → "san "
]


_COUNTY_CACHE: list[dict[str, Any]] | None = None


def _load_counties() -> list[dict[str, Any]]:
    """Read the reference county list from disk (cached after first call)."""
    global _COUNTY_CACHE
    if _COUNTY_CACHE is None:
        with open(COUNTIES_FILE) as fh:
            _COUNTY_CACHE = json.load(fh)
    return _COUNTY_CACHE


def _normalize(text: str) -> str:
    """
    Normalise a county string for fuzzy comparison.

    Steps: unicode NFKD → lowercase → expand abbreviations →
    strip punctuation → collapse whitespace.
    """
    text = unicodedata.normalize("NFKD", text).lower().strip()

    # Expand abbreviations *before* stripping punctuation so the dot is
    # still present for the regex anchors.
    for pattern, replacement in _ABBREVIATIONS:
        text = re.sub(pattern, replacement, text, count=1)

    # Remove remaining punctuation, keep letters/digits/spaces.
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def enrich_county(
    extracted: ExtractedDeed,
) -> tuple[Optional[str], float, Optional[float], dict[str, Any]]:
    """
    Match ``extracted.county_raw`` against the reference county list.

    Returns
    -------
    (canonical_name | None, confidence, tax_rate | None, county_meta)

    ``county_meta`` is the full county record from counties.json (including
    the ``state`` field and any state-specific rate fields).
    """
    counties = _load_counties()
    raw_norm = _normalize(extracted.county_raw)

    best_name: Optional[str] = None
    best_score: float = 0.0
    best_tax: Optional[float] = None
    best_meta: dict[str, Any] = {}

    for county in counties:
        canon_norm = _normalize(county["name"])
        # rapidfuzz token_sort_ratio returns 0–100; we normalise to 0–1.
        score = fuzz.token_sort_ratio(raw_norm, canon_norm) / 100.0
        logger.debug("  '%s' vs '%s' → %.3f", raw_norm, canon_norm, score)
        if score > best_score:
            best_score = score
            best_name = county["name"]
            best_tax = county["tax_rate"]
            best_meta = county

    if best_score >= COUNTY_MATCH_THRESHOLD:
        logger.info(
            "County '%s' → '%s' (confidence=%.2f, state=%s)",
            extracted.county_raw, best_name, best_score,
            best_meta.get("state", "?"),
        )
        return best_name, best_score, best_tax, best_meta

    logger.warning(
        "County '%s' unmatched (best=%.2f < threshold=%.2f)",
        extracted.county_raw, best_score, COUNTY_MATCH_THRESHOLD,
    )
    return None, best_score, None, {}


def build_enriched_deed(extracted: ExtractedDeed) -> EnrichedDeed:
    """
    Run county enrichment and return a new ``EnrichedDeed`` with the results
    merged in.
    """
    canonical, confidence, tax_rate, county_meta = enrich_county(extracted)

    return EnrichedDeed(
        **extracted.model_dump(),
        county_canonical=canonical,
        county_match_confidence=confidence,
        tax_rate=tax_rate,
        county_meta=county_meta,
    )
