"""
Turning an `asset:` reference in a body into the file it names (coho-data doc 80 ML-1).

A Markdown or HTML field names an asset by **slug** — `![A bridge](asset:bridge-at-dusk)` —
rather than by URL, so the body carries no asset domain, survives being moved between
branches, and is seen by everything that counts a file as used. Nothing renders that on its
own: Coho records what the prose named in the entry's `body_assets`, delivery embeds those
assets as it embeds any asset field, and this turns one into the other.

It is here rather than in each application because the rule is not obvious and has to match
the server's: several copies of these patterns already exist, and every consumer that renders
a body would otherwise write another.

## Resolve at the read, and never before a write

Call this where an entry arrives, once, rather than at each place a body is drawn — a body
usually reaches more than one renderer, and the version that none of them can forget is the
one at the read.

⛔ **Never resolve a body you may write back.** A resolved body holds URLs, and saving one
destroys the reference the scheme exists to keep: the asset stops counting as used, the link
breaks when the file is replaced, and moving the entry to another project carries the old
domain with it. Anything that edits content must keep the body exactly as delivered — which
is why resolving is a call you make and not something a read does for you.

## What an unresolved reference does

A reference to an asset the entry does not carry is **left exactly as written**. That is an
asset not merged onto this ref, or a slug typed by hand; an image then falls back to its alt
text. Rewriting it to nothing would hide it, and throwing would stop a page over one figure.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, TypeVar

from .models import CohoModel

ASSET_SCHEME = "asset:"
"""The scheme a body names an asset by."""

BODY_ASSETS_FIELD = "_bodyAssets"
"""The key delivery sends an entry's prose assets under (coho-data doc 80 §10)."""

_SLUG = r"[A-Za-z0-9][A-Za-z0-9._-]*"
"""A slug's shape, as the server reads one. These must agree."""

_SLUG_ONLY = re.compile(rf"^{_SLUG}$")

_TARGET = re.compile(rf"""(!?\[[^\]]*\]\(\s*){ASSET_SCHEME}({_SLUG})(\s*(?:"[^"]*")?\s*\))""")
"""
`![alt](asset:slug)` and `[label](asset:slug)`, with Markdown's optional title after it.
Bare text is deliberately not a reference, so a body can write about the scheme.
"""

_ATTRIBUTE = re.compile(rf"""(\b(?:src|href|poster)\s*=\s*["']){ASSET_SCHEME}({_SLUG})(["'])""")
"""
`src`, `href` or `poster` naming an asset: a video directive's attribute in Markdown, or an
attribute in an HTML field. Only attributes that fetch something, and only when the whole
value is the reference — so `alt="asset:x"` and a URL with the text inside it are not
mistaken for one.
"""

T = TypeVar("T")


def asset_reference(slug: str) -> str:
    """What a body writes to name the asset with this slug."""
    return f"{ASSET_SCHEME}{slug}"


def referenced_slug(value: object) -> str | None:
    """
    The slug `value` references, or None when it is an ordinary URL or anything else. For code
    that wants to find references rather than replace them.
    """
    if not isinstance(value, str) or not value.startswith(ASSET_SCHEME):
        return None
    slug = value[len(ASSET_SCHEME) :]
    return slug if _SLUG_ONLY.match(slug) else None


def body_assets(entry: object) -> Sequence[Any]:
    """
    The assets `entry` carries for its prose, read from a hydrated model or from an untyped
    read's mapping alike, and empty for anything that carries none.
    """
    if isinstance(entry, Mapping):
        held = entry.get(BODY_ASSETS_FIELD)
    else:
        held = getattr(entry, "body_assets", None)
    return list(held) if isinstance(held, Sequence) and not isinstance(held, str) else []


def _urls(assets: Iterable[Any]) -> dict[str, str]:
    """Slug to URL, for the assets that have both: one with no URL cannot be resolved to."""
    by: dict[str, str] = {}
    for asset in assets:
        slug = asset.get("slug") if isinstance(asset, Mapping) else getattr(asset, "slug", None)
        url = asset.get("url") if isinstance(asset, Mapping) else getattr(asset, "url", None)
        if isinstance(slug, str) and slug and isinstance(url, str) and url:
            by[slug] = url
    return by


def resolve_prose(text: str, assets: Iterable[Any]) -> str:
    """
    `text` with every `asset:` reference `assets` can place replaced by that asset's URL. A
    reference to an asset that is not there, or to one with no URL, is left as written.
    """
    if ASSET_SCHEME not in text:
        return text
    by = _urls(assets)
    if not by:
        return text

    def swap(match: re.Match[str]) -> str:
        url = by.get(match[2])
        return match[0] if url is None else f"{match[1]}{url}{match[3]}"

    return _ATTRIBUTE.sub(swap, _TARGET.sub(swap, text))


def resolve_entry(entry: T) -> T:
    """
    `entry` with every `asset:` reference in it resolved, at any depth: its own prose, the
    prose of every repeater item it holds, and any entry it links.

    **Each entry resolves against its own `body_assets`.** A linked entry read in the same
    graph carries its own, so a page does not resolve a linked article's figures against its
    own list.

    Strings only, and only ones holding the scheme, so a field that is not prose comes back
    as it was. What did not change is returned as the same object rather than a copy, so an
    entry with no references — almost all of them — is returned identical. The models are
    frozen, so a changed one is a copy and the original is left alone either way.

    ⛔ The warning at the top of this module applies here most of all: the result is for
    rendering, never for saving.
    """

    def walk(value: Any, assets: Sequence[Any]) -> Any:
        if isinstance(value, str):
            return resolve_prose(value, assets)

        if isinstance(value, CohoModel):
            here = body_assets(value) or assets
            # Not `body_assets` itself: the asset list is not prose, and an asset's own text
            # is not a body. Everything else, so a repeater item or linked entry is reached.
            changed = {
                name: walked
                for name in type(value).model_fields
                if name != "body_assets"
                and (walked := walk(getattr(value, name), here)) is not getattr(value, name)
            }
            return value.model_copy(update=changed) if changed else value

        if isinstance(value, Mapping):
            here = body_assets(value) or assets
            held = {
                key: walk(each, here) for key, each in value.items() if key != BODY_ASSETS_FIELD
            }
            if all(each is value[key] for key, each in held.items()):
                return value
            return {**value, **held}

        if isinstance(value, (list, tuple)):
            walked = [walk(each, assets) for each in value]
            if all(each is was for each, was in zip(walked, value, strict=True)):
                return value
            return type(value)(walked)

        return value

    return walk(entry, body_assets(entry))  # type: ignore[no-any-return]
