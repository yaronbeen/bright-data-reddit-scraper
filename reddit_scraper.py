#!/usr/bin/env python3
"""Reddit Scraper via Bright Data.

Collect structured Reddit data - posts, comments, and user profiles -
using Bright Data's maintained Reddit datasets. Public data only; no
login or cookies required.

Three collection modes, selected with --mode:
  1. Posts (default) - scrape posts from subreddits or search by keyword
  2. Comments        - collect comments from specific post URLs
  3. Profiles        - gather user profile data from user URLs

Workflow: input CSV -> Bright Data Reddit dataset -> structured data -> output file

Quick examples:
    python reddit_scraper.py                                    # built-in sample
    python reddit_scraper.py subreddits.csv                     # posts from subreddits
    python reddit_scraper.py subreddits.csv --comments          # posts + comments
    python reddit_scraper.py --mode comments posts.csv          # comments only
    python reddit_scraper.py --mode profiles users.csv          # user profiles
    python reddit_scraper.py subreddits.csv --dry-run           # validate, no credit
    python reddit_scraper.py --help

Requires:
    - Python 3.9+ (standard library only, no pip install)
    - Bright Data API key: export BRIGHT_DATA_API_KEY=your-key
      Get it at https://brightdata.com/cp/setting/users
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

__version__ = "1.0.0"

# ============================================================
# CONFIGURATION
# ============================================================
API_KEY = os.environ.get("BRIGHT_DATA_API_KEY", "")

# Bright Data dataset IDs (verified from Bright Data dashboard).
POSTS_DATASET_ID = "gd_lvz8ah06191smkebj4"       # Reddit - Posts
COMMENTS_DATASET_ID = "gd_lvzdpsdlw09j6t702"     # Reddit - Comments
PROFILES_DATASET_ID = "gd_mgnh0p8w16o65lmhp"     # Reddit - User profiles

BASE_URL = "https://api.brightdata.com/datasets/v3"

REQUEST_TIMEOUT = 180   # seconds per HTTP call
POLL_INTERVAL = 15      # seconds between progress checks
POLL_TIMEOUT = 1800     # max seconds to wait for a collection

DEFAULT_NUM_POSTS = 50  # default posts per keyword search

# Sample subreddit URLs used when no CSV is provided.
DEFAULT_SUBREDDITS = [
    "https://www.reddit.com/r/python/",
    "https://www.reddit.com/r/machinelearning/",
    "https://www.reddit.com/r/webdev/",
    "https://www.reddit.com/r/datascience/",
    "https://www.reddit.com/r/artificial/",
]

POST_FIELDS = [
    "post_url", "post_id", "title", "body", "author", "subreddit",
    "subscribers", "upvotes", "num_comments", "created_at", "flair",
]

COMMENT_FIELDS = [
    "comment_url", "comment_id", "post_url", "author", "body",
    "score", "created_at", "subreddit",
]

PROFILE_FIELDS = [
    "profile_url", "username", "display_name", "total_karma",
    "post_karma", "comment_karma", "created_at", "description",
]

DATASET_IDS = {
    "posts": POSTS_DATASET_ID,
    "comments": COMMENTS_DATASET_ID,
    "profiles": PROFILES_DATASET_ID,
}

FIELDS = {
    "posts": POST_FIELDS,
    "comments": COMMENT_FIELDS,
    "profiles": PROFILE_FIELDS,
}

_QUIET = False


def log(message: str = "") -> None:
    """Print progress unless --quiet is set."""
    if not _QUIET:
        print(message)


# ============================================================
# HTTP
# ============================================================
def api_request(
    method: str,
    url: str,
    data: Any = None,
    raw: bool = False,
) -> Union[Dict[str, Any], List[Dict[str, Any]], str, None]:
    """Make an HTTP request to the Bright Data API.

    Args:
        method: "GET" or "POST".
        url: Full API URL.
        data: Optional JSON-serializable body (list or dict).
        raw: If True, return the response body as a decoded string without
            JSON parsing (used for NDJSON responses from /scrape).

    Returns:
        Decoded string (raw=True), parsed JSON (dict/list), or None for empty.

    Raises:
        HTTPError: On an HTTP error status (401, 403, 429, 5xx, ...).
        URLError: On a network-level failure.
    """
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode() if data is not None else None
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            text = resp.read().decode()
            if raw:
                return text
            if not text.strip():
                return None
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text.strip()
    except HTTPError as e:
        body_text = e.read().decode() if e.fp else ""
        if e.code == 401:
            log("  x API authentication failed (401)")
            log("    -> Check BRIGHT_DATA_API_KEY at https://brightdata.com/cp/setting/users")
        elif e.code == 403:
            log("  x Access denied (403) - check dataset/account permissions")
        elif e.code == 429:
            log("  x Rate limited (429) - wait a few minutes before retrying")
        else:
            log(f"  x HTTP {e.code}: {body_text[:200]}")
        raise


# ============================================================
# PARSING HELPERS
# ============================================================
def parse_float(value: Any) -> Optional[float]:
    """Parse a float from various formats.

    Args:
        value: A number, string (may contain commas), or None.

    Returns:
        The float value, or None if it is missing/unparseable.
    """
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def parse_int(value: Any) -> Optional[int]:
    """Parse an int, handling '1,234' and '1.2K'/'3M' shorthand.

    Args:
        value: A number, string with commas/multipliers, or None.

    Returns:
        The int value, or None if missing/unparseable.
    """
    if value is None or value == "":
        return None
    s = str(value).strip().replace(",", "")
    mult = 1
    if s and s[-1] in ("K", "k"):
        mult, s = 1_000, s[:-1]
    elif s and s[-1] in ("M", "m"):
        mult, s = 1_000_000, s[:-1]
    try:
        return int(float(s) * mult)
    except (ValueError, TypeError):
        return None


def first(record: Dict[str, Any], *keys: str, default: str = "") -> Any:
    """Return the first non-empty value among several possible keys.

    Bright Data field names can vary slightly between dataset versions, so we
    check a few aliases and fall back to a default.
    """
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return default


def looks_like_url(value: Any) -> bool:
    """Return True if the value is an http(s) URL."""
    return str(value).strip().lower().startswith(("http://", "https://"))


# ============================================================
# URL NORMALIZATION
# ============================================================
def normalize_subreddit(raw_value: str) -> str:
    """Normalize a subreddit name or URL to a full Reddit URL.

    Args:
        raw_value: A subreddit name ("python"), r/ prefix ("r/python"),
            or full URL ("https://www.reddit.com/r/python/").

    Returns:
        A fully qualified Reddit subreddit URL with trailing slash.
    """
    val = raw_value.strip().strip("/")
    if val.startswith("http://") or val.startswith("https://"):
        return val.rstrip("/") + "/"
    if val.startswith("r/"):
        return f"https://www.reddit.com/{val}/"
    return f"https://www.reddit.com/r/{val}/"


def normalize_user(raw_value: str) -> str:
    """Normalize a username or URL to a full Reddit user URL.

    Args:
        raw_value: A username ("spez"), u/ prefix ("u/spez"),
            or full URL ("https://www.reddit.com/user/spez/").

    Returns:
        A fully qualified Reddit user URL with trailing slash.
    """
    val = raw_value.strip().strip("/")
    if val.startswith("http://") or val.startswith("https://"):
        return val.rstrip("/") + "/"
    if val.startswith("u/") or val.startswith("user/"):
        name = val.split("/", 1)[1]
        return f"https://www.reddit.com/user/{name}/"
    return f"https://www.reddit.com/user/{val}/"


def is_subreddit_url(url: str) -> bool:
    """True if the URL points to a subreddit (not a specific post or user)."""
    u = url.strip().rstrip("/").lower()
    return bool(re.search(r"/r/[^/]+$", u))


def is_post_url(url: str) -> bool:
    """True if the URL points to a specific Reddit post."""
    return "/comments/" in url.lower()


def is_user_url(url: str) -> bool:
    """True if the URL points to a Reddit user profile."""
    u = url.lower()
    return "/user/" in u or "/u/" in u


# ============================================================
# INPUT CSV
# ============================================================
def detect_input_type(headers: List[str], first_value: Any) -> str:
    """Decide whether a CSV contains keywords or URLs.

    Args:
        headers: Column names from the CSV.
        first_value: First data cell for auto-detection.

    Returns:
        "keyword" or "url".
    """
    header_set = {h.lower().strip() for h in headers}
    if header_set & {"keyword", "query", "search"}:
        return "keyword"
    if header_set & {"url", "urls", "subreddit", "subreddit_url"}:
        return "url"
    if first_value and looks_like_url(first_value):
        return "url"
    return "keyword"


def read_input_csv(
    path: str, mode: str = "posts",
) -> Tuple[str, List[Dict[str, Any]]]:
    """Read an input CSV and return (input_type, inputs) for the API trigger.

    Supports subreddit URLs, keyword search, post URLs, and user URLs.
    Tries UTF-8 first, then latin-1/iso-8859-1/cp1252 so Excel/Windows
    exports still work.

    Args:
        path: Path to the CSV file.
        mode: Collection mode ("posts", "comments", "profiles").

    Returns:
        (input_type, inputs) where input_type is "keyword" or "url".

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file cannot be decoded with any known encoding.
    """
    encodings = ["utf-8", "latin-1", "iso-8859-1", "cp1252"]
    rows: Optional[List[List[str]]] = None
    last_err: Optional[Exception] = None

    for encoding in encodings:
        try:
            with open(path, newline="", encoding=encoding) as f:
                rows = list(csv.reader(f))
            break
        except (UnicodeDecodeError, LookupError) as e:
            last_err = e
            continue

    if rows is None:
        raise ValueError(
            f"Could not decode CSV '{path}' with any of {encodings}. "
            f"Last error: {last_err}. Try re-saving the file as UTF-8."
        )
    if not rows:
        return "url", []

    headers = rows[0]
    body = rows[1:]
    first_value = (
        body[0][0].strip()
        if body and body[0]
        else (headers[0] if headers else "")
    )

    # For comments/profiles mode, input is always URLs.
    if mode in ("comments", "profiles"):
        return "url", _parse_url_rows(headers, body, rows, mode)

    input_type = detect_input_type(headers, first_value)
    if input_type == "keyword":
        return "keyword", _parse_keyword_rows(headers, body)
    return "url", _parse_url_rows(headers, body, rows, mode)


def _parse_url_rows(
    headers: List[str],
    body: List[List[str]],
    all_rows: List[List[str]],
    mode: str,
) -> List[Dict[str, Any]]:
    """Extract {"url": ...} inputs from a URL-mode CSV."""
    header_lower = [h.lower().strip() for h in headers]
    url_columns = {
        "url", "urls", "subreddit", "subreddit_url",
        "post_url", "user_url", "profile_url", "username",
    }
    has_url_header = bool(set(header_lower) & url_columns)

    if has_url_header:
        idx = next(
            (i for i, h in enumerate(header_lower) if h in url_columns), 0
        )
        source = (row[idx] if len(row) > idx else "" for row in body)
    else:
        # No recognized header; assume first row is also data.
        source = (row[0] if row else "" for row in all_rows)

    inputs: List[Dict[str, Any]] = []
    for val in source:
        val = val.strip()
        if not val:
            continue
        if looks_like_url(val):
            inputs.append({"url": val})
        elif mode == "posts":
            inputs.append({"url": normalize_subreddit(val)})
        elif mode == "profiles":
            inputs.append({"url": normalize_user(val)})
    return inputs


def _parse_keyword_rows(
    headers: List[str], body: List[List[str]],
) -> List[Dict[str, Any]]:
    """Extract keyword search inputs from a CSV."""
    col = {h.lower().strip(): i for i, h in enumerate(headers)}

    def cell(row: List[str], *names: str, default: str = "") -> str:
        for n in names:
            idx = col.get(n)
            if idx is not None and idx < len(row) and row[idx].strip() != "":
                return row[idx].strip()
        return default

    inputs: List[Dict[str, Any]] = []
    for row in body:
        if not row or not any(c.strip() for c in row):
            continue
        keyword = cell(row, "keyword", "query", "search")
        if not keyword:
            continue
        num_posts = DEFAULT_NUM_POSTS
        raw_num = cell(row, "num_of_posts", "num_posts", "posts", "limit")
        if raw_num:
            parsed = parse_int(raw_num)
            if parsed:
                num_posts = parsed
        inputs.append({"keyword": keyword, "num_of_posts": num_posts})
    return inputs


# ============================================================
# BRIGHT DATA COLLECTION
# ============================================================
def build_scrape_url(
    dataset_id: str, discover_by: Optional[str] = None,
) -> str:
    """Build the /scrape URL, adding discovery params when needed."""
    params = f"dataset_id={dataset_id}&notify=false&include_errors=true"
    if discover_by:
        params += f"&type=discover_new&discover_by={discover_by}"
    return f"{BASE_URL}/scrape?{params}"


def parse_ndjson(text: str) -> List[Dict[str, Any]]:
    """Parse newline-delimited JSON (one object per line), skipping bad lines."""
    records: List[Dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _looks_like_record(d: Dict[str, Any]) -> bool:
    """True if a dict looks like a data record rather than a status envelope."""
    return any(
        k in d
        for k in ("post_id", "comment_id", "title", "url", "name", "username")
    )


def interpret_scrape_response(
    text: str,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Interpret a /scrape response body.

    The endpoint returns data directly for fast jobs (NDJSON or a JSON array),
    or a status envelope with a snapshot_id for slower jobs, which must then
    be polled and downloaded.

    Returns:
        (records, snapshot_id). Exactly one is populated.
    """
    text = (text or "").strip()
    if not text:
        return [], None
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data, None
        if isinstance(data, dict):
            if "snapshot_id" in data and not _looks_like_record(data):
                return [], data["snapshot_id"]
            return [data], None
    except json.JSONDecodeError:
        pass
    return parse_ndjson(text), None


