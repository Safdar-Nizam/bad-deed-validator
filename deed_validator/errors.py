"""
Typed, structured validation errors.

Every error carries a machine-readable ``code``, a human-readable ``message``,
the ``field`` that triggered it, and an optional ``details`` dict for
programmatic consumers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DeedValidationError(Exception):
    """Base class for all deed validation errors."""

    code: str
    message: str
    field_name: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "field": self.field_name,
            "details": self.details,
        }

    def __str__(self) -> str:
        return f"[{self.code}] {self.field_name}: {self.message}"


# ── Preflight ────────────────────────────────────────────────────────────────


class NotADeedError(DeedValidationError):
    """Input text does not appear to be a deed document."""

    def __init__(self, keyword_count: int, min_required: int) -> None:
        super().__init__(
            code="NOT_A_DEED_ERROR",
            message=(
                f"This does not appear to be a deed document. "
                f"Found only {keyword_count} deed-related keyword(s) "
                f"(minimum {min_required} required). "
                f"Please provide actual property deed OCR text."
            ),
            field_name="document",
            details={
                "keyword_count": keyword_count,
                "min_required": min_required,
            },
        )


# ── Date errors ──────────────────────────────────────────────────────────────


class DateOrderError(DeedValidationError):
    """Recorded date is earlier than signed date."""

    def __init__(self, date_signed: str, date_recorded: str) -> None:
        super().__init__(
            code="DATE_ORDER_ERROR",
            message=(
                f"date_recorded ({date_recorded}) is earlier than "
                f"date_signed ({date_signed}). "
                f"A deed cannot be recorded before it is signed."
            ),
            field_name="date_recorded",
            details={"date_signed": date_signed, "date_recorded": date_recorded},
        )


class DateParseError(DeedValidationError):
    """A date string could not be parsed as YYYY-MM-DD."""

    def __init__(self, field_name: str, raw_value: str, reason: str) -> None:
        super().__init__(
            code="DATE_PARSE_ERROR",
            message=f"Cannot parse date '{raw_value}': {reason}",
            field_name=field_name,
            details={"raw_value": raw_value, "reason": reason},
        )


class FutureDateError(DeedValidationError):
    """A date is in the future."""

    def __init__(self, field_name: str, date_value: str) -> None:
        super().__init__(
            code="FUTURE_DATE_ERROR",
            message=(
                f"{field_name} ({date_value}) is in the future. "
                f"Deeds cannot be signed or recorded on a future date."
            ),
            field_name=field_name,
            details={"date_value": date_value},
        )


class StaleRecordingError(DeedValidationError):
    """Gap between signing and recording exceeds 365 days."""

    def __init__(self, date_signed: str, date_recorded: str, gap_days: int) -> None:
        super().__init__(
            code="STALE_RECORDING_ERROR",
            message=(
                f"Recording gap of {gap_days:,} days between signing "
                f"({date_signed}) and recording ({date_recorded}) exceeds "
                f"the 365-day threshold. This deed may be stale."
            ),
            field_name="date_recorded",
            details={
                "date_signed": date_signed,
                "date_recorded": date_recorded,
                "gap_days": gap_days,
            },
        )


# ── Amount errors ────────────────────────────────────────────────────────────


class AmountMismatchError(DeedValidationError):
    """Numeric dollar amount does not match the written-out words amount."""

    def __init__(self, numeric: int, words: int) -> None:
        super().__init__(
            code="AMOUNT_MISMATCH_ERROR",
            message=(
                f"Numeric amount ({numeric:,}) does not match "
                f"words amount ({words:,}). "
                f"Difference: {abs(numeric - words):,}."
            ),
            field_name="amount",
            details={
                "amount_numeric_value": numeric,
                "amount_words_value": words,
                "difference": abs(numeric - words),
            },
        )


class AmountRangeError(DeedValidationError):
    """Dollar amount is zero, negative, or exceeds a reasonable ceiling."""

    def __init__(self, amount: int, reason: str) -> None:
        super().__init__(
            code="AMOUNT_RANGE_ERROR",
            message=f"Amount ${amount:,} is out of acceptable range: {reason}",
            field_name="amount_numeric_raw",
            details={"amount": amount, "reason": reason},
        )


# ── County / state errors ────────────────────────────────────────────────────


class UnknownCountyError(DeedValidationError):
    """No county in the reference data matched above the confidence threshold."""

    def __init__(self, county_raw: str, confidence: float) -> None:
        super().__init__(
            code="UNKNOWN_COUNTY_ERROR",
            message=(
                f"County '{county_raw}' could not be matched to a known county "
                f"(best confidence: {confidence:.2f})."
            ),
            field_name="county_raw",
            details={"county_raw": county_raw, "best_confidence": confidence},
        )


class StateCountyMismatchError(DeedValidationError):
    """The matched county belongs to a different state than what the deed says."""

    def __init__(self, deed_state: str, county_name: str, county_state: str) -> None:
        super().__init__(
            code="STATE_COUNTY_MISMATCH_ERROR",
            message=(
                f"Deed says state '{deed_state}' but county '{county_name}' "
                f"belongs to '{county_state}'. State and county do not align."
            ),
            field_name="state",
            details={
                "deed_state": deed_state,
                "county_name": county_name,
                "county_state": county_state,
            },
        )


class StateCodeError(DeedValidationError):
    """State code is not a valid US state abbreviation."""

    def __init__(self, state: str) -> None:
        super().__init__(
            code="STATE_CODE_ERROR",
            message=f"State '{state}' is not a valid US state abbreviation.",
            field_name="state",
            details={"state": state},
        )


# ── APN errors ───────────────────────────────────────────────────────────────


class APNFormatError(DeedValidationError):
    """Assessor's Parcel Number does not match expected numeric format."""

    def __init__(self, apn: str, invalid_segments: list[str]) -> None:
        super().__init__(
            code="APN_FORMAT_ERROR",
            message=(
                f"APN '{apn}' contains non-numeric segment(s): "
                f"{invalid_segments}. APNs must be fully numeric "
                f"(digits and dashes only, e.g. '123-456-789')."
            ),
            field_name="apn",
            details={"apn": apn, "invalid_segments": invalid_segments},
        )


