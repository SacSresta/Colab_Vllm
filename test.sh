#!/bin/bash
set -euo pipefail

# 1. Load and export variables from .env
if [ -f .env ]; then
    echo "Loading configuration from .env..."
    set -a
    source .env
    set +a
else
    echo "Error: .env file not found. Please create one."
    exit 1
fi

# 2. Basic validation to ensure variables are set
if [ -z "$MODEL_NAME" ]; then
    echo "Error: MODEL_NAME is not set in .env"
    exit 1
fi

if [ -z "$HF_TOKEN" ]; then
    echo "Error: HF_TOKEN is not set in .env"
    exit 1
fi

TRUST_REMOTE_CODE="${TRUST_REMOTE_CODE:-false}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-8192}"

echo "--- Preparing to serve $MODEL_NAME on port $PORT ---"

# 3. Ensure environment is set up (using uv)
VENV_DIR=".venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    uv venv $VENV_DIR
fi
source $VENV_DIR/bin/activate

# Keep Hugging Face auth available to both vLLM and transformers.
export HUGGINGFACE_HUB_TOKEN="$HF_TOKEN"
export HF_TOKEN="$HF_TOKEN"

# 4. Install/Update vLLM (runs quickly if already installed)
echo "Ensuring vLLM is installed..."
uv pip install vllm

# 5. Check that the token can actually access the requested model before starting vLLM.
.venv/bin/python - <<'PY'
import os
import sys

from huggingface_hub.errors import HfHubHTTPError, LocalEntryNotFoundError
from huggingface_hub import hf_hub_download

model_name = os.environ["MODEL_NAME"]
token = os.environ["HF_TOKEN"]

try:
    hf_hub_download(repo_id=model_name, filename="config.json", token=token)
except (HfHubHTTPError, LocalEntryNotFoundError) as exc:
    root_exc = exc.__cause__ or exc
    message = str(root_exc)
    if "403" in message or "gated" in message.lower():
        print(f"Error: HF_TOKEN does not have access to {model_name}.")
        print("Enable access to public gated repositories for this token, or set MODEL_NAME to a public model.")
    else:
        print(f"Error: unable to reach {model_name}: {exc}")
    sys.exit(1)
PY

# 6. Launch the server using the variables
# We pass the variables directly to the vllm command
serve_args=("$MODEL_NAME" \
    --port "$PORT" \
    --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION" \
    --hf-token "$HF_TOKEN" \
    --max-model-len "$MAX_MODEL_LEN" \
    --dtype auto)

if [ "$TRUST_REMOTE_CODE" = "true" ]; then
    serve_args+=(--trust-remote-code)
fi

vllm serve "${serve_args[@]}"