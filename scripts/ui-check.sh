#!/bin/bash
# Run the library UI accessibility/privacy check (needs Docker and the stack running with demo data).
set -euo pipefail
cd "$(dirname "$0")/ui-check"
exec docker run --rm --network host -e BASE -v "$PWD:/w" -w /w mcr.microsoft.com/playwright:v1.49.1-noble \
  sh -c 'npm install --silent --no-audit --no-fund 2>&1 | tail -2; node library.mjs'
