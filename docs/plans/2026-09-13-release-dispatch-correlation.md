# Release workflow dispatch correlation producer

## Scope

R4 needs exact dispatch recovery rather than recognition by run-name or newest
successful run. The three publication/deployment workflows currently expose no
request identity in retained evidence. Add an optional operation digest input
and a bounded, read-only preflight producer/upload before the existing checks.
An omitted input preserves legacy manual operation; an orchestrated request
must supply its fixed operation digest. No input grants release authority.

Declared files:

- `.github/workflows/publish-release.yml`
- `.github/workflows/deploy-web-runtime-host.yml`
- `.github/workflows/deploy-creator-web.yml`
- `tools/release/dispatch_receipt.py`
- `tests/build/release_dispatch_receipt_test.py`
- `tests/build/release_publish_workflow_test.py`
- `tests/build/web_runtime_deploy_workflow_test.py`
- `tests/build/creator_web_deploy_workflow_test.py`
- `CMakeLists.txt`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-release-dispatch-correlation.md`

The producer validates the closed exact inputs and platform event/ref/actor/
repository/run/attempt/workflow context, retaining distinct event, workflow and
checked-out tooling revisions. It whitelists fields instead of copying the
whole event or GitHub context. The event's bare `main` and fully qualified main
representations are accepted only with platform `GITHUB_REF=refs/heads/main`.
Attempt 2, changed identities, malformed inputs and duplicate JSON fields
refuse without printing raw event/error content. Output is canonical JSON,
exclusive-create, and fsynced. Upload failure blocks preflight; a published
receipt says only that dispatch was received, not that checks/effects passed.

No permissions, Environment, signing, concurrency or job timeout is widened.
The two one-minute deployment steps fit the existing 20-minute preflight
budget including the existing one-minute cleanup margin. The existing
release/deployment artifact contracts remain separate and unchanged.

## Verification

Run the actual producer CLI using isolated temporary event files, checking
the resulting complete JSON, no-secret output, duplicate-key failure and
no-overwrite behavior. Unit cases cover all three closed input sets and
one-fact identity failures. Workflow contract suites prove producer/upload
ordering, opt-in behavior, existing permissions/pins/budgets and gates.
Register the new contract test in root CMake; existing release path rules
own it. Run staged ownership and Portal check.

Remaining R4 acceptance: authenticated API/artifact consumer and complete
pagination/source verification; durable dispatch control and unknown POST
reconciliation; actual run correlation; real far-side publication and both
Host deployment evidence. None is established by this producer-only Task.
No workflow dispatch, provider request or deployment is authorized/executed.

## Version Management

Version impact: none

Reason: internal optional correlation protocol, no product or assembly change.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: describe receipt semantics and remaining end-to-end recovery boundary.

## Local results and limitations

Producer CLI/unit suite 12/12, publication workflow 7/7, Runtime workflow
16/16, Creator workflow 16/16, staged ownership 74/74; all exit 0. Independent
read-only review inspected all 11 files and independently reran the four
behavior suites with no actionable findings. Portal check exited 0: 139/139
tests and 47 routes/internal links valid. The installed YAML parser also
parsed all three workflows with unique keys and the expected new steps.
`actionlint` is unavailable locally, so no actionlint pass is claimed.

Logs: `/tmp/lmdj-dispatch-receipt-{tests,publish,runtime,creator,scope,docs}.log`.
Additional `scripts/core.sh configure dev` failed (exit 1), preserved at
`/tmp/lmdj-dispatch-receipt-configure.log`: the existing Cardputer CMake file
registers `platform.cardputer.input.feedback_interleaving` both explicitly
and in its scenario loop. Both registrations also exist in base `cc9157b3`.
Thus direct execution is proven, but CTest configuration/discovery is not;
the duplicate needs a separate repair without removing either test journey.

Pitfall disposition: no new entry. Closed correlation schema, no-overwrite,
workflow ordering and unchanged budgets are captured by deterministic tests.
No GitHub artifact was uploaded and no live correlation, publication or
deployment has been verified in this Task.
