"""PAA (People Also Ask) source — fetches via SerpAPI."""

import os
import requests
from .base_source import BaseSource

MAX_SEED_TERMS = 15
MAX_PER_TERM = 8


class PAASource(BaseSource):
    cache_ttl_days = 14
    rate_limit_seconds = 2.0
    source_name = "paa"

    def _iter_targets(self, config: dict):
        seed_terms = config.get("seed_terms", [])[:MAX_SEED_TERMS]
        for term in seed_terms:
            yield term, {"term": term}

    def _fetch_target(self, target: str, term: str = "", **_) -> list[dict]:
        api_key = os.environ.get("SERPAPI_KEY", "")
        if not api_key:
            print("[paa] WARNING: SERPAPI_KEY not set — skipping")
            return []

        params = {
            "engine": "google",
            "q": term,
            "api_key": api_key,
            "hl": "en",
            "gl": "gb",
            "num": 10,
        }

        try:
            resp = requests.get(
                "https://serpapi.com/search",
                params=params,
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            print(f"[paa] WARNING: request failed for '{term}' — {exc}")
            return []

        results = []
        for item in data.get("related_questions", [])[:MAX_PER_TERM]:
            question = item.get("question", "").strip()
            if not question:
                continue
            results.append({
                "text": question,
                "source": "paa",
                "source_detail": f"google-paa:{term}",
                "engagement": {},
                "raw_url": "",
            })

        if not results:
            print(f"[paa] WARNING: no PAA results for '{term}' — check API key or query")

        return results
