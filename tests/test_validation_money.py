"""
Tests for amount / money validation logic.

Covers:
- AmountMismatchError when numeric ≠ words (the sample input case)
- Correct error values and difference
- No error when amounts match
"""

from __future__ import annotations

import pytest

from deed_validator.errors import AmountMismatchError
from deed_validator.validate import validate
from tests.fixtures import make_enriched


class TestAmountMismatchError:
    """
    Sample input: $1,250,000 (numeric) vs "One Million Two Hundred Thousand"
    (words = 1,200,000).  Difference = 50,000.
    """

    def test_mismatch_is_raised(self) -> None:
        _, errors = validate(make_enriched())
        codes = [e.code for e in errors]
        assert "AMOUNT_MISMATCH_ERROR" in codes

    def test_mismatch_is_correct_type(self) -> None:
        _, errors = validate(make_enriched())
        err = next(e for e in errors if e.code == "AMOUNT_MISMATCH_ERROR")
        assert isinstance(err, AmountMismatchError)

    def test_mismatch_details_numeric_value(self) -> None:
        _, errors = validate(make_enriched())
        err = next(e for e in errors if e.code == "AMOUNT_MISMATCH_ERROR")
        assert err.details["amount_numeric_value"] == 1_250_000

    def test_mismatch_details_words_value(self) -> None:
        _, errors = validate(make_enriched())
        err = next(e for e in errors if e.code == "AMOUNT_MISMATCH_ERROR")
        assert err.details["amount_words_value"] == 1_200_000

    def test_mismatch_details_difference(self) -> None:
        _, errors = validate(make_enriched())
        err = next(e for e in errors if e.code == "AMOUNT_MISMATCH_ERROR")
        assert err.details["difference"] == 50_000


class TestMatchingAmounts:
    """When both representations agree, no AmountMismatchError should appear."""

    def test_no_mismatch_when_amounts_agree(self) -> None:
        deed = make_enriched(
            date_signed="2024-01-10",
            date_recorded="2024-01-15",
            amount_numeric_raw="$1,200,000.00",
            amount_words_raw="One Million Two Hundred Thousand Dollars",
        )
        _, errors = validate(deed)
        amount_errors = [e for e in errors if e.code == "AMOUNT_MISMATCH_ERROR"]
        assert amount_errors == []