def poll_until_ready(snapshot_id: str) -> None:
    """Poll Bright Data until a snapshot is ready to download.

    Raises:
        RuntimeError: If the collection fails/cancels.
        TimeoutError: If it exceeds POLL_TIMEOUT.
    """
    url = f"{BASE_URL}/progress/{snapshot_id}"
    start = time.time()
    last_status = None
    while time.time() - start < POLL_TIMEOUT:
        try:
            resp = api_request("GET", url)
        except (HTTPError, URLError) as e:
            if time.time() - start < POLL_TIMEOUT:
                log(f"  Transient error (will retry): {type(e).__name__}")
                time.sleep(POLL_INTERVAL)
                continue
            raise
        status = resp.get("status") if isinstance(resp, dict) else str(resp)
        if status != last_status:
            log(f"  Status: {status} ({int(time.time() - start)}s elapsed)")
            last_status = status
        if status == "ready":
            time.sleep(5)
            return
        if status in ("failed", "error", "cancelled"):
            raise RuntimeError(f"Collection failed: {status}. Details: {resp}")
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"Collection timed out after {POLL_TIMEOUT}s")


def download_snapshot(
    snapshot_id: str, retries: int = 3,
) -> Optional[List[Dict[str, Any]]]:
    """Download snapshot results as a list of JSON records.

    Raises:
        RuntimeError: If the snapshot is still not ready after all retries.
    """
    url = f"{BASE_URL}/snapshot/{snapshot_id}?format=json"
    for attempt in range(retries):
        log(
            f"  Downloading snapshot {snapshot_id} "
            f"(attempt {attempt + 1}/{retries})..."
        )
        try:
            text = api_request("GET", url, raw=True)
        except (HTTPError, URLError) as e:
            log(f"  Download error: {type(e).__name__}")
            if attempt < retries - 1:
                time.sleep(10)
                continue
            raise
        records, still_building = interpret_scrape_response(text or "")
        if still_building and not records:
            if attempt < retries - 1:
                time.sleep(15)
                continue
            raise RuntimeError(
                f"Snapshot not ready after {retries} attempts"
            )
        return records
    return None


