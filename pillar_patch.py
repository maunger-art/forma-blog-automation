"""
Patch forma_blog_build.py to add --build-pillar mode.
Run from the forma-blog-automation repo root.
"""
from pathlib import Path
import json, sys

f = Path("forma_blog_build.py")
if not f.exists():
    sys.exit("ERROR: forma_blog_build.py not found — run from repo root")

src = f.read_text()

# ── 1. PILLAR_SPECS_PATH constant ─────────────────────────────────────────
if "PILLAR_SPECS_PATH" not in src:
    done = False
    for variant in [
        'MANIFEST_PATH  = _SCRIPT_DIR / "shared" / "cluster_manifest.json"',
        'MANIFEST_PATH = _SCRIPT_DIR / "shared" / "cluster_manifest.json"',
    ]:
        if variant in src:
            src = src.replace(
                variant,
                variant + '\nPILLAR_SPECS_PATH = _SCRIPT_DIR / "shared" / "pillar_page_specs.json"',
                1
            )
            done = True
            break
    print("+ PILLAR_SPECS_PATH" if done else "! PILLAR_SPECS_PATH anchor not found — check manually")
else:
    print("= PILLAR_SPECS_PATH already present")

# ── 2. --build-pillar argument ────────────────────────────────────────────
if "--build-pillar" not in src:
    src = src.replace(
        'parser.add_argument("--from-queue",',
        (
            'parser.add_argument("--build-pillar", action="store_true",\n'
            '                        help="Build pillar pages from pillar_page_specs.json")\n'
            '    parser.add_argument("--from-queue",'
        )
    )
    print("+ --build-pillar arg")
else:
    print("= --build-pillar arg already present")

