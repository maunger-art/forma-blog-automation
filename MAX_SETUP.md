# Forma blog engine on the Claude Max plan

This engine used to call `api.anthropic.com` with an `ANTHROPIC_API_KEY`. That key is
unfunded, so scheduled generation stopped. It now runs on a **Claude Max subscription**
via Claude Code headless (`claude -p`) — no metered API bill. The swap is isolated to
one shim file, `llm.py`.

## What changed
- **`llm.py`** — new. Routes both the engine's call styles through `claude -p`:
  - `llm.complete(prompt, ...)` for the raw-`urllib` scripts;
  - a drop-in `anthropic.Anthropic` class for the SDK scripts.
- **Live scripts migrated** (the three wired to crons):
  - `content_generator.py` — `call_api()` now uses `llm.complete()`; API-key guard removed.
  - `generate_weekly_post.py` — `import anthropic` → `import llm as anthropic`; key guard removed.
  - `generate_topic_queue.py` — title polish now runs on Max (fails safe to deterministic titles).
- **3 workflows** — `content_publish.yml`, `blog-publish.yml`, `topic-queue-refill.yml` now
  install Claude Code and pass `CLAUDE_CODE_OAUTH_TOKEN` instead of `ANTHROPIC_API_KEY`.
- Also migrated (not on any active cron, but now consistent): `pillar_content_fill.py`,
  `backlink_engine.py`, `forma_blog_scheduler.py`. Every generation path in the repo now runs on Max.

## One-time setup (before the crons go green)
1. On a machine logged into Max: `claude setup-token` (prints a 1-year token).
2. Repo → Settings → Secrets and variables → Actions → New secret:
   name `CLAUDE_CODE_OAUTH_TOKEN`, paste the token.
3. (Optional) delete the old `ANTHROPIC_API_KEY` secret.

## Test locally first
On your Mac (already `claude login`-ed to Max), no token needed:
```bash
python3 content_generator.py --batch 1     # uses your Max session via `claude -p`
```
Model defaults to `sonnet`; the old weekly-post used opus — set `LLM_MODEL=opus` for long-form:
```bash
LLM_MODEL=opus python generate_weekly_post.py
```

## Caveats
- Renew the token ~yearly (`claude setup-token`); ~5-day expiry warning.
- Use plain `claude -p` in CI (the shim does) — not `--bare`, which ignores the token.
- Keep volume modest and confirm Anthropic's ToS covers scheduled subscription use before scaling.
