"""
Hydrated reads on one ref: what generated code builds its typed client from, so that the
logic lives in this package and reaches every library with an update.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar, cast

import httpx

from .client import DEFAULT_CACHE_SIZE, AsyncDeliveryClient, DeliveryClient, DeliveryConfig
from .hydrate import Issue, OnIssue, Shape, hydrate, warn
from .models import EntryBase
from .types import EntryGraph

T = TypeVar("T")
O = TypeVar("O", bound=str)  # noqa: E741  the sortable fields, as in Coho's other SDKs


@dataclass(frozen=True)
class ContentConfig:
    """What a content client reads, and where from."""

    delivery: DeliveryConfig
    """Where it reads, with which credential: released content, or a preview."""

    ref: str
    """
    The ref to read: an environment such as `prod`, or a tag. With a project token, a branch,
    or an environment pointing at one such as `dev`.
    """

    locale: str | None = None
    """The locale to project to, unless a read names its own. Without one, localized fields are absent."""


@dataclass(frozen=True)
class Page(Generic[T]):
    """A page of hydrated entries."""

    items: list[T]
    has_more: bool


class _Issues:
    """Once per issue for the life of a client rather than per read, so a page rendered a thousand times reports its broken entry once."""

    def __init__(self, on_issue: OnIssue | None):
        self._on_issue = on_issue or warn
        self._reported: set[str] = set()
        self._lock = threading.Lock()

    def __call__(self, issue: Issue) -> None:
        key = f"{issue.kind} {issue.id} {issue.field}"
        with self._lock:
            if key in self._reported:
                return
            self._reported.add(key)
        self._on_issue(issue)


class _Hydrator:
    def __init__(self, config: ContentConfig, shape: Shape, on_issue: OnIssue | None):
        self.config = config
        self.shape = shape
        self.issues = _Issues(on_issue)

    def locale(self, asked: str | None) -> str | None:
        return asked if asked is not None else self.config.locale

    def all(self, graph: EntryGraph) -> list[EntryBase]:
        return hydrate(graph, self.shape, self.issues)

    def first(self, graph: EntryGraph | None) -> EntryBase | None:
        if graph is None:
            return None
        entries = self.all(graph)
        return entries[0] if entries else None


def _of(family: Sequence[str], entry: EntryBase | None) -> Any:
    """A slug is unique per ref, not per type, so a typed read checks what it found."""
    return entry if entry is not None and entry.type in family else None


class ContentClient:
    """Hydrated reads on one ref, synchronous."""

    def __init__(
        self,
        config: ContentConfig,
        shape: Shape | None = None,
        *,
        http_client: httpx.Client | None = None,
        cache_size: int = DEFAULT_CACHE_SIZE,
        on_issue: OnIssue | None = None,
    ):
        """
        `on_issue` is called once per issue, for the life of the client; the default is a
        warning on the `coho` logger.
        """
        self.delivery = DeliveryClient(
            config.delivery, http_client=http_client, cache_size=cache_size
        )
        """The untyped client underneath, for anything the hydrated reads do not cover."""
        self._h = _Hydrator(config, shape or {}, on_issue)

    @property
    def config(self) -> ContentConfig:
        return self._h.config

    def by_slug(
        self, slug: str, *, depth: int | None = None, locale: str | None = None
    ) -> EntryBase | None:
        """The entry with this slug, whatever its type, or None."""
        graph = self.delivery.entry_by_slug(
            self.config.ref, slug, depth=depth, locale=self._h.locale(locale)
        )
        return self._h.first(graph)

    def by_id(
        self, id: str, *, depth: int | None = None, locale: str | None = None
    ) -> EntryBase | None:
        """The entry with this id, whatever its type, or None."""
        graph = self.delivery.entry(self.config.ref, id, depth=depth, locale=self._h.locale(locale))
        return self._h.first(graph)

    def by_ids(
        self, ids: Sequence[str], *, depth: int | None = None, locale: str | None = None
    ) -> list[EntryBase]:
        """The entries that exist, sorted by id. Ids not on the ref are left out."""
        graph = self.delivery.entries_by_id(
            self.config.ref, ids, depth=depth, locale=self._h.locale(locale)
        )
        return self._h.all(graph)

    def type(self, slug: str, family: Sequence[str] | None = None) -> TypeReader[Any, Any]:
        """
        Reads of one content type. Delivery lists a type with the types that extend it, so for
        a base type generated code also names `family`, the types an entry read here can be;
        without it, only `slug`'s own.
        """
        return TypeReader(self, slug, tuple(family or (slug,)))

    def close(self) -> None:
        self.delivery.close()

    def __enter__(self) -> ContentClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class TypeReader(Generic[T, O]):
    """Reads of one content type, as `T`. `O` names its sortable fields."""

    def __init__(self, content: ContentClient, slug: str, family: tuple[str, ...]):
        self._content = content
        self._slug = slug
        self._family = family

    def by_slug(
        self, slug: str, *, depth: int | None = None, locale: str | None = None
    ) -> T | None:
        """The entry with this slug, or None if there is none or it is of another type."""
        return cast(
            "T | None", _of(self._family, self._content.by_slug(slug, depth=depth, locale=locale))
        )

    def by_id(self, id: str, *, depth: int | None = None, locale: str | None = None) -> T | None:
        """The entry with this id, or None if there is none or it is of another type."""
        return cast(
            "T | None", _of(self._family, self._content.by_id(id, depth=depth, locale=locale))
        )

    def list(
        self,
        *,
        order: O | None = None,
        limit: int | None = None,
        offset: int | None = None,
        depth: int | None = None,
        locale: str | None = None,
    ) -> Page[T]:
        """
        A page of the type's entries, its descendants' included. `order` is a sortable field,
        prefixed `-` for descending.
        """
        content = self._content
        page = content.delivery.entries(
            content.config.ref,
            type=self._slug,
            order=order,
            limit=limit,
            offset=offset,
            depth=depth,
            locale=content._h.locale(locale),
        )
        items = [entry for entry in content._h.all(page) if entry.type in self._family]
        return Page(items=cast("list[T]", items), has_more=page["hasMore"])


class AsyncContentClient:
    """Hydrated reads on one ref, asynchronous: `ContentClient`'s reads, awaited."""

    def __init__(
        self,
        config: ContentConfig,
        shape: Shape | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
        cache_size: int = DEFAULT_CACHE_SIZE,
        on_issue: OnIssue | None = None,
    ):
        self.delivery = AsyncDeliveryClient(
            config.delivery, http_client=http_client, cache_size=cache_size
        )
        """The untyped client underneath, for anything the hydrated reads do not cover."""
        self._h = _Hydrator(config, shape or {}, on_issue)

    @property
    def config(self) -> ContentConfig:
        return self._h.config

    async def by_slug(
        self, slug: str, *, depth: int | None = None, locale: str | None = None
    ) -> EntryBase | None:
        graph = await self.delivery.entry_by_slug(
            self.config.ref, slug, depth=depth, locale=self._h.locale(locale)
        )
        return self._h.first(graph)

    async def by_id(
        self, id: str, *, depth: int | None = None, locale: str | None = None
    ) -> EntryBase | None:
        graph = await self.delivery.entry(
            self.config.ref, id, depth=depth, locale=self._h.locale(locale)
        )
        return self._h.first(graph)

    async def by_ids(
        self, ids: Sequence[str], *, depth: int | None = None, locale: str | None = None
    ) -> list[EntryBase]:
        graph = await self.delivery.entries_by_id(
            self.config.ref, ids, depth=depth, locale=self._h.locale(locale)
        )
        return self._h.all(graph)

    def type(self, slug: str, family: Sequence[str] | None = None) -> AsyncTypeReader[Any, Any]:
        return AsyncTypeReader(self, slug, tuple(family or (slug,)))

    async def aclose(self) -> None:
        await self.delivery.aclose()

    async def __aenter__(self) -> AsyncContentClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()


