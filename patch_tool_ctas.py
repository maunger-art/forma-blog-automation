#!/usr/bin/env python3
"""
Patch posts_manifest.json to add tool_ctas to relevant posts.
Run from ~/forma-blog-automation/
"""
import json, re

# ── Tool CTA mapping ──────────────────────────────────────────────────────────
# key = substring to match in slug
# value = list of tool names (slugified by the builder as /tools/{name-with-dashes})

TOOL_MAP = {
    # Zone 2 calculator → zone2-calculator
    "zone-2": ["zone2 calculator"],
    "zone2": ["zone2 calculator"],
    "easy-run": ["zone2 calculator"],
    "aerobic-base": ["zone2 calculator"],
    "slow": ["zone2 calculator"],

    # HR Zone calculator → hr-zone-calculator
    "training-zone": ["hr zone calculator"],
    "heart-rate": ["hr zone calculator"],
    "cycling-training-zone": ["hr zone calculator", "zone2 calculator"],
    "ftp": ["hr zone calculator"],
    "hrv": ["hr zone calculator"],
    "readiness": ["hr zone calculator"],
    "garmin-readiness": ["hr zone calculator"],
    "garmin-training-readiness": ["hr zone calculator"],
}

# Load manifest
with open("posts_manifest.json") as f:
    manifest = json.load(f)

updated = 0
for post in manifest:
    slug = post.get("slug", "")
    tools = set(post.get("tool_ctas", []))
    
    for pattern, ctas in TOOL_MAP.items():
        if pattern in slug:
            for cta in ctas:
                tools.add(cta)
    
    if tools != set(post.get("tool_ctas", [])):
        post["tool_ctas"] = sorted(list(tools))
        updated += 1
        print(f"  ✓ {slug} → {post['tool_ctas']}")

# Save
with open("posts_manifest.json", "w") as f:
    json.dump(manifest, f, indent=2)

print(f"\nDone. {updated} posts updated.")
