#!/usr/bin/env python3
"""
generate_weekly_post.py
=======================
Reads the next topic from blog_topic_queue.txt, generates a blog post
via the Anthropic API, appends it to forma_blog_posts.md, and removes
the used topic from the queue.

Exit codes:
  0  — post generated successfully, OR no topic queued (skip gracefully)
  1  — error (missing API key, API failure, file write error)
"""

import os
import re
import sys
from pathlib import Path
import anthropic

QUEUE_FILE  = Path("blog_topic_queue.txt")
POSTS_FILE  = Path("forma_blog_posts.md")
MODEL       = "claude-opus-4-20250514"
MAX_TOKENS  = 4096

def load_queue() -> list:
    if not QUEUE_FILE.exists():
        return []
    return [l.strip() for l in QUEUE_FILE.read_text(encoding="utf-8").splitlines()
            if l.strip()]

def save_queue(lines: list):
    QUEUE_FILE.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

def next_post_number() -> int:
    if not POSTS_FILE.exists():
        return 1
    content = POSTS_FILE.read_text(encoding="utf-8")
    numbers = [int(m) for m in re.findall(r"^## (\d+)\.", content, re.MULTILINE)]
    return max(numbers, default=0) + 1

def generate_post(topic: str) -> tuple:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY environment variable is not set.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""You are writing a blog post for Forma, an AI-powered adaptive training app
for endurance athletes (runners and cyclists).

Brand voice: direct, science-backed, anti-hype. Write like a smart coach who has
read the research — not a journalist. Use real numbers and mechanisms. Avoid
motivational fluff. The reader trains 5–10 hours per week and wants to understand
their body, not just be told what to do.

Topic: {topic}

Requirements:
- 700–1000 words of body content
- Use markdown section headings (## for main sections, ### for subsections)
- Open with a strong counterintuitive hook or a common mistake
- Include at least one concrete example with real numbers
- End with a practical takeaway that connects to readiness-driven training
- Do NOT use motivational clichés ("push through", "dig deep", "no pain no gain")
- Do NOT include a top-level # heading — that will be generated separately

Return ONLY two lines followed by the article body, in this exact format:
TITLE: <the blog post title, 50-65 chars, includes primary keyword>
---
<markdown body starting immediately, no preamble>"""

    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()
    lines = raw.splitlines()
    title_line = lines[0] if lines else ""

    if title_line.upper().startswith("TITLE:"):
        title = title_line[6:].strip()
        separator_idx = next(
            (i for i, l in enumerate(lines) if l.strip() == "---"), 1
        )
        body = "\n".join(lines[separator_idx + 1:]).strip()
    else:
        title = topic
        body = raw

    return title, body

def main():
    print("=" * 56)
    print("  Forma Weekly Post Generator")
    print("=" * 56)

    queue = load_queue()

    if not queue:
        print("ℹ️  No topics queued — nothing to do.")
        sys.exit(0)

    topic = queue[0]
    remaining = queue[1:]
    post_number = next_post_number()

    print(f"  Topic     : {topic}")
    print(f"  Post #    : {post_number}")
    print(f"  Queue left: {len(remaining)} after this")
    print()

    print("🤖 Calling Anthropic API...")
    title, body = generate_post(topic)
    print(f"  ✓ Title: {title}")
    print(f"  ✓ Body : {len(body.split())} words")

    # Append to forma_blog_posts.md
    separator = "\n\n---\n\n" if POSTS_FILE.exists() else ""
    new_section = f"{separator}## {post_number}. {title}\n\n{body}\n"
    with open(POSTS_FILE, "a", encoding="utf-8") as f:
        f.write(new_section)
    print(f"  ✓ Appended to {POSTS_FILE}")

    save_queue(remaining)
    print(f"  ✓ Queue updated ({len(remaining)} topics remaining)")

    # Flag file so workflow knows a post was generated
    Path(".post_generated").write_text(title, encoding="utf-8")

    print()
    print("=" * 56)
    print(f"  ✅ Post #{post_number} ready for build")
    print("=" * 56)

if __name__ == "__main__":
    main()
