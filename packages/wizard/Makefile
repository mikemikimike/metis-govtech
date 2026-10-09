.PHONY: generate-schema check-schema

generate-schema:
	uv run python scripts/generate_schema.py

check-schema:
	uv run python -c "\
	import json; from pathlib import Path; \
	from metis.wizard.domain.specification import Specification, _SPECIFICATION_VERSION; \
	schema = Specification.model_json_schema(); \
	schema['title'] = f'Specification v{_SPECIFICATION_VERSION}'; \
	expected = json.dumps(schema, indent=2) + '\n'; \
	actual = Path('schemas/specification.schema.json').read_text(); \
	assert actual == expected, 'Schema out of sync — run: make generate-schema'; \
	print('Schemas OK')"
