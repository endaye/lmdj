# P1 default admission and inventory fixture composition

## Task and declared files

Compose the independently verified correction Tasks with actual parents
`671cc369a55ca9df3e7824a76368ac80ef461a2a` (default request admission) and
`da1401378bc4cd06a9bb53b1d57d1cf6ad295ee3` (HTTP inventory fixture ordering).
Work on `fix/p1-default-admission-compose`; retain both parents, rather than
recreating their changes from a patch.

Declared files relative to the admission parent:

- `apps/creator-web/test/deploy_command_test.py`
- `apps/web-runtime-host/test/deploy_command_test.py`
- `docs/plans/2026-10-03-p1-netlify-inventory-fixture.md`
- `docs/plans/2026-10-03-p1-default-admission-composition.md`

The three incoming fixture/plan blobs must equal the inventory parent exactly.
All other existing files must equal the admission parent, including the seven
R20 correction files, current lifecycle barriers, Native quota/replay receipts,
default Catalog, asset observer and manifests. No merge conflict is expected.

## Verification

Run both unchanged inventory-refusal cases under the original controlled HTTP
ordering driver on the composed tree; each must refuse at the inventory
boundary before draft creation. Run all Creator unit tests serially with
unchanged test budgets, TypeScript/Vite, Platform tests, staged path ownership
and whitespace checks. Verify parentage, exact incoming blobs and preservation
of every existing file outside the declared scope before and after commit.

The parent Tasks retain their actual full lower checks, original strict REDs,
all GREEN results and full portal verification. This composition's lower
checks do not replace complete committed-head lanes. Recompute the canonical
lane plan: the inventory fixture changes Creator, Runtime and Deploy input
keys; admission additionally changes Creator. Execute complete proofs for
the new inputs without caching. Reuse older lane results only with their real
producer head, unchanged required inputs and retained raw proof. Original
Creator failures and the independent R20 Changes Requested report remain
preserved until current complete proof and independent review satisfy them.

## Version Management

Version impact: none. This correction composition allocates no Product Build
and changes no version identity; P1 coordinated identity settlement remains
required in its integration Task.

Documentation impact: none. Relative to the admission parent this Task only
composes HTTP fixtures and plans. Its current Host page and actual documented
product behavior are preserved exactly from the independently tested parent.
No portal page, diagram, identity projection or Assembly changes here.

## Acceptance boundary

Current-head independent review, real conversation/conflict protection and
complete selected lane evidence remain required for shipping. Source and
automated proof do not accept physical Safari/iPad, MIDI, microphone or audible
output. This composition initiates no release, deployment, promotion, Issue
closeout or cleanup.
