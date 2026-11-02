from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import coho_delivery_sdk
from coho_delivery_sdk import webhooks
from coho_delivery_sdk.webhooks import CohoWebhookError

SIGNATURES: dict[str, Any] = json.loads(
    (Path(__file__).resolve().parents[3] / "spec" / "webhooks" / "signatures.json").read_text(
        encoding="utf-8"
    )
)
CASES: list[dict[str, Any]] = SIGNATURES["cases"]


def at(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, UTC)


def named(name: str) -> dict[str, Any]:
    return next(case for case in CASES if case["name"] == name)


# THE SPEC'S CASES
# THE SPEC'S CASES
# THE SPEC'S CASES


@pytest.mark.parametrize("as_bytes", [False, True], ids=["str", "bytes"])
@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_the_spec_s_cases(case: dict[str, Any], as_bytes: bool) -> None:
    body: str | bytes = case["body"].encode("utf-8") if as_bytes else case["body"]

    def verify() -> webhooks.WebhookEvent:
        return webhooks.verify(
            body,
            case["headers"],
            case["secret"],
            now=at(case["now"]),
            tolerance_seconds=SIGNATURES["toleranceSeconds"],
        )

    if case["valid"]:
        assert verify() == json.loads(case["body"])
    else:
        with pytest.raises(CohoWebhookError) as refused:
            verify()
        assert refused.value.reason == case["reason"]


# THE EVENT
# THE EVENT
# THE EVENT


def test_an_accepted_request_answers_its_event() -> None:
    case = named("coho-event")
    event = webhooks.verify(case["body"], case["headers"], case["secret"], now=at(case["now"]))
    assert event["id"] == case["headers"]["webhook-id"]
    assert event["type"] == "environment.promoted"
    assert event["created_at"] == "2026-11-02T14:03:11.204Z"
    assert event["project"] == {
        "id": "4f6c0b9e-2a51-4d7e-9f0a-6b1c2d3e4f50",
        "name": "Café Zürich — site",
    }
    assert event["actor"]["kind"] == "person"
    assert event["data"]["environment"] == "prod"


def test_the_package_carries_the_module() -> None:
    assert coho_delivery_sdk.webhooks.verify is webhooks.verify


# SECRETS
# SECRETS
# SECRETS


def test_a_list_of_secrets_accepts_a_request_signed_with_any_one_of_them() -> None:
    case = named("coho-event")
    previous = named("wrong-secret")["secret"]
    now = at(case["now"])
    for secrets in ([previous, case["secret"]], (case["secret"], previous)):
        event = webhooks.verify(case["body"], case["headers"], secrets, now=now)
        assert event["id"] == case["headers"]["webhook-id"]
    with pytest.raises(CohoWebhookError) as refused:
        webhooks.verify(case["body"], case["headers"], [previous], now=now)
    assert refused.value.reason == "signature"


def test_a_secret_that_is_not_a_webhook_secret_is_the_receiver_s_mistake() -> None:
    case = named("coho-event")
    now = at(case["now"])
    secrets: list[str | list[str]] = [case["secret"].removeprefix("whsec_"), "whsec_not base64", []]
    for secret in secrets:
        with pytest.raises(ValueError):
            webhooks.verify(case["body"], case["headers"], secret, now=now)


# HEADERS
# HEADERS
# HEADERS


def test_header_names_are_matched_whatever_their_case() -> None:
    case = named("coho-event")
    shouted = {name.upper(): value for name, value in case["headers"].items()}
    titled = {name.title(): value for name, value in case["headers"].items()}
    for headers in (shouted, titled):
        event = webhooks.verify(case["body"], headers, case["secret"], now=at(case["now"]))
        assert event["id"] == case["headers"]["webhook-id"]


def test_an_empty_header_is_a_missing_one_and_the_refusal_names_it() -> None:
    case = named("coho-event")
    with pytest.raises(CohoWebhookError, match="webhook-id") as refused:
        webhooks.verify(
            case["body"], {**case["headers"], "webhook-id": ""}, case["secret"], now=at(case["now"])
        )
    assert refused.value.reason == "headers"


def test_a_timestamp_that_is_not_a_number_is_refused_for_its_timestamp() -> None:
    case = named("coho-event")
    with pytest.raises(CohoWebhookError) as refused:
        webhooks.verify(
            case["body"],
            {**case["headers"], "webhook-timestamp": "1793628191.0"},
            case["secret"],
            now=at(case["now"]),
        )
    assert refused.value.reason == "timestamp"


def test_the_tolerance_can_be_narrowed() -> None:
    case = named("coho-event")
    with pytest.raises(CohoWebhookError) as refused:
        webhooks.verify(
            case["body"], case["headers"], case["secret"], now=at(case["now"]), tolerance_seconds=10
        )
    assert refused.value.reason == "timestamp"
