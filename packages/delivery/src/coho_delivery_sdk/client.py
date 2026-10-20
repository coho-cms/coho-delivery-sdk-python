"""The delivery API, untyped: entries come back as the server sends them."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, cast
from urllib.parse import quote

import httpx

from . import cache as caching
from .cache import Cached, ResponseCache
from .errors import CohoDeliveryError
from .types import EntryGraph, EntryList, Problem

TOKEN_PREFIX = "coho_pt_"
"""The project token prefix, by which Coho tells a token from a person's sign-in."""


@dataclass(frozen=True)
class ReleasedConfig:
    """
    Released content: tags, and environments pointing at them, such as `qa` and `prod`, from
    delivery, with a delivery key.
    """

    url: str
    """Where delivery is served, such as `https://delivery.coho.example`."""

    project: str
    """The project id. It selects the project; the key is what authorizes."""

    key: str | None = field(default=None, repr=False)
    """
    A delivery key, sent as `Authorization: Bearer` and never in a URL. Leave it out only for
    an environment the project has opened to keyless reads.
    """


@dataclass(frozen=True)
class PreviewConfig:
    """
    Unreleased content: `dev` and branch heads, read live through Coho with a project token.
    The same answers in the same shapes as delivery, never cached, so a preview runs the code
    production runs.
    """

    url: str
    """Coho's own URL, where you sign in, such as `https://api.coho.example`. Not delivery's."""

    account: str
    """The account the project belongs to."""

    project: str

    token: str = field(repr=False)
    """
    A project token, `coho_pt_…`, with read access to the project: the viewer role is enough.
    It reads everything unreleased, so keep it on the server.
    """

    def __post_init__(self) -> None:
        if not self.token.startswith(TOKEN_PREFIX):
            raise ValueError(f"A Coho preview token is a project token, starting {TOKEN_PREFIX}")


@dataclass(frozen=True)
class MountedConfig:
    """The whole base URL, `…/v1/projects/{project}`, for a mount `url` and `project` cannot express."""

    base_url: str

    key: str | None = field(default=None, repr=False)
    """A delivery key, sent as `Authorization: Bearer` and never in a URL."""


DeliveryConfig = ReleasedConfig | PreviewConfig | MountedConfig

Reads = Literal["released", "preview"]
"""Released content, from delivery; or unreleased, read live through Coho's preview mount."""

Query = Mapping[str, str | int | None]

DEFAULT_CACHE_SIZE = 1000


class _Core:
    """
    What the sync and async clients share: where requests go, what they carry, and what an
    answer means. Only sending differs between the two.
    """

    def __init__(self, config: DeliveryConfig, cache_size: int):
        self.base, self.credential, self.reads = _connection(config)
        self.cache = ResponseCache(cache_size) if cache_size > 0 else None

    def request(self, path: str, query: Query) -> tuple[str, dict[str, str], Cached | None]:
        """The URL, the headers, and what the cache holds for it."""
        url = f"{self.base}{path}{_query_string(query)}"
        cached = self.cache.get(url) if self.cache is not None else None
        headers = {"accept": "application/json"}
        if self.credential is not None:
            headers["authorization"] = f"Bearer {self.credential}"
        if cached is not None and cached.etag is not None:
            headers["if-none-match"] = cached.etag
        return url, headers, cached

    def fresh(self, cached: Cached | None) -> bytes | None:
        """The cached body, while it may be used without asking."""
        if cached is not None and cached.fresh_until > caching.now():
            return cached.body
        return None

    def answer(self, url: str, response: httpx.Response, cached: Cached | None) -> Any:
        if response.status_code == 304 and cached is not None:
            self._remember(url, cached.body, response, cached.etag)
            return json.loads(cached.body)
        if not response.is_success:
            raise _refusal(response, self.reads)

        body = response.content
        try:
            parsed = json.loads(body)
        except ValueError:
            raise CohoDeliveryError(
                response.status_code,
                "UNEXPECTED_RESPONSE",
                f"Delivery answered {response.status_code} with a body that is not JSON",
            ) from None
        self._remember(url, body, response)
        return parsed

    def _remember(
        self,
        url: str,
        body: bytes,
        response: httpx.Response,
        previous_etag: str | None = None,
    ) -> None:
        if self.cache is None:
            return
        now = caching.now()
        until = caching.fresh_until(response.headers.get("cache-control"), now)
        etag = response.headers.get("etag") or previous_etag
        # Nothing to gain from keeping a body that can neither be served nor revalidated.
        if until is None or (until <= now and etag is None):
            self.cache.delete(url)
        else:
            self.cache.set(url, Cached(body=body, etag=etag, fresh_until=until))


