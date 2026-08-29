# Stage 9 Sequence Flush Idempotency Remediation Plan

**Issue:** #372

**Parent:** #371

**Finding:** M3 in the Stage 9 review

**Design authority:** SR-D21 and SR-D22

## Outcome

Make an active Sequence flush retry-safe across the interval where Project
Truth has committed but the caller has not received a receipt. Reusing the
original `command_id` must finish or replay the original durable flush identity;
events admitted after the failed attempt must remain pending for a later fresh
command instead of being rebound to the old command.

## Task 1: Lock journal command identity

**Files:**

- `packages/project-io/src/sequence_journal.cpp`
- `tests/core/project_io/sequence_journal_test.cpp`

Add a failing component test proving that an exact repeated command returns the
existing flush record without changing journal bytes, including after
completion, while a different payload with the same command is rejected before
append. Implement the command lookup while holding the journal append mutex and
writer lease.

Verification:

```bash
ctest --test-dir build/core/dev --output-on-failure -R '^project_io.sequence_journal$'
```

## Task 2: Retain the in-flight flush in the Facade

**Files:**

- `packages/application-facade/src/application.cpp`
- `tests/core/facade/sequence_surface_test.cpp`

Add a failing Facade test that injects a journal-completion failure after the
Project revision is visible, admits another event, retries the original
command, and then flushes the later event under a fresh command. Retain the
durable flush record in session runtime before execution; on retry, execute
that exact identity first and remove only the events represented by it.

Verification:

```bash
ctest --test-dir build/core/dev --output-on-failure -R '^facade.sequence_surface$'
```

## Task 3: Expand recovery evidence

**Files:**

- `tests/core/project_io/sequence_journal_test.cpp`

Run both post-commit fault points through same-bundle retry and restart
reconciliation. Assert one Project revision, one journal flush identity, receipt
replay, and no overdub.

## Task 4: Update current documentation

**Files:**

- `docs/quality/2026-08-23-stage9-sequence-recording-acceptance.md`
- `docs/quality/2026-08-27-stage9-sequence-recording-review.md`
- `apps/architecture-portal/docs/product/workflows.mdx`
- `apps/architecture-portal/docs/platform/storage.mdx`
- `apps/architecture-portal/docs/core/modules/project-io.mdx`
- `apps/architecture-portal/docs/core/modules/application-facade.mdx`
- `apps/architecture-portal/docs/operations/testing-and-proof.mdx`

Record the remediation semantics and tests without claiming the integration
Issue, Product Build refresh, remote CI, merge, release, deployment, or Channel
promotion is complete.

## Task 5: Verify and ship

Run the focused tests, Core fast/full/stress tests, dependency and active-tree
checks, version verification, and Architecture Portal check. Stage only the
declared files, inspect the staged diff, create one Conventional Commit, and
ship through the repository issue workflow.

## Version Management

Version impact: deferred to integration Issue #379. This Task affects Project
I/O and Application Facade behavior but does not allocate or reuse a Product
Build or independently change module manifests. Issue #379 performs the fresh
identity audit and one coherent Stage 9 remediation version refresh.

## Documentation Impact

Documentation impact: required. Affected current Portal routes are Product /
Workflows, Platform / Storage, Core Modules / Project I/O, Core Modules /
Application Facade, and Operations / Testing and Proof. The Stage 9 review and
acceptance ledger are updated in the same Task. No source diagram changes are
required because module ownership and dependency edges do not change.
