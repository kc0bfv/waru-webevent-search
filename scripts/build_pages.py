#!/usr/bin/env python3
"""
build_pages.py — Generate Hugo content and data files from event JSON.

Reads:  data/events/*.json               (source of truth, committed to repo)
Writes: site/content/events/{id}.md      (Hugo content stub with frontmatter)
        site/data/events/{id}.json        (Hugo data file; cues live here)

Run this after pull_recent.py and before running `hugo`.
"""

import json
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_EVENTS = REPO_ROOT / "data" / "events"
SITE_CONTENT = REPO_ROOT / "site" / "content" / "events"
SITE_DATA = REPO_ROOT / "site" / "data" / "events"


def make_frontmatter(event: dict) -> str:
    """Generate Hugo markdown frontmatter for one event."""
    title = event.get("title", "Untitled").replace('"', '\\"')
    date = event.get("date", "1970-01-01")
    event_id = event.get("id", "unknown")
    summary = ""
    if event.get("cues"):
        # First ~200 chars of transcript as the page description
        first_text = " ".join(c["text"] for c in event["cues"][:5])
        summary = first_text[:200].replace('"', '\\"')
    return (
        f'---\n'
        f'title: "{title}"\n'
        f'date: {date}\n'
        f'event_id: "{event_id}"\n'
        f'description: "{summary}"\n'
        f'draft: false\n'
        f'---\n'
    )


def main() -> None:
    if not SRC_EVENTS.exists():
        print("data/events/ not found. Run pull_recent.py first.")
        return

    event_files = sorted(SRC_EVENTS.glob("*.json"))
    if not event_files:
        print("No event JSON files found in data/events/. Run pull_recent.py first.")
        return

    SITE_CONTENT.mkdir(parents=True, exist_ok=True)
    SITE_DATA.mkdir(parents=True, exist_ok=True)

    count = 0
    skipped = 0
    for json_path in event_files:
        if json_path.name == ".gitkeep":
            continue
        try:
            event = json.loads(json_path.read_text())
        except json.JSONDecodeError as exc:
            print(f"  SKIP (bad JSON): {json_path.name}: {exc}")
            skipped += 1
            continue

        event_id = event.get("id")
        if not event_id:
            print(f"  SKIP (no id): {json_path.name}")
            skipped += 1
            continue

        # Copy full JSON (with cues) to site/data/events/ for Hugo data access
        dest_data = SITE_DATA / json_path.name
        shutil.copy(json_path, dest_data)

        # Write minimal Hugo content stub
        content_path = SITE_CONTENT / f"{event_id}.md"
        content_path.write_text(make_frontmatter(event))

        count += 1
        print(f"  ✓ {event_id}  ({len(event.get('cues', []))} cues)")

    print(f"\nBuilt {count} pages" + (f", skipped {skipped}" if skipped else "") + ".")


if __name__ == "__main__":
    main()
