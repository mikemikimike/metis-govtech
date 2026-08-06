"""Slice A gate: a hand-written profile compiles to something the engine actually loads.

This is the end of the first build slice. No model call has happened anywhere in it — the
profile is written by hand, the compiler is a pure function, and the engine's own validator
is the judge. If this passes, the output contract is proven before anything upstream of it
exists.

`_validate_inputs` is the engine's real load path, not a stand-in: it parses `experiment.yaml`
through `Experiment`, checks persona references resolve, checks every fixture file is present,
and imports every metric FQN via `importlib` to confirm it is a real metric class. That last
part is the one that matters most here — metric FQNs are strings until run time, so a typo in
a compiled file is invisible until something tries to import it.
"""

from pathlib import Path

import pytest
from fixtures.profiles import CITATION_METRIC, research_assistant

from metis.wizard.application.compile import write_experiment, write_review

EXPERIMENT_ID = "research-assistant"


def _input_dir(tmp_path: Path) -> Path:
    """Compile a profile into the directory layout the engine reads.

    The engine's input directory is `experiment.yaml` plus a `fixtures/` folder — there is
    no separate personas file, because personas are inline.
    """
    profile = research_assistant()
    write_experiment(profile, EXPERIMENT_ID, tmp_path / "experiment.yaml")
    write_review(profile, EXPERIMENT_ID, tmp_path / "review.md")

    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    for scenario in profile.scenarios:
        for name in scenario.fixtures:
            (fixtures / name).write_text("stand-in fixture\n")

    return tmp_path


def test_the_engine_loads_the_compiled_experiment(tmp_path: Path) -> None:
    from metis.engine.cli import _validate_inputs

    input_dir = _input_dir(tmp_path)

    # `_validate_inputs` calls sys.exit(1) on any problem, so reaching the end is the pass.
    _validate_inputs(input_dir)

    assert (input_dir / "experiment.yaml").is_file()
    assert (input_dir / "review.md").is_file()


def test_the_gate_would_catch_an_unimportable_metric(tmp_path: Path) -> None:
    """Proves the gate is actually checking, rather than passing vacuously.

    FQNs are resolved by importlib at run time, so an experiment naming a metric that has
    moved stops loading. Not silent — which is what this asserts.
    """
    from metis.engine.cli import _validate_inputs

    input_dir = _input_dir(tmp_path)
    experiment = input_dir / "experiment.yaml"
    original = experiment.read_text()
    # The metrics' old home, deleted when they moved to metis-library. Deliberately dead —
    # an experiment compiled before the move names this and must fail loudly. Sourced from
    # the fixture so this cannot quietly become a no-op if the compiled metrics change.
    dead_fqn = CITATION_METRIC.replace("metis.library.", "metis.engine.")
    assert CITATION_METRIC in original, (
        "the corrupted metric must actually be compiled in"
    )
    experiment.write_text(original.replace(CITATION_METRIC, dead_fqn))

    with pytest.raises(SystemExit) as exit_info:
        _validate_inputs(input_dir)

    assert exit_info.value.code == 1
