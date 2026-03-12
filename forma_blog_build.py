#!/usr/bin/env python3
"""
Forma Blog Builder  v7
======================
Unchanged from v5 except three additions:
  C. writes output/sitemap.xml and output/feed.xml
  D. generates output/og-default.png and injects og:image / twitter:image
     into every page (index + posts)
Adds to v6:
  E. Automatic internal linking — inserts contextual links between related
     posts based on keyword matching. No AI, no external deps, HTML-only.
"""

import argparse
import json
import re
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

CLUSTER_TO_CATEGORY = {
    "zone-2-training":   "Training Science",
    "hrv-readiness":     "HRV",
    "training-load":     "Load",
    "garmin-wearable":   "Wearables",
    "marathon-training": "Performance",
    "cycling-endurance": "Performance",
    "recovery-sleep":    "Recovery",
    "injury-prevention": "Recovery",
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
    drawer_items = []
    for label, url, k in links:
        active_class = " class='active'" if k == active else ""
        items.append(f'<li><a href="{url}"{active_class}>{label}</a></li>')
        drawer_active = " drawer-active" if k == active else ""
        drawer_items.append(f'<a href="{url}" class="drawer-link{drawer_active}">{label}</a>')
    lis = "\n".join(items)
    drawer_links = "\n      ".join(drawer_items)
    return f"""<nav id="site-nav">
  <div class="nav-inner">
    <a class="nav-logo" href="{SITE_URL}">{LOGO_SVG}</a>
    <ul class="nav-links">{lis}</ul>
    <a href="{SITE_URL}/login" class="btn-login">Log in</a>
    <a href="{SITE_URL}/pricing" class="btn-start">Start free</a>
    <button class="nav-menu-btn" id="menuBtn" aria-label="Open menu" aria-expanded="false">
      <span class="bar"></span><span class="bar"></span><span class="bar"></span>
    </button>
  </div>
</nav>
<div class="nav-drawer" id="navDrawer" aria-hidden="true">
  <div class="drawer-inner">
    <div class="drawer-header">
      <a class="drawer-logo" href="{SITE_URL}">{LOGO_SVG}</a>
      <button class="drawer-close" id="drawerClose" aria-label="Close menu">
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><line x1="2" y1="2" x2="16" y2="16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><line x1="16" y1="2" x2="2" y2="16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
      </button>
    </div>
    <nav class="drawer-nav">
      {drawer_links}
    </nav>
    <div class="drawer-cta">
      <a href="{SITE_URL}/pricing" class="drawer-btn-start">Start free</a>
      <a href="{SITE_URL}/login" class="drawer-btn-login">Log in</a>
    </div>
  </div>
</div>
<div class="nav-overlay" id="navOverlay"></div>"""

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

# ── Mobile drawer JS (injected into every page) ───────────────────────────────
DRAWER_JS = """
const menuBtn  = document.getElementById('menuBtn');
const drawer   = document.getElementById('navDrawer');
const overlay  = document.getElementById('navOverlay');
const closeBtn = document.getElementById('drawerClose');
function openDrawer() {
  drawer.classList.add('open'); overlay.classList.add('open');
  menuBtn.setAttribute('aria-expanded','true');
  drawer.setAttribute('aria-hidden','false');
  document.body.style.overflow = 'hidden';
}
function closeDrawer() {
  drawer.classList.remove('open'); overlay.classList.remove('open');
  menuBtn.setAttribute('aria-expanded','false');
  drawer.setAttribute('aria-hidden','true');
  document.body.style.overflow = '';
}
if (menuBtn)  menuBtn.addEventListener('click', openDrawer);
if (closeBtn) closeBtn.addEventListener('click', closeDrawer);
if (overlay)  overlay.addEventListener('click', closeDrawer);
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDrawer(); });
"""

# ── Shared CSS ────────────────────────────────────────────────────────────────
BRAND_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Oxanium:wght@200;300;400;500;600;700;800&display=swap');
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --green: #1A6B4A; --green-mid: #2D9165; --green-light: #F0FFF4;
  --ink: #0F1117; --ink-60: #5A5F6E; --ink-30: #B0B5C3; --ink-10: #F5F6F8;
  --surface: #F8F9FB; --border: #E8EAF0; --white: #FFFFFF; --radius: 12px;
  --font: 'Oxanium', system-ui, sans-serif;
}
body { font-family: var(--font); color: var(--ink); background: var(--white);
  font-size: 16px; line-height: 1.6; -webkit-font-smoothing: antialiased; }
