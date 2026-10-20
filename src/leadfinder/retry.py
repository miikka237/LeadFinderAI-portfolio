"""Small, explicit retry helper for external API calls.

Only transient failures (timeouts, connection problems, HTTP 5xx) are
retried. Permanent failures (invalid API key, quota exhausted, bad
request) fail immediately, because retrying would only waste paid calls.
"""

import time
from typing import Callable, Sequence, TypeVar

T = TypeVar("T")


class TransientError(Exception):
    """A failure that may succeed if tried again shortly."""


class PermanentError(Exception):
    """A failure that will not be fixed by retrying."""


def call_with_retry(
    fn: Callable[[], T],
    backoff_seconds: Sequence[float] = (0.5, 1.0),
    sleep: Callable[[float], None] = time.sleep,
    on_retry: Callable[[int, Exception], None] = None,
) -> T:
    """Call fn(); on TransientError, wait and retry once per backoff entry.

    Any other exception is raised immediately. If every attempt fails,
    the last TransientError is re-raised.
    """
    attempt = 0
    while True:
        try:
            return fn()
        except TransientError as exc:
            if attempt >= len(backoff_seconds):
                raise
            if on_retry:
                on_retry(attempt + 1, exc)
            sleep(backoff_seconds[attempt])
            attempt += 1
