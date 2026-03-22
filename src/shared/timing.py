"""Small timing helpers for debugging latency."""

import time
from contextlib import contextmanager
from typing import Iterator


def now() -> float:
    """Return a monotonic timestamp."""
    return time.perf_counter()


def elapsed_ms(start: float) -> float:
    """Return elapsed milliseconds from a monotonic start time."""
    return (time.perf_counter() - start) * 1000.0


@contextmanager
def timed(label: str) -> Iterator[None]:
    """Print elapsed milliseconds for a block."""
    start = now()
    try:
        yield
    finally:
        print("[timing] {} took {:.1f}ms".format(label, elapsed_ms(start)))
