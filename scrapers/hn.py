"""
HN Scraper — uses Algolia HN Search API (free, no auth required)
https://hn.algolia.com/api
"""
import requests
import hashlib
from datetime import datetime, timezone

from config import ALL_KEYWORDS, PRIMARY_KEYWORDS, REACH_WEIGHT_UPVOTES, REACH_WEIGHT_COMMENTS

HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
HN_BASE_URL   = "https://news.ycombinator.com"


def compute_reach(author_followers: int, shares: int, likes: int, comments: int, upvotes: int) -> int:
    """HN-specific reach: upvotes drive algorithmic distribution, cap at 500K (approx frontpage)."""
    base = max(author_followers, 5000)  # HN has no followers; use HN avg visitor baseline
    raw = base * (1 + (upvotes * REACH_WEIGHT_UPVOTES) + (comments * REACH_WEIGHT_COMMENTS))
    return min(int(raw), 500_000)


def classify_keyword(text: str) -> tuple[str, str]:
    """Returns (primary_keyword_hit, all_keywords_csv)."""
    text_lower = text.lower()
    hits = [kw for kw in ALL_KEYWORDS if kw.lower() in text_lower]
    primary = next((kw for kw in PRIMARY_KEYWORDS if kw.lower() in text_lower), hits[0] if hits else "")
    return primary, ",".join(hits)


def score_relevance(item: dict) -> int:
    """1-10 relevance score based on points, comments, and keyword density."""
    points   = item.get("points") or 0
    n_comments = item.get("num_comments") or 0
    title    = (item.get("title") or "").lower()
    story_text = (item.get("story_text") or "").lower()
    combined = title + " " + story_text

    keyword_count = sum(1 for kw in ALL_KEYWORDS if kw.lower() in combined)
    score = min(keyword_count * 2, 5)  # up to 5 for keyword density
    if points > 100: score = min(score + 3, 10)
    elif points > 20: score = min(score + 2, 10)
    elif points > 5: score = min(score + 1, 10)
    if n_comments > 10: score = min(score + 1, 10)
    return max(score, 1)


def score_sentiment(text: str) -> str:
    """Naive keyword-based sentiment."""
    text_lower = text.lower()
    positive_words = ["great", "love", "amazing", "excellent", "awesome", "useful", "impressive",
                      "fast", "reliable", "elegant", "solved", "works", "recommend", "cool", "nice"]
    negative_words = ["slow", "broken", "bug", "issue", "problem", "terrible", "awful", "hate",
                      "frustrating", "doesn't work", "failed", "error", "crash", "bad", "worse"]
    pos = sum(1 for w in positive_words if w in text_lower)
    neg = sum(1 for w in negative_words if w in text_lower)
    if pos > neg: return "positive"
    if neg > pos: return "negative"
    return "neutral"


def fetch(lookback_days: int = 1) -> list[dict]:
    """Fetch HN mentions for all keywords from the last 24 hours only."""
    import time
    cutoff_ts = int(time.time()) - (lookback_days * 86400)

    seen_ids = set()
    results  = []

    for keyword in ALL_KEYWORDS:
        try:
            resp = requests.get(HN_SEARCH_URL, params={
                "query":         keyword,
                "tags":          "(story,comment)",
                "hitsPerPage":   50,
                "numericFilters": f"created_at_i>{cutoff_ts}",
            }, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[HN] Error fetching '{keyword}': {e}")
            continue

        for hit in data.get("hits", []):
            object_id = hit.get("objectID", "")
            post_id   = str(object_id)
            uid       = f"hackernews:{post_id}"

            if uid in seen_ids:
                continue
            seen_ids.add(uid)

            # Filter noise: must contain keyword in title or text
            title   = hit.get("title") or hit.get("comment_text") or ""
            content = hit.get("story_text") or hit.get("comment_text") or ""
            combined = (title + " " + content).lower()
            if keyword.lower() not in combined:
                continue

            points     = hit.get("points") or 0
            n_comments = hit.get("num_comments") or 0
            author     = hit.get("author") or ""
            created_at = hit.get("created_at") or datetime.now(timezone.utc).isoformat()
            url        = hit.get("url") or f"{HN_BASE_URL}/item?id={post_id}"

            kw_primary, kw_all = classify_keyword(combined)
            reach = compute_reach(0, 0, points, n_comments, points)

            results.append({
                "id":               uid,
                "platform":         "hackernews",
                "post_id":          post_id,
                "url":              url,
                "author":           author,
                "author_followers": 0,
                "title":            title[:500] if title else None,
                "content":          content[:2000] if content else None,
                "keyword_hit":      kw_primary,
                "keyword_hits_all": kw_all,
                "posted_at":        created_at[:19].replace("T", " "),
                "relevance":        score_relevance(hit),
                "sentiment":        score_sentiment(combined),
                "likes":            points,
                "shares":           0,
                "comments":         n_comments,
                "upvotes":          points,
                "potential_reach":  reach,
                "notes":            f"HN {hit.get('type','story')}: {points} pts, {n_comments} comments",
            })

    print(f"[HN] Found {len(results)} mentions across {len(ALL_KEYWORDS)} keywords")
    return results
