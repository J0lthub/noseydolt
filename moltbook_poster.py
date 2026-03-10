"""
NoseyDolt → Moltbook cross-poster
Posts the top daily find from HN/GitHub into m/dolt.
Handles Moltbook's AI verification challenge (obfuscated math puzzle).
"""
import re
import os
import requests

MOLTBOOK_API  = "https://www.moltbook.com/api/v1"
MOLTBOOK_KEY  = os.getenv("MOLTBOOK_API_KEY", "")
SUBMOLT       = "dolt"


def _headers():
    return {
        "Authorization": f"Bearer {MOLTBOOK_KEY}",
        "Content-Type": "application/json",
    }


def _solve_challenge(challenge_text: str) -> str:
    """
    Decode Moltbook's obfuscated math challenge.
    Format: alternating caps, scattered symbols (^[]/-), shattered words.
    e.g. "A] lO^bSt-Er S[wImS aT/ tW]eNn-Tyy mE^tE[rS aNd] SlO/wS bY^ fI[vE"
    Strategy: strip symbols, lowercase, reconstruct, extract numbers and operator.
    """
    # Strip obfuscation chars, lowercase
    clean = re.sub(r'[\[\]^/\\]', '', challenge_text).lower()
    clean = re.sub(r'\s+', ' ', clean).strip()

    # Number word map
    number_words = {
        "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
        "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
        "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
        "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
        "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
        "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
        "eighty": 80, "ninety": 90, "hundred": 100,
    }

    # Extract all numbers (digits or words)
    numbers = []
    # Find digit numbers
    for m in re.finditer(r'\b\d+\.?\d*\b', clean):
        numbers.append(float(m.group()))
    # Find word numbers (handle compound like "twenty five")
    tokens = clean.split()
    i = 0
    word_nums = []
    while i < len(tokens):
        tok = re.sub(r'[^a-z]', '', tokens[i])
        if tok in number_words:
            val = number_words[tok]
            # Check for compound: "twenty five" = 25
            if i + 1 < len(tokens):
                next_tok = re.sub(r'[^a-z]', '', tokens[i+1])
                if next_tok in number_words and number_words[next_tok] < 10:
                    val += number_words[next_tok]
                    i += 1
            word_nums.append(val)
        i += 1

    if not numbers and word_nums:
        numbers = [float(v) for v in word_nums]
    elif word_nums and len(word_nums) >= 2 and not numbers:
        numbers = [float(v) for v in word_nums]

    # Detect operator
    operator = "+"
    if any(w in clean for w in ["slows", "slow", "minus", "subtract", "less", "fewer", "reduces", "decrease"]):
        operator = "-"
    elif any(w in clean for w in ["times", "multiply", "multiplied", "product"]):
        operator = "*"
    elif any(w in clean for w in ["divided", "divides", "splits", "per"]):
        operator = "/"
    elif any(w in clean for w in ["adds", "plus", "gains", "increases", "more", "faster", "speeds"]):
        operator = "+"

    if len(numbers) < 2:
        print(f"[MoltbookPoster] Could not parse numbers from: {challenge_text[:80]}")
        return "0.00"

    a, b = numbers[0], numbers[1]
    if operator == "+":   result = a + b
    elif operator == "-": result = a - b
    elif operator == "*": result = a * b
    elif operator == "/": result = a / b if b != 0 else 0
    else:                 result = a + b

    answer = f"{result:.2f}"
    print(f"[MoltbookPoster] Challenge: '{clean[:60]}' → {a} {operator} {b} = {answer}")
    return answer


def _verify(verification_code: str, answer: str) -> bool:
    """Submit answer to Moltbook verification challenge."""
    try:
        resp = requests.post(f"{MOLTBOOK_API}/verify",
            headers=_headers(),
            json={"verification_code": verification_code, "answer": answer},
            timeout=10)
        data = resp.json()
        if data.get("success"):
            print(f"[MoltbookPoster] Verification passed ✅")
            return True
        else:
            print(f"[MoltbookPoster] Verification failed: {data.get('error')} | hint: {data.get('hint')}")
            return False
    except Exception as e:
        print(f"[MoltbookPoster] Verify error: {e}")
        return False


def post_to_mdolt(title: str, url: str = None, content: str = None) -> bool:
    """
    Post a link or text post to m/dolt.
    Returns True if successfully posted and verified.
    """
    if not MOLTBOOK_KEY:
        print("[MoltbookPoster] No API key — skipping")
        return False

    payload = {
        "submolt_name": SUBMOLT,
        "title": title[:300],
    }
    if url:
        payload["url"]  = url
        payload["type"] = "link"
    if content:
        payload["content"] = content[:40000]

    try:
        resp = requests.post(f"{MOLTBOOK_API}/posts",
            headers=_headers(), json=payload, timeout=10)
        data = resp.json()
    except Exception as e:
        print(f"[MoltbookPoster] Post error: {e}")
        return False

    if not data.get("success"):
        print(f"[MoltbookPoster] Post failed: {data.get('error')}")
        return False

    post = data.get("post", {})
    post_id = post.get("id")

    # Handle verification challenge
    if data.get("verification_required") and post.get("verification"):
        v = post["verification"]
        challenge  = v.get("challenge_text", "")
        v_code     = v.get("verification_code", "")
        answer     = _solve_challenge(challenge)
        verified   = _verify(v_code, answer)
        if not verified:
            print(f"[MoltbookPoster] Post {post_id} created but verification failed — will be hidden")
            return False

    print(f"[MoltbookPoster] ✅ Posted to m/dolt: '{title[:60]}' → {MOLTBOOK_API}/posts/{post_id}")
    return True


def cross_post_top_mentions(mentions: list[dict], max_posts: int = 1) -> int:
    """
    Cross-post the top N mentions from today's scrape into m/dolt.
    Picks highest-relevance HN/GitHub finds only.
    Returns count of successful posts.
    """
    # Only cross-post from HN and GitHub — high signal sources
    eligible = [
        m for m in mentions
        if m.get("platform") in ("hackernews", "github")
        and m.get("relevance", 0) >= 3
        and m.get("url")
        and m.get("title")
    ]

    # Sort by relevance then reach
    eligible.sort(key=lambda m: (m.get("relevance", 0), m.get("potential_reach", 0)), reverse=True)

    posted = 0
    for mention in eligible[:max_posts]:
        platform = mention["platform"].upper()
        title    = mention.get("title") or ""
        url      = mention.get("url") or ""
        kw       = mention.get("keyword_hit") or ""
        reach    = mention.get("potential_reach", 0)

        post_title   = f"[{platform}] {title}"[:300]
        post_content = (
            f"Found by NoseyDolt 🗞️\n\n"
            f"Keyword: {kw}\n"
            f"Estimated reach: {reach:,}\n\n"
            f"Source: {url}"
        )

        success = post_to_mdolt(title=post_title, url=url, content=post_content)
        if success:
            posted += 1

    print(f"[MoltbookPoster] Cross-posted {posted}/{len(eligible[:max_posts])} mentions to m/dolt")
    return posted
