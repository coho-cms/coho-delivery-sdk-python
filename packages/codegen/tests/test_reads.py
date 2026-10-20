"""
The generated code, read through: the committed packages in `expected/`, run against the
recordings, so what the generator writes is checked against what the server sends. `mypy`
checks this file too, so a type the generator gets wrong fails there first.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import coho_delivery_sdk as runtime
import delivery_fixture
import inheritance
import traits
from coho_delivery_sdk import ContentConfig, ReleasedConfig, Unresolved, is_resolved, resolved
from delivery_fixture import Article, AsyncCoho, Citation, Coho, Figure
from replay import KEY, Replay

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