h1, h2, h3, h4 { font-family: var(--font); font-weight: 300; }
nav { position: sticky; top: 0; z-index: 100; background: rgba(255,255,255,0.97);
  backdrop-filter: blur(12px); border-bottom: 1px solid var(--border); }
.nav-inner { max-width: 1200px; margin: 0 auto; padding: 0 32px; height: 68px;
  display: flex; align-items: center; position: relative; }
.nav-logo { display: flex; align-items: center; text-decoration: none;
  flex-shrink: 0; margin-right: auto; }
.nav-logo svg { height: 28px; width: auto; }
.nav-links { display: flex; gap: 4px; list-style: none;
  position: absolute; left: 50%; transform: translateX(-50%); }
.nav-links a { font-size: 0.9rem; font-weight: 500; color: var(--ink-60);
  text-decoration: none; padding: 6px 14px; border-radius: 8px; transition: color 0.15s; }
.nav-links a:hover { color: var(--ink); }
.nav-links a.active { color: var(--green); font-weight: 600;
  border-bottom: 2px solid var(--green); border-radius: 0; padding-bottom: 4px; }
.btn-login { padding: 8px 20px; border-radius: 99px; border: 1.5px solid var(--border);
  background: white; color: var(--ink); font-size: 0.875rem; font-weight: 500;
  font-family: var(--font); text-decoration: none; margin-right: 8px;
  transition: border-color 0.15s; white-space: nowrap; }
.btn-login:hover { border-color: var(--ink-30); }
.btn-start { padding: 9px 22px; border-radius: 99px; background: var(--green);
  color: white; font-size: 0.875rem; font-weight: 600; font-family: var(--font);
  text-decoration: none; transition: background 0.15s; white-space: nowrap; }
.btn-start:hover { background: var(--green-mid); }
/* ── Mobile nav trigger ── */
.nav-menu-btn { display: none; align-items: center; justify-content: center;
  width: 40px; height: 40px; border-radius: 10px; border: 1.5px solid var(--border);
  background: white; cursor: pointer; flex-direction: column; gap: 5px; padding: 0;
  margin-left: 12px; transition: border-color 0.15s, background 0.15s; flex-shrink: 0; }
.nav-menu-btn:hover { border-color: var(--ink-30); background: var(--surface); }
.nav-menu-btn .bar { display: block; width: 16px; height: 1.5px; background: var(--ink);
  border-radius: 2px; transition: transform 0.2s, opacity 0.2s; }
.nav-menu-btn[aria-expanded="true"] .bar:nth-child(1) { transform: translateY(6.5px) rotate(45deg); }
.nav-menu-btn[aria-expanded="true"] .bar:nth-child(2) { opacity: 0; }
.nav-menu-btn[aria-expanded="true"] .bar:nth-child(3) { transform: translateY(-6.5px) rotate(-45deg); }
/* ── Drawer ── */
.nav-drawer { position: fixed; top: 0; right: 0; bottom: 0; width: min(320px, 88vw);
  background: white; z-index: 200; transform: translateX(100%);
  transition: transform 0.28s cubic-bezier(0.4,0,0.2,1);
  box-shadow: -8px 0 32px rgba(0,0,0,0.08); display: flex; flex-direction: column; }
.nav-drawer.open { transform: translateX(0); }
.nav-overlay { position: fixed; inset: 0; background: rgba(15,17,23,0.35);
  z-index: 199; opacity: 0; pointer-events: none;
  transition: opacity 0.28s ease; backdrop-filter: blur(2px); }
