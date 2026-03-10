#!/usr/bin/env python3
"""
generate_topic_queue.py
=======================
Refills blog_topic_queue.txt with fresh SEO-friendly endurance training topics.

Strategy (in order):
  1. If queue already has >= MIN_QUEUE_SIZE unused topics → exit immediately (no cost)
  2. Build a deduplicated candidate list from a large deterministic seed bank,
     combining topic buckets × question frames via combinatorial expansion
  3. Strip any candidates already covered by existing posts or queue entries
     (fuzzy keyword match — not just exact string match)
  4. If ANTHROPIC_API_KEY is set, optionally ask the API to rewrite/improve
     the top N raw candidates into polished long-tail SEO titles (single call)
  5. Append new topics to blog_topic_queue.txt (one per line)
  6. Print a clear summary log

Exit codes:
  0 — topics added (or queue already full, no-op)
  1 — fatal error
"""

import json
import os
import re
import sys
from pathlib import Path

QUEUE_FILE    = Path("blog_topic_queue.txt")
POSTS_FILE    = Path("forma_blog_posts.md")
MANIFEST_FILE = Path("posts_manifest.json")

MIN_QUEUE_SIZE = 10   # Don't do anything if queue already has this many topics
TARGET_ADD     = 15   # How many new topics to append when we do run
MAX_AI_IMPROVE = 20   # Max candidates sent to AI for polishing (keeps cost low)


# ══════════════════════════════════════════════════════════════════════════════
# 1. SEED BANK
#    Topic buckets × question frames → combinatorial expansion.
#    All deterministic. No network calls.
# ══════════════════════════════════════════════════════════════════════════════

# Core subjects Forma covers
SUBJECTS = [
    # HRV
    ("HRV",                         "hrv"),
    ("heart rate variability",       "hrv"),
    ("HRV score",                    "hrv"),
    ("morning HRV",                  "hrv"),
    ("HRV trends",                   "hrv"),
    # Readiness
    ("readiness score",              "readiness"),
    ("training readiness",           "readiness"),
    ("daily readiness",              "readiness"),
    ("Garmin readiness score",       "readiness"),
    # Recovery
    ("recovery",                     "recovery"),
    ("sleep and recovery",           "recovery"),
    ("active recovery",              "recovery"),
    ("recovery run",                 "recovery"),
    ("recovery week",                "recovery"),
    ("post-race recovery",           "recovery"),
    # Training load
    ("training load",                "load"),
    ("acute training load",          "load"),
    ("chronic training load",        "load"),
    ("training stress",              "load"),
    ("ACWR",                         "load"),
    ("training volume",              "load"),
    # Zone 2
    ("Zone 2",                       "zone2"),
    ("Zone 2 training",              "zone2"),
    ("aerobic base",                 "zone2"),
    ("easy pace",                    "zone2"),
    ("low heart rate training",      "zone2"),
    # Adaptive training
    ("adaptive training",            "adaptive"),
    ("training plan adaptation",     "adaptive"),
    ("auto-regulation",              "adaptive"),
    ("readiness-based training",     "adaptive"),
    # Running performance
    ("running economy",              "running"),
    ("VO2 max",                      "running"),
    ("lactate threshold",            "running"),
    ("marathon training",            "running"),
    ("half marathon training",       "running"),
    ("5k training",                  "running"),
    ("tempo run",                    "running"),
    ("interval training",            "running"),
    ("strides",                      "running"),
    ("long run",                     "running"),
    ("taper",                        "running"),
    ("race day preparation",         "running"),
    # Cycling performance
    ("FTP",                          "cycling"),
    ("power zones",                  "cycling"),
    ("cycling training zones",       "cycling"),
    ("VO2 max intervals cycling",    "cycling"),
    ("cycling base training",        "cycling"),
    ("Sweet Spot training",          "cycling"),
    ("Zwift training",               "cycling"),
    ("outdoor vs indoor cycling",    "cycling"),
    ("power meter",                  "cycling"),
    # Wearables
    ("Garmin",                       "wearables"),
    ("Garmin Body Battery",          "wearables"),
    ("Garmin Training Status",       "wearables"),
    ("Oura ring",                    "wearables"),
    ("WHOOP",                        "wearables"),
    ("Apple Watch",                  "wearables"),
    ("wearable data",                "wearables"),
    ("sleep tracking",               "wearables"),
    # Fatigue & overtraining
    ("overtraining",                 "fatigue"),
    ("fatigue",                      "fatigue"),
    ("accumulated fatigue",          "fatigue"),
    ("functional overreaching",      "fatigue"),
    ("burnout",                      "fatigue"),
    ("tired legs",                   "fatigue"),
    # Nutrition & fuelling
    ("fuelling for endurance",       "nutrition"),
    ("carbohydrate periodisation",   "nutrition"),
    ("race day nutrition",           "nutrition"),
    ("training nutrition",           "nutrition"),
    ("protein for endurance",        "nutrition"),
    # Sleep
    ("sleep for athletes",           "sleep"),
    ("sleep quality",                "sleep"),
    ("sleep debt",                   "sleep"),
    ("sleep and performance",        "sleep"),
    ("napping for athletes",         "sleep"),
    # Strength
    ("strength training for runners","strength"),
    ("strength training cyclists",   "strength"),
    ("plyometrics for runners",      "strength"),
    ("injury prevention exercises",  "strength"),
]

