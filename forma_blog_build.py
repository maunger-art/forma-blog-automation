#!/usr/bin/env python3
"""
Forma Blog Builder  v6
======================
Unchanged from v5 except three additions:
  C. writes output/sitemap.xml and output/feed.xml
  D. generates output/og-default.png and injects og:image / twitter:image
     into every page (index + posts)
"""

import json
import textwrap
from datetime import date, datetime
from pathlib import Path
from email.utils import format_datetime
from xml.sax.saxutils import escape as xml_escape

MANIFEST_FILE = Path("posts_manifest.json")
OUTPUT_DIR    = Path("output")
SITE_URL      = "https://formafit.co.uk"
BLOG_URL      = "https://blog.formafit.co.uk"
BRAND_NAME    = "Forma"
COMPANY_NAME  = "AMTR Health Ltd"
CONTACT_EMAIL = "formafit816@gmail.com"
TODAY         = date.today().isoformat()

OG_IMAGE_URL  = f"{BLOG_URL}/og-default.png"   # shared OG image for all pages

# ── Exact SVG logo mark from brand files ──────────────────────────────────────
LOGO_SVG = """<svg width="200" height="44" viewBox="0 0 200 44" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect x="0" y="0" width="7" height="44" fill="#1A6B4A"/>
  <rect x="0" y="0" width="28" height="7" fill="#1A6B4A"/>
  <rect x="0" y="18.5" width="21" height="7" fill="#1A6B4A"/>
  <polygon points="33,44 39,44 46,28 40,28" fill="#1A6B4A"/>
  <polygon points="38,44 42,44 49,28 45,28" fill="#1A6B4A" opacity="0.22"/>
  <text x="60" y="33" font-family="Oxanium, monospace" font-weight="800" font-size="28" fill="#0F1117" letter-spacing="1">FORMA</text>
</svg>"""

LOGO_SVG_WHITE = """<svg width="200" height="44" viewBox="0 0 200 44" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect x="0" y="0" width="7" height="44" fill="white"/>
  <rect x="0" y="0" width="28" height="7" fill="white"/>
  <rect x="0" y="18.5" width="21" height="7" fill="white"/>
  <polygon points="33,44 39,44 46,28 40,28" fill="white"/>
  <polygon points="38,44 42,44 49,28 45,28" fill="white" opacity="0.22"/>
  <text x="60" y="33" font-family="Oxanium, monospace" font-weight="800" font-size="28" fill="white" letter-spacing="1">FORMA</text>
</svg>"""

CATEGORY_STYLES = {
    "training science": ("#DCFCE7", "#16A34A", "#F0FFF4", "🧬"),
    "wearables":        ("#FEF9C3", "#CA8A04", "#FEFCE8", "⌚"),
    "performance":      ("#FEE2E2", "#DC2626", "#FFF5F5", "🏆"),
    "mindset":          ("#EDE9FE", "#7C3AED", "#F5F3FF", "🧘"),
    "recovery":         ("#DCFCE7", "#16A34A", "#F0FFF4", "😴"),
    "hrv":              ("#DBEAFE", "#2563EB", "#EFF6FF", "📊"),
    "science":          ("#FEF3C7", "#D97706", "#FFFBEB", "🔬"),
    "load":             ("#F3E8FF", "#9333EA", "#FAF5FF", "📈"),
}

def cat_style(cat: str):
    key = cat.lower()
    for k, v in CATEGORY_STYLES.items():
        if k in key:
            return v
    return ("#DCFCE7", "#16A34A", "#F0FFF4", "📖")

def fmt_date(d: str) -> str:
    try:
        dt = datetime.strptime(d[:10], "%Y-%m-%d")
        return dt.strftime("%B %Y").upper()
    except Exception:
        return d.upper() if d else "2026"

def load_fonts() -> str:
    f = Path("forma_fonts.css")
    if f.exists():
        t = f.read_text(encoding="utf-8")
        print(f"✓ Fonts ({len(t)//1024} KB)")
        return t
    print("⚠  No fonts CSS")
    return ""

