# LMDJ CI Cost and Reliability Hardening Implementation Plan

**Goal:** Remove the two structural causes of the 2026-08-12 CI incident day —
every lane downloading pinned third-party sources from `github.com` on every
run, and every web lane reinstalling its multi-hundred-megabyte toolchain from
scratch — stop identity bumps from costing full CI cycles per missed literal,
and stop paid GitHub-hosted infrastructure from absorbing work the repository
already owns idle hardware to run.

**Architecture:** No product source, Module API, Contract, or Proof semantics
change. Task 1 moves the two pinned dependencies into the repository so builds
and the dependency gate stop depending on `github.com` availability at run
time; the pinned SHA-256/commit checks keep their fail-closed meaning against
the vendored bytes. Task 2 adds `actions/cache` for the Emscripten toolchain,
Playwright browsers, and hosted-runner ccache, keyed on the pinned versions.
Task 3 adds an optional lane filter to `workflow_dispatch` without changing
Ready-PR or push semantics. Task 4 makes the test suite read Product identity
from the manifests it already trusts instead of hard-coding it in four literal
forms. Task 5 corrects runner routing so that a momentarily busy trusted pool
queues instead of diverting an entire run to paid infrastructure. Task 6 adds
a local pre-flight that runs the same lane commands on the developer's machine
before a push, so a correctable failure costs no remote cycle at all.

Tasks 1 through 4 reduce the cost of one CI run. Tasks 5 and 6 reduce which
machine pays for that run, and how many runs are needed. The billing evidence
below shows the second pair dominates the invoice.

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

Cost provenance (GitHub billing usage API, 2026-08-01 through 2026-08-13, and
the Actions jobs API for the runs cited):

- Billed this period: `Actions Linux` 6,259 minutes at `$0.006` (gross
  `$37.55`, net `$31.64`) and `Actions macOS 3-core` 795 minutes at `$0.062`
  (gross `$49.28`, net `$36.69`). macOS is 11 percent of the minutes and 57
  percent of the money; no Task above addresses it.
- A 100-run sample of `ci.yml` job records attributes 752 GitHub-hosted Ubuntu
  minutes, 419 self-hosted minutes, and 39 GitHub-hosted macOS minutes to the
  30 most recent runs — which span `2026-08-12T12:46Z` to
  `2026-08-12T19:01Z`, a single six-hour window on one Pull Request. The
  invoice is driven by the number of remote round trips, which no current Task
  reduces.
