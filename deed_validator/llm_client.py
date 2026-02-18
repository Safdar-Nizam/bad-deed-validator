"""
OpenAI LLM client for deed field extraction.

Trust boundary
--------------
The LLM is allowed to *extract* fields from OCR text.  It must **not** fix,
reconcile, or correct any inconsistencies.  Every value it returns is treated
as untrusted input by downstream validation code.

The ``openai`` Python package is used.  The API key is read from the
``OPENAI_API_KEY`` environment variable (never hard-coded).
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone

from openai import OpenAI

from deed_validator.config import OPENAI_API_KEY, OPENAI_MODEL
from deed_validator.errors import LLMOutputFormatError
from deed_validator.models import ExtractedDeed, LLMMeta

logger = logging.getLogger(__name__)

# ── Prompts ──────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a real estate deed field extraction assistant.  You process \
OCR-scanned property deed documents from across the United States, \
including California (CA), Florida (FL), and New York (NY).

YOUR ONLY JOB: Extract fields from the raw OCR text and return them as \
a strict JSON object.

CRITICAL RULES — read every one:
1. EXTRACT EXACTLY WHAT IS WRITTEN.  Never fix typos.  Never correct dates.  \
Never reconcile contradictions.  Never guess.
2. If the numeric dollar amount (e.g. "$1,250,000") and the written-out words \
amount (e.g. "One Million Two Hundred Thousand") do NOT match, return BOTH \
exactly as they appear.  Do NOT pick one over the other.
3. Preserve abbreviations exactly as written (e.g. "S. Clara" must stay \
"S. Clara" — do NOT expand to "Santa Clara").
4. Preserve all formatting, punctuation, and casing from the source text.
5. If a field cannot be found in the text, return an empty string "" for \
that field.
6. Return ONLY the JSON object.  No markdown code fences.  No backticks.  \
No explanation.  No commentary.
7. If the input does not appear to be a deed document, still attempt \
extraction.  Return empty strings for any fields not found.

You are a mechanical extraction tool, NOT a validator.  You must NEVER make \
judgment calls about whether values are correct or consistent.  Downstream \
deterministic Python code will handle all validation.\
"""

_USER_PROMPT = """\
Extract the following fields from the OCR deed text below.
Return a single flat JSON object with exactly these keys (no nesting):

  doc_id              document identifier (e.g., "DEED-TRUST-0042")
  county_raw          county name exactly as written (e.g., "S. Clara")
  state               US state abbreviation (e.g., "CA", "FL", "NY")
  date_signed         signing date exactly as it appears
  date_recorded       recording date exactly as it appears
  grantor             transferor / seller name(s)
  grantee             transferee / buyer name(s)
  amount_numeric_raw  dollar figure with symbols (e.g., "$1,250,000.00")
  amount_words_raw    written-out amount (e.g., "One Million Two Hundred Thousand Dollars")
  apn                 Assessor's Parcel Number or folio number
  status              document status (e.g., "PRELIMINARY", "FINAL")

Rules:
- Preserve all values EXACTLY as they appear.  Do NOT correct errors.
- If multiple amounts appear, extract the first numeric and first words
  representation.
- If a field is not present in the text, use an empty string "".

OCR TEXT:
{ocr_text}\
"""

# Fields the LLM JSON must contain.
_REQUIRED_KEYS = frozenset({
    "doc_id", "county_raw", "state", "date_signed", "date_recorded",
    "grantor", "grantee", "amount_numeric_raw", "amount_words_raw",
    "apn", "status",
})


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def extract_deed_fields(text: str) -> ExtractedDeed:
    """
    Call the OpenAI chat-completions API and return an ``ExtractedDeed``.

    Raises
    ------
    EnvironmentError
        If ``OPENAI_API_KEY`` is not set.
    LLMOutputFormatError
        If the model response is not valid JSON or is missing required keys.
    """
    if not OPENAI_API_KEY:
        raise EnvironmentError(
            "OPENAI_API_KEY is not set. "
            "Set it in your .env file or run in fixture mode (no key needed)."
        )

    client = OpenAI(api_key=OPENAI_API_KEY)

    logger.info("Calling OpenAI model=%s", OPENAI_MODEL)

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _USER_PROMPT.format(ocr_text=text)},
            ],
        )
    except Exception as exc:
        raise LLMOutputFormatError(f"OpenAI API call failed: {exc}") from exc

    raw_output = response.choices[0].message.content or ""
    logger.debug("Raw LLM output:\n%s", raw_output)

    # Strip markdown code fences the model may add despite instructions.
    cleaned = raw_output.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(cleaned.split("\n")[1:])
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]
    cleaned = cleaned.strip()

    # Parse JSON.
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMOutputFormatError(f"JSON decode failed: {exc}", raw=raw_output) from exc

    if not isinstance(data, dict):
        raise LLMOutputFormatError("Expected a JSON object from LLM", raw=raw_output)

    missing = _REQUIRED_KEYS - data.keys()
    if missing:
        raise LLMOutputFormatError(
            f"LLM response missing keys: {sorted(missing)}", raw=raw_output,
        )

    return ExtractedDeed(
        doc_id=data["doc_id"],
        county_raw=data["county_raw"],
        state=data["state"],
        date_signed=data["date_signed"],
        date_recorded=data["date_recorded"],
        grantor=data["grantor"],
        grantee=data["grantee"],
        amount_numeric_raw=data["amount_numeric_raw"],
        amount_words_raw=data["amount_words_raw"],
        apn=data["apn"],
        status=data["status"],
        source_text_hash=_sha256(text),
        llm_meta=LLMMeta(
            model=OPENAI_MODEL,
            extraction_timestamp=datetime.now(timezone.utc).isoformat(),
        ),
    )
