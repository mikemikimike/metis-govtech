.PHONY: generate-schema check-schema install-playwright

generate-schema:
	uv run python scripts/generate_schema.py

check-schema:
	uv run python -c "\
	import json; from pathlib import Path; \
	from metis.engine.simulation.types import Experiment, _EXPERIMENT_VERSION; \
	schema = Experiment.model_json_schema(); \
	schema['title'] = f'Experiment v{_EXPERIMENT_VERSION}'; \
	expected = json.dumps(schema, indent=2) + '\n'; \
	actual = Path('schemas/experiment.schema.json').read_text(); \
	assert actual == expected, 'Schema out of sync — run: make generate-schema'; \
	from metis.engine.reporting._models import Report, _REPORT_VERSION; \
	schema = Report.model_json_schema(by_alias=True); \
	schema['title'] = f'Report v{_REPORT_VERSION}'; \
	expected = json.dumps(schema, indent=2) + '\n'; \
	actual = Path('schemas/report.schema.json').read_text(); \
	assert actual == expected, 'Schema out of sync — run: make generate-schema'; \
	print('Schemas OK')"

install-playwright:
	uv run playwright install --with-deps chromium
