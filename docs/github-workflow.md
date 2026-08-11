# GitHub Collaboration Workflow

This is the day-to-day playbook for collaborating on METIS via GitHub. For coding standards, testing guidelines, and dependency rules, see [CONTRIBUTING.md](../CONTRIBUTING.md).

## For Internal Team Members

### Starting a Release Cycle

1. Create a release branch and tracking issue:

   ```bash
   make release-init PKG=core VER=0.3.0
   ```

   This creates branch `release/metis-core/v0.3.0` off `main` and opens a GitHub issue to track progress.

2. All feature work for this release targets the release branch.

### Working on a Feature or Fix

1. Branch off the release branch:

   ```bash
   git checkout -b feat/score-validation release/metis-core/v0.3.0
   ```

   Use the standard prefixes (`feat/`, `fix/`, `docs/`, `refactor/`, `test/`).

2. Push early and open a **Draft PR** targeting the release branch. This gives the team visibility into in-progress work.

3. Reference the release tracking issue in your PR description (e.g., "Part of #12").

### Changes Not Tied to a Package or App

For work that doesn't belong to a specific package release (e.g., documentation updates, CI config, root-level tooling):

1. Branch directly from `main`:

   ```bash
   git checkout -b docs/update-readme main
   ```

2. Open a PR targeting `main`.

### Code Review and Merge

1. Run `make check` locally before requesting review.
2. Push your branch and request review from a colleague.
3. Address feedback with additional commits — don't force-push on shared branches.
4. Once approved, the **PR author merges** their own PR:
   - Squash-merge for single-concern branches.
   - Merge commit for branches with meaningful intermediate history.
5. Delete the feature branch after merge.

### Completing a Release

1. Ensure all PRs for the release are merged into the release branch.
2. Open a PR from the release branch into `main`. Get it reviewed and approved.
3. Merge with a **merge commit** (not squash) to preserve branch history.
4. Tag the merge commit on `main` with an annotated tag:

   ```bash
   git tag -a metis-core/v0.3.0 -m "metis-core/v0.3.0"
   git push origin metis-core/v0.3.0
   ```

5. Close the tracking issue.

## For External Contributors

1. Fork the repository.
2. Branch off `main` (or the target release branch if contributing to a specific release).
3. Follow the standards in [CONTRIBUTING.md](../CONTRIBUTING.md).
4. Open a PR from your fork targeting the upstream release branch or `main`.
5. A maintainer reviews and merges.

## Quick Reference

| Step | Command / Action |
|------|-----------------|
| Start release | `make release-init PKG=<name> VER=<semver>` |
| Feature branch | `git checkout -b feat/<desc> <release-branch>` |
| Non-package branch | `git checkout -b docs/<desc> main` |
| Run checks | `make check` |
| Open PR | Target the release branch (or `main` for non-package changes) |
| Merge | PR author merges after approval |
| Tag release | `git tag -a <pkg>/v<ver> -m "<pkg>/v<ver>"` on `main` |
