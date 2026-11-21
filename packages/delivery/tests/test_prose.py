"""
Resolving what a body points at (coho-data doc 80 ML-1), against the three shapes the portal
writes, and leaving everything else — a reference nothing can place included — exactly as it
was. The same cases as `@coho-cms/delivery`'s `prose.test.ts`, because the rule has to be one
rule.
"""

from __future__ import annotations

from pydantic import Field

from coho_delivery_sdk import (
    Asset,
    EntryBase,
    asset_reference,
    body_assets,
    referenced_slug,
    resolve_entry,
    resolve_prose,
)

BRIDGE = Asset.model_validate(
    {"id": "e1", "slug": "bridge-at-dusk", "url": "https://assets.test/a/h1/bridge.jpg"}
)
TOUR = Asset.model_validate(
    {"id": "e2", "slug": "ring-road", "url": "https://assets.test/a/h2/tour.mp4"}
)
SHEET = Asset.model_validate(
    {"id": "e3", "slug": "datasheet-2026", "url": "https://assets.test/a/h3/d.pdf"}
)
ASSETS = [BRIDGE, TOUR, SHEET]


class Article(EntryBase):
    """What generated code declares for a type with a prose field and a link."""

    body: str = ""
    featured: Article | None = None
    modules: list[Module] = Field(default_factory=list)


class Module(EntryBase):
    """A repeater item, for the walk's sake: an entry's prose is not only its own fields."""

    note: str = ""


Article.model_rebuild()


def test_an_image_a_video_directive_and_a_download_link_each_resolve() -> None:
    assert (
        resolve_prose("![A bridge](asset:bridge-at-dusk)", ASSETS) == f"![A bridge]({BRIDGE.url})"
    )
    assert (
        resolve_prose('::video[The tour]{src="asset:ring-road"}', ASSETS)
        == f'::video[The tour]{{src="{TOUR.url}"}}'
    )
    assert (
        resolve_prose("[The datasheet](asset:datasheet-2026)", ASSETS)
        == f"[The datasheet]({SHEET.url})"
    )


def test_a_markdown_title_survives_and_an_html_attribute_resolves_too() -> None:
    assert (
        resolve_prose('![A bridge](asset:bridge-at-dusk "At dusk")', ASSETS)
        == f'![A bridge]({BRIDGE.url} "At dusk")'
    )
    assert resolve_prose('<img src="asset:bridge-at-dusk">', ASSETS) == f'<img src="{BRIDGE.url}">'
    assert (
        resolve_prose("<video poster='asset:bridge-at-dusk'>", ASSETS)
        == f"<video poster='{BRIDGE.url}'>"
    )


def test_only_an_attribute_that_fetches_and_only_when_the_value_is_the_whole_reference() -> None:
    # `alt` fetches nothing, and a URL with the text inside it is not a reference.
    assert (
        resolve_prose('<img alt="asset:bridge-at-dusk">', ASSETS)
        == '<img alt="asset:bridge-at-dusk">'
    )
    assert (
        resolve_prose("[x](https://other.test/asset:bridge-at-dusk)", ASSETS)
        == "[x](https://other.test/asset:bridge-at-dusk)"
    )

    # Bare text is not a reference either, so a body can write about the scheme.
    assert (
        resolve_prose("Write asset:bridge-at-dusk to name it.", ASSETS)
        == "Write asset:bridge-at-dusk to name it."
    )


def test_a_reference_the_entry_does_not_carry_is_left_exactly_as_written() -> None:
    assert (
        resolve_prose("![Not here](asset:not-here-yet)", ASSETS)
        == "![Not here](asset:not-here-yet)"
    )

    # An asset with no URL cannot be resolved to either.
    pending = Asset.model_validate({"id": "e4", "slug": "pending"})
    assert resolve_prose("![A](asset:pending)", [pending]) == "![A](asset:pending)"


def test_an_entry_resolves_at_any_depth_its_repeater_items_included() -> None:
    entry = Article.model_validate(
        {
            "_id": "p1",
            "_type": "article",
            "_slug": "home",
            "_bodyAssets": ASSETS,
            "body": "![A bridge](asset:bridge-at-dusk)",
            "modules": [
                {
                    "_id": "m1",
                    "_type": "noteModule",
                    "_slug": "m1",
                    "note": "See [the sheet](asset:datasheet-2026).",
                }
            ],
        }
    )

    resolved = resolve_entry(entry)
    assert resolved.body == f"![A bridge]({BRIDGE.url})"
    assert resolved.modules[0].note == f"See [the sheet]({SHEET.url})."

    # Frozen models, so the entry as delivered is still the entry as delivered — which is what
    # keeps a resolved body from reaching a write by accident.
    assert entry.body == "![A bridge](asset:bridge-at-dusk)"


def test_a_linked_entry_resolves_against_its_own_record_not_the_pages() -> None:
    cones = Asset.model_validate(
        {"id": "e9", "slug": "cone-field", "url": "https://assets.test/a/h9/cones.png"}
    )
    page = Article.model_validate(
        {
            "_id": "p2",
            "_type": "article",
            "_slug": "page",
            "_bodyAssets": [BRIDGE],
            "body": "![A bridge](asset:bridge-at-dusk)",
            "featured": {
                "_id": "p3",
                "_type": "article",
                "_slug": "featured",
                "_bodyAssets": [cones],
                "body": "![Cones](asset:cone-field)",
            },
        }
    )

    resolved = resolve_entry(page)
    assert resolved.body == f"![A bridge]({BRIDGE.url})"
    assert resolved.featured is not None
    assert resolved.featured.body == f"![Cones]({cones.url})"


def test_an_entry_with_nothing_to_resolve_is_returned_as_it_is_not_copied() -> None:
    entry = Article.model_validate(
        {
            "_id": "p4",
            "_type": "article",
            "_slug": "plain",
            "body": "![A bridge](asset:bridge-at-dusk)",
        }
    )

    assert resolve_entry(entry) is entry
    assert body_assets(entry) == []
    assert body_assets(None) == []
    assert body_assets({"_bodyAssets": "not a list"}) == []


def test_an_untyped_read_resolves_too_against_the_key_delivery_sent() -> None:
    entry = {
        "_id": "p5",
        "_slug": "untyped",
        "_bodyAssets": [{"slug": "bridge-at-dusk", "url": BRIDGE.url}],
        "body": "![A bridge](asset:bridge-at-dusk)",
    }

    resolved = resolve_entry(entry)
    assert resolved["body"] == f"![A bridge]({BRIDGE.url})"

    # The list itself comes back untouched: the assets are not prose.
    assert resolved["_bodyAssets"] == entry["_bodyAssets"]


def test_a_reference_reads_back_as_the_slug_it_names() -> None:
    assert asset_reference("bridge-at-dusk") == "asset:bridge-at-dusk"
    assert referenced_slug("asset:bridge-at-dusk") == "bridge-at-dusk"
    assert referenced_slug("https://assets.test/a/h1/bridge.jpg") is None
    assert referenced_slug("asset:") is None
    assert referenced_slug("asset:not a slug") is None
    assert referenced_slug(42) is None
