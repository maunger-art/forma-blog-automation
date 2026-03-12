"""Stage 4 — Cluster Builder v2.
Assigns scored questions to taxonomy clusters, classifies each as
pillar / supporting / tool / research, builds cluster_manifest.json,
pillar_page_specs.json, tool_opportunities.json, and question_graph.json.
Input:  research/data/scored_questions.json
        shared/taxonomy.json
Output: research/data/clustered_questions.json
        research/data/unclassified.json
        research/data/question_graph.json
        shared/cluster_manifest.json
        shared/pillar_page_specs.json
        shared/tool_opportunities.json
Usage:
    python -m research.cluster_builder
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR  = REPO_ROOT / "research" / "data"
SHARED_DIR = REPO_ROOT / "shared"
CLUSTER_THRESHOLD  = 0.2
PILLAR_MIN_SCORE   = 5.5   # composite score floor for pillar candidacy
TOOL_MIN_SCORE     = 4.5
RESEARCH_MIN_SCORE = 5.0
MAX_PILLARS_PER_CLUSTER = 2
# Keywords that signal a question is tool-worthy
TOOL_SIGNALS = [
    "calculator", "calculate", "how much", "how long", "what should my",
    "what is my", "pace", "target heart rate", "how many", "what pace",
    "how fast", "how often", "how many weeks", "what weight",
]
# Keywords that signal a research/data page opportunity
RESEARCH_SIGNALS = [
    "study", "research", "data", "statistics", "evidence", "science",
    "proven", "does it work", "effective", "percentage", "average",
    "how many people", "survey",
]
# Pillar question starters (broad definitional questions)
PILLAR_STARTERS = [
    "what is", "what are", "how does", "how do", "why is", "why does",
]
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _load_json(path: Path):
    with path.open() as fh:
        return json.load(fh)
def _cluster_score(text: str, cluster: dict) -> float:
    lower = text.lower()
    kws = cluster.get("keywords", {})
    primary   = [k.lower() for k in kws.get("primary", [])]
    secondary = [k.lower() for k in kws.get("secondary", [])]
    negative  = [k.lower() for k in kws.get("negative", [])]
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
def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:80].strip("-")
# ---------------------------------------------------------------------------
# Content type classifier
# ---------------------------------------------------------------------------
def _classify_content_type(q: dict) -> str:
    """
    Classify a question as: pillar_article, article, tool, research, programmatic.
    Uses deterministic rule-based logic — no ML.
    """
    text       = q.get("text", "").lower()
    score      = q.get("scores", {}).get("composite", 0)
    wc         = q.get("word_count", 0)
    source     = q.get("source", "")
    qtype      = q.get("question_type", "other")
    is_question = q.get("is_question", False)
    # Tool: question asks for a calculation or specific number
    for signal in TOOL_SIGNALS:
        if signal in text:
            return "tool"
    # Research: question references studies, data, evidence
    for signal in RESEARCH_SIGNALS:
        if signal in text:
            return "research"
    # Pillar: broad definitional question, high score
    if score >= PILLAR_MIN_SCORE and is_question:
        for starter in PILLAR_STARTERS:
            if text.startswith(starter):
                return "pillar_article"
    # Programmatic: autosuggest fragment, short, not a question
    if source == "autosuggest" and not is_question and wc <= 6:
        return "programmatic"
    return "article"
# ---------------------------------------------------------------------------
# Pillar selection (per cluster)
# ---------------------------------------------------------------------------
def _select_pillars(questions: list[dict]) -> list[dict]:
    """
    Return up to MAX_PILLARS_PER_CLUSTER pillar questions from a cluster.
    Prefer: highest composite score among pillar_article typed questions.
    Fallback: broadest "what is / how does" question if no pillar_article exists.
    """
    candidates = [
        q for q in questions
        if q.get("content_type") == "pillar_article"
        and q.get("scores", {}).get("composite", 0) >= PILLAR_MIN_SCORE
    ]
    if not candidates:
        # Fallback: find broad definitional questions
        candidates = [
            q for q in questions
            if any(q.get("text", "").lower().startswith(s) for s in PILLAR_STARTERS)
            and q.get("word_count", 99) <= 8
        ]
    candidates.sort(key=lambda x: x.get("scores", {}).get("composite", 0), reverse=True)
    return candidates[:MAX_PILLARS_PER_CLUSTER]
# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------
def _build_graph(classified: list[dict]) -> dict:
    """
    Build question_graph.json with nodes and typed edges.
    Edge types:
      parent_of   — broader question whose keyword set contains the child's
      adjacent_to — same cluster, share ≥1 keyword, neither is parent/child
      variant_of  — Jaccard similarity > 0.75 (near-duplicate kept for linking)
    """
    nodes = []
    for q in classified:
        nodes.append({
            "id":             q.get("id"),
            "text":           q.get("text"),
            "cluster":        q.get("cluster"),
            "content_type":   q.get("content_type", "article"),
            "composite_score": q.get("scores", {}).get("composite", 0),
            "source":         q.get("source"),
        })
    edges = []
    seen_pairs = set()
    # Group by cluster for efficiency
    by_cluster: dict[str, list] = {}
    for q in classified:
        cid = q.get("cluster", "")
        by_cluster.setdefault(cid, []).append(q)
    for cid, qs in by_cluster.items():
        for i, a in enumerate(qs):
            tokens_a = set(a.get("text", "").lower().split())
            wc_a     = a.get("word_count", 99)
            id_a     = a.get("id")
            for b in qs[i + 1:]:
                id_b     = b.get("id")
                tokens_b = set(b.get("text", "").lower().split())
                wc_b     = b.get("word_count", 99)
                pair = tuple(sorted([id_a, id_b]))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                jaccard = _jaccard(a.get("text", ""), b.get("text", ""))
                # Variant: near-duplicate
                if jaccard > 0.75:
                    edges.append({
                        "source": id_a, "target": id_b,
                        "type": "variant_of", "weight": round(jaccard, 3),
                        "cluster": cid,
                    })
                    continue
                intersection = tokens_a & tokens_b
                if not intersection:
                    continue
                # Parent/child: shorter question whose tokens are subset of longer
                if tokens_a < tokens_b and wc_a < wc_b:
                    edges.append({
                        "source": id_a, "target": id_b,
                        "type": "parent_of", "weight": round(len(intersection) / len(tokens_b), 3),
                        "cluster": cid,
                        "shared_tokens": list(intersection)[:5],
                    })
                elif tokens_b < tokens_a and wc_b < wc_a:
                    edges.append({
                        "source": id_b, "target": id_a,
                        "type": "parent_of", "weight": round(len(intersection) / len(tokens_a), 3),
                        "cluster": cid,
                        "shared_tokens": list(intersection)[:5],
                    })
                # Adjacent: same cluster, shared keywords, neither parent/child
                elif len(intersection) >= 1 and jaccard > 0.15:
                    edges.append({
                        "source": id_a, "target": id_b,
                        "type": "adjacent_to", "weight": round(jaccard, 3),
                        "cluster": cid,
                        "shared_tokens": list(intersection)[:5],
                    })
    return {"nodes": nodes, "edges": edges}
# ---------------------------------------------------------------------------
# Cluster manifest builder
# ---------------------------------------------------------------------------
def _build_cluster_manifest(clusters_out: dict, clusters_meta: list) -> dict:
    manifest_clusters = []
    for c in clusters_meta:
        cid  = c["id"]
        data = clusters_out.get(cid, {})
        qs   = data.get("top_questions", [])
        pillars     = [q for q in qs if q.get("content_type") == "pillar_article"]
        supporting  = [q for q in qs if q.get("content_type") == "article"]
        tools       = [q for q in qs if q.get("content_type") == "tool"]
        research    = [q for q in qs if q.get("content_type") == "research"]
        programmatic = [q for q in qs if q.get("content_type") == "programmatic"]
        pillar_q    = pillars[0] if pillars else None
        manifest_clusters.append({
            "id":               cid,
            "name":             c.get("name"),
            "pillar_question":  pillar_q.get("text") if pillar_q else None,
            "pillar_slug":      _slugify(pillar_q.get("text", "")) if pillar_q else None,
            "total_questions":  len(qs),
            "pillar_count":     len(pillars),
            "supporting_count": len(supporting),
            "tool_count":       len(tools),
            "research_count":   len(research),
            "programmatic_count": len(programmatic),
            "top_pillar_score": pillar_q.get("scores", {}).get("composite", 0) if pillar_q else 0,
            "questions": {
                "pillar":       [{"id": q["id"], "text": q["text"], "score": q.get("scores", {}).get("composite", 0)} for q in pillars],
                "supporting":   [{"id": q["id"], "text": q["text"], "score": q.get("scores", {}).get("composite", 0)} for q in supporting[:10]],
                "tool":         [{"id": q["id"], "text": q["text"], "score": q.get("scores", {}).get("composite", 0)} for q in tools],
                "research":     [{"id": q["id"], "text": q["text"], "score": q.get("scores", {}).get("composite", 0)} for q in research],
            },
        })
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "clusters": manifest_clusters,
    }
# ---------------------------------------------------------------------------
# Pillar page specs builder
# ---------------------------------------------------------------------------
def _build_pillar_specs(clusters_out: dict, clusters_meta: list) -> list[dict]:
    specs = []
    for c in clusters_meta:
        cid = c["id"]
        qs  = clusters_out.get(cid, {}).get("top_questions", [])
        pillars = [q for q in qs if q.get("content_type") == "pillar_article"]
        if not pillars:
            continue
        supporting = [q for q in qs if q.get("content_type") == "article"]
        tools      = [q for q in qs if q.get("content_type") == "tool"]
        for pillar in pillars:
            text = pillar.get("text", "")
            specs.append({
                "slug":              _slugify(text),
                "cluster":           cid,
                "cluster_name":      c.get("name"),
                "h1":                text.rstrip("?"),
                "question_id":       pillar.get("id"),
                "composite_score":   pillar.get("scores", {}).get("composite", 0),
                "target_word_count": 2500,
                "suggested_sections": _suggest_sections(text, supporting),
                "child_questions":   [q.get("text") for q in supporting[:8]],
                "tool_ctas":         [q.get("text") for q in tools[:2]],
                "internal_links_to": [_slugify(q.get("text", "")) for q in supporting[:5]],
            })
    return specs
def _suggest_sections(pillar_text: str, supporting: list[dict]) -> list[str]:
    """Generate suggested H2 sections for a pillar page from supporting questions."""
    sections = []
    seen = set()
    for q in supporting[:6]:
        t = q.get("text", "").strip().rstrip("?")
        if t and t.lower() not in seen:
            sections.append(t)
            seen.add(t.lower())
    # Ensure a definition section always appears first
    if not any("what" in s.lower() for s in sections):
        sections.insert(0, f"What is {pillar_text.lower().replace('what is', '').strip()}")
    return sections[:6]
# ---------------------------------------------------------------------------
# Tool opportunities builder
# ---------------------------------------------------------------------------
def _build_tool_opportunities(clusters_out: dict, clusters_meta: list) -> list[dict]:
    tools = []
    for c in clusters_meta:
        cid = c["id"]
        qs  = clusters_out.get(cid, {}).get("top_questions", [])
        tool_qs = [q for q in qs if q.get("content_type") == "tool"]
        for q in tool_qs:
            text  = q.get("text", "")
            score = q.get("scores", {}).get("composite", 0)
            if score < TOOL_MIN_SCORE:
                continue
            # Find adjacent questions that reinforce the tool need
            adjacent = [
                other.get("text") for other in qs
                if other.get("id") != q.get("id")
                and _jaccard(text, other.get("text", "")) > 0.1
            ][:5]
            tools.append({
                "trigger_question":     text,
                "trigger_question_id":  q.get("id"),
                "cluster":              cid,
                "cluster_name":         c.get("name"),
                "suggested_tool_name":  _suggest_tool_name(text),
                "slug":                 _slugify(_suggest_tool_name(text)),
                "priority_score":       score,
                "supporting_questions": adjacent,
                "status":               "idea",
            })
    tools.sort(key=lambda x: x["priority_score"], reverse=True)
    return tools
def _suggest_tool_name(question: str) -> str:
    """Derive a tool name from a question."""
    q = question.lower().rstrip("?")
    replacements = [
        ("what should my ", ""), ("how much ", ""), ("how long should ",  ""),
        ("what is my ", ""), ("what heart rate is ", ""), ("calculate ", ""),
        ("how do i calculate ", ""), ("how fast should ", ""),
    ]
    for old, new in replacements:
        q = q.replace(old, new)
    return q.strip().title() + " Calculator"
# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    scored_path   = DATA_DIR / "scored_questions.json"
    taxonomy_path = SHARED_DIR / "taxonomy.json"
    for p in (scored_path, taxonomy_path):
        if not p.exists():
            print(f"[cluster] ERROR: {p} not found.")
            sys.exit(1)
    questions: list[dict]  = _load_json(scored_path)
    taxonomy: dict         = _load_json(taxonomy_path)
    clusters_meta: list    = taxonomy.get("clusters", [])
    # ------------------------------------------------------------------
    # Stage 1: Assign clusters + classify content type
    # ------------------------------------------------------------------
    classified:   list[dict] = []
    unclassified: list[dict] = []
    for q in questions:
        text = q.get("text", "")
        best_id    = None
        best_score = 0.0
        for cluster in clusters_meta:
            s = _cluster_score(text, cluster)
            if s > best_score:
                best_score = s
                best_id    = cluster["id"]
        q = dict(q)
        q["content_type"] = _classify_content_type(q)
        if best_score >= CLUSTER_THRESHOLD and best_id:
            q["cluster"]            = best_id
            q["cluster_confidence"] = round(best_score, 4)
            classified.append(q)
        else:
            q["cluster"]            = None
            q["cluster_confidence"] = round(best_score, 4)
            unclassified.append(q)
    # ------------------------------------------------------------------
    # Stage 2: Build cluster buckets + select pillars
    # ------------------------------------------------------------------
    cluster_buckets: dict[str, list] = {c["id"]: [] for c in clusters_meta}
    for q in classified:
        cid = q["cluster"]
        if cid in cluster_buckets:
            cluster_buckets[cid].append(q)
    clusters_out: dict = {}
    for c in clusters_meta:
        cid = c["id"]
        qs  = sorted(
            cluster_buckets.get(cid, []),
            key=lambda x: x.get("scores", {}).get("composite", 0),
            reverse=True,
        )
        # Upgrade pillar_article classification based on cluster context
        pillars = _select_pillars(qs)
        pillar_ids = {p["id"] for p in pillars}
        for q in qs:
            if q["id"] in pillar_ids:
                q["content_type"] = "pillar_article"
        ct_split = {"article": 0, "programmatic": 0, "tool": 0,
                    "research": 0, "pillar_article": 0}
        for q in qs:
            ct = q.get("content_type", "article")
            ct_split[ct] = ct_split.get(ct, 0) + 1
        clusters_out[cid] = {
            "name":                c["name"],
            "question_count":      len(qs),
            "top_questions":       qs,
            "content_type_split":  ct_split,
        }
    # ------------------------------------------------------------------
    # Stage 3: Write core outputs
    # ------------------------------------------------------------------
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    clustered_output = {
        "generated_at":   generated_at,
        "total_questions": len(classified),
        "clusters":        clusters_out,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with (DATA_DIR / "clustered_questions.json").open("w") as fh:
        json.dump(clustered_output, fh, indent=2)
    with (DATA_DIR / "unclassified.json").open("w") as fh:
        json.dump(unclassified, fh, indent=2)
    # ------------------------------------------------------------------
    # Stage 4: Build graph
    # ------------------------------------------------------------------
    graph = _build_graph(classified)
    with (DATA_DIR / "question_graph.json").open("w") as fh:
        json.dump(graph, fh, indent=2)
    # ------------------------------------------------------------------
    # Stage 5: Build shared Phase 2 outputs
    # ------------------------------------------------------------------
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    cluster_manifest = _build_cluster_manifest(clusters_out, clusters_meta)
    with (SHARED_DIR / "cluster_manifest.json").open("w") as fh:
        json.dump(cluster_manifest, fh, indent=2)
    pillar_specs = _build_pillar_specs(clusters_out, clusters_meta)
    with (SHARED_DIR / "pillar_page_specs.json").open("w") as fh:
        json.dump(pillar_specs, fh, indent=2)
    tool_opps = _build_tool_opportunities(clusters_out, clusters_meta)
    with (SHARED_DIR / "tool_opportunities.json").open("w") as fh:
        json.dump(tool_opps, fh, indent=2)
    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    total        = len(questions)
    n_classified = len(classified)
    n_unclassified = len(unclassified)
    unc_rate     = f"{round(n_unclassified / total * 100, 1)}%" if total else "0%"
    print(f"[cluster] Done. {n_classified} classified, {n_unclassified} unclassified ({unc_rate})")
    by_cluster = {cid: len(qs) for cid, qs in cluster_buckets.items()}
    for cid, cnt in by_cluster.items():
        print(f"          {cid}: {cnt}")
    n_pillars = sum(1 for q in classified if q.get("content_type") == "pillar_article")
    n_tools   = sum(1 for q in classified if q.get("content_type") == "tool")
    n_research = sum(1 for q in classified if q.get("content_type") == "research")
    print(f"[cluster] Content types — pillars: {n_pillars}, tools: {n_tools}, research: {n_research}")
    print(f"[cluster] Graph — {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")
    print(f"[cluster] Pillar specs: {len(pillar_specs)} | Tool opportunities: {len(tool_opps)}")
    # Update harvest report
    report_path = DATA_DIR / "harvest_report.json"
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text())
            report["clustering"] = {
                "classified":        n_classified,
                "unclassified":      n_unclassified,
                "unclassified_rate": unc_rate,
                "by_cluster":        by_cluster,
                "pillar_articles":   n_pillars,
                "tool_opportunities": n_tools,
                "research_pages":    n_research,
            }
            with report_path.open("w") as fh:
                json.dump(report, fh, indent=2)
        except Exception as exc:
            print(f"[cluster] WARNING: could not update harvest_report.json — {exc}")
if __name__ == "__main__":
    main()
