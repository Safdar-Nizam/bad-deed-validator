# Bad Deed Validator

A Python tool that takes messy OCR-scanned property deed text, uses an LLM **only** to extract fields, and then rigorously validates everything with deterministic code before accepting it.

If an AI hallucinates a number on a deed, someone could accidentally record a fraudulent transaction. This project exists to make that impossible. The LLM is a field-extraction tool it's never trusted, never authoritative, and never allowed to "fix" anything.

---

## The Problem

Real-world OCR output is messy. Dates might be flipped, dollar amounts might contradict each other, county names might be abbreviated. An LLM can do a good job of *reading* that mess and pulling out structured fields but it can't be trusted to *validate* them. What if it silently "corrects" a wrong date? What if it picks one dollar amount over another?

This tool draws a hard line:

> **The LLM extracts. Python validates. Never the other way around.**

Every contradiction, every impossible date, every dollar mismatch is caught by deterministic Python code and reported as a specific, typed error. Nothing is silently fixed.

---

## Quick Start

**Python 3.11+** required.

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/bad-deed-validator.git
cd bad-deed-validator

# Create a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# Install dependencies
pip install -e .

# Run the validator on the built-in sample deed
python -m deed_validator
```

That's it. No API key needed without one, the tool uses a built-in fixture so you can see the full pipeline work.

### Want live LLM extraction?

```bash
copy .env.example .env          # Windows
# cp .env.example .env          # macOS / Linux
```

Open `.env` and paste your OpenAI key:

```
OPENAI_API_KEY=sk-proj-...your-key-here...
OPENAI_MODEL=gpt-4.1-mini
```

Then run the same command. The tool will automatically use the real LLM instead of the fixture.

---

## What Happens When You Run It

The built-in sample deed looks like this:

```
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
*** END ***
```

There are three things wrong with this deed, and the validator catches all of them:

| Error | What's wrong |
|---|---|
| **Date Order** | It was recorded on Jan 10 but signed on Jan 15. You can't record a deed before it's signed. |
| **APN Format** | The parcel number `992-001-XA` has letters in it. California APNs must be all numeric. |
| **Amount Mismatch** | The number says $1,250,000 but the words say "One Million Two Hundred Thousand" ($1,200,000). That's a $50,000 discrepancy. |

Meanwhile, "S. Clara" is correctly fuzzy-matched to "Santa Clara" (81% confidence), the state code `CA` is valid, and the status `PRELIMINARY` is acceptable. But the deed is **still rejected** because of those three errors. Nothing is auto-corrected.

### CLI output

```
RESULT: INVALID
[
  {
    "code": "DATE_ORDER_ERROR",
    "message": "date_recorded (2024-01-10) is earlier than date_signed (2024-01-15)...",
    "field": "date_recorded",
    "details": { "date_signed": "2024-01-15", "date_recorded": "2024-01-10" }
  },
  {
    "code": "APN_FORMAT_ERROR",
    "message": "APN '992-001-XA' contains non-numeric segment(s): ['XA']...",
    "field": "apn",
    "details": { "apn": "992-001-XA", "invalid_segments": ["XA"] }
  },
  {
    "code": "AMOUNT_MISMATCH_ERROR",
    "message": "Numeric amount (1,250,000) does not match words amount (1,200,000). Difference: 50,000.",
    "field": "amount",
    "details": { "amount_numeric_value": 1250000, "amount_words_value": 1200000, "difference": 50000 }
  }
]
```

---

## How It Works

The pipeline has four stages. The first is a cheap filter, the second is the only part that touches an LLM, and everything after that is pure deterministic Python.

```
                        Raw OCR Text
                             |
                             v
                 +-----------------------+
                 |  0. Preflight Check   |  Is this even a deed?
                 |  (keyword scan)       |  Rejects "hi", gibberish, code, etc.
                 +-----------+-----------+  before wasting an API call.
                             |
                             v
                 +-----------------------+
                 |  1. LLM Extraction    |  GPT-4.1-mini parses the text into
                 |  (UNTRUSTED)          |  a structured JSON object.
                 +-----------+-----------+  Preserves ALL inconsistencies.
                             |
                             v
                 +-----------------------+
                 |  2. County Enrichment |  "S. Clara" -> "Santa Clara"
                 |  (rapidfuzz)          |  Attaches tax rate + state metadata.
                 +-----------+-----------+  Threshold: 80% similarity.
                             |
                             v
                 +-----------------------+
                 |  3. Validation        |  16 deterministic checks.
                 |  (pure Python)        |  Every error is typed and specific.
                 +-----------+-----------+  No silent corrections.
                             |
                             v
                   +-------------------+
                   |  Any errors?      |
                   |  YES -> INVALID   |  Returns list of typed errors.
                   |  NO  -> VALID     |  Returns ValidatedDeed + closing cost.
                   +-------------------+
