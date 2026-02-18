"""
FastAPI web server for the deed validator.

Serves a beautiful single-page frontend and exposes a POST /api/validate
endpoint that runs the full pipeline and returns structured JSON **with
detailed per-check explanations**.

Usage:
    python -m deed_validator.server
    # Then open http://localhost:8090
"""

from __future__ import annotations

import logging
import re
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from deed_validator.constants import DEFAULT_OCR_TEXT
from deed_validator.enrich import build_enriched_deed
from deed_validator.errors import DeedValidationError
from deed_validator.extractor import extract
from deed_validator.models import EnrichedDeed
from deed_validator.validate import preflight_deed_check, validate

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Bad Deed Validator", version="2.0.0")

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"


# ── Request / Response models ────────────────────────────────────────────────


class ValidateRequest(BaseModel):
    ocr_text: str | None = None  # None → use default


class StepResult(BaseModel):
    step: str
    status: str
    duration_ms: float
    data: dict[str, Any]


class CheckResultModel(BaseModel):
    id: str
    label: str
    status: str          # "pass" | "fail" | "blocked" | "na"
    explanation: str


class ValidateResponse(BaseModel):
    result: str  # "VALID" | "INVALID" | "REJECTED"
    steps: list[StepResult]
    errors: list[dict[str, Any]]
    check_results: list[CheckResultModel]
    deed: dict[str, Any] | None


# ── Check-result builder ─────────────────────────────────────────────────────


def _try_parse_numeric(raw: str) -> Optional[int]:
    """Quick parse for explanations (not validation)."""
    cleaned = re.sub(r"[^\d.]", "", raw)
    try:
        return int(Decimal(cleaned).quantize(Decimal("1")))
    except (InvalidOperation, ValueError):
        return None


