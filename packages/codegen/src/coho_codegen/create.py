"""
Creates a content library from the template: what `npm create coho` does for TypeScript and
`dotnet new coho-library` for .NET.
"""

from __future__ import annotations

import re
import shutil
from importlib import resources
from importlib.metadata import version
from pathlib import Path

from .model import CodegenError

TEMPLATE_DISTRIBUTION = "yourorg-content"
"""The template's distribution name, which a library's name replaces."""

TEMPLATE_PACKAGE = "yourorg_content"
"""The template's import name, which a library's replaces."""

SKIPPED = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "uv.lock",
    ".env",
}

_DISTRIBUTION = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


def bundled_template() -> Path | None:
    """The template bundled into this coho-codegen by its publish workflow, if there is one."""
    bundled = Path(str(resources.files("coho_codegen"))) / "template"
    return bundled if (bundled / "pyproject.toml").exists() else None


def package_of(distribution: str) -> str:
    """`acme-blog-content` is imported as `acme_blog_content`."""
    return distribution.replace("-", "_")


def create(directory: Path, name: str, template: Path) -> Path:
    """
    Copies `template` into `directory`, named `name`: its distribution, `name` itself, and its
    package, the same with underscores. Pins the Coho packages to this coho-codegen's version,
    so the runtime and the generator that wrote its code always match.
    """
    if not _DISTRIBUTION.match(name):
        raise CodegenError(
            f"'{name}' is not a package name: lowercase letters, digits and dashes, such as acme-content"
        )
    if directory.exists() and any(directory.iterdir()):
        raise CodegenError(f"{directory} is not empty")
    if not (template / "pyproject.toml").exists():
        raise CodegenError(f"{template} is not a Coho library template: it has no pyproject.toml")

    package = package_of(name)
    pinned = version("coho-codegen")
    for source in sorted(template.rglob("*")):
        relative = source.relative_to(template)
        if any(part in SKIPPED for part in relative.parts) or source.is_dir():
            continue
        target = directory / Path(
            *(part.replace(TEMPLATE_PACKAGE, package) for part in relative.parts)
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            text = source.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            shutil.copyfile(source, target)
            continue
        text = text.replace(TEMPLATE_PACKAGE, package).replace(TEMPLATE_DISTRIBUTION, name)
        if relative.parts == ("pyproject.toml",):
            text = _pin(text, pinned)
        target.write_text(text, encoding="utf-8")
    return directory


def _pin(pyproject: str, pinned: str) -> str:
    """`coho-delivery-sdk~=…` and `coho-codegen~=…` at this version: its fixes, never its next release."""
    for distribution in ("coho-delivery-sdk", "coho-codegen"):
        pyproject = re.sub(
            rf'"{distribution}[^"]*"',
            f'"{distribution}~={pinned}"',
            pyproject,
        )
    return pyproject
