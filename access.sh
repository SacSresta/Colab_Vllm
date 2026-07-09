#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COLAB_HOME="${COLAB_HOME:-$ROOT_DIR/.colab_state/home}"
COLAB_CFG="${COLAB_CFG:-$ROOT_DIR/.colab_state/sessions.json}"
COLAB_OAUTH="${COLAB_OAUTH:-$COLAB_HOME/.colab-cli-oauth-config.json}"

if [ -x "$ROOT_DIR/.venv/bin/colab" ]; then
  COLAB_BIN="$ROOT_DIR/.venv/bin/colab"
elif command -v colab >/dev/null 2>&1; then
  COLAB_BIN="$(command -v colab)"
else
  echo "Error: colab CLI not found. Run 'uv sync' first." >&2
  exit 1
fi

run_colab() {
  HOME="$COLAB_HOME" "$COLAB_BIN" \
    --config "$COLAB_CFG" \
    --client-oauth-config "$COLAB_OAUTH" \
    "$@"
}

usage() {
  cat <<'EOF'
Usage:
  bash access.sh sessions
  bash access.sh status [SESSION]
  bash access.sh console [SESSION]
  bash access.sh stop [SESSION]
  bash access.sh exec [SESSION] -- <code>
  bash access.sh raw <colab-args...>

Defaults:
  SESSION defaults to vllm-colab when omitted.
EOF
}

cmd="${1:-help}"
shift || true

case "$cmd" in
  sessions)
    run_colab sessions
    ;;
  status)
    session="${1:-vllm-colab}"
    run_colab status --session "$session"
    ;;
  console)
    session="${1:-vllm-colab}"
    run_colab console --session "$session"
    ;;
  stop)
    session="${1:-vllm-colab}"
    run_colab stop --session "$session"
    ;;
  exec)
    session="${1:-vllm-colab}"
    if [ "${2:-}" = "--" ]; then
      shift 2
    else
      shift 1
    fi
    if [ "$#" -eq 0 ]; then
      echo "Error: provide code after --" >&2
      exit 1
    fi
    printf '%s\n' "$*" | run_colab exec --session "$session"
    ;;
  raw)
    run_colab "$@"
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    usage
    exit 1
    ;;
esac
