#!/usr/bin/env python3
"""
Forma Blog Builder  v3  — offline/cache mode
=============================================
Reads posts_manifest.json (already contains all post data from previous
API runs) and rebuilds all HTML without making any Anthropic API calls.

Use this when:
  - You want to deploy immediately without API credits
  - You're testing layout/CSS changes
  - posts_manifest.json already has all posts built

Usage:
    python forma_blog_build.py

Outputs:
    output/index.html
    output/blog/<slug>.html
"""

import os
import re
import json
from datetime import date
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────
MANIFEST_FILE = Path("posts_manifest.json")
OUTPUT_DIR    = Path("output")
SITE_URL      = "https://formafit.co.uk"
BLOG_URL      = "https://blog.formafit.co.uk"
BRAND_NAME    = "Forma"
COMPANY_NAME  = "AMTR Health Ltd"
CONTACT_EMAIL = "formafit816@gmail.com"
TODAY         = date.today().isoformat()

# ── Brand CSS ─────────────────────────────────────────────────────────────────
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
/* NAV — matches formafit.co.uk exactly */
nav { position: sticky; top: 0; z-index: 100; background: rgba(255,255,255,0.97);
  backdrop-filter: blur(12px); border-bottom: 1px solid var(--border); }
.nav-inner { max-width: 1160px; margin: 0 auto; padding: 0 32px; height: 64px;
  display: flex; align-items: center; }
.nav-logo { display: flex; align-items: center; gap: 6px; text-decoration: none;
  margin-right: auto; flex-shrink: 0; }
.nav-logo-mark { display: flex; align-items: baseline; gap: 1px; }
.nav-logo-mark .f { font-size: 1.35rem; font-weight: 800; color: var(--accent);
  letter-spacing: -0.03em; line-height: 1; font-style: italic; }
.nav-logo-mark .slash { font-size: 1.1rem; font-weight: 300; color: var(--accent);
  margin: 0 1px; }
.nav-logo-text { font-size: 0.95rem; font-weight: 700; color: var(--ink);
  letter-spacing: 0.12em; text-transform: uppercase; }
.nav-links { display: flex; gap: 4px; list-style: none; margin-right: 12px; }
.nav-links a { font-size: 0.875rem; font-weight: 500; color: var(--ink-60);
  text-decoration: none; padding: 6px 14px; border-radius: 8px; transition: all 0.15s; }
.nav-links a:hover { color: var(--ink); }
.nav-links a.active { color: var(--ink); font-weight: 600; }
.btn-login { padding: 8px 18px; border-radius: 99px; border: 1.5px solid var(--border);
  background: white; color: var(--ink); font-size: 0.875rem; font-weight: 500;
  text-decoration: none; margin-right: 8px; transition: border-color 0.15s; }
.btn-login:hover { border-color: var(--ink-30); }
.btn-start { padding: 9px 20px; border-radius: 99px; background: var(--accent);
  color: white; font-size: 0.875rem; font-weight: 600; text-decoration: none;
  transition: background 0.15s; white-space: nowrap; }
.btn-start:hover { background: var(--accent-mid); }
@media(max-width:768px){ .nav-links { display: none; } .btn-login { display: none; } }
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
/* FOOTER — matches formafit.co.uk 4-column footer */
footer { background: var(--ink); padding: 64px 32px 40px; }
.footer-top { max-width: 1160px; margin: 0 auto;
  display: grid; grid-template-columns: 220px repeat(3, 1fr); gap: 48px;
  padding-bottom: 48px; border-bottom: 1px solid rgba(255,255,255,0.08); }
@media(max-width:768px) { .footer-top { grid-template-columns: 1fr 1fr; } }
@media(max-width:480px) { .footer-top { grid-template-columns: 1fr; } }
.footer-brand-logo { display: flex; align-items: baseline; gap: 1px; margin-bottom: 12px; }
.footer-brand-logo .f { font-size: 1.3rem; font-weight: 800; color: var(--accent);
  font-style: italic; }
.footer-brand-logo .slash { font-size: 1.05rem; font-weight: 300; color: var(--accent);
  margin: 0 1px; }
.footer-brand-logo .name { font-size: 0.9rem; font-weight: 700; color: white;
  letter-spacing: 0.12em; text-transform: uppercase; }
.footer-brand p { font-size: 0.83rem; color: rgba(255,255,255,0.35); line-height: 1.7;
  max-width: 180px; }
.footer-col h4 { font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.1em; color: rgba(255,255,255,0.3); margin-bottom: 16px; }
.footer-col ul { list-style: none; display: flex; flex-direction: column; gap: 10px; }
.footer-col a { font-size: 0.875rem; color: rgba(255,255,255,0.5);
  text-decoration: none; transition: color 0.15s; }
.footer-col a:hover { color: white; }
.footer-bottom { max-width: 1160px; margin: 0 auto; padding-top: 28px;
  display: flex; justify-content: space-between; align-items: center;
  flex-wrap: wrap; gap: 8px; }
