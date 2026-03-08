#!/usr/bin/env python3
"""
Forma Blog Builder  v2  — with hash-based change detection
=============================================================
Reads forma_blog_posts.md, SEO-enhances new/changed posts via
the Anthropic API, and outputs static HTML to output/.

Skips posts whose markdown content hasn't changed since the last
build (compares SHA-256 hashes stored in posts_manifest.json).
Always rebuilds blog.html index.

Usage:
    python scripts/forma_blog_build.py [--force]

Flags:
    --force    Rebuild all posts regardless of change detection

Environment variables required:
    ANTHROPIC_API_KEY   Your Anthropic API key

Outputs:
    output/blog.html
    output/blog/<slug>.html
    output/posts_manifest.json   (also used as hash cache)
"""

import os
import re
import json
import time
import hashlib
import argparse
from datetime import date
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
INPUT_FILE        = Path("forma_blog_posts.md")
OUTPUT_DIR        = Path("output")
MANIFEST_FILE     = Path("posts_manifest.json")   # committed to repo — hash cache
SITE_URL          = "https://formafit.co.uk"
BRAND_NAME        = "Forma"
COMPANY_NAME      = "AMTR Health Ltd"
CONTACT_EMAIL     = "formafit816@gmail.com"
TODAY             = date.today().isoformat()
MODEL             = "claude-sonnet-4-20250514"

# ── Brand CSS (inline — no external dependencies) ───────────────────────────

BRAND_CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --accent: #1A6B4A; --accent-mid: #2D9165; --accent-light: #E8F5EF;
  --ink: #0F1117; --ink-60: #5A5F6E; --ink-30: #B0B5C3; --ink-10: #F0F1F5;
  --surface: #F8F9FB; --border: #E8EAF0; --white: #FFFFFF; --radius: 12px;
  --font: 'Oxanium', 'DM Sans', system-ui, sans-serif;
}
body { font-family: var(--font); color: var(--ink); background: var(--white);
  font-size: 16px; line-height: 1.6; -webkit-font-smoothing: antialiased; }
nav { position: sticky; top: 0; z-index: 100; background: rgba(255,255,255,0.96);
  backdrop-filter: blur(12px); border-bottom: 1px solid var(--border); }
.nav-inner { max-width: 1100px; margin: 0 auto; padding: 0 24px; height: 64px;
  display: flex; align-items: center; gap: 32px; }
.nav-logo { font-weight: 800; font-size: 1.4rem; color: var(--ink);
  text-decoration: none; letter-spacing: -0.02em; }
.nav-logo span { color: var(--accent); }
.nav-links { display: flex; gap: 28px; list-style: none; flex: 1; }
.nav-links a { font-size: 0.875rem; font-weight: 500; color: var(--ink-60);
  text-decoration: none; transition: color 0.15s; }
.nav-links a:hover, .nav-links a.active { color: var(--ink); }
.btn-nav { padding: 9px 20px; border-radius: 99px; background: var(--accent);
  color: white; font-size: 0.875rem; font-weight: 600; text-decoration: none;
  transition: background 0.15s; white-space: nowrap; }
