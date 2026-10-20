"""
Bundles a coho-template-python checkout into coho-codegen, for `coho-codegen create`:
uv run python packages/codegen/scripts/bundle.py ../coho-template-python

The publish workflow runs it with the template at the release's tag. The bundle is
git-ignored, and the wheel packs it.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from coho_codegen.create import SKIPPED

TARGET = Path(__file__).resolve().parents[1] / "src" / "coho_codegen" / "template"


def main(source: Path) -> None:
    if not (source / "pyproject.toml").exists():
        sys.exit(f"{source} is not a coho-template-python checkout: it has no pyproject.toml")
    shutil.rmtree(TARGET, ignore_errors=True)
    shutil.copytree(source, TARGET, ignore=shutil.ignore_patterns(*SKIPPED))
    print(f"Bundled {source} into {TARGET}", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]).resolve())
