#!/bin/bash
# Build a sample repository and load it into the library (needs Docker; run from the repo root).
#   ./scripts/demo-seed.sh            # creates ./demo-repo, adds it as source "demo", syncs and releases it
# Safe to re-run: it re-syncs and only processes what changed.
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$PWD/demo-repo"; mkdir -p "$REPO"
# Files in ./demo-repo are written as you; the library database lives in ./data, owned by the container's user.
filt() { grep -v "Cannot set gray\|Container\|Network\|INFO:" || true; }
gen() { docker compose run --rm -T --user "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONPATH=/app -v "$PWD/scripts:/scripts:ro" -v "$REPO:/repo" backend "$@" 2>&1 | filt; }
run() { docker compose run --rm -T -v "$REPO:/repo:ro" backend "$@" 2>&1 | filt; }
echo "[1/4] Generating sample documents..."
gen python /scripts/demo_seed.py /repo
echo "[2/4] Adding the repository as a library source (only public/ is allowed; drafts excluded)..."
run python -m backend.library_cli add-source demo --root /repo --include 'public/**' --exclude 'public/drafts/**' \
  --rule 'public/planning/=Planning Commission:zoning,minutes' --rule 'public/parks/=Parks and Recreation:parks' \
  --rule 'public/clerk/=County Clerk:records' --rule 'public/roads/=Public Works:roads' || echo "(source already exists)"
echo "[3/4] Syncing (this OCRs the scanned PDF, so it takes a few seconds)..."
run python -m backend.library_cli sync demo
echo "[4/4] Releasing the processed items to readers..."
run python -m backend.library_cli release demo
echo "Done. Try the library at http://localhost:5173/#/library"
