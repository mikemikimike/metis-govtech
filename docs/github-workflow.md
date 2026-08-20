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

When the suite performs a coordinated major version bump (e.g., v0 → v1), we maintain the old major version on a long-lived branch until users have migrated.

### Rules

- **`main` is always the latest major version.** After the coordinated bump, `main` carries v1.
- **A `maintain/v<N>` branch holds the previous major.** Cut it from `main` immediately before the v1 bump lands.
- **Bug fixes go to `main` first, then cherry-pick back to `maintain/v0`.** This ensures the latest version always has the fix. Exception: if the bug only exists in v0 (code was rewritten in v1), fix directly on `maintain/v0`. Never backport features.
- **Release workflow is identical on both branches.** Use the same `release/<pkg>/v<semver>` branches and `<pkg>/v<semver>` tags — the version numbers are unambiguous.
- **EOL when users migrate** (target: ~2 months). Add a deprecation warning to the final v0 patch releases.

### Procedure

1. Finish all in-flight v0 release branches, merge to `main`, and tag them.
2. Create the maintenance branch:

   ```bash
   git branch maintain/v0 main
   git push origin maintain/v0
   ```

3. Land the coordinated v1 bump on `main` (all `pyproject.toml` versions → `1.0.0`).
4. For subsequent v0 bugfixes, cherry-pick from `main` into `maintain/v0`:

   ```bash
   git checkout maintain/v0
   git cherry-pick <commit>
   # follow normal release workflow from here
   ```

5. When EOL is reached, tag a final patch with a changelog entry pointing users to v1, then archive the branch.

### Git Trajectory

```
main          ─●─●─●─●─●─────────────────●─●─●─●─── (v1.x development)
                       │                  ▲
                       │   v1.0.0 bump ───┘
                       │
                       ▼
maintain/v0    ────────●───────●───────●                (bugfixes only)
                       │       │       │
                       │       │       └─ tag: metis-core/v0.10.2
                       │       └───────── tag: metis-engine/v0.10.1
                       └───────────────── branch cut (last v0 state)


Timeline:
─────────────────────────────────────────────────────────────────────►
     v0 dev        cut        v1 dev             v0 EOL
     on main     maintain/    on main            (archive branch)
                   v0
```

### What Goes Where

| Activity | Branch | Tags |
|----------|--------|------|
| New features (v1) | `main` | `metis-core/v1.0.0`, etc. |
| v0 bugfixes | `maintain/v0` | `metis-core/v0.10.1`, etc. |
| Release branches (v1) | `release/<pkg>/v1.x.y` → `main` | — |
| Release branches (v0) | `release/<pkg>/v0.x.y` → `maintain/v0` | — |
