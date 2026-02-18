"""
Tests for the extended validation checks:
  - APN format (numeric-only segments)
  - Future date rejection
  - Stale recording (gap > 365 days)
  - Grantor/grantee same party (self-dealing)
  - Amount range (zero, negative, ceiling)
  - State code validation
  - State-county mismatch
  - Full sample input produces exactly 3 errors
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from deed_validator.errors import (
    APNFormatError,
    AmountRangeError,
    FutureDateError,
    GrantorGranteeSameError,
    StaleRecordingError,
    StateCodeError,
)
from deed_validator.validate import validate
from tests.fixtures import make_enriched


# ── APN format ───────────────────────────────────────────────────────────────


class TestAPNFormat:
    """APNs are numeric-only segments like 123-456-789."""

    def test_apn_with_letters_triggers_error(self) -> None:
        """Sample APN 992-001-XA has 'XA' — must be caught."""
        _, errors = validate(make_enriched())
        codes = [e.code for e in errors]
        assert "APN_FORMAT_ERROR" in codes

    def test_apn_error_is_correct_type(self) -> None:
        _, errors = validate(make_enriched())
        err = next(e for e in errors if e.code == "APN_FORMAT_ERROR")
        assert isinstance(err, APNFormatError)
        assert "XA" in err.details["invalid_segments"]

    def test_numeric_apn_no_error(self) -> None:
        deed = make_enriched(
            apn="992-001-003",
            date_signed="2024-01-10",
            date_recorded="2024-01-15",
            amount_numeric_raw="$1,200,000.00",
        )
        _, errors = validate(deed)
        apn_errors = [e for e in errors if e.code == "APN_FORMAT_ERROR"]
        assert apn_errors == []

    def test_single_segment_numeric_ok(self) -> None:
        deed = make_enriched(
            apn="992001003",
            date_signed="2024-01-10",
            date_recorded="2024-01-15",
            amount_numeric_raw="$1,200,000.00",
        )
        _, errors = validate(deed)
        apn_errors = [e for e in errors if e.code == "APN_FORMAT_ERROR"]
        assert apn_errors == []


# ── Future date ──────────────────────────────────────────────────────────────


class TestFutureDate:
    """Deeds cannot be signed or recorded in the future."""

    def test_future_signed_date_triggers_error(self) -> None:
        future = str(date.today() + timedelta(days=30))
        deed = make_enriched(date_signed=future, date_recorded=future)
        _, errors = validate(deed)
        future_errors = [e for e in errors if e.code == "FUTURE_DATE_ERROR"]
        assert len(future_errors) >= 1
        fields = [e.field_name for e in future_errors]
        assert "date_signed" in fields

    def test_future_recorded_date_triggers_error(self) -> None:
        future = str(date.today() + timedelta(days=30))
        deed = make_enriched(
            date_signed="2024-01-10",
            date_recorded=future,
        )
        _, errors = validate(deed)
        future_errors = [e for e in errors if e.code == "FUTURE_DATE_ERROR"]
        assert len(future_errors) >= 1

    def test_past_dates_no_future_error(self) -> None:
        deed = make_enriched(
            date_signed="2024-01-10",
            date_recorded="2024-01-15",
            amount_numeric_raw="$1,200,000.00",
            apn="992-001-003",
        )
        _, errors = validate(deed)
        future_errors = [e for e in errors if e.code == "FUTURE_DATE_ERROR"]
        assert future_errors == []


# ── Stale recording ──────────────────────────────────────────────────────────


class TestStaleRecording:
    """Recording gap > 365 days from signing is suspicious."""

    def test_stale_recording_triggers_error(self) -> None:
        deed = make_enriched(
            date_signed="2022-01-01",
            date_recorded="2024-06-01",
            amount_numeric_raw="$1,200,000.00",
            apn="992-001-003",
        )
        _, errors = validate(deed)
        codes = [e.code for e in errors]
        assert "STALE_RECORDING_ERROR" in codes

    def test_stale_recording_correct_type(self) -> None:
        deed = make_enriched(
            date_signed="2022-01-01",
            date_recorded="2024-06-01",
            amount_numeric_raw="$1,200,000.00",
            apn="992-001-003",
        )
        _, errors = validate(deed)
        err = next(e for e in errors if e.code == "STALE_RECORDING_ERROR")
        assert isinstance(err, StaleRecordingError)
        assert err.details["gap_days"] > 365

    def test_normal_gap_no_stale_error(self) -> None:
        deed = make_enriched(
            date_signed="2024-01-10",
            date_recorded="2024-02-15",
            amount_numeric_raw="$1,200,000.00",
            apn="992-001-003",
        )
        _, errors = validate(deed)
        stale = [e for e in errors if e.code == "STALE_RECORDING_ERROR"]
        assert stale == []


# ── Grantor/grantee same party ───────────────────────────────────────────────


class TestGrantorGranteeSame:
    """Self-dealing: the same entity on both sides of a deed is invalid."""

    def test_same_party_triggers_error(self) -> None:
        deed = make_enriched(
            grantor="Acme Corp",
            grantee="Acme Corp",
        )
        _, errors = validate(deed)
        codes = [e.code for e in errors]
        assert "GRANTOR_GRANTEE_SAME_ERROR" in codes

    def test_case_insensitive_match(self) -> None:
        deed = make_enriched(
            grantor="ACME CORP",
            grantee="acme corp",
        )
        _, errors = validate(deed)
        codes = [e.code for e in errors]
        assert "GRANTOR_GRANTEE_SAME_ERROR" in codes

    def test_different_parties_no_error(self) -> None:
        deed = make_enriched(
            date_signed="2024-01-10",
            date_recorded="2024-01-15",
            amount_numeric_raw="$1,200,000.00",
            apn="992-001-003",
        )
        _, errors = validate(deed)
        party_errors = [e for e in errors if e.code == "GRANTOR_GRANTEE_SAME_ERROR"]
        assert party_errors == []


# ── Amount range ─────────────────────────────────────────────────────────────


class TestAmountRange:
    """Zero, negative, or absurdly large amounts must be flagged."""

    def test_zero_amount_triggers_error(self) -> None:
        deed = make_enriched(
            amount_numeric_raw="$0.00",
            amount_words_raw="Zero Dollars",
        )
        _, errors = validate(deed)
        codes = [e.code for e in errors]
        assert "AMOUNT_RANGE_ERROR" in codes

    def test_excessive_amount_triggers_error(self) -> None:
        deed = make_enriched(
            amount_numeric_raw="$999,999,999,999.00",
            amount_words_raw="Zero Dollars",
        )
        _, errors = validate(deed)
        codes = [e.code for e in errors]
        assert "AMOUNT_RANGE_ERROR" in codes

    def test_normal_amount_no_range_error(self) -> None:
        deed = make_enriched(
            date_signed="2024-01-10",
            date_recorded="2024-01-15",
            amount_numeric_raw="$1,200,000.00",
            amount_words_raw="One Million Two Hundred Thousand Dollars",
            apn="992-001-003",
        )
        _, errors = validate(deed)
        range_errors = [e for e in errors if e.code == "AMOUNT_RANGE_ERROR"]
        assert range_errors == []


# ── State code ───────────────────────────────────────────────────────────────


class TestStateCode:
    """State abbreviation must be a real US state."""

    def test_invalid_state_triggers_error(self) -> None:
        deed = make_enriched(state="ZZ")
        _, errors = validate(deed)
        codes = [e.code for e in errors]
        assert "STATE_CODE_ERROR" in codes

    def test_valid_state_no_error(self) -> None:
        deed = make_enriched(
            state="CA",
            date_signed="2024-01-10",
            date_recorded="2024-01-15",
            amount_numeric_raw="$1,200,000.00",
            apn="992-001-003",
        )
        _, errors = validate(deed)
        state_errors = [e for e in errors if e.code == "STATE_CODE_ERROR"]
        assert state_errors == []

    def test_lowercase_state_accepted(self) -> None:
        """Validation normalises to uppercase, so 'ca' should pass."""
        deed = make_enriched(
            state="ca",
            date_signed="2024-01-10",
            date_recorded="2024-01-15",
            amount_numeric_raw="$1,200,000.00",
            apn="992-001-003",
        )
        _, errors = validate(deed)
        state_errors = [e for e in errors if e.code == "STATE_CODE_ERROR"]
        assert state_errors == []

    def test_florida_state_valid(self) -> None:
        deed = make_enriched(state="FL")
        _, errors = validate(deed)
        state_errors = [e for e in errors if e.code == "STATE_CODE_ERROR"]
        assert state_errors == []

    def test_new_york_state_valid(self) -> None:
        deed = make_enriched(state="NY")
        _, errors = validate(deed)
        state_errors = [e for e in errors if e.code == "STATE_CODE_ERROR"]
        assert state_errors == []


# ── Full sample integration ──────────────────────────────────────────────────


class TestSampleInputFullErrors:
    """The default sample must produce exactly 3 errors."""

    def test_sample_produces_three_errors(self) -> None:
        _, errors = validate(make_enriched())
        assert len(errors) == 3

    def test_sample_has_date_order_error(self) -> None:
        _, errors = validate(make_enriched())
        codes = [e.code for e in errors]
        assert "DATE_ORDER_ERROR" in codes

    def test_sample_has_apn_format_error(self) -> None:
        _, errors = validate(make_enriched())
        codes = [e.code for e in errors]
        assert "APN_FORMAT_ERROR" in codes

    def test_sample_has_amount_mismatch_error(self) -> None:
        _, errors = validate(make_enriched())
        codes = [e.code for e in errors]
        assert "AMOUNT_MISMATCH_ERROR" in codes

    def test_sample_result_is_invalid(self) -> None:
        validated, errors = validate(make_enriched())
        assert validated is None
        assert len(errors) > 0
