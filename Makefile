.PHONY: help install lint lint-fix format format-check fix typecheck check ci clean release-init release-branch release-issue

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
	@printf "  make release-init      Create release branch + tracking issue (PKG=<name>|APP=<name> VER=<semver>)\n"
	@printf "  make release-branch    Create release branch only\n"
	@printf "  make release-issue     Create release tracking issue only\n"

install:
	uv sync --group dev
	$(MAKE) -C packages/engine install-playwright

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
	$(MAKE) -C packages/engine check-schema

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf .ruff_cache .pyright .mypy_cache
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

# --- Release workflow -----------------------------------------------------------

# Resolve component name and directory from PKG= or APP=
ifdef PKG
  ifdef APP
    $(error Set PKG or APP, not both)
  endif
  COMPONENT := $(PKG)
  COMPONENT_DIR := packages/$(PKG)
  FULL_NAME := metis-$(PKG)
else ifdef APP
  COMPONENT := $(APP)
  COMPONENT_DIR := apps/$(APP)
  FULL_NAME := metis-$(APP)
else
  # Allow targets that don't need these variables to still work
  COMPONENT :=
  COMPONENT_DIR :=
  FULL_NAME :=
endif

# Platform detection (override with PLATFORM=github|gitlab)
REMOTE_URL := $(shell git remote get-url origin 2>/dev/null)
ifndef PLATFORM
  ifneq (,$(findstring github.com,$(REMOTE_URL)))
    PLATFORM := github
  else ifneq (,$(findstring gitlab.com,$(REMOTE_URL)))
    PLATFORM := gitlab
  endif
endif

define check_release_args
	@if [ -z "$(COMPONENT)" ]; then \
		printf "Error: Set PKG=<name> (for packages/) or APP=<name> (for apps/)\n"; \
		printf "  Example: make $@ PKG=engine VER=0.2.1\n"; \
		printf "  Example: make $@ APP=api VER=1.0.0\n"; \
		exit 1; \
	fi
	@if [ -z "$(VER)" ]; then \
		printf "Error: Set VER=<semver>\n"; \
		printf "  Example: make $@ PKG=$(COMPONENT) VER=0.2.1\n"; \
		exit 1; \
	fi
	@if [ ! -d "$(COMPONENT_DIR)" ]; then \
		printf "Error: Directory $(COMPONENT_DIR) does not exist\n"; \
		exit 1; \
	fi
endef

RELEASE_BRANCH := $(COMPONENT)/v$(VER)
TEMPLATE := docs/templates/release-issue.md

release-init: release-branch release-issue

release-branch:
	$(check_release_args)
	@if [ -n "$$(git status --porcelain --untracked-files=no)" ]; then \
		printf "Error: Working tree is not clean. Commit or stash changes first.\n"; \
		exit 1; \
	fi
	git fetch origin main
	git checkout -b "$(RELEASE_BRANCH)" origin/main
	@printf "Created and switched to branch: $(RELEASE_BRANCH)\n"

release-issue:
	$(check_release_args)
	@TITLE="Release: $(FULL_NAME) v$(VER)"; \
	BODY=$$(sed \
		-e 's|{{package}}|$(FULL_NAME)|g' \
		-e 's|{{version}}|$(VER)|g' \
		-e 's|{{dir}}|$(COMPONENT_DIR)|g' \
		"$(TEMPLATE)" | sed '1,/^---$$/d'); \
	if [ "$(PLATFORM)" = "github" ] && command -v gh >/dev/null 2>&1; then \
		printf "%s\n" "$$BODY" | gh issue create --title "$$TITLE" --label release --body-file -; \
	elif [ "$(PLATFORM)" = "gitlab" ] && command -v glab >/dev/null 2>&1; then \
		printf "%s\n" "$$BODY" | glab issue create --title "$$TITLE" --label release --description "$$BODY"; \
	else \
		printf "=== Issue Title ===\n%s\n\n=== Issue Body ===\n%s\n" "$$TITLE" "$$BODY"; \
		printf "\n---\nNo platform CLI detected. Paste the above into your issue tracker manually.\n"; \
		printf "Hint: install gh (GitHub) or glab (GitLab), or set PLATFORM=github|gitlab\n"; \
	fi
