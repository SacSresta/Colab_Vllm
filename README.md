# vLLM on Colab with a Local Endpoint

Run open-source LLMs on a Google Colab GPU using `vLLM`, and call them locally via an OpenAI-compatible endpoint.

## How It Works

`deploy.sh` does the full flow:

1. Reuse or create a Colab session.
2. Install/validate `vllm` in Colab.
3. Start `vllm serve` remotely.
4. Create a Cloudflare quick tunnel from Colab.
5. Start a local proxy on `127.0.0.1` that forwards to that tunnel.

Your app calls:

- `http://127.0.0.1:8000/v1`

while inference runs on Colab GPU.

## Prerequisites

- Linux or macOS
- Python 3.12+
- `uv`
- Colab account (OAuth login on first run)

Install dependencies:

```bash
uv sync
```

## Configuration

Create `.env` from the example:

```bash
cp .env.example .env
```

Then edit values as needed:

```env
MODEL_NAME=Qwen/Qwen2.5-0.5B-Instruct
PORT=8000
GPU_MEMORY_UTILIZATION=0.50
TRUST_REMOTE_CODE=false
MAX_MODEL_LEN=8192
```

Optional:

- `HF_TOKEN` for gated/private Hugging Face models.

## Quick Start

```bash
bash deploy.sh
curl http://127.0.0.1:8000/v1/models
```

## Useful Overrides

```bash
# different accelerator/session name
COLAB_GPU=L4 COLAB_SESSION_NAME=my-vllm-session bash deploy.sh

# different local port
LOCAL_BIND_PORT=8010 bash deploy.sh

# slower environments
COLAB_INSTALL_TIMEOUT=3600 COLAB_BOOT_TIMEOUT=300 COLAB_TUNNEL_TIMEOUT=400 bash deploy.sh
```

## Console Access

Use the helper script so you always use the same Colab state as `deploy.sh`:

```bash
bash access.sh sessions
bash access.sh status
bash access.sh console
```

## Repo Layout

Core files for this workflow:

- `deploy.sh`: end-to-end Colab deploy and local bind
- `main.py`: remote vLLM launcher
- `remote_tunnel.py`: starts cloudflared tunnel on Colab
- `local_proxy.py`: local reverse proxy
- `access.sh`: short commands for status/console/sessions

## Runtime Files (Ignored by Git)

- `.colab_state/`
- `.local-vllm-proxy.pid`
- `local-vllm-proxy.log`
- `vllm.log`

## Troubleshooting

- `502 Bad Gateway` from tunnel URL:
  Colab origin is not reachable yet. Check `/content/vllm.log` and `/content/cloudflared-vllm.log` in Colab.
- `ImportError: libcudart.so.13`:
  CUDA runtime mismatch. The deploy flow now installs runtime libs and sets `LD_LIBRARY_PATH` automatically.
- `colab console` cannot find session:
  use `bash access.sh console` instead of plain `colab console`.

## Security Notes

- Never commit `.env` or tokens.
- Treat OAuth auth codes as sensitive.
- Cloudflare quick tunnel URL is public; local proxy binds to `127.0.0.1`.

## Contributing

See [CONTRIBUTING.md](/media/sacsresta/48F9473C7383F9492/vllm_colab/CONTRIBUTING.md).
