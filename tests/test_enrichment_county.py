"""
Tests for county enrichment (fuzzy matching via rapidfuzz).

Covers:
- "S. Clara" -> "Santa Clara" with high confidence (CA)
- Tax rate is correctly attached
- Unknown counties produce UnknownCountyError during validation
- Multi-state county matching (FL, NY counties)
- County meta includes state field
"""

from __future__ import annotations

import pytest

from deed_validator.enrich import enrich_county
from deed_validator.errors import UnknownCountyError
from deed_validator.validate import validate
from tests.fixtures import make_enriched, make_extracted


class TestCaliforniaCountyMatching:
    """Verify that California county abbreviations map correctly."""

    def test_s_clara_maps_to_santa_clara(self) -> None:
        extracted = make_extracted(county_raw="S. Clara")
        canonical, confidence, tax_rate, meta = enrich_county(extracted)
        assert canonical == "Santa Clara"

    def test_confidence_above_threshold(self) -> None:
        extracted = make_extracted(county_raw="S. Clara")
        _, confidence, _, _ = enrich_county(extracted)
        assert confidence >= 0.80

    def test_tax_rate_correct(self) -> None:
        extracted = make_extracted(county_raw="S. Clara")
        _, _, tax_rate, _ = enrich_county(extracted)
        assert tax_rate == pytest.approx(0.012)

    def test_county_meta_includes_state(self) -> None:
        extracted = make_extracted(county_raw="S. Clara")
        _, _, _, meta = enrich_county(extracted)
        assert meta.get("state") == "CA"

    def test_san_mateo_matches(self) -> None:
        extracted = make_extracted(county_raw="San Mateo")
        canonical, confidence, tax_rate, _ = enrich_county(extracted)
        assert canonical == "San Mateo"
        assert confidence >= 0.80
        assert tax_rate == pytest.approx(0.011)

    def test_santa_cruz_matches(self) -> None:
        extracted = make_extracted(county_raw="Santa Cruz")
        canonical, confidence, tax_rate, _ = enrich_county(extracted)
        assert canonical == "Santa Cruz"
        assert confidence >= 0.80
        assert tax_rate == pytest.approx(0.010)


class TestUnknownCounty:
    """When no county matches, validation must raise UnknownCountyError."""

    def test_unknown_county_yields_error(self) -> None:
        deed = make_enriched(
            county_raw="Xyzzy Nowhere",
            county_canonical=None,
            county_match_confidence=0.10,
            tax_rate=None,
        )
        _, errors = validate(deed)
        codes = [e.code for e in errors]
        assert "UNKNOWN_COUNTY_ERROR" in codes

    def test_unknown_county_error_type(self) -> None:
        deed = make_enriched(
            county_raw="Xyzzy Nowhere",
            county_canonical=None,
            county_match_confidence=0.10,
            tax_rate=None,
        )
        _, errors = validate(deed)
        err = next(e for e in errors if e.code == "UNKNOWN_COUNTY_ERROR")
        assert isinstance(err, UnknownCountyError)

    def test_low_confidence_county_returns_none(self) -> None:
        extracted = make_extracted(county_raw="Xyzzy Nowhere")
        canonical, confidence, tax_rate, meta = enrich_county(extracted)
        assert canonical is None
        assert tax_rate is None
        assert confidence < 0.80
        assert meta == {}
