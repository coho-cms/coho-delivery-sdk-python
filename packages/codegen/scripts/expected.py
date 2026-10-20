"""Regenerates tests/expected from the spec's fixtures: run after changing the generator, and review the diff."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from coho_codegen.files import write
from coho_codegen.generate import generate
from coho_codegen.model import read_type_model

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "spec" / "type-model" / "fixtures"
EXPECTED = Path(__file__).resolve().parents[1] / "tests" / "expected"


def main() -> None:
    for fixture in sorted(FIXTURES.glob("*.json")):
        model = read_type_model(json.loads(fixture.read_text(encoding="utf-8")))
        write(generate(model).files, EXPECTED / fixture.stem.replace("-", "_"))
        print(
            f"Wrote {EXPECTED.relative_to(ROOT) / fixture.stem.replace('-', '_')}", file=sys.stderr
        )


if __name__ == "__main__":
    main()
