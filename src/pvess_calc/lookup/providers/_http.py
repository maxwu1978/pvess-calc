"""Shared HTTP layer for online lookup providers.

Every online provider goes through `http_get_json()` so we get one
consistent place for:
  * timeout (default 5s — small enough that a wizard run never blocks
    perceptibly, large enough for a healthy API)
  * exception → `ProviderError` mapping (the orchestrator already
    catches Exception, but we still want stable error types in case
    callers want fine-grained handling)
  * response shape sanity (HTTP 200 + parseable JSON)

Test strategy: providers call this function; tests use the `responses`
library to stub HTTP at the `requests` layer. No real network in CI.
"""
from __future__ import annotations

from typing import Any, Mapping

import requests

from ..config import DEFAULT_HTTP_TIMEOUT_S


class ProviderError(Exception):
    """Anything that prevents an online provider from returning data —
    timeout, bad status, malformed JSON, missing credential. The
    orchestrator's per-provider try/except converts this (and any other
    Exception) into a 'miss' ProviderResult.
    """


def http_get_json(
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_HTTP_TIMEOUT_S,
) -> dict[str, Any]:
    """GET a JSON-returning endpoint. Raises `ProviderError` on any
    network or shape problem.

    Why no automatic retry: providers are called inside a wizard prompt;
    blocking the user 15s on retries is worse than a graceful miss. If
    a future bulk-resolve path needs retry, layer it OVER this function.
    """
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    except requests.exceptions.Timeout as exc:
        raise ProviderError(f"timeout after {timeout}s: {url}") from exc
    except requests.exceptions.ConnectionError as exc:
        raise ProviderError(f"connection failed: {exc}") from exc
    except requests.exceptions.RequestException as exc:
        raise ProviderError(f"request error: {exc}") from exc

    if resp.status_code >= 400:
        raise ProviderError(
            f"HTTP {resp.status_code} from {url}: {resp.text[:200]}"
        )

    try:
        return resp.json()
    except ValueError as exc:
        raise ProviderError(f"non-JSON response: {exc}") from exc