# ── 3. build_pillar_html() function ──────────────────────────────────────
PILLAR_FN = '''
def build_pillar_html(spec, all_posts, font_css, link_map=None):
    """Build a long-form pillar page from a pillar_page_specs.json entry."""
    import re as _re

    slug      = spec["slug"]
    h1        = spec["h1"]
    cluster   = spec.get("cluster", "")
    sections  = spec.get("suggested_sections", [])
    tool_ctas = spec.get("tool_ctas", [])
    links_to  = spec.get("internal_links_to", [])
    canonical = f"{BLOG_URL}/blog/{slug}"
    pub_date  = TODAY

    cat_map = {
        "zone-2-training":   "Training Science",
        "hrv-readiness":     "Wearables",
        "training-load":     "Training Science",
        "garmin-wearable":   "Wearables",
        "marathon-training": "Running",
        "cycling-endurance": "Cycling",
        "recovery-sleep":    "Recovery",
        "injury-prevention": "Recovery",
    }
    category  = cat_map.get(cluster, "Training Science")
    h1_clean  = h1.lower().rstrip("?")
    meta_desc = f"The complete guide to {h1_clean}. Evidence-based answers for endurance athletes."

    # Schema
    faq_entries = [
        {
            "@type": "Question",
            "name": q,
            "acceptedAnswer": {
                "@type": "Answer",
                "text": f"See the full answer in our guide to {h1_clean}."
            }
        }
        for q in sections[:6]
    ]
    schema_article = {
        "@context": "https://schema.org", "@type": "Article",
        "headline": h1, "description": meta_desc,
        "author": {"@type": "Organization", "name": COMPANY_NAME, "url": SITE_URL},
        "publisher": {"@type": "Organization", "name": BRAND_NAME},
        "datePublished": pub_date, "dateModified": TODAY,
        "url": canonical, "mainEntityOfPage": canonical,
    }
    schema_faq = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": faq_entries
    }

    # TOC
    toc_li = "".join(
        f\'<li><a href="#s{i}">{s}</a></li>\'
        for i, s in enumerate(sections)
    )
    toc_block = (
        f\'<div class="sidebar-card">\'
        f\'<div class="sidebar-card-title">In this article</div>\'
        f\'<ul class="toc-list">{toc_li}</ul></div>\'
    ) if sections else ""

    # Sections
    sec_html = "".join(
        f\'<h2 id="s{i}">{s}</h2>\'
        f\'<p style="color:#666;font-style:italic;line-height:1.7">\'
        f\'This section covers {s.lower().rstrip("?")}. \'
        f\'Forma uses this data to personalise your training plan.</p>\'
        for i, s in enumerate(sections)
    )

    # Tool CTAs
    tool_cards = "".join(
        f\'<div class="tool-cta-card">\'
        f\'<span style="font-size:1.5rem">&#x1F9EE;</span>\'
        f\'<div><strong>{t.title()}</strong>\'
        f\'<p style="margin:.2rem 0 0;font-size:.85rem;color:#666">Free calculator</p></div>\'
        f\'<a href="{SITE_URL}/tools/{_re.sub(r" +", "-", t.lower())}" \'
        f\'style="margin-left:auto;background:#1A6B4A;color:white;padding:.5rem 1rem;\'
        f\'border-radius:6px;font-size:.85rem;font-weight:600;text-decoration:none">\'
        f\'Try free &#x2192;</a></div>\'
        for t in tool_ctas
    )
    tool_block = (
        f\'<div style="margin:2.5rem 0"><h3>Free calculators for this topic</h3>{tool_cards}</div>\'
    ) if tool_ctas else ""

    # Related posts
    related_posts = [p for p in all_posts if p["slug"] in links_to][:4]
    related_cards = "".join(
        f\'<a class="related-card" href="/blog/{p["slug"]}.html">\'
        f\'<div class="tag">{p.get("category", "")}</div>\'
        f\'<h3>{p["title"]}</h3></a>\'
        for p in related_posts
    )
    related_block = (
        f\'<section class="related-section"><div class="related-inner">\'
        f\'<h2>Keep reading</h2><div class="related-grid">{related_cards}</div>\'
        f\'</div></section>\'
    ) if related_cards else ""

    # Quick answer (AI search optimisation)
    qa_block = (
        f\'<div style="background:#F0FFF8;border-left:4px solid #1A6B4A;\'
        f\'padding:1.25rem 1.5rem;border-radius:0 8px 8px 0;margin:1.5rem 0 2rem">\'
        f\'<div style="font-size:.7rem;font-weight:700;letter-spacing:.1em;\'
        f\'text-transform:uppercase;color:#1A6B4A;margin-bottom:.5rem">Quick Answer</div>\'
        f\'<p>{h1.rstrip("?")} — this guide covers everything you need to know, \'
        f\'from the science to practical steps you can take today. \'
        f\'Forma uses this data to adapt your training plan every morning.</p></div>\'
    )

    pillar_css = (
        ".pillar-badge{display:inline-block;background:#1A6B4A;color:white;"
        "font-size:.65rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;"
        "padding:.25rem .6rem;border-radius:4px;margin-bottom:.75rem}"
        ".tool-cta-card{display:flex;align-items:center;gap:1rem;"
        "background:#FAFAFA;border:1px solid #E5E7EB;"
        "border-radius:8px;padding:1rem 1.25rem;margin-bottom:.75rem}"
    )

    s_art = json.dumps(schema_article, indent=2)
    s_faq = json.dumps(schema_faq, indent=2)

    return (
        "<!DOCTYPE html>\\n"
        \'<html lang="en">\\n\'
        "<head>\\n"
        \'<meta charset="UTF-8">\\n\'
        \'<meta name="viewport" content="width=device-width,initial-scale=1.0">\\n\'
        f"<title>{h1} &#x2014; Complete Guide &#x2014; Forma</title>\\n"
        f\'<meta name="description" content="{meta_desc}">\\n\'
        f\'<link rel="canonical" href="{canonical}">\\n\'
        \'<meta name="robots" content="index,follow">\\n\'
        f\'<meta property="og:type" content="article">\\n\'
        f\'<meta property="og:url" content="{canonical}">\\n\'
        f\'<meta property="og:title" content="{h1}">\\n\'
        f\'<meta property="og:description" content="{meta_desc}">\\n\'
        f\'<meta property="og:image" content="{OG_IMAGE_URL}">\\n\'
        \'<meta property="og:site_name" content="Forma">\\n\'
        \'<meta property="og:locale" content="en_GB">\\n\'
        f\'<meta name="twitter:card" content="summary_large_image">\\n\'
        f\'<meta name="twitter:title" content="{h1}">\\n\'
        f\'<meta name="twitter:description" content="{meta_desc}">\\n\'
        f\'<meta name="twitter:image" content="{OG_IMAGE_URL}">\\n\'
        f\'<link rel="alternate" type="application/rss+xml" title="Forma Blog" href="{BLOG_URL}/feed.xml">\\n\'
        f\'<script type="application/ld+json">{s_art}</script>\\n\'
        f\'<script type="application/ld+json">{s_faq}</script>\\n\'
        "<style>\\n"
        f"{font_css}\\n"
        f"{BRAND_CSS}\\n"
        f"{pillar_css}\\n"
        "</style>\\n"
        "</head>\\n"
        "<body>\\n"
        f"{NAV()}\\n"
        \'<header class="article-hero">\\n\'
        \'<div class="article-hero-inner">\\n\'
        \'<div class="pillar-badge">Complete Guide</div>\\n\'
        f\'<div class="cat-pill">{category}</div>\\n\'
        f"<h1>{h1}</h1>\\n"
        \'<div class="article-meta">\'
        \'<span><strong>10 MIN READ</strong></span>\'
        \'<span>&#xB7;</span>\'
        f\'<span>Updated {fmt_date(pub_date)}</span>\'
        \'<span>&#xB7;</span>\'
        \'<span>Forma Training Intelligence</span>\'
        "</div>\\n"
        "</div></header>\\n"
        \'<div class="article-layout">\\n\'
        \'<article class="article-body">\\n\'
        f"{qa_block}\\n"
        f"{sec_html}\\n"
        f"{tool_block}\\n"
        "</article>\\n"
        \'<aside class="article-sidebar">\\n\'
        f"{toc_block}\\n"
        \'<div class="cta-card">\\n\'
        "<h3>Train smarter from tomorrow</h3>\\n"
        "<p>Forma adapts your plan every morning based on how your body actually feels.</p>\\n"
        f\'<a href="{SITE_URL}/pricing">Start 14-day free trial &#x2192;</a>\\n\'
        "</div>\\n"
        "</aside>\\n"
        "</div>\\n"
        f"{related_block}\\n"
        f"{FOOTER}\\n"
        "<script>\\n"
        "document.querySelectorAll(\'.toc-list a\').forEach(a => {\\n"
        "  a.addEventListener(\'click\', e => {\\n"
        "    e.preventDefault();\\n"
        "    const t = document.getElementById(a.getAttribute(\'href\').slice(1));\\n"
        "    if (t) t.scrollIntoView({ behavior:\'smooth\', block:\'start\' });\\n"
        "  });\\n"
        "});\\n"
        "</script>\\n"
        "</body>\\n"
        "</html>"
    )

'''

