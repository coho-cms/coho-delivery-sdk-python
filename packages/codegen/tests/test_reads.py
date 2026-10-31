"""
The generated code, read through: the committed packages in `expected/`, run against the
recordings, so what the generator writes is checked against what the server sends. `mypy`
checks this file too, so a type the generator gets wrong fails there first.
"""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

import coho_delivery_sdk as runtime
import delivery_fixture
import inheritance
import lists
import nested
import traits
from coho_delivery_sdk import ContentConfig, ReleasedConfig, Unresolved, is_resolved, resolved
from delivery_fixture import (
    Article,
    AsyncCoho,
    Citation,
    Coho,
    Figure,
    Note,
    Outline,
    OutlineSection,
    Point,
    Step,
)
from replay import KEY, RECORDINGS, Replay, graph, recording

CONFIG = ContentConfig(
    ReleasedConfig(url="https://delivery.test", project="p1", key=KEY), ref="v0.0.1"
)


def coho(replay: Replay) -> Coho:
    return Coho(CONFIG, http_client=replay.client())


def test_a_typed_read_returns_the_types_model_with_its_references_followed() -> None:
    post = coho(Replay()).article.by_slug("chain-1", depth=2, locale="en-US")

    assert isinstance(post, Article)
    assert post.title == "Chain 1"
    [second] = resolved(post.related)
    assert second.slug == "chain-2"
    assert [link.unresolved for link in second.related if isinstance(link, Unresolved)] == [
        "absent"
    ]
    third = next(link for link in second.related if is_resolved(link))
    assert isinstance(third, Article)
    assert third.related == [Unresolved.model_validate({"_id": post.id, "_unresolved": "cycle"})]


def test_a_list_is_ordered_by_a_sortable_field() -> None:
    page = coho(Replay()).article.list(order="-rank", limit=3, locale="en-US")

    ranks = [post.rank or 0 for post in page.items]
    assert ranks == sorted(ranks, reverse=True)
    assert page.has_more


def test_an_untranslated_field_is_none() -> None:
    page = coho(Replay()).article.list(locale="fr-FR", limit=100)

    assert any(post.title is None for post in page.items)
    assert all(post.locale == "fr-FR" for post in page.items)


def test_assets_and_repeater_items_are_typed() -> None:
    client = coho(Replay())
    figure = client.figure.by_id("00000000-0000-7000-8000-0000000000f1")
    assert isinstance(figure, Figure)
    assert figure.image is not None and figure.image.file is not None
    assert figure.image.file.width == 1600
    assert figure.poster is None

    with_sources = client.figure.by_id("00000000-0000-7000-8000-0000000000f2")
    assert with_sources is not None
    assert [type(item) for item in with_sources.sources] == [Citation, Citation]
    assert with_sources.sources[1].year == 2010


def test_localized_items_and_lists_are_read_as_the_locale_has_them() -> None:
    figure = coho(Replay()).figure.by_id("00000000-0000-7000-8000-0000000000f3", locale="de-DE")

    assert isinstance(figure, Figure)
    assert [type(step) for step in figure.steps] == [Step, Step]
    # The second step's label has no German, so delivery left it out.
    assert [step.label for step in figure.steps] == ["Messen", None]
    assert [step.minutes for step in figure.steps] == [5, 2]
    # None in German, on purpose: an empty list, where an untranslated one would be None.
    assert figure.keywords == []
    assert figure.sizes == [3, 5]