.footer-copy { font-size: 0.78rem; color: rgba(255,255,255,0.2); }
.footer-tagline { font-size: 0.78rem; color: rgba(255,255,255,0.2); font-style: italic; }
"""

def load_fonts() -> str:
    font_file = Path("forma_fonts.css")
    if font_file.exists():
        content = font_file.read_text(encoding="utf-8")
        print(f"✓ Fonts loaded ({len(content)//1024} KB)")
        return content
    print("⚠  forma_fonts.css not found — using system fonts")
    return ""

def load_manifest() -> list:
    if not MANIFEST_FILE.exists():
        print(f"❌ {MANIFEST_FILE} not found. Cannot build without cached post data.")
        raise SystemExit(1)
    with open(MANIFEST_FILE) as f:
        posts = json.load(f)
    # Filter to only posts that have body_html (fully built)
    ready = [p for p in posts if p.get("body_html")]
    print(f"✓ Loaded {len(ready)} posts from {MANIFEST_FILE}")
    if len(ready) < len(posts):
        print(f"⚠  {len(posts) - len(ready)} posts skipped (no body_html — need API build)")
    return ready

def build_post_html(post: dict, all_posts: list, font_css: str) -> str:
    slug      = post["slug"]
    title     = post["title"]
    meta_desc = post.get("meta_description", "")
    category  = post.get("category", "Training")
    read_time = post.get("read_time", 5)
    keywords  = post.get("keywords", "")
    body_html = post.get("body_html", "")
    toc_items = post.get("toc_items", [])
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
        f'<a class="related-card" href="/blog/{p['slug']}.html">'
        f'<div class="tag">{p.get("category","")}</div>'
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
  <style>
{font_css}
{BRAND_CSS}
  </style>
</head>
<body>
<nav>
  <div class="nav-inner">
    <a class="nav-logo" href="{SITE_URL}">
      <div class="nav-logo-mark"><span class="f">F</span><span class="slash">/</span></div>
      <span class="nav-logo-text">Forma</span>
    </a>
    <ul class="nav-links">
      <li><a href="{SITE_URL}/features">Features</a></li>
      <li><a href="{SITE_URL}/pricing">Pricing</a></li>
      <li><a href="{BLOG_URL}" class="active">Blog</a></li>
      <li><a href="{SITE_URL}/help">Help</a></li>
    </ul>
    <a href="{SITE_URL}/login" class="btn-login">Log in</a>
    <a href="{SITE_URL}/pricing" class="btn-start">Start free</a>
  </div>
</nav>
<header class="article-hero">
  <div class="container">
    <div class="article-category">{category}</div>
    <h1>{title}</h1>
    <div class="article-meta">
      <span>By <strong>{COMPANY_NAME}</strong></span>
      <span>·</span><span>{pub_date}</span>
      <span>·</span><span>{read_time} min read</span>
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
      <a href="{SITE_URL}/pricing">Start 14-day free trial</a>
    </div>
  </aside>
</div>
{('<section class="related-section"><div class="related-inner"><h2>Keep reading</h2><div class="related-grid">' + related_html + '</div></div></section>') if related_html else ''}
<footer>
  <div class="footer-top">
    <div class="footer-brand">
      <div class="footer-brand-logo">
        <span class="f">F</span><span class="slash">/</span>
        <span class="name">Forma</span>
      </div>
      <p>Readiness-driven endurance training for runners and cyclists.</p>
    </div>
    <div class="footer-col">
      <h4>Product</h4>
      <ul>
        <li><a href="{SITE_URL}/features">Features</a></li>
        <li><a href="{SITE_URL}/pricing">Pricing</a></li>
        <li><a href="{SITE_URL}/changelog">Changelog</a></li>
      </ul>
    </div>
    <div class="footer-col">
      <h4>Learn</h4>
      <ul>
        <li><a href="{BLOG_URL}">Blog</a></li>
        <li><a href="{SITE_URL}/help">Help Centre</a></li>
        <li><a href="{SITE_URL}/community">Community</a></li>
      </ul>
    </div>
    <div class="footer-col">
      <h4>Company</h4>
      <ul>
        <li><a href="{SITE_URL}/about">About</a></li>
        <li><a href="{SITE_URL}/privacy">Privacy</a></li>
        <li><a href="{SITE_URL}/terms">Terms</a></li>
      </ul>
    </div>
  </div>
  <div class="footer-bottom">
    <span class="footer-copy">© 2026 Forma. Train smart. Stay whole.</span>
    <span class="footer-tagline">Built for endurance. Designed for humans.</span>
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
const obs = new IntersectionObserver(entries => {{
  entries.forEach(e => {{
    if (e.isIntersecting) {{
      document.querySelectorAll('.toc-list a').forEach(l => l.classList.remove('active'));
      const a = document.querySelector(`.toc-list a[href="#${{e.target.id}}"]`);
      if (a) a.classList.add('active');
    }}
  }});
}}, {{ rootMargin:'-20% 0px -70% 0px' }});
document.querySelectorAll('.article-body h2').forEach(h => obs.observe(h));
</script>
</body>
</html>"""

