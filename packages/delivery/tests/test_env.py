from __future__ import annotations

import pytest

from coho_delivery_sdk import PreviewConfig, ReleasedConfig, config_from_env

TOKEN = f"coho_pt_{'a' * 43}"


def test_a_delivery_url_reads_released_content() -> None:
    config = config_from_env(
        {
            "COHO_DELIVERY_URL": "https://delivery.test",
            "COHO_DELIVERY_KEY": "k",
            "COHO_PROJECT": "p1",
            "COHO_REF": "prod",
            "COHO_LOCALE": "en-US",
        }
    )
    assert config.delivery == ReleasedConfig(url="https://delivery.test", project="p1", key="k")
    assert (config.ref, config.locale) == ("prod", "en-US")


def test_a_preview_token_reads_a_preview() -> None:
    config = config_from_env(
        {
            "COHO_URL": "https://coho.test",
            "COHO_ACCOUNT": "acme",
            "COHO_PROJECT": "p1",
            "COHO_REF": "dev",
            "COHO_PREVIEW_TOKEN": TOKEN,
            "COHO_DELIVERY_URL": "https://delivery.test",
        }
    )
    assert config.delivery == PreviewConfig(
        url="https://coho.test", account="acme", project="p1", token=TOKEN
    )
    assert config.locale is None


def test_a_token_and_a_key_together_are_refused() -> None:
    with pytest.raises(ValueError, match="not both"):
        config_from_env({"COHO_PREVIEW_TOKEN": TOKEN, "COHO_DELIVERY_KEY": "k"})


def test_what_is_missing_is_named_and_an_empty_value_counts_as_unset() -> None:
    with pytest.raises(
        ValueError, match="COHO_DELIVERY_URL, COHO_REF are needed to read released content"
    ):
        config_from_env({"COHO_PROJECT": "p1", "COHO_REF": " ", "COHO_DELIVERY_KEY": ""})
    with pytest.raises(ValueError, match="COHO_ACCOUNT is needed to read a preview"):
        config_from_env(
            {"COHO_PREVIEW_TOKEN": TOKEN, "COHO_URL": "u", "COHO_PROJECT": "p", "COHO_REF": "dev"}
        )
