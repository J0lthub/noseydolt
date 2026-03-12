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
from scrapers import hn, reddit, lobsters, stackoverflow, github, moltbook
from moltbook_poster import cross_post_top_mentions
from config import DOLT_REPO_PATH, DOLT_BRANCH, PLATFORMS_ENABLED, EXCLUDE_TERMS

def ensure_branch():
    """Make sure we're on the right branch before doing anything."""
    try:
        result = subprocess.run(
            ["dolt", "branch", "--show-current"],
            cwd=DOLT_REPO_PATH, capture_output=True, text=True, timeout=10
        )
        current = result.stdout.strip()
        if current != DOLT_BRANCH:
            subprocess.run(
                ["dolt", "checkout", DOLT_BRANCH],
                cwd=DOLT_REPO_PATH, timeout=10
            )
            print(f"[run] Switched to branch: {DOLT_BRANCH}")
        else:
            print(f"[run] On branch: {current}")
    except subprocess.TimeoutExpired:
        print("[run] Dolt branch check timed out — continuing anyway")


def build_report(mentions: list[dict], new_count: int, run_date: date) -> str:
    """Build NoseyDolt's daily digest report."""
    platforms_used = list(set(m["platform"] for m in mentions))

    # Sort feed by posted_at DESC (original publish date), fall back to discovered_at
    def sort_key(m):
        ts = m.get("posted_at") or m.get("discovered_at") or ""
        return ts

    mentions = sorted(mentions, key=sort_key, reverse=True)

    top = sorted(mentions, key=lambda m: m.get("potential_reach", 0), reverse=True)[:5]

    positive = [m for m in mentions if str(m.get("sentiment")) == "2"]
    negative = [m for m in mentions if str(m.get("sentiment")) == "0"]
    neutral  = [m for m in mentions if str(m.get("sentiment")) == "1"]

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
        f"  Sentiment: ✅ {len(positive)}  ⚠️ {len(negative)}  ➖ {len(neutral)}",
        "",
        "🔥 Top Mentions by Reach",
    ]

    for m in top:
        reach     = m.get("potential_reach", 0)
        reach_str = f"{reach:,}"
        title     = (m.get("title") or m.get("content") or "")[:80]
        posted    = (m.get("posted_at") or m.get("discovered_at") or "")[:10]
        lines.append(f"  [{m['platform'].upper()}] {title}")
        lines.append(f"    ↳ reach ~{reach_str} · {m.get('keyword_hit')} · {m.get('sentiment', 1)} · {posted}")
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

    # --- Moltbook ---
    if "moltbook" in PLATFORMS_ENABLED:
        try:
            mb_results = moltbook.fetch()
            all_mentions.extend(mb_results)
            platforms_run.append("moltbook")
        except Exception as e:
            print(f"[run] Moltbook error: {e}")
            error_log.append(f"Moltbook: {e}")

    # --- Noise filter ---
    if EXCLUDE_TERMS:
        before = len(all_mentions)
        def _is_noise(m):
            text = ((m.get("title") or "") + " " + (m.get("content") or "")).lower()
            return any(term.lower() in text for term in EXCLUDE_TERMS)
        all_mentions = [m for m in all_mentions if not _is_noise(m)]
        dropped = before - len(all_mentions)
        if dropped:
            print(f"[run] Noise filter dropped {dropped} mention(s)")

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

    # --- Cross-post top find to m/dolt on Moltbook ---
    if new_count > 0:
        try:
            cross_post_top_mentions(all_mentions, max_posts=1)
        except Exception as e:
            print(f"[run] Moltbook cross-post error: {e}")

    # --- Commit to branch ---
    commit_msg = f"daily: {today} — {len(all_mentions)} mentions found, {new_count} new"
    db.commit(commit_msg)

    # --- Push work branch to DoltHub ---
    try:
        push_result = subprocess.run(
            ["dolt", "push", "origin", DOLT_BRANCH],
            cwd=DOLT_REPO_PATH,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if push_result.returncode != 0:
            print(f"[run] DoltHub push warning: {push_result.stderr.strip()}")
        else:
            print(f"[run] Pushed {DOLT_BRANCH} to DoltHub ✓")
    except subprocess.TimeoutExpired:
        print("[run] DoltHub push timed out — skipping")

    # --- Merge work branch into main so dashboard picks it up ---
    # DoltHub SQL API only reads from main; never write directly to main
    try:
        subprocess.run(["dolt", "checkout", "main"], cwd=DOLT_REPO_PATH, timeout=10)
        merge_result = subprocess.run(
            ["dolt", "merge", DOLT_BRANCH, "-m", f"merge: {DOLT_BRANCH} → main ({today})"],
            cwd=DOLT_REPO_PATH,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if merge_result.returncode != 0:
            print(f"[run] Merge warning: {merge_result.stderr.strip()}")
        else:
            print(f"[run] Merged {DOLT_BRANCH} → main ✓")

        main_push = subprocess.run(
            ["dolt", "push", "origin", "main"],
            cwd=DOLT_REPO_PATH,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if main_push.returncode != 0:
            print(f"[run] DoltHub main push warning: {main_push.stderr.strip()}")
        else:
            print(f"[run] Pushed main to DoltHub ✓ (dashboard updated)")

        # Return to work branch for next run
        subprocess.run(["dolt", "checkout", DOLT_BRANCH], cwd=DOLT_REPO_PATH, timeout=10)
    except subprocess.TimeoutExpired:
        print("[run] Merge/push to main timed out — skipping")
        subprocess.run(["dolt", "checkout", DOLT_BRANCH], cwd=DOLT_REPO_PATH, timeout=10)

    # --- Generate static dashboard data for GitHub Pages ---
    db.write_dashboard_json()

    # --- Push dashboard to GitHub so GitHub Pages stays current ---
    try:
        git_push = subprocess.run(
            ["git", "push", "origin", "HEAD"],
            cwd=DOLT_REPO_PATH,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if git_push.returncode != 0:
            print(f"[run] GitHub push warning: {git_push.stderr.strip()}")
        else:
            print(f"[run] Pushed to GitHub ✓")
    except subprocess.TimeoutExpired:
        print("[run] GitHub push timed out — skipping")

    # --- Print report ---
    report = build_report(all_mentions, new_count, today)
    print("\n" + report)

    return report


if __name__ == "__main__":
    main()
