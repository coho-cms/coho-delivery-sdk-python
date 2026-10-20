# coho-delivery-sdk-python

Python packages for reading content from Coho CMS.

| Package | What it is |
|---|---|
| [`coho-delivery-sdk`](packages/delivery) | The delivery client, and the runtime generated content libraries call |
| [`coho-codegen`](packages/codegen) | Generates a typed content library of Pydantic models from your project's content types, and creates one from the template |

To read your content, start with a content library: `uvx coho-codegen create acme-content`
makes one from [coho-template-python](https://github.com/coho-cms/coho-template-python). The
[FastAPI tutorial](https://github.com/coho-cms/coho-samples/tree/HEAD/python/cli-fastapi-blog)
walks through it, from a content model to a web service.

> **Delivery, not management.** These packages read published and preview content with a
> delivery key or a project token, and cannot change anything. Authoring, branching and
> releasing are [coho-management-sdk-python](https://github.com/coho-cms/coho-management-sdk-python)'s,
> which takes a person's credential and belongs in tools and CI, never in a website.

## Development

[uv](https://docs.astral.sh/uv/), and Python 3.11 or later.

```bash
uv sync
uv run pytest
uv run mypy
uv run ruff check .
uv run ruff format --check .
```

`make check` runs all four checks. `spec/` is a copy of
[coho-sdk-spec](https://github.com/coho-cms/coho-sdk-spec): recorded delivery responses and
type model fixtures, produced by the Coho server. The tests run against it, so these packages
agree with the server and with Coho's other SDKs. Don't edit it by hand.

`packages/codegen/tests/expected` holds what the generator writes for each type model
fixture. The tests compare the generator's output with it byte for byte, read the recordings
through it, and `mypy` checks it, so generated code is type-checked on every change. After
changing the generator, rewrite it and review the diff:

```bash
uv run python packages/codegen/scripts/expected.py
```

To try `coho-codegen create` from a checkout, pass `--template`, or bundle a template into it
as the publish workflow does:

```bash
make bundle TEMPLATE=../coho-template-python
```

## Publishing

The two packages are published to PyPI together, at one version: a library `coho-codegen`
creates is pinned to that version of both, and the template is bundled inside it.

1. Set the same new version in both `packages/*/pyproject.toml`, such as `2026.1.1`, and
   merge.
2. Tag [coho-template-python](https://github.com/coho-cms/coho-template-python) at the
   commit to ship, `release-v2026.1.1`.
3. Tag this repository at the release commit, `release-v2026.1.1`. The **Publish** workflow
   tests, bundles the template from its tag of the same name, builds both packages and
   publishes them. `release-v2026.2.0a1` publishes the prerelease `2026.2.0a1`.

Versions are year.release, as in Coho's other SDKs: a fix is a patch, `2026.1.1`, and a
change that breaks a generated library or the runtime's API is the next release,
`2026.2.0`, which a library's `~=2026.1.0` pin does not take.

A version cannot be published twice. The workflow publishes as a PyPI trusted publisher, in
the `pypi` environment, for both projects; no token is stored.

## License

Apache-2.0
