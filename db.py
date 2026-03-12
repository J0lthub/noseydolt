"""
Dolt database writer for NoseyDolt.
Writes mentions to the nosey/work branch.
"""
import subprocess
import json
import os
from datetime import date, datetime

from config import DOLT_REPO_PATH, DOLT_BRANCH


def _sql(query: str) -> str:
    result = subprocess.run(
        ["dolt", "sql", "-q", query],
        cwd=DOLT_REPO_PATH,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Dolt SQL error: {result.stderr.strip()}")
    return result.stdout.strip()


def _esc(val) -> str:
    """Escape a value for SQL insertion."""
    if val is None:
        return "NULL"
    if isinstance(val, (int, float)):
        return str(val)
    # Escape single quotes and wrap in quotes
    return "'" + str(val).replace("\\", "\\\\").replace("'", "''")[:4000] + "'"


def get_existing_ids() -> set:
    """Return set of mention IDs already in DB to deduplicate."""
    try:
        out = _sql("SELECT id FROM mentions;")
        ids = set()
        for line in out.split("\n"):
            line = line.strip()
            if line and not line.startswith("+") and not line.startswith("|  id"):
                ids.add(line.strip("| ").strip())
        return ids
    except Exception:
        return set()


def write_mentions(mentions: list[dict]) -> int:
    """Insert new mentions, skip duplicates. Returns count of new rows written."""
    existing = get_existing_ids()
    new_count = 0

    for m in mentions:
        if m["id"] in existing:
            continue
        try:
            _sql(f"""
INSERT INTO mentions
  (id, platform, post_id, url, author, author_followers, title, content,
   keyword_hit, keyword_hits_all, posted_at, discovered_at, relevance,
   sentiment, likes, shares, comments, upvotes, potential_reach, notes)
VALUES (
  {_esc(m['id'])},
  {_esc(m['platform'])},
  {_esc(m['post_id'])},
  {_esc(m['url'])},
  {_esc(m.get('author'))},
  {_esc(m.get('author_followers', 0))},
  {_esc(m.get('title'))},
  {_esc(m.get('content'))},
  {_esc(m.get('keyword_hit'))},
  {_esc(m.get('keyword_hits_all'))},
  {_esc(m.get('posted_at'))},
  NOW(),
  {_esc(m.get('relevance'))},
  {_esc(m.get('sentiment'))},
  {_esc(m.get('likes', 0))},
  {_esc(m.get('shares', 0))},
  {_esc(m.get('comments', 0))},
  {_esc(m.get('upvotes', 0))},
  {_esc(m.get('potential_reach', 0))},
  {_esc(m.get('notes'))}
);""")
            new_count += 1
        except Exception as e:
            print(f"[DB] Failed to insert {m['id']}: {e}")

    return new_count


def write_keyword_triggers(mentions: list[dict]):
    """Write keyword_triggers rows for multi-keyword matches."""
    for m in mentions:
        all_kws = m.get("keyword_hits_all", "")
        if not all_kws:
            continue
        for kw in all_kws.split(","):
            kw = kw.strip()
            if not kw:
                continue
            try:
                _sql(f"""
INSERT IGNORE INTO keyword_triggers (mention_id, keyword)
VALUES ({_esc(m['id'])}, {_esc(kw)});""")
            except Exception:
                pass


def log_run(run_date: date, platforms: list, mentions_found: int,
            new_mentions: int, status: str, error_log: str = None,
            started_at: datetime = None, finished_at: datetime = None):
    """Write a daily_runs audit row."""
    _sql(f"""
INSERT INTO daily_runs
  (run_date, branch, platforms, mentions_found, new_mentions, status, error_log, started_at, finished_at)
VALUES (
  {_esc(str(run_date))},
  {_esc(DOLT_BRANCH)},
  {_esc(",".join(platforms))},
  {_esc(mentions_found)},
  {_esc(new_mentions)},
  {_esc(status)},
  {_esc(error_log)},
  {_esc(str(started_at) if started_at else None)},
  {_esc(str(finished_at) if finished_at else None)}
);""")


def export_dashboard_json() -> dict:
    """
    Pull all mentions + recent runs from Dolt and return as a dict
    suitable for writing to dashboard/data.json.
    """
    # --- Mentions ---
    mentions_raw = _sql("""
SELECT id, platform, title, url, sentiment, potential_reach,
       keyword_hit, author, posted_at, discovered_at, relevance
FROM mentions
ORDER BY posted_at DESC, potential_reach DESC
LIMIT 2000;
""")
    mentions = []
    headers = None
    for line in mentions_raw.split("\n"):
        line = line.strip()
        if not line or line.startswith("+"):
            continue
        cols = [c.strip() for c in line.split("|") if c.strip()]
        if headers is None:
            headers = cols
            continue
        if len(cols) == len(headers):
            row = dict(zip(headers, cols))
            # Normalize NULLs
            for k, v in row.items():
                if v == "NULL":
                    row[k] = None
            mentions.append(row)

    # --- Daily runs ---
    runs_raw = _sql("""
SELECT run_date, mentions_found, new_mentions, status
FROM daily_runs
ORDER BY run_date DESC
LIMIT 7;
""")
    runs = []
    headers = None
    for line in runs_raw.split("\n"):
        line = line.strip()
        if not line or line.startswith("+"):
            continue
        cols = [c.strip() for c in line.split("|") if c.strip()]
        if headers is None:
            headers = cols
            continue
        if len(cols) == len(headers):
            runs.append(dict(zip(headers, cols)))

    return {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mentions": mentions,
        "daily_runs": runs,
    }


def write_dashboard_json():
    """Export data and write to dashboard/data.json."""
    data = export_dashboard_json()
    out_path = os.path.join(DOLT_REPO_PATH, "dashboard", "data.json")
    with open(out_path, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    print(f"[DB] Wrote dashboard/data.json ({len(data['mentions'])} mentions, {len(data['daily_runs'])} runs)")


def commit(message: str):
    """Dolt add + commit on the current branch."""
    subprocess.run(["dolt", "add", "."], cwd=DOLT_REPO_PATH)
    result = subprocess.run(
        ["dolt", "commit", "-m", message],
        cwd=DOLT_REPO_PATH,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # "nothing to commit" is fine
        if "nothing to commit" in result.stdout + result.stderr:
            print("[DB] Nothing new to commit.")
        else:
            print(f"[DB] Commit warning: {result.stderr.strip()}")
    else:
        print(f"[DB] Committed: {message}")
