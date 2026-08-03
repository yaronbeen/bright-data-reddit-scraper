"""E2E tests against the live Bright Data API for Reddit."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import reddit_scraper as rs
from tests.conftest import skip_no_api_key


@pytest.mark.e2e
class TestRedditE2E:
    @skip_no_api_key
    def test_api_key_valid(self):
        """Confirm the API key is accepted (not 401/403)."""
        try:
            rs.api_request("GET", f"{rs.BASE_URL}/progress/fake_id")
        except Exception as e:
            assert "401" not in str(e)

    @skip_no_api_key
    def test_subreddit_scrape(self):
        """Collect posts from r/python and verify structure."""
        inputs = [{"url": "https://www.reddit.com/r/python/"}]
        raw = rs.collect(
            inputs, rs.POSTS_DATASET_ID, discover_by="subreddit_url",
        )
        assert raw and len(raw) >= 1
        post = raw[0]
        assert isinstance(post, dict)
        assert post.get("title") or post.get("url")

    @skip_no_api_key
    def test_parse_live_post(self):
        """Parse a live post and verify the field mapping is correct."""
        inputs = [{"url": "https://www.reddit.com/r/python/"}]
        raw = rs.collect(
            inputs, rs.POSTS_DATASET_ID, discover_by="subreddit_url",
        )
        assert raw
        row = rs.parse_post(raw[0])
        assert row["post_url"] or row["title"], (
            "Live post should have at least a URL or title"
        )
