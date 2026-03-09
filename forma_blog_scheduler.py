#!/usr/bin/env python3
"""
Forma Blog Scheduler  v1
========================
Runs on a cron schedule (every 2 weeks via GitHub Actions).

What it does:
  1. Reads content_calendar.json → picks the next category in rotation
  2. Reads posts_manifest.json → builds list of already-published titles
  3. Calls Anthropic API → generates a complete, SEO-optimised blog post
  4. Appends new post to posts_manifest.json
  5. Commits to a draft branch + opens a GitHub Pull Request
  6. GitHub emails you the PR link for review → merge to publish

Usage (local test):
    ANTHROPIC_API_KEY=sk-... python forma_blog_scheduler.py

Required env vars (set as GitHub Actions secrets):
    ANTHROPIC_API_KEY   — Anthropic API key
    GITHUB_TOKEN        — auto-provided by GitHub Actions (for PR creation)
    GITHUB_REPOSITORY   — auto-provided (e.g. maunger-art/forma-blog-automation)
"""

import os
import re
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import anthropic
from slugify import slugify

# ── Config ────────────────────────────────────────────────────────────────────
CALENDAR_FILE  = Path("content_calendar.json")
MANIFEST_FILE  = Path("posts_manifest.json")
MODEL          = "claude-opus-4-20250514"
MAX_TOKENS     = 8000
TODAY          = date.today().isoformat()
BRAND_NAME     = "Forma"
SITE_URL       = "https://formafit.co.uk"

# ── Load files ────────────────────────────────────────────────────────────────
def load_calendar() -> dict:
    if not CALENDAR_FILE.exists():
        print(f"❌ {CALENDAR_FILE} not found"); raise SystemExit(1)
    return json.loads(CALENDAR_FILE.read_text())

def load_manifest() -> list:
    if not MANIFEST_FILE.exists():
        print("⚠  posts_manifest.json not found — starting fresh")
        return []
    return json.loads(MANIFEST_FILE.read_text())

def save_calendar(cal: dict):
    CALENDAR_FILE.write_text(json.dumps(cal, indent=2, ensure_ascii=False))

def save_manifest(posts: list):
    MANIFEST_FILE.write_text(json.dumps(posts, indent=2, ensure_ascii=False))

# ── Pick next category ────────────────────────────────────────────────────────
def pick_category(cal: dict) -> dict:
    rotation = cal["category_rotation"]
    idx = cal.get("next_category_index", 0) % len(rotation)
    category = rotation[idx]
    print(f"✓ Category {idx + 1}/{len(rotation)}: {category['label']}")
    return category, idx

# ── Generate post via Anthropic API ──────────────────────────────────────────
def generate_post(category: dict, existing_posts: list, cal: dict) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    existing_titles = [p.get("title", "") for p in existing_posts if p.get("title")]
    existing_str = "\n".join(f"- {t}" for t in existing_titles) if existing_titles else "None yet."

    tone   = cal.get("tone_guidelines", "")
    content_rules = "\n".join(cal.get("content_guidelines", []))
    seo_rules     = "\n".join(cal.get("seo_guidelines", []))

    print(f"  Calling Anthropic API ({MODEL})...")

    prompt = f"""You are a content strategist and expert writer for {BRAND_NAME}, an AI-powered adaptive training app for endurance athletes (runners and cyclists). You are writing a high-quality blog post for {BRAND_NAME}'s blog at blog.formafit.co.uk.

BRAND VOICE:
{tone}

CATEGORY FOR THIS POST: {category['label']}
CATEGORY DESCRIPTION: {category['description']}

ALREADY PUBLISHED POSTS (do NOT repeat these topics — pick something fresh and distinct):
{existing_str}

CONTENT RULES:
{content_rules}

SEO RULES:
{seo_rules}

TODAY'S DATE: {TODAY}

---

Your task: Generate ONE complete, publication-ready blog post in this EXACT JSON format. Return ONLY valid JSON, no markdown fences, no preamble.

{{
  "title": "string — 50-65 chars, includes primary keyword, compelling, not clickbait",
  "meta_description": "string — 150-160 chars, includes keyword, entices click",
  "category": "{category['label']}",
  "keywords": "comma-separated list of 6-8 target keywords",
  "read_time": integer (estimated minutes),
  "toc_items": [
    {{"id": "section-slug", "text": "Section heading text"}}
  ],
  "body_html": "FULL article HTML. Requirements:
    - Use <h2 id='section-slug'> for main sections (IDs must match toc_items)
    - Use <h3> for subsections
    - Use <p> for paragraphs
    - Use <ul>/<li> or <ol>/<li> for lists
    - Use <strong> for emphasis (sparingly)
    - Use <hr> between major sections if needed
    - Do NOT include <h1> (the title is rendered separately)
    - Do NOT include any outer wrapper divs
    - 1500-2000 words of body content
    - End with a section about how {BRAND_NAME}'s readiness system connects to this topic
    - The final section ID must be 'forma-and-this-topic' or similar
    - Make it genuinely useful, specific, and science-backed"
}}"""

    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()

    # Strip any accidental markdown fences
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        post_data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"❌ JSON parse error: {e}")
        print("Raw response (first 500 chars):", raw[:500])
        raise SystemExit(1)

    # Add metadata
    post_data["slug"]        = slugify(post_data["title"])
    post_data["date"]        = TODAY
    post_data["generated"]   = datetime.utcnow().isoformat() + "Z"
    post_data["category_id"] = category["id"]
    post_data["status"]      = "draft"

    print(f"  ✓ Generated: \"{post_data['title']}\"")
    print(f"  ✓ Slug: {post_data['slug']}")
    print(f"  ✓ Read time: {post_data.get('read_time', '?')} min")
    return post_data

