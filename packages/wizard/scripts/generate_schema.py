"""Generate JSON Schema from pydantic models and write to schemas/ directory."""

from __future__ import annotations

import json
from pathlib import Path

from metis.wizard.domain.profile import _PROFILE_VERSION, ProductProfile

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"

_MODELS = [
    (ProductProfile, "profile.schema.json", _PROFILE_VERSION, False),
]


def main() -> None:
    SCHEMA_DIR.mkdir(exist_ok=True)
    for model, filename, version, by_alias in _MODELS:
        schema = model.model_json_schema(by_alias=by_alias)
        schema["title"] = f"{model.__name__} v{version}"
        out = SCHEMA_DIR / filename
        out.write_text(json.dumps(schema, indent=2) + "\n")
        print(f"Written: {out}")


if __name__ == "__main__":
    main()
