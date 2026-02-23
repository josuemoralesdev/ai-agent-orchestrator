import time
from typing import Callable, TypeVar

T = TypeVar("T")


def with_retries(
    fn: Callable[[], T],
    *,
    retries: int = 2,
    backoff_seconds: float = 0.3,
) -> T:
    """
    Minimal retry helper: retries N times with linear backoff.
    Designed to be simple and predictable.
    """
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            if attempt < retries:
                time.sleep(backoff_seconds * (attempt + 1))
            else:
                raise last_exc
    raise last_exc  # unreachable