.btn-nav:hover { background: var(--accent-mid); }
@media(max-width:768px){ .nav-links { display: none; } }
.article-hero { background: var(--ink); padding: 72px 24px 56px; }
.article-hero .container { max-width: 780px; margin: 0 auto; }
.article-category { display: inline-block; padding: 4px 14px; border-radius: 99px;
  font-size: 0.72rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
  background: rgba(74,222,128,0.15); color: #4ADE80; margin-bottom: 20px; }
.article-hero h1 { font-size: clamp(1.75rem, 4vw, 2.75rem); font-weight: 800;
  color: white; line-height: 1.15; letter-spacing: -0.02em; margin-bottom: 20px; }
.article-meta { display: flex; gap: 20px; flex-wrap: wrap; align-items: center;
  font-size: 0.825rem; color: rgba(255,255,255,0.45); }
.article-meta strong { color: rgba(255,255,255,0.7); }
.article-layout { max-width: 1100px; margin: 0 auto; padding: 56px 24px 80px;
  display: grid; grid-template-columns: 1fr 280px; gap: 64px; align-items: start; }
@media(max-width:900px) { .article-layout { grid-template-columns: 1fr; }
  .article-sidebar { display: none; } }
.article-body p { font-size: 1.0625rem; line-height: 1.85; color: var(--ink); margin-bottom: 24px; }
.article-body h2 { font-size: 1.5rem; font-weight: 700; color: var(--ink);
  margin: 44px 0 16px; letter-spacing: -0.01em; line-height: 1.2; scroll-margin-top: 80px; }
.article-body h3 { font-size: 1.15rem; font-weight: 700; color: var(--ink); margin: 32px 0 12px; }
.article-body ul, .article-body ol { padding-left: 24px; margin-bottom: 24px; }
.article-body li { font-size: 1.0625rem; line-height: 1.75; color: var(--ink); margin-bottom: 6px; }
.article-body strong { font-weight: 700; }
.article-body hr { border: none; border-top: 1px solid var(--border); margin: 48px 0; }
.article-sidebar { position: sticky; top: 80px; }
.sidebar-card { background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 20px; margin-bottom: 16px; }
.sidebar-card-title { font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.08em; color: var(--ink-30); margin-bottom: 14px; }
.toc-list { list-style: none; }
.toc-list li { margin-bottom: 8px; }
.toc-list a { font-size: 0.83rem; color: var(--ink-60); text-decoration: none;
  line-height: 1.4; transition: color 0.15s; }
.toc-list a:hover, .toc-list a.active { color: var(--accent); font-weight: 600; }
.cta-card { background: var(--accent); border-radius: var(--radius); padding: 24px; }
.cta-card h3 { font-size: 1rem; font-weight: 700; color: white; margin-bottom: 8px; }
.cta-card p { font-size: 0.83rem; color: rgba(255,255,255,0.7); line-height: 1.6; margin-bottom: 16px; }
.cta-card a { display: block; text-align: center; padding: 11px 16px; border-radius: 99px;
  background: white; color: var(--accent); font-size: 0.875rem; font-weight: 700;
  text-decoration: none; }
.cta-card a:hover { opacity: 0.88; }
.related-section { background: var(--surface); border-top: 1px solid var(--border); padding: 56px 24px; }
.related-inner { max-width: 1100px; margin: 0 auto; }
.related-inner h2 { font-size: 1.25rem; font-weight: 700; margin-bottom: 24px; }
.related-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 16px; }
@media(max-width:768px){ .related-grid { grid-template-columns: 1fr; } }
.related-card { background: white; border: 1px solid var(--border); border-radius: var(--radius);
  padding: 20px; text-decoration: none; display: block; transition: border-color 0.15s, transform 0.15s; }
.related-card:hover { border-color: var(--accent); transform: translateY(-2px); }
.related-card .tag { font-size: 0.68rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.06em; color: var(--accent); margin-bottom: 8px; }
.related-card h3 { font-size: 0.9rem; font-weight: 600; color: var(--ink); line-height: 1.45; }
footer { background: var(--ink); padding: 40px 24px; }
.footer-inner { max-width: 1100px; margin: 0 auto; display: flex; justify-content: space-between;
  align-items: center; flex-wrap: wrap; gap: 16px; font-size: 0.83rem; color: rgba(255,255,255,0.4); }
.footer-inner a { color: rgba(255,255,255,0.4); text-decoration: none; }
.footer-inner a:hover { color: white; }
.footer-links { display: flex; gap: 20px; flex-wrap: wrap; }
"""

# ── Font loading ─────────────────────────────────────────────────────────────

def load_fonts() -> str:
    """Load embedded font-face CSS from forma_fonts.css if available."""
    font_file = Path("forma_fonts.css")
    if font_file.exists():
        return font_file.read_text(encoding="utf-8")
    # Fallback: Google Fonts (requires internet, less ideal for offline)
    return "@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&display=swap');"


# ── Hashing ──────────────────────────────────────────────────────────────────

def content_hash(text: str) -> str:
    """SHA-256 of raw markdown content — used to detect changes."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ── Parse markdown posts ─────────────────────────────────────────────────────

