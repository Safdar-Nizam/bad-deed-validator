"""
Immutable constants used across the package.

The DEFAULT_OCR_TEXT is the exact messy OCR string that ships with the project.
It intentionally contains contradictions that the validator must catch.
"""

DEFAULT_OCR_TEXT = """\
*** RECORDING REQ ***
Doc: DEED-TRUST-0042
County: S. Clara | State: CA
Date Signed: 2024-01-15
Date Recorded: 2024-01-10
Grantor: T.E.S.L.A. Holdings LLC
Grantee: John & Sarah Connor
Amount: $1,250,000.00 (One Million Two Hundred Thousand Dollars)
APN: 992-001-XA
Status: PRELIMINARY
*** END ***"""

# Minimum rapidfuzz similarity score (0–1) to accept a county match.
COUNTY_MATCH_THRESHOLD: float = 0.80
