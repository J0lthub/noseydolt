#!/usr/bin/env python3
import subprocess
import os

docs = {
    "IDENTITY.md": open("IDENTITY.md").read(),
    "SOUL.md": open("SOUL.md").read(),
    "MEMORY.md": open("MEMORY.md").read(),
    "AGENTS.md": open("AGENTS.md").read(),
}

for name, content in docs.items():
    # Escape single quotes for SQL
    safe_content = content.replace("'", "''")
    sql = f"INSERT INTO bot_docs (name, content) VALUES ('{name}', '{safe_content}') ON DUPLICATE KEY UPDATE content='{safe_content}';"
    result = subprocess.run(
        ["dolt", "sql", "-q", sql],
        cwd="/Users/jamesleng/.openclaw/workspace/socialbot",
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"ERROR inserting {name}: {result.stderr}")
    else:
        print(f"✓ {name}")

print("Done.")
