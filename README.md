# WarU Event Search

Full-text search across WarU web event transcripts. Search results link directly to the moment in the video.

**Stack:** Python scripts → Hugo static site → Pagefind client-side search → GitHub Pages

An [`llms.txt`](https://github.com/kc0bfv/waru-webevent-search/blob/main/site/static/llms.txt) file is generated at build time and deployed with the site. It lists every event with direct links to the raw JSON on GitHub (structured transcript data with per-cue timestamps) for easy LLM ingestion.

---

## How it works

1. **`pull_recent.py`** — Scrapes the waru.edu events listing, fetches WebVTT transcripts via the Kaltura API, parses cue timings, and writes per-event JSON to `data/events/`.
2. **`build_pages.py`** — Reads `data/events/*.json` and generates Hugo content stubs and data files.
3. **Hugo** — Builds a static site from the content and layouts. Each event gets its own page with an embedded player and a full timestamp-linked transcript.
4. **Pagefind** — Indexes the built HTML and injects client-side search. Results include the matching transcript excerpt and link directly to `#t-{seconds}` on the event page, which auto-seeks the embedded video.
5. **GitHub Actions** — Runs the full pipeline daily and deploys to GitHub Pages.

---

## Setup

### 1. Fork / clone this repo

```bash
git clone https://github.com/YOUR-USERNAME/waru-search.git
cd waru-search
```

### 2. Configure the site URL

Edit `site/hugo.toml` and set your actual GitHub Pages URL:

```toml
baseURL = "https://YOUR-USERNAME.github.io/waru-search/"
```

### 3. Enable GitHub Pages

In your repo settings:
- **Settings → Pages → Source:** Deploy from a branch
- **Branch:** `gh-pages` / `(root)`

GitHub Actions will create and push to the `gh-pages` branch on first deploy.

### 4. Run the initial full-history import

Trigger the workflow manually with **full history** enabled:
- Go to **Actions → Pull Events and Deploy → Run workflow**
- Set "Fetch full event history" to `true`

Or run locally (see below).

---

## Local testing

**Prerequisites:** Python 3.11+, [Hugo](https://gohugo.io/installation/), Node.js (for `npx pagefind`)

```bash
# Install Python deps
pip install -r scripts/requirements.txt

# Test with a specific event URL:
bash local_test.sh "https://www.waru.edu/events/your-event-slug"

# Or with existing data (skip the network pull):
SKIP_PULL=1 bash local_test.sh

# Serve locally:
cd public && python -m http.server 8000
# → open http://localhost:8000
```

> **Note:** Pagefind loads its index over HTTP, so you must use a local server — opening `index.html` directly as a file won't work.

---

## Data model

### `data/events.json` — deduplication index

```json
{
  "version": 1,
  "known_entry_ids": ["1_abc123", "1_def456"],
  "known_event_urls": ["https://www.waru.edu/events/..."],
  "last_updated": "2025-03-15T10:00:00Z"
}
```

### `data/events/{id}.json` — per-event data

```json
{
  "id": "2025-03-15-ai-systems-engineering",
  "title": "AI Systems Engineering: Architecture Principles",
  "date": "2025-03-15",
  "event_url": "https://www.waru.edu/events/...",
  "entry_id": "1_abc123",
  "partner_id": "2203981",
  "uiconf_id": "49600112",
  "thumbnail_url": "https://...",
  "cues": [
    {
      "start": 12.0,
      "end": 18.5,
      "start_int": 12,
      "timestamp_label": "0:12",
      "text": "So the first thing we want to talk about is..."
    }
  ]
}
```

The `id` field doubles as the Hugo content slug and the key into Hugo's data directory (`site/data/events/{id}.json`).

---

## Deep-linking

Each cue on an event page has an anchor `id="t-{start_int}"`. A Pagefind sub-result (or any direct link) like:

```
/events/2025-03-15-ai-systems-engineering/#t-12
```

…will scroll to that cue and seek the embedded Kaltura player to that timestamp via iframe `playFrom=` reload.

If `uiconf_id` wasn't scraped for an event (older events may lack it), a fallback notice links out to waru.edu instead of embedding the player.

---

## Workflow schedule

The GitHub Actions workflow runs daily at **10:00 AM UTC** and scans the last ~3 listing pages for new events. You can also trigger it manually with:

- A **specific event URL** to ingest one event immediately.
- **Full history mode** to backfill everything.

---

## Directory structure

```
waru-search/
├── data/
│   ├── events.json          ← deduplication index (committed)
│   └── events/              ← per-event JSON (committed, source of truth)
├── scripts/
│   ├── pull_recent.py       ← discover + ingest events
│   ├── build_pages.py       ← JSON → Hugo content
│   └── requirements.txt
├── site/
│   ├── hugo.toml            ← Hugo config (update baseURL!)
│   ├── layouts/             ← HTML templates
│   ├── assets/css/          ← CSS
│   ├── content/events/      ← generated Hugo stubs (committed)
│   └── data/events/         ← generated Hugo data files (committed)
├── .github/workflows/
│   └── pull-and-build.yml   ← daily pull + deploy
├── local_test.sh            ← end-to-end local test helper
└── README.md
```
