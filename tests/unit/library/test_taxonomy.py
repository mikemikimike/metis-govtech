"""Public JSON contracts for taxonomy values and support declarations."""

import json
from enum import StrEnum

import pytest
from pydantic import TypeAdapter, ValidationError

from metis.library import taxonomy

ENUM_TYPES = [
    value
    for name in taxonomy.__all__
    if isinstance(value := getattr(taxonomy, name), type) and issubclass(value, StrEnum)
]


@pytest.mark.parametrize(
    "enum_type", ENUM_TYPES, ids=lambda enum_type: enum_type.__name__
)
def test_taxonomy_values_validate_and_round_trip_as_json(enum_type) -> None:
    adapter = TypeAdapter(enum_type)
    values = [member.value for member in enum_type]
    assert adapter.json_schema()["enum"] == values
    for member in enum_type:
        encoded = json.dumps(member.value).encode()
        assert adapter.validate_json(encoded) is member
        assert adapter.dump_json(member) == encoded
    with pytest.raises(ValidationError, match="Input should be"):
        adapter.validate_json('"unsupported_taxonomy_value"')


@pytest.fixture
def declaration() -> dict[str, object]:
    return {
        "subdimension": None,
        "scopes": ["complete_trajectory_episode"],
        "grader_types": ["llm"],
        "reference_types": ["rubric_based"],
        "judgment_forms": ["binary"],
        "aggregations": ["none_single_score"],
    }


@pytest.mark.parametrize(
    "subdimension", [None, taxonomy.EvaluationSubdimension.TASK_CONSTRAINT_ADHERENCE]
)
def test_subdimension_round_trips_as_a_nullable_scalar(
    declaration, subdimension
) -> None:
    declaration["subdimension"] = subdimension
    support = taxonomy.GraderTaxonomy.model_validate(declaration)
    assert support.subdimension is subdimension
    encoded = support.model_dump_json()
    assert json.loads(encoded)["subdimension"] == subdimension
    assert taxonomy.GraderTaxonomy.model_validate_json(encoded) == support


def test_subdimension_requires_an_explicit_value(declaration) -> None:
    del declaration["subdimension"]
    with pytest.raises(ValidationError, match="(?s)subdimension.*Field required"):
        taxonomy.GraderTaxonomy.model_validate(declaration)


@pytest.mark.parametrize(
    "subdimensions",
    [
        ["task_constraint_adherence"],
        ["task_constraint_adherence", "communication_clarity"],
    ],
)
def test_subdimension_rejects_collections(declaration, subdimensions) -> None:
    declaration["subdimension"] = subdimensions
    with pytest.raises(ValidationError, match="subdimension"):
        taxonomy.GraderTaxonomy.model_validate(declaration)


@pytest.mark.parametrize(
    ("field", "enum_type"),
    [
        ("scopes", taxonomy.GraderScope),
        ("grader_types", taxonomy.GraderType),
        ("reference_types", taxonomy.ReferenceType),
        ("judgment_forms", taxonomy.JudgmentForm),
        ("aggregations", taxonomy.Aggregation),
    ],
)
def test_support_fields_require_one_or_more_values(
    declaration, field, enum_type
) -> None:
    declaration[field] = []
    with pytest.raises(ValidationError, match=field):
        taxonomy.GraderTaxonomy.model_validate(declaration)
    for count in (1, 2):
        values = list(enum_type)[:count]
        declaration[field] = values
        support = taxonomy.GraderTaxonomy.model_validate(declaration)
        assert getattr(support, field) == tuple(values)
        assert (
            taxonomy.GraderTaxonomy.model_validate_json(support.model_dump_json())
            == support
        )
