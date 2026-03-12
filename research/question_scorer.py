"""Stage 3 — Question Scorer.

Scores each deduplicated question on 5 dimensions (0–10 each),
computes weighted composite, infers content_type, and generates
suggested_title.

Input:  research/data/raw_questions.json
        research/config/scoring_weights.json
Output: research/data/scored_questions.json

Usage:
    python -m research.question_scorer
"""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "research" / "data"
CONFIG_DIR = REPO_ROOT / "research" / "config"
SHARED_DIR = REPO_ROOT / "shared"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path):
    with path.open() as fh:
        return json.load(fh)


def _contains_any(text: str, keywords: list[str]) -> bool:
    lower = text.lower()
    return any(kw.lower() in lower for kw in keywords)


def _stepwise_upvote_score(upvotes: int, thresholds: list) -> int:
    """Map upvote count to score via stepwise table [[min_upvotes, score], ...]."""
    score = 1
    for min_up, s in thresholds:
        if upvotes >= min_up:
            score = s
    return score


# ---------------------------------------------------------------------------
# Scoring dimensions
# ---------------------------------------------------------------------------

def _score_search_potential(q: dict, weights_cfg: dict) -> float:
    source = q.get("source", "")
    thresholds = weights_cfg["engagement_thresholds"]
    if source == "reddit":
        upvotes = q.get("engagement", {}).get("upvotes", 0)
        return _stepwise_upvote_score(upvotes, thresholds["reddit_upvotes"])
    elif source == "paa":
        return thresholds["paa_default"]
    elif source == "autosuggest":
        return thresholds["autosuggest_default"]
    elif source == "competitor":
        return thresholds["competitor_default"]
    return 5  # default


def _score_pain_intensity(q: dict, weights_cfg: dict) -> float:
    pain_kws = weights_cfg["pain_keywords"]
    qtype = q.get("question_type", "other")
    base_map = {"why": 7, "how": 6, "what": 4, "other": 3}
    base = base_map.get(qtype, 5 if qtype in ("is", "should", "can") else 3)
    score = base
    if _contains_any(q.get("text", ""), pain_kws):
        score += 2
    if q.get("word_count", 0) >= 12:
        score += 1
    return min(score, 10)


def _score_commercial_intent(q: dict, weights_cfg: dict) -> float:
    text = q.get("text", "")
    lower = text.lower()
    score = 3
    if _contains_any(text, weights_cfg["device_keywords"]):
        score += 3
    if _contains_any(text, weights_cfg["product_keywords"]):
        score += 2
    improve_kws = ["improve", "fix", "better", "best"]
    if _contains_any(text, improve_kws):
        score += 2
    if lower.startswith("what is"):
        score -= 1
    return min(max(score, 0), 10)


def _score_topical_fit(q: dict, taxonomy_clusters: list) -> float:
    text = q.get("text", "").lower()
    best = 0.0
    for cluster in taxonomy_clusters:
        kws = cluster.get("keywords", {})
        primary = [k.lower() for k in kws.get("primary", [])]
        secondary = [k.lower() for k in kws.get("secondary", [])]
        negative = [k.lower() for k in kws.get("negative", [])]

        # Negative match kills this cluster
        if any(n in text for n in negative):
            continue

        p_matches = sum(1 for p in primary if re.search(r"\b" + re.escape(p) + r"\b", text))
        s_matches = sum(1 for s in secondary if re.search(r"\b" + re.escape(s) + r"\b", text))

        if p_matches >= 2:
            score = 8.0
        elif p_matches == 1 and s_matches >= 1:
            score = 6.0
        elif p_matches == 1:
            score = 4.0
        elif s_matches >= 1:
            score = 3.0
        else:
            score = 0.0

        if p_matches >= 1:
            # Full primary keyword match bonus
            score = max(score, 10.0 if p_matches >= 1 and _full_primary_match(text, primary) else score)

        best = max(best, score)
    return best


def _full_primary_match(text: str, primary: list[str]) -> bool:
    """True if any single primary keyword appears as a standalone phrase."""
    for p in primary:
        pattern = re.compile(r"\b" + re.escape(p) + r"\b", re.IGNORECASE)
        if pattern.search(text):
            return True
    return False


def _jaccard(a: str, b: str) -> float:
    sa = set(a.lower().split())
    sb = set(b.lower().split())
    if not sa and not sb:
        return 1.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


def _score_differentiation(q: dict, competitor_texts: list[str]) -> float:
    text = q.get("text", "").lower().strip()
    score = 7.0
    for ct in competitor_texts:
        ct_lower = ct.lower().strip()
        if text == ct_lower:
            score -= 5
            break
        sim = _jaccard(text, ct_lower)
        if sim > 0.6:
            score -= 2
            break
    return max(score, 0.0)


# ---------------------------------------------------------------------------
# Content type inference
# ---------------------------------------------------------------------------

METRIC_WORDS_RE = re.compile(
    r"\b(miles|km|kilometres|kilometers|minutes|hours|pace|bpm|watts|steps|calories|beats)\b",
    re.IGNORECASE,
)


