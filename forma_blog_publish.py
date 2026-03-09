#!/usr/bin/env python3
"""
forma_blog_publish.py
=====================
Runs on merge of a draft/post-* branch to main.
Clears status="draft" → "published" on all posts so Netlify builds them live.

Called by the blog-publish GitHub Actions workflow.
"""

import json
from pathlib import Path
from datetime import date

MANIFEST_FILE = Path("posts_manifest.json")

def main():
    if not MANIFEST_FILE.exists():
        print("❌ posts_manifest.json not found"); raise SystemExit(1)

    posts = json.loads(MANIFEST_FILE.read_text())
    changed = 0

    for post in posts:
        if post.get("status") == "draft":
            post["status"]    = "published"
            post["published"] = date.today().isoformat()
            changed += 1
            print(f"  ✓ Published: {post.get('title', post.get('slug', '?'))}")

    if changed == 0:
        print("  Nothing to publish (no draft posts found)")
    else:
        MANIFEST_FILE.write_text(json.dumps(posts, indent=2, ensure_ascii=False))
        print(f"\n✓ {changed} post(s) marked published")

if __name__ == "__main__":
    main()
