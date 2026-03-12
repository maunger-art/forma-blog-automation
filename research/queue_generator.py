"""Stage 5 — Queue Generator.

Fills shared/queue.json from clustered_questions.json, respecting
per-cluster article_quota from taxonomy.json. Preserves non-published
existing entries, never duplicates, sorts by composite_score desc.

Input:  research/data/clustered_questions.json
        shared/taxonomy.json
        shared/queue.json (optional, existing)
Output: shared/queue.json

Usage:
    python -m research.queue_generator
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "research" / "data"
SHARED_DIR = REPO_ROOT / "shared"


def _load_json(path: Path):
    with path.open() as fh:
        return json.load(fh)


def main() -> None:
    clustered_path = DATA_DIR / "clustered_questions.json"
    taxonomy_path = SHARED_DIR / "taxonomy.json"
    queue_path = SHARED_DIR / "queue.json"

    for p in (clustered_path, taxonomy_path):
        if not p.exists():
            print(f"[queue] ERROR: {p} not found.")
            sys.exit(1)

    clustered: dict = _load_json(clustered_path)
    taxonomy: dict = _load_json(taxonomy_path)
    clusters_meta: list = taxonomy.get("clusters", [])

    # Build quota map from taxonomy
    quota_map: dict[str, int] = {c["id"]: c.get("article_quota", 0) for c in clusters_meta}

    # Load existing queue
    existing_queue: list[dict] = []
    if queue_path.exists():
        try:
            existing_queue = json.loads(queue_path.read_text())
        except Exception:
            existing_queue = []

    # Preserve non-published entries
    preserved = [e for e in existing_queue if e.get("status") != "published"]

    # Build sets of already-queued/published question IDs
    already_queued_ids: set[str] = {e["question_id"] for e in existing_queue}

    # Count currently queued per cluster (non-published)
    queued_per_cluster: dict[str, int] = {}
    for e in preserved:
        cid = e.get("cluster", "")
        queued_per_cluster[cid] = queued_per_cluster.get(cid, 0) + 1

    new_entries: list[dict] = []
    new_count = 0

    cluster_data = clustered.get("clusters", {})

    for cluster in clusters_meta:
        cid = cluster["id"]
        quota = quota_map.get(cid, 0)
        currently_queued = queued_per_cluster.get(cid, 0)
        slots_remaining = quota - currently_queued

        if slots_remaining <= 0:
            continue

        cluster_qs = cluster_data.get(cid, {}).get("top_questions", [])
        # Already sorted by composite desc from cluster_builder

        added = 0
        for q in cluster_qs:
            if added >= slots_remaining:
                break
            qid = q.get("id")
            if qid in already_queued_ids:
                continue

            entry = {
                "rank": 0,  # assigned after sorting
                "question_id": qid,
                "question_text": q.get("text", ""),
                "suggested_title": q.get("suggested_title", ""),
                "cluster": cid,
                "content_type": q.get("content_type", "article"),
                "composite_score": q.get("scores", {}).get("composite", 0.0),
                "status": "unassigned",
                "assigned_to": None,
                "due_date": None,
                "published_url": None,
            }
            new_entries.append(entry)
            already_queued_ids.add(qid)
            added += 1
            new_count += 1

    # Merge: preserved + new, sort by composite_score desc
    final_queue = preserved + new_entries
    final_queue.sort(key=lambda x: x.get("composite_score", 0), reverse=True)

    # Assign ranks
    for i, entry in enumerate(final_queue, start=1):
        entry["rank"] = i

    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    with queue_path.open("w") as fh:
        json.dump(final_queue, fh, indent=2)

    # Stats
    total = len(final_queue)
    assigned = sum(1 for e in final_queue if e.get("status") == "assigned")
    in_progress = sum(1 for e in final_queue if e.get("status") == "in_progress")
    published = sum(1 for e in existing_queue if e.get("status") == "published")

    print(f"[queue] Done. {total} total queued ({new_count} new this run) → {queue_path}")

    # Update harvest report
    report_path = DATA_DIR / "harvest_report.json"
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text())
            report["queue"] = {
                "total_queued": total,
                "new_this_run": new_count,
                "assigned": assigned,
                "in_progress": in_progress,
                "published": published,
            }
            with report_path.open("w") as fh:
                json.dump(report, fh, indent=2)
        except Exception as exc:
            print(f"[queue] WARNING: could not update harvest_report.json — {exc}")


if __name__ == "__main__":
    main()