def _entries_query(
    type: str | None,
    order: str | None,
    limit: int | None,
    offset: int | None,
    depth: int | None,
    locale: str | None,
) -> Query:
    return {
        "type": type,
        "order": order,
        "limit": limit,
        "offset": offset,
        "depth": depth,
        "locale": locale,
    }


def _at(ref: str) -> str:
    return f"/{quote(ref, safe='')}"


def _not_found(error: CohoDeliveryError) -> bool:
    """A single read's refusal for a missing entry is a None, not an error."""
    return error.code == "ENTRY_NOT_FOUND"


class DeliveryClient:
    """
    The delivery API, untyped and synchronous. Entries come back as the server sends them.

    Keeps a private cache of responses, following `Cache-Control` and `ETag`. Close it when
    you are done, or use it as a context manager, unless you passed your own `http_client`.
    """

    def __init__(
        self,
        config: DeliveryConfig,
        *,
        http_client: httpx.Client | None = None,
        cache_size: int = DEFAULT_CACHE_SIZE,
    ):
        """
        `cache_size` is how many responses the private cache holds; 0 turns it off. Pass your
        own `http_client` to set timeouts, proxies or transports; it is then yours to close.
        """
        self._core = _Core(config, cache_size)
        self._owns_http = http_client is None
        self._http = http_client or httpx.Client()

    def _get(self, path: str, query: Query) -> Any:
        url, headers, cached = self._core.request(path, query)
        fresh = self._core.fresh(cached)
        if fresh is not None:
            return json.loads(fresh)
        return self._core.answer(url, self._http.get(url, headers=headers), cached)

    def entries(
        self,
        ref: str,
        *,
        type: str | None = None,
        order: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        depth: int | None = None,
        locale: str | None = None,
    ) -> EntryList:
        """
        A page of entries on `ref`, in the order `order` asks for, or by id. `order` is a
        sortable field of `type`, prefixed `-` for descending, and needs `type`.
        """
        query = _entries_query(type, order, limit, offset, depth, locale)
        return cast(EntryList, self._get(f"{_at(ref)}/entries", query))

    def entry(
        self, ref: str, id: str, *, depth: int | None = None, locale: str | None = None
    ) -> EntryGraph | None:
        """One entry by id, or None if it is not on `ref`."""
        try:
            path = f"{_at(ref)}/entries/{quote(id, safe='')}"
            return cast(EntryGraph, self._get(path, {"depth": depth, "locale": locale}))
        except CohoDeliveryError as error:
            if _not_found(error):
                return None
            raise

    def entry_by_slug(
        self, ref: str, slug: str, *, depth: int | None = None, locale: str | None = None
    ) -> EntryGraph | None:
        """One entry by slug, or None if it is not on `ref`."""
        try:
            path = f"{_at(ref)}/entries-by-slug/{quote(slug, safe='')}"
            return cast(EntryGraph, self._get(path, {"depth": depth, "locale": locale}))
        except CohoDeliveryError as error:
            if _not_found(error):
                return None
            raise

    def entries_by_id(
        self,
        ref: str,
        ids: Sequence[str],
        *,
        depth: int | None = None,
        locale: str | None = None,
    ) -> EntryGraph:
        """Several entries by id, at most 100. An id not on `ref` is reported as `absent`."""
        if len(ids) == 0:
            return {"roots": [], "entries": {}, "unresolved": {}}
        query: Query = {"ids": ",".join(ids), "depth": depth, "locale": locale}
        return cast(EntryGraph, self._get(f"{_at(ref)}/entries-by-id", query))

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> DeliveryClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class AsyncDeliveryClient:
    """The delivery API, untyped and asynchronous: `DeliveryClient`'s reads, awaited."""

    def __init__(
        self,
        config: DeliveryConfig,
        *,
        http_client: httpx.AsyncClient | None = None,
        cache_size: int = DEFAULT_CACHE_SIZE,
    ):
        self._core = _Core(config, cache_size)
        self._owns_http = http_client is None
        self._http = http_client or httpx.AsyncClient()

    async def _get(self, path: str, query: Query) -> Any:
        url, headers, cached = self._core.request(path, query)
        fresh = self._core.fresh(cached)
        if fresh is not None:
            return json.loads(fresh)
        return self._core.answer(url, await self._http.get(url, headers=headers), cached)

    async def entries(
        self,
        ref: str,
        *,
        type: str | None = None,
        order: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        depth: int | None = None,
        locale: str | None = None,
    ) -> EntryList:
        query = _entries_query(type, order, limit, offset, depth, locale)
        return cast(EntryList, await self._get(f"{_at(ref)}/entries", query))

    async def entry(
        self, ref: str, id: str, *, depth: int | None = None, locale: str | None = None
    ) -> EntryGraph | None:
        try:
            path = f"{_at(ref)}/entries/{quote(id, safe='')}"
            return cast(EntryGraph, await self._get(path, {"depth": depth, "locale": locale}))
        except CohoDeliveryError as error:
            if _not_found(error):
                return None
            raise

    async def entry_by_slug(
        self, ref: str, slug: str, *, depth: int | None = None, locale: str | None = None
    ) -> EntryGraph | None:
        try:
            path = f"{_at(ref)}/entries-by-slug/{quote(slug, safe='')}"
            return cast(EntryGraph, await self._get(path, {"depth": depth, "locale": locale}))
        except CohoDeliveryError as error:
            if _not_found(error):
                return None
            raise

    async def entries_by_id(
        self,
        ref: str,
        ids: Sequence[str],
        *,
        depth: int | None = None,
        locale: str | None = None,
    ) -> EntryGraph:
        if len(ids) == 0:
            return {"roots": [], "entries": {}, "unresolved": {}}
        query: Query = {"ids": ",".join(ids), "depth": depth, "locale": locale}
        return cast(EntryGraph, await self._get(f"{_at(ref)}/entries-by-id", query))

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self) -> AsyncDeliveryClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()


