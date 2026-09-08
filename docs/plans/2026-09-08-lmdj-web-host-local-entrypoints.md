# Host-local build and verification entrypoints

## Task and declared files

Add `apps/creator-web/README.md`, `apps/web-runtime-host/README.md`, and this
plan only. Neither Host currently has an adjacent local-development README.
The root README describes proof; the Portal gives broader architecture and
testing context. These short local guides make the stable entrypoints and
their differing build/package/test prerequisites discoverable at the source.

Do not edit Host code, scripts, scope policy, workflow, test selection or
versions. Do not claim this documentation makes automatic CI cutover complete.
Keep authoritative policy links instead of copying mutable version identities.

## Source facts and verification

Check the actual shell dispatch and functions: Creator build does not call
package; package requires build outputs and a clean source tree; serve requires
dist; test runs nonbrowser suites; proof adds fixture/reproducibility/browser
journeys. Runtime Host build packages; test requires dist and runs browser
gates; there is no public package or run_nonbrowser_tests subcommand. Each clean
function validates its own fixed build root. Verify all relative Markdown link
targets and document command verbs against those actual script dispatches.

Run staged `python3 tests/build/ci_change_scope_test.py`, cached whitespace
checks, `scripts/local-ci.sh --lanes docs_static` on the final committed range,
and `scripts/architecture-portal.sh check` before commit. Missing local Portal
dependencies must be reported, not bypassed or treated as a build pass. Product
Host proofs are not run solely to verify prose; no product acceptance is claimed.
No new gate or reduced coverage threshold is introduced.

Local results: all relative README links resolve, every documented command verb
exists in the actual stable script dispatch, and source functions were inspected
for the distinctions above. Staged ownership: 66 passed. Actual classifier
assertion: focused with the exact five-suite union below. Portal check reached
57 tests: 54 passed, three failed for missing installed Portal dependencies in
this isolated worktree; downstream Portal validation/build did not run. Final
committed-range docs-static is checked separately after the local commit.

## Actual test scope and O1 limitation

Evaluate the real `test_scope.select` on the declared paths. Creator README
selects `creator`, `docs_static`, `portal`. Runtime Host README selects those
plus `web_runtime_host` and its consumer `web_runtime_lab`. The complete Task
union is focused with exactly these five suites, not none and not full.
The explanatory plan contributes no additional product suite. No labels are
fabricated to produce this result.

The Runtime Host dependency closure already includes Creator, so these two
README changes are not proof of nonredundant lane accumulation. Their useful
role in a later O1 journey is a real focused changed interval with correct
consumer coverage. This local commit is held without push or merge until the
current none journey is completed and the root explicitly authorizes shipping.

## Documentation Impact

Documentation impact: none — adjacent contributor guides clarify unchanged
script behavior and link existing Portal guidance; no Portal page, diagram,
projected identity or product behavior changes.

## Version Management

Version impact: none — contributor documentation only, no Product Build,
Module, Provider or Contract identity allocation.

Pitfall impact: none — command distinctions are derivable from existing code;
no new platform incident or process invariant is introduced.