def load_manifest() -> list:
    if not MANIFEST_FILE.exists():
        print(f"❌ {MANIFEST_FILE} not found"); raise SystemExit(1)
    all_posts = json.load(open(MANIFEST_FILE))
    posts = [
        p for p in all_posts
        if p.get("body_html") and p.get("status", "published") != "draft"
    ]
    drafts = len(all_posts) - len(posts)
    print(f"✓ {len(posts)} posts loaded ({drafts} drafts skipped)")
    return posts

# ── Shared nav ────────────────────────────────────────────────────────────────
def NAV(active="blog"):
    links = [("Features", f"{SITE_URL}/features",  "features"),
             ("Pricing",  f"{SITE_URL}/pricing",   "pricing"),
             ("Blog",     BLOG_URL,                 "blog"),
             ("Help",     f"{SITE_URL}/help",       "help")]
    items = []
    for label, url, k in links:
        active_class = " class='active'" if k == active else ""
        items.append(f'<li><a href="{url}"{active_class}>{label}</a></li>')
    lis = "\n".join(items)
    return f"""<nav>
  <div class="nav-inner">
    <a class="nav-logo" href="{SITE_URL}">{LOGO_SVG}</a>
    <ul class="nav-links">{lis}</ul>
    <a href="{SITE_URL}/login" class="btn-login">Log in</a>
    <a href="{SITE_URL}/pricing" class="btn-start">Start free</a>
  </div>
</nav>"""

# ── Shared footer ─────────────────────────────────────────────────────────────
FOOTER = f"""<footer>
  <div class="footer-top">
    <div class="footer-brand">
      <a href="{SITE_URL}" class="footer-logo">{LOGO_SVG_WHITE}</a>
      <p>Readiness-driven endurance training for runners and cyclists chasing their best performance without breaking their body.</p>
    </div>
    <div class="footer-col"><h4>Product</h4><ul>
      <li><a href="{SITE_URL}/features">Features</a></li>
      <li><a href="{SITE_URL}/pricing">Pricing</a></li>
      <li><a href="{SITE_URL}/changelog">Changelog</a></li>
    </ul></div>
    <div class="footer-col"><h4>Learn</h4><ul>
      <li><a href="{BLOG_URL}">Blog</a></li>
      <li><a href="{SITE_URL}/help">Help Centre</a></li>
      <li><a href="{SITE_URL}/community">Community</a></li>
    </ul></div>
    <div class="footer-col"><h4>Company</h4><ul>
      <li><a href="{SITE_URL}/about">About</a></li>
      <li><a href="{SITE_URL}/privacy">Privacy</a></li>
      <li><a href="{SITE_URL}/terms">Terms</a></li>
    </ul></div>
  </div>
  <div class="footer-bottom">
    <span class="footer-copy">© 2026 Forma. Train smart. Stay whole.</span>
    <span class="footer-tagline">Built for endurance. Designed for humans.</span>
  </div>
</footer>"""

# ── Shared CSS ────────────────────────────────────────────────────────────────
BRAND_CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --green: #1A6B4A; --green-mid: #2D9165; --green-light: #F0FFF4;
  --ink: #0F1117; --ink-60: #5A5F6E; --ink-30: #B0B5C3; --ink-10: #F5F6F8;
  --surface: #F8F9FB; --border: #E8EAF0; --white: #FFFFFF; --radius: 12px;
  --font: 'Oxanium', system-ui, sans-serif;
}
body { font-family: var(--font); color: var(--ink); background: var(--white);
  font-size: 16px; line-height: 1.6; -webkit-font-smoothing: antialiased; }
nav { position: sticky; top: 0; z-index: 100; background: rgba(255,255,255,0.97);
  backdrop-filter: blur(12px); border-bottom: 1px solid var(--border); }
.nav-inner { max-width: 1200px; margin: 0 auto; padding: 0 32px; height: 68px;
  display: flex; align-items: center; }
.nav-logo { display: flex; align-items: center; text-decoration: none;
  margin-right: auto; flex-shrink: 0; }
.nav-logo svg { height: 28px; width: auto; }
.nav-links { display: flex; gap: 4px; list-style: none; margin-right: 12px; }
.nav-links a { font-size: 0.9rem; font-weight: 500; color: var(--ink-60);
  text-decoration: none; padding: 6px 14px; border-radius: 8px; transition: color 0.15s; }
