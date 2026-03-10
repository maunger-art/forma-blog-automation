#!/usr/bin/env python3
"""
sync_blog_sources.py  v2
========================
Single source of truth: posts_manifest.json
forma_blog_posts.md is a human-readable archive only.
The builder (forma_blog_build.py) never reads .md.

What this checks:
  1. All manifest entries have body_html (critical for builder)
  2. Posts in .md not in manifest → add them
  3. Report if manifest and .md post counts diverge

Exit codes: 0 = clean/repaired, 1 = fatal
"""

import hashlib, json, re, sys
from pathlib import Path

POSTS_FILE    = Path("forma_blog_posts.md")
MANIFEST_FILE = Path("posts_manifest.json")


def slugify(text):
    s = text.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")[:80]


def md_to_html(md):
    try:
        import markdown as md_lib
        html = md_lib.markdown(md, extensions=["extra"])
        html = re.sub(
            r'<h2>(.*?)</h2>',
            lambda m: f'<h2 id="{re.sub(r"[^a-z0-9]+", "-", m.group(1).lower()).strip("-")}">{m.group(1)}</h2>',
            html
        )
        return html
    except ImportError:
        lines = []
        for line in md.splitlines():
            line = line.strip()
            if not line: continue
            if line.startswith("### "):
                h = line[4:]; hid = re.sub(r"[^a-z0-9]+","-",h.lower()).strip("-")
                lines.append(f'<h2 id="{hid}">{h}</h2>')
            elif line.startswith("## "):
                h = line[3:]; hid = re.sub(r"[^a-z0-9]+","-",h.lower()).strip("-")
                lines.append(f'<h2 id="{hid}">{h}</h2>')
            elif line.startswith(("- ","* ")):
                lines.append(f'<li>{line[2:].strip()}</li>')
            else:
                line = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', line)
                lines.append(f'<p>{line}</p>')
        return "\n".join(lines)


def extract_toc(html):
    return [{"id": m.group(1), "text": m.group(2)}
            for m in re.finditer(r'<h2[^>]*id="([^"]+)"[^>]*>(.*?)</h2>', html)]


def read_time(text):
    return max(1, round(len(text.split()) / 200))


def load_manifest():
    if not MANIFEST_FILE.exists(): return []
    try:
        return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"❌  Invalid JSON in manifest: {e}"); sys.exit(1)


def save_manifest(posts):
    MANIFEST_FILE.write_text(json.dumps(posts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_md_posts():
    """Parse .md file. Returns dict[slug → {number, title, slug, body_md}]."""
    if not POSTS_FILE.exists(): return {}
    content = POSTS_FILE.read_text(encoding="utf-8")
    posts = {}
    for section in re.split(r'\n(?=## \d+\.)', content):
        section = section.strip()
        if not section: continue
        m = re.match(r'^## (\d+)\.\s+(.+?)$', section, re.MULTILINE)
        if not m: continue
        number = int(m.group(1))
        title  = m.group(2).strip()
        slug   = slugify(title)
        body_start = section.find('\n', section.find(m.group(0))) + 1
        body_md = re.sub(r'\n---+\s*$', '', section[body_start:]).strip()
        posts[slug] = {"number": number, "title": title, "slug": slug, "body_md": body_md}
    return posts


def slug_words(s):
    return set(re.sub(r'[^a-z0-9]', ' ', s).split()) - {'the','a','an','and','or','for'}


def fuzzy_match(target_slug, slug_set, threshold=0.55):
    """Return True if target_slug is similar enough to any slug in slug_set."""
    if target_slug in slug_set: return True
    tw = slug_words(target_slug)
    for s in slug_set:
        sw = slug_words(s)
        if not tw or not sw: continue
        if len(tw & sw) / max(len(tw), len(sw)) >= threshold:
            return True
    return False


def main():
    print("=" * 60)
    print("  Forma Blog Source Sync  v2")
    print("=" * 60)

    manifest  = load_manifest()
    md_posts  = load_md_posts()
    manifest_slugs = {p.get("slug") for p in manifest}

    print(f"\n  posts_manifest.json : {len(manifest)} entries")
    print(f"  forma_blog_posts.md : {len(md_posts)} posts")

    repaired = []
    warnings = []
    modified = False

    # ── 1. Fix manifest entries missing body_html (builder will skip them) ────
    print("\n🔍  Checking for missing body_html in manifest...")
    for entry in manifest:
        slug = entry.get("slug", "")
        if entry.get("body_html"):
            continue

        print(f"  ⚠  [{slug}] missing body_html")
        # Find best .md match via fuzzy slug comparison
        md_match = md_posts.get(slug)
        if not md_match:
            for md_slug, md_post in md_posts.items():
                tw, mw = slug_words(slug), slug_words(md_slug)
                if tw and mw and len(tw & mw) / max(len(tw), len(mw)) >= 0.5:
                    md_match = md_post
                    print(f"     → Fuzzy matched to .md entry: [{md_slug}]")
                    break

        if md_match:
            html = md_to_html(md_match["body_md"])
            entry["body_html"] = html
            entry["toc_items"] = extract_toc(html)
            if not entry.get("read_time"):
                entry["read_time"] = read_time(md_match["body_md"])
            repaired.append(f"  ✓ Regenerated body_html for [{slug}]")
            modified = True
        else:
            warnings.append(f"  ✗ [{slug}] — no .md source found, needs manual fix")

    # ── 2. Posts in .md not represented in manifest at all ───────────────────
    print("🔍  Checking .md posts not in manifest...")
    for md_slug, md_post in md_posts.items():
        if fuzzy_match(md_slug, manifest_slugs):
            continue   # already covered

        print(f"  ⚠  [{md_slug}] in .md but not in manifest — adding")
        html = md_to_html(md_post["body_md"])
        manifest.append({
            "slug":             md_slug,
            "title":            md_post["title"],
            "category":         "Training Science",
            "meta_description": md_post["title"],
            "keywords":         "",
            "read_time":        read_time(md_post["body_md"]),
            "date":             "",
            "status":           "published",
            "body_html":        html,
            "toc_items":        extract_toc(html),
            "hash":             hashlib.md5(md_post["body_md"].encode()).hexdigest(),
        })
        manifest_slugs.add(md_slug)
        repaired.append(f"  ✓ Added [{md_slug}] to manifest from .md")
        modified = True

    # ── 3. Save ───────────────────────────────────────────────────────────────
    if modified:
        save_manifest(manifest)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    if repaired:
        print(f"  ✅  {len(repaired)} repair(s) made:")
        for r in repaired: print(r)
    if warnings:
        print(f"\n  ⚠  {len(warnings)} item(s) need manual attention:")
        for w in warnings: print(w)
    if not repaired and not warnings:
        print("  ✅  Sources are in sync — no issues found")

    # Final gate: all entries must have body_html
    missing = [p.get("slug") for p in manifest if not p.get("body_html")]
    if missing:
        print(f"\n❌  Still missing body_html: {missing}")
        sys.exit(1)

    buildable = [p for p in manifest if p.get("body_html") and p.get("status","published") != "draft"]
    print(f"\n  Manifest       : {len(manifest)} entries")
    print(f"  .md posts      : {len(md_posts)}")
    print(f"  Buildable      : {len(buildable)}")
    print(f"\n  ✅  Ready — {len(buildable)} posts will deploy")
    print("=" * 60)


if __name__ == "__main__":
    main()
