#!/usr/bin/env bash
# local_test.sh — End-to-end local test of the full pipeline.
#
# Prerequisites:
#   pip install requests
#   npm install -g pagefind   (or use npx; Node.js required)
#   brew install hugo          (or apt install hugo / download from gohugo.io)
#
# Usage:
#   # Test with a specific event URL:
#   bash local_test.sh "https://www.waru.edu/events/your-event-slug"
#
#   # Run with existing data (skip pull):
#   SKIP_PULL=1 bash local_test.sh

set -euo pipefail

EVENT_URL="${1:-}"

echo "=== WARU Search local test ==="

if [ -z "${SKIP_PULL:-}" ]; then
  if [ -n "$EVENT_URL" ]; then
    echo "→ Pulling event: $EVENT_URL"
    python scripts/pull_recent.py --url "$EVENT_URL"
  else
    echo "→ Pulling recent events (3 listing pages)..."
    python scripts/pull_recent.py
  fi
else
  echo "→ Skipping pull (SKIP_PULL set)."
fi

echo "→ Building Hugo content pages..."
python scripts/build_pages.py

echo "→ Building Hugo site..."
(cd site && hugo --minify --destination ../public)

echo "→ Running Pagefind..."
npx pagefind --site public

echo "→ Building Hugo SharePoint content..."
(cd sharepoint_pages_hugo && hugo --minify --destination ../sharepoint_output)

echo ""
echo "✓ Build complete. Serve with:"
echo "  cd public && python -m http.server 8000"
echo "  Then open http://localhost:8000"