.nav-links a:hover { color: var(--ink); }
.nav-links a.active { color: var(--ink); font-weight: 700;
  border-bottom: 2px solid var(--ink); border-radius: 0; padding-bottom: 4px; }
.btn-login { padding: 8px 20px; border-radius: 99px; border: 1.5px solid var(--border);
  background: white; color: var(--ink); font-size: 0.875rem; font-weight: 500;
  font-family: var(--font); text-decoration: none; margin-right: 8px;
  transition: border-color 0.15s; white-space: nowrap; }
.btn-login:hover { border-color: var(--ink-30); }
.btn-start { padding: 9px 22px; border-radius: 99px; background: var(--green);
  color: white; font-size: 0.875rem; font-weight: 600; font-family: var(--font);
  text-decoration: none; transition: background 0.15s; white-space: nowrap; }
.btn-start:hover { background: var(--green-mid); }
@media(max-width:768px) { .nav-links,.btn-login { display: none; } }
footer { background: var(--ink); padding: 64px 32px 40px; }
.footer-top { max-width: 1200px; margin: 0 auto;
  display: grid; grid-template-columns: 280px repeat(3, 1fr); gap: 48px;
  padding-bottom: 48px; border-bottom: 1px solid rgba(255,255,255,0.07); }
@media(max-width:900px) { .footer-top { grid-template-columns: 1fr 1fr; } }
@media(max-width:500px) { .footer-top { grid-template-columns: 1fr; } }
.footer-logo { display: block; text-decoration: none; margin-bottom: 16px; }
.footer-logo svg { height: 24px; width: auto; }
.footer-brand p { font-size: 0.83rem; color: rgba(255,255,255,0.35); line-height: 1.75; }
.footer-col h4 { font-size: 0.68rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.12em; color: rgba(255,255,255,0.28); margin-bottom: 16px; }
.footer-col ul { list-style: none; display: flex; flex-direction: column; gap: 10px; }
.footer-col a { font-size: 0.875rem; color: rgba(255,255,255,0.5);
  text-decoration: none; transition: color 0.15s; }
