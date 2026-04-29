from __future__ import annotations

import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock

from fastapi import Request


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    name: str
    path: str
    method: str
    limit: int
    window_seconds: int


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    policy_name: str
    limit: int
    remaining: int
    retry_after_seconds: int


class InMemoryRateLimiter:
    def __init__(self, policies: list[RateLimitPolicy]) -> None:
        self._policies = tuple(policies)
        self._windows: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, request: Request) -> RateLimitDecision | None:
        policy = self._matching_policy(request)
        if policy is None:
            return None

        client_key = _client_key(request)
        bucket = (policy.name, client_key)
        now = time.monotonic()

        with self._lock:
            timestamps = self._windows[bucket]
            cutoff = now - policy.window_seconds
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            if len(timestamps) >= policy.limit:
                retry_after = max(1, math.ceil(policy.window_seconds - (now - timestamps[0])))
                return RateLimitDecision(
                    policy_name=policy.name,
                    limit=policy.limit,
                    remaining=0,
                    retry_after_seconds=retry_after,
                )

            timestamps.append(now)
            remaining = max(0, policy.limit - len(timestamps))
            return RateLimitDecision(
                policy_name=policy.name,
                limit=policy.limit,
                remaining=remaining,
                retry_after_seconds=0,
            )

    def _matching_policy(self, request: Request) -> RateLimitPolicy | None:
        path = request.url.path
        method = request.method.upper()
        for policy in self._policies:
            if policy.method == method and policy.path == path:
                return policy
        return None


def _client_key(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        first_hop = forwarded_for.split(",")[0].strip()
        if first_hop:
            return first_hop
    if request.client and request.client.host:
        return request.client.host
    return "unknown"
