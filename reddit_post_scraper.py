#!/usr/bin/env python3
"""Reddit Post Scraper Tool via Bright Data.

Workflow: Subreddits CSV (URLs) or Keywords CSV -> BD Posts Dataset -> Extract post data -> Output CSV

Usage:
    python reddit_post_scraper.py subreddits.csv output_posts.csv

Or simply:
    python reddit_post_scraper.py

Requires:
    - Python 3.9+
    - Bright Data API key (set BRIGHT_DATA_API_KEY environment variable)
"""

import csv
import json
import os
import re
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

API_KEY = os.environ.get("BRIGHT_DATA_API_KEY", "")

POSTS_DATASET_ID = "gd_lvz8ah06191smkebj4"  # Reddit - Posts

BASE_URL = "https://api.brightdata.com/datasets/v3"

POLL_INTERVAL = 15
POLL_TIMEOUT = 1800

DEFAULT_SUBREDDITS = [
    "https://www.reddit.com/r/python/",
    "https://www.reddit.com/r/machinelearning/",
    "https://www.reddit.com/r/webdev/",
    "https://www.reddit.com/r/datascience/",
    "https://www.reddit.com/r/artificial/",
]


def api_request(method, url, data=None):
    """Make an HTTP request to the Bright Data API."""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode() if data else None
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=180) as resp:
            raw = resp.read().decode()
            if not raw.strip():
                return None
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return raw.strip()
    except HTTPError as e:
        body_text = e.read().decode() if e.fp else ""
        print(f"  HTTP {e.code}: {body_text[:500]}")
        raise
    except URLError as e:
        print(f"  Network error: {e.reason}")
        raise


def read_input_csv(path):
    """Read subreddit URLs or keywords from a CSV file.

    Auto-detects input mode from the header:
    - url/subreddit header -> subreddit URL mode
    - keyword header -> keyword search mode
    """
    entries = []
    mode = "subreddit"
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = [fn.lower().strip() for fn in (reader.fieldnames or [])]

        if "keyword" in fieldnames:
            mode = "keyword"
            for row in reader:
                keyword = (row.get("keyword") or "").strip()
                if not keyword:
                    continue
                num_posts = 50
                for key in ("num_of_posts", "num_posts", "posts", "limit"):
                    if key in row and row[key]:
                        try:
                            num_posts = int(row[key])
                        except ValueError:
                            pass
                        break
                entries.append({"keyword": keyword, "num_of_posts": num_posts})
        else:
            # URL/subreddit mode
            url_key = None
            for candidate in ("url", "subreddit", "subreddit_url"):
                if candidate in fieldnames:
                    url_key = candidate
                    break
            if not url_key and fieldnames:
                url_key = reader.fieldnames[0]

            for row in reader:
                val = (row.get(url_key) or "").strip()
                if not val:
                    continue
                entries.append(val)

    return mode, entries


def normalize_subreddit(raw_value):
    """Normalize a subreddit name or URL to a full Reddit URL."""
    val = raw_value.strip().strip("/")

    if val.startswith("http://") or val.startswith("https://"):
        url = val.rstrip("/") + "/"
        return url

    # Handle r/subreddit or just subreddit name
    if val.startswith("r/"):
        return f"https://www.reddit.com/{val}/"
    return f"https://www.reddit.com/r/{val}/"


def trigger_collection(dataset_id, inputs, discover_by=None):
    """Trigger a Bright Data dataset collection. Returns snapshot_id."""
    url = f"{BASE_URL}/trigger?dataset_id={dataset_id}&notify=false&include_errors=true"
    if discover_by:
        url += f"&type=discover_new&discover_by={discover_by}"
    payload = inputs if isinstance(inputs, list) else [inputs]
    print(f"  Triggering collection with {len(payload)} input(s)...")
    resp = api_request("POST", url, payload)
    if isinstance(resp, dict) and "snapshot_id" in resp:
        return resp["snapshot_id"]
    if isinstance(resp, str):
        return resp
    raise RuntimeError(f"Unexpected trigger response: {resp}")


def poll_until_ready(snapshot_id):
    """Poll Bright Data until the snapshot data is ready for download."""
    url = f"{BASE_URL}/progress/{snapshot_id}"
    start = time.time()
    last_status = None
    while time.time() - start < POLL_TIMEOUT:
        try:
            resp = api_request("GET", url)
        except HTTPError:
            time.sleep(POLL_INTERVAL)
            continue

        status = resp.get("status") if isinstance(resp, dict) else str(resp)
        if status != last_status:
            elapsed = int(time.time() - start)
            print(f"  Status: {status} ({elapsed}s elapsed)")
            last_status = status

        if status == "ready":
            time.sleep(5)
            return
        if status in ("failed", "error", "cancelled"):
            raise RuntimeError(f"Collection failed: {status}. Details: {resp}")

        time.sleep(POLL_INTERVAL)

    raise TimeoutError(f"Collection timed out after {POLL_TIMEOUT}s")


