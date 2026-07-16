#!/usr/bin/env python3
"""
pull_recent.py — Discover and ingest WARU web event transcripts.

Scrapes the waru.edu/events listing, identifies events not yet in
data/events.json, downloads their WebVTT transcripts via the Kaltura API,
parses cue timings, and writes per-event JSON files to data/events/.

Usage:
    # Pull last ~3 pages of the listing (default, good for daily cron):
    python scripts/pull_recent.py

    # Pull up to 200 pages of the listing (initial full history import):
    python scripts/pull_recent.py --all

    # Process one or more specific event URLs directly:
    python scripts/pull_recent.py --url https://www.waru.edu/events/some-event

NOTE: If waru.edu's listing page structure differs from Drupal-style href patterns,
adjust the regex in discover_event_urls() accordingly.
"""

import sys
import re
import json
import argparse
import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
EVENTS_DIR = DATA_DIR / "events"
INDEX_FILE = DATA_DIR / "events.json"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WARU_BASE = "https://www.waru.edu"
LISTING_URL = "https://www.waru.edu/events"
KALTURA_API = "https://www.kaltura.com/api_v3/service/multirequest"
WIDGET_ID = "_2203981"

PAGE_HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Content-Type": "application/json",
    "Origin": "https://media.waru.edu",
    "Referer": "https://media.waru.edu/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "cross-site",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
    ),
    "sec-ch-ua": '"Not-A.Brand";v="24", "Chromium";v="146"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
}

# ---------------------------------------------------------------------------
# Index management
# ---------------------------------------------------------------------------


def load_index() -> dict:
    if INDEX_FILE.exists():
        return json.loads(INDEX_FILE.read_text())
    return {
        "version": 1,
        "known_entry_ids": [],
        "known_event_urls": [],
        "last_updated": None,
    }


