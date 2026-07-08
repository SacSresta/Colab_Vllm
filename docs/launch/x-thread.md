1/ I open-sourced a tool to run vLLM on Google Colab GPU and consume it locally as an OpenAI-compatible endpoint (`http://127.0.0.1:8000/v1`).

2/ Why: Colab compute is easy to get, but integrating it into local dev workflows is usually manual.

3/ What it automates:
- Colab session lifecycle
- vLLM install + launch
- tunnel creation
- localhost proxy binding

4/ Quickstart:
```bash
uv sync
cp .env.example .env
bash deploy.sh
curl http://127.0.0.1:8000/v1/models
```

5/ Repo: <PASTE_GITHUB_URL>

6/ Feedback welcome on startup reliability, model support, and docs UX.
