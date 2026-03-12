"""PAA (People Also Ask) source — scrapes Google SERP PAA boxes."""

import requests
from bs4 import BeautifulSoup
from .base_source import BaseSource

MAX_SEED_TERMS = 15
MAX_PER_TERM = 8

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}


class PAASource(BaseSource):
    cache_ttl_days = 14
    rate_limit_seconds = 4.0
    source_name = "paa"

    def _iter_targets(self, config: dict):
        seed_terms = config.get("seed_terms", [])[:MAX_SEED_TERMS]
        for term in seed_terms:
            yield term, {"term": term}

    def _fetch_target(self, target: str, term: str, **_) -> list[dict]:
        try:
            url = f"https://www.google.com/search?q={requests.utils.quote(term)}&hl=en&gl=gb"
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            questions = []

            # Primary selector: div[data-q]
            try:
                for el in soup.select("div[data-q]"):
                    q = el.get("data-q", "").strip()
                    if q:
                        questions.append(q)
            except Exception:
                pass

            # Fallback selectors if primary found nothing
            if not questions:
                try:
                    for el in soup.select("div[jsname] span"):
                        text = el.get_text(strip=True)
                        if text.endswith("?") and len(text.split()) >= 4:
                            questions.append(text)
                except Exception:
                    pass

            results = []
            for q in questions[:MAX_PER_TERM]:
                results.append({
                    "text": q,
                    "source": "paa",
                    "source_detail": f"google-paa:{term}",
                    "engagement": {},
                    "raw_url": "",
                })
            return results
        except Exception as exc:
            print(f"[paa] WARNING: failed for '{term}' — {exc}")
            return []
