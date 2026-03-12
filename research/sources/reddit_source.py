"""Reddit source — fetches top questions via Arctic Shift API."""

import re
import time
import requests
from urllib.parse import quote
from .base_source import BaseSource

QUESTION_RE = re.compile(
    r"^(why|what|how|is|should|can|does|do|will|when|which|who)\b",
    re.IGNORECASE,
)


class RedditSource(BaseSource):
    cache_ttl_days = 7
    rate_limit_seconds = 2.0
    source_name = "arctic-shift"

    def _iter_targets(self, config: dict):
        for sub in config.get("subreddits", []):
            for term in config.get("seed_terms", []):
                yield f"{sub}::{term}", {}

    def _fetch_target(self, target: str, **kwargs) -> list[dict]:
        sub, term = target.split("::", 1)
        one_year_ago = int(time.time()) - (365 * 24 * 60 * 60)
        url = (
            f"https://arctic-shift.photon-reddit.com/api/posts/search"
            f"?q={quote(term)}&subreddit={sub}&limit=100&sort=top&after={one_year_ago}"
        )
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return self._parse(resp.json(), sub)

    def _parse(self, data: dict, sub: str) -> list[dict]:
        results = []
        for p in data.get("data", []):
            title = p.get("title", "").strip()
            score = p.get("score", 0)
            if score < 5:
                continue
            if not QUESTION_RE.match(title):
                continue
            results.append({
                "text": title,
                "source": "reddit",
                "source_detail": f"r/{sub}",
                "engagement": {
                    "upvotes": score,
                    "comments": p.get("num_comments", 0),
                },
                "raw_url": f"https://reddit.com{p.get('permalink', '')}",
            })
        return results
