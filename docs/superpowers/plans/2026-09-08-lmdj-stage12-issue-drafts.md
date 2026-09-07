# Stage 12 local Issue drafts — 2026-09-08

Status: **local drafts, no remote mutations authorized or performed**.
K/B IDs are local labels, not GitHub numbers. Copy one section per Issue only
after explicit remote authorization; re-audit existing Issues to avoid duplicates.
Do not publish unapproved Contract choices as approved decisions.

Authority and full file/verification boundaries:
[Capability plan](2026-09-08-lmdj-stage12-capability-implementation.md),
[benchmark plan](2026-09-08-lmdj-stage12-benchmark-tools.md),
[readiness audit](../../quality/2026-09-08-stage12-readiness-audit.md).

## K1 draft

Title: `Stage 12: formalize sample.slice input/output Contracts and conformance`

Labels: `type:task`, `area:provider`, `area:contracts`, `priority:p2`.
Relates to #467 and #472.

Outcome: capability instance plus WAV profile and slice-points Schema validated
with shape and contextual conformance. Work starts only after C-Q1/C-Q2/C-Q3
confirmation and exact input profile filename/version allocation. Scope is K1's
file list; existing smoke WAV/manifest remain unchanged.

Acceptance:

- Every v2 mandatory field is populated with approved identity/policy values;
  no extra platforms field is added to the JSON contract.
- Closed Schema and contextual validator tests cover all K1 negative vectors,
  source hash/rate/frame_count, integer/onset rules and canonical bytes.
- Registered tests actually run; K1 commands and portal check pass.
- Current Contract pages record implemented availability accurately.

Dependencies: C-Q1/C-Q2/C-Q3; no Stage 10/11 feature dependency.
Version impact: required for the future Task, proposed output and capability
initial 1.0.0; exact WAV profile identity awaits approval; capability.v2 unchanged.
Documentation impact: required, `/contracts/capability/` and the approved new
profile/output routes. Publication, product registration and adoption excluded.
Suggested branch: `feat/stage12-slice-contracts`.

## K2 draft

Title: `Stage 12: migrate Provider execution to owned ArtifactSource inputs`

Labels: `type:task`, `area:provider`, `area:core`, `area:contracts`, `priority:p2`.
Relates to #467 and #472.

Outcome: SDK v2 input custody/output validation with all existing implementations,
mocks and call sites migrated in one coherent ABI Task. K2's complete migration
inventory and refreshed exact version cascade are its declared file boundary.

Acceptance:

- Only approved bindings reach owner resolver; integrity and aggregate budget
  failures prevent run. Inputs have immutable owned bytes, no inferred paths.
- Saved callbacks fail safely after return, alias/lifetime/concurrency rules are
  tested under approved C-Q4, including callbacks whose errors Provider ignores.
- Structured outputs pass consumer validator before visible success. Domain
  errors retain approved types; malformed/partial output never becomes Candidate.
- Full fault-injected durability/restart sequence follows C-Q5; terminal history
  remains immutable. Existing proof conformance and all named mocks migrate.
- K2's build/tests/stress/version/dependency/portal commands pass; unavailable
  platform evidence is explicit. No JobRecord/CandidateIndex/adoption scope.

Dependencies: K1, C-Q3–C-Q5, fresh exact version/file allocation and Stage 11
shared-file coordination. Not an independent “SDK-only” landing.
Version impact: required; SDK MAJOR proposal 2.0.0, dependency/factory/lock cascade
per refreshed manifest audit, snapshot if Product Build allocated.
Documentation impact: required, SDK/proof/Facade pages and all actual cascade
routes plus source diagrams. Suggested branch: `feat/stage12-artifact-source`.

## K3 draft

Title: `Stage 12: add an unregistered deterministic sample-slice reference Provider`

Labels: `type:task`, `area:provider`, `area:contracts`, `priority:p2`.
Relates to #467 and #472.

