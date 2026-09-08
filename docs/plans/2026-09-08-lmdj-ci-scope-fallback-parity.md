# Separate unavailable review advice from incomplete Git scope

## Declared files

- `scripts/ci/batch_controller.py`
- `scripts/ci/review_merge_map_reader.py`
- `tests/build/ci_batch_controller_test.py`
- `tests/build/ci_review_merge_map_reader_test.py`
- `.agents/pitfalls/fake-tool-stub-strictness.md`
- `scripts/ci/batch_runtime.py` (diagnostic wording only, after the concurrent
  explicit-resume Task has shipped; do not overwrite that Task).
- This plan.

## Design parity

The accepted incremental spec sections 3.2 and 3.3 distinguish missing review
records from missing actual-main changes or policy. Missing review records use
actual-file rules as fallback; incomplete Git history, unknown classification
or unavailable historical policy cannot justify a smaller selection.

The temporary GitInputs wiring incorrectly passed advisory completeness as the
path inventory completeness flag. As a result, even a fully authenticated pure
explanatory-doc interval selected all suites when AI review or its mapping was
unavailable. The mapping reader is now implemented; this placeholder must not
become the final scheduling policy or an O1-only exception.

Keep complete first-parent collection independent. Every required historical
policy is still loaded or explicitly missing. Select their deterministic union
plus every valid partial AI suggestion, regardless of whether all PR mappings
were available. Unknown paths/dependencies, missing policies and valid full
advice still require full; missing Git history still blocks. Malformed advisory
ports are errors, not empty advice. Record the review gap and remedy in the
frozen selection reasons, without claiming review success. All-backend failure
Issue reporting remains a separate required path.

No record authentication is relaxed, mutable labels are not read, and existing
request/target/claim/failed observations or debt are not rewritten. This applies
to future admission only. It does not cancel or shrink the running full O1
bootstrap. Missing optional API advice cannot be mistaken for no main changes:
main and its complete interval are independently obtained and verified.

Independent review identified a prerequisite defect hidden by unconditional
full fallback: the reader expected `commit.paths`, but actual collect_interval
produces `commit.changes[*].paths`. Synthetic fixtures had invented the former
shape and mocked collection, losing real valid AI advice under an exception.
Derive each commit's complete path union from actual changes, including rename
ends and deletion. A real temporary Git interval now goes through the actual
reader and GitInputs selection, retaining an authenticated fixture's creator
advice on an otherwise explanatory document. Real Git is exercised; the HTTP
producer receipts remain fixtures and are not remote O1 evidence.

## Verification

Observe red/green real-Git cases for missing advice on explanatory docs and
incomplete advice on a Host plus valid extra consumer advice. Preserve full
on Contract/unknown paths, missing historical policy and valid full advice.
Run controller, mapping reader, actual runtime and complete CI contracts; stage
new plan before ownership check. Local tests do not certify remote O1 none or
focused execution. Existing known broken historical batches remain red.

## Documentation Impact

Documentation impact: none

Reason: restore internal pre-cutover behavior to the accepted spec; no current
Portal pages or automatic triggers change. T5 still owns their synchronized
cutover after actual O1.

## Version Management

Version impact: none

Reason: no product version/identity, tag, Release, publication or deployment.

Pitfall impact: recurrence fake-tool-stub-strictness — the internal Git return
shape was replaced by an incompatible synthetic shape. Record the actual
independent review finding and real-Git regression; broader escalation #726
remains open and no remote lost-advice incident is invented.
