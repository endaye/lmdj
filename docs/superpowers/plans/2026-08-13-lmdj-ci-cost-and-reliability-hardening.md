# LMDJ CI Cost and Reliability Hardening Implementation Plan

**Goal:** Remove the two structural causes of the 2026-08-12 CI incident day —
every lane downloading pinned third-party sources from `github.com` on every
run, and every web lane reinstalling its multi-hundred-megabyte toolchain from
scratch — and stop identity bumps from costing full CI cycles per missed
literal.

**Architecture:** No product source, Module API, Contract, or Proof semantics
change. Task 1 moves the two pinned dependencies into the repository so builds
and the dependency gate stop depending on `github.com` availability at run
time; the pinned SHA-256/commit checks keep their fail-closed meaning against
the vendored bytes. Task 2 adds `actions/cache` for the Emscripten toolchain,
Playwright browsers, and hosted-runner ccache, keyed on the pinned versions.
Task 3 adds an optional lane filter to `workflow_dispatch` without changing
Ready-PR or push semantics. Task 4 makes the test suite read Product identity
from the manifests it already trusts instead of hard-coding it in four literal
forms.

Incident provenance (2026-08-12, all auditable in this repository's run
history):

- `github.com` edge throttled the contabo runners (HTTP/2 `REFUSED_STREAM`
  x5 -> curl 56) and later returned 503 to GitHub-hosted runners for the same
  release asset, while `objects.githubusercontent.com` and a residential
  connection stayed healthy (diagnostic run 31622225202; hosted 503s in run
  31624942435). Five lanes fetch the identical 114 KiB archive within seconds
  of each other on every run.
- Both web lanes clone and install the pinned emsdk 6.0.5 from scratch on
  every run (`ci.yml` "Clone pinned emsdk", two sites) and reinstall
  Playwright Chromium+WebKit; `actions/cache` is not used anywhere in the
  workflow, and ccache exists only as a self-hosted-runner convenience.
- The `1.0.16.9` identity propagation cost two extra full CI cycles because
  the Product Build appears in four literal shapes the token pass could not
  see uniformly: dotted strings, `ProductVersion(1, 0, 16, 8)` positional
  arguments, numeric `"patch": 8` JSON fields, and a Build embedded in an
  acceptance-report filename.

## Global Constraints

- Work happens on `fix/ci-cost-hardening` in an isolated worktree; `main`
  stays deployable.
- Each Task is one reviewable Conventional Commit with its declared files
  only.
- Pinned dependency identities do not move: nlohmann/json v3.12.0
  (`42f6e95c...`) and PicoSHA2 `161cb3fc...` stay exactly as pinned; only
  their supply channel changes. Licenses accompany the vendored sources.
- Gate semantics may not weaken: the dependency gate still fails closed on a
  hash mismatch; cache misses must fall back to the existing download path;
  Draft/Ready/push lane selection rules are unchanged.
- `scripts/ci/` and `.github/workflows/ci.yml` are the central CI control
  plane — every Task here triggers full-mode CI by policy, which is expected
  and correct.
- This plan settles no open product-level Contract or concurrency question.

## Tasks

### Task 1: Vendor the pinned third-party sources — IMPLEMENTED (`15a798b`)

`scripts/verify-core-dependencies.sh` curls the nlohmann/json release archive
and fetches PicoSHA2 from `github.com` on every core lane of every run, and
`cmake/LmdjDependencies.cmake` FetchContent-downloads the same archive in
every build. Both artifacts are tiny (114 KiB archive; PicoSHA2 is a
single-header library) and both are already pinned by content identity, so
the network fetch adds availability risk without adding trust.

