"""
sync_goodidea.py — Weekly job: generate new topic batch via Claude,
commit to mguozhen/goodidea repo, then force-refresh local topic DBs.

Usage:
  python3 sync/sync_goodidea.py
"""
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).parent.parent

# Paths to sibling operator projects (update if moved)
OPERATOR_PROJECTS = [
    Path.home() / "x-matrix-operator",
    Path.home() / "reddit-matrix-operator",
]

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TOPICS_DIR = BASE / "topics"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _latest_vol_number() -> int:
    nums = []
    for f in TOPICS_DIR.glob("vol-*.md"):
        m = re.search(r"vol-(\d+)", f.name)
        if m:
            nums.append(int(m.group(1)))
    return max(nums) if nums else 0


def _existing_topics() -> set:
    """Return all topic texts already in the repo to avoid duplicates."""
    seen = set()
    for f in TOPICS_DIR.glob("*.md"):
        for m in re.finditer(r"^\d+\.\s+(.+)$", f.read_text(), re.MULTILINE):
            seen.add(m.group(1).strip().lower())
    return seen


def _generate_topics(existing: set) -> list:
    """Call Claude to generate a new batch of 50 topics."""
    try:
        import anthropic
    except ImportError:
        print("[sync] anthropic not installed: pip3 install anthropic")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    existing_sample = "\n".join(list(existing)[:30]) if existing else "(none yet)"

    prompt = f"""You are a content strategist for AI/ecommerce thought leadership.

Generate 50 NEW, high-engagement post topics for X (Twitter), LinkedIn, and Reddit.
Target audiences: Amazon sellers, Shopify merchants, ecommerce agency owners, AI startup founders, SMB decision-makers.

Rules:
- Each topic must be a specific question or angle (not generic titles)
- Mix controversy, data hooks, founder confessions, predictions, and how-tos
- Topics should trigger "I have an opinion on this" reactions
- Write in Chinese (中文) for most, but 20% in English for global reach
- DO NOT repeat or rephrase any of these existing topics:
{existing_sample}

Format: return ONLY a numbered list, one topic per line:
1. [topic]
2. [topic]
...
50. [topic]"""

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()

    topics = []
    for m in re.finditer(r"^\d+\.\s+(.+)$", raw, re.MULTILINE):
        t = m.group(1).strip()
        if len(t) > 15 and t.lower() not in existing:
            topics.append(t)
    return topics


def _write_vol_file(vol_num: int, topics: list) -> Path:
    """Write a new vol markdown file."""
    today = date.today().strftime("%Y-%m-%d")
    next_num = _latest_vol_number()  # offset for numbering
    start = next_num * 50 + 1  # approximate global offset

    lines = [
        f"# Vol.{vol_num:02d} — 新灵感批次 ({today})\n",
        f"> 由 Claude 自动生成，每周同步。共 {len(topics)} 题。\n\n---\n",
    ]
    for i, t in enumerate(topics, start=start):
        lines.append(f"{i}. {t}")

    path = TOPICS_DIR / f"vol-{vol_num:02d}-{today}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[sync] Wrote {path.name} ({len(topics)} topics)")
    return path


def _git_push(vol_file: Path, vol_num: int):
    """Commit and push the new vol file to GitHub."""
    today = date.today().isoformat()
    cmds = [
        ["git", "-C", str(BASE), "add", str(vol_file)],
        ["git", "-C", str(BASE), "commit", "-m",
         f"chore: add vol-{vol_num:02d} topics ({today}) [auto-sync]"],
        ["git", "-C", str(BASE), "push"],
    ]
    for cmd in cmds:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[sync] git cmd failed: {' '.join(cmd)}\n{result.stderr}")
            return
    print(f"[sync] Pushed vol-{vol_num:02d} to GitHub")


def _refresh_local_dbs():
    """Force-refresh topic_db in each operator project."""
    for proj in OPERATOR_PROJECTS:
        db_path = proj / "logs" / "topics.db"
        if db_path.exists():
            db_path.unlink()
            print(f"[sync] Cleared {db_path} (will re-sync on next run)")
        # Trigger a sync now if topic_db is importable
        sys.path.insert(0, str(proj / "scripts"))
        try:
            import importlib
            import topic_db
            importlib.reload(topic_db)
            # Override DB path for this project
            topic_db.DB_PATH = db_path.parent.parent / "logs" / "topics.db"
            topic_db.DB_PATH.parent.mkdir(exist_ok=True)
            added = topic_db.sync(force=True)
            print(f"[sync] {proj.name}: refreshed {added} topics")
        except Exception as e:
            print(f"[sync] {proj.name}: refresh failed ({e})")
        finally:
            if str(proj / "scripts") in sys.path:
                sys.path.remove(str(proj / "scripts"))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not ANTHROPIC_API_KEY:
        print("[sync] ANTHROPIC_API_KEY not set")
        sys.exit(1)

    print(f"[sync] Starting goodidea weekly sync — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    existing = _existing_topics()
    print(f"[sync] Existing topics in repo: {len(existing)}")

    topics = _generate_topics(existing)
    if not topics:
        print("[sync] No new topics generated, aborting")
        sys.exit(1)

    vol_num = _latest_vol_number() + 1
    vol_file = _write_vol_file(vol_num, topics)

    _git_push(vol_file, vol_num)
    _refresh_local_dbs()

    print(f"[sync] Done. Added {len(topics)} new topics (vol-{vol_num:02d})")


if __name__ == "__main__":
    main()
