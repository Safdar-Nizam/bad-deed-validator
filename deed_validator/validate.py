"""
Deterministic validation logic.  100 % Python — no LLM involved.

Every check is a small, composable function that either returns clean parsed
values or appends typed errors to a collector list.  The top-level
``validate()`` function orchestrates them all.

Checks implemented (in order):
 1. Required fields — no blanks
 2. Status — must be PRELIMINARY or FINAL
 3. State code — must be a valid US state abbreviation
 4. County enrichment — must have matched
 5. State-county alignment — county's state must match deed state
 6. Date parsing, order, future, and staleness
 7. APN format — numeric segments only
 8. Grantor / grantee — must be distinct parties
 9. Amount parsing, cross-check, and range

Returns ``(ValidatedDeed, [])`` on success, or ``(None, errors)`` on failure.

State-specific closing cost computation:
- **CA**: property tax only (``amount * tax_rate``)
- **FL**: property tax + documentary stamp tax + Miami-Dade surtax (if applicable)
- **NY**: property tax + transfer tax + mansion tax (if amount >= $1M)
"""

from __future__ import annotations

import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from deed_validator.errors import (
    AmountMismatchError,
    AmountRangeError,
    APNFormatError,
    DateOrderError,
    DateParseError,
    DeedValidationError,
    FutureDateError,
    GrantorGranteeSameError,
    InvalidStatusError,
    NotADeedError,
    SchemaMissingFieldError,
    StaleRecordingError,
    StateCodeError,
    StateCountyMismatchError,
    UnknownCountyError,
)
from deed_validator.models import EnrichedDeed, ValidatedDeed
from deed_validator.money_words import words_to_dollars

logger = logging.getLogger(__name__)

VALID_STATUSES = frozenset({"PRELIMINARY", "FINAL"})

# $500 M ceiling — anything above is almost certainly an OCR artefact or error.
MAX_DEED_AMOUNT: int = 500_000_000

# If recording happens more than a year after signing, flag as stale.
MAX_RECORDING_GAP_DAYS: int = 365

# Minimum number of deed-related keywords to accept an input as a deed.
MIN_DEED_KEYWORDS: int = 3

_REQUIRED_FIELDS: list[str] = [
    "doc_id", "county_raw", "state", "date_signed", "date_recorded",
    "grantor", "grantee", "amount_numeric_raw", "amount_words_raw",
    "apn", "status",
]

# All 50 US states + DC.
_US_STATE_CODES = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
})

# Keywords that indicate the text is likely a deed document.
_DEED_KEYWORDS = frozenset({
    "deed", "trust", "grantor", "grantee", "apn", "parcel",
    "recorded", "recording", "county", "signed", "amount",
    "property", "convey", "transfer", "mortgage", "lien",
    "notary", "witness", "consideration", "warranty",
    "quitclaim", "bargain", "sale", "doc", "document",
    "instrument", "folio", "assessor",
})


# ── Preflight ─────────────────────────────────────────────────────────────────


def preflight_deed_check(raw_text: str) -> tuple[bool, int, Optional[NotADeedError]]:
    """
    Quick deterministic check: does this text look like a deed?

    Returns ``(passed, keyword_count, error_or_none)``.
    """
    text_lower = raw_text.lower()
    keyword_count = sum(1 for kw in _DEED_KEYWORDS if kw in text_lower)

    if keyword_count < MIN_DEED_KEYWORDS:
        return False, keyword_count, NotADeedError(keyword_count, MIN_DEED_KEYWORDS)
    return True, keyword_count, None


# ── Individual checks ────────────────────────────────────────────────────────


def _check_required_fields(deed: EnrichedDeed) -> list[DeedValidationError]:
    """Verify that no required field is missing or blank."""
    errors: list[DeedValidationError] = []
    for name in _REQUIRED_FIELDS:
        value = getattr(deed, name, None)
        if not value or (isinstance(value, str) and not value.strip()):
            errors.append(SchemaMissingFieldError(name))
    return errors


def _validate_state(deed: EnrichedDeed) -> list[DeedValidationError]:
    """State abbreviation must be a real US state."""
    if deed.state.strip().upper() not in _US_STATE_CODES:
        return [StateCodeError(deed.state)]
    return []


