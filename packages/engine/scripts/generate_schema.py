"""Generate JSON Schema from pydantic models and write to schemas/ directory."""

from __future__ import annotations

import json
from pathlib import Path

from metis.engine.simulation.types import (
    _EXPERIMENT_VERSION,
    Experiment,
)

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"

_MODELS = [
    (Experiment, "experiment.schema.json", _EXPERIMENT_VERSION),
]


def main() -> None:
    SCHEMA_DIR.mkdir(exist_ok=True)
    for model, filename, version in _MODELS:
        schema = model.model_json_schema()
        schema["title"] = f"{model.__name__} v{version}"
        out = SCHEMA_DIR / filename
        out.write_text(json.dumps(schema, indent=2) + "\n")
        print(f"Written: {out}")


if __name__ == "__main__":
    main()