def _connection(config: DeliveryConfig) -> tuple[str, str | None, Reads]:
    """Where requests go, what authorizes them, and which side of Coho answers."""

    def trim(url: str) -> str:
        return url.rstrip("/")

    if isinstance(config, PreviewConfig):
        project = f"{quote(config.account, safe='')}/projects/{quote(config.project, safe='')}"
        return f"{trim(config.url)}/api/v1/accounts/{project}/preview", config.token, "preview"
    if isinstance(config, MountedConfig):
        return trim(config.base_url), config.key, "released"
    return (
        f"{trim(config.url)}/v1/projects/{quote(config.project, safe='')}",
        config.key,
        "released",
    )


def _query_string(query: Query) -> str:
    """
    Parameters in name order, whatever order the caller gave, so two call sites asking the
    same question share one URL, and so one cache entry here and one at any edge. Commas are
    left readable: `ids` is a comma-separated list.
    """
    parts = [
        f"{name}={quote(str(value), safe=',')}"
        for name, value in sorted(query.items())
        if value is not None
    ]
    return f"?{'&'.join(parts)}" if parts else ""


HINTS: dict[Reads, dict[str, str]] = {
    "released": {
        "PROJECT_NOT_FOUND": " Check that the key was issued for this project.",
        "REF_NOT_FOUND": (
            " Delivery serves tags and the environments pointing at them; read a branch, or dev,"
            " with a project token."
        ),
    },
    "preview": {
        "PROJECT_NOT_FOUND": (
            " Check that the token was issued for this project, and that the account is the one"
            " it belongs to."
        ),
        "REF_NOT_FOUND": (
            " A preview reads branches, and environments pointing at one such as dev; a release"
            " is read from delivery, with a key."
        ),
    },
}
"""
What to check, for the refusals whose answer is deliberately vague. A credential for another
project is answered exactly as a project that does not exist, so that one customer's cannot
confirm another's project; and each side serves only its own refs.
"""


def _refusal(response: httpx.Response, reads: Reads) -> CohoDeliveryError:
    problem = _problem_of(response)
    status = response.status_code
    if problem is None:
        return CohoDeliveryError(
            status, "UNEXPECTED_RESPONSE", f"Delivery answered {status} with no problem document"
        )
    code = problem["code"]
    text = (problem.get("detail") or problem.get("title") or "").rstrip(".")
    hint = HINTS[reads].get(code, "")
    return CohoDeliveryError(status, code, f"{code}: {text}.{hint}", problem)


def _problem_of(response: httpx.Response) -> Problem | None:
    # Read either JSON type. The contract says `application/problem+json`, and servers before
    # 2026-10-13 labelled problems `application/json`.
    if "json" not in response.headers.get("content-type", ""):
        return None
    try:
        body = json.loads(response.content)
    except ValueError:
        return None
    if isinstance(body, dict) and isinstance(body.get("code"), str):
        return cast(Problem, body)
    return None
