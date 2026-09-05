#!/bin/bash
# Standalone WebReader deploy script (Docker Compose flavor). Pulls prebuilt
# images from GHCR -- no repo checkout needed, just this script and the
# docker-compose.yml next to it.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v docker &>/dev/null; then
    echo "[ERROR] docker not found. Install Docker first: https://docs.docker.com/get-docker/" >&2
    exit 1
fi
if ! docker compose version &>/dev/null; then
    echo "[ERROR] 'docker compose' not available (need Docker Compose v2)." >&2
    exit 1
fi

# Size the backend/worker memory cap to this machine's RAM (see
# backend/captioning.py in the source repo for why this matters -- image
# captioning is the heavy part). Skipped if ML_MEM_LIMIT is already set,
# e.g. by re-running this script or exporting it yourself beforehand.
if [ -z "${ML_MEM_LIMIT:-}" ] && ! grep -q '^ML_MEM_LIMIT=' .env 2>/dev/null; then
    if command -v free &>/dev/null; then
        TOTAL_MB=$(free -m | awk '/^Mem:/{print $2}')
    elif command -v sysctl &>/dev/null; then
        TOTAL_MB=$(( $(sysctl -n hw.memsize) / 1024 / 1024 ))
    else
        TOTAL_MB=8192  # unknown platform; assume a reasonable default
    fi
    TARGET_MB=$(( TOTAL_MB * 40 / 100 ))
    if [ "$TARGET_MB" -lt 2048 ]; then TARGET_MB=2048; fi
    if [ "$TARGET_MB" -gt 8192 ]; then TARGET_MB=8192; fi
    TARGET_GB=$(( (TARGET_MB + 1023) / 1024 ))
    echo "ML_MEM_LIMIT=${TARGET_GB}g" >> .env
    echo "Detected ${TOTAL_MB}MB total RAM -> backend/worker memory cap set to ${TARGET_GB}g"
fi

echo "Pulling images..."
docker compose pull
echo "Starting WebReader..."
docker compose up -d

echo
echo "WebReader is starting. Open http://localhost:5173 once containers report healthy:"
echo "  docker compose ps"
echo "Logs:"
echo "  docker compose logs -f"
