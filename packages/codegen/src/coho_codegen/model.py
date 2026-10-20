"""
The type model: a language-neutral description of one ref's content types, produced by the
Coho server. See `type-model.schema.json` in coho-sdk-spec.

Only what the generator reads is declared here. Readers ignore keys they do not know, which
is what lets a minor version add them.
"""

from __future__ import annotations

import re
from typing import Any, Literal, NotRequired, TypedDict, cast


class Source(TypedDict):
    project: str
    ref: str
    """The branch or tag the types came from."""
    immutable: bool
    """True for a tag, whose types can never change."""
    schemaHash: str


class Field(TypedDict):
    id: str
    name: str
    kind: str
    """Open: a kind added after this generator was written is emitted untyped."""
    presence: Literal["always", "maybe"]
    """Whether delivery always includes the field. The one rule for optionality."""
    required: bool
    localized: bool
    sortable: bool
    many: NotRequired[bool]
    accept: NotRequired[list[str]]
    """On assets (1.1): the media types a linked file may be, or family wildcards. Empty for any."""
    of: NotRequired[list[str]]
    """Reference targets, each a key of `types`; or a repeater's component types, keys of `components`."""
    values: NotRequired[list[str]]
    textFormat: NotRequired[str]
    inherited: NotRequired[bool]
    """Since 1.3: the field reaches this type exactly as its parent has it."""
    trait: NotRequired[str]
    """Since 1.4: the trait the field comes from, a key of `traits`."""


class ContentType(TypedDict):
    slug: str
    name: str
    version: str
    extends: NotRequired[str]
    """Since 1.3: the type this one extends, a key of the same map. `fields` already has what it inherits."""
    abstract: NotRequired[bool]
    """Since 1.3: no entry is of this type itself, only its descendants."""
    traits: NotRequired[list[str]]
    """Since 1.4: every trait it has, each a key of `traits`, its ancestors' first."""
    fields: list[Field]


class Trait(TypedDict):
    slug: str
    name: str
    version: str
    fields: list[Field]


class ModelWarning(TypedDict):
    type: str
    field: str
    message: str


class TypeModel(TypedDict):
    irVersion: str
    source: Source
    types: dict[str, ContentType]
    components: NotRequired[dict[str, ContentType]]
    """Since 1.2: component types by slug, the items repeaters hold."""
    traits: NotRequired[dict[str, Trait]]
    """Since 1.4: traits by slug, named groups of fields that types take. Never types."""
    warnings: NotRequired[list[ModelWarning]]


SUPPORTED_MAJOR = 1
"""The type model's major version this generator reads."""


class CodegenError(Exception):
    """A type model, a configuration or a server answer the generator cannot use."""


def read_type_model(json: Any) -> TypeModel:
    """
    Checks that `json` is a type model this generator can read, and returns it. An unknown
    major version is refused: the shape may mean something this generator cannot know.
    """
    if not isinstance(json, dict):
        raise CodegenError("The type model is not a JSON object")

    version = json.get("irVersion")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+", version):
        raise CodegenError(f"The type model has no valid irVersion: {version!r}")
    major = int(version.split(".")[0])
    if major != SUPPORTED_MAJOR:
        raise CodegenError(
            f"The type model is version {version}; this generator reads {SUPPORTED_MAJOR}.x. "
            "Upgrade coho-codegen."
        )

    if not isinstance(json.get("source"), dict):
        raise CodegenError("The type model has no source")
    for key, what in (("types", "Type"), ("components", "Component type"), ("traits", "Trait")):
        group = json.get(key)
        if group is None and key != "types":
            continue
        if not isinstance(group, dict):
            raise CodegenError(f"The type model's {key} are not an object")
        for slug, each in group.items():
            if not isinstance(each, dict) or not isinstance(each.get("fields"), list):
                raise CodegenError(f"{what} '{slug}' in the type model has no fields")
    return cast(TypeModel, json)
