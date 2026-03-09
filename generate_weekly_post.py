#!/usr/bin/env python3
"""
generate_weekly_post.py  v3
===========================
Reads the next topic from blog_topic_queue.txt, generates a full blog post
via the Anthropic API, appends it to forma_blog_posts.md, AND updates
posts_manifest.json so the builder picks it up immediately.

Exit codes:
  0  — post generated (sets .post_generated flag), OR queue empty (no-op)
  1  — fatal error (missing API key, API failure, write error)
"""

import hashlib
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import anthropic

QUEUE_FILE    = Path("blog_topic_queue.txt")
POSTS_FILE    = Path("forma_blog_posts.md")
MANIFEST_FILE = Path("posts_manifest.json")
FLAG_FILE     = Path(".post_generated")
MODEL         = "claude-opus-4-20250514"
TODAY         = date.today().isoformat()


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_queue() -> list:
    if not QUEUE_FILE.exists():
        return []
    return [l.strip() for l in QUEUE_FILE.read_text(encoding="utf-8").splitlines()
            if l.strip()]

def save_queue(lines: list):
    QUEUE_FILE.write_text(
        "\n".join(lines) + ("\n" if lines else ""),
        encoding="utf-8"
    )

def next_post_number() -> int:
    if not POSTS_FILE.exists():
        return 1
    content = POSTS_FILE.read_text(encoding="utf-8")
    numbers = [int(m) for m in re.findall(r"^## (\d+)\.", content, re.MULTILINE)]
    return max(numbers, default=0) + 1

def load_manifest() -> list:
    if not MANIFEST_FILE.exists():
        return []
    return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))

def slug_from_title(title: str) -> str:
    s = title.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:80]

