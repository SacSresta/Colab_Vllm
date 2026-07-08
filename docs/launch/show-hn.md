Title: Show HN: vLLM on Colab with a local OpenAI-compatible endpoint

I built a small open-source project that runs `vLLM` on a Google Colab GPU and exposes it as a local endpoint on your machine.

Why I built it:
- Colab GPU is convenient, but wiring local tooling to it is usually manual and fragile.
- I wanted one command to get a usable local `/v1` endpoint.

What it does:
- Creates/reuses a Colab session
- Installs/validates vLLM remotely
- Launches vLLM in Colab
- Opens a Cloudflare quick tunnel from Colab
- Binds local proxy to `http://127.0.0.1:8000/v1`

Quickstart:
```bash
uv sync
cp .env.example .env
bash deploy.sh
curl http://127.0.0.1:8000/v1/models
```

Repo: <PASTE_GITHUB_URL>

Would love feedback on reliability and UX for developer onboarding.