```

### The trust boundary

The LLM prompt explicitly says: *"You are a mechanical extraction tool, NOT a validator. Never fix typos. Never correct dates. Never reconcile contradictions."* The model returns what it sees, and then Python decides if what it sees makes sense.

If the LLM returns invalid JSON, it's caught as an `LLMOutputFormatError`. If it returns a date that looks fine but is logically impossible, `validate.py` catches it. The LLM has zero authority over the final decision.

---

## All 16 Validation Checks

Every check produces a specific, typed error with a code, message, affected field, and a details dict. All errors are collected (not short-circuited), so the user sees everything wrong in one pass.

| # | Check | Error Code | What it catches |
|---|---|---|---|
| 0 | Document detection | `NOT_A_DEED_ERROR` | Non-deed input rejected before LLM runs |
| 1 | Required fields | `SCHEMA_MISSING_FIELD_ERROR` | Blank or missing extracted fields |
| 2 | Status | `INVALID_STATUS_ERROR` | Status is not `PRELIMINARY` or `FINAL` |
| 3 | State code | `STATE_CODE_ERROR` | Not a valid US state abbreviation |
| 4 | County match | `UNKNOWN_COUNTY_ERROR` | No county matched above 80% fuzzy confidence |
| 5 | State-county alignment | `STATE_COUNTY_MISMATCH_ERROR` | County belongs to a different state than deed claims |
| 6 | Date parsing | `DATE_PARSE_ERROR` | Date string can't be parsed as YYYY-MM-DD |
| 7 | Date order | `DATE_ORDER_ERROR` | Recorded before signed (impossible) |
| 8 | Future dates | `FUTURE_DATE_ERROR` | Signed or recorded date is in the future |
| 9 | Stale recording | `STALE_RECORDING_ERROR` | More than 365 days between signing and recording |
| 10 | APN format | `APN_FORMAT_ERROR` | Non-numeric segments in the parcel number |
| 11 | Distinct parties | `GRANTOR_GRANTEE_SAME_ERROR` | Grantor and grantee are the same entity (self-dealing) |
| 12 | Amount cross-check | `AMOUNT_MISMATCH_ERROR` | Numeric dollar amount doesn't match written-out words |
| 13 | Amount range | `AMOUNT_RANGE_ERROR` | Zero, negative, or above $500M |
| 14 | FL doc stamps | `FL_DOC_STAMP_REQUIRED` | Florida documentary stamp tax must be disclosed |
| 15 | NY mansion tax | `NY_MANSION_TAX_APPLICABLE` | New York mansion tax applies (property >= $1M) |

---

## Multi-State Support

The validator handles state-specific rules for California, Florida, and New York. County reference data (tax rates, surcharges, thresholds) lives in `counties.json`.

### California
- Counties: Santa Clara, San Mateo, Santa Cruz
- APN format check: numeric dash-separated segments only
- Closing cost: `amount x county_tax_rate`
I also included the two locations this job opening applies to, New York and Miami, so that during the demo I can show how we can incorporate state specific rules and logic when we build this in production.

### Florida
- Counties: Miami-Dade, Broward, Palm Beach, Orange, Hillsborough
- Documentary stamp tax: $0.70 per $100 (0.7%)
- Miami-Dade surtax: additional $0.45 per $100 — only in Miami-Dade
- Closing cost: base tax + doc stamps + surtax (if applicable)

### New York
- Counties: New York, Kings, Queens, Westchester, Nassau, Suffolk
- Transfer tax: $2 per $500 (0.4%)
- Mansion tax: 1% on residential properties at or above $1,000,000
- Closing cost: base tax + transfer tax + mansion tax (if applicable)

Closing costs are only computed if the deed passes **all** validation checks. A deed with errors never gets a dollar estimate.

---

## Running Tests

```bash
pytest -v
```

**114 tests, all passing.** Tests never call the LLM — a `conftest.py` fixture forcibly clears `OPENAI_API_KEY` before every test to guarantee isolation. All extraction uses deterministic fixture data.

| Test file | What it covers |
|---|---|
| `test_pipeline_integration.py` | End-to-end pipeline on the sample deed — proves the exact 3 errors are caught |
| `test_validation_dates.py` | Date order errors, date parsing errors, valid date scenarios |
| `test_validation_money.py` | Amount mismatch detection, matching amounts pass cleanly |
| `test_enrichment_county.py` | "S. Clara" -> "Santa Clara" fuzzy matching, unknown counties, multi-state |
| `test_money_words.py` | English words-to-dollars conversion ("One Million Two Hundred Thousand" -> 1200000) |
| `test_validation_extended.py` | APN format, future dates, stale recording, self-dealing, amount range, state codes |
| `test_fl_ny_specific.py` | FL documentary stamps, Miami-Dade surtax, NY mansion tax, state-county mismatches |
| `test_preflight.py` | Non-deed rejection ("hi", empty string, random text), real deed acceptance |

---

## Web UI (Optional)

There's a visual frontend that shows the pipeline running step by step, with animated check results and explanations.

```bash
pip install -e ".[web]"
python -m deed_validator.server
# Open http://localhost:8090
```

You can paste any OCR text or hit "Validate" to run the default sample. Non-deed input gets instantly rejected at preflight with all downstream checks shown as blocked.

---

## Project Structure

```
bad-deed-validator/
├── counties.json                 # County reference data (CA, FL, NY)
├── .env.example                  # Template — copy to .env, add your key
├── .gitignore
├── pyproject.toml
├── README.md
│
├── deed_validator/
│   ├── __init__.py
│   ├── __main__.py               # python -m deed_validator
│   ├── config.py                 # Reads env vars (python-dotenv)
│   ├── constants.py              # DEFAULT_OCR_TEXT + thresholds
│   ├── models.py                 # Pydantic schemas: Extracted -> Enriched -> Validated
│   ├── errors.py                 # 16 typed error classes
│   ├── llm_client.py             # OpenAI wrapper (extraction only)
│   ├── extractor.py              # Routes to LLM or fixture fallback
│   ├── enrich.py                 # County fuzzy matching (rapidfuzz)
│   ├── money_words.py            # "One Million Two Hundred Thousand" -> 1200000
│   ├── validate.py               # All 16 validation checks
│   ├── pipeline.py               # Orchestrates: preflight -> extract -> enrich -> validate
│   ├── cli.py                    # CLI entry point
│   ├── server.py                 # FastAPI web server (optional)
│   └── frontend/
│       └── index.html            # Single-page visual demo
│
└── tests/
    ├── conftest.py               # Blocks LLM calls during tests
    ├── fixtures.py               # Test data factories (CA, FL, NY)
    ├── fixtures/
    │   └── extracted_deed.json   # Static extraction fixture
    ├── test_pipeline_integration.py
    ├── test_validation_dates.py
    ├── test_validation_money.py
    ├── test_validation_extended.py
    ├── test_enrichment_county.py
    ├── test_fl_ny_specific.py
    ├── test_money_words.py
    └── test_preflight.py