- Add `third_party/nlohmann-json/json-v3.12.0.tar.xz` (byte-identical to the
  pinned archive) and `third_party/picosha2/` (the pinned commit's sources)
  with their MIT license files and a `third_party/README.md` recording the
  upstream URLs, versions, and pinned identities.
- Rework `scripts/verify-core-dependencies.sh` to verify the vendored bytes
  against the same pinned SHA-256/commit-derived identity, offline. The gate
  keeps failing closed on any mismatch; it no longer has an
  environment-blocked failure mode.
- Point `cmake/LmdjDependencies.cmake` at the vendored archive
  (`URL file://...` with the existing `URL_HASH`), removing the network path
  from configure entirely.
- Update `tests/build/test_active_tree.sh` / source-boundary expectations for
  the new `third_party/` top level, and the scope policy's
  `known_top_levels` (`scripts/ci/scope_policy.json`) with `third_party/`
  mapped to the core family.
- Verify: `bash scripts/verify-core-dependencies.sh` offline (network
  disabled), `scripts/core.sh proof`, `bash tests/build/test_active_tree.sh`.

Files: `third_party/**`, `scripts/verify-core-dependencies.sh`,
`cmake/LmdjDependencies.cmake`, `scripts/ci/scope_policy.json`,
`tests/build/test_active_tree.sh`.

### Task 2: Cache toolchains and compiler state on hosted runners — IMPLEMENTED without ccache (`dbf4497`)

Every web lane clones emsdk and runs `emsdk install 6.0.5` (hundreds of
megabytes from GitHub's release infrastructure), then installs Playwright
Chromium+WebKit, on every run. Hosted core lanes rebuild cold every time.

- Wrap both "Clone pinned emsdk" sites with `actions/cache` keyed on the
  pinned emsdk revision + SDK version (`emsdk-dfb9d1a4-6.0.5-<os>`); on hit,
  skip clone/install and only `emsdk activate`/source the environment. On
  miss, the existing steps run unchanged and the cache is saved.
- Cache Playwright browsers (`~/.cache/ms-playwright`) keyed on the pinned
  Playwright version from the relevant lockfile; keep
  `playwright install --with-deps` as the miss path (`--with-deps` system
  packages still install each run; browsers do not re-download).
- Hosted ccache is **not** implemented. `tests/build/ci_build_acceleration_test.py`
  pins ccache to the self-hosted lane and asserts `actions/cache` never appears
  inside the acceleration action, so hosted ccache would require overturning an
  existing deliberate invariant. Recorded below as an owner decision instead.
- Determinism boundary: caches supply *inputs* (toolchain, browsers,
  compiler object cache) only. The double-clean-build byte-identity gates in
  the web proofs are unchanged and keep proving that outputs do not depend
  on cache state.
- Verify: two consecutive full-mode dispatch runs — first populates, second
  hits; compare wall-clock on `web-toolchain-conformance`,
  `web-runtime-host`, `creator-web`, and hosted core lanes; byte-identity
  gates still pass.

Files: `.github/workflows/ci.yml`,
`.github/actions/configure-build-acceleration/action.yml`.

### Task 3: Lane selection input for workflow_dispatch

Policy sends every manual dispatch to full mode — all 14 lanes — so a
targeted verification (one browser suite, one host proof) burns the entire
matrix. On 2026-08-12 that multiplied every retry.

- Add an optional `lanes` input to `workflow_dispatch` (comma-separated lane
  names validated against the policy's canonical list). Empty input keeps
  the current behavior: full mode, all lanes.
- Thread the input through `Change Scope`: a non-empty selection produces a
  `focused` manifest with exactly the requested lanes plus their required
  jobs; `PR Gate` adjudicates that manifest as it already does for focused
  Ready PRs. Draft, Ready, push, and label semantics are untouched.
- Extend `scripts/ci/change_scope.py` validation and
  `tests/build/ci_runner_fallback_test.py` / scope tests for the new input,
  including rejection of unknown lane names (fail closed).
- Verify: `python3.11` scope tests; a dispatch with `lanes=docs_static`
  runs exactly that lane plus gate; a dispatch with empty input still
  selects all 14.

Files: `.github/workflows/ci.yml`, `scripts/ci/change_scope.py`,
`scripts/ci/scope_policy.json` (if a schema field is needed), scope tests.

### Task 4: Single-source Product identity in tests

Four literal shapes of the Product Build live in tests and specs; every
corrective candidate must find all of them or burn a full CI cycle per miss.

- `tests/host/cli_test.py`, `tests/host/mcp_stdio_test.py`,
  `apps/creator-web/test/package_test.py`, and
  `apps/creator-web/test/server_test.py` read the expected identity from
  `products/lmdj/version.json` / the module manifests instead of hard-coding
  dict literals. The assertions keep their exactness — they compare the
  binary/manifest output against the parsed source of truth, so a real
  mismatch still fails; what disappears is the duplicated literal.
- `tests/build/version_test.py` keeps its structural assertions
  (`ProductVersion` shape and invalid-input rejection) but derives the
  expected current version from `version.json` rather than repeating it.
- `tests/platform/web/creator/creator_web_browser.spec.mjs` builds the
  expected acceptance-report filename from the packaged distribution
  manifest it already loads, not a hard-coded Build string.
- Explicitly out of scope: the dual-Host runtime identity constants
  (`apps/creator-web/src/main.tsx` / `apps/web-runtime-host/src/main.mjs`,
  Stage 7 review F5) are product source with a manifest gate behind them;
  single-sourcing them is a product Task, not a CI Task.
- Verify: `scripts/core.sh proof`, `creator-web` lane; then a rehearsal bump
  of `version.json` on a scratch branch must fail only the version gates,
  not the host/creator identity tests.

Files: the five test files above.

## Owner decisions deliberately not taken here

- Reducing the double-clean-build byte-identity proofs (they are the
  determinism gate; halving them would trade governance strength for
  minutes).
- Playwright worker parallelism inside the conformance suites (the 6-minute
  single-worker Project I/O spec is timing-sensitive around fault
  injection; parallelizing risks flakiness for ~4 minutes saved).
- Re-enabling the contabo runners (operational: with Task 1 landed, runner-side
  github.com health no longer matters for the dependency gate).
- Hosted ccache: `ci_build_acceleration_test` currently forbids it, and the
  value is uncertain on ephemeral runners because the ccache directory must
  round-trip through `actions/cache` on a parallelism-3 build. Enabling it
  means changing that contract test, which is an owner decision. The three
  Ubuntu compile lanes keep today's self-hosted-only behavior.

## Version Management

Canonical policy: `docs/governance/version-management.md`.

Version impact: none.
Reason: No Module, Host, Provider, Contract, or Assembly identity changes.
Tasks change build supply, workflow caching, CI control plane, and test
plumbing; built Product artifacts remain byte-identical (same pinned inputs),
which the unchanged double-clean-build gates continue to prove. Precedent:
#115/#116 (CI control plane) carried no version impact. If review concludes
that vendoring constitutes an Assembly-visible change, the fallback is a
PATCH candidate allocated at integration time under the standard rules.

## Documentation Impact

Documentation impact: required.

- Affected portal routes: `/operations/testing-and-proof/` (dependency gate
  now verifies vendored sources offline; toolchain caching and its
  determinism boundary; dispatch lane selection).
- No Product Build or Assembly change is planned, so no immutable snapshot
  is required; if the fallback PATCH allocation triggers, the snapshot
  obligation follows automatically.

## Pull Request and Completion Boundary

Every Task here touches the central CI control plane, so each integration
candidate runs full-mode CI by policy. After the final Task, inspect every
commit and staged file list, run `git diff --cached --check` per commit, and
request code review before any push authorization. A green local run does not
authorize push; a green pushed PR does not authorize merge. The plan is
complete only when the approved PR is squash-merged, required checks pass on
current code, and merged `main` re-runs Core, Web Runtime Host, Creator Web,
and Portal Proof — with the second consecutive run demonstrating the intended
cache-hit wall-clock reduction.
