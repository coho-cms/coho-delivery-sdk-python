"""The delivery API's response shapes, as it sends them."""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict


class Entry(TypedDict):
    """One entry: one locale's values, flattened."""

    id: str

    slug: str
    """Unique on its ref."""

    type: str
    """The content type's slug."""

    locale: NotRequired[str]
    """The locale this entry was projected for. Absent when none was requested."""

    fields: dict[str, Any]
    """
    The author's fields. A localized field with no value in the requested locale is absent,
    not null. A reference holds an entry id, or a list of them.
    """


class DeliveryWarning(TypedDict):
    """One warning. `code` says what, the rest says where. Show an unknown code; never fail on one."""

    code: str
    entry: str
    field: str
    asset: str


class EntryGraph(TypedDict):
    """What every read returns: the roots, everything reached from them, and what was not."""

    roots: list[str]
    """The entries asked for that exist, in the order the read defines."""

    entries: dict[str, Entry]
    """The roots and every entry reached from them, keyed by id."""

    unresolved: dict[str, str]
    """
    Why a requested or referenced entry is not in `entries`: `depth` beyond the requested
    depth, `absent` not on the ref. Open, so a reason the server adds later still parses.
    """

    warnings: NotRequired[list[DeliveryWarning]]
    """
    What the response could not give in full (delivery 2.1.0): an asset field whose asset is
    gone, which is then `None`, or left out of a list.
    """


class EntryList(EntryGraph):
    """A page of a list."""

    hasMore: bool


class Problem(TypedDict):
    """An RFC 9457 problem document. Branch on `code`, not on the status."""

    code: str
    title: str
    status: int
    type: NotRequired[str]
    detail: NotRequired[str]
