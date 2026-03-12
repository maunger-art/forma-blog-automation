"""Reddit source — fetches top questions from target subreddits."""

import re
import time
import requests
from .base_source import BaseSource

QUESTION_RE = re.compile(
    r"^(why|what|how|is|should|can|does|do|will|when|which|who)\b",
    re.IGNORECASE,
)

USER_AGENT = "Forma-AQE/1.0 contact:tech@formafit.co.uk"


class RedditSource(BaseSource):
    cache_ttl_days = 7
    rate_limit_seconds = 2.0
    source_name = "reddit"

    # Each (subreddit, term) pair is a target
    def _iter_targets(self, config: dict):
        subreddits = config.get("subreddits", [])
        seed_terms = config.get("seed_terms", [])
        for sub in subreddits:
            for term in seed_terms:
                target = f"{sub}::{term}"
                yield target, {"sub": sub, "term": term}

    def _fetch_target(self, target: str, sub: str, term: str, **_) -> list[dict]:
        url = (
            f"https://www.reddit.com/r/{sub}/search.json"
            f"?q={requests.utils.quote(term)}&sort=top&t=year&limit=100&restrict_sr=1"
        )
        headers = {"User-Agent": USER_AGENT}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for post in data.get("data", {}).get("children", []):
            p = post.get("data", {})
            title: str = p.get("title", "").strip()
            score: int = p.get("score", 0)
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
