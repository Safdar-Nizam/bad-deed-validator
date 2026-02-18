"""
Tests for the preflight deed-detection check.

The preflight rejects input that doesn't look like a deed document
**before** any LLM call is made.  This is the first gate in the pipeline.

Covers:
- Random gibberish / greetings are rejected
- Real deed text passes
- Edge cases (empty string, partial keywords)
"""

from __future__ import annotations

import pytest

from deed_validator.constants import DEFAULT_OCR_TEXT
from deed_validator.errors import NotADeedError
from deed_validator.validate import preflight_deed_check


class TestNonDeedRejection:
    """Random or non-deed text must be rejected at preflight."""

    def test_hi_is_rejected(self) -> None:
        passed, count, error = preflight_deed_check("hi")
        assert not passed
        assert count < 3
        assert isinstance(error, NotADeedError)
        assert error.code == "NOT_A_DEED_ERROR"

    def test_hello_how_are_you_rejected(self) -> None:
        passed, _, error = preflight_deed_check("hello how are you doing today?")
        assert not passed
        assert error is not None

    def test_random_sentence_rejected(self) -> None:
        passed, _, error = preflight_deed_check(
            "The quick brown fox jumps over the lazy dog."
        )
        assert not passed
        assert error is not None

    def test_empty_string_rejected(self) -> None:
        passed, count, error = preflight_deed_check("")
        assert not passed
        assert count == 0
        assert error is not None

    def test_numbers_only_rejected(self) -> None:
        passed, _, error = preflight_deed_check("12345 67890 00000")
        assert not passed
        assert error is not None

    def test_question_about_real_estate_rejected(self) -> None:
        """Even a question mentioning 'property' won't have 3+ deed keywords."""
        passed, _, error = preflight_deed_check(
            "What is the current property tax rate in Florida?"
        )
        assert not passed
        assert error is not None

    def test_code_snippet_rejected(self) -> None:
        passed, _, error = preflight_deed_check(
            "def hello_world():\n    print('Hello, world!')"
        )
        assert not passed
        assert error is not None


class TestDeedTextAccepted:
    """Actual deed text must pass the preflight."""

    def test_default_ocr_text_passes(self) -> None:
        passed, count, error = preflight_deed_check(DEFAULT_OCR_TEXT)
        assert passed
        assert count >= 3
        assert error is None

    def test_minimal_deed_passes(self) -> None:
        """A minimal document with 3+ deed keywords should pass."""
        text = "Deed of Trust\nGrantor: John Doe\nRecorded: 2024-01-01"
        passed, count, error = preflight_deed_check(text)
        assert passed
        assert count >= 3
        assert error is None

    def test_florida_deed_passes(self) -> None:
        text = (
            "WARRANTY DEED\nCounty: Miami-Dade | State: FL\n"
            "Grantor: Sun LLC\nGrantee: Jane Smith\n"
            "Amount: $500,000\nRecorded: 2024-01-15"
        )
        passed, _, error = preflight_deed_check(text)
        assert passed
        assert error is None

    def test_new_york_deed_passes(self) -> None:
        text = (
            "BARGAIN AND SALE DEED\nCounty: New York | State: NY\n"
            "Grantor: NYC Holdings\nGrantee: Robert Johnson\n"
            "Amount: $2,000,000\nRecorded: 2024-06-01"
        )
        passed, _, error = preflight_deed_check(text)
        assert passed
        assert error is None


class TestPreflightErrorDetails:
    """The NotADeedError must carry useful details."""

    def test_error_has_keyword_count(self) -> None:
        _, _, error = preflight_deed_check("hi")
        assert error is not None
        assert error.details["keyword_count"] == 0

    def test_error_has_min_required(self) -> None:
        _, _, error = preflight_deed_check("hi")
        assert error is not None
        assert error.details["min_required"] == 3

    def test_error_message_is_helpful(self) -> None:
        _, _, error = preflight_deed_check("hi")
        assert error is not None
        assert "does not appear to be a deed" in error.message.lower()
