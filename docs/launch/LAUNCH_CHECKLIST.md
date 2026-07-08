# Launch Checklist

## Before Opening Public Access

- [ ] `README.md` is accurate and tested
- [ ] `.env.example` exists and matches runtime settings
- [ ] `LICENSE` is present
- [ ] CI workflow is in repo and passing
- [ ] No secrets in git history (`.env`, tokens, OAuth codes)
- [ ] Repo visibility set to Public

## GitHub Release Steps

1. Confirm clean branch:
   ```bash
   git status
   ```
2. Tag release:
   ```bash
   git tag -a v0.1.0 -m "First public release"
   git push origin v0.1.0
   ```
3. Create GitHub release and paste `RELEASE_NOTES_v0.1.0.md`.

## Announcement Targets

- Hacker News (`Show HN`)
- Reddit (`r/LocalLLaMA`, `r/MachineLearning`, follow rules)
- X (thread)
- LinkedIn

Announcement drafts are in `docs/launch/`.
