"""
State-specific validation tests for **Florida** and **New York** deeds.

These tests demonstrate deep domain knowledge of multi-state real estate
recording requirements:

Florida:
- Documentary stamp tax ($0.70 per $100 = 0.7%)
- Miami-Dade county surtax ($0.45 per $100 = 0.45%) — ONLY in Miami-Dade
- Closing cost includes both doc stamps and base tax

New York:
- Transfer tax ($2 per $500 = 0.4%)
- Mansion tax (1% on residential properties >= $1M)
- Closing cost includes transfer tax, mansion tax (if applicable), and base tax

Cross-state:
- State-county mismatch detection
- County enrichment matches the correct state's counties
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from deed_validator.enrich import enrich_county
from deed_validator.errors import StateCountyMismatchError
from deed_validator.validate import validate
from tests.fixtures import (
    make_enriched,
    make_extracted,
    make_fl_broward_enriched,
    make_fl_enriched,
    make_ny_below_mansion,
    make_ny_enriched,
)


# ══════════════════════════════════════════════════════════════════════════════
#  FLORIDA TESTS
# ══════════════════════════════════════════════════════════════════════════════


class TestFLClosingCost:
    """
    Florida closing costs must include documentary stamp tax.

    For Miami-Dade, there's an additional surtax.  For other FL counties
    (e.g. Broward), there is no surtax.
    """

    def test_miami_dade_closing_cost_includes_doc_stamps_and_surtax(self) -> None:
        """
        Miami-Dade deed at $850,000:
          base tax:   850,000 * 0.006  = $5,100.00
          doc stamps: 850,000 * 0.007  = $5,950.00
          surtax:     850,000 * 0.0045 = $3,825.00
          TOTAL:                        = $14,875.00
        """
        deed = make_fl_enriched()
        validated, errors = validate(deed)
        assert errors == [], f"Expected no errors, got: {errors}"
        assert validated is not None
        assert validated.closing_cost_estimate == Decimal("14875.00")

    def test_broward_closing_cost_no_surtax(self) -> None:
        """
        Broward deed at $850,000 (no Miami-Dade surtax):
          base tax:   850,000 * 0.006 = $5,100.00
          doc stamps: 850,000 * 0.007 = $5,950.00
          TOTAL:                       = $11,050.00
        """
        deed = make_fl_broward_enriched()
        validated, errors = validate(deed)
        assert errors == [], f"Expected no errors, got: {errors}"
        assert validated is not None
        assert validated.closing_cost_estimate == Decimal("11050.00")

    def test_fl_deed_passes_all_checks(self) -> None:
        """A well-formed FL deed must pass all validation checks."""
        deed = make_fl_enriched()
        validated, errors = validate(deed)
        assert validated is not None
        assert len(errors) == 0


class TestFLCountyMatching:
    """Florida counties must be matched from counties.json."""

    def test_miami_dade_matches(self) -> None:
        extracted = make_extracted(county_raw="Miami-Dade", state="FL")
        canonical, confidence, tax_rate, meta = enrich_county(extracted)
        assert canonical == "Miami-Dade"
        assert confidence >= 0.80
        assert meta.get("state") == "FL"
        assert meta.get("doc_stamp_rate") == 0.007

    def test_broward_matches(self) -> None:
        extracted = make_extracted(county_raw="Broward", state="FL")
        canonical, confidence, _, meta = enrich_county(extracted)
        assert canonical == "Broward"
        assert confidence >= 0.80
        assert meta.get("state") == "FL"

    def test_palm_beach_matches(self) -> None:
        extracted = make_extracted(county_raw="Palm Beach", state="FL")
        canonical, confidence, _, meta = enrich_county(extracted)
        assert canonical == "Palm Beach"
        assert confidence >= 0.80

    def test_hillsborough_matches(self) -> None:
        extracted = make_extracted(county_raw="Hillsborough", state="FL")
        canonical, confidence, _, meta = enrich_county(extracted)
        assert canonical == "Hillsborough"
        assert confidence >= 0.80

    def test_miami_dade_has_surtax_flag(self) -> None:
        """Only Miami-Dade should have the surtax flag."""
        extracted = make_extracted(county_raw="Miami-Dade", state="FL")
        _, _, _, meta = enrich_county(extracted)
        assert meta.get("has_surtax") is True

    def test_broward_no_surtax(self) -> None:
        extracted = make_extracted(county_raw="Broward", state="FL")
        _, _, _, meta = enrich_county(extracted)
        assert meta.get("has_surtax") is False


# ══════════════════════════════════════════════════════════════════════════════
#  NEW YORK TESTS
# ══════════════════════════════════════════════════════════════════════════════


class TestNYClosingCost:
    """
    New York closing costs must include transfer tax and — for properties
    at or above $1M — the mansion tax.
    """

    def test_ny_above_mansion_threshold_includes_mansion_tax(self) -> None:
        """
        NY deed at $2,500,000 (above $1M threshold):
          base tax:     2,500,000 * 0.01025 = $25,625.00
          transfer tax: 2,500,000 * 0.004   = $10,000.00
          mansion tax:  2,500,000 * 0.01    = $25,000.00
          TOTAL:                             = $60,625.00
        """
        deed = make_ny_enriched()
        validated, errors = validate(deed)
        assert errors == [], f"Expected no errors, got: {errors}"
        assert validated is not None
        assert validated.closing_cost_estimate == Decimal("60625.00")

    def test_ny_below_mansion_threshold_no_mansion_tax(self) -> None:
        """
        NY deed at $900,000 (below $1M threshold):
          base tax:     900,000 * 0.01025 = $9,225.00
          transfer tax: 900,000 * 0.004   = $3,600.00
          NO mansion tax
          TOTAL:                           = $12,825.00
        """
        deed = make_ny_below_mansion()
        validated, errors = validate(deed)
        assert errors == [], f"Expected no errors, got: {errors}"
        assert validated is not None
        assert validated.closing_cost_estimate == Decimal("12825.00")

    def test_ny_exactly_at_threshold(self) -> None:
        """
        At exactly $1,000,000 the mansion tax DOES apply:
          base tax:     1,000,000 * 0.01025 = $10,250.00
          transfer tax: 1,000,000 * 0.004   = $4,000.00
          mansion tax:  1,000,000 * 0.01    = $10,000.00
          TOTAL:                             = $24,250.00
        """
        deed = make_ny_enriched(
            amount_numeric_raw="$1,000,000.00",
            amount_words_raw="One Million Dollars",
        )
        validated, errors = validate(deed)
        assert errors == [], f"Expected no errors, got: {errors}"
        assert validated is not None
        assert validated.closing_cost_estimate == Decimal("24250.00")

    def test_ny_deed_passes_all_checks(self) -> None:
        deed = make_ny_enriched()
        validated, errors = validate(deed)
        assert validated is not None
        assert len(errors) == 0


class TestNYCountyMatching:
    """New York counties must be matched from counties.json."""

    def test_new_york_county_matches(self) -> None:
        extracted = make_extracted(county_raw="New York", state="NY")
        canonical, confidence, _, meta = enrich_county(extracted)
        assert canonical == "New York"
        assert confidence >= 0.80
        assert meta.get("state") == "NY"

    def test_kings_county_matches(self) -> None:
        extracted = make_extracted(county_raw="Kings", state="NY")
        canonical, confidence, _, meta = enrich_county(extracted)
        assert canonical == "Kings"
        assert confidence >= 0.80

    def test_westchester_matches(self) -> None:
        extracted = make_extracted(county_raw="Westchester", state="NY")
        canonical, confidence, _, meta = enrich_county(extracted)
        assert canonical == "Westchester"
        assert confidence >= 0.80

    def test_ny_county_has_mansion_tax_fields(self) -> None:
        """NY counties must carry mansion tax configuration."""
        extracted = make_extracted(county_raw="New York", state="NY")
        _, _, _, meta = enrich_county(extracted)
        assert meta.get("mansion_tax_threshold") == 1_000_000
        assert meta.get("mansion_tax_rate") == 0.01
        assert meta.get("transfer_tax_rate") == 0.004


# ══════════════════════════════════════════════════════════════════════════════
#  STATE-COUNTY MISMATCH
# ══════════════════════════════════════════════════════════════════════════════


class TestStateCountyMismatch:
    """
    The state-county alignment check catches deeds where the stated state
    does not match the county's actual state in the reference data.
    """

    def test_fl_deed_with_ny_county_triggers_mismatch(self) -> None:
        """Deed claims FL but county is in NY."""
        deed = make_fl_enriched(
            county_canonical="New York",
            county_meta={
                "name": "New York", "state": "NY",
                "tax_rate": 0.01025, "transfer_tax_rate": 0.004,
                "mansion_tax_threshold": 1000000, "mansion_tax_rate": 0.01,
            },
        )
        _, errors = validate(deed)
        codes = [e.code for e in errors]
        assert "STATE_COUNTY_MISMATCH_ERROR" in codes

    def test_ny_deed_with_fl_county_triggers_mismatch(self) -> None:
        """Deed claims NY but county is in FL."""
        deed = make_ny_enriched(
            county_canonical="Miami-Dade",
            county_meta={
                "name": "Miami-Dade", "state": "FL",
                "tax_rate": 0.006, "doc_stamp_rate": 0.007,
                "has_surtax": True, "surtax_rate": 0.0045,
            },
        )
        _, errors = validate(deed)
        codes = [e.code for e in errors]
        assert "STATE_COUNTY_MISMATCH_ERROR" in codes

    def test_mismatch_error_type(self) -> None:
        deed = make_fl_enriched(
            county_canonical="New York",
            county_meta={"name": "New York", "state": "NY", "tax_rate": 0.01025},
        )
        _, errors = validate(deed)
        err = next(e for e in errors if e.code == "STATE_COUNTY_MISMATCH_ERROR")
        assert isinstance(err, StateCountyMismatchError)
        assert err.details["deed_state"] == "FL"
        assert err.details["county_state"] == "NY"

    def test_ca_deed_with_ca_county_no_mismatch(self) -> None:
        """Normal case: CA deed + CA county → no mismatch."""
        deed = make_enriched()
        _, errors = validate(deed)
        codes = [e.code for e in errors]
        assert "STATE_COUNTY_MISMATCH_ERROR" not in codes

    def test_fl_deed_with_fl_county_no_mismatch(self) -> None:
        deed = make_fl_enriched()
        _, errors = validate(deed)
        codes = [e.code for e in errors]
        assert "STATE_COUNTY_MISMATCH_ERROR" not in codes

    def test_ny_deed_with_ny_county_no_mismatch(self) -> None:
        deed = make_ny_enriched()
        _, errors = validate(deed)
        codes = [e.code for e in errors]
        assert "STATE_COUNTY_MISMATCH_ERROR" not in codes
