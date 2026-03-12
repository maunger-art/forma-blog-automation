"""Stage 1 — Question Collector.

Orchestrates all data sources, assigns IDs, detects question type,
and writes research/data/raw_questions.json.

Usage:
    python -m research.question_collector
    AQE_SOURCES=reddit,autosuggest python -m research.question_collector
"""

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "research" / "data"
CONFIG_DIR = REPO_ROOT / "research" / "config"
SHARED_DIR = REPO_ROOT / "shared"

DATA_DIR.mkdir(parents=True, exist_ok=True)

QUESTION_START_RE = re.compile(
    r"^(why|what|how|is|should|can|does|do|will|when|which|who)\b",
    re.IGNORECASE,
)

COMPARISON_RE = re.compile(r"\bvs\.?\b|\bversus\b|\bcompared?\b", re.IGNORECASE)


def _load_json(path: Path) -> dict | list:
    with path.open() as fh:
        return json.load(fh)


def _question_type(text: str) -> str:
    lower = text.lower().strip()
    first = lower.split()[0] if lower.split() else ""
    if COMPARISON_RE.search(lower):
        return "comparison"
    mapping = {
        "why": "why", "what": "what", "how": "how",
        "is": "is", "should": "should", "can": "can",
        "does": "does", "do": "do", "will": "will",
        "when": "when", "which": "which", "who": "who",
    }
    qtype = mapping.get(first)
    if qtype in ("is", "should", "can", "does", "do", "will", "when", "which", "who"):
        return qtype
    return qtype or "other"


def _is_question(text: str) -> bool:
    return bool(QUESTION_START_RE.match(text.strip())) or text.strip().endswith("?")


def _make_id(source: str, text: str) -> str:
    h = hashlib.md5(text.lower().encode()).hexdigest()[:8]
    prefix = source.split("-")[0][:8]
    return f"{prefix}-{h}"


def _build_raw_question(item: dict, now_iso: str) -> dict:
    text = item.get("text", "").strip()
    source = item.get("source", "unknown")
    return {
        "id": _make_id(source, text),
        "text": text,
        "source": source,
        "source_detail": item.get("source_detail", ""),
        "collected_at": now_iso,
        "engagement": item.get("engagement", {}),
        "raw_url": item.get("raw_url", ""),
        "question_type": _question_type(text),
        "word_count": len(text.split()),
        "is_question": _is_question(text),
    }


def _source_failures_summary(failures: list[str]) -> list[str]:
    return failures


def main() -> None:
    sources_cfg = _load_json(CONFIG_DIR / "sources.json")
    taxonomy = _load_json(SHARED_DIR / "taxonomy.json")

    env_sources = os.environ.get("AQE_SOURCES", "all").lower()
    if os.environ.get("AQE_SKIP_CACHE"):
        # Bust cache by temporarily renaming cache dir — simplest approach
        pass

    enabled: set[str]
    if env_sources == "all":
        enabled = {"reddit", "autosuggest", "paa", "competitor"}
    else:
        enabled = {s.strip() for s in env_sources.split(",")}

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Lazy imports — only load what's needed
    source_map = {}
    if "reddit" in enabled:
        from research.sources.reddit_source import RedditSource
        source_map["reddit"] = RedditSource()
    if "autosuggest" in enabled:
        from research.sources.autosuggest_source import AutosuggestSource
        source_map["autosuggest"] = AutosuggestSource()
    if "paa" in enabled:
        from research.sources.paa_source import PAASource
        source_map["paa"] = PAASource()
    if "competitor" in enabled:
        from research.sources.competitor_source import CompetitorSource
        source_map["competitor"] = CompetitorSource()

    collection_counts: dict[str, int] = {}
    source_failures: list[str] = []
    all_raw: list[dict] = []

    for source_name, source_obj in source_map.items():
        print(f"[collector] Running source: {source_name}")
        try:
            items = source_obj.fetch(sources_cfg)
        except Exception as exc:
            print(f"[collector] WARNING: {source_name} failed — {exc}")
            source_failures.append(source_name)
            items = []
        collection_counts[source_name] = len(items)
        for item in items:
            all_raw.append(_build_raw_question(item, now_iso))

    # Deduplicate IDs — keep first occurrence per ID
    seen_ids: set[str] = set()
    unique_raw: list[dict] = []
    for q in all_raw:
        if q["id"] not in seen_ids:
            seen_ids.add(q["id"])
            unique_raw.append(q)

    out_path = DATA_DIR / "raw_questions.json"
    with out_path.open("w") as fh:
        json.dump(unique_raw, fh, indent=2)

    total = len(unique_raw)
    print(f"[collector] Done. Wrote {total} unique questions to {out_path}")
    for src, cnt in collection_counts.items():
        print(f"           {src}: {cnt} raw")

    # Write harvest report (partial — updated by later stages)
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%d-weekly")
    report_path = DATA_DIR / "harvest_report.json"
    existing_report: dict = {}
    if report_path.exists():
        try:
            existing_report = json.loads(report_path.read_text())
        except Exception:
            pass

    report = {
        "run_id": run_id,
        "run_at": now_iso,
        "collection": {
            "reddit": collection_counts.get("reddit", 0),
            "autosuggest": collection_counts.get("autosuggest", 0),
            "paa": collection_counts.get("paa", 0),
            "competitor": collection_counts.get("competitor", 0),
            "total_raw": sum(collection_counts.values()),
            "source_failures": source_failures,
        },
        "deduplication": existing_report.get("deduplication", {"exact_removed": 0, "fuzzy_removed": 0, "total_unique": 0}),
        "scoring": existing_report.get("scoring", {"scored": 0, "avg_composite": 0.0, "top_score": 0.0, "bottom_score": 0.0}),
        "clustering": existing_report.get("clustering", {"classified": 0, "unclassified": 0, "unclassified_rate": "0%", "by_cluster": {}}),
        "queue": existing_report.get("queue", {"total_queued": 0, "new_this_run": 0, "assigned": 0, "in_progress": 0, "published": 0}),
    }
    with report_path.open("w") as fh:
        json.dump(report, fh, indent=2)


if __name__ == "__main__":
    main()