def _build_check_results(
    enriched: Optional[EnrichedDeed],
    errors: list[DeedValidationError],
    preflight_passed: bool,
    keyword_count: int,
) -> list[CheckResultModel]:
    """Build detailed per-check results with human-readable explanations."""

    error_codes = {e.code for e in errors}
    error_map: dict[str, DeedValidationError] = {}
    for e in errors:
        error_map.setdefault(e.code, e)

    results: list[CheckResultModel] = []

    # -- Helper --
    def _check(
        cid: str, label: str, codes: list[str], pass_text: str,
        *, state_filter: Optional[str] = None,
    ) -> CheckResultModel:
        if state_filter and enriched:
            deed_state = enriched.state.strip().upper()
            if deed_state != state_filter:
                return CheckResultModel(
                    id=cid, label=label, status="na",
                    explanation=f"Not applicable -- deed is in {deed_state}, not {state_filter}.",
                )
        failed = any(c in error_codes for c in codes)
        if failed:
            err = next((error_map[c] for c in codes if c in error_map), None)
            return CheckResultModel(
                id=cid, label=label, status="fail",
                explanation=err.message if err else "Check failed.",
            )
        return CheckResultModel(
            id=cid, label=label, status="pass",
            explanation=pass_text,
        )

    # -- 0. Document Detection --
    if preflight_passed:
        results.append(CheckResultModel(
            id="document_check", label="Document Detection", status="pass",
            explanation=f"Found {keyword_count} deed-related keywords in the input text.",
        ))
    else:
        err = error_map.get("NOT_A_DEED_ERROR")
        results.append(CheckResultModel(
            id="document_check", label="Document Detection", status="fail",
            explanation=err.message if err else "No deed keywords found.",
        ))
        _BLOCKED = [
            ("required_fields", "Required Fields"),
            ("status", "Status Valid"),
            ("state_code", "State Code"),
            ("county_match", "County Match"),
            ("state_county_match", "State-County Alignment"),
            ("date_parse", "Date Parsing"),
            ("date_order", "Date Order"),
            ("future_dates", "No Future Dates"),
            ("stale_recording", "Recording Freshness"),
            ("apn_format", "APN Format"),
            ("party_distinct", "Distinct Parties"),
            ("amount_match", "Amount Cross-Check"),
            ("amount_range", "Amount Range"),
            ("fl_doc_stamps", "FL Documentary Stamps"),
            ("ny_mansion_tax", "NY Mansion Tax"),
        ]
        for cid, label in _BLOCKED:
            results.append(CheckResultModel(
                id=cid, label=label, status="blocked",
                explanation="Blocked -- document detection failed. Input is not a deed.",
            ))
        return results

    if enriched is None:
        return results

    # -- 1. Required Fields --
    results.append(_check(
        "required_fields", "Required Fields",
        ["SCHEMA_MISSING_FIELD_ERROR"],
        "All 11 required fields are present and non-empty.",
    ))

    # -- 2. Status --
    results.append(_check(
        "status", "Status Valid",
        ["INVALID_STATUS_ERROR"],
        f"Status '{enriched.status}' is an accepted value (PRELIMINARY or FINAL).",
    ))

    # -- 3. State Code --
    results.append(_check(
        "state_code", "State Code",
        ["STATE_CODE_ERROR"],
        f"State '{enriched.state}' is a valid US state abbreviation.",
    ))

    # -- 4. County Match --
    if enriched.county_canonical:
        county_msg = (
            f"'{enriched.county_raw}' matched to '{enriched.county_canonical}' "
            f"at {enriched.county_match_confidence:.0%} confidence."
        )
    else:
        county_msg = "County matching completed."
    results.append(_check(
        "county_match", "County Match",
        ["UNKNOWN_COUNTY_ERROR"],
        county_msg,
    ))

    # -- 5. State-County Alignment --
    county_state = enriched.county_meta.get("state", "?")
    results.append(_check(
        "state_county_match", "State-County Alignment",
        ["STATE_COUNTY_MISMATCH_ERROR"],
        f"County '{enriched.county_canonical}' ({county_state}) aligns with deed state '{enriched.state}'.",
    ))

    # -- 6. Date Parsing --
    results.append(_check(
        "date_parse", "Date Parsing",
        ["DATE_PARSE_ERROR"],
        f"Signed: {enriched.date_signed}, Recorded: {enriched.date_recorded} -- both valid YYYY-MM-DD.",
    ))

    # -- 7. Date Order --
    results.append(_check(
        "date_order", "Date Order",
        ["DATE_ORDER_ERROR"],
        f"Recorded ({enriched.date_recorded}) is on or after signed ({enriched.date_signed}).",
    ))

    # -- 8. Future Dates --
    results.append(_check(
        "future_dates", "No Future Dates",
        ["FUTURE_DATE_ERROR"],
        "Neither date is in the future.",
    ))

    # -- 9. Stale Recording --
    results.append(_check(
        "stale_recording", "Recording Freshness",
        ["STALE_RECORDING_ERROR"],
        "Recording gap is within the 365-day threshold.",
    ))

    # -- 10. APN Format --
    results.append(_check(
        "apn_format", "APN Format",
        ["APN_FORMAT_ERROR"],
        f"APN '{enriched.apn}' has valid numeric segments.",
    ))

    # -- 11. Distinct Parties --
    results.append(_check(
        "party_distinct", "Distinct Parties",
        ["GRANTOR_GRANTEE_SAME_ERROR"],
        f"Grantor ('{enriched.grantor}') differs from grantee ('{enriched.grantee}').",
    ))

    # -- 12. Amount Cross-Check --
    results.append(_check(
        "amount_match", "Amount Cross-Check",
        ["AMOUNT_MISMATCH_ERROR"],
        "Numeric and written-out dollar amounts match.",
    ))

    # -- 13. Amount Range --
    results.append(_check(
        "amount_range", "Amount Range",
        ["AMOUNT_RANGE_ERROR"],
        "Amount is within acceptable range ($1 to $500M).",
    ))

    # -- 14. FL Documentary Stamps --
    meta = enriched.county_meta
    state = enriched.state.strip().upper()
    amount = _try_parse_numeric(enriched.amount_numeric_raw)
    if state == "FL" and amount and meta.get("doc_stamp_rate"):
        stamp = amount * meta["doc_stamp_rate"]
        surtax = amount * meta.get("surtax_rate", 0) if meta.get("has_surtax") else 0
        fl_msg = (
            f"FL documentary stamps: ${stamp:,.2f} "
            f"({meta['doc_stamp_rate']*100:.1f}%)"
        )
        if surtax:
            fl_msg += f" + Miami-Dade surtax: ${surtax:,.2f}"
        fl_msg += f". Total transfer taxes: ${stamp + surtax:,.2f}."
        results.append(CheckResultModel(
            id="fl_doc_stamps", label="FL Documentary Stamps",
            status="pass", explanation=fl_msg,
        ))
    else:
        results.append(_check(
            "fl_doc_stamps", "FL Documentary Stamps",
            ["FL_DOC_STAMP_REQUIRED"],
            "Documentary stamp tax computed for this Florida deed.",
            state_filter="FL",
        ))

    # -- 15. NY Mansion Tax --
    if state == "NY" and amount and meta.get("mansion_tax_threshold"):
        threshold = meta["mansion_tax_threshold"]
        ttr = meta.get("transfer_tax_rate", 0)
        transfer = amount * ttr
        if amount >= threshold:
            mt_rate = meta.get("mansion_tax_rate", 0.01)
            mansion = amount * mt_rate
            ny_msg = (
                f"Mansion tax APPLIES: ${mansion:,.2f} "
                f"({mt_rate*100:.0f}% on ${amount:,} >= ${threshold:,} threshold). "
                f"Transfer tax: ${transfer:,.2f} ({ttr*100:.1f}%). "
                f"Buyer must budget for both."
            )
        else:
            ny_msg = (
                f"Amount ${amount:,} is below ${threshold:,} mansion tax threshold. "
                f"Transfer tax: ${transfer:,.2f} ({ttr*100:.1f}%)."
            )
        results.append(CheckResultModel(
            id="ny_mansion_tax", label="NY Mansion Tax",
            status="pass", explanation=ny_msg,
        ))
    else:
        results.append(_check(
            "ny_mansion_tax", "NY Mansion Tax",
            ["NY_MANSION_TAX_APPLICABLE"],
            "Mansion tax check completed for this New York deed.",
            state_filter="NY",
        ))

    return results


