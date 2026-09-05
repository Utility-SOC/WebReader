#!/bin/bash
# Sizes the backend and worker containers' memory cap (see docker-compose.yml)
# to this machine's total RAM and writes it to .env, which `docker compose`
# loads automatically from the project directory -- no wrapper script needed
# for `docker compose up` itself.
#
# Only host RAM is considered: image captioning here runs on CPU by design
# (no GPU code path), and Docker's mem_limit is a host-memory cgroup limit
# that doesn't apply to VRAM regardless -- GPU memory would need a separate,
# driver-level reservation if CUDA support were added later.
#
# Re-run this after moving the repo to different hardware.
set -euo pipefail
cd "$(dirname "$0")/.."

TOTAL_MB=$(free -m | awk '/^Mem:/{print $2}')
TARGET_MB=$(( TOTAL_MB * 40 / 100 ))

# Floor: Florence-2-base + quantization overhead needs ~2GB just to load.
# Ceiling: captioning has been observed to peak around 2.3GB RSS in testing;
# no benefit to reserving much more than that plus margin.
if [ "$TARGET_MB" -lt 2048 ]; then TARGET_MB=2048; fi
if [ "$TARGET_MB" -gt 8192 ]; then TARGET_MB=8192; fi
TARGET_GB=$(( (TARGET_MB + 1023) / 1024 ))

if [ -f .env ] && grep -q '^ML_MEM_LIMIT=' .env; then
    sed -i "s/^ML_MEM_LIMIT=.*/ML_MEM_LIMIT=${TARGET_GB}g/" .env
else
    echo "ML_MEM_LIMIT=${TARGET_GB}g" >> .env
fi

echo "Detected ${TOTAL_MB}MB total RAM -> mem_limit set to ${TARGET_GB}g in .env"