# Question frames — applied to subjects to produce long-tail queries
FRAMES = [
    "What {subject} actually means for endurance athletes",
    "How to use {subject} to train smarter",
    "Why {subject} matters more than most runners think",
    "{subject} explained for runners and cyclists",
    "The truth about {subject} that coaches don't tell you",
    "How to interpret {subject} data without overreacting",
    "{subject}: what the research actually says",
    "Common {subject} mistakes endurance athletes make",
    "How {subject} changes during a training block",
    "What a low {subject} really means",
    "What a high {subject} really means",
    "Should you train when your {subject} is low?",
    "How long does it take to improve {subject}?",
    "The relationship between {subject} and injury risk",
    "How {subject} differs between runners and cyclists",
    "{subject} vs resting heart rate: which should you trust?",
    "How to track {subject} without obsessing over numbers",
    "Why your {subject} drops during race week",
    "How sleep affects {subject} for endurance athletes",
    "Building a training plan around {subject}",
]

# Standalone hand-crafted topics that don't fit the template pattern
HAND_CRAFTED = [
    "What Garmin's Training Readiness score actually measures",
    "HRV vs resting heart rate: which is the better recovery signal?",
    "How to structure a recovery week without losing fitness",
    "Zone 2 for runners: how slow is slow enough?",
    "Why easy runs feel so hard (and what to do about it)",
    "How to taper for a marathon without losing your mind",
    "The difference between fatigue and fitness — and how to tell",
    "Should you run with sore legs? What the research says",
    "How wearable data can mislead runners into overtraining",
    "Why your HRV looks terrible during race week",
    "How to build aerobic base without getting bored",
    "What happens to your body during a recovery run",
    "Training with a power meter vs heart rate: pros and cons",
    "Why athletes plateau despite consistent training",
    "How to use perceived exertion alongside wearable data",
    "The science of supercompensation for endurance athletes",
    "Why warm-up matters more than most runners think",
    "How heat affects training load and recovery",
    "What altitude training does (and doesn't do) for performance",
    "How to return to training after illness without setbacks",
    "Polarised vs pyramidal training: what works for amateur athletes?",
    "Why running economy matters more than VO2 max",
    "How to read your Garmin Training Status: productive vs overreaching",
    "The case for doing less: why recovery is training",
    "How many rest days do endurance athletes actually need?",
    "Why your race performance doesn't always match your training",
    "How to interpret sleep score data from wearables",
    "Building weekly training structure around your life (not against it)",
    "Why Zone 2 training feels deceptively easy — and why that's the point",
    "How to avoid the grey zone in endurance training",
    "What a good Oura readiness score actually tells you",
    "WHOOP recovery score explained for runners",
    "How chronic training load predicts race performance",
    "What training stress balance (TSB) means and how to use it",
    "How to peak for race day using training load data",
    "Why consistency beats intensity for endurance athletes",
    "How to adjust training load after a missed week",
    "The role of sleep in endurance adaptation",
    "How caffeine affects HRV and recovery metrics",
    "Why your easy pace should be slower in summer",
    "How to use cadence data to improve running economy",
    "What heart rate drift tells you about aerobic fitness",
    "How to know when to skip a workout vs push through",
    "Why the 10% rule for training load increase is mostly right",
    "How to train for your second marathon using data from your first",
    "What causes post-marathon fatigue and how long it lasts",
    "How to structure a training block using periodisation",
    "Why tracking resting heart rate beats expensive gadgets",
    "How to use recovery weeks to break through performance plateaus",
]