# ── Party errors ─────────────────────────────────────────────────────────────


class GrantorGranteeSameError(DeedValidationError):
    """Grantor and grantee appear to be the same party."""

    def __init__(self, grantor: str, grantee: str) -> None:
        super().__init__(
            code="GRANTOR_GRANTEE_SAME_ERROR",
            message=(
                f"Grantor and grantee appear to be the same party: "
                f"'{grantor}'. A deed requires distinct parties."
            ),
            field_name="grantor",
            details={"grantor": grantor, "grantee": grantee},
        )


# ── State-specific errors ────────────────────────────────────────────────────


class MansionTaxApplicableError(DeedValidationError):
    """NY: Property exceeds $1M mansion tax threshold — tax flag required."""

    def __init__(self, amount: int, threshold: int, mansion_tax_rate: float) -> None:
        tax_due = int(amount * mansion_tax_rate)
        super().__init__(
            code="NY_MANSION_TAX_APPLICABLE",
            message=(
                f"New York mansion tax applies: property amount "
                f"${amount:,} exceeds the ${threshold:,} threshold. "
                f"Estimated mansion tax: ${tax_due:,} "
                f"({mansion_tax_rate:.0%}). This must be disclosed."
            ),
            field_name="amount",
            details={
                "amount": amount,
                "threshold": threshold,
                "mansion_tax_rate": mansion_tax_rate,
                "estimated_mansion_tax": tax_due,
            },
        )


class FLDocStampMissingError(DeedValidationError):
    """FL: Documentary stamp tax must be paid at recording."""

    def __init__(self, amount: int, doc_stamp_rate: float, has_surtax: bool,
                 surtax_rate: float = 0.0) -> None:
        stamp = round(amount * doc_stamp_rate, 2)
        surtax = round(amount * surtax_rate, 2) if has_surtax else 0
        total = stamp + surtax
        super().__init__(
            code="FL_DOC_STAMP_REQUIRED",
            message=(
                f"Florida documentary stamp tax required at recording. "
                f"Estimated doc stamps: ${stamp:,.2f}"
                + (f" + Miami-Dade surtax: ${surtax:,.2f}" if has_surtax else "")
                + f". Total: ${total:,.2f}. "
                f"Ensure stamps are paid before recording."
            ),
            field_name="amount",
            details={
                "amount": amount,
                "doc_stamp_rate": doc_stamp_rate,
                "doc_stamp_amount": stamp,
                "has_surtax": has_surtax,
                "surtax_amount": surtax,
                "total_stamps": total,
            },
        )


# ── Schema errors ────────────────────────────────────────────────────────────


class SchemaMissingFieldError(DeedValidationError):
    """A required field is missing or empty in the extracted data."""

    def __init__(self, field_name: str) -> None:
        super().__init__(
            code="SCHEMA_MISSING_FIELD_ERROR",
            message=f"Required field '{field_name}' is missing or empty.",
            field_name=field_name,
        )


class InvalidStatusError(DeedValidationError):
    """Status value is not one of the recognised values."""

    def __init__(self, status: str) -> None:
        super().__init__(
            code="INVALID_STATUS_ERROR",
            message=f"Status '{status}' is not valid. Expected PRELIMINARY or FINAL.",
            field_name="status",
            details={"status": status},
        )


# ── LLM output errors ───────────────────────────────────────────────────────


class LLMOutputFormatError(Exception):
    """The LLM returned something that is not valid structured JSON."""

    def __init__(self, reason: str, raw: str = "") -> None:
        self.reason = reason
        self.raw = raw
        super().__init__(f"LLM output format error: {reason}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the same shape as DeedValidationError for API consumers."""
        return {
            "code": "LLM_OUTPUT_FORMAT_ERROR",
            "message": f"LLM output format error: {self.reason}",
            "field": "llm_output",
            "details": {
                "reason": self.reason,
                "raw_preview": self.raw[:500] if self.raw else "",
            },
        }
