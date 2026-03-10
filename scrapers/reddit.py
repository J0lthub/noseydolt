"""
Reddit Scraper — uses PRAW (Python Reddit API Wrapper)
Needs REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET in .env
"""
import praw
from datetime import datetime, timezone

from config import (ALL_KEYWORDS, PRIMARY_KEYWORDS,
                    REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT,
                    REACH_WEIGHT_UPVOTES, REACH_WEIGHT_COMMENTS, REACH_WEIGHT_SHARES)


SEARCH_SUBREDDITS = ["all"]   # search across all of Reddit
POSTS_PER_KEYWORD = 25


def get_reddit():
    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        raise ValueError("Reddit credentials not set. Add REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET to .env")
    return praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent=REDDIT_USER_AGENT,
    )


def compute_reach(subreddit_subscribers: int, upvotes: int, comments: int) -> int:
    base = max(subreddit_subscribers, 1000)
    raw  = base * (1 + (upvotes * REACH_WEIGHT_UPVOTES) + (comments * REACH_WEIGHT_COMMENTS))
    return int(raw)


def classify_keyword(text: str) -> tuple[str, str]:
    text_lower = text.lower()
    hits    = [kw for kw in ALL_KEYWORDS if kw.lower() in text_lower]
    primary = next((kw for kw in PRIMARY_KEYWORDS if kw.lower() in text_lower), hits[0] if hits else "")
    return primary, ",".join(hits)


def score_relevance(submission, combined: str) -> int:
    keyword_count = sum(1 for kw in ALL_KEYWORDS if kw.lower() in combined)
    score = min(keyword_count * 2, 5)
    score += min(int(submission.score / 20), 3)
    if submission.num_comments > 5:
        score = min(score + 1, 10)
    if hasattr(submission, 'subreddit'):
        sub_name = str(submission.subreddit).lower()
        if any(x in sub_name for x in ["programming", "database", "devops", "machinelearning", "artificial"]):
            score = min(score + 1, 10)
    return max(score, 1)


def score_sentiment(text: str) -> str:
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
    """Fetch Reddit mentions for all keywords."""
    try:
        reddit = get_reddit()
    except ValueError as e:
        print(f"[Reddit] Skipping: {e}")
        return []

    seen_ids = set()
    results  = []

    for keyword in ALL_KEYWORDS:
        try:
            submissions = reddit.subreddit("all").search(
                query=keyword,
                sort="new",
                time_filter="day",
                limit=POSTS_PER_KEYWORD,
            )
            for sub in submissions:
                uid = f"reddit:{sub.id}"
                if uid in seen_ids:
                    continue
                seen_ids.add(uid)

                title   = sub.title or ""
                content = sub.selftext or ""
                combined = (title + " " + content).lower()

                if keyword.lower() not in combined:
                    continue

                sub_subs   = sub.subreddit.subscribers if hasattr(sub.subreddit, 'subscribers') else 0
                upvotes    = sub.score or 0
                n_comments = sub.num_comments or 0
                posted_dt  = datetime.fromtimestamp(sub.created_utc, tz=timezone.utc)
                url        = f"https://reddit.com{sub.permalink}"

                kw_primary, kw_all = classify_keyword(combined)
                reach = compute_reach(sub_subs, upvotes, n_comments)

                results.append({
                    "id":               uid,
                    "platform":         "reddit",
                    "post_id":          sub.id,
                    "url":              url,
                    "author":           str(sub.author) if sub.author else "[deleted]",
                    "author_followers": sub_subs,
                    "title":            title[:500],
                    "content":          content[:2000] if content else None,
                    "keyword_hit":      kw_primary,
                    "keyword_hits_all": kw_all,
                    "posted_at":        posted_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "relevance":        score_relevance(sub, combined),
                    "sentiment":        score_sentiment(combined),
                    "likes":            upvotes,
                    "shares":           0,
                    "comments":         n_comments,
                    "upvotes":          upvotes,
                    "potential_reach":  reach,
                    "notes":            f"r/{sub.subreddit} — {upvotes} upvotes, {n_comments} comments",
                })

        except Exception as e:
            print(f"[Reddit] Error on keyword '{keyword}': {e}")
            continue

    print(f"[Reddit] Found {len(results)} mentions across {len(ALL_KEYWORDS)} keywords")
    return results
