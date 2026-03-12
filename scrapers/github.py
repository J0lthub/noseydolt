"""
GitHub Search Scraper — GitHub REST API v3 (free public search, no auth needed)
Searches: repositories, issues, discussions mentioning keywords
Rate limit: 10 req/min unauthenticated. Set GITHUB_TOKEN in .env for 30 req/min.
https://docs.github.com/en/rest/search
"""
import requests
import os
import time
from datetime import datetime, timezone, timedelta

from config import ALL_KEYWORDS, PRIMARY_KEYWORDS

GH_API_BASE  = "https://api.github.com/search"
GH_TOKEN     = os.getenv("GITHUB_TOKEN", "")

# GitHub search is noisy — only use primary + high-signal secondary keywords
GH_KEYWORDS = [
    "Dolt", "DoltHub", "DoltGres", "dolthub.com",
    "Steve Yegge", "Yegge",
    "go-mysql-server",
    "agentic memory",
]


def _headers():
    h = {"Accept": "application/vnd.github+json", "User-Agent": "NoseyDolt/1.0"}
    if GH_TOKEN:
        h["Authorization"] = f"Bearer {GH_TOKEN}"
    return h


def classify_keyword(text: str) -> tuple[str, str]:
    text_lower = text.lower()
    hits    = [kw for kw in ALL_KEYWORDS if kw.lower() in text_lower]
    primary = next((kw for kw in PRIMARY_KEYWORDS if kw.lower() in text_lower), hits[0] if hits else "")
    return primary, ",".join(hits)


def score_sentiment(text: str) -> str:
    text_lower = text.lower()
    positive = ["great","love","amazing","excellent","awesome","useful","impressive",
                "solved","works","recommend","cool","nice","helpful","integrat"]
    negative = ["slow","broken","bug","issue","problem","terrible","awful","hate",
                "frustrating","failed","error","crash","bad","worse","doesn't work"]
    pos = sum(1 for w in positive if w in text_lower)
    neg = sum(1 for w in negative if w in text_lower)
    if pos > neg: return 2
    if neg > pos: return 0
    return 1


def _search_issues(keyword: str, since: str) -> list[dict]:
    """Search issues and PRs."""
    results = []
    try:
        resp = requests.get(f"{GH_API_BASE}/issues", params={
            "q":       f'"{keyword}" created:>{since}',
            "sort":    "created",
            "order":   "desc",
            "per_page": 20,
        }, headers=_headers(), timeout=10)

        if resp.status_code == 403:
            reset_ts = resp.headers.get("X-RateLimit-Reset")
            if reset_ts:
                wait = max(int(reset_ts) - int(time.time()) + 2, 5)
                wait = min(wait, 15)  # cap at 15s — don't blow the cron budget
                print(f"[GitHub] Rate limited, backing off {wait}s")
                time.sleep(wait)
            else:
                print(f"[GitHub] Rate limited (no reset header), skipping keyword")
            return []
        resp.raise_for_status()

        for item in resp.json().get("items", []):
            title   = item.get("title") or ""
            content = item.get("body") or ""
            combined = (title + " " + content).lower()

            if keyword.lower() not in combined:
                continue

            issue_id  = str(item.get("id", ""))
            post_id   = f"issue-{item.get('number', '')}"
            repo      = item.get("repository_url", "").replace("https://api.github.com/repos/", "")
            url       = item.get("html_url") or ""
            author    = item.get("user", {}).get("login") or ""
            comments  = item.get("comments") or 0
            reactions = item.get("reactions", {}).get("total_count") or 0
            created   = item.get("created_at", "")[:19].replace("T", " ")

            kw_primary, kw_all = classify_keyword(combined)
            reach = max(reactions * 50 + comments * 100, 500)

            results.append({
                "id":               f"github:{issue_id}",
                "platform":         "github",
                "post_id":          post_id,
                "url":              url,
                "author":           author,
                "author_followers": 0,
                "title":            f"[{repo}] {title}"[:500],
                "content":          content[:2000] if content else None,
                "keyword_hit":      kw_primary,
                "keyword_hits_all": kw_all,
                "posted_at":        created,
                "relevance":        min(len([kw for kw in ALL_KEYWORDS if kw.lower() in combined]) * 2 + min(reactions, 3), 10),
                "sentiment":        score_sentiment(combined),
                "likes":            reactions,
                "shares":           0,
                "comments":         comments,
                "upvotes":          reactions,
                "potential_reach":  reach,
                "notes":            f"GitHub issue/PR in {repo}: {reactions} reactions, {comments} comments",
            })
    except Exception as e:
        print(f"[GitHub] Issue search error for '{keyword}': {e}")

    return results


def fetch(lookback_days: int = 1) -> list[dict]:
    """Fetch GitHub mentions for high-signal keywords."""
    since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    seen_ids = set()
    results  = []

    for keyword in GH_KEYWORDS:
        issues = _search_issues(keyword, since)
        for r in issues:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                results.append(r)
        # Rate limiting: 6s unauthenticated (10/min), 2s with token (30/min)
        time.sleep(2 if GH_TOKEN else 6)

    print(f"[GitHub] Found {len(results)} mentions across {len(GH_KEYWORDS)} keywords")
    return results