# ══════════════════════════════════════════════════════════════════════════════
# 2. HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def normalise(text: str) -> str:
    """Lowercase, strip punctuation/articles for fuzzy comparison."""
    t = text.lower()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\b(a|an|the|and|or|for|to|of|in|is|are|how|why|what|when|does|do|your|you)\b", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def significant_words(text: str) -> set:
    """Return set of significant words (3+ chars) from normalised text."""
    return {w for w in normalise(text).split() if len(w) >= 3}


def is_duplicate(candidate: str, existing_norms: list[set]) -> bool:
    """
    Fuzzy duplicate check: if candidate shares >= 60% of its significant
    words with any existing title, treat it as a duplicate.
    """
    cw = significant_words(candidate)
    if not cw:
        return False
    for ew in existing_norms:
        if not ew:
            continue
        overlap = len(cw & ew) / len(cw)
        if overlap >= 0.60:
            return True
    return False


def load_existing_titles() -> list[str]:
    """Pull titles from posts_manifest.json (preferred) and forma_blog_posts.md."""
    titles = []

    if MANIFEST_FILE.exists():
        try:
            posts = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
            titles += [p.get("title", "") for p in posts if p.get("title")]
        except Exception:
            pass

    if POSTS_FILE.exists():
        for line in POSTS_FILE.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^##\s+\d+\.\s+(.+)", line)
            if m:
                titles.append(m.group(1).strip())

    return list(set(t for t in titles if t))


def load_queue() -> list[str]:
    if not QUEUE_FILE.exists():
        return []
    return [l.strip() for l in QUEUE_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]


def save_queue(lines: list[str]):
    QUEUE_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_candidates() -> list[str]:
    """Generate all template-based + hand-crafted candidates."""
    candidates = list(HAND_CRAFTED)

    for subject, _bucket in SUBJECTS:
        for frame in FRAMES:
            # Only use frames that naturally fit (avoid awkward combos)
            topic = frame.format(subject=subject)
            # Capitalise first letter
            topic = topic[0].upper() + topic[1:]
            candidates.append(topic)

    # Deduplicate within candidate list itself (exact)
    seen = set()
    unique = []
    for c in candidates:
        key = c.strip().lower()
        if key not in seen:
            seen.add(key)
            unique.append(c)

    return unique


# ══════════════════════════════════════════════════════════════════════════════
# 3. OPTIONAL AI POLISH
#    Single Anthropic call to rewrite raw template topics into natural titles.
#    Only fires if ANTHROPIC_API_KEY is set. Cost: ~1–2k tokens per run.
# ══════════════════════════════════════════════════════════════════════════════

