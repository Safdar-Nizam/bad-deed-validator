"""
Centralised configuration read from environment variables.

Values are loaded once at import time.  ``python-dotenv`` is used so that a
local ``.env`` file is picked up automatically during development.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the repo root (one level above this package directory).
_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env")

OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
COUNTIES_FILE: Path = _REPO_ROOT / "counties.json"
