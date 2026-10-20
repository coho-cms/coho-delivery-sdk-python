from __future__ import annotations

import asyncio

import httpx
import pytest

from coho_delivery_sdk import (
    AsyncDeliveryClient,
    CohoDeliveryError,
    DeliveryClient,
    MountedConfig,
    PreviewConfig,
    ReleasedConfig,
)
from coho_delivery_sdk import cache as caching
from replay import KEY, OTHER_KEY, Answering, Replay, graph

# REQUESTS
# REQUESTS
# REQUESTS


def test_requests_go_to_the_contracts_paths_with_the_key_in_a_header_and_the_parameters_in_name_order() -> (
    None
):
    answering = Answering()
    client = DeliveryClient(
        ReleasedConfig(url="https://delivery.test/", project="p1", key="secret"),
        http_client=answering.client(),
        cache_size=0,
    )

    client.entries("v1.0.0", type="article", order="-rank", limit=3, locale="en-US")
    client.entry_by_slug("release/1", "a b")
    client.entries_by_id("prod", ["id-2", "id-1"], depth=1)

    assert [call.url for call in answering.calls] == [
        "https://delivery.test/v1/projects/p1/v1.0.0/entries?limit=3&locale=en-US&order=-rank&type=article",
        "https://delivery.test/v1/projects/p1/release%2F1/entries-by-slug/a%20b",
        "https://delivery.test/v1/projects/p1/prod/entries-by-id?depth=1&ids=id-2,id-1",
    ]
    for call in answering.calls:
        assert call.headers["authorization"] == "Bearer secret"
        assert "secret" not in call.url


def test_a_base_url_replaces_the_url_and_project_for_mounts_they_cannot_express() -> None:
    answering = Answering()
    client = DeliveryClient(
        MountedConfig(base_url="https://proxy.test/coho/v1/projects/p1/"),
        http_client=answering.client(),
        cache_size=0,
    )

    client.entries("prod")

    assert answering.calls[0].url == "https://proxy.test/coho/v1/projects/p1/prod/entries"
    assert "authorization" not in answering.calls[0].headers


def test_no_ids_asks_nothing() -> None:
    answering = Answering()
    client = DeliveryClient(
        ReleasedConfig(url="https://delivery.test", project="p1"), http_client=answering.client()
    )

    assert client.entries_by_id("prod", []) == {"roots": [], "entries": {}, "unresolved": {}}
    assert answering.calls == []


def test_a_config_never_prints_its_credential() -> None:
    assert "secret" not in repr(
        ReleasedConfig(url="https://delivery.test", project="p1", key="secret")
    )
    assert TOKEN not in repr(
        PreviewConfig(url="https://coho.test", account="acme", project="p1", token=TOKEN)
    )


# PREVIEWS
# PREVIEWS
# PREVIEWS

TOKEN = f"coho_pt_{'a' * 43}"


def test_a_preview_reads_through_cohos_preview_mount_with_the_token_in_a_header() -> None:
    answering = Answering(headers={"content-type": "application/json", "cache-control": "no-cache"})
    client = DeliveryClient(
        PreviewConfig(url="https://coho.test/", account="acme", project="p1", token=TOKEN),
        http_client=answering.client(),
    )

    client.entries("dev", type="article", locale="en-US")
    client.entry_by_slug("feature/x", "hello")

    assert [call.url for call in answering.calls] == [
        "https://coho.test/api/v1/accounts/acme/projects/p1/preview/dev/entries?locale=en-US&type=article",
        "https://coho.test/api/v1/accounts/acme/projects/p1/preview/feature%2Fx/entries-by-slug/hello",
    ]
    for call in answering.calls:
        assert call.headers["authorization"] == f"Bearer {TOKEN}"
        assert TOKEN not in call.url


def test_a_preview_is_never_answered_from_the_cache() -> None:
    answering = Answering(headers={"content-type": "application/json", "cache-control": "no-cache"})
    client = DeliveryClient(
        PreviewConfig(url="https://coho.test", account="acme", project="p1", token=TOKEN),
        http_client=answering.client(),
    )

    client.entries("dev")
    client.entries("dev")

    assert len(answering.calls) == 2
    assert "if-none-match" not in answering.calls[1].headers


def test_a_preview_takes_a_project_token() -> None:
    with pytest.raises(ValueError, match="starting coho_pt_"):
        PreviewConfig(url="https://coho.test", account="acme", project="p1", token="eyJhbGciOi")


# REPLAYED
# REPLAYED
# REPLAYED


def released(replay: Replay, key: str | None = KEY) -> DeliveryClient:
    return DeliveryClient(
        ReleasedConfig(url="https://delivery.test", project="p1", key=key),
        http_client=replay.client(),
    )


def test_reads_return_the_graph_as_delivery_sent_it() -> None:
    replay = Replay()
    client = released(replay)

    assert client.entry_by_slug("v0.0.1", "chain-1", depth=2, locale="en-US") == graph(
        "entry-by-slug-depth-2"
    )
    assert client.entries(
        "v0.0.1", type="article", order="-rank", limit=3, locale="en-US"
    ) == graph("entries-ordered")
    assert client.entry(
        "v0.0.1", "00000000-0000-7000-8000-0000000000c3", depth=1, locale="de-DE"
    ) == graph("entry-by-id-de")


