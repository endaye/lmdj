---
id: unregistered-test-file-reads-as-coverage
area: ci-release
status: open
recurrences:
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/issues/784
    observed_by: Claude Code (Opus 5)
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/issues/900
    observed_by: claude-code/opus-5
exit: none
---

# A test file that exists but is not registered in CTest never runs, and reads to everyone as coverage

## Why

`tests/conformance/project_bundle_contract_test.py` had existed since Stage 7.
It was thorough: schema and fixture validation, pack determinism, a header and
payload round trip, path-traversal, case-fold, gap, overlap and hash negatives,
and every size limit. It was also **never registered in `CMakeLists.txt`**, so
no tier ever ran it. `scripts/core.sh test dev full` was green with the file
sitting in the conformance directory, untouched, for six Stages.

The cost was #784. `lmdj.project-bundle.v1` enumerated `project_contract` up to
`lmdj.project.v3`; #842 moved Project I/O's writer to `lmdj.project.v4`; no
Project the product created could be packed as a Bundle. The suite even
contained a case asserting that `lmdj.project.v4` must be *refused* — so the
gap was written down, in a file nobody was running.

Two properties made this invisible rather than merely unlucky:

- A directory of test files looks like coverage. `tests/conformance/` held six
  suites and four were registered; nothing in the directory, the filenames or
  the file contents distinguishes the two that were not.
- `tests/build/test_test_taxonomy.py` validates that every **registered** CTest
  entry has exactly one tier and a sane timeout. It reads the registration set,
  so a file absent from that set is outside what it can see. A check that
  enumerates only what is registered can never report what is missing.

The same shape reaches beyond CTest: `.github/workflows` lanes, coverage target
lists ([`coverage-target-list-omits-new-test`](coverage-target-list-omits-new-test.md)),
and any suite whose runner takes an explicit list.

The second occurrence, #900, is that reach made concrete, and it is worse than
the first because everything looks wired. `packages/web-runtime-platform/test/project_bundle_reader.test.mjs`
is a real suite, it runs locally, and `scripts/ci/scope_policy.json` gives it an
exact rule — `["portal", "web_toolchain", "web_runtime_host"]`. The only place
in the repository that executes it is `scripts/creator-web.sh:190`
(`node --test "$repo_root"/packages/web-runtime-platform/test/*.test.mjs`), and
that script runs in the **`creator`** lane
(`.github/actions/web-ci-proof/action.yml:200`). The `web_runtime_host` lane
globs a different directory, `apps/web-runtime-host/test/*.test.mjs`. So the
suite was routed to three lanes and executed by none of them, for every file it
covers. Two of the affected rules already carried `creator`
(`performance_master_capture`, `performance_master_tap_worklet`), so the policy
contradicted itself in the same block and nothing read it.

The repair is not uniform, which is itself the lesson: twelve of the thirteen
rules needed `creator`, and the thirteenth needed the opposite.
`packages/web-runtime-platform/test/source_boundary_test.py` is not a `.mjs`
file, so `creator-web.sh`'s glob never matched it either; its runner is CTest
(`platform.web_runtime_source_boundary`, tier `contract`, registered at
`packages/web-runtime-platform/CMakeLists.txt:479`), so it needs the core lanes.
Routing it to `creator` would have left it exactly as unrun as before while
burning the most expensive lane in the set. Read the runner before choosing the
lane; the directory a file sits in does not name it.

That is why the browser half of the Bundle enumeration could go stale in #784
and stay stale through #900: even the suite that would have noticed had no lane
to notice in. A rule that names lanes is not evidence that any of them runs the
file; the runner is a different file, and the two never reference each other.

## How to apply

- When a defect gets past a suite that should have caught it, check first
  whether that suite runs at all. Do not read the assertions until you have
  confirmed the file is invoked: `ctest --test-dir build/core/dev -N | grep
  <name>`, or grep the runner's registration list for the filename. A suite
  that never ran cannot have a bug in its assertions.
- After adding a test file, prove it runs before believing it. Registering it
  is not proof; run it and watch the count change, then break the assertion on
  purpose and watch it fail. A suite that passes in 0.01 s with no output is
  the same observation as a suite that did not run.
- When auditing a directory of suites, compare the file listing with the
  registration listing directly, rather than reading either alone. The two
  disagreeing is the finding.
- A lane assignment in `scripts/ci/scope_policy.json` is not proof of
  execution. Before trusting one, find the command that actually runs the file
  and the lane that runs that command: `grep -rn "<test dir>" scripts/ .github/`,
  then follow the script to `.github/actions/web-ci-proof/action.yml` or the
  `scripts/core.sh` invocations in `.github/workflows/ci.yml`. Where sibling
  rules in the same block disagree about a lane, the disagreement is the
  finding, not a style difference. The same holds for tier filters: `tests/e2e/`
  routes to `core_ubuntu`, and `core-ubuntu` runs `scripts/core.sh proof`, whose
  `-E` filter excludes `^e2e\.` — so editing an e2e test selects a lane that
  will not run it.
- Prefer coupling an inventory to the thing it describes over restating it.
  The repair for #784 added a conformance case binding the Bundle Contract's
  `project_contract` enum to the set of `contracts/project/lmdj.project.v*`
  schemas the repository defines, and an e2e case that packs a Project the CLI
  Host actually created rather than a synthetic checkpoint the suite wrote
  itself. A suite that authors its own input can only ever confirm its own
  assumptions. #900 repeated that repair on the browser side: the reader's
  accepted levels are now exported and bound to
  `contracts/project/lmdj.project-bundle.v1.schema.json` by
  `packages/web-runtime-platform/test/project_bundle_reader.test.mjs`, and
  `e2e.project_bundle_browser_reader` feeds the browser reader a Bundle the real
  CLI and the real packer produced.

`exit: none` at recurrence 2 because the mechanism is not this entry's to land:
[#914](https://github.com/endaye/lmdj/issues/914) owns it and names the shape —
a sibling of `test_every_document_a_test_reads_reaches_that_test_lane` in
[`tests/build/ci_change_scope_test.py`](../../tests/build/ci_change_scope_test.py)
that scans runner scripts for literal test globs, maps each script to the lanes
that run it, and asserts every tracked file it matches is routed to one of them.
#900 repaired the instance by routing twelve rules to `creator` and one to the
core lanes; it added no gate. When #914 lands, record it here as
`gate:tests/build/ci_change_scope_test.py` and set `status: absorbed`.
