#!/bin/bash
# Run the privacy check against a running WebReader (default http://localhost:5173).
#   ./scripts/privacy-check.sh                       # test the local stack
#   BASE_URL=https://reading-room.example.gov ./scripts/privacy-check.sh
#   EXPECT_READING_ROOM=1 ./scripts/privacy-check.sh # for a reading-room deployment
# Needs Docker (uses the official Playwright image) and no changes to your system.
set -euo pipefail
cd "$(dirname "$0")/privacy-check"
exec docker run --rm --network host \
  -e BASE_URL -e ALLOWED_ORIGINS -e EXPECT_READING_ROOM \
  -v "$PWD:/w" -w /w mcr.microsoft.com/playwright:v1.49.1-noble \
  sh -c 'npm install --silent --no-audit --no-fund 2>&1 | tail -2; node check.mjs'
