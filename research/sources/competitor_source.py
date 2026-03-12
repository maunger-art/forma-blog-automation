"""Competitor source — scrapes blog post titles from competitor sites."""

import requests
from bs4 import BeautifulSoup
from .base_source import BaseSource

MAX_PER_SITE = 50
MIN_TITLE_LEN = 15

SELECTORS = ["h2 a", "h3 a", ".post-title a", "article a"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


class CompetitorSource(BaseSource):
    cache_ttl_days = 30
    rate_limit_seconds = 3.0
    source_name = "competitor"

    def _iter_targets(self, config: dict):
        for site in config.get("competitor_sites", []):
            yield site["url"], {"name": site["name"], "url": site["url"]}

    def _fetch_target(self, target: str, name: str, url: str, **_) -> list[dict]:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            titles = []
            for selector in SELECTORS:
                try:
                    for el in soup.select(selector):
                        text = el.get_text(strip=True)
                        if len(text) >= MIN_TITLE_LEN and text not in titles:
                            titles.append(text)
                        if len(titles) >= MAX_PER_SITE:
                            break
                except Exception:
                    continue
                if len(titles) >= MAX_PER_SITE:
                    break

            results = []
            for title in titles[:MAX_PER_SITE]:
                results.append({
                    "text": title,
                    "source": "competitor",
                    "source_detail": name,
                    "engagement": {},
                    "raw_url": url,
                })
            return results
        except Exception as exc:
            print(f"[competitor] WARNING: failed for '{name}' — {exc}")
            return []
