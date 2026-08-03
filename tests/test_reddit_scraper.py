"""Unit tests for Reddit scraper helper functions (no API key needed)."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import reddit_scraper as rs

pytestmark = pytest.mark.unit


# ============================================================
# PARSING HELPERS
# ============================================================
class TestParseFloat:
    def test_simple(self):
        assert rs.parse_float("4.7") == 4.7

    def test_commas(self):
        assert rs.parse_float("1,234.5") == 1234.5

    def test_empty(self):
        assert rs.parse_float("") is None

    def test_none(self):
        assert rs.parse_float(None) is None

    def test_invalid(self):
        assert rs.parse_float("abc") is None

    def test_int_input(self):
        assert rs.parse_float(42) == 42.0


class TestParseInt:
    def test_commas(self):
        assert rs.parse_int("98,500") == 98500

    def test_k_suffix(self):
        assert rs.parse_int("1.2K") == 1200

    def test_m_suffix(self):
        assert rs.parse_int("3M") == 3_000_000

    def test_lowercase_k(self):
        assert rs.parse_int("1.5k") == 1500

    def test_int_input(self):
        assert rs.parse_int(42) == 42

    def test_float_input(self):
        assert rs.parse_int(1.5) == 1

    def test_plain_string(self):
        assert rs.parse_int("100") == 100

    def test_empty(self):
        assert rs.parse_int("") is None

    def test_none(self):
        assert rs.parse_int(None) is None

    def test_invalid(self):
        assert rs.parse_int("n/a") is None


class TestFirst:
    def test_returns_first_non_empty(self):
        rec = {"a": "", "b": None, "c": "found", "d": "later"}
        assert rs.first(rec, "a", "b", "c", "d") == "found"

    def test_default_when_all_missing(self):
        assert rs.first({}, "x", "y", default="dflt") == "dflt"

    def test_zero_is_valid(self):
        rec = {"a": 0}
        assert rs.first(rec, "a") == 0

    def test_false_is_valid(self):
        rec = {"a": False}
        assert rs.first(rec, "a") is False


class TestLooksLikeUrl:
    def test_https(self):
        assert rs.looks_like_url("https://www.reddit.com/r/python/")

    def test_http(self):
        assert rs.looks_like_url("http://example.com")

    def test_not_url(self):
        assert not rs.looks_like_url("python tutorial")

    def test_r_prefix(self):
        assert not rs.looks_like_url("r/python")


# ============================================================
# URL NORMALIZATION
# ============================================================
class TestNormalizeSubreddit:
    def test_name_only(self):
        assert rs.normalize_subreddit("python") == "https://www.reddit.com/r/python/"

    def test_r_prefix(self):
        assert rs.normalize_subreddit("r/python") == "https://www.reddit.com/r/python/"

    def test_full_url(self):
        result = rs.normalize_subreddit("https://www.reddit.com/r/python/")
        assert result == "https://www.reddit.com/r/python/"

    def test_url_without_trailing_slash(self):
        result = rs.normalize_subreddit("https://www.reddit.com/r/python")
        assert result.endswith("/")

    def test_strips_whitespace(self):
        assert rs.normalize_subreddit("  python  ") == "https://www.reddit.com/r/python/"

    def test_strips_slashes(self):
        assert rs.normalize_subreddit("/python/") == "https://www.reddit.com/r/python/"


class TestNormalizeUser:
    def test_username_only(self):
        assert rs.normalize_user("spez") == "https://www.reddit.com/user/spez/"

    def test_u_prefix(self):
        assert rs.normalize_user("u/spez") == "https://www.reddit.com/user/spez/"

    def test_user_prefix(self):
        assert rs.normalize_user("user/spez") == "https://www.reddit.com/user/spez/"

    def test_full_url(self):
        result = rs.normalize_user("https://www.reddit.com/user/spez/")
        assert result == "https://www.reddit.com/user/spez/"

    def test_trailing_slash(self):
        result = rs.normalize_user("https://www.reddit.com/user/spez")
        assert result.endswith("/")

    def test_strips_whitespace(self):
        assert rs.normalize_user("  spez  ") == "https://www.reddit.com/user/spez/"


class TestUrlDetection:
    def test_subreddit_url_true(self):
        assert rs.is_subreddit_url("https://www.reddit.com/r/python/")
        assert rs.is_subreddit_url("https://www.reddit.com/r/Python")

    def test_post_url_not_subreddit(self):
        assert not rs.is_subreddit_url(
            "https://www.reddit.com/r/python/comments/abc123/my_post/"
        )

    def test_post_url_detected(self):
        assert rs.is_post_url(
            "https://www.reddit.com/r/python/comments/abc123/my_post/"
        )

    def test_subreddit_not_post(self):
        assert not rs.is_post_url("https://www.reddit.com/r/python/")

    def test_user_url_detected(self):
        assert rs.is_user_url("https://www.reddit.com/user/spez/")
        assert rs.is_user_url("https://www.reddit.com/u/spez")

    def test_subreddit_not_user(self):
        assert not rs.is_user_url("https://www.reddit.com/r/python/")


# ============================================================
# INPUT DETECTION
# ============================================================
class TestInputTypeDetection:
    def test_keyword_from_header(self):
        assert rs.detect_input_type(["keyword", "num_of_posts"], "python") == "keyword"

    def test_query_header(self):
        assert rs.detect_input_type(["query"], "python") == "keyword"

    def test_url_from_header(self):
        assert rs.detect_input_type(["url"], "https://reddit.com/r/python/") == "url"

    def test_subreddit_header(self):
        assert rs.detect_input_type(["subreddit"], "python") == "url"

    def test_url_from_value(self):
        assert rs.detect_input_type(["col"], "https://reddit.com/r/python/") == "url"

    def test_default_keyword(self):
        assert rs.detect_input_type(["something"], "python tutorial") == "keyword"


# ============================================================
# CSV READING
# ============================================================
class TestCSVReading:
    def test_subreddit_url_csv(self, tmp_path):
        csv_file = tmp_path / "subs.csv"
        csv_file.write_text(
            "url\nhttps://www.reddit.com/r/python/\nhttps://www.reddit.com/r/webdev/",
            encoding="utf-8",
        )
        input_type, inputs = rs.read_input_csv(str(csv_file), "posts")
        assert input_type == "url"
        assert len(inputs) == 2
        assert inputs[0]["url"] == "https://www.reddit.com/r/python/"

    def test_keyword_csv(self, tmp_path):
        csv_file = tmp_path / "kw.csv"
        csv_file.write_text(
            "keyword,num_of_posts\npython tutorial,20\nweb scraping,30",
            encoding="utf-8",
        )
        input_type, inputs = rs.read_input_csv(str(csv_file), "posts")
        assert input_type == "keyword"
        assert len(inputs) == 2
        assert inputs[0]["keyword"] == "python tutorial"
        assert inputs[0]["num_of_posts"] == 20

    def test_keyword_default_num_posts(self, tmp_path):
        csv_file = tmp_path / "kw.csv"
        csv_file.write_text("keyword\npython", encoding="utf-8")
        _, inputs = rs.read_input_csv(str(csv_file), "posts")
        assert inputs[0]["num_of_posts"] == rs.DEFAULT_NUM_POSTS

    def test_bare_subreddit_names(self, tmp_path):
        csv_file = tmp_path / "subs.csv"
        csv_file.write_text("subreddit\npython\nmachinelearning", encoding="utf-8")
        input_type, inputs = rs.read_input_csv(str(csv_file), "posts")
        assert input_type == "url"
        assert inputs[0]["url"] == "https://www.reddit.com/r/python/"
        assert inputs[1]["url"] == "https://www.reddit.com/r/machinelearning/"

    def test_comments_mode_always_url(self, tmp_path):
        csv_file = tmp_path / "posts.csv"
        csv_file.write_text(
            "url\nhttps://www.reddit.com/r/python/comments/abc/test/",
            encoding="utf-8",
        )
        input_type, inputs = rs.read_input_csv(str(csv_file), "comments")
        assert input_type == "url"
        assert len(inputs) == 1

    def test_profiles_mode_bare_usernames(self, tmp_path):
        csv_file = tmp_path / "users.csv"
        csv_file.write_text("username\nspez\ngallowboob", encoding="utf-8")
        input_type, inputs = rs.read_input_csv(str(csv_file), "profiles")
        assert input_type == "url"
        assert inputs[0]["url"] == "https://www.reddit.com/user/spez/"
        assert inputs[1]["url"] == "https://www.reddit.com/user/gallowboob/"

    def test_empty_csv(self, tmp_path):
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("", encoding="utf-8")
        _, inputs = rs.read_input_csv(str(csv_file), "posts")
        assert len(inputs) == 0

    def test_latin1_fallback(self, tmp_path):
        csv_file = tmp_path / "latin.csv"
        csv_file.write_text("keyword\ncaf\u00e9", encoding="latin-1")
        _, inputs = rs.read_input_csv(str(csv_file), "posts")
        assert inputs[0]["keyword"] == "caf\u00e9"

    def test_skips_empty_rows(self, tmp_path):
        csv_file = tmp_path / "gaps.csv"
        csv_file.write_text("keyword\npython\n\nrust\n", encoding="utf-8")
        _, inputs = rs.read_input_csv(str(csv_file), "posts")
        assert len(inputs) == 2


# ============================================================
# SCRAPE URL
# ============================================================
class TestScrapeUrl:
    def test_posts_subreddit_discovery(self):
        url = rs.build_scrape_url(rs.POSTS_DATASET_ID, "subreddit_url")
        assert "/scrape?" in url
        assert "type=discover_new" in url
        assert "discover_by=subreddit_url" in url
        assert rs.POSTS_DATASET_ID in url

    def test_posts_keyword_discovery(self):
        url = rs.build_scrape_url(rs.POSTS_DATASET_ID, "keyword")
        assert "discover_by=keyword" in url
        assert "type=discover_new" in url

    def test_comments_no_discovery(self):
        url = rs.build_scrape_url(rs.COMMENTS_DATASET_ID)
        assert "/scrape?" in url
        assert "discover_new" not in url
        assert rs.COMMENTS_DATASET_ID in url

    def test_profiles_no_discovery(self):
        url = rs.build_scrape_url(rs.PROFILES_DATASET_ID)
        assert "discover_new" not in url
        assert rs.PROFILES_DATASET_ID in url


# ============================================================
# RESPONSE INTERPRETATION
# ============================================================
class TestInterpretScrapeResponse:
    def test_ndjson_records(self):
        text = '{"post_id":"A","title":"One"}\n{"post_id":"B","title":"Two"}'
        records, sid = rs.interpret_scrape_response(text)
        assert sid is None
        assert len(records) == 2 and records[1]["title"] == "Two"

    def test_json_array(self):
        text = '[{"post_id":"A"},{"post_id":"B"}]'
        records, sid = rs.interpret_scrape_response(text)
        assert sid is None and len(records) == 2

    def test_snapshot_envelope(self):
        text = '{"snapshot_id":"sd_123","message":"still in progress"}'
        records, sid = rs.interpret_scrape_response(text)
        assert records == [] and sid == "sd_123"

    def test_single_record_object(self):
        text = '{"post_id":"A","title":"Solo"}'
        records, sid = rs.interpret_scrape_response(text)
        assert sid is None and records[0]["title"] == "Solo"

    def test_empty(self):
        assert rs.interpret_scrape_response("") == ([], None)

    def test_whitespace_only(self):
        assert rs.interpret_scrape_response("   \n  ") == ([], None)

    def test_ndjson_skips_bad_lines(self):
        text = '{"post_id":"A"}\nnot json\n{"post_id":"B"}'
        records, sid = rs.interpret_scrape_response(text)
        assert len(records) == 2


# ============================================================
# RECORD PARSING
# ============================================================
class TestParsePost:
    def test_maps_standard_fields(self):
        rec = {
            "url": "https://www.reddit.com/r/python/comments/abc/post/",
            "post_id": "abc123",
            "title": "Hello World",
            "description": "My first post",
            "user_posted": "testuser",
            "community_name": "r/python",
            "community_members_num": 1500000,
            "num_upvotes": 42,
            "num_comments": 7,
            "date_posted": "2024-01-15",
            "tag": "Discussion",
        }
        row = rs.parse_post(rec)
        assert row["post_url"] == rec["url"]
        assert row["post_id"] == "abc123"
        assert row["title"] == "Hello World"
        assert row["body"] == "My first post"
        assert row["author"] == "testuser"
        assert row["subreddit"] == "r/python"
        assert row["subscribers"] == 1500000
        assert row["upvotes"] == 42
        assert row["num_comments"] == 7
        assert row["created_at"] == "2024-01-15"
        assert row["flair"] == "Discussion"

    def test_alias_fields(self):
        rec = {
            "link": "https://x",
            "author": "bob",
            "selftext": "body text",
            "subreddit_name": "r/test",
            "score": 100,
        }
        row = rs.parse_post(rec)
        assert row["post_url"] == "https://x"
        assert row["author"] == "bob"
        assert row["body"] == "body text"
        assert row["subreddit"] == "r/test"
        assert row["upvotes"] == 100

    def test_missing_fields(self):
        row = rs.parse_post({})
        assert row["title"] == ""
        assert row["upvotes"] is None
        assert row["subscribers"] is None

    def test_non_dict(self):
        row = rs.parse_post("not a dict")
        assert set(row.keys()) == set(rs.POST_FIELDS)
        assert all(v == "" for v in row.values())

    def test_k_suffix_subscribers(self):
        rec = {"community_members_num": "1.5M"}
        row = rs.parse_post(rec)
        assert row["subscribers"] == 1500000


class TestParseComment:
    def test_maps_standard_fields(self):
        rec = {
            "url": "https://www.reddit.com/r/python/comments/abc/post/c123",
            "comment_id": "c123",
            "post_url": "https://www.reddit.com/r/python/comments/abc/post/",
            "author": "commenter",
            "body": "Great post!",
            "score": 15,
            "created_at": "2024-01-16",
            "subreddit": "r/python",
        }
        row = rs.parse_comment(rec)
        assert row["comment_url"] == rec["url"]
        assert row["comment_id"] == "c123"
        assert row["post_url"] == rec["post_url"]
        assert row["author"] == "commenter"
        assert row["body"] == "Great post!"
        assert row["score"] == 15
        assert row["created_at"] == "2024-01-16"

    def test_alias_fields(self):
        rec = {"user_posted": "alice", "text": "Nice", "upvotes": 5}
        row = rs.parse_comment(rec)
        assert row["author"] == "alice"
        assert row["body"] == "Nice"
        assert row["score"] == 5

    def test_non_dict(self):
        row = rs.parse_comment(None)
        assert set(row.keys()) == set(rs.COMMENT_FIELDS)


class TestParseProfile:
    def test_maps_standard_fields(self):
        rec = {
            "url": "https://www.reddit.com/user/spez/",
            "username": "spez",
            "display_name": "spez",
            "total_karma": 250000,
            "post_karma": 100000,
            "comment_karma": 150000,
            "created_at": "2005-06-06",
            "description": "Reddit CEO",
        }
        row = rs.parse_profile(rec)
        assert row["profile_url"] == rec["url"]
        assert row["username"] == "spez"
        assert row["total_karma"] == 250000
        assert row["post_karma"] == 100000
        assert row["comment_karma"] == 150000
        assert row["description"] == "Reddit CEO"

    def test_alias_fields(self):
        rec = {"name": "bob", "karma": 5000, "link_karma": 2000, "bio": "Hello"}
        row = rs.parse_profile(rec)
        assert row["username"] == "bob"
        assert row["total_karma"] == 5000
        assert row["post_karma"] == 2000
        assert row["description"] == "Hello"

    def test_non_dict(self):
        row = rs.parse_profile("string")
        assert set(row.keys()) == set(rs.PROFILE_FIELDS)


# ============================================================
# DEDUPE
# ============================================================
class TestDedupe:
    def test_dedupe_by_key(self):
        rows = [
            {"post_id": "A", "title": "one"},
            {"post_id": "A", "title": "dup"},
            {"post_id": "B", "title": "two"},
        ]
        out = rs.dedupe(rows, "post_id")
        assert len(out) == 2
        assert out[0]["title"] == "one"

    def test_keeps_rows_with_empty_key(self):
        rows = [{"post_id": ""}, {"post_id": ""}]
        assert len(rs.dedupe(rows, "post_id")) == 2

    def test_preserves_order(self):
        rows = [{"id": "C"}, {"id": "A"}, {"id": "B"}]
        out = rs.dedupe(rows, "id")
        assert [r["id"] for r in out] == ["C", "A", "B"]


# ============================================================
# OUTPUT
# ============================================================
class TestWriteOutput:
    def test_write_csv(self, tmp_path):
        rows = [{"title": "A", "upvotes": 10}, {"title": "B", "upvotes": None}]
        out = tmp_path / "out.csv"
        rs.write_output(rows, str(out), ["title", "upvotes"], "csv")
        text = out.read_text(encoding="utf-8")
        assert "title,upvotes" in text
        assert "A,10" in text
        assert "B," in text

    def test_write_json(self, tmp_path):
        rows = [{"title": "A", "upvotes": 10}, {"title": "B", "upvotes": None}]
        out = tmp_path / "out.json"
        rs.write_output(rows, str(out), ["title", "upvotes"], "json")
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data[0]["title"] == "A"
        assert data[1]["upvotes"] is None

    def test_write_csv_unicode(self, tmp_path):
        rows = [{"title": "caf\u00e9", "upvotes": 1}]
        out = tmp_path / "out.csv"
        rs.write_output(rows, str(out), ["title", "upvotes"], "csv")
        text = out.read_text(encoding="utf-8")
        assert "caf\u00e9" in text


class TestOutputPaths:
    def test_default_posts_csv(self):
        assert rs.default_output_path("posts", "csv") == "output_posts.csv"

    def test_default_posts_json(self):
        assert rs.default_output_path("posts", "json") == "output_posts.json"

    def test_default_comments(self):
        assert rs.default_output_path("comments", "csv") == "output_comments.csv"

    def test_default_profiles(self):
        assert rs.default_output_path("profiles", "json") == "output_profiles.json"

    def test_comments_output_path_csv(self):
        assert rs.comments_output_path("out.csv") == "out_comments.csv"

    def test_comments_output_path_json(self):
        assert rs.comments_output_path("data/out.json") == os.path.join(
            "data", "out_comments.json"
        )


# ============================================================
# LOOKUPS
# ============================================================
class TestLookups:
    def test_get_fields_posts(self):
        assert rs.get_fields("posts") == rs.POST_FIELDS

    def test_get_fields_comments(self):
        assert rs.get_fields("comments") == rs.COMMENT_FIELDS

    def test_get_fields_profiles(self):
        assert rs.get_fields("profiles") == rs.PROFILE_FIELDS

    def test_get_dataset_id_posts(self):
        assert rs.get_dataset_id("posts") == rs.POSTS_DATASET_ID

    def test_get_dataset_id_comments(self):
        assert rs.get_dataset_id("comments") == rs.COMMENTS_DATASET_ID

    def test_get_dataset_id_profiles(self):
        assert rs.get_dataset_id("profiles") == rs.PROFILES_DATASET_ID

    def test_get_parser_posts(self):
        assert rs.get_parser("posts") is rs.parse_post

    def test_get_parser_comments(self):
        assert rs.get_parser("comments") is rs.parse_comment

    def test_get_parser_profiles(self):
        assert rs.get_parser("profiles") is rs.parse_profile


# ============================================================
# ARG PARSER
# ============================================================
class TestArgParser:
    def test_defaults(self):
        args = rs.build_arg_parser().parse_args([])
        assert args.mode == "posts"
        assert args.format == "csv"
        assert args.comments is False
        assert args.limit is None
        assert args.dry_run is False
        assert args.quiet is False

    def test_comments_flag(self):
        args = rs.build_arg_parser().parse_args(["--comments"])
        assert args.comments is True

    def test_mode_selection(self):
        args = rs.build_arg_parser().parse_args(["--mode", "profiles", "users.csv"])
        assert args.mode == "profiles"
        assert args.input == "users.csv"

    def test_full_args(self):
        args = rs.build_arg_parser().parse_args(
            [
                "subs.csv", "out.json", "--format", "json", "--mode", "posts",
                "--comments", "--limit", "10",
            ]
        )
        assert args.input == "subs.csv"
        assert args.output == "out.json"
        assert args.format == "json"
        assert args.comments is True
        assert args.limit == 10

    def test_dry_run(self):
        args = rs.build_arg_parser().parse_args(["--dry-run"])
        assert args.dry_run is True


# ============================================================
# DISCOVER_BY LOGIC
# ============================================================
class TestDiscoverBy:
    def test_posts_keyword(self):
        assert rs._discover_by_for("posts", "keyword") == "keyword"

    def test_posts_url(self):
        assert rs._discover_by_for("posts", "url") == "subreddit_url"

    def test_comments_returns_none(self):
        assert rs._discover_by_for("comments", "url") is None

    def test_profiles_returns_none(self):
        assert rs._discover_by_for("profiles", "url") is None


# ============================================================
# FIXTURE TEST
# ============================================================
class TestFixture:
    """Runs parse_post() against a sample API response fixture."""

    def _load(self):
        path = os.path.join(
            os.path.dirname(__file__), "fixtures", "reddit_post.json"
        )
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def test_core_fields_present(self):
        row = rs.parse_post(self._load())
        for field in ("post_url", "post_id", "title", "author", "subreddit"):
            assert row[field] not in (None, ""), (
                f"{field} unexpectedly blank on fixture"
            )

    def test_upvotes_parsed(self):
        row = rs.parse_post(self._load())
        assert isinstance(row["upvotes"], int)
        assert row["upvotes"] == 342

    def test_num_comments_parsed(self):
        row = rs.parse_post(self._load())
        assert isinstance(row["num_comments"], int)
        assert row["num_comments"] == 47

    def test_subscribers_parsed(self):
        row = rs.parse_post(self._load())
        assert isinstance(row["subscribers"], int)
        assert row["subscribers"] == 1850000

    def test_flair_parsed(self):
        row = rs.parse_post(self._load())
        assert row["flair"] == "Showcase"

    def test_body_from_description(self):
        row = rs.parse_post(self._load())
        assert "data collection" in row["body"]
