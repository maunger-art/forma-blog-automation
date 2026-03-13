#!/usr/bin/env python3
"""
patch_tool_ctas_v2.py
Adds tool_ctas for the 4 new tools:
  - pace-predictor
  - marathon-pace-calculator
  - training-load-calculator
  - readiness-explainer

Run from forma-blog-automation/:
  python3 patch_tool_ctas_v2.py
"""

import json

MANIFEST = "posts_manifest.json"

# ── Rules ──────────────────────────────────────────────────────────────────────
# Each entry: (tool_slug, set_of_slug_keywords)
# If any keyword appears in the post slug, that tool gets added.

RULES = [
    (
        "pace-predictor",
        [
            "marathon", "pace", "race", "5k", "10k", "half",
            "training-plan", "cycling-endurance", "running",
            "what-pace", "how-long-should-i-run", "how-long-should-you-train",
        ],
    ),
    (
        "marathon-pace-calculator",
        [
            "marathon", "pace", "what-pace", "10-10-10",
            "training-plan", "hal-higdon", "16-weeks", "20-weeks",
            "12-weeks", "6-months", "5-months",
        ],
    ),
    (
        "training-load-calculator",
        [
            "training-load", "atl", "ctl", "acwr", "28-day",
            "what-is-the-training-load", "what-is-a-good-training-load",
            "training-load-apple-watch", "training-load-class",
            "80-20", "aerobic-base", "overtraining", "injury-prevention",
            "how-long-does-it-take-to-build",
        ],
    ),
    (
        "readiness-explainer",
        [
            "readiness", "hrv", "garmin-readiness", "garmin-training-readiness",
            "sleep", "recovery", "stress", "whoop", "oura",
            "why-is-my-garmin", "what-garmin-recovery",
            "how-sleep-debt", "garmin-vs-oura",
        ],
    ),
]

# ── Run ────────────────────────────────────────────────────────────────────────
with open(MANIFEST, "r") as f:
    posts = json.load(f)

updated = 0

for post in posts:
    slug = post["slug"]
    existing = post.get("tool_ctas", [])
    if isinstance(existing, str):
        existing = [existing]

    to_add = []
    for tool_slug, keywords in RULES:
        if tool_slug not in existing:
            if any(kw in slug for kw in keywords):
                to_add.append(tool_slug)

    if to_add:
        post["tool_ctas"] = existing + to_add
        updated += 1
        print(f"  + {slug}")
        print(f"    added: {to_add}")
        print(f"    full:  {post['tool_ctas']}")

with open(MANIFEST, "w") as f:
    json.dump(posts, f, indent=2)

print(f"\nDone. {updated} posts updated.")
