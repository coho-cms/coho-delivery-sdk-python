"""Hydration: a delivery graph's roots as models, with each reference replaced by its target."""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import ValidationError

from .models import CohoModel, EntryBase, HydratedEntry, ItemBase, RepeaterItem, Unresolved
from .types import Entry, EntryGraph

logger = logging.getLogger("coho")


@dataclass(frozen=True)
class Link:
    """A reference field: one link or a list, and the types its targets may be."""

    many: bool

    targets: tuple[str, ...] | None = None
    """
    The concrete types a target may be, a base type's descendants included. A target of any
    other type becomes a `type` stub. None accepts any type.
    """


@dataclass(frozen=True)
class TypeShape:
    """
    What hydration needs to know about one content or component type. Generated code writes
    it from the type model. Untyped callers may write one by hand, or pass none, in which
    case entries are `HydratedEntry`s and references stay ids.
    """

    model: type[CohoModel] | None = None
    """The model an entry or item of the type is validated as."""

    links: Mapping[str, Link] = field(default_factory=dict)
    """The reference fields, by field id."""

    always: Mapping[str, Any] = field(default_factory=dict)
    """
    The fields delivery always includes, by field id, each with the value it takes when an
    entry has none, as older entries may after a field becomes required.
    """

    items: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    """
    The repeater fields, by field id, each with the component types its generated code knows.
    An item of any other component is left out, and reported, so code generated before a
    component was added never meets an item it has no type for.
    """


Shape = Mapping[str, TypeShape]
"""Type shapes, by content or component type slug."""

IssueKind = Literal[
    "missing-field",
    "unexpected-value",
    "unlisted-link",
    "unknown-item",
    "invalid-value",
]


@dataclass(frozen=True)
class Issue:
    """
    Something about an entry that its type says cannot happen. Reported, never raised.

    `missing-field`: a field the type always has is absent, as old entries are after a field
    becomes required; it takes its type's empty value. `unexpected-value`: one link where the
    type says many, or the other way round. `unlisted-link`: a link delivery neither resolved
    nor reported. `unknown-item`: a repeater item of a component the code has no type for,
    left out. `invalid-value`: a value its model refuses, such as text where a number belongs;
    the entry is left out, and a link to it is an `invalid` stub.
    """

    kind: IssueKind
    id: str
    slug: str
    type: str
    field: str
    message: str


OnIssue = Callable[[Issue], None]


def warn(issue: Issue) -> None:
    """The default `on_issue`: a warning on the `coho` logger."""
    logger.warning("[coho] %s", issue.message)


def hydrate(
    graph: EntryGraph, shape: Shape | None = None, on_issue: OnIssue | None = None
) -> list[EntryBase]:
    """
    The graph's roots, in order, as models, with each reference replaced by its target or a
    stub.

    Each root gets its own pass, so its tree holds everything reachable from it. Within a pass
    an entry is built once and shared, and a link back to an entry still being built becomes a
    `cycle` stub, so the result has no cycles and serializes as it is. Models are built from
    the leaves up, so each reference holds the model of its target's own type, which is how a
    link to a base type holds a subtype.
    """
    return _Hydration(graph, shape or {}, on_issue or warn).roots()


class _Hydration:
    def __init__(self, graph: EntryGraph, shape: Shape, on_issue: OnIssue):
        self.graph = graph
        self.shape = shape
        self.on_issue = on_issue
        self.reported: set[str] = set()

    def report(self, kind: IssueKind, entry: Entry, field: str, what: str) -> None:
        key = f"{kind} {entry['id']} {field}"
        if key in self.reported:
            return
        self.reported.add(key)
        message = f"{entry['type']} '{entry['slug']}' {what}"
        self.on_issue(Issue(kind, entry["id"], entry["slug"], entry["type"], field, message))

    def roots(self) -> list[EntryBase]:
        out: list[EntryBase] = []
        for root_id in self.graph["roots"]:
            root = self.graph["entries"].get(root_id)
            if root is None:
                continue
            built = _Pass(self).build(root)
            if isinstance(built, EntryBase):
                out.append(built)
        return out


