# coho-codegen

Generates a typed content library from your Coho CMS content types: a Pydantic model per content type, and a client whose reads return them. And creates that library, from the template.

It belongs in your content library, the package your sites and services install, as a development dependency beside [`coho-delivery-sdk`](https://pypi.org/project/coho-delivery-sdk/). `coho-codegen create` sets that library up for you:

```bash
uvx coho-codegen create acme-content
cd acme-content
uv sync
uv run coho-codegen init --url https://app.coho.example --ref v1.4.0
```

## Commands

```bash
coho-codegen create <dir>  # a new content library from the template, named after <dir>
coho-codegen init          # point the library at a project: asks Coho whose token it is
coho-codegen pull          # fetch the type model for the configured ref into coho-ir.json
coho-codegen generate      # write the library's coho/ package from coho-ir.json
coho-codegen check         # fail if coho/ differs from what generate would write
```

Commit `coho-ir.json` and the generated package. `generate` removes the modules of types no longer on the ref, and leaves anything it did not write. A schema change then shows up as a diff in review, and `check` in CI catches generated code that is out of date. `generate` and `check` never call the server.

`init` and `pull` need a project token with read access, `coho token create --role viewer`. `init` takes it with `--token`, from `COHO_TOKEN`, or by asking, checks it with Coho, writes the account and project it is for into the config, and the token into `.env`. `pull` reads `COHO_TOKEN` from the environment, or for local runs from a `.env` beside the config, and never from the config itself. Keep it in CI secrets and out of every app that installs the library. `pull --ref v1.4.0` pulls another tag than the config names. An unchanged type model costs a `304`.

## Configuration

`coho.config.json`, beside the library's `pyproject.toml`. Paths are relative to it.

```json
{
  "url": "https://app.coho.example",
  "account": "0192…",
  "project": "0192…",
  "ref": "v1.4.0",
  "typeModel": "coho-ir.json",
  "outDir": "src/acme_content/coho"
}
```

Generate from a tag for a release. A branch's types can change, and `generate` warns when the model came from one.

## What is generated

```python
import os

from coho_delivery_sdk import config_from_env
from acme_content import Coho, resolved

coho = Coho(config_from_env(os.environ))

post = coho.blog_post.by_slug("hello-world", depth=2)
latest = coho.blog_post.list(order="-publishedAt", limit=3)
```

- **One model per content type, in its own module**, named from its slug: `blogPost` becomes `BlogPost`, in `blog_post.py`. The package's `__init__.py` exports them all, with `Coho` and `AsyncCoho`, the same reads awaited. Each model derives from `EntryBase`, with `id`, `type`, `slug` and `locale` beside its fields.
- **Fields have Python names, aliased to Coho's**: `publishedAt` is `published_at`. A field whose name would be a keyword, a system value or one of Pydantic's gets `_` after it, `class_`, and keeps its id on the wire.
- **A field is optional when delivery can leave it out**, which includes every localized field. A list is never `None`: it is empty. A choice is a `Literal` of its values, or any other `str`, so a value added after generation never fails to validate.
- **References are typed by their targets**: `Linked[TeamMember]`, which is the entry, or a stub saying why it is not there.
- **An asset field is an `Asset | None`**, or a `list[Asset]` when it holds several, and an `ImageAsset` when it accepts only raster images, which always have dimensions and resize. A single asset is optional even when required, because an asset deleted on the ref is delivered as `None`; in a list it is left out.
- **A repeater holds typed items.** Each component type is a model of its own, `Citation` in `citation.py`, deriving from `ItemBase`, and a repeater is a list of them: `list[Citation]`, or `list[Callout | Quote]` when it holds several. An item of a component added after the code was generated is left out of the list, and reported. A repeater whose components are not on the ref holds `RepeaterItem`s.
- **A type that extends another derives from its model.** `class ServicePage(Page)` declares only what it adds or tightens. A type that others extend is read and linked as its family, `AnyPage = Page | ServicePage | …`, and each entry comes back as its own model, so `isinstance` tells them apart.
- **A trait is a `Protocol`** of the fields it declares, `Seo` in `seo.py`, which every type with it satisfies, to `mypy` and to `isinstance`. So a function that takes a `Seo` takes an entry of any type with the trait.
- **`order` accepts only fields the type can be sorted by**: `BlogPostOrder`, a `Literal` of each sortable field and its `-` descending form, so an unsortable order is a type error rather than a refused request.
- **`AnyEntry`** is the union of every type an entry can be; `content_types` lists their slugs; `source` names the ref and schema the code was generated from.
- **The library reads no environment.** The app passes its config to `Coho`.

If a type's name would collide with one the generated code defines (`Coho`, `AsyncCoho`, `AnyEntry`, `Linked`, `Unresolved`, `RepeaterItem`), its model gets `Entry` after it. A type read as one of `Coho`'s own members (`by_slug`, `by_id`, `by_ids`, `content`, `close`, `aclose`) is read as `coho.<name>_type`. A family whose `Any<Type>` name a type already has is named `<Type>Family`. `generate` says when any of these happens.

## License

Apache-2.0
