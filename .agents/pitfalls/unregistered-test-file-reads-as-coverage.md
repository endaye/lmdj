---
id: unregistered-test-file-reads-as-coverage
area: ci-release
status: open
recurrences:
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/issues/784
    observed_by: Claude Code (Opus 5)
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
- Prefer coupling an inventory to the thing it describes over restating it.
  The repair for #784 added a conformance case binding the Bundle Contract's
  `project_contract` enum to the set of `contracts/project/lmdj.project.v*`
  schemas the repository defines, and an e2e case that packs a Project the CLI
  Host actually created rather than a synthetic checkpoint the suite wrote
  itself. A suite that authors its own input can only ever confirm its own
  assumptions.
