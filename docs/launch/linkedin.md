I just open-sourced a new project: **vLLM on Colab with a local OpenAI-compatible endpoint**.

It lets you run open-source models on Google Colab GPU while keeping local developer ergonomics.

What it does in one command (`bash deploy.sh`):
- sets up/reuses a Colab session
- installs and launches vLLM remotely
- creates a tunnel from Colab
- exposes `http://127.0.0.1:8000/v1` locally

Quickstart:
```bash
uv sync
cp .env.example .env
bash deploy.sh
curl http://127.0.0.1:8000/v1/models
```

Repo: <PASTE_GITHUB_URL>

I’d value feedback from anyone building with open-source LLM serving stacks.
