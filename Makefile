.PHONY: help install lint lint-fix format format-check fix typecheck check ci clean

help:
	@printf "Available targets:\n"
	@printf "  make install           Install all workspace dependencies (including dev group)\n"
	@printf "  make lint              Run Ruff lint checks\n"
	@printf "  make lint-fix          Apply Ruff lint autofixes\n"
	@printf "  make format            Format all Python files with Ruff\n"
	@printf "  make format-check      Check formatting without modifying files\n"
	@printf "  make fix               Apply lint autofixes and format\n"
	@printf "  make typecheck         Run Pyright type checking\n"
	@printf "  make check             Run lint + format-check + typecheck (non-mutating)\n"
	@printf "  make ci                Full CI suite: check + test\n"
	@printf "  make clean             Remove all generated/cached files\n"

install:
	uv sync --group dev

lint:
	uv run ruff check .

lint-fix:
	uv run ruff check . --fix

format:
	uv run ruff format .

format-check:
	uv run ruff format . --check

fix:
	$(MAKE) lint-fix
	$(MAKE) format

typecheck:
	uv run pyright

# test:
# 	uv run pytest
#
# test-unit:
# 	uv run pytest tests/unit/
#
# test-integration:
# 	uv run pytest tests/integration/

check:
	$(MAKE) lint
	$(MAKE) format-check
	$(MAKE) typecheck

ci:
	$(MAKE) check

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf .ruff_cache .pyright .mypy_cache
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
