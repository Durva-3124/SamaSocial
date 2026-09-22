"""Generate fixture files for the evaluation harness.

Usage:
    cd backend
    python -m eval.make_fixtures
"""
from __future__ import annotations

import json
from pathlib import Path

from eval.fixtures import (
    FACTS,
    build_ml_html,
    build_photosynthesis_pdf,
    build_python_transcript,
    build_rest_api_pptx,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def main() -> None:
    FIXTURES_DIR.mkdir(exist_ok=True)

    pdf_path = FIXTURES_DIR / "photosynthesis.pdf"
    pdf_path.write_bytes(build_photosynthesis_pdf())
    print(f"  wrote {pdf_path} ({pdf_path.stat().st_size} bytes)")

    pptx_path = FIXTURES_DIR / "rest_apis.pptx"
    pptx_path.write_bytes(build_rest_api_pptx())
    print(f"  wrote {pptx_path} ({pptx_path.stat().st_size} bytes)")

    html_path = FIXTURES_DIR / "ml_basics.html"
    html_path.write_text(build_ml_html(), encoding="utf-8")
    print(f"  wrote {html_path}")

    transcript_path = FIXTURES_DIR / "python_transcript.json"
    transcript_path.write_text(
        json.dumps(build_python_transcript(), indent=2), encoding="utf-8"
    )
    print(f"  wrote {transcript_path}")

    facts_path = Path(__file__).parent / "facts.json"
    facts_path.write_text(json.dumps(FACTS, indent=2), encoding="utf-8")
    print(f"  wrote {facts_path} ({len(FACTS)} facts)")

    print("Fixtures ready.")


if __name__ == "__main__":
    main()
