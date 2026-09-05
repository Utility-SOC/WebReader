#!/bin/bash
# Standalone WebReader deploy script (Kubernetes flavor). Expects the
# packaged Helm chart (webreader-*.tgz) to be sitting next to this script --
# both ship together in the release's Kubernetes deploy bundle. No repo
# checkout needed.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v helm &>/dev/null; then
    echo "[ERROR] helm not found. Install it first: https://helm.sh/docs/intro/install/" >&2
    exit 1
fi
if ! command -v kubectl &>/dev/null; then
    echo "[ERROR] kubectl not found, or at least a working kubeconfig is needed." >&2
    exit 1
fi

CHART=$(ls webreader-*.tgz 2>/dev/null | head -1)
if [ -z "$CHART" ]; then
    echo "[ERROR] No webreader-*.tgz chart package found next to this script." >&2
    exit 1
fi

RELEASE_NAME="${1:-webreader}"
NAMESPACE="${2:-webreader}"

echo "Deploying $CHART as release '$RELEASE_NAME' in namespace '$NAMESPACE'..."
helm upgrade --install "$RELEASE_NAME" "$CHART" \
    --namespace "$NAMESPACE" --create-namespace

echo
echo "Done. See the notes above for how to reach the app, and read"
echo "backend/database.py's SQLite constraint before scaling anything:"
echo "backend and worker MUST stay at 1 replica each."
