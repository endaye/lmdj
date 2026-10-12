# Active-tree Web command alternatives

## Outcome and authority

Restore the existing active-tree check's recognition of required Web Runtime
Host subcommands when Bash combines literal alternatives in one case arm.
This is a separate repair within the authorized Creator followup Goal.

## Premise disposition

Fresh main and this isolated Task base are
`a5bc444be23edf4d4d14378e3ff60c3c8bf037fc`. Its active-tree check searches for
`proof)` while `scripts/web-runtime-host.sh` declares `proof|quick)`.
The original check was run on this exact base and returned 1 with
`stable Web Runtime Host command is missing: proof`, after its four
no-bare-fork checks passed. The required command is present; the matcher is
wrong. The same early failure prevents the existing proof-failure-artifact
test from reaching its deliberately failing CMake executable and exit 99.

The ongoing P1 Linux verification reports these failures on its frozen input.
Its original results remain independent evidence; this repair does not rewrite
them or authorize a retry of that unchanged input.

## Task and declared files

- `tests/build/test_active_tree.sh`: match complete literal case alternatives,
  retaining all six required commands and every other active-tree check. A
  genuinely missing command must still fail with its name and remedy.
- This plan: record the scope and actual verification disposition.

No Web entry point, product implementation, registration, test selection,
budget, timeout, coverage floor or assertion is changed.

## Verification

Run the original active-tree check and proof-failure-artifact test. In the
owned worktree, temporarily test the existing Web case arm with the required
command first and last, and with spaces around alternatives. Remove each of
the six required command alternatives in turn; each original active-tree
invocation must fail for that specific missing command. Restore the exact
original Web script with a fresh mtime and verify the repaired tree again.
These checks execute the current shell artifact directly and do not build or
run a native product artifact.

Before commit, stage only the two declared files and run the staged new-file
ownership suite. Classify the committed head using the canonical selector;
complete every selected batch-only lane before merge. The current path rules
select Core Ubuntu, ASan, coverage, macOS and Package; their results are pending.
Existing runtime, D04, keyboard and manual acceptance remains separate.

### Actual Task verification

At this unchanged base, the original gate returned 1 before the fix. After
the fix, Bash syntax, the original active-tree check and
`python3 tests/build/proof_failure_artifacts_test.py` returned 0; the last test
again reached its intentionally failing CMake command and verified its
preserved failure artifact.

The 11 direct original-gate invocations returned their expected results:
required command first, last and with spaces, plus exact restoration, all
returned 0. Removing configure, build, test, proof, serve and clean separately
returned 1 for that named command. Replacing proof with proofish also returned
1 for proof. All seven negative results retained both why and remedy. The
Web script was restored byte-for-byte with a fresh mtime; only the two
declared files remain changed. No native artifact was built or run.

Before commit, a fresh main fetch again resolved to
`a5bc444be23edf4d4d14378e3ff60c3c8bf037fc`; no successor delivered this fix.
The exact command receipts and raw streams are retained under the external
`2026-10-12-active-tree-case-arm-investigation` evidence directory. Core
Ubuntu, ASan, coverage, macOS and Package remain pending; these direct checks
do not establish those complete results or clear the P1 frozen-head failures.

## Version Management

Version impact: none — only an existing source-tree assertion is corrected;
no product, module, contract or active manifest changes.

## Documentation Impact

Documentation impact: none — required public commands and Portal source facts
are unchanged; this plan records the verification repair.

## Pitfall Impact

Pitfall impact: none — the lexical mismatch is directly visible in the check
and its owning entry point. Apply the existing gate failure readability rule.
