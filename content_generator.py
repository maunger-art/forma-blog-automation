#!/usr/bin/env python3
"""
Forma Content Generator
=======================
Reads top unassigned questions from shared/queue.json, generates full blog
post content via the Anthropic API, writes to posts_manifest.json, and marks
queue entries as assigned.

Usage:
    python3 content_generator.py              # generate up to --batch (default 4)
    python3 content_generator.py --batch 8    # generate 8 posts
    python3 content_generator.py --dry-run    # preview without writing
    python3 content_generator.py --rebuild    # rebuild HTML after generating

Schedule: run Mon/Wed/Fri/Sat to achieve 4 posts/week cadence
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT      = Path(__file__).resolve().parent
QUEUE_PATH     = REPO_ROOT / "shared" / "queue.json"
MANIFEST_PATH  = REPO_ROOT / "posts_manifest.json"
TAXONOMY_PATH  = REPO_ROOT / "shared" / "taxonomy.json"
BLOG_BUILDER   = REPO_ROOT / "forma_blog_build.py"

# ── Anthropic API ─────────────────────────────────────────────────────────────
API_URL = "https://api.anthropic.com/v1/messages"
MODEL   = "claude-sonnet-4-20250514"

# ── Cluster → category mapping ────────────────────────────────────────────────
CLUSTER_TO_CATEGORY = {
    "zone-2-training":   "Training Science",
    "hrv-readiness":     "Wearables",
    "training-load":     "Training Science",
    "garmin-wearable":   "Wearables",
    "marathon-training": "Running",
    "cycling-endurance": "Cycling",
    "recovery-sleep":    "Recovery",
    "injury-prevention": "Recovery",
}

# ── Publishing schedule ───────────────────────────────────────────────────────
PUB_DAYS = {0: "Monday", 2: "Wednesday", 4: "Friday", 5: "Saturday"}


def slugify(text: str) -> str:
    text = text.lower().strip().rstrip("?")
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text)[:80].strip("-")


def next_pub_dates(n: int) -> list[str]:
    """Return the next n publishing dates (Mon/Wed/Fri/Sat)."""
    dates = []
    d = date.today()
    while len(dates) < n:
        if d.weekday() in PUB_DAYS:
            dates.append(d.isoformat())
        d += timedelta(days=1)
    return dates


def load_queue() -> list[dict]:
    if not QUEUE_PATH.exists():
        sys.exit(f"ERROR: {QUEUE_PATH} not found — run cluster_builder first")
    return json.loads(QUEUE_PATH.read_text())


def load_manifest() -> list[dict]:
    if not MANIFEST_PATH.exists():
        return []
    return json.loads(MANIFEST_PATH.read_text())


def existing_slugs(manifest: list[dict]) -> set[str]:
    return {p["slug"] for p in manifest}


def pick_questions(queue: list[dict], manifest: list[dict], batch: int) -> list[dict]:
    """
    Pick top unassigned questions for content generation.
    Prefers questions that are already in manifest as drafts (fill them first).
    Falls back to questions not yet in manifest.
    Skips questions already published.
    """
    # Build lookup: slug -> manifest entry
    slug_to_entry = {p["slug"]: p for p in manifest}

    # Published slugs — never regenerate
    published_slugs = {p["slug"] for p in manifest if p.get("status") == "published"}

    candidates = []
    for q in queue:
        if q.get("status") not in ("unassigned", None):
            continue
        slug = slugify(q.get("suggested_title") or q.get("question_text", ""))
        if slug in published_slugs:
            continue  # already published — skip
        # Include whether draft or not yet in manifest
        candidates.append(q)

    candidates.sort(key=lambda x: x.get("composite_score", 0), reverse=True)
    return candidates[:batch]


def build_prompt(question: dict) -> str:
    q_text  = question.get("question_text", "")
    title   = question.get("suggested_title") or q_text
    cluster = question.get("cluster", "")
    c_type  = question.get("content_type", "article")

    cluster_context = {
        "zone-2-training":   "Zone 2 training, aerobic base building, easy running pace, low-intensity endurance work",
        "hrv-readiness":     "Heart rate variability, training readiness, Garmin/Whoop/Oura metrics, recovery status",
        "training-load":     "Training load management, ATL/CTL/ACWR, acute and chronic training load, overtraining prevention",
        "garmin-wearable":   "Garmin wearables, sleep tracking, stress scores, training status metrics, GPS watches",
        "marathon-training": "Marathon training, race preparation, long runs, taper, race-day strategy",
        "cycling-endurance": "Cycling endurance, FTP, training zones, power-based training, long rides",
        "recovery-sleep":    "Recovery runs, rest days, sleep quality, returning from illness, active recovery",
        "injury-prevention": "Running injury prevention, biomechanics, strength training for runners, load management",
    }.get(cluster, "endurance training for runners and cyclists")

    return f"""You are writing a blog post for Forma, an adaptive endurance training app for runners and cyclists.

