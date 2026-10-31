# spec

A copy of [coho-sdk-spec](https://github.com/coho-cms/coho-sdk-spec), the material every Coho SDK is tested against. Nothing here is edited by hand: to change it, change coho-sdk-spec and copy it again. Its README has the rules a generator follows.

- `delivery/recordings/`: what the delivery API answered to a fixed set of requests. The runtime's tests replay them, and the generator's tests read them through the code generated from the delivery fixture.
- `type-model/`: the type model's JSON Schema and fixtures. The generator's tests read them.

Copied from coho-sdk-spec's working tree ahead of **v2026.1.0a8**, not yet tagged (2026-10-31): the type model at 1.6, where a component can hold a repeater, so items hold items, with the `nested` fixture, and the `outline`, `outlineSection`, `point`, and `note` types in the delivery fixture; and delivery 2.1.0's recordings, among them `entry-with-assets`, `entry-with-repeater`, `entry-with-localized-items`, and `entry-with-nested-items`. Copy a tagged release and name it here.
