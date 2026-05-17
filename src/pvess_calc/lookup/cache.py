"""On-disk JSON cache for lookup results.

Stored under `~/.pvess/cache/lookup/<sha256(key)>.json`. Each entry has
a `timestamp` (unix seconds) and a `value` (the cached payload). The
default TTL is 24 hours — long enough that re-running the wizard for the
same site is free, short enough that a corrected dataset propagates the
next day.

The cache is deliberately filesystem-only (no SQLite, no Redis). The
volume is tiny (≪ 10 KB per address), and a JSON file is debuggable —
the user can `cat` an entry to see exactly what we returned.

Tests override the cache root via `PVESS_CACHE_ROOT` env var to keep
real ~/.pvess clean.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Optional


DEFAULT_TTL_SECONDS: int = 24 * 3600    # 24h
_ENV_CACHE_ROOT = "PVESS_CACHE_ROOT"


def cache_root() -> Path:
    """Resolve the cache directory. Honours PVESS_CACHE_ROOT (used by
    tests / CI to keep the real ~/.pvess untouched)."""
    override = os.environ.get(_ENV_CACHE_ROOT)
    if override:
        return Path(override) / "lookup"
    return Path.home() / ".pvess" / "cache" / "lookup"


def _key_to_path(key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return cache_root() / f"{digest}.json"


def get(key: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> Optional[Any]:
    """Return the cached value for `key` if it exists and is fresher
    than `ttl_seconds`; else `None`."""
    path = _key_to_path(key)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        ts = float(payload.get("timestamp", 0))
        if time.time() - ts > ttl_seconds:
            return None
        return payload.get("value")
    except (json.JSONDecodeError, OSError, ValueError):
        # Corrupt entry — treat as a miss and let the caller refresh.
        return None


def put(key: str, value: Any) -> None:
    """Write `value` to the cache. Creates parent dirs as needed."""
    path = _key_to_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"timestamp": time.time(), "value": value, "key_hint": key[:80]}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def clear() -> int:
    """Delete every cached entry. Returns the count removed.
    Used by tests + a future `pvess-lookup --clear-cache` flag."""
    root = cache_root()
    if not root.exists():
        return 0
    n = 0
    for f in root.glob("*.json"):
        try:
            f.unlink()
            n += 1
        except OSError:
            pass
    return n
