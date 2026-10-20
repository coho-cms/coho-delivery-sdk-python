from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from coho_codegen.files import drift
from coho_codegen.generate import generate, snake
from coho_codegen.model import CodegenError, TypeModel, read_type_model

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "spec" / "type-model" / "fixtures"
EXPECTED = Path(__file__).resolve().parent / "expected"


def fixture(name: str) -> TypeModel:
    return read_type_model(json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8")))


@pytest.mark.parametrize("name", sorted(path.stem for path in FIXTURES.glob("*.json")))
def test_each_fixture_generates_what_is_committed(name: str) -> None:
    # After a change to the generator: uv run python packages/codegen/scripts/expected.py
    assert drift(generate(fixture(name)).files, EXPECTED / name.replace("-", "_")) == []


def test_generation_is_a_pure_function_of_the_model() -> None:
    assert generate(fixture("traits")) == generate(fixture("traits"))


def model(fields: list[dict[str, Any]], *, slug: str = "page", immutable: bool = True) -> TypeModel:
    return read_type_model(
        {
            "irVersion": "1.4",
            "source": {
                "project": "p",
                "ref": "v1",
                "immutable": immutable,
                "schemaHash": "sha256:" + "0" * 64,
            },
            "types": {slug: {"slug": slug, "name": "Page", "version": "1", "fields": fields}},
        }
    )


def field(id: str, kind: str = "text", **extra: Any) -> dict[str, Any]:
    return {
        "id": id,
        "name": id,
        "kind": kind,
        "presence": "maybe",
        "required": False,
        "localized": False,
        "sortable": False,
        **extra,
    }


def contents(generated: Any, path: str) -> str:
    return str(next(file.contents for file in generated.files if file.path == path))


def test_field_ids_become_snake_case_attributes_aliased_to_their_ids() -> None:
    assert snake("publishedAt") == "published_at"
    assert snake("seoURL") == "seo_url"
    assert snake("heroImage2x") == "hero_image2x"

    page = contents(generate(model([field("publishedAt", "datetime")])), "page.py")
    assert 'published_at: datetime | None = Field(default=None, alias="publishedAt")' in page


def test_a_field_named_like_a_keyword_or_a_system_value_gets_an_underscore() -> None:
    generated = generate(model([field("class"), field("type"), field("modelName"), field("json")]))
    page = contents(generated, "page.py")
    for attribute, wire in (
        ("class_", "class"),
        ("type_", "type"),
        ("model_name_", "modelName"),
        ("json_", "json"),
    ):
        assert f'{attribute}: str | None = Field(default=None, alias="{wire}")' in page


def test_two_fields_one_attribute_are_refused() -> None:
    with pytest.raises(CodegenError, match="would both be foo_bar"):
        generate(model([field("fooBar"), field("foo_bar")]))


def test_a_type_named_like_the_generated_code_gets_entry_after_it() -> None:
    generated = generate(model([field("title")], slug="coho"))
    assert "class CohoEntry(runtime.EntryBase):" in contents(generated, "coho.py")
    assert any("CohoEntry" in warning for warning in generated.warnings)


def test_a_type_read_like_a_method_of_the_client_is_read_with_type_after_it() -> None:
    generated = generate(model([field("title")], slug="content"))
    assert "content_type: runtime.TypeReader[Content, Never]" in contents(generated, "__init__.py")


def test_an_unknown_kind_is_typed_any_with_a_warning_never_a_failure() -> None:
    generated = generate(model([field("where", "geopoint")]))
    assert "where: Any | None = None" in contents(generated, "page.py")
    assert any("'geopoint'" in warning for warning in generated.warnings)


def test_a_branch_warns_that_its_types_can_change() -> None:
    generated = generate(model([field("title")], immutable=False))
    assert any("a branch" in warning for warning in generated.warnings)


def test_a_choice_accepts_values_added_after_generation() -> None:
    page = contents(generate(model([field("tone", "choice", values=["calm", "loud"])])), "page.py")
    assert 'tone: Literal["calm", "loud"] | str | None = None' in page


def test_sortable_fields_name_the_orders_a_list_takes() -> None:
    page = contents(generate(model([field("rank", "integer", sortable=True)])), "page.py")
    assert 'PageOrder = Literal["rank", "-rank"]' in page


def test_a_field_always_present_has_no_default_and_its_empty_value_is_in_the_shape() -> None:
    generated = generate(model([field("rank", "integer", presence="always", required=True)]))
    assert "    rank: int\n" in contents(generated, "page.py")
    assert '"rank": 0,' in contents(generated, "__init__.py")


def test_names_in_docstrings_cannot_end_them() -> None:
    generated = generate(model([{**field("title"), "name": 'Say """hi""" \\ "there"'}]))
    page = contents(generated, "page.py")
    compile(page, "page.py", "exec")


def test_an_unsupported_major_version_is_refused() -> None:
    with pytest.raises(CodegenError, match="version 2.0; this generator reads 1.x"):
        read_type_model({"irVersion": "2.0", "source": {}, "types": {}})
