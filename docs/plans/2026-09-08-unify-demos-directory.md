# Unify standalone projects under demos

## Scope

Move the three existing `references/demos/` projects to root `demos/`, preserving
source and assets. Permit continued iteration and indefinite retention under Git.
Keep these independent projects outside formal product builds and releases.
Update current navigation and CI path ownership; preserve historical evidence and
immutable portal snapshots. Do not implement the ESP32 concurrency prototype here.

## Verification

- Verify tracked project inventory, unchanged source/assets and file modes.
- Run `bash tests/build/test_active_tree.sh`.
- Run `python3 tests/build/ci_change_scope_test.py` after staging the new paths.
- Run `scripts/architecture-portal.sh check`.
- Inspect staged paths and `git diff --cached --check` before a local commit.

## Version Management

Version impact: none. Directory organization and documentation only; no Product
Build, Module, Provider or Contract identity changes.

## Documentation Impact

Documentation impact: required. Update current portal route
`/history/legacy-patch-architecture`, root/source-boundary documentation, demo
navigation and run commands. No immutable version snapshots are modified.