class AsyncTypeReader(Generic[T, O]):
    """Reads of one content type, as `T`, awaited. `O` names its sortable fields."""

    def __init__(self, content: AsyncContentClient, slug: str, family: tuple[str, ...]):
        self._content = content
        self._slug = slug
        self._family = family

    async def by_slug(
        self, slug: str, *, depth: int | None = None, locale: str | None = None
    ) -> T | None:
        return cast(
            "T | None",
            _of(self._family, await self._content.by_slug(slug, depth=depth, locale=locale)),
        )

    async def by_id(
        self, id: str, *, depth: int | None = None, locale: str | None = None
    ) -> T | None:
        return cast(
            "T | None", _of(self._family, await self._content.by_id(id, depth=depth, locale=locale))
        )

    async def list(
        self,
        *,
        order: O | None = None,
        limit: int | None = None,
        offset: int | None = None,
        depth: int | None = None,
        locale: str | None = None,
    ) -> Page[T]:
        content = self._content
        page = await content.delivery.entries(
            content.config.ref,
            type=self._slug,
            order=order,
            limit=limit,
            offset=offset,
            depth=depth,
            locale=content._h.locale(locale),
        )
        items = [entry for entry in content._h.all(page) if entry.type in self._family]
        return Page(items=cast("list[T]", items), has_more=page["hasMore"])