class _Pass:
    """One root's tree."""

    def __init__(self, hydration: _Hydration):
        self.h = hydration
        self.built: dict[str, EntryBase | Unresolved] = {}
        self.building: set[str] = set()

    def build(self, entry: Entry) -> EntryBase | Unresolved:
        h = self.h
        self.building.add(entry["id"])
        type_shape = h.shape.get(entry["type"])
        out: dict[str, Any] = {"_id": entry["id"], "_type": entry["type"], "_slug": entry["slug"]}
        if "locale" in entry:
            out["_locale"] = entry["locale"]
        self.fields(entry, entry["fields"], type_shape, out)

        model = (
            type_shape.model
            if type_shape is not None and type_shape.model is not None
            else HydratedEntry
        )
        result: EntryBase | Unresolved
        try:
            validated = model.model_validate(out)
            assert isinstance(validated, EntryBase)
            result = validated
        except ValidationError as error:
            h.report(
                "invalid-value",
                entry,
                _where(error),
                f"does not match its type, and is left out: {_first(error)}",
            )
            result = Unresolved.model_validate({"_id": entry["id"], "_unresolved": "invalid"})

        self.building.discard(entry["id"])
        self.built[entry["id"]] = result
        return result

    def fields(
        self,
        entry: Entry,
        values: Mapping[str, Any],
        type_shape: TypeShape | None,
        out: dict[str, Any],
    ) -> None:
        """An entry's or an item's fields, with links followed and items built, into `out`."""
        h = self.h
        links = type_shape.links if type_shape is not None else {}
        items = type_shape.items if type_shape is not None else {}
        for name, value in values.items():
            link = links.get(name)
            components = items.get(name)
            if components is not None and isinstance(value, list):
                out[name] = [
                    built
                    for item in value
                    if (built := self.item(entry, name, item, components)) is not None
                ]
            elif link is None or value is None:
                out[name] = value
            elif link.many and isinstance(value, list):
                out[name] = [self.follow(entry, name, each, link) for each in value]
            elif not link.many and not isinstance(value, list):
                out[name] = self.follow(entry, name, value, link)
            else:
                have, want = ("one link", "several") if link.many else ("several links", "one")
                h.report(
                    "unexpected-value",
                    entry,
                    name,
                    f"has {have} in '{name}', where its type has {want}",
                )
                out[name] = value

        for name, default in (type_shape.always if type_shape is not None else {}).items():
            if name not in values:
                h.report("missing-field", entry, name, f"has no '{name}', which its type requires")
                out[name] = copy.deepcopy(default)

    def follow(self, entry: Entry, field: str, value: Any, link: Link) -> Any:
        # Not an id: left as delivery sent it.
        if not isinstance(value, str):
            return value
        done = self.built.get(value)
        if done is not None:
            return self.checked(done, link)
        if value in self.building:
            return _stub(value, "cycle")
        target = self.h.graph["entries"].get(value)
        if target is not None:
            if link.targets is not None and target["type"] not in link.targets:
                return _stub(value, "type")
            return self.build(target)
        reason = self.h.graph["unresolved"].get(value)
        if reason is None:
            self.h.report(
                "unlisted-link",
                entry,
                field,
                f"links '{field}' to {value}, which delivery neither returned nor reported",
            )
        return _stub(value, reason or "absent")

    def checked(self, done: EntryBase | Unresolved, link: Link) -> EntryBase | Unresolved:
        """An entry this pass already built, as this link may hold it."""
        if (
            isinstance(done, EntryBase)
            and link.targets is not None
            and done.type not in link.targets
        ):
            return _stub(done.id, "type")
        return done

    def item(
        self, entry: Entry, field: str, item: Any, components: tuple[str, ...]
    ) -> ItemBase | None:
        h = self.h
        component = item.get("_type") if isinstance(item, dict) else None
        if not isinstance(component, str) or component not in components:
            h.report(
                "unknown-item",
                entry,
                field,
                f"has an item of '{component}' in '{field}', which this code has no type for; it is left out",
            )
            return None
        component_shape = h.shape.get(component)
        out: dict[str, Any] = {key: value for key, value in item.items() if key.startswith("_")}
        self.fields(
            entry,
            {key: value for key, value in item.items() if not key.startswith("_")},
            component_shape,
            out,
        )
        model = (
            component_shape.model
            if component_shape is not None and component_shape.model is not None
            else RepeaterItem
        )
        try:
            validated = model.model_validate(out)
            assert isinstance(validated, ItemBase)
            return validated
        except ValidationError as error:
            h.report(
                "invalid-value",
                entry,
                f"{field}/{_where(error)}",
                f"has an item in '{field}' that does not match '{component}', and is left out: {_first(error)}",
            )
            return None


def _stub(id: str, reason: str) -> Unresolved:
    return Unresolved.model_validate({"_id": id, "_unresolved": reason})


def _where(error: ValidationError) -> str:
    errors = error.errors()
    return "/".join(str(part) for part in errors[0]["loc"]) if errors else ""


def _first(error: ValidationError) -> str:
    errors = error.errors()
    if not errors:
        return str(error)
    first = errors[0]
    where = "/".join(str(part) for part in first["loc"])
    return f"{where}: {first['msg']}" if where else str(first["msg"])