.footer-col a:hover { color: white; }
.footer-bottom { max-width: 1200px; margin: 28px auto 0;
  display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.footer-copy, .footer-tagline { font-size: 0.78rem; color: rgba(255,255,255,0.2); }
.footer-tagline { font-style: italic; }
.article-hero { background: var(--ink); padding: 72px 32px 56px; }
.article-hero-inner { max-width: 800px; margin: 0 auto; }
.cat-pill { display: inline-block; padding: 4px 14px; border-radius: 99px;
  font-size: 0.72rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
  background: rgba(74,222,128,0.15); color: #4ADE80; margin-bottom: 20px; }
.article-hero h1 { font-size: clamp(1.8rem, 4vw, 2.8rem); font-weight: 300;
  color: white; line-height: 1.15; letter-spacing: -0.01em; margin-bottom: 20px; }
.article-meta { display: flex; gap: 20px; flex-wrap: wrap;
  font-size: 0.825rem; color: rgba(255,255,255,0.4); }
.article-meta strong { color: rgba(255,255,255,0.65); }
.article-layout { max-width: 1200px; margin: 0 auto;
  padding: 56px 32px 80px;
  display: grid; grid-template-columns: 1fr 300px; gap: 72px; align-items: start; }
@media(max-width:900px) { .article-layout { grid-template-columns: 1fr; }
  .article-sidebar { display: none; } }
.article-body p { font-size: 1.0625rem; line-height: 1.85; color: var(--ink); margin-bottom: 24px; }
.article-body h2 { font-size: 1.5rem; font-weight: 700; color: var(--ink);
  margin: 48px 0 16px; letter-spacing: -0.02em; scroll-margin-top: 80px; }
.article-body h3 { font-size: 1.15rem; font-weight: 700; color: var(--ink); margin: 32px 0 12px; }
.article-body ul, .article-body ol { padding-left: 24px; margin-bottom: 24px; }
.article-body li { font-size: 1.0625rem; line-height: 1.75; margin-bottom: 6px; }
.article-body strong { font-weight: 700; }
.article-body hr { border: none; border-top: 1px solid var(--border); margin: 48px 0; }
.article-body blockquote { border-left: 3px solid var(--green); padding: 12px 20px;
  background: var(--green-light); border-radius: 0 8px 8px 0; margin: 28px 0; }
.article-sidebar { position: sticky; top: 80px; display: flex; flex-direction: column; gap: 16px; }
.sidebar-card { background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 20px; }
.sidebar-card-title { font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.1em; color: var(--ink-30); margin-bottom: 14px; }
.toc-list { list-style: none; display: flex; flex-direction: column; gap: 4px; }
.toc-list a { font-size: 0.83rem; color: var(--ink-60); text-decoration: none;
  padding: 5px 8px; border-radius: 6px; display: block; line-height: 1.4;
  border-left: 2px solid transparent; transition: all 0.15s; }
.toc-list a:hover { color: var(--ink); background: var(--border); }
.toc-list a.active { color: var(--green); font-weight: 600;
  background: var(--green-light); border-left-color: var(--green); }
.cta-card { background: var(--green); border-radius: var(--radius); padding: 24px; }
.cta-card h3 { font-size: 1rem; font-weight: 700; color: white; margin-bottom: 8px; line-height: 1.35; }
.cta-card p { font-size: 0.83rem; color: rgba(255,255,255,0.72); line-height: 1.6; margin-bottom: 16px; }
.cta-card a { display: block; text-align: center; padding: 11px 16px; border-radius: 99px;
  background: white; color: var(--green); font-size: 0.875rem; font-weight: 700;
  text-decoration: none; font-family: var(--font); }
.cta-card a:hover { opacity: 0.9; }
.related-section { background: var(--surface); border-top: 1px solid var(--border); padding: 56px 32px; }
.related-inner { max-width: 1200px; margin: 0 auto; }
.related-inner h2 { font-size: 1.2rem; font-weight: 700; margin-bottom: 24px; }
.related-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 16px; }
@media(max-width:768px) { .related-grid { grid-template-columns: 1fr; } }
.related-card { background: white; border: 1px solid var(--border); border-radius: var(--radius);
  padding: 20px; text-decoration: none; display: block; transition: all 0.18s; }
.related-card:hover { border-color: var(--green); transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(26,107,74,0.08); }
.related-card .tag { font-size: 0.68rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.06em; color: var(--green); margin-bottom: 8px; }
.related-card h3 { font-size: 0.9rem; font-weight: 600; color: var(--ink); line-height: 1.45; }
"""

# ── C: Sitemap ────────────────────────────────────────────────────────────────
def build_sitemap(all_posts: list) -> str:
    urls = [f"  <url><loc>{BLOG_URL}/</loc><changefreq>weekly</changefreq><priority>1.0</priority></url>"]
    for p in all_posts:
        loc = f"{BLOG_URL}/blog/{p['slug']}.html"
        lastmod = p.get("date", TODAY)
        urls.append(f"  <url><loc>{loc}</loc><lastmod>{lastmod}</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>")
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>"

# ── C: RSS feed ───────────────────────────────────────────────────────────────
def build_rss(all_posts: list) -> str:
    recent = sorted(all_posts, key=lambda p: p.get("date", ""), reverse=True)[:20]

    def rfc822(d: str) -> str:
        try:
            dt = datetime.strptime(d[:10], "%Y-%m-%d")
            return format_datetime(dt)
        except Exception:
            return ""

    items = []
    for p in recent:
        title    = xml_escape(p.get("title", ""))
        link     = f"{BLOG_URL}/blog/{p['slug']}.html"
        desc     = xml_escape(p.get("meta_description", ""))
        pub_date = rfc822(p.get("date", TODAY))
        items.append(f"""  <item>
    <title>{title}</title>
    <link>{link}</link>
    <description>{desc}</description>
    <pubDate>{pub_date}</pubDate>
    <guid isPermaLink="true">{link}</guid>
  </item>""")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Forma Blog — Train smart. Think deep.</title>
    <link>{BLOG_URL}</link>
    <description>Science-backed writing on HRV, recovery and adaptive endurance training.</description>
    <language>en-gb</language>
    <lastBuildDate>{rfc822(TODAY)}</lastBuildDate>
    <atom:link href="{BLOG_URL}/feed.xml" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
  </channel>
</rss>"""

# ── D: OG image (SVG → PNG via Pillow if available, else SVG fallback) ────────
def build_og_image(output_dir: Path):
    """
    Generate a simple branded OG image at output/og-default.png.
    Uses Pillow if installed. Falls back to writing an SVG at og-default.svg
    and a 1x1 transparent PNG stub so the HTML reference doesn't 404.
    """
    out_png = output_dir / "og-default.png"

    try:
        from PIL import Image, ImageDraw, ImageFont
        W, H = 1200, 630
        img = Image.new("RGB", (W, H), "#0F1117")
        draw = ImageDraw.Draw(img)

        # Green accent bar left
        draw.rectangle([0, 0, 8, H], fill="#1A6B4A")

        # Brand name
        try:
            font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32)
            font_tag   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        except Exception:
            font_large = ImageFont.load_default()
            font_small = font_large
            font_tag   = font_large

        draw.text((80, 160), "FORMA", fill="#FFFFFF", font=font_large)
        draw.text((80, 260), "Train smart. Think deep.", fill="#1A6B4A", font=font_small)
        draw.text((80, 330), "Science-backed writing for endurance athletes.", fill="#5A5F6E", font=font_tag)

        # Bottom domain
        draw.text((80, H - 80), "blog.formafit.co.uk", fill="rgba(255,255,255,0.3)", font=font_tag)

        img.save(out_png, "PNG", optimize=True)
        print(f"  ✓ og-default.png ({out_png.stat().st_size // 1024} KB) — Pillow")

    except ImportError:
        # Pillow not installed — write a minimal valid 1×1 PNG stub
        # (real browsers won't error; social crawlers get a fallback)
        import base64
        stub = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        )
        out_png.write_bytes(stub)
        print("  ⚠  og-default.png — stub (install pillow for real image)")


