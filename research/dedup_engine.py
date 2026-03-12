"""Stage 2 — Deduplication Engine.

Two-pass deduplication of raw_questions.json:
  Pass 1: Exact match (MD5 of normalised text)
  Pass 2: Fuzzy match (Jaccard similarity >= 0.75)

Overwrites research/data/raw_questions.json with deduplicated results.
Writes research/data/dedup_log.json for auditing.

Usage:
    python -m research.dedup_engine
"""

import hashlib
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "research" / "data"

JACCARD_THRESHOLD = 0.75
PUNCTUATION_RE = re.compile(r"[^\w\s]")
WHITESPACE_RE = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# Text normalisation
# ---------------------------------------------------------------------------

def _normalise(text: str) -> str:
    text = text.lower()
    text = PUNCTUATION_RE.sub("", text)
    text = WHITESPACE_RE.sub(" ", text).strip()
    return text


def _md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Jaccard similarity
# ---------------------------------------------------------------------------

def _token_set(text: str) -> set[str]:
    return set(_normalise(text).split())


def _jaccard(a: str, b: str) -> float:
    sa = _token_set(a)
    sb = _token_set(b)
    if not sa and not sb:
        return 1.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


# ---------------------------------------------------------------------------
# Engagement comparison
# ---------------------------------------------------------------------------

def _engagement_score(q: dict) -> int:
    eng = q.get("engagement", {})
    return eng.get("upvotes", 0) + eng.get("comments", 0)


def _higher_engagement(a: dict, b: dict) -> dict:
    return a if _engagement_score(a) >= _engagement_score(b) else b


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    raw_path = DATA_DIR / "raw_questions.json"
    if not raw_path.exists():
        print("[dedup] ERROR: raw_questions.json not found. Run question_collector first.")
        sys.exit(1)

    with raw_path.open() as fh:
        questions: list[dict] = json.load(fh)

    dedup_log: list[dict] = []

    # ------------------------------------------------------------------
    # Pass 1 — Exact deduplication
    # ------------------------------------------------------------------
    exact_map: dict[str, dict] = {}  # normalised_hash -> canonical question

    for q in questions:
        norm = _normalise(q.get("text", ""))
        h = _md5(norm)
        if h in exact_map:
            canonical = exact_map[h]
            winner = _higher_engagement(canonical, q)
            loser = q if winner is canonical else canonical
            # Merge variants
            winner.setdefault("variants", [])
            winner["variants"].append(loser.get("id", ""))
            exact_map[h] = winner
            dedup_log.append({
                "kept": winner.get("id"),
                "merged": loser.get("id"),
                "similarity": 1.0,
                "method": "exact",
            })
        else:
            q.setdefault("variants", [])
            exact_map[h] = q

    pass1_questions = list(exact_map.values())
    exact_removed = len(questions) - len(pass1_questions)
    print(f"[dedup] Pass 1 (exact): {len(questions)} → {len(pass1_questions)} ({exact_removed} removed)")

    # ------------------------------------------------------------------
    # Pass 2 — Fuzzy deduplication (Jaccard)
    # ------------------------------------------------------------------
    canonical_list: list[dict] = []

    for q in pass1_questions:
        merged = False
        for canon in canonical_list:
            sim = _jaccard(q.get("text", ""), canon.get("text", ""))
            if sim >= JACCARD_THRESHOLD:
                # Merge into canonical — keep higher engagement
                winner = _higher_engagement(canon, q)
                loser = q if winner is canon else canon
                # Update the canonical_list entry in-place
                idx = canonical_list.index(canon)
                winner.setdefault("variants", [])
                winner["variants"].append(loser.get("id", ""))
                canonical_list[idx] = winner
                dedup_log.append({
                    "kept": winner.get("id"),
                    "merged": loser.get("id"),
                    "similarity": round(sim, 4),
                    "method": "fuzzy",
                })
                merged = True
                break
        if not merged:
            canonical_list.append(q)

    fuzzy_removed = len(pass1_questions) - len(canonical_list)
    print(f"[dedup] Pass 2 (fuzzy): {len(pass1_questions)} → {len(canonical_list)} ({fuzzy_removed} removed)")

    # ------------------------------------------------------------------
    # Write outputs
    # ------------------------------------------------------------------
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with raw_path.open("w") as fh:
        json.dump(canonical_list, fh, indent=2)

    log_path = DATA_DIR / "dedup_log.json"
    with log_path.open("w") as fh:
        json.dump(dedup_log, fh, indent=2)

    print(f"[dedup] Done. {len(canonical_list)} unique questions written to {raw_path}")
    print(f"[dedup] Dedup log written to {log_path}")

    # Update harvest report
    report_path = DATA_DIR / "harvest_report.json"
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text())
            report["deduplication"] = {
                "exact_removed": exact_removed,
                "fuzzy_removed": fuzzy_removed,
                "total_unique": len(canonical_list),
            }
            with report_path.open("w") as fh:
                json.dump(report, fh, indent=2)
        except Exception as exc:
            print(f"[dedup] WARNING: could not update harvest_report.json — {exc}")


if __name__ == "__main__":
    main()
