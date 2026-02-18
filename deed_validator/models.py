"""
Pydantic v2 data models for each pipeline stage.

* **ExtractedDeed** – raw LLM output.  *Untrusted.*
* **EnrichedDeed**  – after deterministic county enrichment.
* **ValidatedDeed** – only created when every check passes.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class LLMMeta(BaseModel):
    """Metadata about the LLM extraction call (model name + timestamp)."""

    model: str
    extraction_timestamp: str


class ExtractedDeed(BaseModel):
    """
    Raw fields extracted by the LLM.  **Untrusted.**

    Every string value is preserved exactly as the LLM returned it.
    No corrections, no reconciliation.
    """

    model_config = ConfigDict(frozen=True)

    doc_id: str
    county_raw: str
    state: str
    date_signed: str
    date_recorded: str
    grantor: str
    grantee: str
    amount_numeric_raw: str
    amount_words_raw: str
    apn: str
    status: str
    source_text_hash: str
    llm_meta: LLMMeta


class EnrichedDeed(ExtractedDeed):
    """
    After deterministic county enrichment.

    Adds canonical county name, match confidence, tax rate, and
    full county metadata (state-specific fields like doc_stamp_rate,
    mansion_tax_threshold, etc.).
    """

    model_config = ConfigDict(frozen=True)

    county_canonical: Optional[str] = None
    county_match_confidence: float = 0.0
    tax_rate: Optional[float] = None
    county_meta: dict[str, Any] = Field(default_factory=dict)


class ValidatedDeed(EnrichedDeed):
    """
    Created **only** when every validation check passes.

    Includes parsed dates, normalized amounts, and the computed
    closing cost estimate.  This is the only model that downstream
    consumers (blockchain recording, etc.) should trust.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    date_signed_parsed: date
    date_recorded_parsed: date
    amount_numeric_value: int
    amount_words_value: int
    closing_cost_estimate: Optional[Decimal] = None
