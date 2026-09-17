# Release workflow dispatch correlation producer

Status: delivery integration of original `2d311fff` onto actual body-binding
squash `1d8465064e644d2997c487a3f82adc3ad3a3c236`. Historical original-stack
evidence below is not current delivery verification; retain current base's
repaired test registrations.

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

## Historical original-stack results and limitations

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

## Delivery integration and verification

Preserve the current base's Task verifier and all subsequent test registrations;
the historical patch's CMake insertion conflict is resolved by adding only the
receipt contract with its original 30-second limit. No current test is removed.

Actual delivery tests passed: receipt producer 12/12 (0.239 seconds), publication
workflow 7/7 (0.002 seconds), Runtime workflow 16/16 (0.030 seconds), Creator
workflow 16/16 (0.031 seconds), all exit 0. Independent complete eleven-file
review found no actionable issue and independently reran all four populations.
Staged ownership/admission passed 74/74 in 7.055 seconds.

Current CMake configuration succeeds and registered receipt CTest passes 1/1
in 0.36 seconds under Python 3.14.7. The old Cardputer duplicate-registration
failure above remains historical evidence, not a current delivery failure or
permission to omit CTest. Both Host step budgets total 19 minutes under their
unchanged 20-minute preflight job caps; permissions, Environments, concurrency
and publication/deployment verification remain unchanged.

After a locked Node 22.22.2 install, the installed `js-yaml` parser loaded all
three workflows with its duplicate-key rejection and confirmed the optional
input and two correlation steps. `actionlint` is still unavailable; no
actionlint pass is claimed. Full Portal passed 144/144 tests, 47-page metadata,
10 diagrams/20 outputs, snapshot consistency, typecheck, production build and
47 routes/internal links; exit 0. No live dispatch, artifact upload, signer,
release or deployment was exercised; actual retained-artifact authentication,
durable unknown-POST recovery and full release acceptance remain subsequent work.

Post-merge integration onto `1d846506` preserves concurrent main Task `169b1ba8`
and introduces no conflict. All ten behavior/workflow/registration/Portal/test
files are byte-identical to independently reviewed delivery `cebb489c`;
independent post-rebase review confirms the complete eleven-file Task range.
Fresh tests pass producer 12/12, publication 7/7, Runtime 16/16 and Creator
16/16; ownership/admission 74/74 (7.005 seconds); configuration and registered
receipt CTest 1/1 (0.40 seconds), all exit 0. Because concurrent main changed
other Portal pages, repeat the full Portal check on this integrated tree:
144/144 tests, all metadata/diagram/snapshot/type checks, production build and
47 routes/internal links pass, exit 0. The final amendment only records these
verified integration facts in this plan.
