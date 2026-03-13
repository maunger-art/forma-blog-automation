#!/usr/bin/env python3
"""
Forma Backlink Engine
=====================
Two modes:

1. POST OUTREACH (--mode outreach)
   After a post or pillar page publishes, find pages that should link to it
   and draft outreach emails. Run manually or as a post-publish step.

2. RESOURCE PAGE FINDER (--mode resources)
   Weekly scan for resource pages across all topic clusters that Forma
   should be listed on. Run alongside the Monday AQE cron.

Outputs:
   output/outreach/{slug}/opportunities.json  — scored link targets
   output/outreach/{slug}/drafts.txt          — ready-to-send email drafts
   output/outreach/resource_pages.json        — weekly resource page shortlist

Usage:
    python3 backlink_engine.py --mode outreach --slug why-is-my-garmin-training-readiness-always-low
    python3 backlink_engine.py --mode outreach --all-recent    # last 7 days of posts
    python3 backlink_engine.py --mode resources                # weekly resource scan
    python3 backlink_engine.py --dry-run                       # preview without API calls

Requirements:
    ANTHROPIC_API_KEY  — for draft generation
    SERPAPI_KEY        — for search results (already used by AQE pipeline)
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
REPO_ROOT     = Path(__file__).resolve().parent
MANIFEST_PATH = REPO_ROOT / "posts_manifest.json"
SPECS_PATH    = REPO_ROOT / "shared" / "pillar_page_specs.json"
OUTREACH_DIR  = REPO_ROOT / "output" / "outreach"

# ── APIs ───────────────────────────────────────────────────────────────────────
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
SERPAPI_URL   = "https://serpapi.com/search"
MODEL         = "claude-sonnet-4-20250514"

# ── Site config ────────────────────────────────────────────────────────────────
FORMA_DOMAIN  = "formafit.co.uk"
BLOG_DOMAIN   = "blog.formafit.co.uk"
CONTACT_EMAIL = "formafit816@gmail.com"

# ── Cluster → topic keywords for resource search ───────────────────────────────
CLUSTER_RESOURCE_QUERIES = {
    "zone-2-training":   [
        "zone 2 heart rate training guide running coach blog",
        "aerobic base training calculator runners coaching blog",
        "zone 2 running pace calculator endurance coaching",
    ],
    "hrv-readiness":     [
        "HRV training guide endurance athletes coaching blog",
        "garmin training readiness score explained running coach",
        "HRV monitoring runners guide coaching blog",
    ],
    "training-load":     [
        "training load management runners guide coaching blog",
        "acute chronic training load ratio running injury blog",
        "CTL ATL TSB explained endurance training blog",
    ],
    "garmin-wearable":   [
        "garmin running metrics explained coaching blog guide",
        "garmin body battery training readiness guide athletes",
        "garmin watch training features runners coaching",
    ],
    "marathon-training": [
        "marathon training plan guide coaching blog recommended",
        "marathon pace calculator training zones coaching guide",
        "marathon preparation tools running coaching blog",
    ],
    "cycling-endurance": [
        "cycling FTP training zones guide coaching blog",
        "cycling endurance training plan calculator coaching",
        "polarised training cycling guide coaching blog",
    ],
    "recovery-sleep":    [
        "athlete sleep recovery guide running coaching blog",
        "recovery run pace guide endurance athletes coaching",
        "sleep quality athletes performance guide coaching blog",
    ],
    "injury-prevention": [
        "running injury prevention guide coaching blog strength",
        "running load management injury prevention coaching",
        "strength training runners guide coaching blog",
    ],
}

# ── Page type signals — pages likely to link out ───────────────────────────────
LINKABLE_PAGE_SIGNALS = [
    "resources", "tools", "guide", "best", "list", "roundup",
    "recommended", "links", "collection", "directory", "wiki",
    "for athletes", "for runners", "for cyclists", "training guide",
]

# ── Domains to skip (Forma's own, major platforms unlikely to link) ────────────
SKIP_DOMAINS = {
    "formafit.co.uk", "blog.formafit.co.uk",
    "google.com", "youtube.com", "facebook.com", "twitter.com",
    "instagram.com", "tiktok.com", "pinterest.com", "linkedin.com",
    "amazon.com",
    "wikipedia.org", "strava.com", "garmin.com", "whoop.com",
}


def slugify(text: str) -> str:
    text = text.lower().strip().rstrip("?")
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text)[:80].strip("-")


def load_manifest() -> list[dict]:
    if not MANIFEST_PATH.exists():
        return []
    return json.loads(MANIFEST_PATH.read_text())


def load_specs() -> list[dict]:
    if not SPECS_PATH.exists():
        return []
    return json.loads(SPECS_PATH.read_text())


def get_domain(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return ""


def score_opportunity(result: dict) -> float:
    """
    Score a SERP result for backlink opportunity quality.
    Returns 0-10. Higher = better opportunity.
    """
    score = 0.0
    url   = result.get("link", "").lower()
    title = result.get("title", "").lower()
    snippet = result.get("snippet", "").lower()
    combined = title + " " + snippet + " " + url

    # Page type signals — resource/tool/guide pages are ideal
    for signal in LINKABLE_PAGE_SIGNALS:
        if signal in combined:
            score += 1.0

    # Coaching / education domains get a bonus
    if any(x in url for x in [".edu", "coaching", "coach", "training", "run", "cycl", "triathlon", "endur"]):
        score += 1.5

    # Blog posts on relevant sites
    if "/blog/" in url or "/articles/" in url or "/guides/" in url:
        score += 1.0

    # Already mentions competitors — warmer prospect
    if any(x in combined for x in ["training peaks", "trainingpeaks", "whoop", "oura", "garmin", "strava"]):
        score += 0.5

    # Penalise low-value page types
    if any(x in url for x in ["shop", "product", "buy", "store", "ecommerce"]):
        score -= 2.0
    if any(x in combined for x in ["advertisement", "sponsored", "affiliate"]):
        score -= 1.5

    return max(0.0, min(10.0, score))


def serp_search(query: str, serpapi_key: str, num: int = 10) -> list[dict]:
    """Call SerpAPI and return organic results."""
    params = {
        "q":       query,
        "api_key": serpapi_key,
        "num":     num,
        "gl":      "gb",
        "hl":      "en",
    }
    url = SERPAPI_URL + "?" + urllib.parse.urlencode(params)

    try:
        req  = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return data.get("organic_results", [])
    except Exception as e:
        print(f"  ⚠ SerpAPI error for '{query}': {e}")
        return []


def draft_outreach(post: dict, opportunity: dict, api_key: str) -> str:
    """
    Use Claude to draft a short, specific outreach email.
    Returns the draft as plain text.
    """
    post_title = post.get("title", "")
    post_url   = f"https://{BLOG_DOMAIN}/blog/{post.get('slug', '')}"
    opp_title  = opportunity.get("title", "")
    opp_url    = opportunity.get("url", "")
    opp_domain = get_domain(opp_url)
    reason     = opportunity.get("link_reason", "")

    prompt = f"""Write a short, specific outreach email asking for a link to a Forma blog post.

