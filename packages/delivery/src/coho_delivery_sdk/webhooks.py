"""
Receiving Coho's webhooks: `verify` checks that a request is Coho's, signed as Standard
Webhooks signs, and answers its event.

```python
from coho_delivery_sdk import webhooks

event = webhooks.verify(body, headers, secret)
```
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import time
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any, Literal, NotRequired, Protocol, TypedDict, cast

__all__ = [
    "TOLERANCE_SECONDS",
    "CohoWebhookError",
    "Refusal",
    "WebhookActor",
    "WebhookEvent",
    "WebhookHeaders",
    "WebhookProject",
    "verify",
]

TOLERANCE_SECONDS = 300
"""How far `webhook-timestamp` may be from the receiver's clock, either way, by default."""

_HEADERS = ("webhook-id", "webhook-timestamp", "webhook-signature")
_SECRET = re.compile(r"whsec_([A-Za-z0-9+/]+={0,2})")
_DIGITS = re.compile(r"[0-9]+")


class WebhookProject(TypedDict):
    """The project an event happened in."""

    id: str
    name: str


class WebhookActor(TypedDict):
    """Who made the change an event reports."""

    kind: str
    """
    `person`, `token` (a project token), or `system` (a sweep, a builder, or Coho's support).
    Open, so a kind the server adds later still parses.
    """

    id: str

    label: NotRequired[str]
    """A token's label. A person is named by id alone, never by an email address."""


class WebhookEvent(TypedDict):
    """
    One webhook event, as Coho sent it (coho-data doc 70 §2.1). `id` is the `webhook-id`
    header too, the same on every attempt and redelivery, so drop an event already handled.
    """

    id: str

    type: str
    """Such as `environment.promoted`, `tag.ready`, or `entries.changed`."""

    created_at: str
    """ISO 8601, in UTC."""

    project: WebhookProject
    actor: WebhookActor

    data: dict[str, Any]
    """
    The event's own values: identifiers and counts only, never content. Read the content
    itself through delivery, which always gives its current state.
    """


Refusal = Literal["signature", "timestamp", "headers"]
"""
Why a request was refused: `headers` when `webhook-id`, `webhook-timestamp`, or
`webhook-signature` is missing; `timestamp` when it was signed too long before or after now;
`signature` when no signature matches any secret.
"""


class CohoWebhookError(Exception):
    """A webhook request that did not come from Coho, or not recently. Answer it `400`."""

    reason: Refusal

    def __init__(self, reason: Refusal, message: str):
        super().__init__(message)
        self.reason = reason


class WebhookHeaders(Protocol):
    """
    Request headers: anything with `items()`, such as a dict, Starlette's and FastAPI's
    `request.headers`, Flask's and Django's.
    """

    def items(self) -> Iterable[tuple[str, str]]: ...


def verify(
    body: str | bytes,
    headers: WebhookHeaders,
    secret: str | Sequence[str],
    *,
    now: datetime | None = None,
    tolerance_seconds: float = TOLERANCE_SECONDS,
) -> WebhookEvent:
    """
    Checks that a webhook request is Coho's, and answers its event.

    Pass the body exactly as it was received, as bytes or a string. A body parsed and
    serialized again is not the body that was signed, and is refused. `secret` is the
    endpoint's, `whsec_…`; while one is being rotated, pass both, and a request signed with
    either is accepted. Header names are matched whatever their case.

    `now` is the receiver's time, the clock's by default; pass one for tests. A
    `webhook-timestamp` more than `tolerance_seconds` from it, before or after, is refused,
    so a captured request cannot be replayed.

    Raises `CohoWebhookError`, with its `reason`, when the request is refused, and
    `ValueError` when a secret is not a webhook secret, which is a mistake in the receiver,
    not in the request.
    """
    keys = [_secret_key(one) for one in ([secret] if isinstance(secret, str) else secret)]
    if not keys:
        raise ValueError("Coho: webhooks.verify needs a secret")

    found = _find(headers)
    missing = [name for name in _HEADERS if name not in found]
    if missing:
        raise CohoWebhookError(
            "headers", f"Coho: the webhook request has no {' or '.join(missing)} header"
        )
    id_, timestamp, signatures = (found[name] for name in _HEADERS)

    current = int(now.timestamp() if now is not None else time.time())
    if _DIGITS.fullmatch(timestamp) is None or abs(current - int(timestamp)) > tolerance_seconds:
        raise CohoWebhookError(
            "timestamp",
            f"Coho: the webhook request was signed at {timestamp}, more than "
            f"{tolerance_seconds} seconds from now ({current})",
        )

    raw = body.encode("utf-8") if isinstance(body, str) else body
    message = f"{id_}.{timestamp}.".encode() + raw
    offered = [
        signature.removeprefix("v1,").encode("utf-8")
        for signature in signatures.split(" ")
        if signature.startswith("v1,")
    ]
    for key in keys:
        expected = base64.b64encode(hmac.new(key, message, hashlib.sha256).digest())
        if any(hmac.compare_digest(signature, expected) for signature in offered):
            return cast(WebhookEvent, json.loads(raw))
    raise CohoWebhookError(
        "signature", "Coho: no signature on the webhook request matches its secret"
    )


def _secret_key(secret: str) -> bytes:
    """The HMAC key a `whsec_` secret holds, in base64."""
    matched = _SECRET.fullmatch(secret)
    if matched is None:
        raise ValueError("Coho: a webhook secret is whsec_ and its key in base64")
    try:
        return base64.b64decode(matched[1], validate=True)
    except binascii.Error as error:
        raise ValueError("Coho: a webhook secret is whsec_ and its key in base64") from error


def _find(headers: WebhookHeaders) -> dict[str, str]:
    """
    The webhook headers, by their names in lower case, leaving out an empty one. A header
    sent twice has its values joined with a space.
    """
    found: dict[str, str] = {}
    for name, value in headers.items():
        lower = name.lower()
        if lower in _HEADERS and value:
            found[lower] = f"{found[lower]} {value}" if lower in found else value
    return found
