"""
What hydrated reads return: entries and repeater items as Pydantic models, and the stubs a
reference becomes when its target is not here.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TypeGuard, TypeVar, Union

from pydantic import BaseModel, ConfigDict, Field


class CohoModel(BaseModel):
    """
    The base of every model Coho hands you, generated ones included.

    Frozen, since a read may share one entry between every link to it. Fields are read by
    their Python names, and validated and serialized by Coho's own, so `model_dump()` and a
    FastAPI response give back the shape delivery sent. A field the code does not know, such
    as one added after it was generated, is ignored.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
        use_attribute_docstrings=True,
    )


class EntryBase(CohoModel):
    """
    The system values on every entry. A field id cannot begin with `_`, so their names on the
    wire never collide with a field's.
    """

    id: str = Field(alias="_id")

    type: str = Field(alias="_type")
    """The content type's slug: what to switch on, or check with `isinstance`."""

    slug: str = Field(alias="_slug")

    locale: str | None = Field(default=None, alias="_locale")
    """The locale the entry was projected for. None when none was requested."""


class ItemBase(CohoModel):
    """
    The system values on every repeater item: its identity, stable across edits and merges,
    and the component type it is.
    """

    id: str = Field(alias="_id")

    type: str = Field(alias="_type")


class HydratedEntry(EntryBase):
    """An entry of a type no generated code declares: its fields are kept, untyped."""

    model_config = ConfigDict(extra="allow")


class RepeaterItem(ItemBase):
    """An item of a repeater whose component types are not on the ref, so its fields are untyped."""

    model_config = ConfigDict(extra="allow")

    type: str | None = Field(default=None, alias="_type")  # type: ignore[assignment]


class Unresolved(CohoModel):
    """Where a reference's target would be, and why it is not."""

    id: str = Field(alias="_id")

    unresolved: str = Field(alias="_unresolved")
    """
    `depth` and `absent` as delivery reports them: beyond the requested depth, or not on the
    ref. `cycle` where following the link would close a loop, `type` where the target is of a
    type the field does not link to, and `invalid` where it does not match its type.
    """


T = TypeVar("T")

Linked = Union[T, Unresolved]  # noqa: UP007  a generic alias, which `|` cannot spell
"""A reference: its target, or a stub saying why the target is not here."""


def is_resolved(link: Linked[T]) -> TypeGuard[T]:
    """Whether a reference reached its target."""
    return not isinstance(link, Unresolved)


def resolved(links: Iterable[Linked[T]]) -> list[T]:
    """The targets of a list of references that are here, leaving out the stubs."""
    return [link for link in links if not isinstance(link, Unresolved)]


@dataclass(frozen=True)
class Source:
    """Where a generated library's types came from, for reporting which release a build was made from."""

    project: str

    ref: str
    """The branch or tag the types came from."""

    immutable: bool
    """True for a tag, whose types can never change."""

    schema_hash: str
    ir_version: str