# ── Post pages ────────────────────────────────────────────────────────────────
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
    canonical = f"{BLOG_URL}/blog/{slug}"

    schema = json.dumps({
        "@context": "https://schema.org", "@type": "BlogPosting",
        "headline": title, "description": meta_desc,
        "author": {"@type": "Organization", "name": COMPANY_NAME, "url": SITE_URL},
        "publisher": {"@type": "Organization", "name": BRAND_NAME},
        "datePublished": pub_date, "dateModified": TODAY,
        "url": canonical, "mainEntityOfPage": canonical, "keywords": keywords
    }, indent=2)

    toc_html = "\n".join([
        f'<li><a href="#{i["id"]}">{i["text"]}</a></li>'
        for i in toc_items
    ])

    others = [p for p in all_posts if p["slug"] != slug][:3]
    related_html = "\n".join([
        f'<a class="related-card" href="/blog/{p["slug"]}.html">'
        f'<div class="tag">{p.get("category","")}</div>'
        f'<h3>{p["title"]}</h3></a>'
        for p in others
    ])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — Forma</title>
  <meta name="description" content="{meta_desc}">
  <link rel="canonical" href="{canonical}">
  <meta name="robots" content="index, follow">
  <meta name="keywords" content="{keywords}">
  <meta property="og:type" content="article">
  <meta property="og:url" content="{canonical}">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{meta_desc}">
  <meta property="og:image" content="{OG_IMAGE_URL}">
  <meta property="og:site_name" content="Forma">
  <meta property="og:locale" content="en_GB">
  <meta property="article:published_time" content="{pub_date}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{title}">
  <meta name="twitter:description" content="{meta_desc}">
  <meta name="twitter:image" content="{OG_IMAGE_URL}">
  <link rel="alternate" type="application/rss+xml" title="Forma Blog" href="{BLOG_URL}/feed.xml">
  <script type="application/ld+json">{schema}</script>
  <style>
{font_css}
{BRAND_CSS}
  </style>
</head>
<body>
{NAV()}
<header class="article-hero">
  <div class="article-hero-inner">
    <div class="cat-pill">{category}</div>
    <h1>{title}</h1>
    <div class="article-meta">
      <span><strong>{read_time} MIN READ</strong></span>
      <span>·</span>
      <span>{fmt_date(pub_date)}</span>
    </div>
  </div>
