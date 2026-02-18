"""
Deterministic English-words-to-integer-dollars converter.

Handles amounts like:
  "One Million Two Hundred Thousand Dollars"  → 1_200_000
  "One Million Two Hundred Fifty Thousand Dollars" → 1_250_000
  "Three Hundred Dollars" → 300

Supports tokens: zero–nineteen, tens (twenty–ninety), hundred, thousand,
million, billion.  The trailing word "dollars" / "dollar" and the
conjunction "and" are stripped before processing.

Raises ``ValueError`` on unrecognised tokens.
"""

from __future__ import annotations

_ONES: dict[str, int] = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19,
}

_TENS: dict[str, int] = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}

_MULTIPLIERS: dict[str, int] = {
    "hundred": 100,
    "thousand": 1_000,
    "million": 1_000_000,
    "billion": 1_000_000_000,
}


def words_to_dollars(text: str) -> int:
    """
    Convert an English dollar phrase to an integer dollar amount.

    Parameters
    ----------
    text:
        A string like ``"One Million Two Hundred Thousand Dollars"``.

    Returns
    -------
    int
        The dollar amount as a whole number.

    Raises
    ------
    ValueError
        If any token in the phrase is not recognised.
    """
    tokens = text.lower().replace("-", " ").split()
    # Strip noise words
    tokens = [t for t in tokens if t not in ("and", "dollars", "dollar")]

    if not tokens:
        return 0

    total = 0
    current = 0

    for token in tokens:
        if token in _ONES:
            current += _ONES[token]
        elif token in _TENS:
            current += _TENS[token]
        elif token == "hundred":
            # "two hundred" → current was 2, now becomes 200
            current *= _MULTIPLIERS["hundred"]
        elif token in ("thousand", "million", "billion"):
            current *= _MULTIPLIERS[token]
            total += current
            current = 0
        else:
            raise ValueError(f"Unrecognised token in amount words: '{token}'")

    total += current
    return total
