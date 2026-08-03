"""The universal epic: pre-bound, read-only, and in the same list as everything else."""

import pytest

from metis.wizard.application.universals import universal_epic, with_universals
from metis.wizard.contracts import EpicScope, Product, ProductProfile


def test_every_universal_criterion_arrives_bound_to_a_metric() -> None:
    """Nothing in the universal epic goes near the matcher — the bindings are hand-chosen."""
    epic = universal_epic()

    criteria = [c for b in epic.behaviours for c in b.criteria]
    assert criteria, "the universal epic should not be empty"
    for criterion in criteria:
        assert criterion.metric_fqn, f"{criterion.id} has no metric"


def test_universal_metric_fqns_are_importable() -> None:
    """A typo in the YAML should fail here, not at engine run time on a compiled file."""
    import importlib

    for behaviour in universal_epic().behaviours:
        for criterion in behaviour.criteria:
            assert criterion.metric_fqn is not None
            module_path, _, class_name = criterion.metric_fqn.rpartition(".")
            module = importlib.import_module(module_path)
            assert hasattr(module, class_name), criterion.metric_fqn


def test_loader_rejects_an_unbound_criterion(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unbound universal criterion is a packaging error, and should be loud."""
    import metis.library.universals as universals_module

    universals_module.universal_epic.cache_clear()
    monkeypatch.setattr(
        universals_module.yaml,
        "safe_load",
        lambda _text: {
            "id": "EP-UNI",
            "name": "Always checked",
            "behaviours": [{"id": "EB-U1", "criteria": [{"id": "AC-U1-1"}]}],
        },
    )

    with pytest.raises(ValueError, match="AC-U1-1"):
        universals_module.universal_epic()

    universals_module.universal_epic.cache_clear()


def test_it_lands_in_the_one_epics_list() -> None:
    """Renderers and the compiler walk `epics` — universals are not a second list."""
    profile = with_universals(
        ProductProfile(product=Product(name="X", summary="s", users="u"))
    )

    assert [e.id for e in profile.epics] == ["EP-UNI"]
    assert profile.universal_epic() is not None
    assert profile.universal_epic().scope is EpicScope.UNIVERSAL  # type: ignore[union-attr]


def test_universals_are_not_counted_as_ticked() -> None:
    """`ticked()` means "the user chose this" — universals are never that."""
    profile = with_universals(
        ProductProfile(product=Product(name="X", summary="s", users="u"))
    )

    assert profile.ticked() == []
    assert profile.universal_behaviours() != []


def test_inserting_twice_does_not_duplicate() -> None:
    """Matters on resume, after the library file has been edited."""
    profile = ProductProfile(product=Product(name="X", summary="s", users="u"))
    with_universals(profile)
    with_universals(profile)

    assert [e.id for e in profile.epics].count("EP-UNI") == 1
