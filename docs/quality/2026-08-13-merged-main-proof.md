# Merged-main Proof Record — 2026-08-13

## Why this record exists

The Stage 7 review recorded finding G1 — no merged-main Proof record existed
for the Product Builds that were merged and tagged — and escalated it to high
severity on the reading that a signed tag had been created without its stated
precondition.

That reading was too harsh, and this record corrects it. `ci.yml` runs on
`push: branches: [main]`, and `scripts/ci/change_scope.py` forces **full mode
(all lanes)** for `push` events. A full-lane Proof therefore runs
automatically on the merged revision after every merge — it is not something
anyone has to remember to trigger. The runs existed all along; what did not
exist was any document binding them to a Build identity.

**G1 is a documentation gap, not a governance violation.** The evidence below
is recovered from the runs that already happened.

## Recovered evidence for the tagged Builds

Both tagged Product Builds have a green, full-mode `push` run on `main` at
exactly the revision their signed tag points to.

| Product Build | Signed tag → revision | main `push` run | Result |
| --- | --- | --- | --- |
| `1.0.16.5` | `lmdj-v1.0.16.5` → `38a8c13` | [31327104838](https://github.com/endaye/lmdj/actions/runs/31327104838) | **success** — 12 jobs green, 1 designed skip |
| `1.0.16.8` | `lmdj-v1.0.16.8` → `336a27c` | [31529410253](https://github.com/endaye/lmdj/actions/runs/31529410253) | **success** — 20 jobs green, 1 designed skip |

The single non-success job in each run is `macOS gates (GitHub-hosted
fallback)`, which is `skipped` by design whenever `macOS gates (primary)`
succeeds on the trusted Mac. The job-count difference between the two runs
reflects lanes added to the workflow between those dates, not a narrower
selection: both ran in full mode.

Neither tag's precondition was violated. What was missing — and what this
record supplies — is the binding from tag to run.

## Current-revision Proof — Product Build `1.0.16.9`

| Field | Value |
| --- | --- |
| Product Build | `1.0.16.9`, Channel `canary` |
| Revision | `d1d8bb6a629b6e05b86b3c8843870ef27edcfe5c` (`main`) |
| Merge | PR #130, `fix(ci): vendor pinned dependencies and cache the web toolchain` |
| Run | [31634688566](https://github.com/endaye/lmdj/actions/runs/31634688566), event `push`, full mode, created 2026-08-12T19:51:04Z |

| Lane / job | Runner | Result |
| --- | --- | --- |
| Change Scope | hosted | success |
| Architecture Portal / portal | hosted | success |
| Docs / static | hosted | success |
| CI contract | hosted | success |
| Deploy contract | hosted | success |
| Chameleon Lab | hosted | success |
| Select Ubuntu runner | hosted | success |
| Select macOS runner | hosted | success |
| core (ubuntu-latest) | contabo-lmdj-linux | success |
| core-asan | contabo-lmdj-linux-02 | success |
| core-coverage | contabo-lmdj-linux | success |
| Core package | contabo-lmdj-linux | success |
| web-runtime-lab | contabo-lmdj-linux | success |
| web-toolchain-conformance | hosted | success |
| creator-web | hosted | success |
| core (macos-latest) | hosted | success |
| core-asan-macos | hosted | success |
| macOS gates (primary) | endaye-mbp-m1 | success |
| macOS gates (GitHub-hosted fallback) | — | skipped by design (primary succeeded) |
| web-runtime-host | contabo-lmdj-linux-02 | success — 33.4 min against the 45-minute limit in force at the time |
| PR Gate | hosted | success — adjudicated every lane above |

The run concluded `success` at 2026-08-12T20:33:17Z, 42.2 minutes wall-clock.
This is the first green merged-main Proof since 2026-08-12 17:43Z. The four
`push` runs before it failed, for causes now fixed rather than for candidate
defects:

| Revision | Run | Cause of failure |
| --- | --- | --- |
| `6f127ff` | 31624068158 | pinned dependency downloads throttled from `github.com` |
| `ea22934` | 31625476029 | same, plus the `1.0.16.9` snapshot provenance unauthenticated after a manual merge |
| `3ebe27a` | 31625804949 | unclassified top-level `LICENSE`, plus the above |
| `d3dc0d7` | 31628507290 | `LICENSE` classification and a dependency-download failure |

PR #129 authenticated the snapshot provenance, PR #130 vendored the
dependencies and classified `LICENSE`. This run is the evidence that those
three repairs hold on the merged tree.

## Observations from this run

- Runner-persistent ccache on the trusted Linux pool is doing real work:
  `core (ubuntu-latest)` completed in 1m32s here against ~18 minutes in the
  preceding pull-request run, because the self-hosted `CCACHE_DIR` was warm
  from that run's compile of the same tree.
- `web-runtime-host` is the pool's critical path and it decides this run's
  wall-clock: 33.4 minutes of the 42.2-minute total, against 16-19 minutes
  for the same lane on GitHub-hosted runners. The other five trusted-pool
  lanes together account for roughly 19 minutes. Its limit has since been
  calibrated from 45 to 75 minutes, because 45 left too little headroom once
  pool contention rises.
- The `actions/cache` toolchain caches added by PR #130 are **not** expected
  to show a benefit in this run. GitHub scopes caches by branch: a cache
  written on a pull-request branch is not readable from `main`. This run
  populates the `main` scope; the saving appears on the next `main` push run.

## Boundary

This record establishes merged-main Proof only. It does not establish a
signed Product tag for `1.0.16.9` (none exists), Release, deployment,
publication, Channel promotion, or physical-device acceptance. The five
physical rows remain `deferred / unverified` and continue to block
physical-pass, `beta`, and `stable`.

| Platform | Browser | Input / journey | Status |
| --- | --- | --- | --- |
| macOS | Safari | Pointer | `deferred / unverified` |
| macOS | Chrome | Pointer | `deferred / unverified` |
| macOS | Chrome | Physical MIDI | `deferred / unverified` |
| iPadOS | Safari | Touch | `deferred / unverified` |
| iPadOS | Safari | Lifecycle | `deferred / unverified` |

## Keeping this cheap

Because full-mode Proof runs automatically on every `main` push, maintaining
this evidence costs a lookup, not a CI cycle. The durable practice is: after
each merge, record the `push` run id and its conclusion against the Product
Build on `main`. A red merged-main run is a signal that `main` is not
deployable and should be treated as such rather than left unrecorded — that,
not a missing run, was the real content of G1.

## Stage 7 remediation current binding — Product Build `1.0.21.0`

PR #134 was protected by successful full PR workflow
[31684663825](https://github.com/endaye/lmdj/actions/runs/31684663825) and
squash-merged as `5613158240f7e31385ccb5d175bded3c245ae33b`. Its PR head
`0f403e805694bce957644e004090dda8d60cbaf6` and the merge revision resolve to
the same tree, `5251522137323f926a8bfa4c04088f5abd31a9eb`.

The exact merge triggered full `main` push run
[31688172806](https://github.com/endaye/lmdj/actions/runs/31688172806). Its
retained scope manifest selects all 14 lanes; the run completed with 20
successful jobs, one designed macOS fallback skip, zero failures, and a
successful aggregate `PR Gate`. A fresh isolated-worktree rerun from exact
`5613158` also passed Core full/stress/coverage/Proof, Web Toolchain, Formal
Host, Creator, Portal, dependency, active-tree, Product version, Assembly, and
lock gates.

The complete exact revisions, hashes, runner ownership, fresh command results,
and unchanged physical-evidence boundary are recorded in
[`2026-08-13-stage7-remediation-merged-main-1.0.21.0.md`](../release-evidence/2026-08-13-stage7-remediation-merged-main-1.0.21.0.md).
