"""Stage 4 — Cluster Builder.

Assigns each scored question to the best-matching taxonomy cluster,
builds the clustered_questions.json summary, writes unclassified.json,
and constructs question_graph.json.

Input:  research/data/scored_questions.json
        shared/taxonomy.json
Output: research/data/clustered_questions.json
        research/data/unclassified.json
        research/data/question_graph.json

Usage:
    python -m research.cluster_builder
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "research" / "data"
SHARED_DIR = REPO_ROOT / "shared"

CLUSTER_THRESHOLD = 0.2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path):
    with path.open() as fh:
        return json.load(fh)


def _cluster_score(text: str, cluster: dict) -> float:
    """Score a question against a cluster. Returns 0–1."""
    lower = text.lower()
    kws = cluster.get("keywords", {})
    primary = [k.lower() for k in kws.get("primary", [])]
    secondary = [k.lower() for k in kws.get("secondary", [])]
    negative = [k.lower() for k in kws.get("negative", [])]

    # Negative keyword match → zero
    for n in negative:
        if re.search(r"\b" + re.escape(n) + r"\b", lower):
            return 0.0

    score = 0.0
    for p in primary:
        if re.search(r"\b" + re.escape(p) + r"\b", lower):
            score += 0.4
    for s in secondary:
        if re.search(r"\b" + re.escape(s) + r"\b", lower):
            score += 0.2

    return min(score, 1.0)


def _jaccard(a: str, b: str) -> float:
    sa = set(a.lower().split())
    sb = set(b.lower().split())
    if not sa and not sb:
        return 1.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def _build_graph(clustered_questions: dict, clusters_meta: list) -> list[dict]:
    """Build pillar→child edges per cluster."""
    cluster_meta_map = {c["id"]: c for c in clusters_meta}
    edges = []

    for cluster_id, cluster_data in clustered_questions.get("clusters", {}).items():
        questions = cluster_data.get("top_questions", [])

        # Find pillar questions: starts with "what is", <= 8 words, no opinion qualifiers
        pillars = [
            q for q in questions
            if q.get("text", "").lower().startswith("what is")
            and q.get("word_count", 999) <= 8
            and not re.search(r"\b(best|good|better|worst)\b", q.get("text", ""), re.IGNORECASE)
        ]

        if not pillars:
            continue

        for pillar in pillars:
            p_text = pillar.get("text", "").lower()
            # Extract core topic: strip "what is" prefix
            core = re.sub(r"^what is\s+", "", p_text).strip().rstrip("?")
            core_tokens = set(core.split())

            for child in questions:
                if child.get("id") == pillar.get("id"):
                    continue
                c_tokens = set(child.get("text", "").lower().split())
                if core_tokens & c_tokens:
                    edges.append({
                        "cluster": cluster_id,
                        "pillar_id": pillar.get("id"),
                        "pillar_text": pillar.get("text"),
                        "child_id": child.get("id"),
                        "child_text": child.get("text"),
                        "relationship": "specificity",
                    })

    return edges


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    scored_path = DATA_DIR / "scored_questions.json"
    taxonomy_path = SHARED_DIR / "taxonomy.json"

    for p in (scored_path, taxonomy_path):
        if not p.exists():
            print(f"[cluster] ERROR: {p} not found.")
            sys.exit(1)

    questions: list[dict] = _load_json(scored_path)
    taxonomy: dict = _load_json(taxonomy_path)
    clusters_meta: list = taxonomy.get("clusters", [])

    classified: list[dict] = []
    unclassified: list[dict] = []

    for q in questions:
        text = q.get("text", "")
        best_id = None
        best_score = 0.0

        for cluster in clusters_meta:
            s = _cluster_score(text, cluster)
            if s > best_score:
                best_score = s
                best_id = cluster["id"]

        q = dict(q)
        if best_score >= CLUSTER_THRESHOLD and best_id:
            q["cluster"] = best_id
            q["cluster_confidence"] = round(best_score, 4)
            classified.append(q)
        else:
            q["cluster"] = None
            q["cluster_confidence"] = round(best_score, 4)
            unclassified.append(q)

    # ------------------------------------------------------------------
    # Build clustered_questions.json
    # ------------------------------------------------------------------
    cluster_buckets: dict[str, list] = {c["id"]: [] for c in clusters_meta}
    for q in classified:
        cid = q["cluster"]
        if cid in cluster_buckets:
            cluster_buckets[cid].append(q)

    clusters_out: dict = {}
    for c in clusters_meta:
        cid = c["id"]
        qs = sorted(
            cluster_buckets.get(cid, []),
            key=lambda x: x.get("scores", {}).get("composite", 0),
            reverse=True,
        )
        ct_split = {"article": 0, "programmatic": 0, "tool": 0, "research": 0, "pillar_article": 0}
        for q in qs:
            ct = q.get("content_type", "article")
            if ct in ct_split:
                ct_split[ct] += 1
            else:
                ct_split["article"] += 1

        clusters_out[cid] = {
            "name": c["name"],
            "question_count": len(qs),
            "top_questions": qs,
            "content_type_split": ct_split,
        }

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    clustered_output = {
        "generated_at": generated_at,
        "total_questions": len(classified),
        "clusters": clusters_out,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    clustered_path = DATA_DIR / "clustered_questions.json"
    with clustered_path.open("w") as fh:
        json.dump(clustered_output, fh, indent=2)

    unclassified_path = DATA_DIR / "unclassified.json"
    with unclassified_path.open("w") as fh:
        json.dump(unclassified, fh, indent=2)

    # ------------------------------------------------------------------
    # Build question_graph.json
    # ------------------------------------------------------------------
    graph_edges = _build_graph(clustered_output, clusters_meta)
    graph_path = DATA_DIR / "question_graph.json"
    with graph_path.open("w") as fh:
        json.dump(graph_edges, fh, indent=2)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    total = len(questions)
    n_classified = len(classified)
    n_unclassified = len(unclassified)
    unc_rate = f"{round(n_unclassified / total * 100, 1)}%" if total else "0%"

    print(f"[cluster] Done. {n_classified} classified, {n_unclassified} unclassified ({unc_rate})")
    by_cluster = {cid: len(qs) for cid, qs in cluster_buckets.items()}
    for cid, cnt in by_cluster.items():
        print(f"          {cid}: {cnt}")

    # Update harvest report
    report_path = DATA_DIR / "harvest_report.json"
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text())
            report["clustering"] = {
                "classified": n_classified,
                "unclassified": n_unclassified,
                "unclassified_rate": unc_rate,
                "by_cluster": by_cluster,
            }
            with report_path.open("w") as fh:
                json.dump(report, fh, indent=2)
        except Exception as exc:
            print(f"[cluster] WARNING: could not update harvest_report.json — {exc}")


if __name__ == "__main__":
    main()
