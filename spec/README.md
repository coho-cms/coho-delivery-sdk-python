# coho-sdk-spec

The shared material every Coho SDK is built and tested against. Each language's SDK copies what it needs from a tagged release of this repository, so all of them agree with the server and with each other.

```
type-model/
├── type-model.schema.json   JSON Schema for the type model
└── fixtures/
    ├── cli-next-blog.json   the type model of the cli-next-blog sample
    ├── delivery-fixture.json   the type model of the delivery recordings' content
    ├── assets.json          asset fields, with number, json and a repeater
    ├── repeaters.json       component types, and repeaters that hold them
    ├── inheritance.json     types that extend others, abstract ones, and links to a base type
    └── traits.json          groups of fields that types take
delivery/
└── recordings/              what the delivery API answered to a fixed set of requests
```

Nothing here is edited by hand. Each file is produced by the Coho server's own code and copied here, so a fixture is exactly what a generator will receive.

## The type model

A language-neutral description of one branch's or tag's content types. Code generators read it and write typed code: one type per content type, with the right fields, optionality, and reference targets. The server has already applied Coho's rules, so a generator never works them out for itself.

### Rules for generators

- **Versioning.** `irVersion` is `major.minor`. Ignore keys you do not know. Refuse a major version you do not support, and name both versions in the error. A minor version only adds optional keys or field kinds.
- **Optionality comes from `presence` alone.** `always` means delivery always includes the field; `maybe` means it can be absent. A localized field is `maybe` even when required, because delivery leaves it out wherever the requested locale has no translation.
- **Choice values are open.** Content can hold a value added after the file was produced. Generated code must accept an unknown value and keep it, not fail: in TypeScript, `'a' | 'b' | (string & {})`; elsewhere, an explicit unknown member carrying the raw value.
- **References name types in the same file.** Every slug in a reference field's `of` is a key of `types`. An empty `of` means the link points at an entry whose type this branch or tag does not have; generate it as an untyped entry.
- **Asset fields** (`kind: asset`, since 1.1) hold files: delivery embeds each asset as an object (`id`, `title`, `alt`, `focalPoint`, `file`, `url`, and for raster images `imageUrl`), never as a link to follow. `many` makes it a list. `accept` lists the media types a linked file may be, or family wildcards such as `image/*`, and is empty for any. **A single asset field is nullable whatever its `presence`**: an asset deleted on the branch or tag is delivered as `null`. In a list, a deleted asset is left out, never `null`. A field whose `accept` names only raster images (`image/png`, `image/jpeg`, `image/gif`, `image/webp`, `image/avif`, `image/heic`) may be typed as an image that always has dimensions; `image/*` includes SVG, which has none.
- **Repeaters hold component types** (since 1.2). `components` is keyed by slug, the same shape as `types`, and every slug in a repeater's `of` is a key of it. Each item carries `_id`, its stable identity, and `_type`, the component's slug: discriminate on `_type`. Content can hold an item of a component added after the file was produced. Leave such an item out of the list, and report it, rather than type it as something it is not; the TypeScript runtime does this from the generated `shape`. An empty `of` means no component type is on this branch or tag; generate items as untyped objects with `_id`. Before 1.2 there is no `components`, and items are untyped.
- **Types extend types** (since 1.3). A type with a parent names it in `extends`, a key of the same map (`types` or `components`); `abstract: true` marks a type no entry is of itself, only its descendants. A type's `fields` already include everything it inherits, so a generator that ignores `extends` stays correct. A field it reaches exactly as its parent has it carries `inherited: true`, for a language that declares it on the parent alone; one the type tightens (a narrower `values`, `of` or `max`, or made required) does not. **Delivery lists a type's descendants with it**: `?type=page` returns every service page and landing page too, each with its own `_type`, so a read or a link of a base type should be typed as any of the concrete types in its family. A reference or repeater whose `of` names a base type holds its descendants too.
- **Types take traits** (since 1.4). A trait is a named group of fields, in the top-level `traits` map; it is never a type, so no entry is of one and no `of` names one. A type lists every trait it has, its ancestors' first, in `traits`, and already has their fields in its own `fields`, each marked `trait` and as the type has it, which may be tighter than the trait's own. A generator that ignores traits stays correct. One that reads them may declare each trait once, `interface Seo`, and declare that every type with it has it, so code written against a trait accepts any entry that has one.
- **Unknown field kinds are untyped.** If `kind` is one you do not know, emit the field as untyped and print a warning. Never fail.
- **Print `warnings`.** When present, each one names a type and field that need attention.
- **Fields hidden from the API are already gone.** Do not look for them.

