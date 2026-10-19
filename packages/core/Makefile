.PHONY: generate-schema check-schema

generate-schema:
	uv run python scripts/generate_schema.py

check-schema:
	uv run python -c "\
	import json; from pathlib import Path; \
	from metis.core.report import Report, _REPORT_VERSION; \
	from metis.core.specification import Specification, _SPECIFICATION_VERSION; \
	models = [(Specification, 'specification.schema.json', _SPECIFICATION_VERSION, False), \
	          (Report, 'report.schema.json', _REPORT_VERSION, True)]; \
	stale = [name for model, name, version, by_alias in models \
	         if Path('schemas', name).read_text() \
	         != json.dumps({**model.model_json_schema(by_alias=by_alias), \
	                        'title': f'{model.__name__} v{version}'}, indent=2) + '\n']; \
	assert not stale, f'Schemas out of sync: {stale} — run: make generate-schema'; \
	print('Schemas OK')"
