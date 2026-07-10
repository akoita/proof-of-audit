"""Authentication and rate-limiting guards for mutating API endpoints.

This module builds a FastAPI dependency that gates the mutating (POST) routes
of the Proof-of-Audit API behind an optional API-key check and an in-process
sliding-window rate limiter.

**Rate-limiter scope caveat:** the limiter is *per process*. Each API worker /
replica keeps its own counters in memory, so a multi-instance deployment (for
example Cloud Run with several containers) enforces the limit per instance, not
globally. Treat this as a coarse abuse brake, not a precise quota. A shared
external limiter (Redis, an API gateway, etc.) is required to enforce a global
limit and should be added when the deployment scales beyond a single instance.
"""

from __future__ import annotations

from collections import deque
import threading
import time
from typing import Callable

from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

API_KEY_HEADER_NAME = "X-API-Key"

_api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)


class _SlidingWindowRateLimiter:
    """Fixed-limit sliding-window rate limiter keyed by caller identity.

    Keeps, per identity, a deque of ``time.monotonic()`` timestamps for calls
    within the trailing ``window_seconds``. Thread-safe via a single lock; the
    state lives only in this process (see the module docstring).
    """

    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self._limit = limit
        self._window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, identity: str) -> float | None:
        """Register a hit for ``identity``.

        Returns ``None`` when the call is allowed, or the number of seconds the
        caller should wait (``Retry-After``) when the limit is exceeded.
        """
        if self._limit <= 0:
            return None
        now = time.monotonic()
        cutoff = now - self._window_seconds
        with self._lock:
            bucket = self._hits.get(identity)
            if bucket is None:
                bucket = deque()
                self._hits[identity] = bucket
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(self._hits) > 10_000:
                # Bound memory against identity-rotation abuse: once the table
                # grows large, drop identities whose entire window is stale.
                stale = [
                    key
                    for key, hits in self._hits.items()
                    if key != identity and (not hits or hits[-1] <= cutoff)
                ]
                for key in stale:
                    del self._hits[key]
            if len(bucket) >= self._limit:
                retry_after = self._window_seconds - (now - bucket[0])
                return max(retry_after, 1.0)
            bucket.append(now)
            return None


def build_mutating_guard(contract_config) -> Callable:
    """Build the async FastAPI dependency guarding mutating endpoints.

    The returned dependency enforces, in order:

    1. **API-key auth** — only when ``contract_config.api_keys`` is non-empty.
       Requires the ``X-API-Key`` header (documented in OpenAPI via
       :class:`APIKeyHeader`); raises 401 when missing, 403 when the value is
       not in the configured set. When no keys are configured the API is open
       (intended for local development only).
    2. **Rate limiting** — an in-process sliding window (60s) per identity
       (the presented API key when present, else ``request.client.host``),
       limited to ``contract_config.mutating_rate_limit_per_minute`` requests.
       A limit of ``0`` disables rate limiting. On breach raises 429 with a
       ``Retry-After`` header.
    """
    api_keys = frozenset(contract_config.api_keys)
    limiter = _SlidingWindowRateLimiter(
        limit=int(contract_config.mutating_rate_limit_per_minute)
    )

    async def guard(
        request: Request,
        api_key: str | None = Security(_api_key_header),
    ) -> None:
        presented = api_key.strip() if isinstance(api_key, str) else None
        if api_keys:
            if not presented:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={
                        "error": "missing_api_key",
                        "message": (
                            f"Missing required {API_KEY_HEADER_NAME} header."
                        ),
                    },
                )
            if presented not in api_keys:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": "invalid_api_key",
                        "message": "The provided API key is not authorized.",
                    },
                )

        if presented:
            identity = f"key:{presented}"
        else:
            client = request.client
            identity = f"ip:{client.host if client is not None else 'unknown'}"

        retry_after = limiter.check(identity)
        if retry_after is not None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "rate_limited",
                    "message": "Rate limit exceeded; retry later.",
                },
                headers={"Retry-After": str(int(retry_after))},
            )

    return guard
