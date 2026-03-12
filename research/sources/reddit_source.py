"""Reddit source — fetches top questions via PullPush API."""

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
    source_name = "reddit"

    def _iter_targets(self, config: dict):
        """Yield (cache_key, kwargs) pairs matching base class contract."""
        for sub in config.get("subreddits", []):
            for term in config.get("seed_terms", []):
                target = f"{sub}::{term}"
                yield target, {"sub": sub, "term": term}

    def _fetch_target(self, target: str, sub: str = "", term: str = "") -> list[dict]:
        one_year_ago = int(time.time()) - (365 * 24 * 60 * 60)
        url = (
            f"https://api.pullpush.io/reddit/search/submission/"
            f"?q={quote(term)}&subreddit={sub}&size=100&sort=score&after={one_year_ago}"
        )
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        results = []
        for p in resp.json().get("data", []):
            title = p.get("title", "").strip()
            score = p.get("score", 0)
            if score < 2:
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
