# Batch lane input closure (#1811)

## Task

One control-plane Task closes local cache and batch-evidence keys over executed
commands, without changing lane selection, evidence syntax, test tiers or gates.
Declared files:

- `scripts/ci/local_preflight.py`
- `tests/build/ci_local_preflight_test.py`
- `docs/plans/2026-10-04-batch-lane-input-closure.md`
- `.agents/pitfalls/batch-key-omits-executed-host-test.md`

Keep the scope-policy inputs as a conservative floor. Add command read domains
independently: ownership says when to schedule, not everything execution reads.
Use whole source/fixture/support directories where a command builds or discovers
a family; additions and deletions then change the key too. Unknown lanes remain
fail-closed. Keys and PR evidence keep their existing format.

## Command audit

| Lane | Reads beyond scheduling ownership |
| --- | --- |
| docs_static | `git diff --check` checks all changed tracked source, including non-Markdown files. |
| ci_contract | Discovery, real-Git fixture copies, ownership and graph tests inspect the repository inventory and control/product source; conservatively bind the whole repository. |
| portal | Current facts hash active component source; tests, changelog/snapshot validators and source references inspect repository docs, demos, tooling and manifests. |
| core_ubuntu / core_macos | `core.sh proof` builds the complete native target graph, then runs CTest plus Host, conformance, distribution and e2e Python suites. Native ASan also compiles that graph. |
| core_asan / core_coverage | Full CTest adds Host, conformance and e2e suites; source-boundary/module-graph checks read Creator and other Hosts, and taxonomy reads its prose policy; coverage also reads its thresholds, helper scripts and quality reports. |
| package | Unqualified CMake build compiles test targets as well as libraries; fast CTest runs compiled Facade tests and Python provider evaluation. Packaging reads distribution scripts, manifests and licenses. |
| web_toolchain | CMake builds shared modules and conformance probes; Node/Python/browser proofs read platform tests, fixtures and Web tools. |
| web_runtime_host / creator | Distribution proofs build native Core fixtures and Web targets; package, browser and contract tests read shared modules, providers, Core test sources and fixture helpers. |
| deploy_contract | Release/deploy discovery imports test support and copies real product, Host, portal and release-control fixtures. |
| web_runtime_lab / chameleon_lab | Demo-local Node/Python suites and scripts; Audio Lab additionally reads the demo index and CI workflow. |

Command-level source domains are deliberately conservative, not an interpreter
for shell/Python/CMake. Keep an independent regression over literal registered
CTest/script inputs, literal rooted reads inside Python command inputs, and representative transitive reads to catch drift. Dynamic paths/imports remain covered by conservative domains and command review, not by a general static interpreter.

## Verification

Lowest tier: `python3 tests/build/ci_local_preflight_test.py`. Regression changes
each omitted test's content identity, verifies a new key, and checks additions,
deletions and unrelated content. Command audit checks actual CMake/shell inputs
against grouped paths. Failure messages name the missing input and remedy.
Run `python3 tests/build/ci_change_scope_test.py` after staging new paths.
Run all selected batch-only lanes on the committed head and retain actual output
and keys before guarded merge; unavailable or failed lanes remain outstanding.

## Version Management

Version impact: none. Only CI input binding and its tests change; no Product,
Module, Host, Provider or Contract identity changes.

## Documentation Impact

Documentation impact: none. No Architecture Portal behavior or documented
product source fact changes; the command audit and pitfall record explain CI
procedure only.
