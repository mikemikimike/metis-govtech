# Major Version Maintenance

When the suite performs a coordinated major version bump (e.g., v0 → v1), we maintain the old major version on a long-lived branch until users have migrated.

## Rules

- **`main` is always the latest major version.** After the coordinated bump, `main` carries v1.
- **A `v<N>.x` branch holds the previous major.** Cut it from `main` immediately before the v1 bump lands.
- **Bug fixes go to `main` first, then cherry-pick back to `v0.x`.** This ensures the latest version always has the fix. Exception: if the bug only exists in v0 (code was rewritten in v1), fix directly on `v0.x`. Never backport features.
- **Release workflow is identical on both branches.** Use the same `release/<pkg>/v<semver>` branches and `<pkg>/v<semver>` tags — the version numbers are unambiguous.
- **EOL when users migrate** (target: ~2 months). Add a deprecation warning to the final v0 patch releases.

## Procedure

1. Finish all in-flight v0 release branches, merge to `main`, and tag them.
2. Create the maintenance branch:

   ```bash
   git branch v0.x main
   git push origin v0.x
   ```

3. Land the coordinated v1 bump on `main` (all `pyproject.toml` versions → `1.0.0`). As part of this
   commit, split the combined `CHANGELOG.next.md` into the per-package files (see
   [Graduating `next` to `main`](#graduating-next-to-main) below).
4. For subsequent v0 bugfixes, cherry-pick from `main` into `v0.x`:

   ```bash
   git checkout v0.x
   git cherry-pick <commit>
   # follow normal release workflow from here
   ```

5. When EOL is reached, tag a final patch with a changelog entry pointing users to v1, then archive the branch.

## Git Trajectory

```
main          ─●─●─●─●─●─────────────────●─●─●─●─●──── (v1.x development)
                       │                  ▲   │
                       │   v1.0.0 bump ───┘   │ cherry-pick
                       │                      ▼
v0.x           ────────●──────────────────────●──●──✕    (bugfixes only, then archived)
                       │                      │  │  │
                       │                      │  │  └─ archive branch
                       │                      │  └──── tag: metis-core/v0.10.2
                       │                      └─────── tag: metis-engine/v0.10.1
                       └────────────────────────────── branch cut (last v0 state)


Timeline:
─────────────────────────────────────────────────────────────────────►
     v0 dev       cut          v1 dev        bugfixes     v0 EOL
     on main     v0.x          on main       cherry-pick  (archive)
```

## Graduating `next` to `main`

This is a **reusable playbook**, not a one-off: every coordinated major bump developed on `next`
(v0 → v1, later v1 → v2, …) graduates the same way. It stays in this doc across cycles — only the
instance-specific pre-release docs listed in step 2 are torn down each time. Do all of it in the same
coordinated bump commit, so `main` never carries any pre-release scaffolding. Below, `N` is the major
version graduating and `vP.x` is the outgoing line (e.g. N = 1, `vP.x` = `v0.x`).

### 1. Fold the combined changelog back into the per-package files

During the pre-release phase, changelog entries accumulate in a single temporary
[`CHANGELOG.next.md`](../CHANGELOG.next.md) at the repo root rather than in the per-package
`CHANGELOG.md` files (see [CONTRIBUTING.md](../CONTRIBUTING.md#target-branch-next-vs-v0x)).

- For each package section in `CHANGELOG.next.md`, prepend a new `## [N.0.0] — <date>` entry to that
  package's `CHANGELOG.md`, carrying over its `Added` / `Changed` / `Removed` / `Fixed` groups.
- Drop any `_No changes yet._` placeholders — a package with no entries still gets an `N.0.0` heading
  (it participates in the coordinated bump) noting the major-version graduation.
- Delete `CHANGELOG.next.md`.

### 2. Strip the instance-specific pre-release docs

The exception-zone rules only make sense while `next` is the active integration branch. Once it merges,
remove the docs that describe that phase so the guides describe a single stable `main` again (a later
major cycle re-adds equivalents when it opens its own `next`):

- Delete the **"Target branch: `next` vs. `vP.x`"** section from [CONTRIBUTING.md](../CONTRIBUTING.md)
  (the exception-zone rules, the branch-selection table, and the `CHANGELOG.next.md` sentence in the
  `vP.x` paragraph).
- Remove the **pre-release note** from [AGENTS.md](../AGENTS.md) (`CLAUDE.md` symlinks to it, so both
  update at once). The adjacent "each package maintains a `CHANGELOG.md` — write entries during
  development" bullet stays and again reads correctly on its own once the note is gone.

Keep this "Graduating `next` to `main`" section — it is the durable playbook for the next cycle.

### 3. Bump the frozen versions

Flip the `version` field in all five `pyproject.toml` files from `N.0.0a1` to `N.0.0` (and re-lock with
`uv lock`). This is the coordinated bump itself — the same action as [Procedure](#procedure) step 3;
it is restated here so this checklist stands alone.

### 4. Sweep for stragglers

Confirm nothing pre-release is left behind:

```bash
grep -rIn --exclude-dir=.git -e '\bnext\b' -e 'N\.0\.0a1' -e 'CHANGELOG\.next' . \
  | grep -iv 'next steps\|next()\|next('  # discard unrelated prose/code hits, then eyeball the rest
```

Every surviving hit that refers to the retired integration branch or the frozen `N.0.0a1` marker must
go — except the generic references in this playbook itself, which describe the process and stay.

## What Goes Where

| Activity | Branch | Tags |
|----------|--------|------|
| New features (v1) | `main` | `metis-core/v1.0.0`, etc. |
| v0 bugfixes | `v0.x` | `metis-core/v0.10.1`, etc. |
| Release branches (v1) | `release/<pkg>/v1.x.y` → `main` | — |
| Release branches (v0) | `release/<pkg>/v0.x.y` → `v0.x` | — |