Forma's voice: authoritative but approachable, science-backed without being academic, written for serious amateur athletes (not beginners, not elite professionals). No fluff, no motivational filler. Every paragraph earns its place.

TOPIC CONTEXT: {cluster_context}

Write a complete blog post answering this question: "{q_text}"
Suggested title: "{title}"

REQUIRED OUTPUT FORMAT — respond with a single JSON object only, no markdown fences, no preamble:

{{
  "title": "Final SEO-optimised title (50-60 chars ideal)",
  "meta_description": "Compelling meta description 140-155 chars",
  "keywords": "comma-separated keyword phrases (6-8 terms)",
  "read_time": <integer minutes, typically 5-8>,
  "toc_items": [
    {{"id": "kebab-case-id", "text": "Section heading text"}},
    ...4-6 items total
  ],
  "body_html": "Full HTML body content — see requirements below"
}}

BODY HTML REQUIREMENTS:
- 900-1400 words
- Opening paragraph hooks immediately — no throat-clearing, no "In this article we will..."
- Use <strong> for key concepts and important terms
- Use <h2 id="matching-toc-id"> for section headings — IDs must match toc_items exactly
- Use <ul>/<li> for lists where natural (max 1-2 lists per post)
- Use <p> tags for all paragraphs
- Include at least one specific data point, study reference, or metric (can be approximate)
- End with a forward-looking paragraph that naturally references adaptive training and Forma
- Do NOT include a conclusion heading — just end naturally
- Do NOT mention competitor apps by name
- HTML must be clean and valid — no inline styles, no div wrappers

TONE EXAMPLES from existing Forma posts:
"Progressive overload is one of the most fundamental principles in endurance training. If you want to run faster or ride further, you need to challenge your body with gradually increasing stress. But the real question isn't whether overload works — it's <strong>how much stress the body can adapt to, and when</strong>."

"Traditional training plans assume that the body behaves predictably. A typical schedule might include intervals on Tuesday, a tempo session on Thursday, and a long run at the weekend. While this structure works for many athletes, it overlooks an important reality: <strong>human physiology fluctuates daily</strong>."

