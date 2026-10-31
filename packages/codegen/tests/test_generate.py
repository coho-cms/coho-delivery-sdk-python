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
            "irVersion": "1.5",
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


def test_a_list_is_a_list_of_its_items_kind_and_empty_when_absent() -> None:
    generated = generate(
        model(
            [
                field("tags", "list", item="text"),
                field("counts", "list", item="integer"),
                field("weights", "list", item="number"),
                field("dates", "list", item="datetime"),
            ]
        )
    )
    page = contents(generated, "page.py")
    for declaration in (
        "tags: list[str] = []",
        "counts: list[int] = []",
        "weights: list[float] = []",
        "dates: list[datetime] = []",
    ):
        assert declaration in page
    assert "from datetime import datetime" in page
    assert not any("does not know" in warning for warning in generated.warnings)


def test_a_localized_list_is_none_where_untranslated_and_empty_is_a_value() -> None:
    page = contents(
        generate(model([field("tags", "list", item="text", localized=True)])), "page.py"
    )
    assert "tags: list[str] | None = None" in page
    assert (
        "None where the locale has no translation. Empty is a value: none in this locale." in page
    )


def test_a_list_always_present_has_no_default_and_is_empty_in_the_shape() -> None:
    generated = generate(
        model([field("dates", "list", item="datetime", presence="always", required=True, min=1)])
    )
    assert "    dates: list[datetime]\n" in contents(generated, "page.py")
    assert '"dates": [],' in contents(generated, "__init__.py")


def test_a_list_in_a_component_is_typed_as_at_the_top_level() -> None:
    talk = contents(generate(fixture("lists")), "talk.py")
    assert "speakers: list[str] = []" in talk
    assert "tracks: list[int] | None = None" in talk


def test_a_list_of_a_kind_the_generator_does_not_know_holds_any_with_a_warning() -> None:
    generated = generate(model([field("spots", "list", item="geopoint")]))
    assert "spots: list[Any] = []" in contents(generated, "page.py")
    assert any("a list of 'geopoint'" in warning for warning in generated.warnings)


def test_a_trait_declares_a_list_as_a_sequence_and_a_localized_one_as_optional() -> None:
    trait = {
        "slug": "tagged",
        "name": "Tagged",
        "version": "1",
        "fields": [
            field("sizes", "list", item="integer"),
            field("tags", "list", item="text", localized=True),
        ],
    }
    generated = generate(read_type_model({**model([]), "traits": {"tagged": trait}}))
    tagged = contents(generated, "tagged.py")
    assert "def sizes(self) -> Sequence[int]:" in tagged
    assert "def tags(self) -> Sequence[str] | None:" in tagged


def test_a_component_holding_itself_is_a_recursive_model() -> None:
    menu_item = contents(generate(fixture("nested")), "menu_item.py")
    assert "children: list[MenuItem] = []" in menu_item
    # Its own name needs no import.
    assert "TYPE_CHECKING" not in menu_item


def test_components_that_hold_each_other_import_each_other_for_type_checkers_alone() -> None:
    def component(slug: str, holds: str) -> dict[str, Any]:
        fields = [field("items", "repeater", of=[holds]), field("label")]
        return {"slug": slug, "name": slug, "version": "1", "fields": fields}

    generated = generate(
        read_type_model(
            {
                **model([field("blocks", "repeater", of=["column"])]),
                "irVersion": "1.6",
                "components": {
                    "column": component("column", "row"),
                    "row": component("row", "column"),
                },
            }
        )
    )
    column, row = contents(generated, "column.py"), contents(generated, "row.py")
    assert "items: list[Row] = []" in column
    assert "if TYPE_CHECKING:\n    from .row import Row" in column
    assert "items: list[Column] = []" in row
    assert "if TYPE_CHECKING:\n    from .column import Column" in row
    index = contents(generated, "__init__.py")
    # Each one's shape lists what its repeater holds, so items are filtered at every level.
    assert '"items": ("row",),' in index and '"items": ("column",),' in index


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
