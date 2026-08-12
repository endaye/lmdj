# OPFS Publication and Recovery Fix Acceptance — 2026-08-12

## Current status

The OPFS publication and recovery candidate is Product Build `1.0.16.9`,
Channel `canary`, with Project I/O `0.5.3`, Application Facade `1.3.4`, Web
Runtime Platform `0.1.6`, Web Runtime Host `1.2.6`, and Creator Web `1.0.6`.
Its immutable Portal snapshot is frozen at source revision
`b2294005c09975d8414105861a0b4c0939cabd7f`. The evidence revision for this
record is branch head `1d0fad3` of `fix/opfs-publication-recovery`, which
differs from the snapshot revision only by evidence-alignment commits
(`1e2b1e2` numeric product-version assertions, `1d0fad3` the Creator
acceptance-report filename expectation); no Product, Module, Host, Contract,
or snapshot source changed after the freeze.

Unlike prior acceptance records, the primary evidence here is **CI
`workflow_dispatch` full-mode runs**, not a local clean-room Proof: the
authoring machine has no Emscripten toolchain, so the browser conformance
suites could only run in CI. Run IDs and per-lane conclusions are recorded
below so each claim stays bound to an auditable revision. This result does not
establish merge, a signed Product tag, Release, deployment, publication,
Channel promotion, or physical-device acceptance.

## What the candidate changes

Two Web OPFS recovery defects from
`docs/quality/2026-08-12-stage7-creator-editor-review.md` (F1, F2), both in
`packages/project-io/src/web/library_opfs_storage.js`:

- A failed directory publication now removes its pending publication intent
  only after the destination is positively confirmed absent; otherwise the
  `pending` intent survives and recovery owns the cleanup on the next writer
  acquisition. Previously the swallowed cleanup failure plus unconditional
  intent removal could leave an unprotected half-built destination that made
  `list_local_projects` fail for the entire Workspace with no recovery path.
- Writer-acquisition recovery now classifies an undecodable or unparseable
  Host storage intent record as torn and removes it, because `createIntent`
  writes and read-back-verifies the record before any destination write and
  never reuses an existing intent file — a torn record proves the mutation
  never began. Records that parse but fail validation stay fail-closed so an
  older reader can never destroy rollback state written by a newer Contract
  revision. Previously one torn record made every later `acquire_writer`
  fail, locking the Project until OPFS was cleared by hand.

Both storage record shapes, all success paths, and the no-overwrite collision
semantics are unchanged.

## Automated evidence

CI runs are GitHub Actions `Core CI` `workflow_dispatch` (full mode, all
lanes) on `fix/opfs-publication-recovery`; dates are 2026-08-12 UTC.

