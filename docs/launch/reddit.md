Title: Open-source: Run vLLM on Colab GPU and use it locally via OpenAI-compatible API

I open-sourced a small tool to run `vLLM` on Google Colab while exposing a local endpoint (`http://127.0.0.1:8000/v1`) for your apps.

Use case:
- You want to prototype with open-source models quickly
- You want local API ergonomics while compute runs on Colab

Core flow (`bash deploy.sh`):
1. Create/reuse Colab session
2. Install/validate vLLM remotely
3. Start vLLM in Colab
4. Create tunnel
5. Start local proxy

Quickstart:
```bash
uv sync
cp .env.example .env
bash deploy.sh
curl http://127.0.0.1:8000/v1/models
```

Repo: <PASTE_GITHUB_URL>

If you test it, I’d appreciate issue reports on model compatibility and startup reliability.