def _validate_state_county_match(deed: EnrichedDeed) -> list[DeedValidationError]:
    """
    County's state (from counties.json) must match the deed's state.

    Catches cases like a deed claiming "FL" but the matched county
    belongs to "NY".  Skipped if county wasn't matched.
    """
    county_state = deed.county_meta.get("state")
    if not county_state or deed.county_canonical is None:
        return []  # Can't check — county unmatched
    deed_state = deed.state.strip().upper()
    if deed_state != county_state.upper():
        return [StateCountyMismatchError(deed.state, deed.county_canonical, county_state)]
    return []


def _parse_date(
    raw: str, field_name: str,
) -> tuple[Optional[date], Optional[DeedValidationError]]:
    """Parse a YYYY-MM-DD string to a ``date`` or return a ``DateParseError``."""
    try:
        return date.fromisoformat(raw.strip()), None
    except ValueError as exc:
        return None, DateParseError(field_name, raw, str(exc))


def _validate_dates(
    deed: EnrichedDeed,
) -> tuple[Optional[date], Optional[date], list[DeedValidationError]]:
    """
    Parse both dates and run all date-related checks:
    - parseable as YYYY-MM-DD
    - recorded >= signed (DateOrderError)
    - neither date in the future (FutureDateError)
    - gap between signing and recording <= 365 days (StaleRecordingError)
    """
    errors: list[DeedValidationError] = []

    signed, err_s = _parse_date(deed.date_signed, "date_signed")
    recorded, err_r = _parse_date(deed.date_recorded, "date_recorded")

    if err_s:
        errors.append(err_s)
    if err_r:
        errors.append(err_r)

    # Order check: recorded must be on or after signed.
    if signed and recorded and recorded < signed:
        errors.append(DateOrderError(str(signed), str(recorded)))

    # Future date check: neither date should be in the future.
    today = date.today()
    if signed and signed > today:
        errors.append(FutureDateError("date_signed", str(signed)))
    if recorded and recorded > today:
        errors.append(FutureDateError("date_recorded", str(recorded)))

    # Stale recording check: only when dates are in valid order.
    if signed and recorded and recorded >= signed:
        gap = (recorded - signed).days
        if gap > MAX_RECORDING_GAP_DAYS:
            errors.append(StaleRecordingError(str(signed), str(recorded), gap))

    return signed, recorded, errors


def _validate_apn(deed: EnrichedDeed) -> list[DeedValidationError]:
    """
    APNs are dash-separated numeric segments (e.g. 123-456-789).
    Any segment containing letters is flagged.
    """
    apn = deed.apn.strip()
    if not apn:
        return []  # already caught by required-fields check

    segments = apn.split("-")
    bad = [seg for seg in segments if seg and not seg.isdigit()]
    if bad:
        return [APNFormatError(apn, bad)]
    return []


def _validate_parties(deed: EnrichedDeed) -> list[DeedValidationError]:
    """Grantor and grantee must not be the same party (self-dealing)."""
    g1 = deed.grantor.strip().lower()
    g2 = deed.grantee.strip().lower()
    if g1 and g2 and g1 == g2:
        return [GrantorGranteeSameError(deed.grantor, deed.grantee)]
    return []


def _parse_numeric_amount(raw: str) -> tuple[Optional[int], Optional[DeedValidationError]]:
    """Parse a raw numeric string like ``"$1,250,000.00"`` to integer dollars."""
    cleaned = re.sub(r"[^\d.]", "", raw)
    try:
        value = Decimal(cleaned).quantize(Decimal("1"))
        return int(value), None
    except InvalidOperation:
        return None, SchemaMissingFieldError("amount_numeric_raw")


def _parse_words_amount(raw: str) -> tuple[Optional[int], Optional[DeedValidationError]]:
    """Parse English words to integer dollars."""
    try:
        return words_to_dollars(raw), None
    except ValueError:
        return None, SchemaMissingFieldError("amount_words_raw")


def _validate_amounts(
    deed: EnrichedDeed,
) -> tuple[Optional[int], Optional[int], list[DeedValidationError]]:
    """Parse both amount representations, compare, and range-check."""
    errors: list[DeedValidationError] = []

    numeric, err_n = _parse_numeric_amount(deed.amount_numeric_raw)
    words, err_w = _parse_words_amount(deed.amount_words_raw)

    if err_n:
        errors.append(err_n)
    if err_w:
        errors.append(err_w)

    # Cross-check: numeric vs words must agree.
    if numeric is not None and words is not None and numeric != words:
        errors.append(AmountMismatchError(numeric, words))

    # Range check on the numeric amount.
    if numeric is not None:
        if numeric <= 0:
            errors.append(AmountRangeError(numeric, "Amount must be positive."))
        elif numeric > MAX_DEED_AMOUNT:
            errors.append(AmountRangeError(
                numeric,
                f"Amount exceeds the ${MAX_DEED_AMOUNT:,} ceiling — likely an OCR artefact.",
            ))

    return numeric, words, errors


