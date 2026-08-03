# Reddit Scraper (Python) - via Bright Data

[![tests](https://github.com/yaronbeen/bright-data-reddit-scraper/actions/workflows/tests.yml/badge.svg)](https://github.com/yaronbeen/bright-data-reddit-scraper/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)
![Dependencies](https://img.shields.io/badge/dependencies-none%20(stdlib)-brightgreen)

Extract **Reddit data** - posts, comments, and user profiles - with a single, dependency-free Python script powered by **[Bright Data](https://brightdata.com)**'s maintained Reddit datasets. Public data only; no login or cookies.

- **Zero dependencies** - Python 3.9+ standard library only
- **Three modes** - posts, comments, and user profiles
- **Two input methods** - scrape subreddits by URL or search by keyword
- **CSV or JSON** output (`--format`)
- **Dry-run** mode to validate inputs and your API key without spending credit

> Great for social listening, market research, content analysis, and building Reddit datasets for AI/RAG.

---

## Quickstart

```bash
# 1. Get a Bright Data API key (free tier: 5,000 records/month, no card):
#    https://brightdata.com/cp/setting/users
export BRIGHT_DATA_API_KEY="your-key"

# 2. Run the built-in sample (5 popular subreddits)
python reddit_scraper.py

# 3. Validate your own file first - spends no credit:
python reddit_scraper.py subreddits.csv --dry-run

# 4. Real runs
python reddit_scraper.py subreddits.csv                     # posts -> output_posts.csv
python reddit_scraper.py subreddits.csv --comments          # posts + comments
python reddit_scraper.py --mode comments posts.csv          # comments only
python reddit_scraper.py --mode profiles users.csv out.json --format json
```

No `pip install` required.

---

## Command-line reference

```
python reddit_scraper.py [input] [output] [options]

positional:
  input                Input CSV (subreddit URLs, post URLs, user URLs, or keywords).
                       Omit for built-in sample.
  output               Output file. Default: output_<mode>.csv (or .json)

options:
  --mode {posts,comments,profiles}  What to collect (default: posts)
  --format {csv,json}               Output format (default: csv)
  --comments                        Also collect comments for each post (posts mode only)
  --limit N                         Max rows to write
  --dry-run                         Validate input + API key without collecting (spends no credit)
  --quiet                           Suppress progress output
  --version                         Print version
  -h, --help                        Show help
```

---

## Input and output

### Posts mode (default)

**Input A - Subreddit URLs** (`subreddits.csv`)

```csv
url
https://www.reddit.com/r/python/
https://www.reddit.com/r/machinelearning/
```

You can also use bare names (`python`) or shorthand (`r/python`); the script normalizes them automatically.

**Input B - Keyword search** (`keywords.csv`)

```csv
keyword,num_of_posts
python web scraping,50
data collection API,30
```

| Column | Required | Default | Notes |
|--------|----------|---------|-------|
| `keyword` | Yes | - | Search term |
| `num_of_posts` | No | 50 | Max results per keyword |

**Output fields (posts)**

| Field | Type | Notes |
|-------|------|-------|
| `post_url` | text | Direct link to the post |
| `post_id` | text | Reddit post ID |
| `title` | text | Post title |
| `body` | text | Post body / self-text |
| `author` | text | Username who posted |
| `subreddit` | text | Subreddit name |
| `subscribers` | int | Subreddit subscriber count (or null) |
| `upvotes` | int | Post upvote count (or null) |
| `num_comments` | int | Number of comments (or null) |
| `created_at` | text | When posted (ISO timestamp) |
| `flair` | text | Post flair / tag |

With `--comments`, a second file `<output>_comments.csv` (or `.json`) is written containing comments for each scraped post.

### Comments mode

```bash
python reddit_scraper.py --mode comments posts.csv
```

Input: CSV with `url` column pointing to Reddit post URLs.

```csv
url
https://www.reddit.com/r/python/comments/abc123/my_post/
```

| Field | Type | Notes |
|-------|------|-------|
| `comment_url` | text | Link to the comment |
| `comment_id` | text | Comment ID |
| `post_url` | text | Link to the parent post |
| `author` | text | Commenter username |
| `body` | text | Comment text |
| `score` | int | Comment score (or null) |
| `created_at` | text | When commented |
| `subreddit` | text | Subreddit name |

### Profiles mode

```bash
python reddit_scraper.py --mode profiles users.csv
```

Input: CSV with `url` column, bare usernames, or `u/` shorthand.

```csv
url
https://www.reddit.com/user/spez/
u/gallowboob
```

| Field | Type | Notes |
|-------|------|-------|
| `profile_url` | text | Link to user profile |
| `username` | text | Username |
| `display_name` | text | Display name |
| `total_karma` | int | Total karma (or null) |
| `post_karma` | int | Post / link karma (or null) |
| `comment_karma` | int | Comment karma (or null) |
| `created_at` | text | Account creation date |
| `description` | text | User bio |

---

## How it works

The script posts to Bright Data's synchronous **`/scrape`** endpoint:

```
POST /datasets/v3/scrape?dataset_id=<ID>&notify=false&include_errors=true
Body: {"input": [ ... ]}
```

Three Bright Data datasets are used:

| Mode | Dataset ID | Input |
|------|-----------|-------|
| Posts | `gd_lvz8ah06191smkebj4` | Subreddit URLs or keywords |
| Comments | `gd_lvzdpsdlw09j6t702` | Post URLs |
| Profiles | `gd_mgnh0p8w16o65lmhp` | User profile URLs |

- **URL collection** returns data **synchronously** as NDJSON (usually under a minute).
- **Discovery** (subreddit scraping, keyword search) is heavier, so Bright Data returns a `snapshot_id` (HTTP 202). The script then polls `GET /datasets/v3/progress/{snapshot_id}` until `ready` and downloads `GET /datasets/v3/snapshot/{snapshot_id}?format=json`. This fallback is automatic.

Field names are mapped defensively: `user_posted` becomes `author`, `community_name` becomes `subreddit`, `community_members_num` becomes `subscribers`, and so on. A fixture file (`tests/fixtures/reddit_post.json`) is committed so `parse_post()` is verified against representative data, not guesses.

---

## Use cases

- **Social listening** - track mentions, sentiment, and discussions across subreddits.
- **Market research** - understand what real users say about your product or competitors.
- **Content analysis** - find trending topics, popular posts, and engagement patterns.
- **AI / RAG datasets** - export Reddit threads as JSON for retrieval or LLM fine-tuning.
- **Community monitoring** - track subreddit growth, top contributors, and posting frequency.

---

## Build a custom Reddit scraper with Scraper Studio

Need fields this scraper does not include, or want to scrape a Reddit page layout not covered here? **[Scraper Studio](https://docs.brightdata.com/datasets/scraper-studio/ai-agent)** lets you build a custom Reddit scraper with plain-English prompts:

1. Describe the data you want ("scrape top 100 posts from r/technology with title, upvotes, author karma, and all top-level comments")
2. Scraper Studio generates a self-healing scraper with your exact schema
3. Proxies, unblocking, and CAPTCHA handling are built in

No code required. Useful when you need a non-standard output schema or want to combine Reddit data with other sources in a single pipeline.

---

## Tests

```bash
pip install pytest
pytest -m unit    # pure helpers, no API key needed (runs in CI)
pytest -m e2e     # live Bright Data API (requires BRIGHT_DATA_API_KEY, spends a little credit)
```

The unit suite covers all parsing helpers, CSV reading, URL normalization, response interpretation, and output writing with zero network calls.

---

## Cost

Bright Data **Web Scraper API** pricing (from [brightdata.com/pricing/web-scraper](https://brightdata.com/pricing/web-scraper), verified at time of writing):

| Plan | Price | Notes |
|------|-------|-------|
| Free tier | **5,000 records/month** | No credit card required |
| Pay as you go | **$1.5 / 1k records** | Pay only for successfully delivered records |
| Scale | **$499/mo** | 384k records included, then $1.3 / 1k |

You pay per **delivered record**, so the built-in 5-subreddit sample costs only a few cents. Pricing changes; always confirm on the pricing page.

---

## Bright Data vs. Apify for Reddit - an honest comparison

The most-used Reddit scraper on the Apify store is [`trudax/reddit-scraper-lite`](https://apify.com/trudax/reddit-scraper-lite) (**33K users**, 4.6 stars, community-maintained by "Trudax"). Here is a straight comparison, verified from both vendors' live pages at time of writing.

| | Bright Data (this repo) | Apify `trudax/reddit-scraper-lite` |
|---|---|---|
| **Maintained by** | Bright Data (the vendor) | Trudax (third-party dev), community-maintained |
| **Base price** | **$1.5 / 1k records** (down to $1.3/1k on Scale) | Apify platform pricing + compute units |
| **Free tier** | 5,000 records / month, no card | Yes (Apify free plan) |
| **Billing model** | Flat per delivered record; pay only for success | Per compute unit consumed |
| **Posts** | Yes (from subreddits or keyword search) | Yes |
| **Comments** | Yes (separate dataset, `gd_lvzdpsdlw09j6t702`) | Yes |
| **User profiles** | Yes (separate dataset, `gd_mgnh0p8w16o65lmhp`) | Limited |
| **Data scope** | Three dedicated datasets (posts, comments, profiles) | Single actor covering posts and comments |
| **Infrastructure** | Vendor-managed proxies, unblocking, CAPTCHA handling | Apify platform proxies |
| **Ecosystem** | Scrapers across 450+ domains | Large actor store + Make/Zapier integrations |

**The honest takeaway:** Base pricing is similar across both platforms. The real differences are:

- **Choose Bright Data** if you want simple, predictable per-record billing from vendor-maintained scrapers with dedicated datasets for posts, comments, and profiles, and pay-only-for-success billing.
- **Choose Apify** if you prefer a single actor covering multiple Reddit data types, or you already use Apify's ecosystem integrations (Make, Zapier).

**Verify before deciding:** [brightdata.com/pricing](https://brightdata.com/pricing) and [apify.com/pricing](https://apify.com/pricing). Prices and features change often.

---

## License

[MIT](./LICENSE) - free to use, modify, and distribute.

Built by the team at **[Bright Data](https://brightdata.com)**. An open, runnable example of the Bright Data Reddit Scraper API.
