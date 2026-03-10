#!/usr/bin/env python3
"""
NoseyDolt — Daily Social Listener
Runs on nosey/work branch. Never touches main.

Usage:
    python run.py
"""
import sys
import subprocess
from datetime import date, datetime

import db
from scrapers import hn, reddit, lobsters, stackoverflow, github
from config import DOLT_REPO_PATH, DOLT_BRANCH, PLATFORMS_ENABLED

def ensure_branch():
    """Make sure we're on the right branch before doing anything."""
    result = subprocess.run(
        ["dolt", "branch", "--show-current"],
        cwd=DOLT_REPO_PATH, capture_output=True, text=True
    )
    current = result.stdout.strip()
    if current != DOLT_BRANCH:
        subprocess.run(["dolt", "checkout", DOLT_BRANCH], cwd=DOLT_REPO_PATH)
        print(f"[run] Switched to branch: {DOLT_BRANCH}")
    else:
        print(f"[run] On branch: {current}")


def build_report(mentions: list[dict], new_count: int, run_date: date) -> str:
    """Build NoseyDolt's daily digest report."""
    platforms_used = list(set(m["platform"] for m in mentions))

    top = sorted(mentions, key=lambda m: m.get("potential_reach", 0), reverse=True)[:5]

    positive = [m for m in mentions if m.get("sentiment") == "positive"]
    negative = [m for m in mentions if m.get("sentiment") == "negative"]
    neutral  = [m for m in mentions if m.get("sentiment") == "neutral"]

    by_platform = {}
    for m in mentions:
        by_platform.setdefault(m["platform"], []).append(m)

    platform_summary = "  ".join(f"{p.upper()}: {len(v)}" for p, v in sorted(by_platform.items()))

    lines = [
        f"🗞️ NoseyDolt Daily — {run_date.strftime('%B %d, %Y')}",
        "",
        f"📊 Stats",
        f"  Total mentions: {len(mentions)} ({new_count} new)",
        f"  Platforms: {', '.join(platforms_used)}",
        f"  {platform_summary}",
        f"  Sentiment: ✅ {len(positive)} positive  ⚠️ {len(negative)} negative  ➖ {len(neutral)} neutral",
        "",
        "🔥 Top Mentions by Reach",
    ]

    for m in top:
        reach = m.get("potential_reach", 0)
        reach_str = f"{reach:,}"
        title = (m.get("title") or m.get("content") or "")[:80]
        lines.append(f"  [{m['platform'].upper()}] {title}")
        lines.append(f"    ↳ reach ~{reach_str} · {m.get('keyword_hit')} · {m.get('sentiment')}")
        lines.append(f"    {m['url']}")
        lines.append("")

    if negative:
        lines.append("⚠️ Negative Mentions (worth reading)")
        for m in negative[:3]:
            title = (m.get("title") or m.get("content") or "")[:80]
            lines.append(f"  [{m['platform'].upper()}] {title}")
            lines.append(f"    {m['url']}")
        lines.append("")

    lines += [
        "---",
        f"Branch: {DOLT_BRANCH} · Review and merge when ready.",
    ]

    return "\n".join(lines)


def main():
    print(f"\n{'='*50}")
    print(f"NoseyDolt starting — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")

    ensure_branch()

    started_at = datetime.now()
    today      = date.today()
    all_mentions  = []
    platforms_run = []
    error_log     = []

    # --- HN ---
    if "hackernews" in PLATFORMS_ENABLED:
        try:
            hn_results = hn.fetch()
            all_mentions.extend(hn_results)
            platforms_run.append("hackernews")
        except Exception as e:
            print(f"[run] HN error: {e}")
            error_log.append(f"HN: {e}")

    # --- Reddit ---
    if "reddit" in PLATFORMS_ENABLED:
        try:
            reddit_results = reddit.fetch()
            all_mentions.extend(reddit_results)
            platforms_run.append("reddit")
        except Exception as e:
            print(f"[run] Reddit error: {e}")
            error_log.append(f"Reddit: {e}")

    # --- Lobste.rs ---
    if "lobsters" in PLATFORMS_ENABLED:
        try:
            lobsters_results = lobsters.fetch()
            all_mentions.extend(lobsters_results)
            platforms_run.append("lobsters")
        except Exception as e:
            print(f"[run] Lobsters error: {e}")
            error_log.append(f"Lobsters: {e}")

    # --- Stack Overflow ---
    if "stackoverflow" in PLATFORMS_ENABLED:
        try:
            so_results = stackoverflow.fetch()
            all_mentions.extend(so_results)
            platforms_run.append("stackoverflow")
        except Exception as e:
            print(f"[run] StackOverflow error: {e}")
            error_log.append(f"StackOverflow: {e}")

    # --- GitHub ---
    if "github" in PLATFORMS_ENABLED:
        try:
            gh_results = github.fetch()
            all_mentions.extend(gh_results)
            platforms_run.append("github")
        except Exception as e:
            print(f"[run] GitHub error: {e}")
            error_log.append(f"GitHub: {e}")

    # --- Write to Dolt ---
    new_count = db.write_mentions(all_mentions)
    db.write_keyword_triggers(all_mentions)

    finished_at = datetime.now()
    status = "success" if not error_log else "partial"

    db.log_run(
        run_date=today,
        platforms=platforms_run,
        mentions_found=len(all_mentions),
        new_mentions=new_count,
        status=status,
        error_log="; ".join(error_log) if error_log else None,
        started_at=started_at,
        finished_at=finished_at,
    )

    # --- Commit to branch ---
    commit_msg = f"daily: {today} — {len(all_mentions)} mentions found, {new_count} new"
    db.commit(commit_msg)

    # --- Print report ---
    report = build_report(all_mentions, new_count, today)
    print("\n" + report)

    return report


if __name__ == "__main__":
    main()
