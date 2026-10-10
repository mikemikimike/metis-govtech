.PHONY: generate-schema check-schema

generate-schema:
	uv run python scripts/generate_schema.py

check-schema:
	uv run python -c "\
	import json; from pathlib import Path; \
	from metis.insights._models import Report, _REPORT_VERSION; \
	schema = Report.model_json_schema(by_alias=True); \
	schema['title'] = f'Report v{_REPORT_VERSION}'; \
	expected = json.dumps(schema, indent=2) + '\n'; \
	actual = Path('schemas/report.schema.json').read_text(); \
	assert actual == expected, 'Schema out of sync — run: make generate-schema'; \
	print('Schemas OK')"
