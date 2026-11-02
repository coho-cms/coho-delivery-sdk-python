"""Hydration, against the recordings, with models written as generated code writes them."""

from __future__ import annotations

import asyncio
from typing import Literal

from pydantic import Field

import coho_delivery_sdk as runtime
from coho_delivery_sdk import (
    AsyncContentClient,
    ContentClient,
    ContentConfig,
    EntryGraph,
    HydratedEntry,
    Issue,
    Link,
    ReleasedConfig,
    TypeShape,
    Unresolved,
    hydrate,
    resolved,
)
from replay import KEY, Replay, graph


class Article(runtime.EntryBase):
    type: Literal["article"] = Field(alias="_type")
    title: str | None = None
    rank: int
    related: list[runtime.Linked[Article]] = []


class Citation(runtime.ItemBase):
    type: Literal["citation"] = Field(alias="_type")
    title: str
    year: int | None = None


class Step(runtime.ItemBase):
    type: Literal["step"] = Field(alias="_type")
    label: str | None = None
    minutes: int | None = None


class Figure(runtime.EntryBase):
    type: Literal["figure"] = Field(alias="_type")
    caption: str | None = None
    image: runtime.ImageAsset | None = None
    poster: runtime.Asset | None = None
    gallery: list[runtime.Asset] = []
    sources: list[Citation] = []
    steps: list[Step] = []
    keywords: list[str] | None = None
    sizes: list[int] = []


Article.model_rebuild()

SHAPE: runtime.Shape = {
    "article": TypeShape(
        model=Article, links={"related": Link(many=True, targets=("article",))}, always={"rank": 0}
    ),
    "figure": TypeShape(model=Figure, items={"sources": ("citation",), "steps": ("step",)}),
    "citation": TypeShape(model=Citation, always={"title": ""}),
    "step": TypeShape(model=Step),
}

C1, C2, C3, MISSING = (
    f"00000000-0000-7000-8000-0000000000{end}" for end in ("c1", "c2", "c3", "ff")
)


def issues() -> tuple[list[Issue], runtime.OnIssue]:
    found: list[Issue] = []
    return found, found.append


def test_references_become_their_targets_or_stubs_that_say_why() -> None:
    found, on_issue = issues()
    [root] = hydrate(graph("entry-by-slug-depth-1"), SHAPE, on_issue)

    assert isinstance(root, Article)
    [second] = root.related
    assert isinstance(second, Article) and second.title == "Chain 2"
    assert second.related == [
        Unresolved.model_validate({"_id": C3, "_unresolved": "depth"}),
        Unresolved.model_validate({"_id": MISSING, "_unresolved": "absent"}),
    ]
    assert found == []


def test_a_link_back_to_an_entry_being_built_is_a_cycle_stub() -> None:
    [root] = hydrate(graph("entry-by-slug-depth-2"), SHAPE)

    assert isinstance(root, Article)
    [second] = resolved(root.related)
    third = resolved(second.related)[0]
    assert third.related == [Unresolved.model_validate({"_id": C1, "_unresolved": "cycle"})]
    # Plain data, with no cycles: it serializes as it is.
    assert root.model_dump_json()


def test_a_target_of_a_type_the_field_does_not_link_to_is_a_type_stub() -> None:
    shape = {
        **SHAPE,
        "article": TypeShape(
            model=Article, links={"related": Link(many=True, targets=("figure",))}
        ),
    }
    [root] = hydrate(graph("entry-by-slug-depth-1"), shape)

    assert isinstance(root, Article)
    assert root.related == [Unresolved.model_validate({"_id": C2, "_unresolved": "type"})]


def test_without_a_shape_entries_are_untyped_and_references_stay_ids() -> None:
    [root] = hydrate(graph("entry-by-slug-depth-1"))

    assert type(root) is HydratedEntry
    assert root.model_extra is not None and root.model_extra["related"] == [C2]


def test_a_missing_field_its_type_always_has_takes_its_empty_value_and_is_reported_once() -> None:
    found, on_issue = issues()
    body = graph("entry-by-slug-depth-1")
    entries = {
        id: {**entry, "fields": {k: v for k, v in entry["fields"].items() if k != "rank"}}
        for id, entry in body["entries"].items()
    }
    damaged: EntryGraph = {**body, "entries": entries}  # type: ignore[typeddict-item]

    [root] = hydrate(damaged, SHAPE, on_issue)

    assert isinstance(root, Article) and root.rank == 0
    assert [(i.kind, i.slug, i.field) for i in found] == [
        ("missing-field", "chain-2", "rank"),
        ("missing-field", "chain-1", "rank"),
    ]


