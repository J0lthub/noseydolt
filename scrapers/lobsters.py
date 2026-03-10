"""
Lobste.rs Scraper — JSON API, no auth required
https://lobste.rs/s/newest.json / search via https://lobste.rs/search
"""
import requests
from datetime import datetime, timezone

from config import ALL_KEYWORDS, PRIMARY_KEYWORDS, REACH_WEIGHT_UPVOTES, REACH_WEIGHT_COMMENTS

LOBSTERS_SEARCH = "https://lobste.rs/search.json"
LOBSTERS_BASE   = "https://lobste.rs"
LOBSTERS_AVG_VISITORS = 50_000  # rough daily active


def classify_keyword(text: str) -> tuple[str, str]:
    text_lower = text.lower()
    hits    = [kw for kw in ALL_KEYWORDS if kw.lower() in text_lower]
    primary = next((kw for kw in PRIMARY_KEYWORDS if kw.lower() in text_lower), hits[0] if hits else "")
    return primary, ",".join(hits)


def score_relevance(item: dict, combined: str) -> int:
    keyword_count = sum(1 for kw in ALL_KEYWORDS if kw.lower() in combined)
    score = min(keyword_count * 2, 5)
    score += min(int((item.get("score") or 0) / 10), 3)
    if (item.get("comment_count") or 0) > 5:
        score = min(score + 1, 10)
    return max(score, 1)


def score_sentiment(text: str) -> str:
    text_lower = text.lower()
    positive = ["great","love","amazing","excellent","awesome","useful","impressive",
                "fast","reliable","elegant","solved","works","recommend","cool","nice"]
    negative = ["slow","broken","bug","issue","problem","terrible","awful","hate",
                "frustrating","failed","error","crash","bad","worse"]
    pos = sum(1 for w in positive if w in text_lower)
    neg = sum(1 for w in negative if w in text_lower)
    if pos > neg: return "positive"
    if neg > pos: return "negative"
    return "neutral"


def fetch(lookback_days: int = 1) -> list[dict]:
    """Fetch Lobste.rs mentions for all keywords."""
    seen_ids = set()
    results  = []

    for keyword in ALL_KEYWORDS:
        try:
            resp = requests.get(LOBSTERS_SEARCH, params={
                "q":      keyword,
                "what":   "stories",
                "order":  "newest",
                "page":   1,
            }, timeout=10, headers={"User-Agent": "NoseyDolt/1.0"})
            resp.raise_for_status()
            stories = resp.json()
        except Exception as e:
            print(f"[Lobsters] Error fetching '{keyword}': {e}")
            continue

        for item in stories:
            uid = f"lobsters:{item.get('short_id', '')}"
            if uid in seen_ids:
                continue
            seen_ids.add(uid)

            title   = item.get("title") or ""
            content = item.get("description") or ""
            combined = (title + " " + content).lower()

            if keyword.lower() not in combined:
                continue

            score      = item.get("score") or 0
            n_comments = item.get("comment_count") or 0
            author     = item.get("submitter_user") or ""
            created_at = item.get("created_at") or datetime.now(timezone.utc).isoformat()
            url        = item.get("url") or f"{LOBSTERS_BASE}/s/{item.get('short_id')}"

            kw_primary, kw_all = classify_keyword(combined)
            reach = min(int(LOBSTERS_AVG_VISITORS * (1 + score * REACH_WEIGHT_UPVOTES + n_comments * REACH_WEIGHT_COMMENTS)), 500_000)

            results.append({
                "id":               uid,
                "platform":         "lobsters",
                "post_id":          item.get("short_id", ""),
                "url":              url,
                "author":           author,
                "author_followers": 0,
                "title":            title[:500],
                "content":          content[:2000] if content else None,
                "keyword_hit":      kw_primary,
                "keyword_hits_all": kw_all,
                "posted_at":        created_at[:19].replace("T", " "),
                "relevance":        score_relevance(item, combined),
                "sentiment":        score_sentiment(combined),
                "likes":            score,
                "shares":           0,
                "comments":         n_comments,
                "upvotes":          score,
                "potential_reach":  reach,
                "notes":            f"Lobsters: {score} pts, {n_comments} comments",
            })

    print(f"[Lobsters] Found {len(results)} mentions across {len(ALL_KEYWORDS)} keywords")
    return results