# ── API endpoint ─────────────────────────────────────────────────────────────


@app.post("/api/validate", response_model=ValidateResponse)
async def api_validate(req: ValidateRequest) -> ValidateResponse:
    """Run the full pipeline and return step-by-step results."""
    ocr_text = req.ocr_text or DEFAULT_OCR_TEXT
    steps: list[StepResult] = []

    # ── Step 0: Preflight ────────────────────────────────────────────────
    t0 = time.perf_counter()
    passed, kw_count, preflight_error = preflight_deed_check(ocr_text)
    dt = (time.perf_counter() - t0) * 1000

    steps.append(StepResult(
        step="Document Detection",
        status="pass" if passed else "fail",
        duration_ms=round(dt, 1),
        data={
            "keyword_count": kw_count,
            "threshold": 3,
            "passed": passed,
        },
    ))

    if preflight_error:
        check_results = _build_check_results(None, [preflight_error], False, kw_count)
        return ValidateResponse(
            result="REJECTED",
            steps=steps,
            errors=[preflight_error.to_dict()],
            check_results=check_results,
            deed=None,
        )

    # ── Step 1: Extraction ───────────────────────────────────────────────
    t0 = time.perf_counter()
    extracted = extract(ocr_text)
    dt = (time.perf_counter() - t0) * 1000

    steps.append(StepResult(
        step="LLM Extraction",
        status="success",
        duration_ms=round(dt, 1),
        data={
            "doc_id": extracted.doc_id,
            "county_raw": extracted.county_raw,
            "state": extracted.state,
            "date_signed": extracted.date_signed,
            "date_recorded": extracted.date_recorded,
            "grantor": extracted.grantor,
            "grantee": extracted.grantee,
            "amount_numeric_raw": extracted.amount_numeric_raw,
            "amount_words_raw": extracted.amount_words_raw,
            "apn": extracted.apn,
            "status": extracted.status,
            "source_text_hash": extracted.source_text_hash[:16] + "...",
            "llm_model": extracted.llm_meta.model,
        },
    ))

    # ── Step 2: Enrichment ───────────────────────────────────────────────
    t0 = time.perf_counter()
    enriched = build_enriched_deed(extracted)
    dt = (time.perf_counter() - t0) * 1000

    steps.append(StepResult(
        step="County Enrichment",
        status="success" if enriched.county_canonical else "warning",
        duration_ms=round(dt, 1),
        data={
            "county_raw": enriched.county_raw,
            "county_canonical": enriched.county_canonical,
            "county_match_confidence": round(enriched.county_match_confidence, 4),
            "tax_rate": enriched.tax_rate,
            "county_state": enriched.county_meta.get("state"),
        },
    ))

    # ── Step 3: Validation ───────────────────────────────────────────────
    t0 = time.perf_counter()
    validated, errors = validate(enriched)
    dt = (time.perf_counter() - t0) * 1000

    steps.append(StepResult(
        step="Deterministic Validation",
        status="pass" if not errors else "fail",
        duration_ms=round(dt, 1),
        data={
            "checks_run": 15,
            "errors_found": len(errors),
        },
    ))

    # Build explanations for every check
    check_results = _build_check_results(enriched, errors, True, kw_count)

    error_dicts = [e.to_dict() for e in errors]
    deed_dict = validated.model_dump(mode="json") if validated else None

    return ValidateResponse(
        result="VALID" if not errors else "INVALID",
        steps=steps,
        errors=error_dicts,
        check_results=check_results,
        deed=deed_dict,
    )


@app.get("/api/default-text")
async def get_default_text() -> JSONResponse:
    return JSONResponse({"text": DEFAULT_OCR_TEXT})


# ── Serve the frontend ───────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    html_path = FRONTEND_DIR / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    print(f"\n  Bad Deed Validator -- http://localhost:{args.port}\n")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")
