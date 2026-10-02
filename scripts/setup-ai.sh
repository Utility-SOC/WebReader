#!/bin/bash
# Choose where WebReader's AI features (image captioning) run, and write the
# choice to .env. docker compose and run_linux.sh both read .env; for
# Kubernetes use the `ai:` block in charts/webreader/values.yaml instead.
#
#   ./scripts/setup-ai.sh                      # interactive
#   ./scripts/setup-ai.sh --provider anthropic --model <model>   # key is still prompted
#                                              # (or pass it as WEBREADER_LLM_API_KEY in the environment)
#
# Providers: local (default, Florence-2 on this machine, nothing leaves it),
#            openai | deepseek | kimi | custom (OpenAI-compatible APIs),
#            gemini | anthropic (native APIs), none (no AI captions).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# Run from the repo root, or from the release zip where this sits next to docker-compose.yml
if [ -f "$HERE/docker-compose.yml" ]; then cd "$HERE"; else cd "$HERE/.."; fi
ENV_FILE=.env

PROVIDER=""; MODEL=""; BASE_URL=""
while [ $# -gt 0 ]; do
  case "$1" in
    --provider) PROVIDER="$2"; shift 2 ;;
    --model)    MODEL="$2";    shift 2 ;;
    --base-url) BASE_URL="$2"; shift 2 ;;
    -h|--help)  sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$PROVIDER" ]; then
  echo "Where should WebReader run image captioning?"
  echo "  1) local      - on this machine (private; needs ~2.5GB RAM, downloads a model once)"
  echo "  2) openai     - OpenAI API"
  echo "  3) deepseek   - DeepSeek API (check the model you pick accepts images)"
  echo "  4) kimi       - Moonshot / Kimi API"
  echo "  5) gemini     - Google Gemini API"
  echo "  6) anthropic  - Anthropic Claude API"
  echo "  7) custom     - any other OpenAI-compatible endpoint (incl. a self-hosted one)"
  echo "  8) none       - no AI captions"
  read -rp "Choice [1]: " c
  case "${c:-1}" in
    1) PROVIDER=local ;; 2) PROVIDER=openai ;; 3) PROVIDER=deepseek ;; 4) PROVIDER=kimi ;;
    5) PROVIDER=gemini ;; 6) PROVIDER=anthropic ;; 7) PROVIDER=custom ;; 8) PROVIDER=none ;;
    *) echo "Invalid choice" >&2; exit 2 ;;
  esac
fi

KEY="${WEBREADER_LLM_API_KEY:-}"
case "$PROVIDER" in
  local|none) MODEL=""; BASE_URL=""; KEY="" ;;
  openai|deepseek|kimi|gemini|anthropic|custom)
    echo
    echo "NOTE: with '$PROVIDER', every image WebReader captions is sent to that provider."
    echo "      Pick 'local' if documents must not leave this machine."
    echo
    if [ "$PROVIDER" = custom ] && [ -z "$BASE_URL" ]; then
      read -rp "Base URL (e.g. http://localhost:11434/v1): " BASE_URL
    fi
    if [ -z "$MODEL" ]; then
      hint=""; [ "$PROVIDER" = anthropic ] && hint=" (e.g. claude-haiku-4-5-20251001)"
      read -rp "Vision-capable model name$hint: " MODEL
    fi
    if [ -z "$KEY" ]; then
      read -rsp "API key (input hidden): " KEY; echo
    fi
    [ -n "$MODEL" ] && [ -n "$KEY" ] || { echo "Model and API key are required." >&2; exit 2; }
    ;;
  *) echo "Unknown provider: $PROVIDER" >&2; exit 2 ;;
esac

# Rewrite only our own lines; keep anything else in .env (e.g. ML_MEM_LIMIT).
touch "$ENV_FILE"; chmod 600 "$ENV_FILE"
grep -v '^WEBREADER_' "$ENV_FILE" > "$ENV_FILE.tmp" || true
{
  echo "WEBREADER_CAPTION_PROVIDER=$PROVIDER"
  [ -n "$MODEL" ]    && echo "WEBREADER_LLM_MODEL=$MODEL"
  [ -n "$BASE_URL" ] && echo "WEBREADER_LLM_BASE_URL=$BASE_URL"
  [ -n "$KEY" ]      && echo "WEBREADER_LLM_API_KEY=$KEY"
} >> "$ENV_FILE.tmp"
chmod 600 "$ENV_FILE.tmp"; mv "$ENV_FILE.tmp" "$ENV_FILE"

echo "Saved to $ENV_FILE (readable only by you; it is git-ignored). Provider: $PROVIDER"
echo "Restart to apply:  docker compose up -d   (or re-run ./run_linux.sh)"
