"""Shared fixtures for Reddit scraper tests."""

import os, csv, sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def has_api_key():
    return bool(os.environ.get("BRIGHT_DATA_API_KEY", "").strip())


skip_no_api_key = pytest.mark.skipif(
    not has_api_key(), reason="BRIGHT_DATA_API_KEY not set"
)


@pytest.fixture
def tmp_csv(tmp_path):
    def _make_csv(header, rows):
        path = tmp_path / "input.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            for row in rows:
                writer.writerow(row)
        return str(path)

    return _make_csv