def download_snapshot(snapshot_id, retries=3):
    """Download snapshot results as JSON."""
    url = f"{BASE_URL}/snapshot/{snapshot_id}?format=json"
    for attempt in range(retries):
        print(
            f"  Downloading snapshot {snapshot_id} (attempt {attempt + 1}/{retries})..."
        )
        try:
            result = api_request("GET", url)
        except Exception as e:
            print(f"  Download error: {e}")
            if attempt < retries - 1:
                time.sleep(10)
                continue
            raise

        if isinstance(result, dict) and "snapshot_id" in result:
            if attempt < retries - 1:
                time.sleep(15)
                continue
            raise RuntimeError(f"Snapshot data not available after {retries} attempts")

        if isinstance(result, list):
            return result

        if attempt < retries - 1:
            time.sleep(10)
            continue
        return result

    return None


def parse_count(value):
    """Parse upvote/comment count from various formats to int."""
    if isinstance(value, (int, float)):
        return int(value)
    if not value:
        return 0
    s = str(value).strip().replace(",", "")
    if s.upper().endswith("K"):
        try:
            return int(float(s[:-1]) * 1_000)
        except ValueError:
            pass
    if s.upper().endswith("M"):
        try:
            return int(float(s[:-1]) * 1_000_000)
        except ValueError:
            pass
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def main():
    if not API_KEY:
        print("ERROR: Set your Bright Data API key:")
        print("  Windows:  set BRIGHT_DATA_API_KEY=your-api-key-here")
        print("  Mac/Linux: export BRIGHT_DATA_API_KEY=your-api-key-here")
        print()
        print("Get your API key from: https://brightdata.com/cp/setting/users")
        sys.exit(1)

    input_csv = sys.argv[1] if len(sys.argv) > 1 else None
    output_csv = sys.argv[2] if len(sys.argv) > 2 else "output_posts.csv"

    if input_csv and os.path.exists(input_csv):
        print(f"[1/5] Reading input from {input_csv}")
        mode, entries = read_input_csv(input_csv)
    else:
        print("[1/5] Using default subreddits (no CSV provided)")
        mode = "subreddit"
        entries = DEFAULT_SUBREDDITS

    if mode == "keyword":
        print(f"  Mode: keyword search")
        print(f"  Keywords: {len(entries)}")
        for e in entries:
            print(f"    {e['keyword']} ({e['num_of_posts']} posts)")
    else:
        print(f"  Mode: subreddit scraping")
        print(f"  Subreddits: {len(entries)}")
        for s in entries:
            print(f"    {s}")

    print(f"\n[2/5] Triggering Bright Data Reddit Posts collection...")

    if mode == "keyword":
        snapshot_id = trigger_collection(
            POSTS_DATASET_ID, entries, discover_by="keyword"
        )
    else:
        url_inputs = [{"url": normalize_subreddit(s)} for s in entries]
        snapshot_id = trigger_collection(
            POSTS_DATASET_ID, url_inputs, discover_by="subreddit_url"
        )

    print(f"  Snapshot ID: {snapshot_id}")

    print(f"\n[3/5] Waiting for collection to complete (this may take 2-5 minutes)...")
    poll_until_ready(snapshot_id)
    print(f"  Downloading results...")
    results = download_snapshot(snapshot_id)

    if not results:
        print("  No post data returned. Exiting.")
        return

    valid = [r for r in results if isinstance(r, dict)]
    errors = [r for r in valid if r.get("error")]
    print(
        f"  Got {len(valid)} results ({len(valid) - len(errors)} posts, {len(errors)} errors)"
    )

    print(f"\n[4/5] Processing {len(valid)} posts...")
    rows = []

    for post_data in valid:
        if post_data.get("error"):
            continue

        post_url = post_data.get("url", "") or ""
        post_id = post_data.get("post_id", "") or ""
        title = post_data.get("title", "") or ""
        description = post_data.get("description", "") or ""
        author = post_data.get("user_posted", "") or ""
        subreddit = post_data.get("community_name", "") or ""
        community_members = parse_count(post_data.get("community_members_num", 0))
        num_upvotes = parse_count(post_data.get("num_upvotes", 0))
        num_comments = parse_count(post_data.get("num_comments", 0))
        date_posted = post_data.get("date_posted", "") or ""
        tag = post_data.get("tag", "") or ""

        rows.append(
            {
                "post_url": post_url,
                "post_id": post_id,
                "title": title[:300],
                "description": str(description)[:500],
                "author": author,
                "subreddit": subreddit,
                "community_members": community_members if community_members else "",
                "num_upvotes": num_upvotes if num_upvotes else "",
                "num_comments": num_comments if num_comments else "",
                "date_posted": date_posted,
                "tag": tag,
            }
        )

    print(f"  Processed {len(rows)} posts")

    print(f"\n[5/5] Writing output to {output_csv}...")
    fieldnames = [
        "post_url",
        "post_id",
        "title",
        "description",
        "author",
        "subreddit",
        "community_members",
        "num_upvotes",
        "num_comments",
        "date_posted",
        "tag",
    ]
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nDone! {len(rows)} posts written to {output_csv}")
    print(
        f"  Unique subreddits: {len(set(r['subreddit'] for r in rows if r['subreddit']))}"
    )


if __name__ == "__main__":
    main()