def _infer_content_type(q: dict, composite: float) -> str:
    text = q.get("text", "").lower()
    wc = q.get("word_count", 0)
    qtype = q.get("question_type", "other")
    source = q.get("source", "")

    if text.startswith("what is") and wc <= 8:
        return "programmatic"
    if re.search(r"\bcalculate\b|\bcalculator\b|\bhow do i calculate\b", text):
        return "tool"
    if re.search(r"\baverage\b|\btypical\b|\bhow many\b", text) and METRIC_WORDS_RE.search(text):
        return "research"
    # Autosuggest fragments with no question word → programmatic SEO targets
    if source == "autosuggest" and qtype == "other" and wc <= 6:
        return "programmatic"
    if composite >= 8.0 and qtype in ("why", "how"):
        return "pillar_article"
    return "article"


# ---------------------------------------------------------------------------
# Title generation
# ---------------------------------------------------------------------------

ACRONYMS = {"ftp", "hrv", "tsb", "ctl", "atl", "tss", "acwr", "vo2", "bpm", "km", "pb", "bq"}


def _title_case(s: str) -> str:
    # Simple title case — capitalise each word except minor words unless first
    MINOR = {"a", "an", "the", "and", "but", "or", "for", "nor", "on", "at",
              "to", "by", "in", "of", "up", "as", "is", "it"}
    words = s.split()
    result = []
    for i, w in enumerate(words):
        if w.lower() in ACRONYMS:
            result.append(w.upper())
        elif i == 0 or w.lower() not in MINOR:
            result.append(w.capitalize())
        else:
            result.append(w.lower())
    return " ".join(result)


def _generate_suggested_title(q: dict) -> str:
    text = q.get("text", "").strip().rstrip("?")
    lower = text.lower()

    if lower.startswith("is "):
        # "Is zone 2 training worth it?" → "Zone 2 Training: Is It Worth It?"
        rest = text[3:].strip()
        return _title_case(f"{rest}: Is It?")

    if lower.startswith("should "):
        # "Should I run in zone 2 every day?" → "Zone 2 Every Day: Should You?"
        rest = text[7:].strip()
        # Replace leading "I " with ""
        rest = re.sub(r"^i\b", "you", rest, flags=re.IGNORECASE)
        return _title_case(f"{rest}: Should You?")

    return _title_case(text)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    raw_path = DATA_DIR / "raw_questions.json"
    weights_path = CONFIG_DIR / "scoring_weights.json"
    taxonomy_path = SHARED_DIR / "taxonomy.json"

    for p in (raw_path, weights_path, taxonomy_path):
        if not p.exists():
            print(f"[scorer] ERROR: {p} not found.")
            sys.exit(1)

    questions: list[dict] = _load_json(raw_path)
    weights_cfg: dict = _load_json(weights_path)
    taxonomy: dict = _load_json(taxonomy_path)
    clusters = taxonomy.get("clusters", [])

    dimension_weights = {
        "search_potential":  weights_cfg["search_potential"],
        "pain_intensity":    weights_cfg["pain_intensity"],
        "commercial_intent": weights_cfg["commercial_intent"],
        "topical_fit":       weights_cfg["topical_fit"],
        "differentiation":   weights_cfg["differentiation"],
    }

    # Collect competitor texts once for differentiation scoring
    competitor_texts = [
        q.get("text", "")
        for q in questions
        if q.get("source") == "competitor"
    ]

    scored: list[dict] = []
    for q in questions:
        sp = _score_search_potential(q, weights_cfg)
        pi = _score_pain_intensity(q, weights_cfg)
        ci = _score_commercial_intent(q, weights_cfg)
        tf = _score_topical_fit(q, clusters)
        di = _score_differentiation(q, competitor_texts)

        composite = round(
            sp * dimension_weights["search_potential"]
            + pi * dimension_weights["pain_intensity"]
            + ci * dimension_weights["commercial_intent"]
            + tf * dimension_weights["topical_fit"]
            + di * dimension_weights["differentiation"],
            1,
        )

        content_type = _infer_content_type(q, composite)
        suggested_title = _generate_suggested_title(q)

        scored_q = dict(q)
        scored_q["scores"] = {
            "search_potential": sp,
            "pain_intensity": pi,
            "commercial_intent": ci,
            "topical_fit": tf,
            "differentiation": di,
            "composite": composite,
        }
        scored_q["content_type"] = content_type
        scored_q["suggested_title"] = suggested_title
        scored_q["status"] = "unscored"
        scored.append(scored_q)

    out_path = DATA_DIR / "scored_questions.json"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as fh:
        json.dump(scored, fh, indent=2)

    composites = [q["scores"]["composite"] for q in scored]
    avg = round(sum(composites) / len(composites), 2) if composites else 0.0
    top = max(composites) if composites else 0.0
    bottom = min(composites) if composites else 0.0

    print(f"[scorer] Done. Scored {len(scored)} questions → {out_path}")
    print(f"         avg={avg}  top={top}  bottom={bottom}")

    # Update harvest report
    report_path = DATA_DIR / "harvest_report.json"
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text())
            report["scoring"] = {
                "scored": len(scored),
                "avg_composite": avg,
                "top_score": top,
                "bottom_score": bottom,
            }
            with report_path.open("w") as fh:
                json.dump(report, fh, indent=2)
        except Exception as exc:
            print(f"[scorer] WARNING: could not update harvest_report.json — {exc}")


if __name__ == "__main__":
    main()