def test_a_missing_entry_is_none_not_an_error() -> None:
    assert released(Replay()).entry_by_slug("v0.0.1", "nope") is None


def test_a_ref_delivery_does_not_serve_says_to_preview_it() -> None:
    with pytest.raises(CohoDeliveryError) as raised:
        released(Replay()).entries("v9.9.9")

    assert (raised.value.status, raised.value.code) == (404, "REF_NOT_FOUND")
    assert "with a project token" in str(raised.value)
    assert raised.value.problem is not None


def test_an_unsortable_order_is_an_invalid_query() -> None:
    with pytest.raises(CohoDeliveryError) as raised:
        released(Replay()).entries("v0.0.1", order="rank")

    assert raised.value.code == "INVALID_QUERY"


def test_no_key_where_one_is_needed_is_key_required() -> None:
    with pytest.raises(CohoDeliveryError) as raised:
        released(Replay(), key=None).entries("v0.0.1")

    assert raised.value.code == "KEY_REQUIRED"


def test_a_key_for_another_project_is_answered_as_no_such_project() -> None:
    with pytest.raises(CohoDeliveryError) as raised:
        released(Replay(), key=OTHER_KEY).entries("v0.0.1")

    assert raised.value.code == "PROJECT_NOT_FOUND"
    assert "issued for this project" in str(raised.value)


def test_an_answer_that_is_not_a_problem_document_is_unexpected() -> None:
    answering = Answering(
        status=502, body=b"<html>Bad gateway</html>", headers={"content-type": "text/html"}
    )
    client = DeliveryClient(
        ReleasedConfig(url="https://delivery.test", project="p1"), http_client=answering.client()
    )

    with pytest.raises(CohoDeliveryError) as raised:
        client.entries("prod")

    assert (raised.value.status, raised.value.code) == (502, "UNEXPECTED_RESPONSE")


# CACHING
# CACHING
# CACHING


def test_a_tag_is_fetched_once() -> None:
    replay = Replay()
    client = released(replay)

    first = client.entry_by_slug("v0.0.1", "chain-1", depth=1, locale="en-US")
    second = client.entry_by_slug("v0.0.1", "chain-1", depth=1, locale="en-US")

    assert first == second
    assert len(replay.calls) == 1


def test_each_read_gets_its_own_copy() -> None:
    replay = Replay()
    client = released(replay)

    first = client.entry_by_slug("v0.0.1", "chain-1", depth=1, locale="en-US")
    assert first is not None
    first["roots"].clear()

    second = client.entry_by_slug("v0.0.1", "chain-1", depth=1, locale="en-US")
    assert second is not None and second["roots"] != []


def test_a_stale_answer_is_revalidated_and_a_304_reuses_it(monkeypatch: pytest.MonkeyPatch) -> None:
    replay = Replay()
    client = released(replay)
    client.entry_by_slug("v0.0.1", "chain-1", depth=1, locale="en-US")

    # A year and a day later, the tag's answer is stale, so the client asks again.
    later = caching.now() + 366 * 24 * 3600
    monkeypatch.setattr(caching, "now", lambda: later)
    again = client.entry_by_slug("v0.0.1", "chain-1", depth=1, locale="en-US")

    assert again == graph("entry-by-slug-depth-1")
    assert replay.calls[1].headers["if-none-match"] == '"entry-by-slug-depth-1"'


def test_cache_size_0_turns_the_cache_off() -> None:
    replay = Replay()
    client = DeliveryClient(
        ReleasedConfig(url="https://delivery.test", project="p1", key=KEY),
        http_client=replay.client(),
        cache_size=0,
    )

    client.entry_by_slug("v0.0.1", "chain-1", depth=1, locale="en-US")
    client.entry_by_slug("v0.0.1", "chain-1", depth=1, locale="en-US")

    assert len(replay.calls) == 2


def test_fresh_until_follows_cache_control() -> None:
    assert caching.fresh_until("no-store", 100) is None
    assert caching.fresh_until("no-cache, max-age=60", 100) == 100
    assert caching.fresh_until("public, max-age=60", 100) == 160
    assert caching.fresh_until(None, 100) == 100


# ASYNC
# ASYNC
# ASYNC


def test_the_async_client_reads_the_same() -> None:
    replay = Replay()

    async def read() -> object:
        async with AsyncDeliveryClient(
            ReleasedConfig(url="https://delivery.test", project="p1", key=KEY),
            http_client=replay.async_client(),
        ) as client:
            return await client.entry_by_slug("v0.0.1", "chain-1", depth=2, locale="en-US")

    assert asyncio.run(read()) == graph("entry-by-slug-depth-2")


def test_closing_leaves_a_client_passed_in_open() -> None:
    http = httpx.Client(transport=httpx.MockTransport(Answering().handle))
    with DeliveryClient(
        ReleasedConfig(url="https://delivery.test", project="p1"), http_client=http
    ) as client:
        client.entries("prod")
    assert not http.is_closed