.nav-overlay.open { opacity: 1; pointer-events: auto; }
.drawer-inner { display: flex; flex-direction: column; height: 100%; padding: 0; }
.drawer-header { display: flex; align-items: center; justify-content: space-between;
  padding: 0 20px; height: 68px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.drawer-logo svg { height: 24px; width: auto; }
.drawer-close { display: flex; align-items: center; justify-content: center;
  width: 36px; height: 36px; border-radius: 8px; border: 1.5px solid var(--border);
  background: white; cursor: pointer; color: var(--ink); transition: border-color 0.15s; }
.drawer-close:hover { border-color: var(--ink-30); }
.drawer-nav { display: flex; flex-direction: column; padding: 12px 12px;
  flex: 1; gap: 2px; }
.drawer-link { display: block; padding: 13px 16px; border-radius: 10px;
  font-size: 1rem; font-weight: 500; color: var(--ink-60);
  text-decoration: none; font-family: var(--font); transition: background 0.12s, color 0.12s; }
.drawer-link:hover { background: var(--surface); color: var(--ink); }
.drawer-link.drawer-active { color: var(--green); font-weight: 600;
  background: var(--green-light); }
.drawer-cta { padding: 16px 20px 32px; border-top: 1px solid var(--border);
  display: flex; flex-direction: column; gap: 10px; }
.drawer-btn-start { display: block; text-align: center; padding: 13px 20px;
  border-radius: 99px; background: var(--green); color: white;
  font-size: 0.9rem; font-weight: 600; font-family: var(--font);
  text-decoration: none; transition: background 0.15s; }
.drawer-btn-start:hover { background: var(--green-mid); }
.drawer-btn-login { display: block; text-align: center; padding: 12px 20px;
  border-radius: 99px; border: 1.5px solid var(--border); background: white;
  color: var(--ink); font-size: 0.9rem; font-weight: 500; font-family: var(--font);
  text-decoration: none; transition: border-color 0.15s; }
.drawer-btn-login:hover { border-color: var(--ink-30); }
@media(max-width:768px) {
  .nav-links, .btn-login, .btn-start { display: none; }
  .nav-menu-btn { display: flex; }
  .nav-inner { padding: 0 20px; }
  .article-hero { padding: 40px 20px 32px; }
  .blog-hero { padding: 40px 20px 36px; }
}
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
.article-hero { background: var(--ink); padding: 56px 32px 44px; }
.article-hero-inner { max-width: 800px; margin: 0 auto; }
.cat-pill { display: inline-block; padding: 4px 14px; border-radius: 99px;
  font-size: 0.72rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
  background: rgba(74,222,128,0.15); color: #4ADE80; margin-bottom: 20px; }
.article-hero h1 { font-size: clamp(1.8rem, 4vw, 2.8rem); font-weight: 200;
  color: white; line-height: 1.15; letter-spacing: -0.02em; margin-bottom: 20px; }
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
.internal-link { color: var(--green); text-decoration: underline;
  text-decoration-color: rgba(26,107,74,0.35); text-underline-offset: 2px;
  transition: text-decoration-color 0.15s; }
.internal-link:hover { text-decoration-color: var(--green); }
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
        draw.text((80, H - 80), "blog.formafit.co.uk", fill="#4B5060", font=font_tag)

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


# ── E: Internal linking ───────────────────────────────────────────────────────
# Keywords that map to specific post slugs.
# Each entry: "phrase to match in body text" → "slug of target post"
_SCRIPT_DIR   = Path(__file__).resolve().parent
GRAPH_PATH    = _SCRIPT_DIR / "shared" / "question_graph.json"
MANIFEST_PATH = _SCRIPT_DIR / "shared" / "cluster_manifest.json"


def _load_graph_link_map() -> dict[str, str]:
    """
    Build an internal link map from question_graph.json.
    Returns {phrase: slug} for all adjacent_to and parent_of edges
    where both source and target nodes have known slugs.
    Falls back to empty dict if graph files don't exist.
    """
    if not GRAPH_PATH.exists() or not MANIFEST_PATH.exists():
        return _fallback_link_map()

    try:
        edges    = json.loads(GRAPH_PATH.read_text())   # list of edge dicts
        manifest = json.loads(MANIFEST_PATH.read_text())
    except Exception as exc:
        print(f"⚠  Could not load graph files — {exc}")
        return _fallback_link_map()

    # Build pillar slugs from cluster_manifest
    pillar_slugs: dict[str, str] = {}
    for cluster in manifest.get("clusters", []):
        if cluster.get("pillar_slug") and cluster.get("pillar_question"):
            pillar_slugs[cluster["pillar_question"].lower()] = cluster["pillar_slug"]

    import re as _re
    link_map: dict[str, str] = {}

    # Graph is a flat list of edges: {source, target, type, shared_tokens, ...}
    for edge in (edges if isinstance(edges, list) else edges.get("edges", [])):
        if edge.get("type") not in ("adjacent_to", "parent_of"):
            continue

        target_text = edge.get("target", "")
        if not target_text:
            continue

        # Derive slug from target question text
        t = target_text.lower().strip().rstrip("?")
        target_slug = _re.sub(r"[^\w\s-]", "", t)
        target_slug = _re.sub(r"[\s_]+", "-", target_slug)[:80].strip("-")

        # Override with pillar slug if available
        target_slug = pillar_slugs.get(target_text.lower(), target_slug)

        # Map shared tokens to target slug
        for token in edge.get("shared_tokens", []):
            if len(token) >= 4:
                link_map[token] = target_slug

        # Map stripped target phrase
        phrase = _re.sub(
            r"^(what is|what are|how does|how do|why is|why does|how to|is it|can i|should i)\s+",
            "", target_text.lower(), flags=_re.IGNORECASE
        ).strip().rstrip("?")
        if len(phrase) >= 6:
            link_map[phrase] = target_slug

    # Add explicit pillar mappings
    for question_text, slug in pillar_slugs.items():
        phrase = _re.sub(
            r"^(what is|what are|how does|how do)\s+", "",
            question_text, flags=_re.IGNORECASE
        ).strip().rstrip("?")
        if len(phrase) >= 4:
            link_map[phrase] = slug

    print(f"  ✓ Graph link map: {len(link_map)} phrases from {len(edges if isinstance(edges, list) else edges.get('edges', []))} edges")
    return link_map


def _slugify_title(text: str) -> str:
    """Convert question text to a URL slug."""
    text = text.lower().strip().rstrip("?")
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text)[:80].strip("-")


def _fallback_link_map() -> dict[str, str]:
    """Hardcoded fallback used when graph files don't exist yet."""
    print("  ⚠  Graph files not found — using fallback link map")
    return {
        "training load":     "training-load-management-atl-ctl-acwr",
        "acute training load": "training-load-management-atl-ctl-acwr",
        "chronic training load": "training-load-management-atl-ctl-acwr",
        "ACWR":              "training-load-management-atl-ctl-acwr",
        "adaptive training": "science-of-adaptive-training",
        "readiness":         "science-of-adaptive-training",
        "Garmin":            "garmin-vs-oura-vs-whoop-wearable-data",
        "Oura":              "garmin-vs-oura-vs-whoop-wearable-data",
        "WHOOP":             "garmin-vs-oura-vs-whoop-wearable-data",
        "HRV":               "garmin-vs-oura-vs-whoop-wearable-data",
        "overtraining":      "athletes-paradox-why-more-training-isnt-better",
        "recovery":          "athletes-paradox-why-more-training-isnt-better",
        "Zone 2":            "easy-runs-too-hard-killing-gains",
        "easy run":          "easy-runs-too-hard-killing-gains",
        "FTP":               "cycling-training-zones-ftp-isnt-everything",
        "training zones":    "cycling-training-zones-ftp-isnt-everything",
    }

MAX_INTERNAL_LINKS = 3   # Max links injected per post


def inject_internal_links(body_html: str, current_slug: str, all_posts: list, link_map: dict = None) -> str:
    """
    Scan body_html for keyword mentions and convert the FIRST plain-text
    occurrence of each matched phrase into an internal link.
    Rules:
    - Never link a post to itself
    - Never link inside an existing <a>…</a> tag
    - Never link inside a heading tag (h1–h4)
    - Only link the first occurrence of each phrase (no repeat links)
    - Stop after MAX_INTERNAL_LINKS total insertions
    - Only link to posts that exist in the manifest (slugs validated)
    Algorithm:
    1. Build a set of valid target slugs from all_posts (exclude current)
    2. Split body_html into "safe" text segments and "protected" HTML tag
       segments using re.split on any tag pattern
    3. For each text segment, try each keyword in priority order (longest
       first to avoid partial matches like "HRV" matching inside "ACWR HRV")
    4. When a match is found, replace it with <a href="...">phrase</a>
       mark the slug as used, increment counter, move to next segment
    5. Reassemble and return
    Returns body_html unchanged if anything goes wrong (safe fallback).
    """
    try:
        valid_slugs = {p["slug"] for p in all_posts if p["slug"] != current_slug}
        # Only keep entries whose target slug actually exists
        link_map = {
            phrase: slug
            for phrase, slug in (link_map or {}).items()
            if slug in valid_slugs
        }
        if not link_map:
            return body_html

        # Sort phrases longest-first to avoid partial-match shadowing
        phrases_by_length = sorted(link_map.keys(), key=len, reverse=True)
        used_slugs   = set()   # one link per destination post
        links_added  = 0
        result_parts = []

        # Split into alternating: text, tag, text, tag, ...
        # Pattern matches any HTML tag including closing and self-closing
        TAG_RE   = re.compile(r'(<[^>]+>)')
        # Protected contexts: we skip text that sits inside <a> or <h1-h4>
        # We track this with a simple depth counter as we walk the segments
        in_anchor  = 0
        in_heading = 0

        segments = TAG_RE.split(body_html)
        for seg in segments:
            if TAG_RE.match(seg):
                # It's a tag — update protection state, pass through unchanged
                tag_lower = seg.lower()
                if tag_lower.startswith('<a ') or tag_lower == '<a>':
                    in_anchor += 1
                elif tag_lower.startswith('</a'):
                    in_anchor = max(0, in_anchor - 1)
                elif re.match(r'<h[1-4][\s>]', tag_lower):
                    in_heading += 1
                elif re.match(r'</h[1-4]>', tag_lower):
                    in_heading = max(0, in_heading - 1)
                result_parts.append(seg)
                continue

            # It's a text node — attempt linking if not inside protected context
            if in_anchor > 0 or in_heading > 0 or links_added >= MAX_INTERNAL_LINKS:
                result_parts.append(seg)
                continue

            for phrase in phrases_by_length:
                if links_added >= MAX_INTERNAL_LINKS:
                    break
                target_slug = link_map[phrase]
                if target_slug in used_slugs:
                    continue   # already linked to this post

                # Case-insensitive search, but preserve original casing in output
                pattern = re.compile(re.escape(phrase), re.IGNORECASE)
                match   = pattern.search(seg)
                if not match:
                    continue

                original_text = match.group(0)   # preserves original case
                url = f"/blog/{target_slug}.html"
                replacement = (
                    f'<a href="{url}" class="internal-link">{original_text}</a>'
                )
                # Replace only the first occurrence in this segment
                seg = seg[:match.start()] + replacement + seg[match.end():]
                used_slugs.add(target_slug)
                links_added += 1

            result_parts.append(seg)

        linked_html = "".join(result_parts)
        if links_added > 0:
            print(f"     → {links_added} internal link(s) injected")
        return linked_html

    except Exception as e:
        # Never crash the build — return original HTML untouched
        print(f"  ⚠  Internal linking skipped: {e}")
        return body_html



# ── Post pages ────────────────────────────────────────────────────────────────
def build_post_html(post: dict, all_posts: list, font_css: str, link_map: dict = None) -> str:
    slug      = post["slug"]
    title     = post["title"]
    meta_desc = post.get("meta_description", "")
    category  = post.get("category", "Training")
    read_time = post.get("read_time", 5)
    keywords  = post.get("keywords", "")
    body_html = post.get("body_html", "")
    body_html = inject_internal_links(body_html, slug, all_posts, link_map)  # E: internal links
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
{DRAWER_JS}
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
.blog-hero {{ padding: 60px 32px 56px; max-width: 1200px; margin: 0 auto; }}
.blog-eyebrow {{ font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.12em; color: var(--green); margin-bottom: 20px; }}
.blog-hero h1 {{ font-size: clamp(2.2rem, 5vw, 3.5rem) !important; font-weight: 200 !important;
  color: var(--ink); line-height: 1.1; letter-spacing: -0.03em; margin-bottom: 20px; }}
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
<script>{DRAWER_JS}</script>
</body>
</html>"""


# ── CLI ───────────────────────────────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--from-queue",
        action="store_true",
        help="Generate stub manifest entries from shared/queue.json"
    )
    parser.add_argument(
        "--queue-path",
        default="../shared/queue.json",
        help="Path to queue.json (default: ../shared/queue.json)"
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=5.0,
        help="Minimum composite_score to include (default: 5.0)"
    )
    return parser.parse_args()


# ── Queue → Manifest stubs ───────────────────────────────────────────────────
def generate_stubs_from_queue(queue_path: str, min_score: float) -> list[dict]:
    """
    Read queue.json and generate stub manifest entries for unassigned
    questions above min_score that don't already exist in posts_manifest.json.
    Returns list of new stub dicts ready to append to the manifest.
    """
    import slugify  # pip install python-slugify

    queue_file = Path(queue_path)
    if not queue_file.exists():
        print(f"[queue] ERROR: {queue_path} not found")
        return []

    queue = json.loads(queue_file.read_text())

    # Load existing manifest slugs to avoid duplicates
    existing_slugs = set()
    if MANIFEST_FILE.exists():
        existing = json.load(open(MANIFEST_FILE))
        existing_slugs = {p["slug"] for p in existing}

    stubs = []
    for entry in queue:
        if entry.get("status") != "unassigned":
            continue
        if entry.get("composite_score", 0) < min_score:
            continue

        title = entry.get("suggested_title") or entry.get("question_text", "")
        if not title:
            continue

        slug = slugify.slugify(title)[:80]
        if slug in existing_slugs:
            continue

        cluster = entry.get("cluster", "")
        category = CLUSTER_TO_CATEGORY.get(cluster, "Training")

        stub = {
            "slug": slug,
            "title": title,
            "meta_description": f"Everything endurance athletes need to know about {title.lower()}.",
            "category": category,
            "date": TODAY,
            "read_time": 6,
            "keywords": entry.get("question_text", ""),
            "status": "draft",
            "body_html": f"<p><em>Coming soon: {title}</em></p>",
            "toc_items": [],
            "_queue_id": entry.get("question_id"),
            "_cluster": cluster,
            "_composite_score": entry.get("composite_score"),
        }
        stubs.append(stub)
        existing_slugs.add(slug)
        print(f"  [queue→manifest] {slug} (score: {entry.get('composite_score')})")

    print(f"[queue] {len(stubs)} stubs generated")
    return stubs


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    args = parse_args()

    print("=" * 60)
    print("  Forma Blog Builder  v8")
    print("=" * 60)

    if args.from_queue:
        print("\n📥 Generating stubs from queue...")
        stubs = generate_stubs_from_queue(args.queue_path, args.min_score)
        if stubs:
            existing = json.load(open(MANIFEST_FILE)) if MANIFEST_FILE.exists() else []
            existing.extend(stubs)
            with open(MANIFEST_FILE, "w") as fh:
                json.dump(existing, fh, indent=2)
            print(f"  ✓ {len(stubs)} stubs appended to {MANIFEST_FILE}")
        return  # Don't build HTML — just update manifest, let next step build

    font_css  = load_fonts()
    all_posts = load_manifest()
    link_map  = _load_graph_link_map()

    blog_dir = OUTPUT_DIR / "blog"
    blog_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n📝 Writing HTML...")
    for post in all_posts:
        html    = build_post_html(post, all_posts, font_css, link_map)
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