def test_items_inside_items_are_typed_at_every_level() -> None:
    outline = coho(Replay()).outline.by_id("00000000-0000-7000-8000-0000000000b1", locale="en-US")

    assert isinstance(outline, Outline)
    [section] = outline.sections
    assert isinstance(section, OutlineSection)
    assert (section.id, section.type, section.heading) == (
        "00000000-0000-7000-8000-0000000000b2",
        "outlineSection",
        "Plan",
    )
    # A point holds points: three levels, each its own model, with its own `_id` and `_type`.
    [first] = section.points
    [second] = first.children
    [third] = second.children
    assert [type(point) for point in (first, second, third)] == [Point, Point, Point]
    assert [point.id[-2:] for point in (first, second, third)] == ["b3", "b4", "b5"]
    assert {point.type for point in (first, second, third)} == {"point"}
    # The third point's text is only in pt-BR, so delivery left it out.
    assert [point.text for point in (first, second, third)] == ["Survey", "Measure", None]
    assert third.children == []
    # `notes` is localized as a whole: the en-US list.
    assert [(type(note), note.text) for note in section.notes] == [(Note, "Bring cones")]


def test_a_nested_item_of_an_unknown_component_is_left_out_where_it_is() -> None:
    body = copy.deepcopy(graph("entry-with-nested-items"))
    [entry] = body["entries"].values()
    first = entry["fields"]["sections"][0]["points"][0]
    # A component added to the ref after the code was generated, beside a known point.
    first["children"].insert(0, {"_id": "x", "_type": "callout", "text": "New"})
    found: list[runtime.Issue] = []

    [outline] = runtime.hydrate(body, delivery_fixture.shape, found.append)

    assert isinstance(outline, Outline)
    [kept] = outline.sections[0].points[0].children
    assert isinstance(kept, Point) and kept.text == "Measure"
    assert [type(point) for point in kept.children] == [Point]
    assert [(issue.kind, issue.field) for issue in found] == [
        ("unknown-item", "sections/0/points/0/children")
    ]


@pytest.mark.parametrize(
    "name",
    sorted(
        path.stem
        for path in RECORDINGS.glob("*.json")
        if recording(path.stem)["response"]["status"] == 200
    ),
)
def test_every_recording_reads_through_the_generated_code_without_an_issue(name: str) -> None:
    found: list[runtime.Issue] = []
    body = graph(name)
    roots = runtime.hydrate(body, delivery_fixture.shape, found.append)

    assert len(roots) == len([id for id in body["roots"] if id in body["entries"]])
    assert found == []


def test_an_untyped_read_is_any_entry() -> None:
    entry = coho(Replay()).by_slug("chain-1", locale="en-US")
    assert isinstance(entry, Article)


def test_the_async_client_reads_the_same() -> None:
    replay = Replay()

    async def read() -> Article | None:
        async with AsyncCoho(CONFIG, http_client=replay.async_client()) as client:
            return await client.article.by_slug("chain-1", depth=2, locale="en-US")

    post = asyncio.run(read())
    assert post is not None and post.title == "Chain 1"


def test_a_model_serializes_as_delivery_sent_it() -> None:
    post = coho(Replay()).article.by_slug("chain-1", locale="en-US")
    assert post is not None
    dumped = post.model_dump(exclude_none=True)
    assert (dumped["_id"], dumped["_type"], dumped["_slug"]) == (post.id, "article", "chain-1")


def test_the_source_names_the_type_model() -> None:
    assert delivery_fixture.source.schema_hash.startswith("sha256:")
    assert delivery_fixture.source.immutable


# INHERITANCE
# INHERITANCE
# INHERITANCE


def test_a_subtype_is_its_base_types_model_and_a_base_type_reads_its_family() -> None:
    assert issubclass(inheritance.PremiumService, inheritance.ServicePage)
    assert issubclass(inheritance.ServicePage, inheritance.Page)

    shape = inheritance.shape["page"]
    assert shape.model is inheritance.Page
    # A link to a page may be any concrete page.
    assert shape.links["related"].targets == ("landingPage", "premiumService", "servicePage")

    premium = inheritance.PremiumService.model_validate(
        {"_id": "1", "_type": "premiumService", "_slug": "gold", "summary": "s", "sla": 4}
    )
    page: inheritance.AnyPage = premium
    assert isinstance(page, inheritance.ServicePage)