def build_blog_index(all_posts: list, font_css: str) -> str:
    cards = "\n".join([
        f'''<a class="related-card" href="/blog/{p["slug"]}.html"
          style="padding:24px;display:flex;flex-direction:column;gap:10px;">
          <div class="tag">{p.get("category","")}</div>
          <h3 style="font-size:1.05rem;font-weight:700;color:var(--ink);line-height:1.35;">{p["title"]}</h3>
          <p style="font-size:0.85rem;color:var(--ink-60);line-height:1.6;flex:1;">{p.get("meta_description","")[:118]}…</p>
          <span style="font-size:0.78rem;color:var(--ink-30);">{p.get("read_time",5)} min read</span>
        </a>'''
        for p in all_posts
    ])
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Blog — Forma Training Intelligence</title>
  <meta name="description" content="Science-backed writing on HRV, recovery, adaptive training, and endurance performance.">
  <link rel="canonical" href="{BLOG_URL}">
  <meta name="robots" content="index, follow">
  <style>
{font_css}
{BRAND_CSS}
.blog-hero {{ background:var(--ink); padding:64px 32px; }}
.blog-hero .container {{ max-width:1160px; margin:0 auto; }}
.blog-hero h1 {{ font-size:clamp(2rem,4vw,3rem); font-weight:800; color:white;
  letter-spacing:-0.02em; margin-bottom:12px; }}
.blog-hero p {{ font-size:1rem; color:rgba(255,255,255,0.5); max-width:520px; }}
.blog-grid-section {{ max-width:1160px; margin:56px auto; padding:0 32px 80px; }}
.blog-grid {{ display:grid; grid-template-columns:repeat(2,1fr); gap:20px; }}
@media(max-width:640px){{ .blog-grid {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
<nav>
  <div class="nav-inner">
    <a class="nav-logo" href="{SITE_URL}">
      <div class="nav-logo-mark"><span class="f">F</span><span class="slash">/</span></div>
      <span class="nav-logo-text">Forma</span>
    </a>
    <ul class="nav-links">
      <li><a href="{SITE_URL}/features">Features</a></li>
      <li><a href="{SITE_URL}/pricing">Pricing</a></li>
      <li><a href="{BLOG_URL}" class="active">Blog</a></li>
      <li><a href="{SITE_URL}/help">Help</a></li>
    </ul>
    <a href="{SITE_URL}/login" class="btn-login">Log in</a>
    <a href="{SITE_URL}/pricing" class="btn-start">Start free</a>
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
  <div class="footer-top">
    <div class="footer-brand">
      <div class="footer-brand-logo">
        <span class="f">F</span><span class="slash">/</span>
        <span class="name">Forma</span>
      </div>
      <p>Readiness-driven endurance training for runners and cyclists.</p>
    </div>
    <div class="footer-col">
      <h4>Product</h4>
      <ul>
        <li><a href="{SITE_URL}/features">Features</a></li>
        <li><a href="{SITE_URL}/pricing">Pricing</a></li>
        <li><a href="{SITE_URL}/changelog">Changelog</a></li>
      </ul>
    </div>
    <div class="footer-col">
      <h4>Learn</h4>
      <ul>
        <li><a href="{BLOG_URL}">Blog</a></li>
        <li><a href="{SITE_URL}/help">Help Centre</a></li>
        <li><a href="{SITE_URL}/community">Community</a></li>
      </ul>
    </div>
    <div class="footer-col">
      <h4>Company</h4>
      <ul>
        <li><a href="{SITE_URL}/about">About</a></li>
        <li><a href="{SITE_URL}/privacy">Privacy</a></li>
        <li><a href="{SITE_URL}/terms">Terms</a></li>
      </ul>
    </div>
  </div>
  <div class="footer-bottom">
    <span class="footer-copy">© 2026 Forma. Train smart. Stay whole.</span>
    <span class="footer-tagline">Built for endurance. Designed for humans.</span>
  </div>
</footer>
</body>
</html>"""

def main():
    print("=" * 60)
    print("  Forma Blog Builder  v3  (offline / cache mode)")
    print("=" * 60)

    font_css   = load_fonts()
    all_posts  = load_manifest()

    blog_dir = OUTPUT_DIR / "blog"
    blog_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n📝 Writing HTML files...")
    for post in all_posts:
        html    = build_post_html(post, all_posts, font_css)
        outfile = blog_dir / f"{post['slug']}.html"
        outfile.write_text(html, encoding="utf-8")
        print(f"   ✓ blog/{post['slug']}.html  ({len(html)//1024} KB)")

    blog_index = build_blog_index(all_posts, font_css)
    (OUTPUT_DIR / "index.html").write_text(blog_index, encoding="utf-8")
    print(f"   ✓ index.html  ({len(blog_index)//1024} KB)")

    print(f"\n{'=' * 60}")
    print(f"  ✅  Done — {len(all_posts)} posts built from cache")
    print(f"  No API calls made.")
    print(f"{'=' * 60}")

if __name__ == "__main__":
    main()
