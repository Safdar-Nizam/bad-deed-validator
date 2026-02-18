"""
Tests for the deterministic English-words-to-dollars converter.

Covers the specific case from the OCR text plus edge cases.
"""

from __future__ import annotations

import pytest

from deed_validator.money_words import words_to_dollars


class TestWordsToDollars:
    """Core conversion tests."""

    def test_one_million_two_hundred_thousand(self) -> None:
        """The exact phrase from the sample OCR text."""
        assert words_to_dollars("One Million Two Hundred Thousand Dollars") == 1_200_000

    def test_one_million_two_hundred_fifty_thousand(self) -> None:
        assert words_to_dollars("One Million Two Hundred Fifty Thousand Dollars") == 1_250_000

    def test_two_hundred_fifty_thousand(self) -> None:
        assert words_to_dollars("Two Hundred Fifty Thousand Dollars") == 250_000

    def test_three_hundred(self) -> None:
        assert words_to_dollars("Three Hundred Dollars") == 300

    def test_five_hundred_thousand(self) -> None:
        assert words_to_dollars("Five Hundred Thousand Dollars") == 500_000

    def test_nineteen(self) -> None:
        assert words_to_dollars("Nineteen Dollars") == 19

    def test_one(self) -> None:
        assert words_to_dollars("One Dollar") == 1

    def test_zero(self) -> None:
        assert words_to_dollars("Zero Dollars") == 0

    def test_with_and_conjunction(self) -> None:
        """'and' is a noise word and must be ignored."""
        assert words_to_dollars("One Hundred and Twenty Three Dollars") == 123

    def test_hyphenated_number(self) -> None:
        """Hyphen-separated numbers like 'twenty-five' are supported."""
        assert words_to_dollars("Twenty-Five Thousand Dollars") == 25_000


class TestInvalidInput:
    """Bad tokens must raise ValueError."""

    def test_unknown_token_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="bazillion"):
            words_to_dollars("One bazillion dollars")

    def test_empty_string_returns_zero(self) -> None:
        assert words_to_dollars("") == 0

    def test_only_dollars_returns_zero(self) -> None:
        assert words_to_dollars("Dollars") == 0
