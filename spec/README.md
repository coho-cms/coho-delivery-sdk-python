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
    ├── traits.json          groups of fields that types take
    ├── lists.json           lists of text, numbers, and date-times, localized and not
    ├── nested.json          items inside items, and a component that holds itself
    └── singletons.json      types with one entry, one of them extending another type
delivery/
└── recordings/              what the delivery API answered to a fixed set of requests
webhooks/
└── signatures.json          webhook requests a receiver must accept and refuse
```

Nothing here is edited by hand. Each file is produced by the Coho server's own code and copied here, so a fixture is exactly what a generator will receive.

## The type model

A language-neutral description of one branch's or tag's content types. Code generators read it and write typed code: one type per content type, with the right fields, optionality, and reference targets. The server has already applied Coho's rules, so a generator never works them out for itself.

### Rules for generators

- **Versioning.** `irVersion` is `major.minor`. Ignore keys you do not know. Refuse a major version you do not support, and name both versions in the error. A minor version only adds optional keys or field kinds.
- **Optionality comes from `presence` alone.** `always` means delivery always includes the field; `maybe` means it can be absent. A localized field is `maybe` even when required, because delivery leaves it out wherever the requested locale has no translation.
- **Choice values are open.** Content can hold a value added after the file was produced. Generated code must accept an unknown value and keep it, not fail: in TypeScript, `'a' | 'b' | (string & {})`; elsewhere, an explicit unknown member carrying the raw value.
- **References name types in the same file.** Every slug in a reference field's `of` is a key of `types`. An empty `of` means the link points at an entry whose type this branch or tag does not have; generate it as an untyped entry.
- **Asset fields** (`kind: asset`, since 1.1) hold files: delivery embeds each asset as an object (`id`, `slug` since delivery 2.3.0, `title`, `alt`, `focalPoint`, `file`, `url`, and for raster images `imageUrl`), never as a link to follow. `many` makes it a list. `accept` lists the media types a linked file may be, or family wildcards such as `image/*`, and is empty for any. **A single asset field is nullable whatever its `presence`**: an asset deleted on the branch or tag is delivered as `null`. In a list, a deleted asset is left out, never `null`. A field whose `accept` names only raster images (`image/png`, `image/jpeg`, `image/gif`, `image/webp`, `image/avif`, `image/heic`) may be typed as an image that always has dimensions; `image/*` includes SVG, which has none.
- **Repeaters hold component types** (since 1.2). `components` is keyed by slug, the same shape as `types`, and every slug in a repeater's `of` is a key of it. Each item carries `_id`, its stable identity, and `_type`, the component's slug: discriminate on `_type`. Content can hold an item of a component added after the file was produced. Leave such an item out of the list, and report it, rather than type it as something it is not; the TypeScript runtime does this from the generated `shape`. An empty `of` means no component type is on this branch or tag; generate items as untyped objects with `_id`. Before 1.2 there is no `components`, and items are untyped.
- **Types extend types** (since 1.3). A type with a parent names it in `extends`, a key of the same map (`types` or `components`); `abstract: true` marks a type no entry is of itself, only its descendants. A type's `fields` already include everything it inherits, so a generator that ignores `extends` stays correct. A field it reaches exactly as its parent has it carries `inherited: true`, for a language that declares it on the parent alone; one the type tightens (a narrower `values`, `of` or `max`, or made required) does not. **Delivery lists a type's descendants with it**: `?type=page` returns every service page and landing page too, each with its own `_type`, so a read or a link of a base type should be typed as any of the concrete types in its family. A reference or repeater whose `of` names a base type holds its descendants too.
- **Types take traits** (since 1.4). A trait is a named group of fields, in the top-level `traits` map; it is never a type, so no entry is of one and no `of` names one. A type lists every trait it has, its ancestors' first, in `traits`, and already has their fields in its own `fields`, each marked `trait` and as the type has it, which may be tighter than the trait's own. A generator that ignores traits stays correct. One that reads them may declare each trait once, `interface Seo`, and declare that every type with it has it, so code written against a trait accepts any entry that has one.
- **Lists are their own kind** (since 1.5). A field of `kind: list` is an array of plain values, each of the kind in `item`: `text`, `integer`, `number`, or `datetime`. Type it as a list of that kind (`readonly string[]` in TypeScript). `min` and `max` count its values. A localized list is delivered as the requested locale's array, and an empty array is a value, "none in this locale", where an untranslated locale leaves the field out, so `presence` still decides optionality. **Keep the two apart in generated code**: a missing localized list is absent (`undefined`, `None`, `null`), never an empty list, so "not translated" and "none here" read differently. A missing list that is not localized may read as empty, as a list of links does. A list is never sortable. References and assets keep `many`: a list is a kind of its own so that a generator that predates it types the field untyped, never wrongly as one value.
- **Component fields can be localized.** Delivery projects a localized field inside a repeater's item exactly as at the top level: one locale's value, absent where that locale has none. Such a field is `maybe`, as any localized field is, and needs nothing new from a generator.
- **Items hold items** (since 1.6). A component's field may be a repeater, so an item holds items, and a component may hold itself: a `menuItem` whose `children` are `menuItem`s. Generate a recursive type where the model recurses. Delivery projects localized fields at every level, and an entry nests items 5 deep at most. **Filter and hydrate at every level**: leave out an item of a component the code was not generated with wherever it is, not only in a content type's own repeaters, and report it, so a nested item is never typed as something it is not. Nothing in the shape changes, so a generator that predates 1.6 still types nested items, but filters only the first level.
- **A singleton has one entry** (since 1.7). `singleton: true` marks a content type with at most one entry on a ref, and `entrySlug` is the slug that entry answers to: the type's slug in kebab case, `siteSettings` to `site-settings`. Use `entrySlug`; do not derive it. Generate one getter in place of the type's list and read by slug. It reads `entries-by-slug/{entrySlug}` and returns the entry, typed as the type, or nothing before the entry is first written on the ref, as for any missing slug. A singleton is never abstract and never a component, and no type extends it, but it may extend a type, so a read of its parent still includes its entry. Delivery has no route of its own for it. A generator that predates 1.7 types a singleton as an ordinary type, which is still correct.
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
- **`_bodyAssets` is a system key on the entry** (since delivery 2.3.0), beside `_id`, `_type`, `_slug` and `_locale`: the assets this entry's prose names, embedded exactly as an asset field's are. A Markdown or HTML field names an asset by slug — `![A bridge](asset:bridge)` — rather than by URL, so the body carries no asset domain and survives being moved between branches. Nothing in the type model declares it, because no content type does; read it off the entry, as an SDK reads `_slug`. Empty, or absent, on an entry whose prose names nothing.
- **Resolving a reference is the SDK's job, and belongs at the read.** Replace `asset:<slug>` with that asset's `url` where the entry arrives, matching the slug against the entry's **own** `_bodyAssets` — a linked entry read in the same graph carries its own list, so a page must not resolve a linked entry's figures against the outer one's. A slug the entry does not carry is left exactly as written, never blanked and never an error: an image then falls back to its alt text. ⛔ **Never resolve a body that may be written back**: a resolved body holds URLs, and saving one destroys the reference, so resolution is something a caller asks for and never something a read does on its own. Resolve `src`, `href` and `poster`, in a Markdown link or directive and in an HTML field, and only where the whole attribute value is the reference, so `alt="asset:x"` and prose about the scheme are left alone. A slug is `[A-Za-z0-9][A-Za-z0-9._-]*`.
- The content is a type, `article`, with a localized `title`, a `body`, an integer `rank`, and a `related` reference. Three entries, `chain-1` to `chain-3`, link in a loop, and `chain-2` also links to an entry that does not exist. Four more, `entry-1` to `entry-3` and `entry-fr`, carry translated titles. A second type, `notice`, declares an integer `priority` and a text `message`, and has no entries. A third, `figure`, has asset fields: `image` (images only), `poster` and a `gallery` list, and a markdown `body`. `figure-1` links a JPEG with a focal point, an SVG, a PDF, and an asset that does not exist, in `poster` and in `gallery`, and its `body` names the JPEG in prose as `asset:bridge`. `figure` also has `sources`, a repeater of the component type `citation`, and `figure-2` holds two citations. And `figure` has `steps`, a repeater of the component `step`, whose `label` is localized, `keywords`, a localized list of text, and `sizes`, a list of integers: `figure-3` has two steps, one labelled in `en-US` and `de-DE`, the other in `en-US` and `it-IT`, keywords in `en-US` and none on purpose in `de-DE`, and sizes `[3, 5]`. A fourth type, `outline`, holds items inside items: `outline-1` has one section, of the component `outlineSection`, with a localized `heading`, `points`, a repeater of `point`, which holds `point`s in its `children`, three levels deep, each `text` localized and the third only in `pt-BR`, and `notes`, a repeater of `note` localized as a whole, one note in `en-US` and none in `de-DE`.

| Recording | What it shows |
|---|---|
| `entry-by-slug`, `entry-by-slug-depth-1`, `entry-by-slug-depth-2` | One entry's references at depths 0, 1 and 2: `depth` at the boundary, `absent` for the missing entry, and the loop back to the root |
| `entry-by-id-de` | A read by id, projected to `de-DE` |
| `entries-by-id` | A read of several ids, one of which does not exist |
| `entries-ordered` | A page ordered by `-rank`, with more to come |
| `entries-fr` | Every entry projected to `fr-FR`, where most titles are untranslated and so absent |
| `entries-empty-type` | A type with no entries, ordered by its declared field: an empty page, not a refusal |
| `entry-with-assets` | Assets embedded (delivery 2.1.0, and each with its `slug` since 2.3.0): an image with `imageUrl`, an SVG and a PDF without one, a missing asset as `null` in `poster` and left out of `gallery`, and the `warnings` that name it. Its `body` names an asset in prose, and `_bodyAssets` carries the one it names. The project id in URLs is `{project}` |
| `entry-with-repeater` | Repeater items as stored: each with its `_id` and `_type`, the second's `_type` filled in by the server on write |
| `entry-with-localized-items` | `figure-3` in `de-DE`: the first step's label projected to German and the second's left out, an empty `keywords` list, and `sizes` |
| `entry-with-nested-items` | `outline-1` in `en-US`: points three levels deep, each `text` projected and the third's left out, and the section's `notes` as the `en-US` list |
| `entry-not-found`, `ref-not-found`, `invalid-query`, `key-required`, `project-not-found` | The refusals. Each `title` is the one on its code's page in the error reference, at `type`. Branch on `code`, never on `title`: a title is for a person reading it |

## Type model fixtures

| Fixture | Covers |
|---|---|
| `cli-next-blog` | text, longText (plain and markdown), choice, multichoice, datetime, integer, boolean, localized fields, single and many references, and a type that references itself |
| `delivery-fixture` | The types of the delivery recordings' content, `article`, `notice`, `figure` and `outline`, and the components `citation`, `step`, `outlineSection`, `point` and `note`, so a generator's output can be run against the recordings |
| `assets` | asset fields (single and many, image-only and any file), `number`, `json`, and a repeater whose components are not on the tag |
| `repeaters` | component types (1.2): a single-component repeater of `citation`, and a required repeater holding two components and one not on the tag |
| `traits` | traits (1.4): `seo` taken by `page` and inherited by `article`, which tightens its meta title, and `publishing` and `socialCard` taken by `article`, `socialCard` by an unrelated `person` too |
| `lists` | lists (1.5): a localized list of text with a `max`, lists of numbers and of date-times, one required with a `min`, and lists inside a component, one of them localized |
| `nested` | items inside items (1.6): a `page` of `section`s holding `card`s, and a `siteNavigation` whose `footerLinks` are `menuItem`s, each holding `menuItem`s, with translated labels, and whose `topNavigation` is a list per locale of `localeMenuItem`s, which hold themselves too and have plain labels |
| `singletons` | singletons (1.7): `siteSettings`, with a link to `homePage`, a singleton that extends `page`, so a read of `page` includes it |
| `inheritance` | type inheritance (1.3): an abstract `page`, `servicePage` and `landingPage` extending it, `premiumService` extending `servicePage` with a narrower choice, a `menu` linking to `page` and to `servicePage`, and an abstract component `block` with two components extending it, held by a repeater of `block` |

## License

Apache-2.0

## Webhooks

Coho signs every webhook request as [Standard Webhooks](https://www.standardwebhooks.com) does: HMAC-SHA256 with the endpoint's secret over `{webhook-id}.{webhook-timestamp}.{body}`, base64, written `v1,…` in `webhook-signature`. The secret is `whsec_` and its key in base64. While a secret is being rotated the header carries two signatures, space-separated.

`webhooks/signatures.json` is made by the webhook sender's own code. Each case gives the headers as sent, the body, the secret a receiver holds, the Unix time it checks at, and whether it must accept the request.

### Rules for `verify`

- **The body as received, byte for byte.** Never parse and re-serialize it before checking: `body-re-encoded` fails if you do.
- **Any one signature.** Accept when any space-separated `v1,` signature verifies. Ignore other versions (`v1a,` and later); a header with no `v1,` that verifies is refused.
- **Constant time.** Compare signatures with the language's constant-time comparison.
- **The clock.** Refuse a `webhook-timestamp` more than `toleranceSeconds` (300) before or after the receiver's time, so a captured request cannot be replayed. Let the caller pass the time, for tests.
- **Missing headers.** Refuse a request without `webhook-id`, `webhook-timestamp`, or `webhook-signature`.
- **Errors say which.** A refusal names its `reason`: `signature`, `timestamp`, or `headers`.
- **One secret or several.** Take a list too, for a receiver holding both secrets during a rotation.