def parse_posts(filepath: Path) -> list[dict]:
    """Split the markdown file into raw post dicts."""
    raw = filepath.read_text(encoding="utf-8")
    sections = re.split(r'\n## \d+\.\s*', raw)
    posts = []
    for section in sections:
        section = section.strip()
        if not section or section.startswith("# Forma"):
            continue
        lines = section.split("\n")
        title = lines[0].strip()
        body  = "\n".join(lines[1:]).strip()
        posts.append({
            "raw_title": title,
            "raw_body":  body,
            "hash":      content_hash(title + body),
        })
    return posts


# ── Load / save manifest ─────────────────────────────────────────────────────

def load_manifest() -> dict:
    """Load existing manifest (hash cache + post metadata)."""
    if MANIFEST_FILE.exists():
        with open(MANIFEST_FILE) as f:
            data = json.load(f)
        # Index by hash for fast lookup
        return {item["hash"]: item for item in data if "hash" in item}
    return {}


def save_manifest(posts: list[dict]) -> None:
    """Write manifest — used both as SEO metadata and hash cache."""
    manifest = [
        {
            "slug":     p["slug"],
            "title":    p["title"],
            "category": p["category"],
            "url":      f"{SITE_URL}/blog/{p['slug']}",
            "date":     p.get("date", TODAY),
            "hash":     p["hash"],
        }
        for p in posts
    ]
    with open(MANIFEST_FILE, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"   ✓ {MANIFEST_FILE} updated ({len(manifest)} posts)")


# ── Anthropic SEO call ───────────────────────────────────────────────────────

def seo_enhance(raw_title: str, raw_body: str) -> dict:
    """Call Claude API to generate SEO metadata and body HTML."""
    import anthropic

    prompt = f"""You are an SEO specialist for Forma, an adaptive endurance training app (formafit.co.uk) by AMTR Health Ltd.

TITLE: {raw_title}

BODY:
{raw_body}

Return ONLY valid JSON (no markdown fences) with this exact structure:
{{
  "title": "SEO-optimised title, max 65 chars, includes primary keyword",
  "slug": "url-safe-slug",
  "meta_description": "152-158 chars, compelling, includes keyword",
  "category": "Training Science",
  "read_time": 4,
  "keywords": "5-7 LSI keywords comma separated",
  "toc_items": [{{"id": "heading-id", "text": "Heading Text"}}],
  "body_html": "Complete article as semantic HTML. h2 id='heading-id', p, ul, li, strong. Keep ALL original content. No html/body wrapper."
}}"""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    raw_json = message.content[0].text.strip()
    raw_json = re.sub(r'^```json\s*|\s*```$', '', raw_json).strip()
    return json.loads(raw_json)


# ── HTML builders ────────────────────────────────────────────────────────────