def test_a_family_read_keeps_each_entry_as_its_own_type() -> None:
    graph: runtime.EntryGraph = {
        "roots": ["l", "s"],
        "entries": {
            "l": {"id": "l", "slug": "home", "type": "landingPage", "fields": {"rank": 1}},
            "s": {
                "id": "s",
                "slug": "svc",
                "type": "servicePage",
                "fields": {"summary": "x", "related": ["l"]},
            },
        },
        "unresolved": {},
    }
    landing, service = runtime.hydrate(graph, inheritance.shape)

    assert type(landing) is inheritance.LandingPage
    assert type(service) is inheritance.ServicePage
    assert isinstance(service, inheritance.ServicePage)
    assert [type(link) for link in service.related] == [inheritance.LandingPage]


# TRAITS
# TRAITS
# TRAITS


def meta_title(entry: traits.Seo) -> str | None:
    """Written against the trait, so it takes an entry of any type with it."""
    return entry.meta_title


def test_an_entry_of_any_type_with_a_trait_is_one() -> None:
    article = traits.Article.model_validate(
        {
            "_id": "a",
            "_type": "article",
            "_slug": "a",
            "title": "Hello, world",
            "metaTitle": "Hello",
            "publishedAt": "2026-10-01T00:00:00Z",
            "status": "live",
            "priority": 1,
        }
    )
    assert isinstance(article, traits.Seo)
    assert isinstance(article, traits.Publishing)
    assert meta_title(article) == "Hello"

    seo: Sequence[traits.Seo] = [article]
    assert len(seo) == 1


# LISTS
# LISTS
# LISTS


def test_a_list_holds_its_values_as_they_are_and_a_list_of_date_times_is_parsed() -> None:
    graph: runtime.EntryGraph = {
        "roots": ["e"],
        "entries": {
            "e": {
                "id": "e",
                "slug": "launch",
                "type": "event",
                "locale": "en-US",
                "fields": {
                    "title": "Launch",
                    "sessions": ["2026-11-02T09:00:00Z"],
                    "scores": [4.5, 3],
                    # Values that look like ids are still values: a list is never a link.
                    "agenda": [{"_id": "t", "_type": "talk", "speakers": ["e"], "tracks": []}],
                },
            },
        },
        "unresolved": {},
    }
    [event] = runtime.hydrate(graph, lists.shape)

    assert isinstance(event, lists.Event)
    assert event.sessions == [datetime(2026, 11, 2, 9, tzinfo=UTC)]
    assert event.scores == [4.5, 3.0]
    assert event.keywords is None
    [talk] = event.agenda
    assert (talk.speakers, talk.tracks) == (["e"], [])


# NESTED
# NESTED
# NESTED


def test_a_menu_of_menu_items_reads_as_deep_as_it_goes() -> None:
    def item(id: str, label: str, *children: dict[str, object]) -> dict[str, object]:
        return {"_id": id, "_type": "menuItem", "label": label, "children": list(children)}

    graph: runtime.EntryGraph = {
        "roots": ["n"],
        "entries": {
            "n": {
                "id": "n",
                "slug": "main",
                "type": "siteNavigation",
                "locale": "en-US",
                "fields": {
                    "footerLinks": [
                        item("a", "About", item("b", "Team", item("c", "Jobs"))),
                        item("d", "Contact"),
                    ],
                    "topNavigation": [{"_id": "t", "_type": "localeMenuItem", "label": "Home"}],
                },
            },
        },
        "unresolved": {},
    }
    found: list[runtime.Issue] = []
    [navigation] = runtime.hydrate(graph, nested.shape, found.append)

    assert isinstance(navigation, nested.SiteNavigation)
    about, contact = navigation.footer_links
    [team] = about.children
    [jobs] = team.children
    assert [(type(m), m.label) for m in (about, team, jobs, contact)] == [
        (nested.MenuItem, "About"),
        (nested.MenuItem, "Team"),
        (nested.MenuItem, "Jobs"),
        (nested.MenuItem, "Contact"),
    ]
    [home] = navigation.top_navigation
    assert isinstance(home, nested.LocaleMenuItem) and home.children == []
    assert found == []