def ai_polish_topics(raw_topics: list[str]) -> list[str]:
    """
    Ask Anthropic to rewrite raw candidate topics into polished SEO titles.
    Returns original list if API unavailable or call fails.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return raw_topics

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        batch = raw_topics[:MAX_AI_IMPROVE]
        numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(batch))

        prompt = f"""You are an SEO content strategist for Forma, an adaptive endurance training app for runners and cyclists.

Rewrite each of the following blog topic drafts into a polished, specific, long-tail SEO title.

Rules:
- Keep titles under 80 characters
- Use plain English — no jargon unless the keyword is the target (e.g. "HRV", "FTP", "Zone 2")
- Make titles sound like something a real athlete would search for
- Preserve the core subject of each topic
- Return ONLY a JSON array of strings — no numbering, no preamble, no markdown

Draft topics:
{numbered}"""

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = response.content[0].text.strip()
        raw = re.sub(r"^```json\s*", "", raw)
        raw = re.sub(r"```\s*$", "", raw).strip()

        polished = json.loads(raw)

        if isinstance(polished, list) and len(polished) == len(batch):
            # Merge: polished titles for the batch + remainder unchanged
            result = [str(t).strip() for t in polished] + raw_topics[MAX_AI_IMPROVE:]
            print(f"  ✓ AI polished {len(batch)} topics")
            return result
        else:
            print("  ⚠  AI response shape unexpected — using raw topics")
            return raw_topics

    except Exception as e:
        print(f"  ⚠  AI polish skipped: {e}")
        return raw_topics


# ══════════════════════════════════════════════════════════════════════════════
# 4. MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("  Forma Topic Queue Refill")
    print("=" * 60)

    # ── Guard: queue already healthy? ─────────────────────────────────────────
    current_queue = load_queue()
    print(f"\n  Queue now  : {len(current_queue)} topics")

    if len(current_queue) >= MIN_QUEUE_SIZE:
        print(f"  ✅  Queue already has {len(current_queue)} topics (≥ {MIN_QUEUE_SIZE}) — nothing to do.")
        print("=" * 60)
        sys.exit(0)

    needed = TARGET_ADD
    print(f"  Target add : {needed} new topics\n")

    # ── Build existing title corpus for dedup ─────────────────────────────────
    existing_titles = load_existing_titles()
    print(f"  Existing posts  : {len(existing_titles)}")
    print(f"  Topics in queue : {len(current_queue)}")

    all_existing = existing_titles + current_queue
    existing_norms = [significant_words(t) for t in all_existing]

    # ── Generate candidates ────────────────────────────────────────────────────
    candidates = generate_candidates()
    print(f"  Raw candidates  : {len(candidates)}")

    # ── Filter duplicates ──────────────────────────────────────────────────────
    filtered = [c for c in candidates if not is_duplicate(c, existing_norms)]
    print(f"  After dedup     : {len(filtered)}")

    if not filtered:
        print("\n  ⚠  No new candidates found — consider expanding HAND_CRAFTED or SUBJECTS.")
        print("=" * 60)
        sys.exit(0)

    # Take slightly more than needed so AI can trim/improve
    shortlist = filtered[:needed + 5]

    # ── Optional AI polish ─────────────────────────────────────────────────────
    if os.environ.get("ANTHROPIC_API_KEY"):
        print("\n🤖  AI key found — polishing topic titles...")
        shortlist = ai_polish_topics(shortlist)
    else:
        print("\n  ℹ️   No ANTHROPIC_API_KEY — using deterministic titles")

    # Final trim to target
    to_add = shortlist[:needed]

    # ── Write queue ────────────────────────────────────────────────────────────
    updated_queue = current_queue + to_add
    save_queue(updated_queue)

    print(f"\n  ✅  Added {len(to_add)} topics")
    print(f"  📋  Queue now has {len(updated_queue)} topics total\n")
    print("  New topics added:")
    for i, t in enumerate(to_add, 1):
        print(f"    {i:2}. {t}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
