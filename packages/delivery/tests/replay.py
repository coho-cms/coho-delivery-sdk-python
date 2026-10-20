"""Replays the spec's delivery recordings as an httpx transport, so tests check against what the server sends."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast
from urllib.parse import unquote

import httpx

from coho_delivery_sdk import EntryGraph

RECORDINGS = Path(__file__).resolve().parents[3] / "spec" / "delivery" / "recordings"

BASE = "https://delivery.test/v1/projects/p1"
KEY = "test-key"
OTHER_KEY = "other-key"


def recording(name: str) -> dict[str, Any]:
    return cast(
        dict[str, Any], json.loads((RECORDINGS / f"{name}.json").read_text(encoding="utf-8"))
    )


def graph(name: str) -> EntryGraph:
    """A recording's body, as the graph it is."""
    return cast(EntryGraph, recording(name)["response"]["body"])


def _normalize(path_and_query: str) -> str:
    """The path, and the query in name order and decoded, so equal requests compare equal."""
    path, _, query = path_and_query.partition("?")
    params = sorted(unquote(part) for part in query.split("&")) if query else []
    return f"{unquote(path)}?{'&'.join(params)}"


@dataclass
class Call:
    url: str
    headers: dict[str, str]


@dataclass
class Replay:
    """
    Answers from the recordings, as the server did, plus `304` for an `If-None-Match` naming
    the recording's ETag. Each recording's ETag is its name.
    """

    calls: list[Call] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._all = [
            (path.stem, recording(path.stem)) for path in sorted(RECORDINGS.glob("*.json"))
        ]

    def handle(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        headers = {name.lower(): value for name, value in request.headers.items()}
        self.calls.append(Call(url, headers))
        assert url.startswith(BASE), f"Not a delivery URL: {url}"

        authorization = headers.get("authorization")
        auth = (
            "none"
            if authorization is None
            else "key"
            if authorization == f"Bearer {KEY}"
            else "other-key"
        )
        wanted = _normalize(url[len(BASE) :])
        found = next(
            (
                (name, recorded)
                for name, recorded in self._all
                if recorded["request"]["auth"] == auth
                and _normalize(recorded["request"]["path"]) == wanted
            ),
            None,
        )
        if found is None:
            raise AssertionError(f"Nothing recorded for {auth} {wanted}")
        name, recorded = found

        response = recorded["response"]
        answer: dict[str, str] = {}
        for header in ("content-type", "cache-control"):
            if header in response["headers"]:
                answer[header] = response["headers"][header]
        etag = f'"{name}"' if response["headers"].get("etag") else None
        if etag is not None:
            answer["etag"] = etag
        if etag is not None and headers.get("if-none-match") == etag:
            return httpx.Response(304, headers=answer)
        return httpx.Response(
            response["status"], headers=answer, content=json.dumps(response["body"]).encode()
        )

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handle))

    def async_client(self) -> httpx.AsyncClient:
        def handle(request: httpx.Request) -> httpx.Response:
            return self.handle(request)

        return httpx.AsyncClient(transport=httpx.MockTransport(handle))


@dataclass
class Answering:
    """Answers every request with one response, recording what it was asked."""

    status: int = 200
    body: Any = field(
        default_factory=lambda: {"roots": [], "entries": {}, "unresolved": {}, "hasMore": False}
    )
    headers: dict[str, str] = field(default_factory=lambda: {"content-type": "application/json"})
    calls: list[Call] = field(default_factory=list)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(
            Call(str(request.url), {k.lower(): v for k, v in request.headers.items()})
        )
        content = self.body if isinstance(self.body, bytes) else json.dumps(self.body).encode()
        return httpx.Response(self.status, headers=self.headers, content=content)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handle))
