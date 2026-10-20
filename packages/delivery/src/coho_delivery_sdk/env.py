from __future__ import annotations

from collections.abc import Mapping

from .client import DeliveryConfig, PreviewConfig, ReleasedConfig
from .content import ContentConfig


def config_from_env(env: Mapping[str, str | None]) -> ContentConfig:
    """
    A content config from environment variables, so whether an app reads released content or
    previews unreleased content is a deployment's choice, not a code change. It is handed the
    environment, such as `os.environ`, rather than reading one, so a library built on it
    reads no environment of its own.

    | Variable | |
    |---|---|
    | `COHO_PROJECT`, `COHO_REF` | Always. The ref is a tag or an environment, or with a preview token, a branch or `dev` |
    | `COHO_LOCALE` | Optional |
    | `COHO_DELIVERY_URL`, `COHO_DELIVERY_KEY` | Released content, from delivery. The key may be left out for a public environment |
    | `COHO_PREVIEW_TOKEN`, `COHO_URL`, `COHO_ACCOUNT` | Unreleased content, live through Coho: a project token, Coho's URL, and the project's account |

    The names are the same in every Coho SDK, so one deployment's variables serve an app in
    any language. A preview token selects a preview. Setting it and a delivery key is refused
    rather than one quietly winning, since the two read different content. An empty
    variable, such as `COHO_DELIVERY_KEY=` in a `.env` file, counts as unset.
    """

    def value(name: str) -> str | None:
        set_ = (env.get(name) or "").strip()
        return set_ or None

    token = value("COHO_PREVIEW_TOKEN")
    key = value("COHO_DELIVERY_KEY")
    if token is not None and key is not None:
        raise ValueError(
            "Coho: set COHO_PREVIEW_TOKEN to preview unreleased content, or COHO_DELIVERY_KEY "
            "to read released content, not both"
        )

    needed = (
        ["COHO_URL", "COHO_ACCOUNT", "COHO_PROJECT", "COHO_REF"]
        if token is not None
        else ["COHO_DELIVERY_URL", "COHO_PROJECT", "COHO_REF"]
    )
    missing = [name for name in needed if value(name) is None]
    if missing:
        reading = (
            "a preview, since COHO_PREVIEW_TOKEN is set"
            if token is not None
            else "released content"
        )
        verb = "is" if len(missing) == 1 else "are"
        raise ValueError(f"Coho: {', '.join(missing)} {verb} needed to read {reading}")

    def present(name: str) -> str:
        # Checked present above.
        found = value(name)
        assert found is not None
        return found

    delivery: DeliveryConfig = (
        PreviewConfig(
            url=present("COHO_URL"),
            account=present("COHO_ACCOUNT"),
            project=present("COHO_PROJECT"),
            token=token,
        )
        if token is not None
        else ReleasedConfig(
            url=present("COHO_DELIVERY_URL"), project=present("COHO_PROJECT"), key=key
        )
    )
    return ContentConfig(delivery=delivery, ref=present("COHO_REF"), locale=value("COHO_LOCALE"))
