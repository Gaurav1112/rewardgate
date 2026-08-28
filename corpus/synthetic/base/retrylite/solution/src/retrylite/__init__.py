"""Exponential backoff delay calculation.

The bug only appears at high attempt numbers: the delay doubles without bound, so a long retry
loop eventually schedules a wait of days. Short test runs never reach it, which is exactly why it
survives review.
"""

from __future__ import annotations

__all__ = ["backoff_delay"]

BASE_DELAY_SECONDS = 1.0
MAX_DELAY_SECONDS = 60.0


def backoff_delay(attempt: int) -> float:
    """Seconds to wait before retry number `attempt` (1-based), capped at `MAX_DELAY_SECONDS`."""
    if attempt < 1:
        raise ValueError("attempt must be >= 1")
    return min(BASE_DELAY_SECONDS * (2 ** (attempt - 1)), MAX_DELAY_SECONDS)