Outcome: source-handle-to-onset-JSON reference Provider using the approved
algorithm/parameter set, without Product Assembly selection. Exact files are K3.

Acceptance:

- Registry/AttemptStore production execution path with approved source and sink;
  no fixture hash recognition, Host bridge or parameters carrying paths.
- New unseen algorithm fixtures plus retained smoke corpus, deterministic byte
  replay and all malformed input/output cases pass K3 commands.
- Consumer-owned validator is invoked by SDK before terminal publication.
- Source-package identity is generated; quality evidence never auto-promotes.

Dependencies: K1/K2 and C-Q2/C-Q3; B2 optional for scoring.
Version impact: required, proposed initial Provider 1.0.0; no model selected.
Documentation impact: required, `/providers/local-sample-slice/`,
`/providers/overview/`. Suggested branch: `feat/stage12-slice-reference`.

## K4 draft

Title: `Stage 12: register the reviewed slice Provider and integrate product identities`

Labels: `type:task`, `area:product`, `area:provider`, `area:docs-governance`, `priority:p2`.
Relates to #467 and #472.

Outcome: independently reviewed Product registration, lock, current Portal and
immutable Build snapshot, using actual identities allocated at implementation.
K4 is not ready now: exact file/identity inventory must be refreshed first.
At allocation, publish K4a as the mutable identity Task and a separate K4b
snapshot child with title `Stage 12: freeze the allocated slice Product Build
Portal snapshot`; K4b owns only generator outputs, depends on K4a's clean
commit, and verifies portal/snapshot provenance. Each Task gets one commit;
both belong in the same integration PR. No standalone Build-without-snapshot
PR. K4b has the same required documentation/version context, allocates no
additional Build and grants no release authority.

Acceptance: approved inclusion decision and measured evidence; all identities,
compiled registration, locks and real Runtime generation agree; version/schema/
module graph/proof/portal checks pass; selected Build has an immutable snapshot
and later authorized merge obtains provenance verification. No release or deploy.

Dependencies: K3, explicit inclusion decision, fresh allocation, coordination
with Stage 11 #673. Scope: K4 file list; Candidate adoption excluded.
Version impact: required, Product Build/Channel not yet allocated.
Documentation impact: required, `/assembly/lmdj/`, `/product/capability-map/`,
`/providers/overview/`, `/contracts/capability/`, affected modules and diagrams.
Suggested branch: `feat/stage12-slice-product-integration`.

## K5 draft

Title: `Stage 12: wire Artifact owner resolution through Facade and verify Host attempts`

Labels: `type:task`, `area:core`, `area:provider`, `priority:p2`.
Relates to #467 and #472; adoption remains #471.

Outcome: real owner resolver injection reaches SDK from existing Host/Facade
attempt execution, with no path guessing. First produce the exact-file/identity
subplan required by K5 against post-K4 main; this draft is gated, not executable.

Acceptance: every Host → Facade → owner → SDK → validated terminal → inspect →
restart → inspect leg has assertions; missing/changed/unauthorized input fails
closed and leaves Project Truth unchanged. Hash and byte length both verified.
Run all affected K5 Host/Facade/Provider/version/portal checks; explicit gaps for
unavailable platforms. No Candidate UI or new adoption commands.

Dependencies: K4, approved owner API and Stage 11 shared-file coordination.
Version impact: required, fresh post-K4 allocation.
Documentation impact: required, `/core/modules/application-facade/` plus actual
owner/Host routes declared by the subplan.
Suggested branch: `feat/stage12-owner-resolver-hosts`.

## B1 draft — independently implementable tool Task

Title: `Stage 12: validate benchmark reports with execution-zone evidence rules`

Labels: `type:task`, `area:provider`, `area:docs-governance`, `priority:p2`.
Relates to #466 and #472.

Outcome: B1's closed local report schema, strict Python validator, examples and
README. Scope is exactly the B1 file list; no SDK/Provider integration.

Acceptance:

