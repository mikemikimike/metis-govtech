.PHONY: generate-schema check-schema

generate-schema:
	uv run python scripts/generate_schema.py

check-schema:
	uv run python -c "\
	import json; from pathlib import Path; \
	from metis.wizard.domain.profile import ProductProfile, _PROFILE_VERSION; \
	schema = ProductProfile.model_json_schema(); \
	schema['title'] = f'ProductProfile v{_PROFILE_VERSION}'; \
	expected = json.dumps(schema, indent=2) + '\n'; \
	actual = Path('schemas/profile.schema.json').read_text(); \
	assert actual == expected, 'Schema out of sync — run: make generate-schema'; \
	print('Schemas OK')"
