# P1 verification fixture follow-up

The coordinated seven-role identity exposed an incomplete current-identity
Creator server fixture: it copied the generated identity but omitted the actual
offline worker source before packaging. Preserve the new inventory and complete
the fixture rather than reverting the Host version or skipping server tests.

Declared files: `apps/creator-web/test/server_test.py`,
`tests/platform/web/creator/creator_web_system.spec.mjs`,
`tests/platform/web/creator/creator_web_capture.spec.mjs`,
`tests/platform/web/creator/creator_web_perform.spec.mjs` and this plan.
Lowest-tier verification: all Creator server/proxy tests; a new assertion checks
the actual packaged worker digest, isolation headers and root registration scope,
and confirms the ordinary main script receives no worker scope grant. Run the
complete Creator proof again afterwards. The System journey obtains the native
Pattern transport session from the actual request, then reads its dedicated
inspect operation and compares the wire `transport_epoch` before and after
navigation; an unrelated Host status field is not authoritative transport proof. The microphone reopen assertion uses the displayed short identifier and separately
compares the complete Project identity and Artifact. The master-tap assertion
selects its unique role rather than assuming the old six-role inventory order.
The Perform journey deletes B1 through the Sample editor, checks authoritative
empty-slot truth and unchanged saved Performances, then records the complete replay into it, asserting playing and complete
before release rather than an arbitrary delay, and reopens the complete Artifact identity. No journey leg is removed.
Historical deployment fixtures retain
their original Host identities and inventories.

## Version Management

Version impact: none — only verification fixtures and this plan change; active
Product and Host sources and the immutable P1 snapshot stay identical.

Documentation impact: none
Reason: test-fixture completeness changes no portal source fact or product behavior.