def hash_text(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()

def word_count_to_read_time(text: str) -> int:
    words = len(text.split())
    return max(1, round(words / 200))


# ── API call ──────────────────────────────────────────────────────────────────

def generate_post(topic: str) -> dict:
    """
    Calls Anthropic once and gets back a full structured post as JSON.
    Returns a dict with all fields needed for both the markdown file
    and the posts_manifest.json entry.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌  ANTHROPIC_API_KEY is not set.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""You are writing a blog post for Forma, an AI-powered adaptive training app
for endurance athletes (runners and cyclists).

Brand voice: direct, science-backed, no hype. Write like a smart coach who has read
the research. Use real numbers and mechanisms. The reader trains 5–10 hours per week.

Topic: {topic}

Return ONLY valid JSON — no markdown fences, no preamble, nothing else.
Use this exact schema:

{{
  "title": "60-80 char SEO title including primary keyword",
  "slug": "url-slug-from-title",
  "category": "one of: Training Science | Recovery | Wearables | Performance | Mindset | HRV",
  "meta_description": "150-160 char meta description",
  "keywords": "5-8 comma-separated keywords",
  "read_time": <integer minutes>,
  "body_markdown": "700-1000 word markdown article with ## section headings. Strong counterintuitive hook. At least one concrete example with real numbers. Practical takeaway at the end. No motivational clichés. No top-level # heading.",
  "toc_items": [
    {{"id": "heading-slug", "text": "Heading Text"}}
  ]
}}

The toc_items should list every ## heading in the body_markdown, with id being
the heading text lowercased, spaces replaced with hyphens, punctuation removed."""

    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()

    # Strip any accidental fences
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"```\s*$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"❌  JSON parse error: {e}")
        print(f"    Raw response (first 500 chars): {raw[:500]}")
        sys.exit(1)

    return data


# ── Convert markdown body to HTML (minimal, matches existing builder style) ──

def md_to_html(md: str) -> str:
    """
    Very lightweight markdown → HTML.
    Uses the `markdown` library if available (it's in requirements.txt).
    """
    try:
        import markdown as md_lib
        html = md_lib.markdown(md, extensions=["extra"])
        # Add heading IDs for TOC scrollspy
        html = re.sub(
            r'<h2>(.*?)</h2>',
            lambda m: f'<h2 id="{re.sub(r"[^a-z0-9]+", "-", m.group(1).lower()).strip("-")}">{m.group(1)}</h2>',
            html
        )
        return html
    except ImportError:
        # Bare-minimum fallback
        lines = []
        for line in md.splitlines():
            if line.startswith("## "):
                heading = line[3:].strip()
                hid = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")
                lines.append(f'<h2 id="{hid}">{heading}</h2>')
            elif line.startswith("### "):
                lines.append(f'<h3>{line[4:].strip()}</h3>')
            elif line.strip():
                lines.append(f'<p>{line.strip()}</p>')
        return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 56)
    print("  Forma Weekly Post Generator  v3")
    print("=" * 56)

    queue = load_queue()

    if not queue:
        print("ℹ️   No topics queued — nothing to do.")
        print("    Add topics (one per line) to blog_topic_queue.txt")
        FLAG_FILE.unlink(missing_ok=True)
        sys.exit(0)

    topic      = queue[0]
    remaining  = queue[1:]
    post_number = next_post_number()

    print(f"  Topic     : {topic}")
    print(f"  Post #    : {post_number}")
    print(f"  Queue left: {len(remaining)} after this")
    print()
    print("🤖  Calling Anthropic API...")

    post_data = generate_post(topic)

    title         = post_data.get("title", topic)
    slug          = post_data.get("slug") or slug_from_title(title)
    category      = post_data.get("category", "Training Science")
    meta_desc     = post_data.get("meta_description", "")
    keywords      = post_data.get("keywords", "")
    body_md       = post_data.get("body_markdown", "")
    toc_items     = post_data.get("toc_items", [])
    read_time     = post_data.get("read_time") or word_count_to_read_time(body_md)

    body_html = md_to_html(body_md)

    print(f"  ✓ Title    : {title}")
    print(f"  ✓ Slug     : {slug}")
    print(f"  ✓ Category : {category}")
    print(f"  ✓ Words    : {len(body_md.split())}")
    print(f"  ✓ Read time: {read_time} min")

    # ── 1. Append to forma_blog_posts.md ─────────────────────────────────────
    separator = "\n\n---\n\n" if POSTS_FILE.exists() else ""
    new_section = f"{separator}## {post_number}. {title}\n\n{body_md}\n"
    with open(POSTS_FILE, "a", encoding="utf-8") as f:
        f.write(new_section)
    print(f"\n  ✓ Appended post #{post_number} to {POSTS_FILE}")

    # ── 2. Update posts_manifest.json ────────────────────────────────────────
    manifest = load_manifest()

    # Guard: don't add duplicate slugs
    existing_slugs = {p.get("slug") for p in manifest}
    if slug in existing_slugs:
        slug = f"{slug}-{post_number}"
        print(f"  ⚠  Slug collision — using: {slug}")

    new_entry = {
        "slug":             slug,
        "title":            title,
        "category":         category,
        "meta_description": meta_desc,
        "keywords":         keywords,
        "read_time":        read_time,
        "date":             TODAY,
        "status":           "published",
        "body_html":        body_html,
        "toc_items":        toc_items,
        "hash":             hash_text(body_md),
    }

    manifest.append(new_entry)
    MANIFEST_FILE.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"  ✓ posts_manifest.json updated — {len(manifest)} total posts")

    # ── 3. Remove used topic from queue ──────────────────────────────────────
    save_queue(remaining)
    print(f"  ✓ Queue updated ({len(remaining)} topics remaining)")

    # ── 4. Write flag for workflow ────────────────────────────────────────────
    FLAG_FILE.write_text(title, encoding="utf-8")

    print()
    print("=" * 56)
    print(f"  ✅  Post #{post_number} ready — manifest updated")
    print("=" * 56)


if __name__ == "__main__":
    main()
