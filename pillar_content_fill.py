#!/usr/bin/env python3
"""
Forma Pillar Content Fill
=========================
Reads pillar_page_specs.json, generates full long-form content for each
pillar page via the Anthropic API, and rebuilds the pillar HTML files.

Each pillar page gets 2,500-3,500 words of comprehensive, section-by-section
content — written as a single coherent guide rather than stitched fragments.

Usage:
    python3 pillar_content_fill.py                    # fill all pillars
    python3 pillar_content_fill.py --slug zone-2      # fill one pillar by slug
    python3 pillar_content_fill.py --dry-run          # preview without generating
    python3 pillar_content_fill.py --rebuild          # rebuild HTML after filling

Requirements:
    ANTHROPIC_API_KEY environment variable or --api-key flag
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
REPO_ROOT         = Path(__file__).resolve().parent
PILLAR_SPECS_PATH = REPO_ROOT / "shared" / "pillar_page_specs.json"
MANIFEST_PATH     = REPO_ROOT / "posts_manifest.json"
BLOG_BUILDER      = REPO_ROOT / "forma_blog_build.py"
OUTPUT_DIR        = REPO_ROOT / "output" / "blog"

# ── Anthropic API ──────────────────────────────────────────────────────────────
API_URL = "https://api.anthropic.com/v1/messages"
MODEL   = "claude-sonnet-4-20250514"

# ── Cluster context for prompt ─────────────────────────────────────────────────
CLUSTER_CONTEXT = {
    "zone-2-training":   "Zone 2 training, aerobic base building, easy running pace, MAF method, fat oxidation, mitochondrial density, low-intensity endurance",
    "hrv-readiness":     "Heart rate variability, Garmin training readiness, recovery status, HRV4Training, parasympathetic nervous system, autonomic balance",
    "training-load":     "Training load management, ATL (acute training load), CTL (chronic training load), ACWR (acute:chronic workload ratio), TSS, overtraining prevention",
    "garmin-wearable":   "Garmin wearables, Garmin Connect, sleep tracking, stress scores, Body Battery, training status, Firstbeat Analytics, GPS accuracy",
    "marathon-training": "Marathon training, long run structure, periodisation, taper strategy, race-day nutrition, pacing strategy, 16-20 week build",
    "cycling-endurance": "Cycling endurance, FTP (functional threshold power), training zones, power-based training, VO2max intervals, long ride structure, base miles",
    "recovery-sleep":    "Recovery runs, active recovery, sleep quality for athletes, returning from illness, rest day protocols, parasympathetic recovery",
    "injury-prevention": "Running injury prevention, load management, strength training for runners, biomechanics, hip stability, glute activation, tendon conditioning",
}


def slugify(text: str) -> str:
    text = text.lower().strip().rstrip("?")
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text)[:80].strip("-")


def load_specs() -> list[dict]:
    if not PILLAR_SPECS_PATH.exists():
        sys.exit(f"ERROR: {PILLAR_SPECS_PATH} not found — run cluster_builder first")
    return json.loads(PILLAR_SPECS_PATH.read_text())


def load_manifest() -> list[dict]:
    if not MANIFEST_PATH.exists():
        return []
    return json.loads(MANIFEST_PATH.read_text())


def build_prompt(spec: dict) -> str:
    h1       = spec["h1"]
    cluster  = spec.get("cluster", "")
    sections = spec.get("suggested_sections", [])
    tool_ctas = spec.get("tool_ctas", [])

    context  = CLUSTER_CONTEXT.get(cluster, "endurance training for runners and cyclists")

    # Format sections as a numbered list for the prompt
    sections_formatted = "\n".join(f"{i+1}. {s}" for i, s in enumerate(sections))

    # Tool CTA note
    tool_note = ""
    if tool_ctas:
        tool_names = ", ".join(t.title() for t in tool_ctas)
        tool_note = f"\nNote: This topic has free calculator tools available ({tool_names}). Reference these naturally in the relevant sections where a reader would want to calculate their own numbers."

    return f"""You are writing a comprehensive long-form guide for Forma, an adaptive endurance training app for runners and cyclists.

