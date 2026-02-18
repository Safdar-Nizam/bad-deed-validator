"""
End-to-end pipeline: **Preflight → Extract → Enrich → Validate**.

The pipeline returns a ``(ValidatedDeed | None, list[errors])`` tuple.
If there are any errors the deed is rejected and ``ValidatedDeed`` is ``None``.

The preflight step is a fast deterministic check that rejects input that
doesn't look like a deed document (e.g. "hi", random gibberish) **before**
any LLM call is made.  This saves cost and provides instant feedback.
"""

from __future__ import annotations

import logging
from typing import Optional

from deed_validator.enrich import build_enriched_deed
from deed_validator.errors import DeedValidationError
from deed_validator.extractor import extract
from deed_validator.models import ValidatedDeed
from deed_validator.validate import preflight_deed_check, validate

logger = logging.getLogger(__name__)


def run(
    ocr_text: str,
) -> tuple[Optional[ValidatedDeed], list[DeedValidationError]]:
    """
    Run the full validation pipeline on raw OCR text.

    Steps
    -----
    0. **Preflight** – reject non-deed input before calling the LLM.
    1. **Extract** – LLM (or fixture) produces ``ExtractedDeed`` (untrusted).
    2. **Enrich**  – deterministic county matching produces ``EnrichedDeed``.
    3. **Validate** – deterministic checks produce ``ValidatedDeed`` or errors.
    """
    logger.info("=== Pipeline start ===")

    # Step 0: Preflight — is this even a deed?
    passed, kw_count, preflight_error = preflight_deed_check(ocr_text)
    logger.info("Preflight: %d deed keywords found, passed=%s", kw_count, passed)

    if preflight_error:
        logger.info("=== Pipeline result: REJECTED (not a deed) ===")
        return None, [preflight_error]

    # Step 1: Extraction (untrusted)
    extracted = extract(ocr_text)
    logger.info(
        "Extracted doc_id=%s  source_hash=%s...",
        extracted.doc_id,
        extracted.source_text_hash[:12],
    )

    # Step 2: Enrichment (deterministic)
    enriched = build_enriched_deed(extracted)
    logger.info(
        "County enrichment: '%s' -> '%s' (confidence=%.2f, tax_rate=%s, county_state=%s)",
        enriched.county_raw,
        enriched.county_canonical,
        enriched.county_match_confidence,
        enriched.tax_rate,
        enriched.county_meta.get("state", "?"),
    )

    # Step 3: Validation (deterministic, strict)
    validated, errors = validate(enriched)

    if errors:
        logger.info("=== Pipeline result: INVALID (%d errors) ===", len(errors))
    else:
        logger.info("=== Pipeline result: VALID ===")

    return validated, errors