Match this tone exactly — direct, confident, specific."""


def call_api(prompt: str, api_key: str) -> dict:
    """Call Anthropic API and return parsed JSON response."""
    import urllib.request

    payload = json.dumps({
        "model": MODEL,
        "max_tokens": 4000,
        "messages": [{"role": "user", "content": prompt}]
    }).encode()

    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        sys.exit(f"API error {e.code}: {body}")

    text = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            text += block["text"]

    # Strip any accidental markdown fences
    text = re.sub(r"^```json\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  ✗ JSON parse error: {e}")
        print(f"  Raw response (first 500 chars): {text[:500]}")
        return {}


def build_manifest_entry(question: dict, generated: dict, pub_date: str) -> dict:
    cluster  = question.get("cluster", "")
    category = CLUSTER_TO_CATEGORY.get(cluster, "Training Science")
    title    = generated.get("title") or question.get("suggested_title") or question.get("question_text", "")
    slug     = slugify(title)

    return {
        "slug":             slug,
        "title":            title,
        "date":             pub_date,
        "category":         category,
        "meta_description": generated.get("meta_description", ""),
        "keywords":         generated.get("keywords", ""),
        "read_time":        generated.get("read_time", 5),
        "toc_items":        generated.get("toc_items", []),
        "body_html":        generated.get("body_html", ""),
        "status":           "published",
        "_queue_id":        question.get("question_id", ""),
        "_cluster":         cluster,
        "_composite_score": question.get("composite_score", 0),
    }


def mark_assigned(queue: list[dict], question_ids: list[str]) -> list[dict]:
    id_set = set(question_ids)
    for q in queue:
        if q.get("question_id") in id_set:
            q["status"] = "assigned"
            q["assigned_to"] = "content_generator"
            q["due_date"] = date.today().isoformat()
    return queue


def parse_args():
    parser = argparse.ArgumentParser(description="Forma AI Content Generator")
    parser.add_argument("--batch",    type=int, default=4, help="Number of posts to generate (default: 4)")
    parser.add_argument("--dry-run",  action="store_true", help="Preview questions without generating")
    parser.add_argument("--rebuild",  action="store_true", help="Run blog builder after generating")
    parser.add_argument("--api-key",  default=os.environ.get("ANTHROPIC_API_KEY", ""), help="Anthropic API key")
    return parser.parse_args()


def main():
    args = parse_args()

    print("=" * 60)
    print("  Forma Content Generator")
    print("=" * 60)

    queue    = load_queue()
    manifest = load_manifest()
    selected = pick_questions(queue, manifest, args.batch)

    if not selected:
        print("\n  No unassigned questions available — queue may be empty or all assigned")
        return

    pub_dates = next_pub_dates(len(selected))

    print(f"\n  {len(selected)} questions selected for generation:")
    for i, (q, d) in enumerate(zip(selected, pub_dates)):
        print(f"  {i+1}. [{d}] ({q['composite_score']:.1f}) {q.get('suggested_title') or q.get('question_text','')}")

    if args.dry_run:
        print("\n  Dry run — no content generated")
        return

    if not args.api_key:
        sys.exit("\nERROR: No API key found. Set ANTHROPIC_API_KEY env var or pass --api-key")

    print(f"\n  Generating content via Claude API...")
    generated_entries = []
    assigned_ids      = []

    for i, (question, pub_date) in enumerate(zip(selected, pub_dates)):
        q_title = question.get("suggested_title") or question.get("question_text", "")
        print(f"\n  [{i+1}/{len(selected)}] {q_title}")
        print(f"         cluster: {question.get('cluster')} | score: {question.get('composite_score'):.1f} | date: {pub_date}")

        prompt    = build_prompt(question)
        generated = call_api(prompt, args.api_key)

        if not generated or not generated.get("body_html"):
            print(f"  ✗ Generation failed — skipping")
            continue

        entry = build_manifest_entry(question, generated, pub_date)
        generated_entries.append(entry)
        assigned_ids.append(question.get("question_id", ""))

        word_count = len(re.sub(r"<[^>]+>", "", generated.get("body_html", "")).split())
        print(f"  ✓ Generated: \"{entry['title']}\"")
        print(f"    slug: {entry['slug']} | words: {word_count} | read_time: {entry['read_time']}min")

        # Rate limit — avoid hammering API
        if i < len(selected) - 1:
            time.sleep(2)

    if not generated_entries:
        print("\n  No entries generated")
        return

    # ── Write to manifest ────────────────────────────────────────────────────
    # Replace existing drafts with generated content; add new entries
    new_slugs = {e["slug"] for e in generated_entries}
    manifest  = [p for p in manifest if p["slug"] not in new_slugs]
    manifest.extend(generated_entries)

    # Sort by date descending
    manifest.sort(key=lambda x: x.get("date", ""), reverse=True)

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"\n  ✓ {len(generated_entries)} entries written to posts_manifest.json")

    # ── Update queue ─────────────────────────────────────────────────────────
    updated_queue = mark_assigned(queue, assigned_ids)
    QUEUE_PATH.write_text(json.dumps(updated_queue, indent=2, ensure_ascii=False))
    print(f"  ✓ {len(assigned_ids)} queue entries marked as assigned")

    # ── Rebuild HTML ─────────────────────────────────────────────────────────
    if args.rebuild:
        print(f"\n  Rebuilding HTML...")
        result = subprocess.run(
            [sys.executable, str(BLOG_BUILDER)],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print("  ✓ Blog rebuilt successfully")
        else:
            print(f"  ✗ Blog build failed:\n{result.stderr[:500]}")

    print(f"\n{'='*60}")
    print(f"  Done — {len(generated_entries)} posts generated")
    for e in generated_entries:
        print(f"   + {e['date']}  {e['title']}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