def build_post_html(post: dict, all_posts: list, font_css: str) -> str:
    slug      = post["slug"]
    title     = post["title"]
    meta_desc = post["meta_description"]
    category  = post["category"]
    read_time = post["read_time"]
    keywords  = post["keywords"]
    body_html = post["body_html"]
    toc_items = post["toc_items"]
    pub_date  = post.get("date", TODAY)
    canonical = f"{SITE_URL}/blog/{slug}"
    og_image  = f"{SITE_URL}/og/blog-{slug}.jpg"

    schema = json.dumps({
        "@context": "https://schema.org", "@type": "BlogPosting",
        "headline": title, "description": meta_desc,
        "author": {"@type": "Organization", "name": COMPANY_NAME, "url": SITE_URL},
        "publisher": {"@type": "Organization", "name": BRAND_NAME,
                      "logo": {"@type": "ImageObject", "url": f"{SITE_URL}/logo.png"}},
        "datePublished": pub_date, "dateModified": TODAY,
        "url": canonical, "mainEntityOfPage": canonical, "keywords": keywords
    }, indent=2)

    toc_html = "\n".join([
        f'<li><a href="#{i["id"]}">{i["text"]}</a></li>'
        for i in toc_items
    ])

    others = [p for p in all_posts if p["slug"] != slug][:3]
    related_html = "\n".join([
        f'<a class="related-card" href="{p["slug"]}.html">'
        f'<div class="tag">{p["category"]}</div>'
        f'<h3>{p["title"]}</h3></a>'
        for p in others
    ])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — {BRAND_NAME}</title>
  <meta name="description" content="{meta_desc}">
  <link rel="canonical" href="{canonical}">
  <meta name="robots" content="index, follow">
  <meta name="keywords" content="{keywords}">
  <meta property="og:type" content="article">
  <meta property="og:url" content="{canonical}">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{meta_desc}">
  <meta property="og:image" content="{og_image}">
  <meta property="og:site_name" content="{BRAND_NAME}">
  <meta property="og:locale" content="en_GB">
  <meta property="article:published_time" content="{pub_date}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{title}">
  <meta name="twitter:description" content="{meta_desc}">
  <meta name="twitter:image" content="{og_image}">
  <script type="application/ld+json">
{schema}
  </script>
  <script type="application/ld+json">
  {{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[
    {{"@type":"ListItem","position":1,"name":"Home","item":"{SITE_URL}/"}},
    {{"@type":"ListItem","position":2,"name":"Blog","item":"{SITE_URL}/blog"}},
    {{"@type":"ListItem","position":3,"name":"{title}","item":"{canonical}"}}
  ]}}
  </script>
  <style>
{font_css}
{BRAND_CSS}
  </style>
</head>
<body>
<nav>
  <div class="nav-inner">
    <a class="nav-logo" href="../index.html">Forma<span>.</span></a>
    <ul class="nav-links">
      <li><a href="../features.html">Features</a></li>
      <li><a href="../pricing.html">Pricing</a></li>
      <li><a href="../blog.html" class="active">Blog</a></li>
      <li><a href="../help.html">Help</a></li>
    </ul>
    <a href="../pricing.html" class="btn-nav">Start free trial</a>
  </div>
</nav>
<header class="article-hero">
  <div class="container">
    <div class="article-category">{category}</div>
    <h1>{title}</h1>
    <div class="article-meta">
      <span>By <strong>{COMPANY_NAME}</strong></span>
      <span>·</span>
      <span>{pub_date}</span>
      <span>·</span>
      <span>{read_time} min read</span>
    </div>
  </div>
</header>
<div class="article-layout">
  <article class="article-body">
    {body_html}
  </article>
  <aside class="article-sidebar">
    <div class="sidebar-card">
      <div class="sidebar-card-title">In this article</div>
      <ul class="toc-list">{toc_html}</ul>
    </div>
    <div class="cta-card">
      <h3>Train smarter from tomorrow</h3>
      <p>Forma adapts your plan every morning based on how your body actually feels.</p>
      <a href="../pricing.html">Start 14-day free trial</a>
    </div>
  </aside>
</div>
{('<section class="related-section"><div class="related-inner"><h2>Keep reading</h2>'
  '<div class="related-grid">' + related_html + '</div></div></section>') if related_html else ''}
<footer>
  <div class="footer-inner">
    <span>© 2026 {COMPANY_NAME} · <a href="../privacy.html">Privacy</a> · <a href="../terms.html">Terms</a></span>
    <div class="footer-links">
      <a href="../blog.html">← All articles</a>
      <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>
    </div>
  </div>
