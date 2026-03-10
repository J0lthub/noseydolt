"""
Stack Overflow Scraper — Stack Exchange API v2.3 (free, no key needed for read)
https://api.stackexchange.com/docs
"""
import requests
from datetime import datetime, timezone
import time

from config import ALL_KEYWORDS, PRIMARY_KEYWORDS, REACH_WEIGHT_UPVOTES, REACH_WEIGHT_COMMENTS

SO_API_BASE   = "https://api.stackexchange.com/2.3"
SO_AVG_VIEWS  = 10_000  # default monthly views for an average SO question


def classify_keyword(text: str) -> tuple[str, str]:
    text_lower = text.lower()
    hits    = [kw for kw in ALL_KEYWORDS if kw.lower() in text_lower]
    primary = next((kw for kw in PRIMARY_KEYWORDS if kw.lower() in text_lower), hits[0] if hits else "")
    return primary, ",".join(hits)


def score_relevance(item: dict, combined: str) -> int:
    keyword_count = sum(1 for kw in ALL_KEYWORDS if kw.lower() in combined)
    score  = min(keyword_count * 2, 5)
    score += min(int((item.get("score") or 0) / 5), 3)
    if (item.get("answer_count") or 0) > 2:
        score = min(score + 1, 10)
    if item.get("is_answered"):
        score = min(score + 1, 10)
    return max(score, 1)


def score_sentiment(text: str) -> str:
    text_lower = text.lower()
    positive = ["great","love","amazing","excellent","awesome","useful","impressive",
                "solved","works","recommend","cool","nice","helpful"]
    negative = ["slow","broken","bug","issue","problem","terrible","awful","hate",
                "frustrating","failed","error","crash","bad","worse","doesn't work"]
    pos = sum(1 for w in positive if w in text_lower)
    neg = sum(1 for w in negative if w in text_lower)
    if pos > neg: return "positive"
    if neg > pos: return "negative"
    return "neutral"


def fetch(lookback_days: int = 1) -> list[dict]:
    """Fetch Stack Overflow questions mentioning keywords from the last N days."""
    cutoff_ts = int(time.time()) - (lookback_days * 86400)
    seen_ids  = set()
    results   = []

    for keyword in ALL_KEYWORDS:
        try:
            resp = requests.get(f"{SO_API_BASE}/search/advanced", params={
                "q":        keyword,
                "site":     "stackoverflow",
                "sort":     "creation",
                "order":    "desc",
                "fromdate": cutoff_ts,
                "pagesize": 25,
                "filter":   "!9_bDE(fI5",  # include body
            }, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[StackOverflow] Error fetching '{keyword}': {e}")
            continue

        for item in data.get("items", []):
            q_id = str(item.get("question_id", ""))
            uid  = f"stackoverflow:{q_id}"

            if uid in seen_ids:
                continue
            seen_ids.add(uid)

            title   = item.get("title") or ""
            content = item.get("body") or ""
            tags    = " ".join(item.get("tags") or [])
            combined = (title + " " + content + " " + tags).lower()

            if keyword.lower() not in combined:
                continue

            score      = item.get("score") or 0
            n_answers  = item.get("answer_count") or 0
            views      = item.get("view_count") or SO_AVG_VIEWS
            author     = item.get("owner", {}).get("display_name") or ""
            created_ts = item.get("creation_date") or 0
            created_at = datetime.fromtimestamp(created_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if created_ts else ""
            url        = item.get("link") or f"https://stackoverflow.com/q/{q_id}"

            kw_primary, kw_all = classify_keyword(combined)
            reach = min(int(views * (1 + score * REACH_WEIGHT_UPVOTES + n_answers * REACH_WEIGHT_COMMENTS)), 1_000_000)

            results.append({
                "id":               uid,
                "platform":         "stackoverflow",
                "post_id":          q_id,
                "url":              url,
                "author":           author,
                "author_followers": 0,
                "title":            title[:500],
                "content":          content[:2000] if content else None,
                "keyword_hit":      kw_primary,
                "keyword_hits_all": kw_all,
                "posted_at":        created_at,
                "relevance":        score_relevance(item, combined),
                "sentiment":        score_sentiment(combined),
                "likes":            score,
                "shares":           0,
                "comments":         n_answers,
                "upvotes":          score,
                "potential_reach":  reach,
                "notes":            f"SO: score {score}, {n_answers} answers, {views:,} views",
            })

        # Respect SO rate limits — 30 req/s without key, be polite
        time.sleep(0.1)

    print(f"[StackOverflow] Found {len(results)} mentions across {len(ALL_KEYWORDS)} keywords")
    return results
