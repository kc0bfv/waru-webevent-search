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
SITE_STATIC = REPO_ROOT / "site" / "static"

GITHUB_REPO = "https://github.com/kc0bfv/waru-webevent-search"
GITHUB_RAW = "https://raw.githubusercontent.com/kc0bfv/waru-webevent-search/main"


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


def write_llms_txt(events: list[dict]) -> None:
    """Write site/static/llms.txt listing all events with raw GitHub URLs."""
    lines = [
        "# WarU Web Event Search",
        "",
        "> Full-text search across WarU (Warfighting Acquisition University) web event",
        "> transcripts. Each event includes a timestamped transcript and an embedded",
        "> Kaltura video player. Search results deep-link to the exact moment in the video.",
        "",
        f"Source repository: {GITHUB_REPO}",
        "",
        "## Machine-readable event data",
        "",
        "Each event is available as structured JSON. Fields: id, title, date, event_url,",
        "entry_id, partner_id, uiconf_id, thumbnail_url, cues[]{start, end, start_int,",
        "timestamp_label, text}.",
        "",
    ]
    for event in sorted(events, key=lambda e: e.get("date", ""), reverse=True):
        eid = event.get("id", "")
        title = event.get("title", "Untitled")
        date = event.get("date", "")
        cue_count = len(event.get("cues", []))
        json_url = f"{GITHUB_RAW}/data/events/{eid}.json"
        lines.append(f"- [{date} — {title}]({json_url}) ({cue_count} transcript segments)")

    lines += [
        "",
        "## Hugo content stubs",
        "",
        "Minimal markdown frontmatter files used to generate the static site:",
        f"{GITHUB_RAW}/site/content/events/",
        "",
        "## Deduplication index",
        "",
        f"{GITHUB_RAW}/data/events.json",
    ]

    SITE_STATIC.mkdir(parents=True, exist_ok=True)
    (SITE_STATIC / "llms.txt").write_text("\n".join(lines) + "\n")
    print(f"  Wrote llms.txt ({len(events)} events)")


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

    events_built: list[dict] = []
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

        events_built.append(event)
        count += 1
        print(f"  ✓ {event_id}  ({len(event.get('cues', []))} cues)")

    write_llms_txt(events_built)
    print(f"\nBuilt {count} pages" + (f", skipped {skipped}" if skipped else "") + ".")


if __name__ == "__main__":
    main()
