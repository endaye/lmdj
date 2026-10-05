# P1 Provider permission updates across retained surfaces

Task: repair the Creator settings mutations on the reviewed System integration
candidate `0f5170332edb450f2dba053fc5520c46ba600051`. The two actual Creator
mutators must preserve an unrelated grant when grant/revoke requests overlap;
a successful System revoke must also update the still-mounted Slice controls.

Declared files:

- `apps/creator-web/src/state/provider_permissions.ts`
- `apps/creator-web/src/components/system_surface.tsx`
- `apps/creator-web/src/components/candidate_surface.tsx`
- `apps/creator-web/test/system_surface.test.tsx`
- `docs/plans/2026-10-05-p1-provider-settings-ordering.md`

One session-keyed Host helper orders each Creator read/change/write and sends
the fresh provider listing plus the authoritative successful permission receipt
to mounted consumers. Initial reads cannot overwrite a later successful update.
The existing Runtime full-set configure operation and Facade policy remain the
same; no new operation or cross-session permission authority is introduced.

Lowest-tier tests exercise both actual surfaces sharing one session. A delayed
FIFO configure response reproduces the real control lane's in-flight boundary
and checks that overlapping grant/revoke leaves the unrelated granted permission
intact. A revoke in System must enable regrant in the retained Slice controls,
and that regrant must restore the far-side session permission. Fresh provider
identity readback and refusal/queue recovery get independent assertions.

Verification: original failing component regressions, then complete System and
Candidate component suites, TypeScript/Vite, declared new-file ownership and
whitespace. The owning PR additionally reruns the complete selected committed-
head Creator proof. Preserve the original reviewed-head whole outcomes and
review findings; they do not establish the repaired candidate's whole proof.

## Version Management

Version impact: none. This repairs existing Host settings behavior without
changing an active manifest, Contract, runtime operation or Product identity.
The coordinated P1 version settlement remains a separate Task.

Documentation impact: none. Existing portal permission/navigation facts remain
applicable; the implementation now preserves those facts across overlapping
settings gestures and the already-documented retained creative surface.

## Actual Task verification

The original production code failed all three new regressions: fresh Provider
readback, the FIFO overlapping grant/revoke, and retained Slice regrant. After
the repair, all 23 System/Candidate component tests and the TypeScript/Vite
build pass. Original failing logs remain in the task evidence directory.
The additional delayed-initialization and refusal/retry cases pass as well.
No test budget, assertion, selected lane or journey transition was weakened.
