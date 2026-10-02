#!/bin/bash
# Browser check of an admin accessibility report page (needs Docker).
#   ./scripts/report-check.sh path/to/report.html      # made by: python -m backend.library_cli report NAME --html report.html
# Runs axe (WCAG 2.2 AA + best practice) in light, dark and forced-colors, checks there are no external requests, the skip link,
# heading order, keyboard use of the links and details, 320px reflow, and that it renders in Chromium, Firefox and WebKit.
set -euo pipefail
REPORT="${1:-}"
[ -f "$REPORT" ] || { echo "usage: report-check.sh path/to/report.html" >&2; exit 2; }
cd "$(dirname "$0")/ui-check"
exec docker run --rm -e "REPORT_NAME=$(basename "$REPORT")" -v "$(cd "$(dirname "$REPORT")" && pwd):/r:ro" -v "$PWD:/w" -w /w \
  mcr.microsoft.com/playwright:v1.49.1-noble sh -c 'npm install --silent --no-audit --no-fund 2>&1 | tail -2; node report.mjs'
