"""Autosuggest source — Google autocomplete suggestions."""

import json
import requests
from .base_source import BaseSource


NOISE_TERMS = ["roblox", "cricket", "studio", "minecraft"]


class AutosuggestSource(BaseSource):
    cache_ttl_days = 14
    rate_limit_seconds = 1.5
    source_name = "autosuggest"

    def _iter_targets(self, config: dict):
        for term in config.get("seed_terms", []):
            yield term, {"term": term}

    def _fetch_target(self, target: str, term: str, **_) -> list[dict]:
        url = (
            "https://suggestqueries.google.com/complete/search"
            f"?client=firefox&q={requests.utils.quote(term)}&hl=en"
        )
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()

        # Response is JSON array: [query, [suggestions, ...]]
        data = json.loads(resp.text)
        suggestions = data[1] if len(data) > 1 else []

        results = []
        for suggestion in suggestions:
            suggestion = suggestion.strip()
            if any(noise in suggestion.lower() for noise in NOISE_TERMS):
                continue
            if len(suggestion.split()) >= 4:
                results.append({
                    "text": suggestion,
                    "source": "autosuggest",
                    "source_detail": f"google:{term}",
                    "engagement": {},
                    "raw_url": "",
                })
        return results
