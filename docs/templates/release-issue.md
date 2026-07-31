---
name: Release
about: Track a new package release
labels: release
title: "{{package}}/v{{version}}"
---

<!-- Canonical release issue template.
     Source of truth: docs/templates/release-issue.md
     GitHub: symlinked at .github/ISSUE_TEMPLATE/release-issue.md
     GitLab: symlink .gitlab/issue_templates/release-issue.md to this file -->

## Summary

<!-- What's in this release? Fill in as scope becomes clear. -->

## Branch

`{{package}}/v{{version}}`

## Merge & Release Checklist

- [ ] Version bumped in `{{dir}}/pyproject.toml`
- [ ] `{{dir}}/CHANGELOG.md` updated
- [ ] All PRs merged to release branch
- [ ] Release branch merged to `main`
- [ ] Annotated tag created on the merge commit (`{{package}}/v{{version}}`)
- [ ] This issue closed
