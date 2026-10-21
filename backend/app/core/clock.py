"""A single source of "now" so tests and simulations can move time deterministically.

All application code calls ``clock.utcnow()`` instead of ``datetime.now()``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

_override: datetime | None = None


def utcnow() -> datetime:
    return _override if _override is not None else datetime.now(UTC)


def set_now(value: datetime | None) -> None:
    global _override
    if value is not None and value.tzinfo is None:
        raise ValueError("clock.set_now requires a timezone-aware datetime")
    _override = value


def advance(delta: timedelta) -> datetime:
    """Move a frozen clock forward (freezing it at the current time first if needed)."""
    set_now(utcnow() + delta)
    return utcnow()


@contextmanager
def frozen(at: datetime) -> Iterator[None]:
    previous = _override
    set_now(at)
    try:
        yield
    finally:
        set_now(previous)
