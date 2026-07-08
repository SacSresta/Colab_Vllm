# v0.1.0 - Initial Public Release

## What This Project Does

Run `vLLM` on a Google Colab GPU and expose an OpenAI-compatible endpoint on your local machine:

- Local endpoint: `http://127.0.0.1:8000/v1`
- Remote inference: Colab GPU session

## Highlights

- One-command deploy: `bash deploy.sh`
- Colab session lifecycle + remote launcher orchestration
- Cloudflare quick tunnel from Colab VM
- Local reverse proxy for localhost-compatible API usage
- Helper command wrapper for session operations: `bash access.sh ...`

## Core Commands

```bash
# deploy
bash deploy.sh

# verify
curl http://127.0.0.1:8000/v1/models

# session access
bash access.sh sessions
bash access.sh status
bash access.sh console
```

## Notes

- First run requires Colab OAuth.
- Quick tunnel URL is public; local proxy binds to `127.0.0.1`.
- Use `.env.example` to bootstrap config.

## Known Constraints

- Depends on Colab CLI and Colab VM availability.
- Tunnel DNS/propagation can take a short warm-up period.