# ── State-specific closing cost ──────────────────────────────────────────────


def _compute_closing_cost(
    numeric: int,
    deed: EnrichedDeed,
) -> Decimal:
    """
    Compute closing cost estimate with state-specific tax components.

    - **CA**: amount * county tax_rate
    - **FL**: base tax + documentary stamp tax ($0.70/$100) + Miami-Dade
              surtax ($0.45/$100) if applicable
    - **NY**: base tax + transfer tax ($2/$500) + mansion tax (1% if >= $1M)
    """
    amount = Decimal(numeric)
    meta = deed.county_meta
    state = deed.state.strip().upper()

    # Base: property tax estimate
    cost = (amount * Decimal(str(deed.tax_rate or 0))).quantize(Decimal("0.01"))

    # FL: Documentary stamp tax + surtax
    if state == "FL":
        dsr = Decimal(str(meta.get("doc_stamp_rate", 0)))
        cost += (amount * dsr).quantize(Decimal("0.01"))
        if meta.get("has_surtax"):
            sr = Decimal(str(meta.get("surtax_rate", 0)))
            cost += (amount * sr).quantize(Decimal("0.01"))

    # NY: Transfer tax + mansion tax
    if state == "NY":
        ttr = Decimal(str(meta.get("transfer_tax_rate", 0)))
        cost += (amount * ttr).quantize(Decimal("0.01"))
        mt_threshold = meta.get("mansion_tax_threshold", 0)
        if mt_threshold and numeric >= mt_threshold:
            mt_rate = Decimal(str(meta.get("mansion_tax_rate", 0)))
            cost += (amount * mt_rate).quantize(Decimal("0.01"))

    return cost


# ── Orchestrator ─────────────────────────────────────────────────────────────


def validate(
    deed: EnrichedDeed,
) -> tuple[Optional[ValidatedDeed], list[DeedValidationError]]:
    """
    Run every deterministic check against an enriched deed.

    Returns ``(ValidatedDeed, [])`` if all checks pass, otherwise
    ``(None, [errors])``.
    """
    all_errors: list[DeedValidationError] = []

    # 1. Required fields
    all_errors.extend(_check_required_fields(deed))

    # 2. Status
    if deed.status.upper() not in VALID_STATUSES:
        all_errors.append(InvalidStatusError(deed.status))

    # 3. State code
    all_errors.extend(_validate_state(deed))

    # 4. County enrichment
    if deed.county_canonical is None or deed.tax_rate is None:
        all_errors.append(
            UnknownCountyError(deed.county_raw, deed.county_match_confidence)
        )

    # 5. State-county alignment
    all_errors.extend(_validate_state_county_match(deed))

    # 6. Dates (parse, order, future, staleness)
    signed, recorded, date_errors = _validate_dates(deed)
    all_errors.extend(date_errors)

    # 7. APN format
    all_errors.extend(_validate_apn(deed))

    # 8. Grantor / grantee distinct
    all_errors.extend(_validate_parties(deed))

    # 9. Amounts (parse, cross-check, range)
    numeric, words, amount_errors = _validate_amounts(deed)
    all_errors.extend(amount_errors)

    # ── Decision ─────────────────────────────────────────────────────────
    if all_errors:
        logger.info("Validation FAILED — %d error(s)", len(all_errors))
        return None, all_errors

    # Closing cost is only computed when the deed is fully valid.
    closing_cost: Optional[Decimal] = None
    if deed.tax_rate is not None and numeric is not None:
        closing_cost = _compute_closing_cost(numeric, deed)

    validated = ValidatedDeed(
        **deed.model_dump(),
        date_signed_parsed=signed,      # type: ignore[arg-type]
        date_recorded_parsed=recorded,  # type: ignore[arg-type]
        amount_numeric_value=numeric,   # type: ignore[arg-type]
        amount_words_value=words,       # type: ignore[arg-type]
        closing_cost_estimate=closing_cost,
    )

    logger.info("Validation PASSED — doc_id=%s", deed.doc_id)
    return validated, []