- Required identity and measurement fields validated, unknown keys/units,
  non-finite values, missing gate data, duplicate IDs and unsafe paths rejected.
- Direct/isolated/remote distinctions enforced; self-reported observations cannot
  pass resource gates; fixture reports cannot pass require-measured.
- Every invalid CLI case fails for its stated reason with why/remedy; positive
  fixture passes; CTest discovery and ownership checks pass B1 commands.
- No actual Provider benchmark, hard-resource enforcement or promotion claimed.

Dependencies: accepted tool plan; no Stage 10/11 or #467 implementation dependency.
Version impact: none, internal tools only.
Documentation impact: none, tool README/retained format only.
Suggested branch: `feat/stage12-benchmark-report`.

## B2 draft — independently implementable tool Task

Title: `Stage 12: score slice onsets against the retained smoke corpus`

Labels: `type:task`, `area:provider`, `priority:p2`.
Relates to #466 and #472.

Outcome: deterministic CLI/library for one-to-one onset matching and exact
TP/FP/FN counts, nullable case precision/recall/F1 and micro aggregation.
Scope is B2's exact file list. Read the existing manifest/digests/tolerances;
no output Contract instance, SDK calls or smoke regeneration.

Acceptance:

- Validate closed frame prediction input, complete success-case inventory,
  actual source byte length/hash and manifest hash; failure cases unscored.
- Inclusive tolerance, maximum-cardinality matching and deterministic pairs;
  independent exhaustive small-set matching oracle agrees.
- Silence/no-prediction null handling and micro counts match plan; no averaging
  nullable ratios, no fabricated provider/model identity or quality threshold.
- CLI/error/repeat-byte tests, unchanged 15-test corpus, CTest discovery and
  staged ownership verification pass B2 commands.

Dependencies: accepted tool plan. B1 optional for full report wrapping; no
Stage 10/11 or Provider v2 dependency. Coordinate README/CMake ownership.
Version impact: none. Documentation impact: none, internal scoring tooling only.
Suggested branch: `feat/stage12-slice-score`.

## Draft remote corrections (not executed)

For #466, proposed comment/status correction:

> Relates to #466. A fresh 2026-09-08 audit found the approved benchmark design
> and #586 smoke corpus delivered, while report tooling, production execution
> harness, resource/timeout/output-failure conformance, broader evaluation
> corpora and blind-review packages remain outstanding. Recommend reopening
> this retained parent and allocating B1/B2 separately; keep the delivered
> fixture child complete. Current CLOSED state is not whole-acceptance evidence.

For #467, proposed body corrections:

- Replace both “provider-sdk MINOR” requirements with “provider-sdk MAJOR for
  the proposed replacement execution ABI; proposed 2.0.0 subject to fresh
  allocation and complete dependent-version review.”
- Link the revised design, implementation plan and C-Q1–C-Q5 decision gates.
- Replace blanket Stage 10 wait text with completed prerequisites and current
  Stage 11 shared-file/version integration coordination.
- Set documentation impact for the retained review to `none` with concrete
  reason (no current Portal change); future implementation declares required
  routes. Keep portal verification acceptance.
- Keep approved-design and implementation-Issue acceptance pending: local
  drafts are not published Issues and this review has not approved itself.

For #472, proposed execution-map correction:

- Record #586 as the delivered smoke slice, not completion of all #466 work.
- Use SDK MAJOR migration language and actual shared Facade/identity boundaries.
- Link K1–K5/B1–B2 only after their remote allocation is authorized; do not invent
  Issue numbers. Mark design status truthfully.

## Version Management

Version impact: none for these drafts. Future Task declarations above are
conditional allocations, not active manifest edits. No tags, Product Builds,
Channels, release/deploy/promotion or remote mutations are authorized.

## Documentation Impact

Documentation impact: none. Reason: local Issue bodies and correction proposals
change no current Architecture Portal source facts. Future implementation
impacts appear explicitly in each Task body.
