"""Unit tests for Reddit scraper helper functions."""

import os, pytest
import reddit_post_scraper as scraper


class TestNormalizeSubreddit:
    def test_name_only(self):
        assert (
            scraper.normalize_subreddit("python") == "https://www.reddit.com/r/python/"
        )

    def test_r_prefix(self):
        assert (
            scraper.normalize_subreddit("r/python")
            == "https://www.reddit.com/r/python/"
        )

    def test_full_url(self):
        result = scraper.normalize_subreddit("https://www.reddit.com/r/python/")
        assert "reddit.com/r/python/" in result

    def test_trailing_slash(self):
        result = scraper.normalize_subreddit("https://www.reddit.com/r/python")
        assert result.endswith("/")


class TestParseCount:
    def test_int(self):
        assert scraper.parse_count(1234) == 1234

    def test_k(self):
        assert scraper.parse_count("1.2K") == 1200

    def test_m(self):
        assert scraper.parse_count("1.5M") == 1500000

    def test_none(self):
        assert scraper.parse_count(None) == 0

    def test_empty(self):
        assert scraper.parse_count("") == 0


class TestReadInputCsv:
    def test_subreddit_mode(self, tmp_csv):
        path = tmp_csv(["url"], [["https://www.reddit.com/r/python/"]])
        mode, entries = scraper.read_input_csv(path)
        assert mode == "subreddit"
        assert len(entries) == 1

    def test_keyword_mode(self, tmp_path):
        import csv

        path = tmp_path / "kw.csv"
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["keyword", "num_of_posts"])
            w.writerow(["python tutorial", "10"])
        mode, entries = scraper.read_input_csv(str(path))
        assert mode == "keyword"
        assert entries[0]["keyword"] == "python tutorial"
        assert entries[0]["num_of_posts"] == 10
