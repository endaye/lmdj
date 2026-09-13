# Reuse the original unfinished release request

Delivery base: `b76c6c6a2da6e839aa54c610bb946b656835ebfd`.
Reapply bounded Task `240a13904c224f6353ba8248766dfd9b0b8ce758`, preserving
the newer journal size bound and before-write parent guards. A duplicate natural-language request can receive a new transport
ID and observe a newer main baseline; it must not allocate another version.
Resolve the original unfinished request under the existing journal writer lock,
authenticate both incoming and original authority, and advance only the original
state. Never rewrite its ID, authorization reference, baseline or operation IDs.

Declared files:

- tools/release/orchestration.py
- tools/release/orchestration_driver.py
- tests/build/release_orchestration_driver_test.py
- apps/docs-site/docs/operations/version-and-release.mdx
- docs/plans/2026-09-13-release-active-request-reuse.md

Same-scope matching requires repository, actor, pinned policy and control
revision, mode and exact requested tag. A changed authorization reference or
observed main baseline does not overwrite the original request. A same-ID
request still requires full exact equality. Different scope or ambiguous active
inventory refuses; completed history does not suppress a new release.
This uses the existing per-repository journal exclusion, not a cross-directory
or distributed Site lock. Production authenticated intake/service composition
and original-scope adapter construction remain outstanding.
This Task does not yet retain a new transport ID as an alias: after the original
completes, replaying that previously coalesced ID still needs durable alias
binding to prevent it becoming a new release. That immediate follow-up is
required before production admission can be considered idempotent.

## Verification

Use the actual ReleaseDriver and private RequestJournal with far-side filesystem
fixtures: duplicate ID/main/authority observations resume the old request; old
authority revocation blocks; different actor/policy/control/mode/tag refuses;
same-ID rebinding refuses; complete history permits a new authenticated request;
ambiguous and malformed journal entries fail closed; interrupted effects do not
repeat. Run journal/driver and concrete managed adapters, ownership, Portal and
independent review. Fixtures do not prove a real release or service cold start.

## Version Management

Version impact: none

Reason: internal release request admission; no Product/Assembly version change.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

## Evidence

The unchanged actual driver/journal first rejected a duplicate same-scope
request as another unfinished request: 1 error in 0.076 seconds, exit 1;
`/tmp/lmdj-request-reuse-delivery-red-v1.log`. Original-stack logs remain
historical, not current delivery evidence.

Current direct tests passed: driver 24/24 in 0.368 seconds and journal 21/21 in
0.153 seconds, each exit 0 (`/tmp/lmdj-request-reuse-delivery-driver-v1.log`,
`/tmp/lmdj-request-reuse-delivery-journal-v1.log`). Registered CTest passed
4/4, exit 0, total 13.63 seconds: journal 21/21 (0.27s), driver 24/24 (0.49s),
managed dispatch 20/20 (12.23s), managed PR transition 26/26 (0.64s).
No failed/skipped population; existing budgets unchanged. Logs:
`/tmp/lmdj-request-reuse-delivery-ctest-v1.log` and
`build/core/dev/Testing/Temporary/LastTest.log`. Newer bounded journal write
and parent guards remain present and tested, not replaced by the old stack.

Staged ownership/admission passed 74/74, 6.069 seconds, exit 0
(`/tmp/lmdj-request-reuse-delivery-scope-v1.log`). Final Portal and independent
review also passed: locked npm ci and Portal under Node 22.22.2, 144/144 tests
plus 47 routes/internal links, exit 0 (`/tmp/lmdj-request-reuse-delivery-deps-v1.log`,
`/tmp/lmdj-request-reuse-delivery-docs-v1.log`). Independent complete five-file
review found no new in-scope finding and independently ran driver 24/24 in
0.376 seconds and journal 21/21 in 0.161 seconds, both exit 0. It explicitly
confirmed the outstanding post-completion alias gap above.

Pitfall disposition: direct admission regressions express this invariant; no
new process-only ledger entry. Production intake, original-scope adapter
factory, service and global Site exclusion remain incomplete.
