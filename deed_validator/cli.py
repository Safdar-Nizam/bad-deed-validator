"""
CLI entrypoint for the deed validator.

Usage
-----
::

    python -m deed_validator              # uses DEFAULT_OCR_TEXT
    python -m deed_validator deed.txt     # reads OCR text from file
"""

from __future__ import annotations

import json
import logging
import sys

from deed_validator.constants import DEFAULT_OCR_TEXT
from deed_validator.pipeline import run

# Configure structured logging for the whole package.
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s %(name)s: %(message)s",
)


def main() -> None:
    """Run the validation pipeline and print the result as JSON."""
    if len(sys.argv) > 1:
        path = sys.argv[1]
        with open(path, encoding="utf-8") as fh:
            ocr_text = fh.read()
        logging.getLogger(__name__).info("Reading OCR text from %s", path)
    else:
        ocr_text = DEFAULT_OCR_TEXT
        logging.getLogger(__name__).info("Using built-in DEFAULT_OCR_TEXT")

    validated, errors = run(ocr_text)

    print()  # visual separator after log lines
    if errors:
        print("RESULT: INVALID")
        print(json.dumps([e.to_dict() for e in errors], indent=2, default=str))
        sys.exit(1)
    else:
        print("RESULT: VALID")
        print(json.dumps(
            validated.model_dump(mode="json") if validated else {},
            indent=2,
            default=str,
        ))
        sys.exit(0)


if __name__ == "__main__":
    main()
