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

3. Land the coordinated v1 bump on `main` (all `pyproject.toml` versions → `1.0.0`).
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

## What Goes Where

| Activity | Branch | Tags |
|----------|--------|------|
| New features (v1) | `main` | `metis-core/v1.0.0`, etc. |
| v0 bugfixes | `v0.x` | `metis-core/v0.10.1`, etc. |
| Release branches (v1) | `release/<pkg>/v1.x.y` → `main` | — |
| Release branches (v0) | `release/<pkg>/v0.x.y` → `v0.x` | — |