| Gate | Result and binding |
| --- | --- |
| `web-toolchain-conformance` (Chromium/WebKit toolchain, Chromium Project I/O conformance incl. the two new fault cases, Chromium AudioWorklet) | PASS at `1d0fad3` (run 31619225148); also PASS at `1e2b1e2` (run 31617909553) and `26f67c7` (run 31616344202). Case-level log at run 31602589389: Chromium Project I/O 3/3 including the new publication-cleanup-failure and torn-intent phases; WebKit capability path 1 pass/1 designed skip; Chromium AudioWorklet 21/21 |
| `creator-web` (Vitest, package/server, packaged Chromium journey, WebKit boundary) | PASS at `1d0fad3` (run 31619225148) |
| `core (macos-latest)`, `core-asan-macos` | PASS at `1d0fad3` (run 31619225148) |
| `macOS gates (primary)` | PASS at `1d0fad3` (run 31619225148) |
| `Core package` | PASS at `1d0fad3` (run 31619225148, attempt 2) |
| `Architecture Portal / portal`, `Docs / static`, `CI contract`, `Deploy contract`, `web-runtime-lab`, `Chameleon Lab`, `Change Scope` | PASS at `1d0fad3` (run 31619225148) |
| `core (ubuntu-latest)`, `core-asan`, `core-coverage` | ENVIRONMENT BLOCKED at `1d0fad3`: two attempts failed in `scripts/verify-core-dependencies.sh` with `curl (56)` fetching the pinned third-party sources from `github.com` on the self-hosted `contabo` Linux runners. Not recorded as PASS. The same three lanes PASS at `1e2b1e2` (run 31617909553), whose lane-relevant tree is identical — `1d0fad3` changes one Creator Playwright expectation only |
| `web-runtime-host` | ENVIRONMENT BLOCKED at `1d0fad3`: two attempts failed in CMake `FetchContent` — "Each download failed" for `nlohmann/json v3.12.0` with "Failure when receiving data from the peer" and an SSL local-issuer warning on the same self-hosted runners. Not recorded as PASS. The same lane PASS at `1e2b1e2` (run 31617909553) and at `26f67c7` (run 31616344202); its lane-relevant tree is unchanged through `1d0fad3` |
| Local `scripts/core.sh proof` (Python 3.11) | PASS at the `1e2b1e2` tree: 37/37 CTests, schema checks 9 positive/11 negative/17 Product artifacts, package acceptance PASS, Product `1.0.16.9`, Channel `canary`, Assembly Lock `MATCH` |
| Local `scripts/architecture-portal.sh check` | PASS at `26f67c7` (42 routes and internal links valid, snapshot gap closed) |
| Local `python3.11 scripts/version.py verify`, `tests/build/version_test.py`, `tests/conformance/version_lock_test.py`, `tests/conformance/module_graph_test.py`, `bash tests/build/test_active_tree.sh` | PASS at `b229400` |

The blocked rows are a runner-environment failure, not candidate evidence:
the pinned dependency identities (SHA-256 for nlohmann/json, pinned commit
for PicoSHA2) are recorded in tracked source and independently verifiable,
and every blocked lane has a green run on this branch at a lane-equivalent
tree. They remain blocked in this record until a green run exists at the
evidence revision itself.

## Conformance journey for the two fixes

The Chromium Project I/O conformance suite drives the production
Emscripten/OPFS storage library end to end. The new publication phase injects
a publication that fails *with* a failing destination cleanup and asserts the
pending intent survives, enumeration keeps hiding the physically complete
destination, and a later writer acquisition recovers and republishes the
Project. The new recovery phase writes a truncated intent body for a prepared
Project and asserts acquisition succeeds, the destination bytes are
unchanged, and that Project's intent entry is gone; it then writes a
structured record with an unknown `contract` value and asserts acquisition
still fails closed. The pre-existing ten publication fault points, the
malformed publication intent case, and the legacy-project case are unchanged
and passing.

## Physical acceptance rows

| Platform | Browser | Input / journey | Status |
| --- | --- | --- | --- |
| macOS | Safari | Pointer | `deferred / unverified` |
| macOS | Chrome | Pointer | `deferred / unverified` |
| macOS | Chrome | Physical MIDI | `deferred / unverified` |
| iPadOS | Safari | Touch | `deferred / unverified` |
| iPadOS | Safari | Lifecycle | `deferred / unverified` |

## External state

| State transition | Status |
| --- | --- |
| Push | performed; `fix/opfs-publication-recovery` at `1d0fad3` on `origin` |
| Pull Request | #127 open as draft at the evidence point; being marked ready together with this record |
| Pull Request CI | no green PR-event result exists at `1d0fad3`; the four self-hosted Linux lanes are environment-blocked as recorded above |
| Merge | not performed |
| Product tag or GitHub Release | not created |
| Deployment or publication | not performed |
| Channel promotion | not performed |

This is a point-in-time evidence record. The candidate remains a CI-proven
canary candidate until the required PR checks are green at the evidence
revision, the separately authorized merge completes, and merged `main`
re-runs the required Proof. The five physical rows remain accurately deferred
and continue to block physical-pass, `beta`, and `stable`.