if "def build_pillar_html(" not in src:
    src = src.replace("def build_post_html(", PILLAR_FN + "def build_post_html(", 1)
    print("+ build_pillar_html()")
else:
    print("= build_pillar_html() already present")

# ── 4. main() handler ─────────────────────────────────────────────────────
HANDLER = (
    "\n    if args.build_pillar:\n"
    "        print('\\n Building pillar pages...')\n"
    "        if not PILLAR_SPECS_PATH.exists():\n"
    "            print(f'  Error: {PILLAR_SPECS_PATH} not found — run cluster_builder first')\n"
    "            return\n"
    "        specs      = json.loads(PILLAR_SPECS_PATH.read_text())\n"
    "        font_css   = load_fonts()\n"
    "        all_posts  = load_manifest()\n"
    "        link_map   = _load_graph_link_map()\n"
    "        pillar_dir = OUTPUT_DIR / 'blog'\n"
    "        pillar_dir.mkdir(parents=True, exist_ok=True)\n"
    "        for spec in specs:\n"
    "            html    = build_pillar_html(spec, all_posts, font_css, link_map)\n"
    "            outfile = pillar_dir / f\"{spec['slug']}.html\"\n"
    "            outfile.write_text(html, encoding='utf-8')\n"
    "            print(f\"   + blog/{spec['slug']}.html  ({len(html)//1024} KB)\")\n"
    "        print(f'\\n  Done - {len(specs)} pillar pages built')\n"
    "        return\n"
)

if "args.build_pillar" not in src:
    anchor = "    font_css  = load_fonts()\n    all_posts = load_manifest()\n    link_map  = _load_graph_link_map()"
    if anchor in src:
        src = src.replace(anchor, HANDLER + anchor, 1)
        print("+ main() handler")
    else:
        print("! main() anchor not found — check manually")
else:
    print("= main() handler already present")

# ── Write ─────────────────────────────────────────────────────────────────
f.write_text(src)
print("\nDone — forma_blog_build.py patched")
