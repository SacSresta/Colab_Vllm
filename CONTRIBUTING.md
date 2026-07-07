# Contributing

## Development Setup

1. Install dependencies:
   ```bash
   uv sync
   ```
2. Create your local env file:
   ```bash
   cp .env.example .env
   ```
3. Run deploy flow:
   ```bash
   bash deploy.sh
   ```

## Before Opening a PR

Run local checks:

```bash
bash -n deploy.sh access.sh
python -m py_compile main.py remote_tunnel.py local_proxy.py
```

Ensure docs match behavior:

- `README.md` updated if commands or env vars changed
- `.env.example` updated if config changed

## Commit Style

Prefer conventional commit prefixes:

- `feat:`
- `fix:`
- `docs:`
- `chore:`
- `refactor:`

## Security

- Never commit `.env` or tokens.
- Treat OAuth codes and session artifacts as sensitive.
