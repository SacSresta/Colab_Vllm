# Repository Guidelines

## Project Structure & Module Organization

This repository is intentionally small and script-driven.

- `deploy.sh`: end-to-end Colab deployment and local endpoint binding.
- `main.py`: remote vLLM launcher executed inside Colab.
- `remote_tunnel.py`: starts and validates the Cloudflare tunnel in Colab.
- `local_proxy.py`: local reverse proxy to expose `/v1` on localhost.
- `access.sh`: helper wrapper for `sessions`, `status`, and `console` using repo-local Colab state.
- `docs/launch/`: public launch and distribution materials.

Runtime files such as `.colab_state/`, logs, and PID files are local-only and must stay out of version control.

## Build, Test, and Development Commands

- `uv sync`: install project dependencies.
- `bash deploy.sh`: launch/reuse Colab session and expose local endpoint.
- `bash access.sh sessions|status|console`: inspect and access active Colab session.
- `bash -n deploy.sh access.sh`: shell syntax checks.
- `.venv/bin/python -m py_compile main.py remote_tunnel.py local_proxy.py`: Python syntax checks.

## Coding Style & Naming Conventions

- Use Python 3.12-compatible code and Bash with `set -euo pipefail`.
- Prefer clear, minimal scripts over heavy abstraction.
- Keep configuration via environment variables (see `.env.example`).
- File names use snake_case for Python and lowercase shell script names.

## Testing Guidelines

There is no formal unit-test suite yet. Minimum validation for changes:

1. Run syntax checks (`bash -n`, `py_compile`).
2. Run `bash deploy.sh` for behavior changes.
3. Verify endpoint health with `curl http://127.0.0.1:8000/v1/models`.

## Commit & Pull Request Guidelines

Use conventional commit prefixes: `feat:`, `fix:`, `docs:`, `chore:`.

PRs should include:

- concise summary of behavior changes,
- commands used for validation,
- README and `.env.example` updates when config/usage changes,
- confirmation that no secrets/tokens were committed.

## Security & Configuration Tips

Never commit `.env`, OAuth codes, or API tokens. Cloudflare quick tunnel URLs are public; local proxy should remain bound to `127.0.0.1`.