def collect(
    inputs: List[Dict[str, Any]],
    dataset_id: str,
    discover_by: Optional[str] = None,
    limit_per_input: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Collect records for the given inputs via the /scrape endpoint.

    Fast jobs (e.g. collecting known URLs) return data synchronously. Slower
    jobs (e.g. subreddit discovery) return a snapshot_id, which we then poll
    and download automatically.

    Args:
        inputs: Trigger inputs (URL dicts or keyword dicts).
        dataset_id: Bright Data dataset id.
        discover_by: Discovery type (e.g. "subreddit_url", "keyword").
        limit_per_input: Optional cap on results per input.

    Returns:
        A list of raw record dicts.
    """
    url = build_scrape_url(dataset_id, discover_by)
    body: Dict[str, Any] = {"input": inputs}
    if limit_per_input:
        body["limit_per_input"] = limit_per_input
    log(f"  Requesting scrape with {len(inputs)} input(s)...")
    text = api_request("POST", url, body, raw=True)
    records, snapshot_id = interpret_scrape_response(text or "")
    if snapshot_id:
        log(
            f"  Large job -> async snapshot {snapshot_id}; "
            f"polling until ready..."
        )
        poll_until_ready(snapshot_id)
        records = download_snapshot(snapshot_id) or []
    return records or []


# ============================================================
# RECORD MAPPING
# ============================================================
def parse_post(record: Dict[str, Any]) -> Dict[str, Any]:
    """Map a Bright Data Reddit post record to a flat output row.

    Args:
        record: One raw post dict from the API.

    Returns:
        A dict with the POST_FIELDS keys (missing values are "" or None).
    """
    if not isinstance(record, dict):
        return {k: "" for k in POST_FIELDS}
    return {
        "post_url": first(record, "url", "link", "permalink"),
        "post_id": first(record, "post_id", "id"),
        "title": first(record, "title", "name"),
        "body": first(
            record, "description", "selftext", "body", "content",
        ),
        "author": first(
            record, "user_posted", "author", "user", "username",
        ),
        "subreddit": first(
            record, "community_name", "subreddit", "subreddit_name",
        ),
        "subscribers": parse_int(
            first(
                record, "community_members_num", "subscribers",
                "members", default="",
            )
        ),
        "upvotes": parse_int(
            first(
                record, "num_upvotes", "upvotes", "score", "ups",
                default="",
            )
        ),
        "num_comments": parse_int(
            first(
                record, "num_comments", "comments_count",
                "num_of_comments", default="",
            )
        ),
        "created_at": first(
            record, "date_posted", "created_at", "created_utc",
            "timestamp",
        ),
        "flair": first(record, "tag", "flair", "link_flair_text"),
    }


def parse_comment(record: Dict[str, Any]) -> Dict[str, Any]:
    """Map a Bright Data Reddit comment record to a flat output row.

    Args:
        record: One raw comment dict from the API.

    Returns:
        A dict with the COMMENT_FIELDS keys.
    """
    if not isinstance(record, dict):
        return {k: "" for k in COMMENT_FIELDS}
    return {
        "comment_url": first(record, "url", "link", "permalink"),
        "comment_id": first(record, "comment_id", "id"),
        "post_url": first(
            record, "post_url", "parent_url", "submission_url",
        ),
        "author": first(
            record, "author", "user", "username", "user_posted",
        ),
        "body": first(record, "body", "text", "content", "comment"),
        "score": parse_int(
            first(record, "score", "upvotes", "ups", default="")
        ),
        "created_at": first(
            record, "created_at", "date_posted", "timestamp",
            "created_utc",
        ),
        "subreddit": first(
            record, "subreddit", "community_name", "subreddit_name",
        ),
    }


def parse_profile(record: Dict[str, Any]) -> Dict[str, Any]:
    """Map a Bright Data Reddit user profile record to a flat output row.

    Args:
        record: One raw profile dict from the API.

    Returns:
        A dict with the PROFILE_FIELDS keys.
    """
    if not isinstance(record, dict):
        return {k: "" for k in PROFILE_FIELDS}
    return {
        "profile_url": first(record, "url", "link", "profile_url"),
        "username": first(
            record, "username", "name", "user", "screen_name",
        ),
        "display_name": first(
            record, "display_name", "display", "full_name",
        ),
        "total_karma": parse_int(
            first(
                record, "total_karma", "karma", "combined_karma",
                default="",
            )
        ),
        "post_karma": parse_int(
            first(record, "post_karma", "link_karma", default="")
        ),
        "comment_karma": parse_int(
            first(record, "comment_karma", default="")
        ),
        "created_at": first(
            record, "created_at", "created_utc", "account_created",
            "created_date",
        ),
        "description": first(
            record, "description", "bio", "about",
            "public_description",
        ),
    }


PARSERS = {
    "posts": parse_post,
    "comments": parse_comment,
    "profiles": parse_profile,
}


def get_fields(mode: str) -> List[str]:
    """Return the output field list for the given mode."""
    return FIELDS[mode]


def get_dataset_id(mode: str) -> str:
    """Return the Bright Data dataset ID for the given mode."""
    return DATASET_IDS[mode]


def get_parser(mode: str):
    """Return the record-parsing function for the given mode."""
    return PARSERS[mode]


def dedupe(rows: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    """Drop rows sharing the same non-empty value for `key` (keep first)."""
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for row in rows:
        val = row.get(key) or ""
        if val and val in seen:
            continue
        if val:
            seen.add(val)
        out.append(row)
    return out


# ============================================================
# OUTPUT
# ============================================================
def write_output(
    rows: List[Dict[str, Any]],
    path: str,
    fields: List[str],
    fmt: str,
) -> None:
    """Write rows to `path` as CSV or JSON."""
    if fmt == "json":
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)
    else:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)


def default_output_path(mode: str, fmt: str) -> str:
    """Default output filename for the chosen mode and format."""
    ext = "json" if fmt == "json" else "csv"
    return f"output_{mode}.{ext}"


def comments_output_path(posts_path: str) -> str:
    """Derive a comments filename next to the posts output."""
    stem, ext = os.path.splitext(posts_path)
    return f"{stem}_comments{ext or '.csv'}"


# ============================================================
# CLI
# ============================================================
def build_arg_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="reddit_scraper.py",
        description=(
            "Scrape Reddit data (posts, comments, profiles) via "
            "Bright Data (public data only)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python reddit_scraper.py\n"
            "  python reddit_scraper.py subreddits.csv\n"
            "  python reddit_scraper.py subreddits.csv --comments\n"
            "  python reddit_scraper.py --mode comments posts.csv\n"
            "  python reddit_scraper.py --mode profiles users.csv "
            "out.json --format json\n"
            "  python reddit_scraper.py subreddits.csv --dry-run\n"
        ),
    )
    parser.add_argument(
        "input", nargs="?",
        help="Input CSV (subreddit URLs, post URLs, user URLs, or "
             "keywords). Omit for built-in sample.",
    )
    parser.add_argument(
        "output", nargs="?",
        help="Output file. Default: output_<mode>.csv/.json",
    )
    parser.add_argument(
        "--mode", choices=["posts", "comments", "profiles"],
        default="posts",
        help="What to collect (default: posts)",
    )
    parser.add_argument(
        "--format", choices=["csv", "json"], default="csv",
        help="Output format (default: csv)",
    )
    parser.add_argument(
        "--comments", action="store_true",
        help="Also collect comments for each post (posts mode only)",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Max rows to write",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate input + API key without collecting "
             "(spends no credit)",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress progress output",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def check_auth() -> bool:
    """Cheap auth probe: hit a bogus progress endpoint.

    Returns:
        True if the key is accepted (any non-auth response), False on 401/403.
    """
    try:
        api_request("GET", f"{BASE_URL}/progress/dryrun_invalid_snapshot")
        return True
    except HTTPError as e:
        return e.code not in (401, 403)
    except URLError:
        raise


def _load_inputs(
    input_csv: Optional[str], mode: str,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Load inputs from a CSV or fall back to the built-in sample."""
    if input_csv:
        if not os.path.exists(input_csv):
            log(f"x ERROR: Input file not found: {input_csv}")
            sys.exit(1)
        log(f"[1/4] Reading input from {input_csv}")
        return read_input_csv(input_csv, mode)
    log("[1/4] No CSV provided - using built-in sample subreddits")
    log(
        "     (Sample: r/python, r/machinelearning, r/webdev, "
        "r/datascience, r/artificial)"
    )
    return "url", [{"url": u} for u in DEFAULT_SUBREDDITS]


def _discover_by_for(mode: str, input_type: str) -> Optional[str]:
    """Return the discover_by param for a mode + input_type combination."""
    if mode == "posts":
        if input_type == "keyword":
            return "keyword"
        return "subreddit_url"
    # Comments and profiles are direct URL collection (no discovery).
    return None


def _collect_comments(
    post_rows: List[Dict[str, Any]], limit: Optional[int],
) -> List[Dict[str, Any]]:
    """Collect comments for scraped posts."""
    urls = [r["post_url"] for r in post_rows if r.get("post_url")]
    if limit:
        urls = urls[:limit]
    if not urls:
        log("  No post URLs available for comments; skipping.")
        return []
    comment_inputs = [{"url": u} for u in urls]
    log(f"\n[+] Collecting comments for {len(comment_inputs)} post(s)...")
    raw = collect(comment_inputs, COMMENTS_DATASET_ID)
    rows = [
        parse_comment(r)
        for r in raw
        if isinstance(r, dict) and not r.get("error")
    ]
    return rows


def main(argv: Optional[List[str]] = None) -> None:
    """Entry point. See build_arg_parser() for CLI options.

    Exit codes: 0 = success, 1 = validation/config/API error.
    """
    global _QUIET
    args = build_arg_parser().parse_args(argv)
    _QUIET = args.quiet

    mode = args.mode
    fmt = args.format
    output_path = args.output or default_output_path(mode, fmt)

    # --- Preconditions -----------------------------------------------
    if not API_KEY:
        print("ERROR: Set your Bright Data API key:")
        print("  Mac/Linux: export BRIGHT_DATA_API_KEY=your-key")
        print("  Windows:   set BRIGHT_DATA_API_KEY=your-key")
        print(
            "\nGet your API key from "
            "https://brightdata.com/cp/setting/users"
        )
        sys.exit(1)

    output_dir = os.path.dirname(output_path) or "."
    if not os.path.isdir(output_dir):
        print(f"ERROR: Output directory does not exist: {output_dir}")
        sys.exit(1)
    if not os.access(output_dir, os.W_OK):
        print(
            f"ERROR: No write permission for output directory: {output_dir}"
        )
        sys.exit(1)

    try:
        input_type, inputs = _load_inputs(args.input, mode)
        if not inputs:
            print("  x No valid inputs found. See README for CSV formats.")
            sys.exit(1)
        log(
            f"  Mode: {mode} | input type: {input_type} "
            f"| inputs: {len(inputs)}"
        )

        # --- Dry run ------------------------------------------------
        if args.dry_run:
            log("\n[dry-run] Validating API key...")
            ok = check_auth()
            if not ok:
                print(
                    "  x API key rejected (401/403). "
                    "Fix BRIGHT_DATA_API_KEY."
                )
                sys.exit(1)
            log("  API key accepted.")
            log(
                f"  Would collect: mode={mode}, input_type={input_type}, "
                f"inputs={len(inputs)}, comments={args.comments}, "
                f"format={fmt}, output={output_path}"
            )
            log("\nDry run OK. Remove --dry-run to collect for real.")
            return

        # --- Collect ------------------------------------------------
        dataset_id = get_dataset_id(mode)
        discover_by = _discover_by_for(mode, input_type)
        fields = get_fields(mode)
        parser_fn = get_parser(mode)
        dedupe_key = {
            "posts": "post_id",
            "comments": "comment_id",
            "profiles": "username",
        }.get(mode, "")

        log(f"\n[2/4] Requesting Bright Data Reddit {mode} data...")
        limit_per_input = args.limit if input_type == "keyword" else None
        raw_records = collect(
            inputs, dataset_id, discover_by, limit_per_input,
        )
        if not raw_records:
            print(
                f"  Warning: No {mode} data returned. "
                f"Check your inputs for typos."
            )
            return

        log(f"\n[3/4] Parsing {len(raw_records)} record(s)...")
        valid = [
            r for r in raw_records
            if isinstance(r, dict) and not r.get("error")
        ]
        parsed_rows = dedupe(
            [parser_fn(r) for r in valid], key=dedupe_key,
        )
        if args.limit:
            parsed_rows = parsed_rows[: args.limit]
        log(
            f"  {len(parsed_rows)} unique {mode} from "
            f"{len(raw_records)} record(s)"
        )

        log(
            f"\n[4/4] Writing {len(parsed_rows)} {mode} to "
            f"{output_path} ({fmt})..."
        )
        write_output(parsed_rows, output_path, fields, fmt)

        # --- Comments (optional, posts mode only) -------------------
        if args.comments and mode == "posts":
            comment_rows = _collect_comments(parsed_rows, args.limit)
            if comment_rows:
                cpath = comments_output_path(output_path)
                write_output(comment_rows, cpath, COMMENT_FIELDS, fmt)
                log(f"  Wrote {len(comment_rows)} comment(s) to {cpath}")

        log(f"\nDone! Output: {output_path}")

    except FileNotFoundError as e:
        print(f"\nERROR: File not found: {e.filename}")
        sys.exit(1)
    except PermissionError as e:
        print(f"\nERROR: Permission denied: {e.filename}")
        sys.exit(1)
    except ValueError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)
    except TimeoutError as e:
        print(f"\nERROR: {e}\n  -> Try again with fewer inputs.")
        sys.exit(1)
    except RuntimeError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)
    except (HTTPError, URLError) as e:
        print(f"\nERROR: Network/API issue: {type(e).__name__}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)


if __name__ == "__main__":
    main()