</footer>
<script>
document.querySelectorAll('.toc-list a').forEach(a => {{
  a.addEventListener('click', e => {{
    e.preventDefault();
    const t = document.getElementById(a.getAttribute('href').slice(1));
    if (t) t.scrollIntoView({{ behavior:'smooth', block:'start' }});
  }});
}});
const headings = document.querySelectorAll('.article-body h2');
const tocLinks = document.querySelectorAll('.toc-list a');
const obs = new IntersectionObserver(entries => {{
  entries.forEach(e => {{
    if (e.isIntersecting) {{
      tocLinks.forEach(l => l.classList.remove('active'));
      const a = document.querySelector(`.toc-list a[href="#${{e.target.id}}"]`);
      if (a) a.classList.add('active');
    }}
  }});
}}, {{ rootMargin:'-20% 0px -70% 0px' }});
headings.forEach(h => obs.observe(h));
</script>
</body>
</html>"""


def build_blog_index(all_posts: list, font_css: str) -> str:
    cards = "\n".join([
        f'''<a class="related-card" href="blog/{p["slug"]}.html"
          style="padding:24px;display:flex;flex-direction:column;gap:10px;">
          <div class="tag">{p["category"]}</div>
          <h3 style="font-size:1.05rem;font-weight:700;color:var(--ink);line-height:1.35;">{p["title"]}</h3>
          <p style="font-size:0.85rem;color:var(--ink-60);line-height:1.6;flex:1;">{p["meta_description"][:118]}…</p>
          <span style="font-size:0.78rem;color:var(--ink-30);">{p["read_time"]} min read</span>
        </a>'''
        for p in all_posts
    ])
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Blog — Forma Training Intelligence</title>
  <meta name="description" content="Science-backed writing on HRV, recovery, adaptive training, and endurance performance for runners and cyclists.">
  <link rel="canonical" href="{SITE_URL}/blog">
  <meta name="robots" content="index, follow">
  <meta property="og:title" content="Blog — Forma Training Intelligence">
  <meta property="og:description" content="Science-backed writing on HRV, recovery, and adaptive endurance training.">
  <meta property="og:url" content="{SITE_URL}/blog">
  <meta property="og:site_name" content="{BRAND_NAME}">
  <script type="application/ld+json">
  {{"@context":"https://schema.org","@type":"Blog","name":"Forma Training Blog",
  "url":"{SITE_URL}/blog","publisher":{{"@type":"Organization","name":"{COMPANY_NAME}","url":"{SITE_URL}"}}}}
  </script>
  <style>
{font_css}
{BRAND_CSS}
.blog-hero {{ background:var(--ink); padding:64px 24px; }}
.blog-hero .container {{ max-width:1100px; margin:0 auto; }}
.blog-hero h1 {{ font-size:clamp(2rem,4vw,3rem); font-weight:800; color:white;
  letter-spacing:-0.02em; margin-bottom:12px; }}
.blog-hero p {{ font-size:1rem; color:rgba(255,255,255,0.5); max-width:520px; }}
.blog-grid-section {{ max-width:1100px; margin:56px auto; padding:0 24px 80px; }}
.blog-grid {{ display:grid; grid-template-columns:repeat(2,1fr); gap:20px; }}
@media(max-width:640px){{ .blog-grid {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
<nav>
  <div class="nav-inner">
    <a class="nav-logo" href="index.html">Forma<span>.</span></a>
    <ul class="nav-links">
      <li><a href="features.html">Features</a></li>
      <li><a href="pricing.html">Pricing</a></li>
      <li><a href="blog.html" class="active">Blog</a></li>
      <li><a href="help.html">Help</a></li>
    </ul>
    <a href="pricing.html" class="btn-nav">Start free trial</a>
  </div>
</nav>
<header class="blog-hero">
  <div class="container">
    <div class="article-category">Training Intelligence</div>
    <h1>Train smart. Think deep.</h1>
    <p>Science-backed writing on HRV, recovery, and adaptive endurance training.</p>
  </div>
</header>
<div class="blog-grid-section">
  <div class="blog-grid">{cards}</div>
</div>
<footer>
  <div class="footer-inner">
    <span>© 2026 {COMPANY_NAME}</span>
    <div class="footer-links">
      <a href="privacy.html">Privacy</a>
      <a href="terms.html">Terms</a>
      <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>
    </div>
  </div>
</footer>
</body>
</html>"""


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Forma blog builder")
    parser.add_argument("--force", action="store_true",
                        help="Rebuild all posts ignoring change detection")
    args = parser.parse_args()

    print("=" * 60)
    print("  Forma Blog Builder  v2")
    print("=" * 60)

    if not ANTHROPIC_API_KEY:
        print("\n❌  ANTHROPIC_API_KEY is not set.")
        print("    export ANTHROPIC_API_KEY=sk-ant-...")
        raise SystemExit(1)

    # Load fonts
    font_css = load_fonts()
    print(f"✓ Fonts loaded ({len(font_css)//1024} KB)")

    # Parse posts
    raw_posts = parse_posts(INPUT_FILE)
    print(f"✓ Parsed {len(raw_posts)} posts from {INPUT_FILE}")

    # Load existing manifest (hash cache)
    manifest_cache = load_manifest()
    if args.force:
        print("  --force flag set: rebuilding all posts")
        manifest_cache = {}

    # Create output dirs
    blog_dir = OUTPUT_DIR / "blog"
    blog_dir.mkdir(parents=True, exist_ok=True)

    # Process each post
    all_enhanced: list[dict] = []
    rebuilt = 0
    cached  = 0

    for i, raw in enumerate(raw_posts, 1):
        h = raw["hash"]
        short_title = raw["raw_title"][:55]

        if h in manifest_cache:
            # Post unchanged — load cached metadata, rebuild HTML from cache
            cached_meta = manifest_cache[h]
            print(f"[{i}/{len(raw_posts)}] ⏭  CACHED  {short_title[:50]}")

            # We need full metadata to rebuild HTML — store it in manifest
            # If full post data is in cache, reuse it; otherwise force rebuild
            if "body_html" in cached_meta:
                all_enhanced.append(cached_meta)
                cached += 1
                continue
            # Fall through to rebuild if body_html not cached

        print(f"[{i}/{len(raw_posts)}] 🔄  BUILDING  {short_title}...")
        print(f"     → Calling Anthropic API...")

        try:
            enhanced = seo_enhance(raw["raw_title"], raw["raw_body"])
            enhanced["hash"]  = h
            enhanced["date"]  = TODAY
            all_enhanced.append(enhanced)
            rebuilt += 1
            print(f"     ✓ /{enhanced['slug']}  |  {len(enhanced['meta_description'])} char desc")

            if i < len(raw_posts):
                time.sleep(0.5)  # polite rate limiting

        except Exception as e:
            print(f"     ❌ Failed: {e}")
            raise  # fail fast in CI — don't silently skip

    # Write post HTML files (always write all — cheap operation)
    print(f"\n📝 Writing HTML files...")
    for post in all_enhanced:
        html    = build_post_html(post, all_enhanced, font_css)
        outfile = blog_dir / f"{post['slug']}.html"
        outfile.write_text(html, encoding="utf-8")
        flag = "⏭" if post in [all_enhanced[j] for j in range(len(all_enhanced)) if all_enhanced[j].get("hash") in manifest_cache and "body_html" in manifest_cache.get(all_enhanced[j].get("hash"), {})] else "✓"
        print(f"   ✓ blog/{post['slug']}.html  ({len(html)//1024} KB)")

    # Always rebuild blog index
    blog_index = build_blog_index(all_enhanced, font_css)
    (OUTPUT_DIR / "blog.html").write_text(blog_index, encoding="utf-8")
    print(f"   ✓ blog.html  ({len(blog_index)//1024} KB)")

    # Save manifest with full post data embedded (enables future cache hits)
    # We save the full enhanced post data so next run can restore from cache
    full_manifest = []
    for p in all_enhanced:
        full_manifest.append({
            "slug":         p["slug"],
            "title":        p["title"],
            "category":     p["category"],
            "url":          f"{SITE_URL}/blog/{p['slug']}",
            "date":         p.get("date", TODAY),
            "hash":         p["hash"],
            "meta_description": p["meta_description"],
            "read_time":    p["read_time"],
            "keywords":     p["keywords"],
            "toc_items":    p["toc_items"],
            "body_html":    p["body_html"],
        })
    with open(MANIFEST_FILE, "w") as f:
        json.dump(full_manifest, f, indent=2)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  ✅  Done")
    print(f"  Built: {rebuilt} posts  |  Cached: {cached} posts")
    print(f"  Output: {OUTPUT_DIR}/")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
