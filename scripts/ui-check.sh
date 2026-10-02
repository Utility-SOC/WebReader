#!/bin/bash
# Browser checks for the UI (need Docker and the stack running; the library check also needs demo data: scripts/demo-seed.sh).
#   BASE=http://localhost:5173 ./scripts/ui-check.sh            # library UI: axe, keyboard, paging, privacy, reflow
#   BASE=http://localhost:5173 ./scripts/ui-check.sh box        # PDF-editor selection boxes: text stays readable in 3 browsers x 10 configurations
set -euo pipefail
cd "$(dirname "$0")/ui-check"
case "${1:-library}" in
  library) SCRIPT=library.mjs ;;
  box)     SCRIPT=box-visibility.mjs ;;
  *) echo "usage: ui-check.sh [library|box]" >&2; exit 2 ;;
esac
exec docker run --rm --network host -e BASE -e ONLY -v "$PWD:/w" -w /w mcr.microsoft.com/playwright:v1.49.1-noble \
  sh -c "npm install --silent --no-audit --no-fund 2>&1 | tail -2; node $SCRIPT"