Forma's voice: authoritative, science-backed, written for serious amateur athletes. Direct and specific. No motivational filler. No throat-clearing. Every sentence earns its place.

TOPIC CONTEXT: {context}

Write a complete, comprehensive guide answering: "{h1}"

The guide must cover ALL of these sections in order:
{sections_formatted}
{tool_note}

TARGET: 2,500-3,500 words total across all sections.

REQUIRED OUTPUT FORMAT — respond with a single JSON object only, no markdown fences, no preamble:

{{
  "sections": [
    {{
      "id": "s0",
      "heading": "Exact section heading text from the list above",
      "html": "<p>Full HTML content for this section...</p>"
    }},
    ...one entry per section
  ],
  "intro_html": "<p>Opening 2-3 paragraphs before the first section heading. Hook immediately.</p>",
  "meta_description": "Compelling meta description 140-155 chars covering the full guide",
  "keywords": "comma-separated keyword phrases (8-10 terms)"
}}

CONTENT REQUIREMENTS:
- intro_html: 150-250 words. Hook immediately — state the core problem or insight. No "In this guide we will cover..." openers.
- Each section html: 250-400 words. Dense, specific, actionable. Use <p> tags for paragraphs, <strong> for key terms, <ul>/<li> for lists where natural (max 1 list per section).
- Include specific numbers, study references, or measurable thresholds in each section (e.g. "Zone 2 sits below 75% of max heart rate", "studies show a 6-week aerobic base phase increases mitochondrial density by 15-25%").
- The sections should flow as a coherent guide — later sections can reference earlier ones naturally.
- End the final section with a forward-looking paragraph that references how Forma's adaptive engine uses this data daily.
- Do NOT include conclusion headings. End naturally.
- HTML must be clean — no inline styles, no div wrappers, no class attributes.
- IDs must be s0, s1, s2... matching the section order exactly.

TONE EXAMPLES from existing Forma posts:
"Progressive overload is one of the most fundamental principles in endurance training. If you want to run faster or ride further, you need to challenge your body with gradually increasing stress. But the real question isn't whether overload works — it's <strong>how much stress the body can adapt to, and when</strong>."

"Traditional training plans assume that the body behaves predictably. A typical schedule might include intervals on Tuesday, a tempo session on Thursday, and a long run at the weekend. While this structure works for many athletes, it overlooks an important reality: <strong>human physiology fluctuates daily</strong>."

