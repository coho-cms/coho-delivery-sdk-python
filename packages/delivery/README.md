# coho-delivery-sdk

The Coho CMS delivery client, and the runtime your generated content library calls.

Most projects don't import this directly. They install their own content library, generated from their content types by [`coho-codegen`](https://pypi.org/project/coho-codegen/), which depends on this package and gives every content type its own Pydantic model and typed reads. Use this package directly for untyped access, or for anything the generated reads don't cover.

```bash
uv add coho-delivery-sdk
```

Python 3.11 or later. Built on [httpx](https://www.python-httpx.org/) and [Pydantic](https://docs.pydantic.dev/) 2, with a synchronous and an asynchronous client. Typed, and `mypy --strict` passes on it.

## Untyped reads

```python
import os

from coho_delivery_sdk import DeliveryClient, ReleasedConfig

delivery = DeliveryClient(
    ReleasedConfig(url="https://delivery.coho.example", project="0192…", key=os.environ["COHO_DELIVERY_KEY"])
)

home = delivery.entry_by_slug("prod", "home-page", depth=2, locale="en-US")
# {"roots": [id], "entries": {id: entry}, "unresolved": {id: "depth" | "absent"}}, or None
```

`entries`, `entry`, `entry_by_slug` and `entries_by_id` return the delivery API's response as it was sent: the entries you asked for in `roots`, everything they reference within `depth` hops in `entries`, and anything referenced but not returned in `unresolved`. `AsyncDeliveryClient` has the same reads, awaited.

## Hydrated reads

`ContentClient` returns entries as models, with their references replaced by the entries they point at. It is what generated libraries are built on.

```python
from typing import Literal

from pydantic import Field

import coho_delivery_sdk as runtime
from coho_delivery_sdk import ContentClient, ContentConfig, Link, TypeShape


# What a generated library declares for you.
class Author(runtime.EntryBase):
    type: Literal["author"] = Field(alias="_type")
    full_name: str = Field(alias="fullName")


class BlogPost(runtime.EntryBase):
    type: Literal["blogPost"] = Field(alias="_type")
    title: str | None = None
    author: runtime.Linked[Author] | None = None


content = ContentClient(
    ContentConfig(delivery=config, ref="prod", locale="en-US"),
    {
        "author": TypeShape(model=Author),
        "blogPost": TypeShape(model=BlogPost, links={"author": Link(many=False, targets=("author",))}),
    },
)

post = content.type("blogPost").by_slug("hello-world", depth=2)
if post is not None and isinstance(post.author, Author):
    print(post.author.full_name)
```

- **Entries are frozen Pydantic models**, with their fields beside the system values `id`, `type`, `slug` and `locale`. Fields are read by their Python names, and validated and serialized by Coho's own, so `model_dump()`, or an entry returned from a FastAPI route, has the shape delivery sent.
- **A reference is a `Linked[T]`**: its target, or an `Unresolved` stub saying why it is not there: `depth` when it is beyond the requested depth, `absent` when it is not on the ref, `cycle` where following it would loop back, `type` where the target is of a type the field does not link to, and `invalid` where it does not match its model. `resolved(post.tags)` gives the targets of a list of links that are here, leaving out the stubs.
- **A link to a base type holds its subtype.** Models are built from the leaves up, each as its own type, so a link to a `page` that is a landing page holds a `LandingPage`, and `isinstance` tells them apart.
- **A singleton is read with `get()`.** `content.singleton("siteSettings", "site-settings").get()` reads a type that has one entry on a ref (type model 1.7), by the slug its entry answers to, and is `None` before that entry is first written. Generated code passes the type model's `entrySlug`.
- **Problems are reported, not raised.** An entry missing a field its type always has, which happens to older entries after a field becomes required, takes the field's empty value, and is passed to `on_issue`, once per entry and field for the life of the client. The default is a warning on the `coho` logger.

## Released and unreleased content

What a client reads depends on its config.

| | `ReleasedConfig` | `PreviewConfig` |
|---|---|---|
| Refs | Tags, and environments pointing at one, such as `qa` and `prod` | Branches, and environments pointing at one, such as `dev` |
| Served by | Delivery, cached at the edge | Coho, live, never cached |
| `url` | Delivery's, such as `https://delivery.coho.example` | Coho's own, where you sign in, such as `https://api.coho.example` |
| Credential | `key`: a delivery key | `token`: a project token, `coho_pt_…`, with the viewer role, plus the `account` |

Both answer the same requests in the same shapes, so a preview runs the code production does. Create a token for previews with `coho token create --role viewer`, separate from any token your content library uses to pull its types.

**Keep both on the server.** A credential is sent as `Authorization: Bearer`, never in a URL, and a config's `repr` never shows it. A token reads everything unreleased.

### From the environment

`config_from_env` turns environment variables into a config, so whether a deployment previews or reads releases is a matter of its variables:

```python
import os

from coho_delivery_sdk import ContentClient, config_from_env

content = ContentClient(config_from_env(os.environ))
```

| Variable | |
|---|---|
| `COHO_PROJECT`, `COHO_REF` | Always |
| `COHO_LOCALE` | Optional |
| `COHO_DELIVERY_URL`, `COHO_DELIVERY_KEY` | Released content. The key may be left out for a public environment |
| `COHO_PREVIEW_TOKEN`, `COHO_URL`, `COHO_ACCOUNT` | A preview |

The names are the same in every Coho SDK. Setting a preview token and a delivery key together is refused, since they read different content.

## Assets

An asset field is read as an `Asset`: its `file` (media type, size, and for images width and height), `alt`, `focal_point`, and the URLs the asset CDN serves it at. It builds resized URLs with no request and no secret:

```python
post.hero.image(width=800, format="auto")                  # resized at the edge
post.hero.image(width=400, height=400, fit="fill")         # cropped around its focal point
post.hero.srcset(format="auto")                            # 640w … up to the original
post.hero.srcset(width=300, densities=[1, 2])              # 1x, 2x
post.brochure.download()                                   # the original, as an attachment
```

- **Only raster images resize** (`is_image`). An SVG, a PDF or any other file has only its original, which `image` and `srcset` return whatever the options. A field that accepts only raster images is an `ImageAsset`, whose `file` always has dimensions.
- **The edge snaps widths up** to `IMAGE_WIDTHS`, so a `srcset` built from them lands on cached images.
- **`download` asks the edge to send the file as an attachment**, under its own name, where `url` opens it in the browser.
- **An asset is as public as its URL**, drafts included, and deleting it does not stop the URL working.

## Assets in prose

A Markdown or HTML field names an asset by **slug** rather than by URL — `![A bridge](asset:bridge-at-dusk)` — so the body carries no asset domain, survives being moved between branches, and is seen by everything that counts a file as used. Coho records what the prose named in the entry's `body_assets`; `resolve_entry` turns one into the other.

```python
post = resolve_entry(reads.post.by_slug("a-bridge"))
post.body                                     # every asset: reference now a URL
resolve_prose(post.body, post.body_assets)    # or one body at a time
referenced_slug(value)                        # the slug a value references, or None
```

- **Resolve at the read**, once, rather than at each place a body is drawn: a body usually reaches more than one renderer, and the version none of them can forget is the one where the entry arrives. `resolve_entry` walks an entry to any depth — its own prose, its repeater items, and the entries it links, each against its own `body_assets` — and takes an untyped read's dict as readily as a model.
- **Never resolve a body you may write back.** A resolved body holds URLs, and saving one destroys the reference the scheme exists to keep: the asset stops counting as used, the link breaks when the file is replaced, and moving the entry to another project carries the old domain with it. Anything that edits content must keep the body exactly as delivered — which is why resolving is a call you make and not something a read does for you. The models are frozen, so what was delivered is still there either way.
- **A reference the entry does not carry is left as written**, so an image falls back to its alt text. That is an asset not merged onto this ref, or a slug typed by hand; rewriting it to nothing would hide it, and throwing would stop a page over one figure.
- **`src`, `href` and `poster` resolve**, in a Markdown link or directive and in an HTML field, and only when the whole value is the reference. `alt="asset:x"` and prose about the scheme are left alone.
- **A `srcset` still needs the asset.** The widths to offer and an image's own dimensions are the asset's, and Markdown has nowhere to put either, so a renderer that wants them matches the resolved URL back to an asset in `body_assets`.

## Caching

Each client keeps a private cache of responses, following `Cache-Control` and `ETag`. A tag named directly is fetched once. An environment is reused for its short `max-age`, then revalidated, which costs a `304` when nothing was promoted. A preview is fetched every time. Pass `cache_size=0` to turn it off. Each read parses its own copy, so no caller can change what another is served.

## Receiving webhooks

Coho signs each webhook request the way [Standard Webhooks](https://www.standardwebhooks.com) does. `webhooks.verify` checks the signature and the timestamp and answers the event, using only the standard library.

**Verify the body exactly as it arrived.** A body parsed and serialized again is not the one that was signed, and is refused, so read the raw bytes: `await request.body()` in FastAPI or Starlette, `request.get_data()` in Flask, never a parsed model or `request.json`.

```python
import os

from fastapi import FastAPI, HTTPException, Request, Response

from coho_delivery_sdk import webhooks

app = FastAPI()


@app.post("/hooks/coho")
async def coho_webhook(request: Request) -> Response:
    try:
        event = webhooks.verify(
            await request.body(), request.headers, os.environ["COHO_WEBHOOK_SECRET"]
        )
    except webhooks.CohoWebhookError as refused:
        raise HTTPException(400, refused.reason) from refused
    if event["type"] == "environment.promoted":
        ...
    return Response(status_code=204)
```

```python
# Flask
@app.post("/hooks/coho")
def coho_webhook():
    try:
        event = webhooks.verify(request.get_data(), request.headers, os.environ["COHO_WEBHOOK_SECRET"])
    except webhooks.CohoWebhookError as refused:
        return refused.reason, 400
    ...
    return "", 204
```

- **A refusal raises `CohoWebhookError`**, whose `reason` is `signature`, `timestamp`, or `headers`. Answer it `400`.
- **The timestamp must be within five minutes** of the receiver's clock, before or after, so a captured request cannot be replayed. `tolerance_seconds` changes the window, and `now` sets the clock, for tests.
- **While a secret is rotated, pass both**, `[current, previous]`. For 24 hours each request carries two signatures, one from each, and either is accepted.
- **Header names match whatever their case**, from a dict or anything with `items()`, such as Starlette's, Flask's, or Django's `request.headers`.
- **The event is as Coho sent it**, a `WebhookEvent` dict: `id`, `type`, `created_at`, `project`, `actor`, and `data`. Its `id` is the `webhook-id` header too, the same on every attempt, so drop an event already handled; events can arrive twice, and out of order. `data` holds identifiers and counts, never content: read the content itself through delivery.

## Errors

A refusal raises `CohoDeliveryError`. Branch on its `code`: `REF_NOT_FOUND`, `KEY_REQUIRED`, `PROJECT_NOT_FOUND`, `INVALID_QUERY` or `RESOLUTION_LIMIT` for the request; `ARTIFACT_UNREADABLE` or `POOL_UNAVAILABLE` for the server; or `UNEXPECTED_RESPONSE` for an answer that isn't a problem document. A preview adds `UNAUTHENTICATED`, for a token that has expired or been revoked, and `ACCOUNT_SUSPENDED`, `ACCOUNT_CLOSED` and `USER_SUSPENDED`. A missing entry is `None`, not an error.

## License

Apache-2.0
