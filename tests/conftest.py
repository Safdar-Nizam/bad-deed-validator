"""
Shared pytest configuration and fixtures.

Ensures tests **never** accidentally call a live LLM:
  - OPENAI_API_KEY is forcibly cleared before any test runs.
  - A safety autouse fixture guarantees this at the session level.

This file also serves as documentation: the test suite is 100% deterministic
and can run in CI without any external API keys.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _block_live_llm_calls() -> None:
    """
    Prevent any test from accidentally calling the real OpenAI API.

    Even if a developer has ``OPENAI_API_KEY`` set in their shell, this
    fixture clears it so the extractor falls back to the static fixture
    JSON.  Tests must never depend on network calls.
    """
    os.environ.pop("OPENAI_API_KEY", None)

    # Also patch the config module's cached value, since it's read at import time.
    import deed_validator.config as cfg
    cfg.OPENAI_API_KEY = ""
