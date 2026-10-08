# Portal dependency security maintenance

## Task and scope

Refresh the Portal dependency tree against the eight open Dependabot alerts
observed on 2026-10-08. This Task changes only:

- `apps/docs-site/package.json`
- `apps/docs-site/package-lock.json`
- `docs/plans/2026-10-08-portal-dependency-security.md`
- `.agents/pitfalls/npm-major-override-lockfile-drift.md`

Creator, product identities, release state and CI control-plane are outside this
Task. All installs and builds use this Task's isolated worktree and cache.

## Implementation

Docusaurus 3.10.2 is still the latest published release. Its dependency ranges
retain affected versions, so use exact, scoped overrides for tinypool 2.1.2,
serialize-javascript 7.0.5 (copy and CSS minimizer consumers), and uuid 11.1.1
(SockJS consumer). Override affected postcss-selector-parser versions to 7.1.6,
covering both the 6.x and 7.x branches. Use an unconditional exact package
override: a conditional `<7.1.6` override installed with npm 11 but caused the
declared npm 10.9.3 clean install to report missing 6.1.4 lock entries. The final
lockfile must pass a clean install with npm 10.9.3. Do not change unrelated direct
packages.

The tinypool 2.0 and serialize-javascript 7.0 breaking changes raise their Node
minimums; the Portal already requires Node 26. Selector-parser 7 changes safe
insertion during traversal. SockJS calls the preserved `uuid.v4()` interface.
Compatibility requires executing the consumers, beyond resolving package names.

Alias the direct `gray-matter` dependency to `@11ty/gray-matter` 1.0.0, the fork
already used by Docusaurus utils. Its js-yaml 4 dependency removes the old argparse
and sprintf-js path while preserving the import name used by Portal scripts.

`braces` 3.0.3 has no published patched version for GHSA-vfj7-8cjw-p6xm, and both
Docusaurus' micromatch and chokidar still require it. Keep that alert visible;
this Task neither dismisses it nor claims all dependencies are free of alerts.

## Verification

- Clean `npm ci` after the lockfile update; inspect the installed dependency tree
  and `npm audit --json` against the original alert inventory.
- `scripts/docs-site.sh check`: all Portal tests, document metadata, diagrams,
  derived facts, immutable release docs, typecheck, production build and far-side
  routes/identity/link checks, without weakening any check.
- Execute tinypool worker run/destroy and SockJS session exchange; verify the
  serializer and both selector-parser consumers on their resolved safe versions.
- Run the CSS minimizer/copy consumer production build and retain its output.
- Stage the declared plan and run `python3 tests/build/ci_change_scope_test.py`.
- Classify the committed range and satisfy any selected batch-only lane before
  merge. Independent current-head review remains required.

## Version Management

Version impact: none
Reason: Portal build tooling is independent of Product Assembly, Host, Module,
Provider and Contract version identities; no Product Build is allocated here.

## Documentation Impact

Documentation impact: none
Reason: Dependency maintenance changes no current manual page, product behavior,
public boundary, projected identity or documented operating procedure. The full
Portal proof still applies because its build tooling changes.

## Pitfall Impact

Pitfall impact: new npm-major-override-lockfile-drift
Reason: Conditional overrides produced an npm-major-specific clean-install
difference that cannot be inferred from product code; record the declared npm
verification boundary without changing shared CI control-plane.

## Primary evidence

- https://github.com/tinylibs/tinypool/releases/tag/v2.0.0
- https://github.com/yahoo/serialize-javascript/releases/tag/v7.0.0
- https://github.com/postcss/postcss-selector-parser/releases/tag/v7.0.0
- https://github.com/11ty/gray-matter
- https://github.com/advisories/GHSA-vfj7-8cjw-p6xm
- https://github.com/advisories/GHSA-hp3w-g68c-fv3c