def test_a_value_its_model_refuses_leaves_the_entry_out_and_a_link_to_it_is_an_invalid_stub() -> (
    None
):
    found, on_issue = issues()
    body = graph("entry-by-slug-depth-1")
    entries = dict(body["entries"])
    entries[C2] = {**entries[C2], "fields": {**entries[C2]["fields"], "rank": "high"}}
    [root] = hydrate({**body, "entries": entries}, SHAPE, on_issue)

    assert isinstance(root, Article)
    assert root.related == [Unresolved.model_validate({"_id": C2, "_unresolved": "invalid"})]
    assert [(i.kind, i.slug) for i in found] == [("invalid-value", "chain-2")]


def test_assets_are_embedded_and_a_gone_one_is_none_or_left_out() -> None:
    [figure] = hydrate(graph("entry-with-assets"), SHAPE)

    assert isinstance(figure, Figure)
    assert figure.image is not None and figure.image.file.width == 1600
    assert figure.image.image(width=800, height=400, fit="fill").endswith(
        "?w=800&h=400&fit=fill&fx=0.25&fy=0.75"
    )
    assert figure.poster is None
    assert [asset.file.media_type for asset in figure.gallery if asset.file] == [
        "image/jpeg",
        "image/svg+xml",
        "application/pdf",
    ]


def test_repeater_items_are_their_components_and_an_unknown_one_is_left_out() -> None:
    found, on_issue = issues()
    [figure] = hydrate(graph("entry-with-repeater"), SHAPE, on_issue)

    assert isinstance(figure, Figure)
    assert [type(item) for item in figure.sources] == [Citation, Citation]
    assert all(item.id for item in figure.sources)

    shape = {**SHAPE, "figure": TypeShape(model=Figure, items={"sources": ("quote",)})}
    [figure] = hydrate(graph("entry-with-repeater"), shape, on_issue)
    assert isinstance(figure, Figure) and figure.sources == []
    assert {i.kind for i in found} == {"unknown-item"}


def test_a_localized_item_field_is_left_out_where_untranslated_and_lists_are_values() -> None:
    found, on_issue = issues()
    [figure] = hydrate(graph("entry-with-localized-items"), SHAPE, on_issue)

    assert isinstance(figure, Figure)
    assert [(step.label, step.minutes) for step in figure.steps] == [("Messen", 5), (None, 2)]
    assert figure.keywords == []
    assert figure.sizes == [3, 5]
    assert found == []


def test_a_content_client_reads_typed_and_reports_each_issue_once_for_its_life() -> None:
    found, on_issue = issues()
    replay = Replay()
    content = ContentClient(
        ContentConfig(
            ReleasedConfig(url="https://delivery.test", project="p1", key=KEY), ref="v0.0.1"
        ),
        SHAPE,
        http_client=replay.client(),
        on_issue=on_issue,
    )
    articles: runtime.TypeReader[Article, Literal["rank", "-rank"]] = content.type("article")

    page = articles.list(order="-rank", limit=3, locale="en-US")
    assert [a.slug for a in page.items] == [
        e["slug"]
        for e in (
            graph("entries-ordered")["entries"][id] for id in graph("entries-ordered")["roots"]
        )
    ]
    assert page.has_more is True
    assert articles.by_slug("chain-1", depth=2, locale="en-US") is not None
    assert articles.by_slug("nope") is None
    # A slug is unique per ref, not per type: a typed read of another type is None.
    assert content.type("figure").by_slug("chain-1", locale="en-US") is None


def test_a_singleton_reads_its_one_entry_by_its_fixed_slug_and_is_none_for_another_types_or_no_ones() -> (
    None
):
    released = ReleasedConfig(url="https://delivery.test", project="p1", key=KEY)
    replay = Replay()
    content = ContentClient(
        ContentConfig(released, ref="v0.0.1", locale="en-US"), SHAPE, http_client=replay.client()
    )
    # The recordings have no singleton, so `chain-1` stands in for an entry slug.
    settings: runtime.SingletonReader[Article] = content.singleton("article", "chain-1")

    entry = settings.get(depth=2)
    assert isinstance(entry, Article) and entry.title == "Chain 1"
    assert "/entries-by-slug/chain-1?" in replay.calls[0].url
    assert content.singleton("notice", "chain-1").get(depth=2) is None
    # `entry-not-found` was asked with no locale.
    bare = ContentClient(ContentConfig(released, ref="v0.0.1"), SHAPE, http_client=replay.client())
    assert bare.singleton("article", "nope").get() is None

    async def read() -> tuple[Article | None, object]:
        async with AsyncContentClient(
            ContentConfig(released, ref="v0.0.1", locale="en-US"),
            SHAPE,
            http_client=replay.async_client(),
        ) as awaited:
            reader: runtime.AsyncSingletonReader[Article] = awaited.singleton("article", "chain-1")
            return await reader.get(depth=2), await awaited.singleton("notice", "chain-1").get()

    found, other = asyncio.run(read())
    assert found is not None and found.title == "Chain 1"
    assert other is None