THE POST WE WANT LINKED:
Title: {post_title}
URL: {post_url}

THE TARGET PAGE:
Title: {opp_title}
URL: {opp_url}
Why it's a good fit: {reason}

FORMA CONTEXT:
Forma is an adaptive endurance training app for runners and cyclists that personalises training plans daily based on readiness, HRV, and training load data.

REQUIREMENTS:
- Under 120 words total
- Subject line on the first line, then a blank line, then the email body
- Reference the specific page or section of theirs that would naturally link to the Forma post
- Explain in one sentence what the Forma post covers and why their readers would find it useful
- No "I love your content" or generic flattery
- No "I came across your website" opener
- Direct, professional, calm tone
- End with: "Best, [Name]" — leave [Name] as a placeholder
- Do not include a postscript or any explanation of what you wrote

Respond with the email text only — subject line first, then body."""

    payload = json.dumps({
        "model":      MODEL,
        "max_tokens": 400,
        "messages":   [{"role": "user", "content": prompt}]
    }).encode()

    req = urllib.request.Request(
        ANTHROPIC_URL,
        data=payload,
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block["text"]
        return text.strip()
    except Exception as e:
        return f"[Draft generation failed: {e}]"


def run_outreach(posts: list[dict], args) -> None:
    """Find link opportunities and draft outreach for given posts."""
    serpapi_key = os.environ.get("SERPAPI_KEY", args.serpapi_key)
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", args.api_key)

    if not serpapi_key:
        sys.exit("ERROR: SERPAPI_KEY not set. Set env var or pass --serpapi-key")
    if not anthropic_key and not args.dry_run:
        sys.exit("ERROR: ANTHROPIC_API_KEY not set. Set env var or pass --api-key")

    OUTREACH_DIR.mkdir(parents=True, exist_ok=True)

    for post in posts:
        slug     = post.get("slug", "")
        title    = post.get("title", "")
        category = post.get("category", "")
        keywords = post.get("keywords", "")

        print(f"\n  Processing: {title}")
        print(f"  slug: {slug}")

        # Build search queries from post title and keywords
        kw_list = [k.strip() for k in keywords.split(",")][:3] if keywords else []
        queries = [
            f"resources {title.lower()} site:*.com",
            f"guide {' '.join(kw_list[:2])} endurance athletes",
            f"tools {category.lower()} training resources",
        ]

        all_results = []
        for q in queries:
            if args.dry_run:
                print(f"    [dry-run] Would search: {q}")
                continue
            results = serp_search(q, serpapi_key, num=8)
            all_results.extend(results)
            time.sleep(1)  # Rate limit

        if args.dry_run:
            continue

        # Deduplicate by URL
        seen_urls = set()
        unique_results = []
        for r in all_results:
            url = r.get("link", "")
            domain = get_domain(url)
            if url and url not in seen_urls and domain not in SKIP_DOMAINS:
                seen_urls.add(url)
                unique_results.append(r)

        # Score and filter
        opportunities = []
        for r in unique_results:
            score = score_opportunity(r)
            if score >= 1.5:
                opportunities.append({
                    "url":         r.get("link", ""),
                    "title":       r.get("title", ""),
                    "snippet":     r.get("snippet", ""),
                    "domain":      get_domain(r.get("link", "")),
                    "score":       round(score, 1),
                    "link_reason": f"Page covers {category.lower()} training — {r.get('snippet', '')[:100]}",
                })

        opportunities.sort(key=lambda x: x["score"], reverse=True)
        top_opportunities = opportunities[:8]

        print(f"  Found {len(top_opportunities)} scored opportunities (from {len(unique_results)} results)")

        # Save opportunities
        post_outreach_dir = OUTREACH_DIR / slug
        post_outreach_dir.mkdir(parents=True, exist_ok=True)

        (post_outreach_dir / "opportunities.json").write_text(
            json.dumps({
                "post_slug":     slug,
                "post_title":    title,
                "post_url":      f"https://{BLOG_DOMAIN}/blog/{slug}",
                "generated_at":  date.today().isoformat(),
                "opportunities": top_opportunities,
            }, indent=2),
            encoding="utf-8"
        )

        if not top_opportunities:
            print(f"  No qualifying opportunities found")
            continue

        # Generate outreach drafts for top 5
        drafts = []
        for j, opp in enumerate(top_opportunities[:5]):
            print(f"  Drafting email {j+1}/5: {opp['domain']}")
            draft = draft_outreach(post, opp, anthropic_key)
            drafts.append({
                "target_url":   opp["url"],
                "target_title": opp["title"],
                "domain":       opp["domain"],
                "score":        opp["score"],
                "draft":        draft,
            })
            time.sleep(1.5)

        # Write drafts as a readable text file
        drafts_text = f"OUTREACH DRAFTS — {title}\n"
        drafts_text += f"Post URL: https://{BLOG_DOMAIN}/blog/{slug}\n"
        drafts_text += f"Generated: {date.today().isoformat()}\n"
        drafts_text += "=" * 60 + "\n\n"

        for j, d in enumerate(drafts):
            drafts_text += f"DRAFT {j+1} — {d['domain']} (score: {d['score']})\n"
            drafts_text += f"Target: {d['target_url']}\n"
            drafts_text += "-" * 40 + "\n"
            drafts_text += d["draft"] + "\n\n"
            drafts_text += "=" * 60 + "\n\n"

        (post_outreach_dir / "drafts.txt").write_text(drafts_text, encoding="utf-8")
        print(f"  ✓ {len(drafts)} drafts saved to output/outreach/{slug}/drafts.txt")


def run_resource_finder(args) -> None:
    """Weekly scan for resource pages Forma should be listed on."""
    serpapi_key = os.environ.get("SERPAPI_KEY", args.serpapi_key)

    if not serpapi_key:
        sys.exit("ERROR: SERPAPI_KEY not set")

    OUTREACH_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n  Scanning {len(CLUSTER_RESOURCE_QUERIES)} topic clusters for resource pages...")

    all_opportunities = []

    for cluster, queries in CLUSTER_RESOURCE_QUERIES.items():
        print(f"\n  Cluster: {cluster}")
        cluster_results = []

        for q in queries:
            if args.dry_run:
                print(f"    [dry-run] Would search: {q}")
                continue
            results = serp_search(q, serpapi_key, num=8)
            cluster_results.extend(results)
            time.sleep(1.2)

        if args.dry_run:
            continue

        # Deduplicate
        seen = set()
        unique = []
        for r in cluster_results:
            url = r.get("link", "")
            domain = get_domain(url)
            if url and url not in seen and domain not in SKIP_DOMAINS:
                seen.add(url)
                unique.append(r)

        # Score and filter for resource pages specifically
        for r in unique:
            score = score_opportunity(r)
            url   = r.get("link", "").lower()
            title = r.get("title", "").lower()

            # Boost for explicit resource/list pages
            is_resource_page = any(
                s in url or s in title
                for s in ["resource", "tool", "list", "best", "top", "guide", "directory"]
            )
            if is_resource_page:
                score += 2.0

            if score >= 1.5:
                all_opportunities.append({
                    "cluster":       cluster,
                    "url":           r.get("link", ""),
                    "title":         r.get("title", ""),
                    "snippet":       r.get("snippet", ""),
                    "domain":        get_domain(r.get("link", "")),
                    "score":         round(score, 1),
                    "is_resource":   is_resource_page,
                    "action":        "Request listing" if is_resource_page else "Request link",
                    "suggested_page": f"https://{BLOG_DOMAIN}/tools/" if "calculator" in r.get("snippet", "").lower() else f"https://{BLOG_DOMAIN}/blog/",
                })

    if args.dry_run:
        print(f"\n  [dry-run] Resource finder complete — no API calls made")
        return

    # Sort by score, deduplicate by domain
    all_opportunities.sort(key=lambda x: x["score"], reverse=True)
    seen_domains = set()
    deduped = []
    for opp in all_opportunities:
        if opp["domain"] not in seen_domains:
            seen_domains.add(opp["domain"])
            deduped.append(opp)

    output = {
        "generated_at":   date.today().isoformat(),
        "total_found":    len(deduped),
        "opportunities":  deduped[:30],  # Top 30
    }

    outpath = OUTREACH_DIR / "resource_pages.json"
    outpath.write_text(json.dumps(output, indent=2), encoding="utf-8")

    # Also write a human-readable summary
    summary = f"RESOURCE PAGE OPPORTUNITIES — {date.today().isoformat()}\n"
    summary += f"Total found: {len(deduped)}\n"
    summary += "=" * 60 + "\n\n"

    for opp in deduped[:20]:
        summary += f"[{opp['score']:.1f}] {opp['domain']}\n"
        summary += f"Cluster:  {opp['cluster']}\n"
        summary += f"Page:     {opp['url']}\n"
        summary += f"Title:    {opp['title']}\n"
        summary += f"Action:   {opp['action']}\n"
        summary += f"Send to:  {opp['suggested_page']}\n"
        summary += "-" * 40 + "\n\n"

    (OUTREACH_DIR / "resource_pages_summary.txt").write_text(summary, encoding="utf-8")

    print(f"\n  ✓ {len(deduped)} resource page opportunities found")
    print(f"  → output/outreach/resource_pages.json")
    print(f"  → output/outreach/resource_pages_summary.txt")
    print(f"\n  Top 5 opportunities:")
    for opp in deduped[:5]:
        print(f"  [{opp['score']:.1f}] {opp['domain']} — {opp['title'][:60]}")


def parse_args():
    parser = argparse.ArgumentParser(description="Forma Backlink Engine")
    parser.add_argument("--mode",        choices=["outreach", "resources"], default="resources",
                        help="outreach: find links for specific posts | resources: weekly resource page scan")
    parser.add_argument("--slug",        default=None,
                        help="[outreach mode] Specific post slug to find links for")
    parser.add_argument("--all-recent",  action="store_true",
                        help="[outreach mode] Process all posts published in last 7 days")
    parser.add_argument("--dry-run",     action="store_true",
                        help="Preview searches without making API calls")
    parser.add_argument("--api-key",     default=os.environ.get("ANTHROPIC_API_KEY", ""),
                        help="Anthropic API key (for draft generation)")
    parser.add_argument("--serpapi-key", default=os.environ.get("SERPAPI_KEY", ""),
                        help="SerpAPI key (for search results)")
    return parser.parse_args()


def main():
    args = parse_args()

    print("=" * 60)
    print(f"  Forma Backlink Engine — mode: {args.mode}")
    print("=" * 60)

    if args.mode == "resources":
        run_resource_finder(args)

    elif args.mode == "outreach":
        manifest = load_manifest()
        published = [p for p in manifest if p.get("status") == "published"]

        if args.slug:
            posts = [p for p in published if args.slug.lower() in p.get("slug", "").lower()]
            if not posts:
                sys.exit(f"No published post found matching slug '{args.slug}'")

        elif args.all_recent:
            cutoff = (date.today() - timedelta(days=7)).isoformat()
            posts  = [p for p in published if p.get("date", "") >= cutoff]
            if not posts:
                print("  No posts published in the last 7 days")
                return

        else:
            # Default: most recent post
            published.sort(key=lambda x: x.get("date", ""), reverse=True)
            posts = published[:1]

        print(f"\n  Posts to process: {len(posts)}")
        for p in posts:
            print(f"  · {p.get('date', '')}  {p.get('title', '')}")

        run_outreach(posts, args)

    print(f"\n{'='*60}")
    print("  Done")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
