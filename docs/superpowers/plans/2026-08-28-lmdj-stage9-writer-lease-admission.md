# Stage 9 Writer-Lease Admission Remediation Plan

Date: 2026-08-28

Status: implementation

Issue: [#378](https://github.com/endaye/lmdj/issues/378)

## Goal

Close H1 from the Stage 9 Sequence Recording review. A non-whitelisted
authoring command must not pass a process-local Sequence check and then commit
after a Sequence session begins. An orphan active journal must be reconciled
before authoring continues, and Project I/O must repeat the authoritative
journal admission while holding the Project writer lease.

## Locked Behavior

- Application Facade owns one Project-scoped local admission critical section:
  check the in-memory session, reconcile orphan journal authority, then enter
  Project I/O without releasing the local Sequence mutex.
- Project I/O re-reads `recovery/active/sequence.jsonl` only after acquiring the
  writer lease and before `commit_loaded` can publish a revision.
- Non-whitelisted commands fail closed with `reason=sequence_session_active`,
  the active `session_id`, and a concrete stop-or-reconcile remedy.
- `UpdateSequenceSettings` remains the only existing selective-rebase
  whitelist entry. Project I/O rebases the active journal after a successful
  settings commit; the Facade does not perform a second rebase.
- A missing active journal admits normal authoring. A malformed journal fails
  closed. An orphan valid journal is sealed as `owner_lost` by the Facade
  before the command reaches the Store.
- No retired `lmdj.patch.v1` or `lmdj.materials.v1` surface is restored.

## Task

One reviewable implementation Task and one Conventional Commit:

1. Change `packages/application-facade/src/application.cpp` and its private
   testing hooks so the local admission lock spans orphan reconciliation and
   the Store mutation.
2. Change `packages/project-io/src/project_store.cpp` so generic commands,
   playback updates, and every artifact-import mutation read active Sequence
   authority inside the writer lease. Keep settings as the sole whitelist and
   perform its journal rebase in the Store.
3. Extend `tests/core/facade/sequence_surface_test.cpp` with a deterministic
   begin-versus-authoring gate and an orphan-journal authoring journey.
4. Extend `tests/core/project_io/project_store_test.cpp` with direct Store
   rejection and settings-rebase coverage.
5. Update the Stage 9 review disposition and current Architecture Portal pages
   for Project I/O, Application Facade, storage, and automated proof.
6. Record any qualifying Pitfall Ledger recurrence found while shipping this
   Task under the repository governance contract.

## Verification

- Build and run `project_io.project_store` and `facade.sequence_surface`.
- Run `scripts/core.sh test dev fast`.
- Run `scripts/core.sh test dev stress` because the fix changes concurrency
  admission, even though the new deterministic gate is a component test.
- Run `scripts/architecture-portal.sh check`.
- Run version, dependency, and active-tree verification required by the root
  workflow.

## Version Management

Version impact: deferred to [#379](https://github.com/endaye/lmdj/issues/379).

This Task changes behavior in the `project-io` and `application-facade` patch
domains but does not change either public header, Contract, Host protocol,
Provider, active manifest, Assembly lock, or Product Build. The six remediation
children merge as functional Tasks; #379 performs one fresh identity audit,
applies the accumulated SemVer/Assembly changes, and allocates the next verified
unused Product Build. [#380](https://github.com/endaye/lmdj/issues/380) owns the
separate clean-commit immutable snapshot boundary. Product Build `1.0.37.0` is
not rewritten or reclassified by this Task.

## Documentation Impact

Documentation impact: required.

Affected current Portal routes:

- `/core/modules/project-io/`
- `/core/modules/application-facade/`
- `/platform/storage/`
- `/operations/testing-and-proof/`

The Task also updates
`docs/quality/2026-08-27-stage9-sequence-recording-review.md` with a truthful H1
disposition. No immutable snapshot is created here; #379 and #380 own final
identity integration and immutable evidence.

## External Boundaries

This Task authorizes no Product tag, Release, deployment, publication, or
Channel promotion. Physical/manual acceptance remains deferred under #360
until all six #371 findings are closed and the corrected Product Build is
snapshotted.
