# Native Sample preparation read failure after a saved mutation

Parent: #2112 / #2229.
Integration base: `fcc30c5400bb34d47d47249acc838707eb7579ca`.

## Premise audit

- Delivered: #2490 preserves the known saved outcome for an IO_ERROR snapshot
  receipt and records its diagnostic. Its page fixture replaces a genuine
  successful publication receipt; it is explicitly consumer evidence.
- Delivered: current Project I/O validates every Asset before authoring. A
  capture-only ordinary Chromium experiment really changes one other Asset's
  bytes without changing its length, then requests a Sample mutation. Native
  refuses it with MISSING_ASSET, and the Project remains at revision 47 after
  the exact bytes are restored. This is the correct precommit boundary, not a
  saved-publication failure or a product RED. Preserve that evidence.
- Outstanding: a Native producer receipt obtained from an actual filesystem
  read failure after a known durable commit, with full saved Truth, explicit
  preparation-only recovery and persisted reopen. Existing timeout/quota Host
  cases are positive controls for committed-failure receipts; they do not
  exercise this real file-read boundary.
- The current `sample_mutation_result` inspects the saved Sample before
  `prepare_and_publish` loads it again. Use the existing native storage
  decorator's read observation, keeping its real delegated result. No new
  production hook, manufactured error, SDK receipt replacement or timing race.

## Task and declared files

One test-only Task, one Conventional Commit:

1. `packages/web-runtime-platform/test/control_runtime_test.cpp`
2. This plan.

Keep every existing Host case and its registration/budget. Add one complete
journey to the original default executable. At the second manifest storage access that
observes the new durable revision, preserve the entire committed file map and
atomically move that actual manifest aside. The original native filesystem
reader must encounter its missing path. Restore those exact committed bytes
after the original response; do not invent the error or roll back the commit.

## Acceptance journey

1. Create a real Project, import and assign real WAV bytes, retaining the
   complete revision-2 Truth and Sample playback.
2. Request one real mute mutation. Prove the selected manifest already names
   revision 3 before the move, the actual read path is absent, and the original
   response retains committed_revision=3 with an unpublished runtime and the
   real INVALID_PROJECT snapshot diagnostic. It must not report mutation rejection.
3. Restore the exact revision-3 manifest. Check whole Truth against an
   independent revision-only Project delta, and separately assert the saved
   Sample mute at revision 3 (Project inspection omits playback).
4. Explicitly call the existing Native snapshot.retry operation. Require actual
   publication at revision 3, no second mutation, identical complete Project
   files and unchanged Asset bytes. This proves the existing Native operation;
   it does not choose Creator's non-COOK_FAILED retry eligibility.
5. Destroy the original Runtime, create a fresh owner, open the saved Project,
   and require the same whole Truth, saved Sample playback and complete files.

This is Native Host producer evidence with a real temporary filesystem fault.
It is not a physical disk failure, a Wasm/OPFS after-commit fault, a complete
candidate, or permission to change recovery strategy. Those gaps stay explicit.
The existing IO_ERROR page fixture remains consumer-only evidence; this test
does not change its classification or claim that a missing manifest emits IO_ERROR.

## Initial execution observation

The first new Native run reached the actual moved, committed manifest and
failed at the test's assumed IO_ERROR code. The real original producer returns
INVALID_PROJECT: Project I/O's existing layout validation explicitly maps an
unreadable manifest length to "project manifest is missing or invalid". Bind
the exact expected code to that source contract, preserving the nonzero result;
this is a corrected test premise, not a product bug or an assertion tolerance.
The whole saved Truth, playback, file identity, retry and fresh-owner legs are
still required. The clean baseline full Host run passed in 87.70 seconds.

## Verification

- Clean current-base configure/build and original complete
  `ctest --test-dir build/core/dev --output-on-failure -R '^host.web_control_runtime$'`.
- Rebuild the changed original target and repeat that complete Host selection;
  inspect its original default main registration and the new far-side checks.
- Preserve the capture-only ordinary browser experiment independently. No
  browser product change is declared and it is not a producer failure PASS.
- Staged/committed new-path ownership, diff inspection, exact PR-body checks,
  current-head independent review, all findings/conversations and live
  protection/freeze checks before guarded squash and actual merge readback.

### Recorded results

The corrected rebuilt original Host executable passes in full: 90.02 seconds
CTest / 90.11 seconds wrapper, within its unchanged 120-second budget. Its new
journey returns the original Native receipt with committed_revision=3,
runtime_revision=2, runtime_published=false and snapshot_error INVALID_PROJECT.
The explicit Native snapshot.retry then publishes generation 2 at revision 3,
with no snapshot error. A fresh Runtime reopens identical whole Truth and Sample
playback; all nine committed files compare byte-for-byte before/after retry and
reopen, and the WAV compares with its independent original input bytes.

The initial code-expectation failure is retained separately. It proves the
fault ran and contradicts the assumed IO_ERROR; it is not a product regression.
The unchanged ordinary Chromium counter-experiment also retains complete
restored revision-47 Truth and its real MISSING_ASSET precommit refusal. Its
capture-only PASS must not be presented as an after-commit producer failure.

Advisory classification selects full13 through the three expensive-family
closure. This Task executes the owning complete Native Host suite, not those
thirteen complete lanes. No full Creator, candidate, sanitizer, Portal or
physical OPFS/device result is claimed.

## Version Management

Version impact: none — tests and plan only; existing #2237 product/API/ABI debts
and candidate identity allocation remain open.

## Documentation Impact

Documentation impact: none — no Portal fact, diagram or product behavior change.
The plan records the verified boundary and the unverified platforms.

## Pitfall disposition

Apply fresh-premise, genuine-side-effect, full-journey and complete-identity
procedures. No new qualifying process defect or gate is introduced.
