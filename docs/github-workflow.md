# GitHub Collaboration Workflow

This is the day-to-day playbook for collaborating on METIS via GitHub. For coding standards, testing guidelines, and dependency rules, see [CONTRIBUTING.md](../CONTRIBUTING.md).

## Ownership

Each package and app has a designated owner responsible for release decisions and final merge of release PRs. GitHub auto-assigns reviewers based on [`.github/CODEOWNERS`](../.github/CODEOWNERS).

| Component | Owner |
|-----------|-------|
| `metis-core` | @mqf20 |
| `metis-library` | @mqf20 |
| `metis-engine` | @mqf20 |
| `metis-wizard` | @leannetan |
| `metis-api` (app) | @mqf20 |
| `metis-web` (app) | @mqf20 |

## For Internal Team Members

### Starting a Release Cycle

1. Create a release branch and tracking issue:

   ```bash
   make release-init PKG=core VER=0.3.0
   ```

   This creates branch `release/metis-core/v0.3.0` off `main` and opens a GitHub issue (labelled `release`, `package`, and the package label e.g. `metis-core`) to track progress.

2. Bump the version in the package's `pyproject.toml` and update the lockfile:

   ```bash
   # edit packages/core/pyproject.toml → version = "0.3.0"
   uv lock
   ```

3. Add a placeholder section in the package's `CHANGELOG.md`:

   ```markdown
   ## [0.3.0] - Unreleased

   ### Added

   ### Changed

   ### Fixed
   ```

4. Commit and push:

   ```bash
   git commit -m "chore(core): initialize release v0.3.0"
   git push -u origin release/metis-core/v0.3.0
   ```

5. Open a PR from the release branch into `main`:
   - Title: `metis-core/v0.3.0`
   - Labels: `release`, `package`, the package label (e.g., `metis-core`)
   - This PR stays open and accumulates work until the release is complete.

6. All feature work for this release targets the release branch. Link the PR back to the tracking issue (e.g., "Closes #12").

### Working on a Feature or Fix

1. Open an issue for the work and add it as a **sub-issue** of the release tracking issue. This gives the team a clear view of what's in scope for the release.

2. Branch off the release branch:

   ```bash
   git checkout -b feat/score-validation release/metis-core/v0.3.0
   ```

   Use the standard prefixes (`feat/`, `fix/`, `docs/`, `refactor/`, `test/`).

3. Push early and open a **Draft PR** targeting the release branch. This gives the team visibility into in-progress work.
   - Labels: `package` or `app`, and the component label (e.g., `metis-core`).

4. Reference the release tracking issue in your PR description (e.g., "Part of #12").

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
2. Open a PR from the release branch into `main`:
   - Title: `metis-core/v0.3.0`
   - Labels: `release`, `package`, the package label (e.g., `metis-core`)
3. Get it reviewed and approved.
4. The **package/app owner** merges with a **merge commit** (not squash) to preserve branch history.
5. Tag the merge commit on `main` with an annotated tag:

   ```bash
   git tag -a metis-core/v0.3.0 -m "metis-core/v0.3.0"
   git push origin metis-core/v0.3.0
   ```

6. Close the tracking issue.

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

## Major Version Maintenance

See [docs/version-maintenance.md](version-maintenance.md) for the full strategy on maintaining previous major versions (branching, cherry-picks, EOL).
