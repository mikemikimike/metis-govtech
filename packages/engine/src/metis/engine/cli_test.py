"""Tests for _validate_inputs in cli.py."""

from pathlib import Path
from textwrap import dedent

import pytest

from metis.engine.cli import _validate_inputs

MINIMAL_EXPERIMENT = dedent("""\
    schema_version: 1
    id: test-exp
    description: test
    personas:
      - id: alice
        description: a persona
    tasks:
      - id: task-1
        description: a task
        persona_refs: [alice]
""")


def _write_experiment(tmp_path: Path, content: str = MINIMAL_EXPERIMENT) -> Path:
    """Write experiment.yaml and return input_dir."""
    (tmp_path / "experiment.yaml").write_text(content)
    return tmp_path


# --- Check 1: directory exists ---


def test_missing_directory(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    missing = tmp_path / "nonexistent"
    with pytest.raises(SystemExit) as exc_info:
        _validate_inputs(missing)
    assert exc_info.value.code == 1
    assert "does not exist" in capsys.readouterr().err


# --- Check 2: experiment.yaml exists ---


def test_missing_experiment_yaml(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit) as exc_info:
        _validate_inputs(tmp_path)
    assert exc_info.value.code == 1
    assert "experiment.yaml" in capsys.readouterr().err


# --- Check 3: pydantic parse failure ---


def test_malformed_experiment_yaml(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    (tmp_path / "experiment.yaml").write_text("schema_version: 1\nid: x\n")
    with pytest.raises(SystemExit) as exc_info:
        _validate_inputs(tmp_path)
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "validation failed" in err


# --- Check 4: duplicate persona IDs ---


def test_duplicate_persona_id(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    content = dedent("""\
        schema_version: 1
        id: test-exp
        description: test
        personas:
          - id: alice
            description: first
          - id: alice
            description: duplicate
        tasks:
          - id: task-1
            description: a task
            persona_refs: [alice]
    """)
    _write_experiment(tmp_path, content)
    with pytest.raises(SystemExit) as exc_info:
        _validate_inputs(tmp_path)
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "duplicate persona id" in err
    assert "alice" in err


# --- Check 5: duplicate task IDs ---


def test_duplicate_task_id(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    content = dedent("""\
        schema_version: 1
        id: test-exp
        description: test
        personas:
          - id: alice
            description: a persona
        tasks:
          - id: task-1
            description: first
            persona_refs: [alice]
          - id: task-1
            description: duplicate
            persona_refs: [alice]
    """)
    _write_experiment(tmp_path, content)
    with pytest.raises(SystemExit) as exc_info:
        _validate_inputs(tmp_path)
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "duplicate task id" in err
    assert "task-1" in err


# --- Check 6: unknown persona_ref ---


def test_unknown_persona_ref(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    content = dedent("""\
        schema_version: 1
        id: test-exp
        description: test
        personas:
          - id: alice
            description: a persona
        tasks:
          - id: task-1
            description: a task
            persona_refs: [bob]
    """)
    _write_experiment(tmp_path, content)
    with pytest.raises(SystemExit) as exc_info:
        _validate_inputs(tmp_path)
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    # This is caught by pydantic validation (step 3), so check appropriate message
    assert "bob" in err or "persona" in err.lower()


# --- Check 7: missing fixture file ---


def test_missing_fixture(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    content = dedent("""\
        schema_version: 1
        id: test-exp
        description: test
        personas:
          - id: alice
            description: a persona
        tasks:
          - id: task-1
            description: a task
            persona_refs: [alice]
            fixtures: [missing.csv]
    """)
    _write_experiment(tmp_path, content)
    with pytest.raises(SystemExit) as exc_info:
        _validate_inputs(tmp_path)
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "missing.csv" in err
    assert "does not exist" in err


# --- Check 8: non-importable metric FQN ---


def test_bad_metric_fqn(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    content = dedent("""\
        schema_version: 1
        id: test-exp
        description: test
        personas:
          - id: alice
            description: a persona
        tasks:
          - id: task-1
            description: a task
            persona_refs: [alice]
            metric_refs:
              - no.such.module.FakeMetric
    """)
    _write_experiment(tmp_path, content)
    with pytest.raises(SystemExit) as exc_info:
        _validate_inputs(tmp_path)
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "could not be imported" in err


def test_metric_not_basemetric_subclass(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    content = dedent("""\
        schema_version: 1
        id: test-exp
        description: test
        personas:
          - id: alice
            description: a persona
        tasks:
          - id: task-1
            description: a task
            persona_refs: [alice]
            metric_refs:
              - os.path.join
    """)
    _write_experiment(tmp_path, content)
    with pytest.raises(SystemExit) as exc_info:
        _validate_inputs(tmp_path)
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "not a subclass" in err or "could not be imported" in err


# --- Happy path ---


def test_valid_input_passes(tmp_path: Path):
    _write_experiment(tmp_path)
    # Should not raise
    _validate_inputs(tmp_path)


def test_valid_input_with_fixtures(tmp_path: Path):
    content = dedent("""\
        schema_version: 1
        id: test-exp
        description: test
        personas:
          - id: alice
            description: a persona
        tasks:
          - id: task-1
            description: a task
            persona_refs: [alice]
            fixtures: [data.csv]
    """)
    _write_experiment(tmp_path, content)
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    (fixtures_dir / "data.csv").write_text("col1,col2\n1,2\n")
    _validate_inputs(tmp_path)


# --- MetricRef input formats ---


def test_metric_ref_all_formats(tmp_path: Path):
    """All accepted MetricRef formats parse without error."""
    content = dedent("""\
        schema_version: 1
        id: test-exp
        description: test
        personas:
          - id: alice
            description: a persona
        tasks:
          - id: task-1
            description: a task
            persona_refs: [alice]
            metric_refs:
              - deepeval.metrics.AnswerRelevancyMetric
              - deepeval.metrics.AnswerRelevancyMetric:
                  threshold: 0.5
    """)
    _write_experiment(tmp_path, content)
    _validate_inputs(tmp_path)


def test_metric_ref_legacy_class_format(tmp_path: Path):
    """Legacy {class: ..., args: ...} format parses without error."""
    from metis.engine.simulation.types import Experiment

    content = dedent("""\
        schema_version: 1
        id: test-exp
        description: test
        personas:
          - id: alice
            description: a persona
        tasks:
          - id: task-1
            description: a task
            persona_refs: [alice]
            metric_refs:
              - class: deepeval.metrics.AnswerRelevancyMetric
                args: {threshold: 0.5}
    """)
    (tmp_path / "experiment.yaml").write_text(content)
    exp = Experiment.load_file(tmp_path / "experiment.yaml")
    assert exp.tasks[0].metric_refs[0].fqn == "deepeval.metrics.AnswerRelevancyMetric"
    assert exp.tasks[0].metric_refs[0].args == {"threshold": 0.5}


def test_metric_ref_null_args(tmp_path: Path):
    """Single-key mapping with null args normalizes to empty dict."""
    from metis.engine.simulation.types import Experiment

    content = dedent("""\
        schema_version: 1
        id: test-exp
        description: test
        personas:
          - id: alice
            description: a persona
        tasks:
          - id: task-1
            description: a task
            persona_refs: [alice]
            metric_refs:
              - deepeval.metrics.AnswerRelevancyMetric:
    """)
    (tmp_path / "experiment.yaml").write_text(content)
    exp = Experiment.load_file(tmp_path / "experiment.yaml")
    assert exp.tasks[0].metric_refs[0].fqn == "deepeval.metrics.AnswerRelevancyMetric"
    assert exp.tasks[0].metric_refs[0].args == {}


# --- extra="ignore" on Persona ---


def test_extra_persona_fields_ignored(tmp_path: Path):
    """Extra fields on persona don't cause validation failure."""
    content = dedent("""\
        schema_version: 1
        id: test-exp
        description: test
        personas:
          - id: alice
            description: a persona
            tone: formal
            mood: cheerful
        tasks:
          - id: task-1
            description: a task
            persona_refs: [alice]
    """)
    _write_experiment(tmp_path, content)
    _validate_inputs(tmp_path)
