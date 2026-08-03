"""Shared pytest fixtures and markers."""

import csv
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

skip_no_api_key = pytest.mark.skipif(
    not os.environ.get("BRIGHT_DATA_API_KEY"),
    reason="BRIGHT_DATA_API_KEY not set; skipping live Bright Data API test",
)


@pytest.fixture
def tmp_csv(tmp_path):
    """Create a temporary CSV file with the given header and rows."""
    def _make_csv(header, rows):
        path = tmp_path / "input.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            for row in rows:
                writer.writerow(row)
        return str(path)
    return _make_csv
