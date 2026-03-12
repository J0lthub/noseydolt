"""
Lobste.rs Scraper — JSON API, no auth required
https://lobste.rs/s/newest.json / search via https://lobste.rs/search
"""
import requests
from datetime import datetime, timezone

from config import ALL_KEYWORDS, PRIMARY_KEYWORDS, REACH_WEIGHT_UPVOTES, REACH_WEIGHT_COMMENTS

LOBSTERS_NEWEST = "https://lobste.rs/newest.json"
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
    if pos > neg: return 2
    if neg > pos: return 0
    return 1


def fetch(lookback_days: int = 1) -> list[dict]:
    """Fetch recent Lobste.rs stories and filter by keywords locally."""
    import time as _time
    cutoff_ts = _time.time() - (lookback_days * 86400)

    # Fetch pages of newest stories until we hit the cutoff
    seen_ids = set()
    all_stories = []
    for page in range(1, 6):  # max 5 pages = 125 stories
        try:
            resp = requests.get(LOBSTERS_NEWEST, params={"page": page},
                                timeout=10, headers={"User-Agent": "NoseyDolt/1.0"})
            resp.raise_for_status()
            page_stories = resp.json()
            if not page_stories:
                break
            # Stop if oldest story on page is beyond cutoff
            oldest = page_stories[-1].get("created_at", "")
            if oldest:
                try:
                    dt = datetime.fromisoformat(oldest.replace("Z", "+00:00"))
                    if dt.timestamp() < cutoff_ts:
                        all_stories.extend(page_stories)
                        break
                except Exception:
                    pass
            all_stories.extend(page_stories)
            _time.sleep(1)
        except Exception as e:
            print(f"[Lobsters] Error fetching page {page}: {e}")
            break

    results = []
    for item in all_stories:
            uid = f"lobsters:{item.get('short_id', '')}"
            if uid in seen_ids:
                continue

            title   = item.get("title") or ""
            content = item.get("description") or ""
            url_str = item.get("url") or ""
            combined = (title + " " + content + " " + url_str).lower()

            # Check if any keyword matches
            matched_kws = [kw for kw in ALL_KEYWORDS if kw.lower() in combined]
            if not matched_kws:
                continue

            seen_ids.add(uid)

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