- Within those hosted minutes, `creator-web` (176) and
  `web-toolchain-conformance` (171) are 44 percent of the total. Both are
  pinned to `runs-on: ubuntu-24.04` by
  `tests/build/ci_runner_fallback_test.py::test_resource_intensive_web_gates_use_hosted_runners`,
  an invariant deliberately frozen by the risk-based CI gating plan
  (`docs/superpowers/plans/2026-08-11-risk-based-ci-gating.md`, "Do not add
  runners ... in this implementation"). Task 2's caching makes these lanes
  cheaper per run but leaves them entirely on paid infrastructure.
- `select-ubuntu-runner` resolves once, before any workload job starts, and
  requires `.status == "online" and .busy == false`. Because the trusted pool
  holds two runner services while a full manifest needs six Linux lanes, a
  pool that is merely busy at that instant sends the *entire* run to
  GitHub-hosted Ubuntu rather than queueing — the documented "at most two
  selected jobs concurrently; additional jobs queue" behavior in
  `docs/quality/core-test-policy.md` only applies once the pool has already
  been selected. Concurrent retries make each other's runs expensive.
- `select-macos-runner` has the same all-or-nothing shape against a single
  laptop runner (`endaye-mbp-m1`). Every run started while that machine is
  asleep, offline, or busy buys GitHub-hosted macOS at 10.3x the Linux rate,
  with no cap, no warning, and no distinction between a Draft Pull Request and
  a release candidate.
- All three trusted runners (`contabo-lmdj-linux`, `contabo-lmdj-linux-02`,
  `endaye-mbp-m1`) report `online` and `busy == false` at the time of writing,
  so "re-enabling the contabo runners" is no longer the open question the
  owner-decision list below recorded.

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

### Task 5: Route Linux and macOS work to the trusted pools the repository owns

The selectors treat a *busy* trusted pool the same as an *absent* one, so a
single saturated instant diverts a whole 25-minute manifest to paid
infrastructure, and two lanes never consult the pool at all.

- Change trusted-pool eligibility in `select-ubuntu-runner` from
  `.status == "online" and .busy == false` to `.status == "online"`. GitHub
  already queues label-matched jobs against a busy pool; the selector's real
  responsibility is detecting an *absent* pool, not a loaded one. The fork,
  missing-token, and Runner-API-failure fallbacks keep their current
  fail-to-hosted behavior unchanged, because those are trust and availability
  conditions rather than load.
- Operational precondition (not a repository change): run three runner
  services per contabo VM so the trusted Linux pool offers six slots and a
  full manifest's six Linux lanes stop serializing behind two. This adds no
  host and no spend. Record the resulting slot count in
  `docs/quality/core-test-policy.md`, which currently states two.
- Move `web-toolchain-conformance` and `creator-web` onto
  `select-ubuntu-runner`, overturning
  `test_resource_intensive_web_gates_use_hosted_runners`. That invariant
  protected two browser-heavy suites from a two-slot pool; with six slots and
  Task 2's toolchain caches the premise no longer holds. Rewrite the test to
  assert the selector topology for these jobs instead of deleting it, so the
  routing stays pinned in the opposite direction.
- Bound the macOS hosted fallback by event rather than leaving it unbounded:
  `push` to `main`, `workflow_dispatch`, and release candidates may still
  select GitHub-hosted macOS immediately; a Pull Request run queues for
  `endaye-mbp-m1`. The infrastructure-recovery semantics of `macos-fallback`
  itself — one attempt, only for a missing terminal result, never after a
  published semantic failure — are unchanged.
- Gate boundary: routing decides which machine executes a lane, never whether
  its result is required. The `PR Gate` truth table, the 18-result key set,
  the no-retry policy, fork isolation, LFS hydration, and package ccache
  suppression are all untouched.
- Verify: `tests/build/ci_runner_fallback_test.py`,
  `tests/build/ci_build_acceleration_test.py`,
  `tests/build/ci_workflow_topology_test.py`; a full-mode dispatch issued
  while the pool is deliberately saturated must show queued self-hosted jobs
  rather than `GitHub Actions` runner names; compare hosted minutes for the
  same manifest through the Actions jobs API before and after.

Files: `.github/workflows/ci.yml`, `tests/build/ci_runner_fallback_test.py`,
`docs/quality/core-test-policy.md`,
`apps/architecture-portal/docs/operations/testing-and-proof.mdx`.

### Task 6: Local pre-flight that reuses the CI scope decision

Nothing today lets a developer learn a lane's verdict without spending a
remote cycle, and nothing lets an unchanged lane be skipped between
iterations. Task 3 narrows a manual dispatch but still round-trips.

- Add `scripts/ci/local_preflight.py` and a thin `scripts/local-ci.sh`
  entry point. The pre-flight runs `scripts/ci/change_scope.py` against
  `git diff` of the working branch versus `origin/main` to obtain the same
  `lmdj.ci-scope.v1` manifest CI would compute, then executes each selected
  lane locally.
- The lane-to-local-command mapping lives in `scripts/ci/local_lanes.json`,
  keyed by the policy's canonical lane list, with a contract test asserting
  key equality against `policy["lanes"]` so the pre-flight cannot silently
  drift from the workflow.
- Cache each lane verdict under `~/.cache/lmdj/preflight/` keyed by a digest
  of the lane name, its resolved command, and the content hashes of every
  path the policy maps to that lane. A lane whose inputs are unchanged since
  its last local pass reports `cached-pass` and does not re-execute. The
  cache lives outside the worktree and has no path into a CI result.
- Report honestly rather than optimistically. Lanes that cannot execute on
  the developer's platform — `core_asan`'s Python-hosted sanitizer coverage
  on arm64 macOS, `core_coverage`'s Linux toolchain — report
  `not-runnable-here`, never `pass`. The pre-flight is an advisory filter and
  produces no evidence: `PR Gate` remains the single aggregate decision, and
  a green local run authorizes no push, merge, or state transition.
- Provide `--install-hook` to write a `pre-push` hook that runs the
  pre-flight and refuses the push on a hard failure, with `--no-verify`
  documented as the deliberate escape.
- Add scope rules for the new files. `change_scope.py` sends any path that
  matches no rule to full mode (`unclassified path`), so
  `scripts/local-ci.sh`, `scripts/ci/local_lanes.json`, and the new test must
  be classified — the two `scripts/ci/` paths already inherit the central
  control-plane full rule; `scripts/local-ci.sh` needs an explicit
  `ci_contract` mapping.
- Verify: `tests/build/ci_local_preflight_test.py` covering manifest reuse,
  cache-key invalidation on a touched input, and the `not-runnable-here`
  classification; a docs-only working tree selects exactly `docs_static`; a
  `packages/foundation/` edit selects the core lanes; a second consecutive
  invocation with no edits reports every lane cached.

Files: `scripts/ci/local_preflight.py`, `scripts/ci/local_lanes.json`,
`scripts/local-ci.sh`, `tests/build/ci_local_preflight_test.py`,
`scripts/ci/scope_policy.json`, `docs/governance/git-workflow.md`,
`docs/quality/core-test-policy.md`.

## Task order and independence

Tasks 5 and 6 are independent of each other and of Tasks 1 through 4, and
both should land before Task 3: Task 3 makes a targeted remote run cheaper,
while Tasks 5 and 6 remove remote runs and paid runners from the loop
entirely. Task 6 touches no workflow file and can proceed while Task 5's
runner provisioning is still in progress.

## Owner decisions deliberately not taken here

- Reducing the double-clean-build byte-identity proofs (they are the
  determinism gate; halving them would trade governance strength for
  minutes).
- Playwright worker parallelism inside the conformance suites (the 6-minute
  single-worker Project I/O spec is timing-sensitive around fault
  injection; parallelizing risks flakiness for ~4 minutes saved).
- Hosted ccache: `ci_build_acceleration_test` currently forbids it, and the
  value is uncertain on ephemeral runners because the ccache directory must
  round-trip through `actions/cache` on a parallelism-3 build. Enabling it
  means changing that contract test, which is an owner decision. The three
  Ubuntu compile lanes keep today's self-hosted-only behavior.
- Re-enabling the contabo runners is no longer open: all three trusted
  runners report `online` and idle, so Task 5 addresses slot count and
  selector eligibility instead of service availability.
- Adding trusted hosts. Task 5 raises Linux capacity by running more runner
  services on the existing VMs; buying a second Mac or more Linux capacity is
  a spending decision left to the owner, and the pre-flight in Task 6 is the
  cheaper answer to the same pressure.
- A hard spending cap or budget alert on GitHub-hosted minutes. Task 5 bounds
  when hosted macOS may be selected, which is a routing rule; an account-level
  cap is an owner-side billing control outside this repository.
- Replacing GitHub Actions with a purely local gate. `main` is protected and
  the governance model depends on externally auditable run records for portal
  snapshots and release evidence; Task 6 deliberately produces an advisory
  filter rather than a substitute for `PR Gate`.

## Version Management

Canonical policy: `docs/governance/version-management.md`.

Version impact: none.
Reason: No Module, Host, Provider, Contract, or Assembly identity changes.
Tasks change build supply, workflow caching, CI control plane, runner routing,
local developer tooling, and test plumbing. Tasks 5 and 6 in particular change
only which machine executes a lane and whether a developer learns its verdict
before pushing; neither alters a lane's command, its required status, or its
inputs. Built Product artifacts remain byte-identical (same pinned inputs),
which the unchanged double-clean-build gates continue to prove. Precedent:
#115/#116 (CI control plane) carried no version impact. If review concludes
that vendoring constitutes an Assembly-visible change, the fallback is a
PATCH candidate allocated at integration time under the standard rules.

## Documentation Impact

Documentation impact: required.

- Affected portal routes: `/operations/testing-and-proof/` (dependency gate
  now verifies vendored sources offline; toolchain caching and its
  determinism boundary; dispatch lane selection; Task 5's selector
  eligibility rule, trusted Linux slot count, web-lane routing, and the
  event-bounded macOS fallback).
- `docs/quality/core-test-policy.md` is updated by Tasks 5 and 6: the
  two-concurrent-job statement, the "busy" selector condition, the
  hosted-by-design web lanes, the macOS fallback trigger set, and the new
  advisory pre-flight and its explicit non-evidence status.
- `docs/governance/git-workflow.md` is updated by Task 6 with the pre-flight
  invocation, the optional `pre-push` hook, and a restatement that a local
  pass authorizes no push, Pull Request, merge, or later state transition.
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

Tasks 5 and 6 add one further completion condition, measured rather than
asserted: after the merged `main` run, the Actions jobs API for that run must
attribute the six Linux lanes and `macos-primary` to named self-hosted
runners rather than `GitHub Actions` runner names, and the following billing
period must show hosted Ubuntu and hosted macOS minutes below the
2026-08-01..13 baseline recorded in the cost provenance above. A routing
change that does not move minutes has not achieved its goal, whatever the
workflow file says.