# ── Git operations ────────────────────────────────────────────────────────────
def run(cmd: str, **kwargs) -> str:
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, **kwargs)
    if result.returncode != 0:
        print(f"❌ Command failed: {cmd}")
        print(result.stderr)
        raise SystemExit(1)
    return result.stdout.strip()

def create_pr(branch: str, title: str, body: str) -> str:
    """Create a GitHub PR using the gh CLI (available in GitHub Actions)."""
    # Write PR body to a temp file to avoid shell escaping issues
    pr_body_file = Path("/tmp/pr_body.md")
    pr_body_file.write_text(body)

    result = subprocess.run(
        f'gh pr create --base main --head "{branch}" --title "{title}" --body-file /tmp/pr_body.md',
        shell=True, capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"⚠  PR creation failed: {result.stderr}")
        return ""
    pr_url = result.stdout.strip()
    print(f"  ✓ PR created: {pr_url}")
    return pr_url

def push_draft_branch(post: dict, cal: dict, category_idx: int) -> str:
    """Commit updated manifest + calendar to a draft branch, open a PR."""
    slug   = post["slug"]
    branch = f"draft/post-{TODAY}-{slug[:40]}"

    # Configure git identity (needed in CI)
    run('git config user.email "bot@formafit.co.uk"')
    run('git config user.name "Forma Blog Bot"')

    # Create and switch to draft branch
    run(f'git checkout -b "{branch}"')

    # Stage updated files
    run(f'git add {MANIFEST_FILE} {CALENDAR_FILE}')
    run(f'git commit -m "draft: {post["title"][:72]}"')
    run(f'git push origin "{branch}"')

    # Build PR description
    toc_preview = "\n".join(
        f"- {item['text']}" for item in post.get("toc_items", [])
    )

    pr_body = f"""## 📝 New Blog Post Ready for Review

**Title:** {post['title']}
**Category:** {post['category']}
**Read time:** {post.get('read_time', '?')} min
**Slug:** `{slug}`
**URL (after merge):** https://blog.formafit.co.uk/blog/{slug}.html

---

### Contents
{toc_preview}

---

### Meta description
> {post.get('meta_description', '')}

---

### Keywords
`{post.get('keywords', '')}`

---

## To publish
1. Review the post below (check `posts_manifest.json` diff for full HTML)
2. Happy with it? Click **Merge pull request**
3. Netlify auto-deploys — live in ~60 seconds ✅

## To request changes
- Comment on this PR with what to change
- Or edit `posts_manifest.json` directly on this branch

---
*Generated by Forma Blog Bot on {TODAY}. Category: {category_idx + 1}/{len(cal['category_rotation'])} in rotation.*
"""

    pr_title = f"[Blog Draft] {post['title']}"
    pr_url   = create_pr(branch, pr_title, pr_body)
    return pr_url

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  Forma Blog Scheduler  v1")
    print("=" * 60)
    print(f"  Date: {TODAY}")
    print()

    # Validate env
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("❌ ANTHROPIC_API_KEY not set"); raise SystemExit(1)

    # Load state
    cal   = load_calendar()
    posts = load_manifest()

    print(f"  Existing posts: {len(posts)}")

    # Pick category
    category, cat_idx = pick_category(cal)

    # Generate post
    print(f"\n🤖 Generating post...")
    post = generate_post(category, posts, cal)

    # Append to manifest
    posts.append(post)
    save_manifest(posts)
    print(f"\n✓ Manifest updated ({len(posts)} posts total)")

    # Advance rotation index
    cal["next_category_index"] = (cat_idx + 1) % len(cal["category_rotation"])
    cal["generation_history"].append({
        "date": TODAY,
        "title": post["title"],
        "slug": post["slug"],
        "category": category["label"]
    })
    save_calendar(cal)
    print(f"  ✓ Next category: {cal['category_rotation'][cal['next_category_index']]['label']}")

    # Push draft branch + open PR (only in CI)
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"\n🔀 Creating draft branch and PR...")
        pr_url = push_draft_branch(post, cal, cat_idx)
        print(f"\n{'=' * 60}")
        print(f"  ✅  Done — PR opened for review")
        print(f"  {pr_url}")
        print(f"{'=' * 60}")
    else:
        print(f"\n{'=' * 60}")
        print(f"  ✅  Done — post generated locally")
        print(f"  Title: {post['title']}")
        print(f"  Slug:  {post['slug']}")
        print(f"  (Run in GitHub Actions to auto-create PR)")
        print(f"{'=' * 60}")

if __name__ == "__main__":
    main()
