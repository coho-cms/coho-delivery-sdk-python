from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .model import CodegenError


@dataclass(frozen=True)
class CodegenConfig:
    """
    `coho.config.json`, the same file every Coho generator reads. Paths are relative to it.
    The token is never here: `pull` reads it from `COHO_TOKEN`, so the file can be committed.
    """

    url: str | None = None
    """The Coho API's origin, such as `https://app.coho.example`. Only `pull` needs it."""

    account: str | None = None
    project: str | None = None

    ref: str | None = None
    """The tag or branch to generate from. Release builds should name a tag."""

    type_model: str | None = None
    """The type model file. Default `coho-ir.json`."""

    out_dir: str | None = None
    """Where generated code goes, a package of its own. Nothing else should be kept there."""

    def with_ref(self, ref: str) -> CodegenConfig:
        return CodegenConfig(
            self.url, self.account, self.project, ref, self.type_model, self.out_dir
        )


@dataclass(frozen=True)
class Loaded:
    config: CodegenConfig
    file: Path
    type_model: Path
    """The type model file, resolved."""
    out_dir: Path
    """The output directory, resolved."""


DEFAULT_OUT_DIR = "src/coho"


def load_config(file: Path) -> Loaded:
    try:
        raw: Any = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise CodegenError(f"Cannot read {file}: {error}") from None
    if not isinstance(raw, dict):
        raise CodegenError(f"{file} is not a JSON object")

    def text(key: str) -> str | None:
        value = raw.get(key)
        if value is not None and not isinstance(value, str):
            raise CodegenError(f"{file}: {key} is not a string")
        return value

    config = CodegenConfig(
        url=text("url"),
        account=text("account"),
        project=text("project"),
        ref=text("ref"),
        type_model=text("typeModel"),
        out_dir=text("outDir"),
    )
    base = file.resolve().parent
    return Loaded(
        config=config,
        file=file.resolve(),
        type_model=(base / (config.type_model or "coho-ir.json")).resolve(),
        out_dir=(base / (config.out_dir or DEFAULT_OUT_DIR)).resolve(),
    )


def edit_config(file: Path, values: dict[str, str | None]) -> None:
    """Sets `values` in the config file, keeping everything else in it as it was."""
    current: Any = json.loads(file.read_text(encoding="utf-8")) if file.exists() else {}
    if not isinstance(current, dict):
        raise CodegenError(f"{file} is not a JSON object")
    for key, value in values.items():
        if value:
            current[key] = value
    file.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