def save_index(index: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    index["last_updated"] = datetime.now(timezone.utc).isoformat()
    INDEX_FILE.write_text(json.dumps(index, indent=2))


def save_event(event_data: dict) -> Path:
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    path = EVENTS_DIR / f"{event_data['id']}.json"
    path.write_text(json.dumps(event_data, indent=2, ensure_ascii=False))
    return path


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover_event_urls(max_pages: int = 5) -> list:
    """
    Scrape the waru.edu/events listing for event page URLs.
    Uses Drupal-style ?page=N pagination and stops when no new links appear.
    """
    seen: set = set()
    urls: list = []

    for page in range(max_pages):
        listing = LISTING_URL if page == 0 else f"{LISTING_URL}?page={page}"
        print(f"  Scanning listing page {page}: {listing}", file=sys.stderr)
        try:
            resp = throttled_request(listing, headers=PAGE_HEADERS, timeout=30)
            resp.raise_for_status()
        except Exception as exc:
            print(f"  Warning: could not fetch {listing}: {exc}", file=sys.stderr)
            break

        # Match /events/{slug} where slug is lowercase with hyphens/numbers.
        # Excludes bare /events, /events?..., /events/add, etc.
        found = re.findall(r'href="(/events/[a-z0-9][a-z0-9\-]+)"', resp.text)
        new_this_page = 0
        for slug in found:
            full = urljoin(WARU_BASE, slug)
            if full not in seen:
                seen.add(full)
                urls.append(full)
                new_this_page += 1

        if new_this_page == 0:
            print(f"  No new links on page {page}; stopping.", file=sys.stderr)
            break

    return urls


# ---------------------------------------------------------------------------
# Page scraping
# ---------------------------------------------------------------------------

THROTTLE_PREV_TIME = 0
THROTTLE_PERIOD = 1
def throttled_request(*args: str, **kwargs: dict) -> requests.Response:
    """
    Make a call to requests.get with args and kwargs, but
    sleep such that calls can only be made once per second.
    """
    global THROTTLE_PREV_TIME

    sleep_time = THROTTLE_PERIOD - (time.time() - THROTTLE_PREV_TIME)
    if sleep_time > 0:
        time.sleep(sleep_time)

    THROTTLE_PREV_TIME = time.time()
    return requests.get(*args, **kwargs)


def fetch_page_data(event_url: str) -> dict:
    """
    Download a waru.edu event page and extract:
    - entry_id (Kaltura media ID)
    - event_date (YYYY-MM-DD)
    - title (from og:title or <h1>)
    - uiconf_id (Kaltura player config ID, for iframe embedding)
    """
    resp = throttled_request(event_url, headers=PAGE_HEADERS, timeout=30)
    resp.raise_for_status()
    html = resp.text

    # entry_id
    m = re.search(r'entry_id[="\s:]+([0-9a-zA-Z_\-]{5,})', html)
    if not m:
        m = re.search(r'"entry_id"\s*:\s*"([0-9a-zA-Z_\-]{5,})"', html)
    entry_id = m.group(1) if m else ""

    # event date from <time datetime="YYYY-MM-DDT...">
    dm = re.search(r'<time[^>]+datetime="(\d{4}-\d{2}-\d{2})T', html)
    event_date = dm.group(1) if dm else ""

    # uiconf_id from Kaltura embed URL
    um = re.search(r'uiconf_id[/=](\d{6,})', html)
    uiconf_id = um.group(1) if um else ""

    # title: og:title first, fall back to h1
    tm = re.search(
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\'<]+)["\']',
        html,
    )
    if not tm:
        tm = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
    title = tm.group(1).strip() if tm else ""

    return {
        "entry_id": entry_id,
        "event_date": event_date,
        "uiconf_id": uiconf_id,
        "title": title,
    }


# ---------------------------------------------------------------------------
# Kaltura API
# ---------------------------------------------------------------------------


def kaltura_multirequest(entry_id: str) -> ET.Element:
    payload = {
        "1": {
            "service": "session",
            "action": "startWidgetSession",
            "widgetId": WIDGET_ID,
        },
        "2": {
            "service": "baseEntry",
            "action": "list",
            "ks": "{1:result:ks}",
            "filter": {"redirectFromEntryId": entry_id},
            "responseProfile": {
                "type": 1,
                "fields": "id,partnerId,name,duration,thumbnailUrl",
            },
        },
        "3": {
            "service": "baseEntry",
            "action": "getPlaybackContext",
            "entryId": "{2:result:objects:0:id}",
            "ks": "{1:result:ks}",
            "contextDataParams": {
                "objectType": "KalturaContextDataParams",
                "flavorTags": "all",
            },
        },
    }
    resp = requests.post(
        KALTURA_API,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    return ET.fromstring(resp.text)


def _txt(el: ET.Element, tag: str, default: str = "") -> str:
    child = el.find(tag)
    return (child.text or "").strip() if child is not None else default


def extract_kaltura_data(root: ET.Element) -> dict:
    """Extract title, IDs, thumbnail, and first WebVTT URL from Kaltura response."""
    items = root.findall("result/item")
    if len(items) < 3:
        raise ValueError("Unexpected Kaltura response (< 3 result items)")

    entry = items[1].find("objects/item")
    if entry is None:
        raise ValueError("No entry in baseEntry/list result")

    title = _txt(entry, "name")
    entry_id = _txt(entry, "id")
    partner_id = _txt(entry, "partnerId")
    thumbnail_url = _txt(entry, "thumbnailUrl")

    vtt_url = ""
    for cap in items[2].findall("playbackCaptions/item"):
        url = _txt(cap, "webVttUrl")
        if url:
            vtt_url = url
            break  # take the first available caption track

    return {
        "title": title,
        "entry_id": entry_id,
        "partner_id": partner_id,
        "thumbnail_url": thumbnail_url,
        "vtt_url": vtt_url,
    }


# ---------------------------------------------------------------------------
# VTT parsing
# ---------------------------------------------------------------------------


def vtt_time_to_seconds(ts: str) -> float:
    """Convert WebVTT timestamp (HH:MM:SS.mmm or MM:SS.mmm) to float seconds."""
    ts = ts.strip().split()[0]  # drop any trailing positioning hints
    parts = ts.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(parts[0])
    except ValueError:
        return 0.0


def format_timestamp(seconds: float) -> str:
    """Format a float seconds value as M:SS or H:MM:SS."""
    s = int(seconds)
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    if h > 0:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def parse_vtt(content: str) -> list:
    """
    Parse WebVTT content into a list of cue dicts:
      { start, end, start_int, timestamp_label, text }
    Strips inline VTT tags (<c.color...>, <00:00:00.000>, etc.).
    """
    cues = []
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "-->" in line:
            parts = line.split("-->")
            start = vtt_time_to_seconds(parts[0])
            end = vtt_time_to_seconds(parts[1])
            text_parts = []
            i += 1
            while i < len(lines) and lines[i].strip():
                cleaned = re.sub(r"<[^>]+>", "", lines[i]).strip()
                if cleaned:
                    text_parts.append(cleaned)
                i += 1
            text = " ".join(text_parts)
            if text:
                cues.append(
                    {
                        "start": round(start, 3),
                        "end": round(end, 3),
                        "start_int": int(start),
                        "timestamp_label": format_timestamp(start),
                        "text": text,
                    }
                )
        i += 1
    return cues


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _peek_existing(norm_url: str, index: dict) -> dict | None:
    """Return the on-disk event dict whose event_url matches norm_url, or None."""
    for p in EVENTS_DIR.glob("*.json"):
        try:
            data = json.loads(p.read_text())
            if data.get("event_url", "").rstrip("/") == norm_url:
                return data
        except Exception:
            pass
    return None


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^\w\s\-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:80]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def process_event(event_url: str, index: dict) -> dict | None:
    """
    Ingest a single event. Returns the event dict on success, None if
    already known or if ingestion fails.
    """
    norm_url = event_url.rstrip("/")

    if norm_url in index["known_event_urls"]:
        print(f"  Skip (known URL): {norm_url}", file=sys.stderr)
        return None

    print(f"\nProcessing: {event_url}", file=sys.stderr)

    try:
        page_data = fetch_page_data(event_url)
    except Exception as exc:
        print(f"  ERROR fetching page: {exc}", file=sys.stderr)
        return None

    if not page_data["entry_id"]:
        print("  No entry_id found — skipping.", file=sys.stderr)
        return None

    if page_data["entry_id"] in index["known_entry_ids"]:
        print(
            f"  Skip (known entry_id): {page_data['entry_id']}", file=sys.stderr
        )
        # Only permanently skip if the existing file already has a transcript.
        # If cues are empty the entry is a future/pending event — leave it out
        # of known_event_urls so it gets retried on the next run.
        existing = next(
            (json.loads(p.read_text()) for p in EVENTS_DIR.glob("*.json")
             if json.loads(p.read_text()).get("entry_id") == page_data["entry_id"]),
            None,
        )
        if existing and existing.get("cues"):
            index["known_event_urls"].append(norm_url)
        return None

    try:
        root = kaltura_multirequest(page_data["entry_id"])
        kaltura = extract_kaltura_data(root)
    except Exception as exc:
        print(f"  ERROR calling Kaltura API: {exc}", file=sys.stderr)
        return None

    title = kaltura["title"] or page_data["title"] or "Untitled Event"
    date = page_data["event_date"] or datetime.now().strftime("%Y-%m-%d")
    event_id = f"{date}-{slugify(title)}" if date else slugify(title)

    cues = []
    if kaltura["vtt_url"]:
        try:
            vtt_resp = throttled_request(kaltura["vtt_url"], timeout=30)
            vtt_resp.raise_for_status()
            cues = parse_vtt(vtt_resp.text)
            print(f"  Parsed {len(cues)} cues from VTT.", file=sys.stderr)
        except Exception as exc:
            print(f"  Warning: could not fetch/parse VTT: {exc}", file=sys.stderr)
    else:
        print("  No WebVTT caption track found.", file=sys.stderr)

    event_data = {
        "id": event_id,
        "title": title,
        "date": date,
        "event_url": event_url,
        "entry_id": kaltura["entry_id"],
        "partner_id": kaltura["partner_id"],
        "uiconf_id": page_data["uiconf_id"],
        "thumbnail_url": kaltura["thumbnail_url"],
        "cues": cues,
    }

    path = save_event(event_data)
    index["known_entry_ids"].append(kaltura["entry_id"])
    if cues:
        # Only mark as permanently done once we have a real transcript.
        # Events with no cues yet (future/pending) stay out of known_event_urls
        # so they are retried on subsequent runs.
        index["known_event_urls"].append(norm_url)
    else:
        print("  No transcript yet — will retry on next run.", file=sys.stderr)
    print(f"  Saved → {path.name} ({len(cues)} cues)", file=sys.stderr)
    return event_data


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover and ingest WARU web event transcripts."
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=3,
        metavar="N",
        help="Number of listing pages to scan.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Scan up to 200 listing pages (initial full-history import).",
    )
    parser.add_argument(
        "--url",
        nargs="+",
        metavar="URL",
        help="Process specific event URL(s) directly instead of discovering.",
    )
    args = parser.parse_args()

    index = load_index()

    if args.url:
        urls = args.url
    elif args.all:
        urls = discover_event_urls(max_pages=200)
    else:
        urls = discover_event_urls(max_pages=args.pages)

    print(f"Found {len(urls)} candidate event URL(s).", file=sys.stderr)

    new_count = 0
    for url in urls:
        result = process_event(url, index)
        if result:
            new_count += 1

    save_index(index)
    print(f"\nDone. {new_count} new event(s) ingested.")


if __name__ == "__main__":
    main()
