"""
A private cache of delivery responses, honouring `Cache-Control` and `ETag`.

Private is what makes it allowed: the client holds the key, so it may keep keyed responses
that a shared cache must not. A tag named directly is `immutable` for a year and is fetched
once. An environment is fresh for its short `max-age`, then revalidated with
`If-None-Match`, which costs a `304` rather than a body when nothing was promoted.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass


@dataclass(frozen=True)
class Cached:
    body: bytes
    """The body as it arrived. Each read parses its own copy, so no caller can change another's."""

    etag: str | None

    fresh_until: float
    """Until when, in seconds since the epoch, the body may be used without asking."""


class ResponseCache:
    """Bounded, least recently used out first. Safe to share between threads."""

    def __init__(self, max_entries: int):
        self._max_entries = max_entries
        self._entries: OrderedDict[str, Cached] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, url: str) -> Cached | None:
        with self._lock:
            cached = self._entries.get(url)
            if cached is not None:
                self._entries.move_to_end(url)
            return cached

    def set(self, url: str, cached: Cached) -> None:
        with self._lock:
            self._entries[url] = cached
            self._entries.move_to_end(url)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def delete(self, url: str) -> None:
        with self._lock:
            self._entries.pop(url, None)


def fresh_until(cache_control: str | None, now: float) -> float | None:
    """
    Until when a response may be used without asking, from its `Cache-Control`, or None when
    it must not be stored at all. A response that makes no claim is stale at once, so it is
    only ever reused after a `304`.
    """
    no_store = False
    no_cache = False
    max_age: int | None = None
    for directive in (cache_control or "").split(","):
        name, _, value = directive.strip().lower().partition("=")
        if name == "no-store":
            no_store = True
        elif name == "no-cache":
            no_cache = True
        elif name == "max-age" and value.isdigit():
            max_age = int(value)

    if no_store:
        return None
    if no_cache or max_age is None:
        return now
    return now + max_age


def now() -> float:
    return time.time()