### File form

The type model is two-space-indented JSON with `"key": value`, one array element per line, `[]` and `{}` when empty, and a trailing newline: the layout of `JSON.stringify(model, null, 2)`. Tooling that writes the file in that layout produces no diff.

`source.schemaHash` is the SHA-256 of `types`, serialized compactly in the order given, or of `{"types": …, "components": …}` when `components` is not empty. Equal hashes mean equal types, whichever branch or tag they came from.

## Delivery recordings

Each file is one request to the delivery API and its answer, recorded from the server running against a fixed set of content. A delivery SDK replays them as its HTTP layer, so its tests check it against what the server actually sends.

```json
{
  "request":  { "method": "GET", "path": "/v0.0.1/entries-by-slug/chain-1?depth=2&locale=en-US", "auth": "key" },
  "response": { "status": 200, "headers": { "content-type": "…", "cache-control": "…", "etag": true }, "body": { … } }
}
```

- `path` is relative to the project's base URL, `…/v1/projects/{project}`. Compare the query as a set: an SDK may send the same parameters in another order.
- `auth` is `key` for the project's delivery key, `none` for no `Authorization` header, and `other-key` for a valid key that grants a different project.
- `etag` says whether the response carried one. The value is not recorded, because it changes every time the content is rebuilt; a replaying SDK can make up its own.
- The content is a type, `article`, with a localized `title`, a `body`, an integer `rank`, and a `related` reference. Three entries, `chain-1` to `chain-3`, link in a loop, and `chain-2` also links to an entry that does not exist. Four more, `entry-1` to `entry-3` and `entry-fr`, carry translated titles. A second type, `notice`, declares an integer `priority` and a text `message`, and has no entries. A third, `figure`, has asset fields: `image` (images only), `poster` and a `gallery` list. `figure-1` links a JPEG with a focal point, an SVG, a PDF, and an asset that does not exist, in `poster` and in `gallery`. `figure` also has `sources`, a repeater of the component type `citation`, and `figure-2` holds two citations.

| Recording | What it shows |
|---|---|
| `entry-by-slug`, `entry-by-slug-depth-1`, `entry-by-slug-depth-2` | One entry's references at depths 0, 1 and 2: `depth` at the boundary, `absent` for the missing entry, and the loop back to the root |
| `entry-by-id-de` | A read by id, projected to `de-DE` |
| `entries-by-id` | A read of several ids, one of which does not exist |
| `entries-ordered` | A page ordered by `-rank`, with more to come |
| `entries-fr` | Every entry projected to `fr-FR`, where most titles are untranslated and so absent |
| `entries-empty-type` | A type with no entries, ordered by its declared field: an empty page, not a refusal |
| `entry-with-assets` | Assets embedded (delivery 2.1.0): an image with `imageUrl`, an SVG and a PDF without one, a missing asset as `null` in `poster` and left out of `gallery`, and the `warnings` that name it. The project id in URLs is `{project}` |
| `entry-with-repeater` | Repeater items as stored: each with its `_id` and `_type`, the second's `_type` filled in by the server on write |
| `entry-not-found`, `ref-not-found`, `invalid-query`, `key-required`, `project-not-found` | The refusals |

## Type model fixtures

| Fixture | Covers |
|---|---|
| `cli-next-blog` | text, longText (plain and markdown), choice, multichoice, datetime, integer, boolean, localized fields, single and many references, and a type that references itself |
| `delivery-fixture` | The types of the delivery recordings' content, `article`, `notice` and `figure`, and the component `citation`, so a generator's output can be run against the recordings |
| `assets` | asset fields (single and many, image-only and any file), `number`, `json`, and a repeater whose components are not on the tag |
| `repeaters` | component types (1.2): a single-component repeater of `citation`, and a required repeater holding two components and one not on the tag |
| `traits` | traits (1.4): `seo` taken by `page` and inherited by `article`, which tightens its meta title, and `publishing` and `socialCard` taken by `article`, `socialCard` by an unrelated `person` too |
| `inheritance` | type inheritance (1.3): an abstract `page`, `servicePage` and `landingPage` extending it, `premiumService` extending `servicePage` with a narrower choice, a `menu` linking to `page` and to `servicePage`, and an abstract component `block` with two components extending it, held by a repeater of `block` |

## License

Apache-2.0
