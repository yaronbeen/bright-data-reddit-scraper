"""E2E tests against the live Bright Data API for Reddit posts."""

import os, sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import reddit_post_scraper as scraper
from tests.conftest import skip_no_api_key


@pytest.mark.e2e
class TestRedditE2E:
    @skip_no_api_key
    def test_api_key_valid(self):
        try:
            scraper.api_request("GET", f"{scraper.BASE_URL}/progress/fake_id")
        except Exception as e:
            assert "401" not in str(e)

    @skip_no_api_key
    def test_subreddit_scrape(self):
        inputs = [{"url": "https://www.reddit.com/r/python/"}]
        sid = scraper.trigger_collection(
            scraper.POSTS_DATASET_ID, inputs, discover_by="subreddit_url"
        )
        assert sid
        scraper.poll_until_ready(sid)
        results = scraper.download_snapshot(sid)
        assert results and len(results) >= 1
        post = results[0]
        assert isinstance(post, dict)
        assert post.get("title") or post.get("url")