Match this tone exactly — direct, confident, specific, no fluff."""


def call_api(prompt: str, api_key: str) -> dict:
    """Call Anthropic API and return parsed JSON response."""
    import urllib.request

    payload = json.dumps({
        "model":      MODEL,
        "max_tokens": 8000,
        "messages":   [{"role": "user", "content": prompt}]
    }).encode()

    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        sys.exit(f"API error {e.code}: {body}")

    text = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            text += block["text"]

    # Strip accidental markdown fences
    text = re.sub(r"^```json\s*", "", text.strip())
    text = re.sub(r"\s*```$",     "", text.strip())

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  ✗ JSON parse error: {e}")
        print(f"  Raw response (first 800 chars): {text[:800]}")
        return {}


def build_filled_pillar_html(spec: dict, generated: dict, all_posts: list, font_css_placeholder: str = "") -> str:
    """
    Assemble the full pillar HTML with real generated content.
    Mirrors the structure of build_pillar_html() in forma_blog_build.py
    but injects actual section content instead of placeholders.
    """
    import re as _re

    slug      = spec["slug"]
    h1        = spec["h1"]
    cluster   = spec.get("cluster", "")
    sections  = spec.get("suggested_sections", [])
    tool_ctas = spec.get("tool_ctas", [])
    links_to  = spec.get("internal_links_to", [])

    # Content from API
    intro_html   = generated.get("intro_html", "")
    gen_sections = generated.get("sections", [])
    meta_desc    = generated.get("meta_description", f"Complete guide to {h1.lower().rstrip('?')}. Evidence-based answers for endurance athletes.")
    keywords     = generated.get("keywords", "")

    today     = date.today().isoformat()
    canonical = f"https://blog.formafit.co.uk/blog/{slug}"

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
    category = cat_map.get(cluster, "Training Science")

    # Schema
    faq_entries = [
        {
            "@type": "Question",
            "name": s,
            "acceptedAnswer": {
                "@type": "Answer",
                "text": next(
                    (re.sub(r"<[^>]+>", "", gs.get("html", ""))[:200]
                     for gs in gen_sections if gs.get("heading", "").strip() == s.strip()),
                    f"See the full answer in our guide to {h1.lower().rstrip('?')}."
                )
            }
        }
        for s in sections[:6]
    ]

    schema_article = {
        "@context": "https://schema.org", "@type": "Article",
        "headline": h1, "description": meta_desc,
        "author": {"@type": "Organization", "name": "AMTR Health Ltd", "url": "https://formafit.co.uk"},
        "publisher": {"@type": "Organization", "name": "Forma"},
        "datePublished": today, "dateModified": today,
        "url": canonical, "mainEntityOfPage": canonical,
        "keywords": keywords,
    }
    schema_faq = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": faq_entries
    }

    # TOC
    toc_li    = "".join(f'<li><a href="#s{i}">{s}</a></li>' for i, s in enumerate(sections))
    toc_block = (
        f'<div class="sidebar-card">'
        f'<div class="sidebar-card-title">In this article</div>'
        f'<ul class="toc-list">{toc_li}</ul></div>'
    ) if sections else ""

    # Section bodies — use generated content, fall back to placeholder
    gen_map = {gs.get("id", f"s{i}"): gs.get("html", "") for i, gs in enumerate(gen_sections)}
    sec_parts = []
    for i, s in enumerate(sections):
        sid      = f"s{i}"
        body_html = gen_map.get(sid, "")
        if not body_html:
            # Try matching by heading text
            body_html = next(
                (gs.get("html", "") for gs in gen_sections
                 if gs.get("heading", "").strip().lower() == s.strip().lower()),
                f"<p>This section covers {s.lower().rstrip('?')}. Forma uses this data to personalise your training plan.</p>"
            )
        sec_parts.append(f'<h2 id="{sid}">{s}</h2>\n{body_html}')
    sections_html = "\n\n".join(sec_parts)

    # Tool CTAs
    tool_cards = "".join(
        f'<div class="tool-cta-card">'
        f'<span style="font-size:1.5rem">&#x1F9EE;</span>'
        f'<div><strong>{t.title()}</strong>'
        f'<p style="margin:.2rem 0 0;font-size:.85rem;color:#666">Free calculator</p></div>'
        f'<a href="https://formafit.co.uk/tools/{_re.sub(r" +", "-", t.lower())}" '
        f'style="margin-left:auto;background:#1A6B4A;color:white;padding:.5rem 1rem;'
        f'border-radius:6px;font-size:.85rem;font-weight:600;text-decoration:none">'
        f'Try free &#x2192;</a></div>'
        for t in tool_ctas
    )
    tool_block = (
        f'<div style="margin:2.5rem 0"><h3>Free calculators for this topic</h3>{tool_cards}</div>'
    ) if tool_cards else ""

    # Related posts
    related_posts  = [p for p in all_posts if p.get("slug") in links_to][:4]
    related_cards  = "".join(
        f'<a class="related-card" href="/blog/{p["slug"]}.html">'
        f'<div class="tag">{p.get("category", "")}</div>'
        f'<h3>{p["title"]}</h3></a>'
        for p in related_posts
    )
    related_block = (
        f'<section class="related-section"><div class="related-inner">'
        f'<h2>Keep reading</h2><div class="related-grid">{related_cards}</div>'
        f'</div></section>'
    ) if related_cards else ""

    # Quick answer block
    qa_block = (
        f'<div style="background:#F0FFF8;border-left:4px solid #1A6B4A;'
        f'padding:1.25rem 1.5rem;border-radius:0 8px 8px 0;margin:1.5rem 0 2rem">'
        f'<div style="font-size:.7rem;font-weight:700;letter-spacing:.1em;'
        f'text-transform:uppercase;color:#1A6B4A;margin-bottom:.5rem">Quick Answer</div>'
        f'<p>{intro_html[:300].split("</p>")[0].replace("<p>", "").strip() if intro_html else h1.rstrip("?") + " — comprehensive guide below."}</p>'
        f'</div>'
    )

    s_art = json.dumps(schema_article, indent=2)
    s_faq = json.dumps(schema_faq, indent=2)

    # Read mode estimate
    total_words = len(re.sub(r"<[^>]+>", "", intro_html + sections_html).split())
    read_time   = max(8, round(total_words / 200))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{h1} — Complete Guide — Forma</title>
<meta name="description" content="{meta_desc}">
<link rel="canonical" href="{canonical}">
<meta name="robots" content="index,follow">
<meta name="keywords" content="{keywords}">
<meta property="og:type" content="article">
<meta property="og:url" content="{canonical}">
<meta property="og:title" content="{h1}">
<meta property="og:description" content="{meta_desc}">
<meta property="og:image" content="https://blog.formafit.co.uk/images/og-default.png">
<meta property="og:site_name" content="Forma">
<meta property="og:locale" content="en_GB">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{h1}">
<meta name="twitter:description" content="{meta_desc}">
<meta name="twitter:image" content="https://blog.formafit.co.uk/images/og-default.png">
<link rel="alternate" type="application/rss+xml" title="Forma Blog" href="https://blog.formafit.co.uk/feed.xml">
<script type="application/ld+json">{s_art}</script>
<script type="application/ld+json">{s_faq}</script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#0F1117;background:#fff;line-height:1.7}}
.pillar-badge{{display:inline-block;background:#1A6B4A;color:white;font-size:.65rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;padding:.25rem .6rem;border-radius:4px;margin-bottom:.75rem}}
.article-hero{{background:#0F1117;padding:4rem 2rem 3rem;text-align:center}}
.article-hero-inner{{max-width:760px;margin:0 auto}}
.article-hero h1{{font-size:2.2rem;font-weight:700;color:white;line-height:1.25;margin:.5rem 0 1rem}}
.cat-pill{{display:inline-block;background:rgba(255,255,255,0.1);color:rgba(255,255,255,0.7);font-size:.7rem;font-weight:600;letter-spacing:.1em;text-transform:uppercase;padding:.3rem .8rem;border-radius:20px;margin-bottom:.75rem}}
.article-meta{{display:flex;align-items:center;justify-content:center;gap:.75rem;font-size:.8rem;color:rgba(255,255,255,0.5);flex-wrap:wrap}}
.article-layout{{max-width:1100px;margin:0 auto;padding:3rem 2rem;display:grid;grid-template-columns:1fr 300px;gap:4rem;align-items:start}}
@media(max-width:768px){{.article-layout{{grid-template-columns:1fr;gap:2rem}}}}
.article-body h2{{font-size:1.4rem;font-weight:700;color:#0F1117;margin:2.5rem 0 1rem;line-height:1.3}}
.article-body p{{margin-bottom:1.1rem;color:#333;font-size:1rem}}
.article-body ul{{margin:.75rem 0 1.1rem 1.5rem}}
.article-body li{{margin-bottom:.4rem;color:#333}}
.article-body strong{{color:#0F1117;font-weight:600}}
.article-sidebar{{position:sticky;top:2rem}}
.sidebar-card{{background:#F8F9FA;border-radius:10px;padding:1.25rem;margin-bottom:1.25rem}}
.sidebar-card-title{{font-size:.7rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#888;margin-bottom:.75rem}}
.toc-list{{list-style:none;padding:0}}
.toc-list li{{margin-bottom:.4rem}}
.toc-list a{{font-size:.85rem;color:#1A6B4A;text-decoration:none;line-height:1.4;display:block}}
.toc-list a:hover{{text-decoration:underline}}
.cta-card{{background:#0F1117;border-radius:10px;padding:1.5rem;color:white}}
.cta-card h3{{font-size:1rem;font-weight:700;margin-bottom:.5rem}}
.cta-card p{{font-size:.85rem;color:rgba(255,255,255,0.65);margin-bottom:1rem}}
.cta-card a{{display:block;background:#1A6B4A;color:white;text-align:center;padding:.65rem 1rem;border-radius:7px;font-size:.85rem;font-weight:600;text-decoration:none}}
.cta-card a:hover{{background:#155A3C}}
.tool-cta-card{{display:flex;align-items:center;gap:1rem;background:#FAFAFA;border:1px solid #E5E7EB;border-radius:8px;padding:1rem 1.25rem;margin-bottom:.75rem}}
.related-section{{background:#F8F9FA;padding:3rem 2rem}}
.related-inner{{max-width:1100px;margin:0 auto}}
.related-inner h2{{font-size:1.3rem;font-weight:700;margin-bottom:1.5rem}}
.related-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:1rem}}
.related-card{{background:white;border-radius:10px;padding:1.25rem;text-decoration:none;border:1px solid #E5E7EB;transition:box-shadow .2s}}
.related-card:hover{{box-shadow:0 4px 16px rgba(0,0,0,0.08)}}
.related-card .tag{{font-size:.65rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#1A6B4A;margin-bottom:.5rem}}
.related-card h3{{font-size:.95rem;font-weight:600;color:#0F1117;line-height:1.4}}
nav{{background:#0F1117;padding:1rem 2rem;display:flex;align-items:center;justify-content:space-between}}
nav a.brand{{color:white;font-weight:700;font-size:1rem;text-decoration:none}}
nav a.nav-cta{{background:#1A6B4A;color:white;padding:.45rem 1rem;border-radius:6px;font-size:.8rem;font-weight:600;text-decoration:none}}
footer{{background:#0F1117;color:rgba(255,255,255,0.4);text-align:center;padding:2rem;font-size:.8rem}}
footer a{{color:rgba(255,255,255,0.4);text-decoration:none}}
</style>
</head>
<body>
<nav>
  <a class="brand" href="https://formafit.co.uk">Forma</a>
  <a class="nav-cta" href="https://formafit.co.uk/pricing">Start free trial</a>
</nav>
<header class="article-hero">
  <div class="article-hero-inner">
    <div class="pillar-badge">Complete Guide</div>
    <div class="cat-pill">{category}</div>
    <h1>{h1}</h1>
    <div class="article-meta">
      <span><strong>{read_time} MIN READ</strong></span>
      <span>·</span>
      <span>Updated {today}</span>
      <span>·</span>
      <span>Forma Training Intelligence</span>
    </div>
  </div>
</header>
<div class="article-layout">
  <article class="article-body">
    {qa_block}
    {intro_html}
    {sections_html}
    {tool_block}
  </article>
  <aside class="article-sidebar">
    {toc_block}
    <div class="cta-card">
      <h3>Train smarter from tomorrow</h3>
      <p>Forma adapts your plan every morning based on how your body actually recovers.</p>
      <a href="https://formafit.co.uk/pricing">Start 14-day free trial &#x2192;</a>
    </div>
  </aside>
</div>
{related_block}
<footer>
  <p>&copy; {date.today().year} AMTR Health Ltd &nbsp;·&nbsp;
  <a href="https://formafit.co.uk/privacy">Privacy</a> &nbsp;·&nbsp;
  <a href="https://formafit.co.uk/terms">Terms</a></p>
</footer>
<script>
document.querySelectorAll('.toc-list a').forEach(a => {{
  a.addEventListener('click', e => {{
    e.preventDefault();
    const t = document.getElementById(a.getAttribute('href').slice(1));
    if (t) t.scrollIntoView({{ behavior:'smooth', block:'start' }});
  }});
}});
</script>
</body>
</html>"""


