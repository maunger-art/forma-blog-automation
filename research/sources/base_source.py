"""Abstract base class for all AQE data sources."""

import hashlib
import json
import os
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = REPO_ROOT / "research" / "cache"


class BaseSource(ABC):
    """Abstract base for all question sources.

    Subclasses must define:
        cache_ttl_days: int
        rate_limit_seconds: float
        source_name: str
    """

    cache_ttl_days: int = 7
    rate_limit_seconds: float = 1.0
    source_name: str = "base"

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def fetch(self, config: dict) -> list[dict]:
        """Fetch questions, using cache where valid. Never raises."""
        try:
            return self._fetch_with_cache(config)
        except Exception as exc:
            print(f"[{self.source_name}] WARNING: fetch failed — {exc}")
            return []

    # ------------------------------------------------------------------
    # Abstract inner fetch — subclasses implement this
    # ------------------------------------------------------------------

    @abstractmethod
    def _do_fetch(self, config: dict) -> list[dict]:
        """Perform the actual network fetch. Returns list of raw dicts."""

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _cache_key(self, target: str) -> str:
        return hashlib.md5(target.encode()).hexdigest()

    def _cache_path(self, target: str) -> Path:
        key = self._cache_key(target)
        source_cache = CACHE_DIR / self.source_name
        source_cache.mkdir(parents=True, exist_ok=True)
        return source_cache / f"{key}.json"

    def _load_cache(self, target: str) -> list[dict] | None:
        """Return cached payload if still valid, else None."""
        path = self._cache_path(target)
        if not path.exists():
            return None
        try:
            with path.open() as fh:
                data = json.load(fh)
            cached_at = datetime.fromisoformat(data["cached_at"])
            age = datetime.now(timezone.utc) - cached_at
            if age < timedelta(days=self.cache_ttl_days):
                return data["payload"]
        except Exception:
            pass
        return None

    def _save_cache(self, target: str, payload: list[dict]) -> None:
        """Write payload to cache."""
        path = self._cache_path(target)
        try:
            with path.open("w") as fh:
                json.dump(
                    {
                        "cached_at": datetime.now(timezone.utc).isoformat(),
                        "payload": payload,
                    },
                    fh,
                    indent=2,
                )
        except Exception as exc:
            print(f"[{self.source_name}] WARNING: cache write failed — {exc}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_with_cache(self, config: dict) -> list[dict]:
        results: list[dict] = []
        items = self._iter_targets(config)
        for i, (target, kwargs) in enumerate(items):
            cached = self._load_cache(target)
            if cached is not None:
                results.extend(cached)
                continue
            if i > 0:
                time.sleep(self.rate_limit_seconds)
            try:
                fresh = self._fetch_target(target, **kwargs)
            except Exception as exc:
                print(f"[{self.source_name}] WARNING: target '{target}' failed — {exc}")
                fresh = []
            self._save_cache(target, fresh)
            results.extend(fresh)
        return results

    def _iter_targets(self, config: dict):
        """Yield (cache_key, kwargs) pairs. Override in subclasses."""
        return []

    def _fetch_target(self, target: str, **kwargs) -> list[dict]:
        """Fetch a single target. Override in subclasses."""
        return []
