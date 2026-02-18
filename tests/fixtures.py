"""
Deterministic test fixtures.

These helpers build ``ExtractedDeed`` and ``EnrichedDeed`` objects with
the same data as the default OCR sample.  Override any field via keyword
arguments so that individual tests can isolate specific scenarios.

Includes state-specific factories for **Florida** and **New York** deeds
to demonstrate multi-state validation awareness.

No LLM is called — these are pure data factories.
"""

from __future__ import annotations

from deed_validator.models import EnrichedDeed, ExtractedDeed, LLMMeta

_META = LLMMeta(model="fixture", extraction_timestamp="2024-01-01T00:00:00+00:00")


# ── Base (California sample) ─────────────────────────────────────────────────

_BASE_EXTRACTED: dict = dict(
    doc_id="DEED-TRUST-0042",
    county_raw="S. Clara",
    state="CA",
    date_signed="2024-01-15",
    date_recorded="2024-01-10",
    grantor="T.E.S.L.A. Holdings LLC",
    grantee="John & Sarah Connor",
    amount_numeric_raw="$1,250,000.00",
    amount_words_raw="One Million Two Hundred Thousand Dollars",
    apn="992-001-XA",
    status="PRELIMINARY",
    source_text_hash="abc123facadedeadbeef",
    llm_meta=_META,
)

_BASE_ENRICHED: dict = dict(
    **_BASE_EXTRACTED,
    county_canonical="Santa Clara",
    county_match_confidence=0.95,
    tax_rate=0.012,
    county_meta={"name": "Santa Clara", "state": "CA", "tax_rate": 0.012},
)


def make_extracted(**overrides: object) -> ExtractedDeed:
    """Build an ``ExtractedDeed`` with optional field overrides."""
    return ExtractedDeed(**{**_BASE_EXTRACTED, **overrides})


def make_enriched(**overrides: object) -> EnrichedDeed:
    """Build an ``EnrichedDeed`` with optional field overrides."""
    return EnrichedDeed(**{**_BASE_ENRICHED, **overrides})


# ── Florida (Miami-Dade) ─────────────────────────────────────────────────────

_FL_ENRICHED: dict = dict(
    doc_id="DEED-FL-001",
    county_raw="Miami-Dade",
    state="FL",
    date_signed="2024-03-01",
    date_recorded="2024-03-05",
    grantor="Sun Holdings LLC",
    grantee="Jane Smith",
    amount_numeric_raw="$850,000.00",
    amount_words_raw="Eight Hundred Fifty Thousand Dollars",
    apn="01-3210-0100",
    status="FINAL",
    source_text_hash="fl_test_hash",
    llm_meta=_META,
    county_canonical="Miami-Dade",
    county_match_confidence=1.0,
    tax_rate=0.006,
    county_meta={
        "name": "Miami-Dade",
        "state": "FL",
        "tax_rate": 0.006,
        "doc_stamp_rate": 0.007,
        "has_surtax": True,
        "surtax_rate": 0.0045,
    },
)


def make_fl_enriched(**overrides: object) -> EnrichedDeed:
    """Build an ``EnrichedDeed`` for a Florida (Miami-Dade) deed."""
    return EnrichedDeed(**{**_FL_ENRICHED, **overrides})


# ── Florida (Broward — no surtax) ────────────────────────────────────────────

_FL_BROWARD_ENRICHED: dict = {
    **_FL_ENRICHED,
    "county_raw": "Broward",
    "county_canonical": "Broward",
    "county_meta": {
        "name": "Broward",
        "state": "FL",
        "tax_rate": 0.006,
        "doc_stamp_rate": 0.007,
        "has_surtax": False,
    },
}


def make_fl_broward_enriched(**overrides: object) -> EnrichedDeed:
    """Build an ``EnrichedDeed`` for a Florida (Broward) deed — no surtax."""
    return EnrichedDeed(**{**_FL_BROWARD_ENRICHED, **overrides})


# ── New York (Manhattan / New York County) ────────────────────────────────────

_NY_ENRICHED: dict = dict(
    doc_id="DEED-NY-001",
    county_raw="New York",
    state="NY",
    date_signed="2024-05-10",
    date_recorded="2024-05-15",
    grantor="Manhattan Holdings Group",
    grantee="Robert Johnson",
    amount_numeric_raw="$2,500,000.00",
    amount_words_raw="Two Million Five Hundred Thousand Dollars",
    apn="100-200-300",
    status="FINAL",
    source_text_hash="ny_test_hash",
    llm_meta=_META,
    county_canonical="New York",
    county_match_confidence=1.0,
    tax_rate=0.01025,
    county_meta={
        "name": "New York",
        "state": "NY",
        "tax_rate": 0.01025,
        "transfer_tax_rate": 0.004,
        "mansion_tax_threshold": 1000000,
        "mansion_tax_rate": 0.01,
    },
)


def make_ny_enriched(**overrides: object) -> EnrichedDeed:
    """Build an ``EnrichedDeed`` for a New York (Manhattan) deed."""
    return EnrichedDeed(**{**_NY_ENRICHED, **overrides})


# ── New York (below mansion tax threshold) ────────────────────────────────────

def make_ny_below_mansion(**overrides: object) -> EnrichedDeed:
    """Build an ``EnrichedDeed`` for a NY deed under the $1M mansion tax threshold."""
    base = {
        **_NY_ENRICHED,
        "amount_numeric_raw": "$900,000.00",
        "amount_words_raw": "Nine Hundred Thousand Dollars",
    }
    return EnrichedDeed(**{**base, **overrides})
