"""
llm.py — Max-plan LLM shim for the Forma blog engine.

The engine used to call api.anthropic.com with an ANTHROPIC_API_KEY (two styles:
raw urllib in content_generator.py/pillar_content_fill.py/backlink_engine.py, and the
`anthropic` SDK in generate_weekly_post.py/generate_topic_queue.py/forma_blog_scheduler.py).
That key is unfunded, so generation stopped.

This shim routes both styles through Claude Code headless (`claude -p`), which
authenticates via a Claude Max subscription — no metered API bill:

  - Locally:  uses your interactive `claude login` session (no key needed).
  - In CI:    set CLAUDE_CODE_OAUTH_TOKEN (generated once via `claude setup-token`).

Two ways to adopt it:
  * SDK scripts:  change `import anthropic` -> `import llm as anthropic`
  * urllib scripts: call `llm.complete(prompt, max_tokens=...)` for the raw text

Env overrides:
  LLM_MODEL   model alias/id for `claude --model` (default "sonnet"; use "opus" for long-form)
  CLAUDE_BIN  path to the claude binary (default "claude")
  LLM_TIMEOUT per-call timeout seconds (default 300)
"""

import json
import os
import shutil
import subprocess

DEFAULT_MODEL = os.environ.get("LLM_MODEL", "sonnet")
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "300"))


class _Block:
    __slots__ = ("text", "type")

    def __init__(self, text: str):
        self.text = text
        self.type = "text"


class _Message:
    """Mimics anthropic's response object: .content[0].text"""

    def __init__(self, text: str):
        self.content = [_Block(text)]


def _build_prompt(system, messages) -> str:
    parts = []
    if system:
        parts.append(str(system).strip())
    for m in messages or []:
        content = m.get("content", "")
        if isinstance(content, list):
            content = "".join(
                b.get("text", "") if isinstance(b, dict) else str(b) for b in content
            )
        if content:
            parts.append(str(content))
    return "\n\n".join(parts)


def _run(prompt: str) -> str:
    if shutil.which(CLAUDE_BIN) is None:
        raise RuntimeError(
            f"'{CLAUDE_BIN}' not found on PATH. Install Claude Code "
            f"(`npm i -g @anthropic-ai/claude-code`) and either run `claude login` "
            f"(local) or set CLAUDE_CODE_OAUTH_TOKEN (CI, from `claude setup-token`)."
        )
    cmd = [
        CLAUDE_BIN, "-p", prompt,
        "--output-format", "json",
        "--model", os.environ.get("LLM_MODEL", DEFAULT_MODEL),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    if proc.returncode != 0:
        raise RuntimeError(
            f"`claude -p` failed (exit {proc.returncode}). "
            f"stderr: {proc.stderr.strip()[:800] or '(empty)'}"
        )
    out = proc.stdout.strip()
    try:
        envelope = json.loads(out)
    except json.JSONDecodeError:
        return out
    if isinstance(envelope, dict):
        if envelope.get("is_error"):
            raise RuntimeError(f"`claude -p` error: {envelope.get('result', out)[:800]}")
        return envelope.get("result", "")
    return out


def complete(prompt: str, system: str | None = None, max_tokens: int | None = None,
             model: str | None = None) -> str:
    """Return the model's text completion for a single prompt (Max plan)."""
    return _run(_build_prompt(system, [{"role": "user", "content": prompt}]))


class _Messages:
    def create(self, *, messages, model=None, system=None, max_tokens=None, **_ignored):
        return _Message(_run(_build_prompt(system, messages)))


class Anthropic:
    """Stand-in for anthropic.Anthropic(); accepts and ignores any init args (e.g. api_key)."""

    def __init__(self, *args, **kwargs):
        self.messages = _Messages()