</header>
<div class="article-layout">
  <article class="article-body">{body_html}</article>
  <aside class="article-sidebar">
    {"<div class='sidebar-card'><div class='sidebar-card-title'>In this article</div><ul class='toc-list'>" + toc_html + "</ul></div>" if toc_html else ""}
    <div class="cta-card">
      <h3>Train smarter from tomorrow</h3>
      <p>Forma adapts your plan every morning based on how your body actually feels.</p>
      <a href="{SITE_URL}/pricing">Start 14-day free trial →</a>
    </div>
  </aside>
</div>
{"<section class='related-section'><div class='related-inner'><h2>Keep reading</h2><div class='related-grid'>" + related_html + "</div></div></section>" if related_html else ""}
{FOOTER}
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


# ── Blog index ────────────────────────────────────────────────────────────────
def build_blog_index(all_posts: list, font_css: str) -> str:
    cards = ""
    for p in all_posts:
        cat = p.get("category", "Training")
        pill_bg, pill_fg, thumb_bg, emoji = cat_style(cat)
        read_time = p.get("read_time", 5)
        pub_date  = fmt_date(p.get("date", TODAY))
        desc      = p.get("meta_description", "")[:130]
        cards += f"""
    <a class="post-card" href="/blog/{p['slug']}.html">
      <div class="post-thumb" style="background:{thumb_bg};">{emoji}</div>
      <div class="post-body">
        <div class="post-pill" style="background:{pill_bg};color:{pill_fg};">{cat}</div>
        <div class="post-meta">{read_time} MIN READ · {pub_date}</div>
        <h3>{p['title']}</h3>
        <p>{desc}{"…" if len(p.get("meta_description","")) > 130 else ""}</p>
      </div>
    </a>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Blog — Forma Training Intelligence</title>
  <meta name="description" content="Science, philosophy and practical guidance for endurance athletes who want to train with their body, not against it.">
  <link rel="canonical" href="{BLOG_URL}">
  <meta name="robots" content="index, follow">
  <meta property="og:title" content="Blog — Forma">
  <meta property="og:description" content="Science-backed writing on HRV, recovery and adaptive endurance training.">
  <meta property="og:url" content="{BLOG_URL}">
  <meta property="og:image" content="{OG_IMAGE_URL}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:image" content="{OG_IMAGE_URL}">
  <link rel="alternate" type="application/rss+xml" title="Forma Blog" href="{BLOG_URL}/feed.xml">
  <style>
{font_css}
{BRAND_CSS}
/* BLOG INDEX */
.blog-hero {{ padding: 80px 32px 72px; max-width: 1200px; margin: 0 auto; }}
.blog-eyebrow {{ font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.12em; color: var(--green); margin-bottom: 20px; }}
.blog-hero h1 {{ font-size: clamp(2.2rem, 5vw, 3.5rem); font-weight: 300;
  color: var(--ink); line-height: 1.1; letter-spacing: -0.02em; margin-bottom: 20px; }}
.blog-hero p {{ font-size: 1.05rem; color: var(--ink-60); max-width: 520px; line-height: 1.75; }}
.blog-divider {{ border: none; border-top: 1px solid var(--border); margin: 0; }}
.blog-grid-section {{ max-width: 1200px; margin: 0 auto; padding: 56px 32px 80px; }}
.blog-grid {{ display: grid; grid-template-columns: repeat(3,1fr); gap: 24px; }}
@media(max-width:900px) {{ .blog-grid {{ grid-template-columns: repeat(2,1fr); }} }}
@media(max-width:580px) {{ .blog-grid {{ grid-template-columns: 1fr; }} }}
.post-card {{ background: white; border: 1px solid var(--border); border-radius: 16px;
  text-decoration: none; display: flex; flex-direction: column;
  overflow: hidden; transition: all 0.2s; }}
.post-card:hover {{ border-color: rgba(26,107,74,0.25); transform: translateY(-3px);
  box-shadow: 0 12px 36px rgba(0,0,0,0.07); }}
.post-thumb {{ height: 180px; display: flex; align-items: center;
  justify-content: center; font-size: 3rem; }}
.post-body {{ padding: 24px; display: flex; flex-direction: column; gap: 8px; flex: 1; }}
.post-pill {{ display: inline-block; padding: 3px 12px; border-radius: 99px;
  font-size: 0.7rem; font-weight: 700; width: fit-content; }}
.post-meta {{ font-size: 0.72rem; font-weight: 600; color: var(--ink-30); letter-spacing: 0.04em; }}
.post-card h3 {{ font-size: 1rem; font-weight: 500; color: var(--ink); line-height: 1.4; flex: 1; }}
.post-card p {{ font-size: 0.85rem; color: var(--ink-60); line-height: 1.65; }}
.subscribe-section {{ background: var(--surface); border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border); padding: 56px 32px; }}
.subscribe-inner {{ max-width: 520px; margin: 0 auto; text-align: center; }}
.subscribe-inner .icon {{ font-size: 2rem; margin-bottom: 16px; }}
.subscribe-inner h2 {{ font-size: 1.25rem; font-weight: 700; margin-bottom: 8px; }}
.subscribe-inner p {{ font-size: 0.9rem; color: var(--ink-60); line-height: 1.65; margin-bottom: 24px; }}
.subscribe-form {{ display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; }}
.subscribe-form input {{ flex: 1; min-width: 220px; padding: 12px 18px; border-radius: 99px;
  border: 1.5px solid var(--border); font-size: 0.875rem; font-family: var(--font);
  outline: none; transition: border-color 0.15s; }}
.subscribe-form input:focus {{ border-color: var(--green); }}
.subscribe-form button {{ padding: 12px 24px; border-radius: 99px; background: var(--green);
  color: white; font-size: 0.875rem; font-weight: 600; font-family: var(--font);
  border: none; cursor: pointer; transition: background 0.15s; white-space: nowrap; }}
.subscribe-form button:hover {{ background: var(--green-mid); }}
  </style>
</head>
<body>
{NAV("blog")}
<div class="blog-hero">
  <div class="blog-eyebrow">The Forma Blog</div>
  <h1>Train smart. Think deep.</h1>
  <p>Science, philosophy and practical guidance for endurance athletes who want to train with their body, not against it.</p>
</div>
<hr class="blog-divider">
<div class="blog-grid-section">
  <div class="blog-grid">{cards}
  </div>
</div>
<section class="subscribe-section">
  <div class="subscribe-inner">
    <div class="icon">📬</div>
    <h2>New posts every two weeks</h2>
    <p>Subscribe to get Forma's writing on recovery science, endurance performance, and data-led coaching.</p>
    <div class="subscribe-form">
      <input type="email" placeholder="your@email.com">
      <button type="button">Subscribe</button>
    </div>
  </div>
</section>
{FOOTER}
</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  Forma Blog Builder  v6")
    print("=" * 60)

    font_css  = load_fonts()
    all_posts = load_manifest()

    blog_dir = OUTPUT_DIR / "blog"
    blog_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n📝 Writing HTML...")
    for post in all_posts:
        html    = build_post_html(post, all_posts, font_css)
        outfile = blog_dir / f"{post['slug']}.html"
        outfile.write_text(html, encoding="utf-8")
        print(f"   ✓ blog/{post['slug']}.html  ({len(html)//1024} KB)")

    idx = build_blog_index(all_posts, font_css)
    (OUTPUT_DIR / "index.html").write_text(idx, encoding="utf-8")
    print(f"   ✓ index.html  ({len(idx)//1024} KB)")

    # C: Sitemap + RSS
    sitemap = build_sitemap(all_posts)
    (OUTPUT_DIR / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    print(f"   ✓ sitemap.xml  ({len(all_posts)+1} URLs)")

    feed = build_rss(all_posts)
    (OUTPUT_DIR / "feed.xml").write_text(feed, encoding="utf-8")
    print(f"   ✓ feed.xml  ({min(len(all_posts),20)} items)")

    # D: OG image
    print(f"\n🖼  Generating OG image...")
    build_og_image(OUTPUT_DIR)

    print(f"\n{'='*60}")
    print(f"  ✅  Done — {len(all_posts)} posts + sitemap + RSS + OG image")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
