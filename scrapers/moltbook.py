"""
Moltbook Scraper — semantic search API
https://www.moltbook.com/api/v1/search
Searches for Dolt/agentic memory discourse using natural language queries.
"""
import requests
import os
from datetime import datetime, timezone

from config import PRIMARY_KEYWORDS

MOLTBOOK_API  = "https://www.moltbook.com/api/v1"
MOLTBOOK_KEY  = os.getenv("MOLTBOOK_API_KEY", "")

# Semantic search queries — natural language, not just keywords
SEMANTIC_QUERIES = [
    "Dolt version controlled database",
    "DoltHub git for data",
    "agentic memory versioning",
    "AI agent database branching",
    "EU AI Act compliance audit trail",
    "Steve Yegge Gastown Wasteland Beads",
    "versioned database SQL",
]


def _headers():
    return {
        "Authorization": f"Bearer {MOLTBOOK_KEY}",
        "Content-Type": "application/json",
    }


def classify_keyword(text: str) -> tuple[str, str]:
    text_lower = text.lower()
    hits    = [kw for kw in PRIMARY_KEYWORDS if kw.lower() in text_lower]
    primary = hits[0] if hits else "moltbook"
    return primary, ",".join(hits) if hits else "moltbook"


def score_sentiment(text: str) -> str:
    text_lower = text.lower()
    positive = ["great","love","amazing","excellent","awesome","useful","impressive",
                "solved","works","recommend","cool","nice","helpful"]
    negative = ["slow","broken","bug","issue","problem","terrible","awful","hate",
                "frustrating","failed","error","crash","bad","worse"]
    pos = sum(1 for w in positive if w in text_lower)
    neg = sum(1 for w in negative if w in text_lower)
    if pos > neg: return "positive"
    if neg > pos: return "negative"
    return "neutral"


def fetch(lookback_days: int = 1) -> list[dict]:
    """Search Moltbook using semantic queries and return normalized mention dicts."""
    if not MOLTBOOK_KEY:
        print("[Moltbook] No API key — skipping")
        return []

    seen_ids = set()
    results  = []

    for query in SEMANTIC_QUERIES:
        try:
            resp = requests.get(f"{MOLTBOOK_API}/search", params={
                "q":     query,
                "type":  "all",
                "limit": 20,
            }, headers=_headers(), timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[Moltbook] Search error for '{query}': {e}")
            continue

        for item in data.get("results", []):
            item_id = item.get("id", "")
            uid     = f"moltbook:{item_id}"
            if uid in seen_ids:
                continue
            seen_ids.add(uid)

            item_type = item.get("type", "post")  # post or comment
            title     = item.get("title") or ""
            content   = item.get("content") or ""
            combined  = (title + " " + content).lower()
            similarity = float(item.get("similarity") or 0)

            # Only keep high-confidence semantic matches
            if similarity < 0.5:
                continue

            author      = item.get("author", {}).get("name") or ""
            upvotes     = item.get("upvotes") or 0
            submolt     = item.get("submolt", {}).get("name") or "general"
            post_id     = item.get("post_id") or item_id
            created_at  = item.get("created_at", "")[:19].replace("T", " ")
            url         = f"https://www.moltbook.com/p/{post_id}"

            kw_primary, kw_all = classify_keyword(combined)
            reach = max(upvotes * 200, 500)  # Moltbook is new, modest reach estimates

            results.append({
                "id":               uid,
                "platform":         "moltbook",
                "post_id":          post_id,
                "url":              url,
                "author":           author,
                "author_followers": 0,
                "title":            (f"[{item_type}] {title}" if title else f"[{item_type}]")[:500],
                "content":          content[:2000] if content else None,
                "keyword_hit":      kw_primary,
                "keyword_hits_all": kw_all,
                "posted_at":        created_at,
                "relevance":        min(int(similarity * 10), 10),
                "sentiment":        score_sentiment(combined),
                "likes":            upvotes,
                "shares":           0,
                "comments":         0,
                "upvotes":          upvotes,
                "potential_reach":  reach,
                "notes":            f"Moltbook {item_type} in m/{submolt} — similarity {similarity:.2f}",
            })

    print(f"[Moltbook] Found {len(results)} mentions across {len(SEMANTIC_QUERIES)} queries")
    return results