def parse_args():
    parser = argparse.ArgumentParser(description="Forma Pillar Content Fill")
    parser.add_argument("--slug",    default=None, help="Fill a single pillar by slug fragment (e.g. 'zone-2')")
    parser.add_argument("--dry-run", action="store_true", help="Preview pillars without generating")
    parser.add_argument("--rebuild", action="store_true", help="Run blog builder after filling")
    parser.add_argument("--api-key", default=os.environ.get("ANTHROPIC_API_KEY", ""), help="Anthropic API key")
    return parser.parse_args()


def main():
    args = parse_args()

    print("=" * 60)
    print("  Forma Pillar Content Fill")
    print("=" * 60)

    specs     = load_specs()
    manifest  = load_manifest()
    all_posts = [p for p in manifest if p.get("status") == "published"]

    # Filter by slug if requested
    if args.slug:
        specs = [s for s in specs if args.slug.lower() in s.get("slug", "").lower()]
        if not specs:
            sys.exit(f"No pillar found matching slug fragment '{args.slug}'")

    print(f"\n  {len(specs)} pillar(s) to fill:")
    for s in specs:
        section_count = len(s.get("suggested_sections", []))
        print(f"  · {s['slug']}  ({section_count} sections)")

    if args.dry_run:
        print("\n  Dry run — no content generated")
        return

    if not args.api_key:
        sys.exit("\nERROR: No API key. Set ANTHROPIC_API_KEY or pass --api-key")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filled = []

    for i, spec in enumerate(specs):
        slug     = spec["slug"]
        h1       = spec["h1"]
        sections = spec.get("suggested_sections", [])

        print(f"\n  [{i+1}/{len(specs)}] {h1}")
        print(f"         cluster: {spec.get('cluster')} | sections: {len(sections)}")

        prompt    = build_prompt(spec)
        generated = call_api(prompt, args.api_key)

        if not generated or not generated.get("sections"):
            print(f"  ✗ Generation failed — skipping")
            continue

        gen_sections = generated.get("sections", [])
        total_words  = sum(
            len(re.sub(r"<[^>]+>", "", gs.get("html", "")).split())
            for gs in gen_sections
        )
        intro_words = len(re.sub(r"<[^>]+>", "", generated.get("intro_html", "")).split())

        print(f"  ✓ Generated: {len(gen_sections)} sections, ~{total_words + intro_words} words")

        # Build and write the filled HTML
        html    = build_filled_pillar_html(spec, generated, all_posts)
        outfile = OUTPUT_DIR / f"{slug}.html"
        outfile.write_text(html, encoding="utf-8")

        print(f"    → output/blog/{slug}.html  ({len(html)//1024} KB)")
        filled.append(slug)

        # Rate limit between pillars
        if i < len(specs) - 1:
            print("    (waiting 3s before next pillar...)")
            time.sleep(3)

    if not filled:
        print("\n  No pillars filled")
        return

    # Optionally trigger the standard blog builder for consistency
    if args.rebuild:
        print(f"\n  Rebuilding full blog HTML...")
        result = subprocess.run(
            [sys.executable, str(BLOG_BUILDER)],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print("  ✓ Blog rebuilt successfully")
        else:
            print(f"  ✗ Blog build error:\n{result.stderr[:400]}")

    print(f"\n{'='*60}")
    print(f"  Done — {len(filled)} pillar(s) filled with real content")
    for slug in filled:
        print(f"   + output/blog/{slug}.html")
    print(f"{'='*60}")
    print(f"\n  Next steps:")
    print(f"  1. Review a page in your browser: open output/blog/{filled[0]}.html")
    print(f"  2. If quality is good: git add output/ && git commit -m 'content: fill pillar pages' && git push")
    print(f"  3. GitHub Actions deploys to blog.formafit.co.uk automatically")


if __name__ == "__main__":
    main()