```

---

## Design Decisions

**Why doesn't the LLM validate anything?**
Because LLMs hallucinate. If the deed says the recording date is before the signing date, an LLM might "helpfully" swap them. In financial document processing, that's not a feature it's a liability. The LLM reads; deterministic code decides.

**Why collect all errors instead of failing on the first one?**
So the user can fix everything in one pass. Discovering errors one at a time is frustrating and wastes cycles.

**Why fuzzy matching for counties?**
OCR output is messy. "S. Clara" should match "Santa Clara". But the fuzzy match has a hard threshold (80%) below that, it's an explicit `UNKNOWN_COUNTY_ERROR`, not a guess.

**Why compute closing costs last?**
A deed with a date error or an amount mismatch should never get a dollar estimate. Computing costs on bad data would be irresponsible. Closing costs are calculated only after all 16 checks pass.

**Why SHA-256 the input text?**
Traceability. The hash of the original OCR text is embedded in every extracted deed. If someone re-runs the pipeline on modified text, the hash changes you can always trace a result back to its exact input.

**Why does the preflight check exist?**
If someone types "hi" or pastes random text, there's no reason to burn an API call on it. A quick keyword scan (looking for "deed", "grantor", "county", etc.) rejects obvious non-deed input before the LLM is ever called.

---

## Security

- **`.env` is gitignored.** Only `.env.example` (with placeholder values) ships in the repo. Your real API key never touches GitHub.
- **API keys are read from environment variables only** — never hardcoded, never logged.
- **LLM output is parsed as untrusted JSON.** Malformed responses raise `LLMOutputFormatError`.
- **Tests never hit the network.** `conftest.py` clears the API key before every test.

---

## Commands Reference

| Command | What it does |
|---|---|
| `python -m deed_validator` | Run CLI with the built-in sample deed |
| `python -m deed_validator deed.txt` | Run CLI with a custom OCR text file |
| `python -m deed_validator.server` | Start the web UI on http://localhost:8090 |
| `pytest -v` | Run all 114 tests |
| `pip install -e .` | Install core dependencies |
| `pip install -e ".[web]"` | Install core + web UI dependencies |
| `pip install -e ".[dev]"` | Install core + test/lint dependencies |
