"""
Tests for date validation logic.

Covers:
- DateOrderError when recorded < signed (the sample input case)
- Correct error details
- No error when dates are valid
- DateParseError for unparseable strings
"""

from __future__ import annotations

import pytest

from deed_validator.errors import DateOrderError, DateParseError
from deed_validator.validate import validate
from tests.fixtures import make_enriched


class TestDateOrderError:
    """The sample input has recorded=2024-01-10 < signed=2024-01-15."""

    def test_date_order_error_is_raised(self) -> None:
        _, errors = validate(make_enriched())
        codes = [e.code for e in errors]
        assert "DATE_ORDER_ERROR" in codes

    def test_date_order_error_type(self) -> None:
        _, errors = validate(make_enriched())
        err = next(e for e in errors if e.code == "DATE_ORDER_ERROR")
        assert isinstance(err, DateOrderError)

    def test_date_order_error_details(self) -> None:
        _, errors = validate(make_enriched())
        err = next(e for e in errors if e.code == "DATE_ORDER_ERROR")
        assert err.details["date_signed"] == "2024-01-15"
        assert err.details["date_recorded"] == "2024-01-10"

    def test_date_order_error_message_mentions_both_dates(self) -> None:
        _, errors = validate(make_enriched())
        err = next(e for e in errors if e.code == "DATE_ORDER_ERROR")
        assert "2024-01-15" in err.message
        assert "2024-01-10" in err.message


class TestValidDates:
    """When dates are in the correct order, no DateOrderError should appear."""

    def test_no_date_order_error_when_valid(self) -> None:
        deed = make_enriched(
            date_signed="2024-01-10",
            date_recorded="2024-01-15",
            # Also fix amounts so we only test date logic in isolation
            amount_numeric_raw="$1,200,000.00",
        )
        _, errors = validate(deed)
        date_errors = [e for e in errors if e.code == "DATE_ORDER_ERROR"]
        assert date_errors == []

    def test_same_day_is_acceptable(self) -> None:
        deed = make_enriched(
            date_signed="2024-01-15",
            date_recorded="2024-01-15",
            amount_numeric_raw="$1,200,000.00",
        )
        _, errors = validate(deed)
        date_errors = [e for e in errors if e.code == "DATE_ORDER_ERROR"]
        assert date_errors == []


class TestDateParseError:
    """Unparseable date strings must produce DateParseError."""

    def test_garbage_date_produces_parse_error(self) -> None:
        deed = make_enriched(date_signed="not-a-date")
        _, errors = validate(deed)
        codes = [e.code for e in errors]
        assert "DATE_PARSE_ERROR" in codes

    def test_parse_error_is_correct_type(self) -> None:
        deed = make_enriched(date_signed="not-a-date")
        _, errors = validate(deed)
        err = next(e for e in errors if e.code == "DATE_PARSE_ERROR")
        assert isinstance(err, DateParseError)
        assert err.field_name == "date_signed"
