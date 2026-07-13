from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


PRIMARY_WINDOW_SECONDS = 5 * 60 * 60
SECONDARY_WINDOW_SECONDS = 7 * 24 * 60 * 60
PRIMARY_SCORE_WEIGHT = 0.62
SECONDARY_SCORE_WEIGHT = 0.38
UNKNOWN_EFFECTIVE_REMAINING = 50.0
UNKNOWN_RESET_AT = 2**63 - 1


@dataclass
class AccountStatus:
    alias: str
    scope: str
    email: str | None
    plan: str | None
    primary_used: int | None
    primary_reset: str | None
    primary_reset_at: int | None
    secondary_used: int | None
    secondary_reset: str | None
    secondary_reset_at: int | None
    error: str | None = None
    primary_window_minutes: int | None = None
    secondary_window_minutes: int | None = None


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def reset_proximity(reset_at: int | None, window_seconds: int, now: int) -> float:
    if reset_at is None:
        return 0.0
    seconds_until_reset = max(0, reset_at - now)
    return clamp(1 - (seconds_until_reset / window_seconds), 0.0, 1.0)


def effective_remaining(used_percent: int | None, reset_at: int | None, window_seconds: int, now: int) -> float:
    if used_percent is None:
        return UNKNOWN_EFFECTIVE_REMAINING
    remaining = clamp(100 - used_percent, 0.0, 100.0)
    refill = 100 - remaining
    return remaining + refill * reset_proximity(reset_at, window_seconds, now)


def is_blocked(used_percent: int | None) -> bool:
    return used_percent is not None and used_percent >= 100


def account_status_blocked(status: AccountStatus) -> bool:
    return is_blocked(status.primary_used) or is_blocked(status.secondary_used)


def blocked_until(status: AccountStatus, now: int) -> int:
    reset_times: list[int] = []
    if is_blocked(status.primary_used):
        reset_times.append(max(now, status.primary_reset_at) if status.primary_reset_at is not None else UNKNOWN_RESET_AT)
    if is_blocked(status.secondary_used):
        reset_times.append(max(now, status.secondary_reset_at) if status.secondary_reset_at is not None else UNKNOWN_RESET_AT)
    return max(reset_times) if reset_times else now


def status_score(status: AccountStatus, now: int) -> float:
    limits: list[tuple[float, float]] = []
    if status.primary_used is not None:
        primary_window = (status.primary_window_minutes or (PRIMARY_WINDOW_SECONDS // 60)) * 60
        limits.append((effective_remaining(status.primary_used, status.primary_reset_at, primary_window, now), PRIMARY_SCORE_WEIGHT))
    if status.secondary_used is not None:
        secondary_window = (status.secondary_window_minutes or (SECONDARY_WINDOW_SECONDS // 60)) * 60
        limits.append((effective_remaining(status.secondary_used, status.secondary_reset_at, secondary_window, now), SECONDARY_SCORE_WEIGHT))
    if not limits:
        return UNKNOWN_EFFECTIVE_REMAINING
    if len(limits) == 1:
        return limits[0][0]
    # Geometric scoring keeps a weak bucket from being hidden by the other bucket.
    return limits[0][0] ** limits[0][1] * limits[1][0] ** limits[1][1]


def status_sort_key(status: AccountStatus, now: int | None = None) -> tuple[Any, ...]:
    if now is None:
        now = int(time.time())
    if status.error:
        return (2, status.alias)

    primary_blocked = is_blocked(status.primary_used)
    secondary_blocked = is_blocked(status.secondary_used)
    blocked_now = primary_blocked or secondary_blocked
    unknown_count = int(status.primary_used is None) + int(status.secondary_used is None)
    personal_penalty = 1 if status.scope == "personal" else 0
    score = status_score(status, now)

    if blocked_now:
        return (
            1,
            blocked_until(status, now),
            personal_penalty,
            -score,
            unknown_count,
            status.alias,
        )

    return (
        0,
        personal_penalty,
        -score,
        unknown_count,
        status.alias,
    )
