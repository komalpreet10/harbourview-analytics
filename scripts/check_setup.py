"""Check portable setup without displaying credentials or calling OpenAI."""

import argparse
import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", action="store_true")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 11):
        raise SystemExit("Use Python 3.11 for the tested dependency set.")
    for module in ("streamlit", "pymongo", "pandas", "pydantic", "plotly", "openai", "dotenv", "presidio_analyzer", "spacy"):
        importlib.import_module(module)
    from dotenv import load_dotenv
    from src.privacy import contains_identifiers
    load_dotenv(ROOT / ".env")
    assert contains_identifiers("Did John Smith relapse?"), "Name detection check failed"
    assert not contains_identifiers("Show monthly admissions in 2025"), "Aggregate question incorrectly blocked"
    if not (ROOT / "data/harbourview_residents.csv").is_file():
        raise SystemExit("Missing supplied CSV: data/harbourview_residents.csv")
    print("Python, dependencies, privacy model, and supplied CSV: OK")
    print("OpenAI API key configured:", bool(os.environ.get("OPENAI_API_KEY")))
    if args.database:
        from src.database import run_query
        from src.schemas import DashboardSpec
        spec = DashboardSpec(metric="admission_count", dimensions=[], filters=[],
            time_window={"start": "2025-01-01", "end": "2025-12-31"}, chart_type="kpi")
        result = run_query(spec, "harbourview")
        print("MongoDB reader and query: OK")
        print("2025 admissions:", result["value"].iloc[0], "(supplied dataset expectation: 81)")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Setup check failed ({type(error).__name__}). Check dependencies, model, and configuration.")
        sys.exit(1)
