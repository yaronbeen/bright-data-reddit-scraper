#!/usr/bin/env python3
"""Runnable examples for the Bright Data Reddit scraper.

Set your API key before running:
    export BRIGHT_DATA_API_KEY="your-key"

Then run:
    python examples.py
"""

import reddit_scraper as rs


def example_posts_from_subreddits():
    """Scrape posts from a list of subreddits."""
    print("=== Example 1: Posts from subreddits ===\n")
    rs.main(["subreddits.csv", "example_posts.csv"])


def example_posts_by_keyword():
    """Search Reddit for posts matching keywords."""
    print("\n=== Example 2: Keyword search ===\n")
    import os
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False,
    ) as f:
        f.write("keyword,num_of_posts\npython web scraping,10\n")
        tmp = f.name
    try:
        rs.main([tmp, "example_keyword_posts.csv"])
    finally:
        os.unlink(tmp)


def example_posts_with_comments():
    """Scrape posts and also collect their comments."""
    print("\n=== Example 3: Posts + comments ===\n")
    rs.main([
        "subreddits.csv", "example_with_comments.csv",
        "--comments", "--limit", "5",
    ])


def example_json_output():
    """Output as JSON instead of CSV."""
    print("\n=== Example 4: JSON output ===\n")
    rs.main([
        "subreddits.csv", "example_posts.json",
        "--format", "json", "--limit", "10",
    ])


def example_dry_run():
    """Validate inputs without spending credit."""
    print("\n=== Example 5: Dry run (no credit spent) ===\n")
    rs.main(["subreddits.csv", "--dry-run"])


if __name__ == "__main__":
    print("Bright Data Reddit Scraper - Examples")
    print("=" * 40)
    print()
    print("Running dry-run example (no credit spent):\n")
    example_dry_run()
    print()
    print("To run live examples, uncomment the calls below in examples.py")
    print("and make sure BRIGHT_DATA_API_KEY is set.")
    # Uncomment to run live examples:
    # example_posts_from_subreddits()
    # example_posts_by_keyword()
    # example_posts_with_comments()
    # example_json_output()
