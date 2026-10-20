"""A `.env` file: `NAME=value` lines, as Coho's other generators read them."""

from __future__ import annotations

import os
from pathlib import Path


def read(path: Path) -> dict[str, str]:
    """The variables in `path`, or none when there is no such file."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        name, equals, value = line.partition("=")
        if not equals or not name.strip():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
            value = value[1:-1]
        values[name.strip()] = value
    return values


def write(path: Path, example: Path, name: str, value: str) -> None:
    """
    Writes `path` from `example`, with `name` set to `value`, keeping anything else `path`
    already set. Only its owner can read it.
    """
    source = path if path.exists() else example
    lines = source.read_text(encoding="utf-8").splitlines() if source.exists() else []
    for i, line in enumerate(lines):
        if line.startswith(f"{name}="):
            lines[i] = f"{name}={value}"
            break
    else:
        lines.insert(0, f"{name}={value}")

    path.touch(mode=0o600, exist_ok=True)
    if os.name != "nt":
        path.chmod(0o600)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
