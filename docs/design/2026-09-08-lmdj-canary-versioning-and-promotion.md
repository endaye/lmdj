# LMDJ daily conditional canary and candidate promotion

Date: 2026-09-08

Status: implementation proposal following the user's design review; not an
activation record and not a replacement for current release governance.

Implementation plan: [phased delivery](../plans/2026-09-08-lmdj-canary-versioning-and-promotion.md).

## 1. Outcome and authority

The intended operator experience is: ordinary PRs merge with current-head review
and Task verification; a daily check prepares and deploys relevant canary changes;
the owner selects an existing exact canary and requests promotion to a named
channel. Automation verifies and performs the covered operations. Promotion
reuses the tested bytes, not a rebuild of today's main.

The user has requested daily conditional deployment plus manual deployment,
batch AI version assessment, per-Host changelogs displayed by the docs site, and
formal GitHub publication by selecting a canary to promote. There is no daily
automatic product test and no per-PR full-CI merge gate.

This document defines proposed implementation defaults. Merging it authorizes
no Product Build allocation, signing, tag push, public Pre-release, Release,
deployment, Environment change or channel promotion. Current technical gates
remain effective until their separately verified replacements are activated.
Task shipping authorization is distinct from release-operation authorization.

## 2. Baseline and changes still required

Current authority is [version management](../governance/version-management.md),
[Git workflow](../governance/git-workflow.md), and the
[release pipeline](2026-08-13-lmdj-standard-release-pipeline-design.md).

| Current implementation | Required prospective change |
| --- | --- |
| Product candidates use `complete-test-v2`, including full 16-suite evidence | Separate canary admission from formal-channel admission; preserve full exact-candidate evidence at formal promotion |
| Product signing happens in trusted local preparation | Add a separately approved isolated automated signing boundary; no key migration is authorized here |
| `web-hosts` Release contains both Host ZIPs, checksums and signatures | Keep a complete same-candidate asset inventory, even when only one site is deployed |
| `promotion.max_channel` is `dev`; stable promotion is explicitly refused | Resolve the stable question, implement target-channel admission and promotion-aware audit before enabling stable |
| Release audit compares metadata to the initial publication channel | Verify immutable initial identity plus append-only promotion receipts and current channel |
| Portal workflow accepts main pushes; Host release deployment remains separately controlled | Introduce daily/manual selection and cut over old triggers only after rehearsal |
| Product/Assembly paths conservatively select full testing | Measure and explicitly handle mechanically verified allocation-only changes before daily activation |

The [stable promotion question](../prd/questions/stable-channel-prerelease-flip.md)
remains open until its decision and implementation ship. GitHub supports changing
Pre-release/Latest metadata while locking release assets and the tag; repository
policy currently imposes additional restrictions. See
[GitHub immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases).

## 3. Identity and complete candidates

- Hosts keep independent SemVer from their active `module.json` files. A change
  to one Host does not mechanically bump every other Host.
- Product Build remains `MILESTONE.MINOR.BUILD.PATCH`, not SemVer. Ordinary
  automated allocations increment BUILD under the existing identity rules;
  AI cannot choose a new milestone, product minor line or Contract ID.
- Any allocated Product Build maps to one exact protected-main revision and
  Assembly lock. Numbers are audited against canonical occupancy and never
  reused after allocation, including abandoned attempts.
- A promotable Product canary contains both Creator and Lab/Runtime artifacts
  from the same final revision and Assembly. Each records its Host version,
  Product Build, toolchain/input identity, digest and byte length.
- Complete packaging and selective site deployment are different decisions.
  V1 builds both Host packages for a Product candidate. It may share verified
  intermediate compilation caches; it never relabels an older final archive.
  Build identity is embedded in Host outputs, so changing Product Build can
  change both packages even if one Host's behavior is unchanged.
- A local or partial preview is not a promotable Product canary. V1 does not
  synthesize a Product Release from separately chosen Host versions or SHAs.
- Channel is external lifecycle metadata, not a version suffix requiring a
  replacement archive at promotion. Historical build-time channel, if present,
  means channel-at-build; current channel must be separately sourced and labeled.
- Build manifests are generated after checkout. They may record the final SHA;
  source files must not attempt to embed their own containing commit SHA.

Package identity is frozen before publication. Required assets must all exist
in the Draft before it becomes an immutable Pre-release. Missing assets cannot
be appended to an already published immutable release.

## 4. Scheduling, scope and distinct progress

The daily schedule is one wakeup/check, not an unconditional build, deployment
or full test. Manual selection runs the same planner with explicit site scope.
V1's proposed schedule is 03:17 Asia/Shanghai (`17 19 * * *` UTC on the previous
UTC date), subject to deployment configuration review. Late/missed schedules
are expected; correctness never depends on a 24-hour PR search window.

Maintain independent durable facts:

| Fact | Meaning |
| --- | --- |
| Version-accounted revision and assessment receipt | Changes already represented by allocated Host versions and changelogs |
| Last successful deployment per site and channel | Exact candidate actually verified at that site's fixed address |
| Last formal publication per product line | Baseline for formal release summaries, not the daily canary baseline |
| Immutable candidate and operation records | Pending, completed, failed and superseded work, including exact input identities |

Do not reuse the CI processed pointer as any of these facts. Processing is not
health. Persist candidate/operation intent before effects and reconcile actual
effect receipts before advancing progress. Version-accounting records never
make a failed deployment look delivered.

For each site, compare its deployed baseline to a pinned main target using the
complete commit interval, old/new paths, dependency closure, build configuration
and documentation source facts. Follow the current deterministic test-scope
floor; authenticated AI may add scope, not erase it. A missing baseline causes
an explicit bootstrap selection; missing history, truncated APIs or unreadable
state are errors, not no-change. Merge/revert history matters for testing;
changelog text must describe surviving user-visible behavior rather than
advertising a reverted feature.

Independent site clocks allow docs-only deployment without allocating a Product
Build. Generated version/changelog changes that the docs site consumes select
docs as well. Operational status records must have narrowly defined consumers;
they must not recursively allocate another Host version or trigger a product
rebuild. No blanket exclusion by bot author, commit title or version label.

Manual `force` can bypass the no-change decision, not identity, signing, test,
smoke or authorization requirements. A forced retry of the same candidate
reuses its version and retained artifacts. An explicit exact candidate selection
must not silently resolve to the newest main commit.

## 5. Batch AI version and changelog assessment

Collect the full version-accounting interval once per batch, using actual
diffs, manifests, dependency changes and existing PR reviews. Input records
include baseline/target SHA, policy and collector identity and content digests.
Truncated content cannot produce a complete assessment. Bounded chunking must
retain a coverage manifest proving every input was examined.

Reuse the trusted review adapter boundary: GLM, then Kimi, then Grok. Persist
backend/model identity and attempt results; the first valid complete result is
used, not an invented union of failed responses. Use bounded retries. When all
backends fail or semantic uncertainty remains, pause that version batch and
enqueue a deduplicated Issue report. Report recovery does not rerun assessment
or block PR merging. API uncertainty is not proof that an Issue POST failed.

AI outputs structured advice per affected version domain:

- affected component IDs resolved from manifests;
- `none`, `patch`, `minor` or `major`, with compatibility rationale;
- supporting PR/commit references and dependency effects;
- added/fixed/changed/breaking/migration changelog entries;
- unknowns and the complete assessed input digest.

Deterministic code validates references, allowed fields, bounds, baseline and
coverage, then computes versions. Within an unaccounted component interval,
take the highest required impact; never count each PR as a new increment.
Previously committed adequate version changes are consumed rather than bumped
again. Conflicting or insufficient pre-bumps require a visible correction.
Upstream major or a `feat` title does not automatically imply Host major.
Data compatibility and public Contract changes require explicit reviewed
decisions; AI cannot silently settle them. Proposed V1 auto-allocation covers
unambiguous compatible patch/minor only; major or migration uncertainty pauses
automatic rollout of the affected candidate, not ordinary merges.

Model input is untrusted, including PR bodies, code, links and changelog prose.
Model execution has no GitHub write, signing or deployment credentials and
cannot emit executable commands. The deterministic publisher escapes untrusted
Markdown/HTML, rejects invented references, and preserves machine markers.

## 6. Version preparation and moving main

Use a short-lived version PR, normal current-head review and expected-head
merge protection. No direct-main bot writes, long-lived release branches or
repository-wide business-merge lock.

An assessment at A does not automatically cover a later version merge C if B
entered main in between. Candidate admission therefore uses this protocol:

1. Record assessed business target A and the last version-accounted baseline.
2. Compute and review a version PR containing only declared allocation files,
   Host changelogs, generated identity/lock files and required docs snapshots.
3. Before merging, reconcile its base and occupancy. If relevant changes are
   unassessed, refresh the assessment and the current-head review.
4. After squash merge, resolve C and enumerate every additional commit/path
   between A and C. Recompute dependency and input identities. Only reviewed
   allocation outputs and explicitly proven irrelevant changes may be accepted
   without renewed assessment. PR head checks alone cannot prove base stability.
5. If coverage changed, do not sign, tag or publish C. Retain its allocated
   number as occupied, mark the attempted candidate superseded/incomplete, and
   prepare a new reviewed cut. Carry all undelivered scope forward. Never
   retarget the old Product Build to the next commit.
6. Once admitted, freeze C. Later main updates belong to the next batch. Create
   snapshot provenance using the canonical post-squash witness mechanism;
   evidence commits do not replace C as the candidate target.

V1 allows at most three automatic cut attempts per wakeup before retaining
pending work and reporting contention. A single allocation writer serializes
occupancy and version publication, with expiring/fenced claims and durable
receipts; it must not hold a lock across AI calls, builds or tests. A replacement
writer reconciles the old attempt before allocating a new identity. It does
not block ordinary business merges. Liveness under sustained main churn is a
measured acceptance item, not an assumed property of optimistic retries.

### Avoid a new full-test amplifier

Changing `products/lmdj/` currently conservatively selects full testing. Daily
allocation must not silently turn this into a daily full product test.

Before activation, a separate scope-policy Task must demonstrate a deterministic
allocation-only recognizer on real committed trees, or report that the capacity
goal remains unmet. It must verify canonical generator outputs, unchanged
underlying component/Contract/provider/build inputs except declared reviewed
version metadata, complete business interval scope and mandatory identity/docs
checks. Changed component payloads, schemas, toolchains, CI, ambiguous inputs
or spoofed bot commits retain existing conservative selection. Do not globally
exclude Product/Assembly paths. Any revised policy ships with differential
fixtures and its consumers before activation; this proposal changes no floor.

## 7. Host changelogs and docs presentation

V1 uses one canonical `CHANGELOG.md` per active versioned Host, alongside its
manifest (including Creator and Runtime). Only changed Hosts acquire entries.
The docs site aggregates these inputs into Host-specific pages; it does not
maintain copies by hand. The docs site itself needs no invented Product/Host
SemVer just to display other Hosts' logs.

Version and changelog updates share one reviewed commit. Entries identify Host
version, allocation date, user-facing changes, migration warnings and verified
PR references. A release date is supplied only after publication. Shared Core
changes explain their actual effect on each affected Host. No change to retired
Contracts is permitted by this workflow.

The portal distinguishes prepared, canary-published, deployed-per-site and
formally-promoted facts. Source changelog entries are immutable after their
version is published; corrections are explicitly attributed addenda, not silent
rewrites. Promotion does not modify Host versions or source changelogs.

Formal summaries compare the prior formal candidate to the selected candidate,
even across many intervening canaries. Proposed V1 renders that summary in an
append-only promotion record on the docs site. Canary Release notes contain a
stable link to the product's promotion history page. Promotion leaves the
original GitHub body and machine plan marker unchanged. Editing a formal
summary directly into an existing Release body would need a separately defined
metadata exception and verifier; it is not an implicit permission here.

Product Build/Assembly allocation still requires current portal updates and an
immutable matching snapshot with valid post-squash provenance. The docs site
must not use a newer current manual as the immutable manual for an older stable
candidate. Live status belongs outside frozen snapshots.

## 8. Canary admission, signing and deployment

Canary admission requires complete identity/lock/freshness checks, both packages
and their verifiers, the package builders' required tests, and selected relevant
main-batch checks. Results bind exact target and effective inputs; evidence
reuse must be explicitly verified, not inferred from similar code. A required
failed/missing result stops candidate delivery, not PR merge. A full main batch
may legitimately be selected by foundational changes; the calendar alone never
requests it. The closed canary check inventory is a prerequisite implementation
deliverable, not the undefined phrase "minimal tests".

Signing and publication occur only after candidate input and package verification.
The proposed automated signer is a dedicated trusted local service/executor,
isolated from PR/model workloads. It verifies a narrowly scoped authenticated
request binding target, Product Build, inventory, digests, policy and replay ID.
Keys retain their existing distinct roles; secrets never enter model prompts,
ordinary runner environments, logs or artifacts. Offline signer means pending,
not unsigned fallback. Concrete host/key custody, request authentication and
recovery need explicit owner-approved configuration before activation.

Product tags remain signed annotated `lmdj-v<PRODUCT_BUILD>` tags with no channel
suffix. The canary prepares a tag after its admitted packages are verified,
then reconciles the exact push, complete Draft and immutable Pre-release in
order. Formal promotion reuses all of those identities. No overwritten assets,
moved tags, blind duplicate POSTs or bulk tag pushes.

Deploy only retained verified release bytes through the existing Host adapter's
candidate validation, fixed-route promotion, HTTP/browser verification and
exact-prior recovery. Preview success is not fixed-address acceptance. Retain
the applicable Cloudflare header, charset, robots, isolation, routing-readiness
and browser-state checks, including real platform side effects and data recovery.

Site targets are explicit per Host/channel. V1's intended automatic target is
canary only, never a stable address. Current Creator/Lab URLs are not silently
reclassified as canary; exact target mapping, credentials and user-data boundary
must be recorded before rollout. Each site advances only after its own verified
success. An unrelated site may remain on an older candidate and must show that
fact, not claim every site runs the latest Product Build.

## 9. Formal promotion

The owner selects an exact existing candidate and target channel. V1 proposes
direct canary-to-stable selection when all stable conditions are satisfied;
intermediate button clicks are unnecessary. This does not infer that today's
product is stable-ready or authorize raising `max_channel` by itself.

The protected controller verifies immutable tag/signatures, exact inventory and
digests, complete current-policy 16-suite evidence for that candidate, required
packaged Host/browser and compatibility acceptance, and explicit disposition of
known candidate-blocking defects/security issues. Historical source tests are
not sufficient for missing artifact acceptance. Missing/expired test evidence
requests an exact-target full batch via the existing scheduler and verifies its
results; it neither rebuilds release assets nor advances automatic test progress.

Published-canary historical audit exceptions must not excuse fresh stable
admission. Old candidates are selectable, not automatically eligible. Do not
silently change identity to include a later fix or require all unrelated Issues
to be closed. Data-migration uncertainty blocks affected promotion even if the
test summary is green.

Promotion is one user intent with separately verified recoverable transitions:
persist intent, verify admission, recheck expected Release state, update only
`prerelease` and the explicitly intended global Latest pointer, verify remote
postconditions, and persist an append-only receipt. Initial publication facts
remain immutable; current channel derives from verified promotions. The audit
must understand this distinction and preserve the original release-plan marker.

Use an operation ID and single fenced writer for the product line's channel/
Latest mutations. Old operations cannot supersede newer ones. Latest is a
global pointer, not an eternal property of every past stable Release. Promoting
an older version must not accidentally roll Latest backward; rollback requires
its own explicit intent and data-compatibility checks.

GitHub and repository state are not a distributed transaction. An API timeout
leaves an unknown state until read-only reconciliation by Release ID, tag and
exact fields succeeds. Record partial effects before resuming. A ledger-write
failure after GitHub success requires record recovery, not a second publication.
Unexplained out-of-band metadata changes are incidents, not accepted promotions.

Formal Release publication and production deployment remain distinct states.
The promotion request must state whether deployment is included; the proposed
default is publication only. No `release.published` deployment fan-out is added.
Releasing twice is not the remedy for a failed site deployment. Rollback reuses
an explicitly selected prior artifact, retains history and validates persisted
data compatibility before changing routes.

## 10. Capacity, retention and activation prerequisites

Routine Linux planning, publishing and builds use existing self-hosted capacity.
The owner's macOS GitHub-hosted fallback remains available for macOS build/test
jobs only, with visible usage; this is not a zero-total-bill promise. Signing
does not follow that fallback. AI requests, storage and network costs are
reported separately from Actions minutes.

One active daily candidate batch coalesces newer main changes into later work;
daily and manual requests share deduplication and resource budgets. Do not cancel
an executing batch merely because another PR merges. Retain candidate artifacts
needed for promotion and exact-prior rollback; do not depend solely on expiring
Actions artifacts. Expired test evidence is reacquired, never fabricated.
Permanent public canary Releases and snapshots accumulate: measure complete
packaging time, storage growth, queue delay and signing availability before
activation. No automatic deletion of published identities is introduced.

Activation requires reviewed resolution/configuration of:

1. complete two-Host packaging budget and closed canary check inventory;
2. allocation scope treatment and moving-main bounded retry evidence;
3. trusted signing executor, key custody and authenticated request boundary;
4. explicit canary/stable site mapping and user-data isolation/migration policy;
5. stable admission checklist, supported channel ceiling, permitted metadata
   transition, promotion-aware audit and recovery;
6. durable storage, retention and failure-Issue delivery;
7. scheduled/manual trigger cutover, exact prior trigger rollback and measured
   rehearsal outcomes.

All may be implemented disabled while prerequisites remain outstanding. A
design merge, a fake API test or a successful prefix is not activation evidence.

## 11. Acceptance matrix

Every row needs a far-side assertion; live rows retain IDs and complete
SHA/digest/size identities. No real Product tag/Release is used for destructive
testing. Authorized sandbox rehearsal names exact disposable targets separately.

| Journey | Required observable |
| --- | --- |
| No change; docs-only; one Host; shared Core change | Respectively no product work; docs only; complete candidate/selective site delivery; dependency-complete testing |
| Missed schedule and several merges | All pending relevant history covered once, no 24-hour hole |
| Pre-bumped component; mixed patch/minor; reverted feature | No double bump, correct batch version, no false feature announcement |
| GLM fails, Kimi succeeds; both fail, Grok succeeds; all fail | Exact fallback receipts; bounded deduplicated Issue; no mutation on invalid advice |
| Untrusted PR commands or invented AI references | No code execution/credential access; assessment rejected |
| Main advances before and during squash merge | Actual merged inputs covered or candidate refused; no mislabeled package |
| Concurrent daily/manual cut and three contention retries | One fenced allocation writer; no duplicate version; pending work remains visible |
| Generated allocation versus forged or substantive Assembly change | Narrow path only for proven generated metadata; true changed inputs retain conservative coverage |
| Signer offline/restart; build failure after allocation | Pending/reconciled identity, no unsigned publication or number reuse |
| Missing Draft asset; upload/publication API outcome unknown | No incomplete immutable release; reconcile IDs before retry |
| Creator deploy succeeds, Lab fails; restart and recovery | Independent progress and exact-prior route recovery, no repeated bump |
| Preview passes but fixed route initially 404s | Bounded readiness followed by unchanged HTTP/browser identity checks |
| Promote same canary after main advances | Same tag/SHA/asset digests/versions before and after; formal evidence binds selected candidate |
| Expired full evidence; failed full evidence | Reacquire for exact target; failure leaves canary unpromoted and PRs mergeable |
| GitHub promotion succeeds but receipt persistence fails | Reconcile actual Release, recover receipt, no duplicate publication |
| Concurrent promotions or older candidate selected | Expected state/fencing prevents unintended Latest rollback |
| Production deploy failure after publication | Release stays published, deployment marked failed; no fictitious all-sites success |
| Roll back with incompatible persisted data | Unsafe rollback refused; prior artifacts/history retained |
| Docs aggregation and promotion | Independent Host entries, truthful per-site/channel state, frozen version manuals unchanged |

## 12. Version Management

Version impact: none

Reason: This design allocates no Product Build and changes no Host, Module,
Contract, Provider, Assembly, generated identity or release asset. Implementation
Tasks must independently declare impact; allocation Tasks require canonical
version tools, current portal changes and immutable snapshot provenance.

## 13. Documentation Impact

Documentation impact: none

Reason: This proposal and its plan do not change current Portal pages or claim
new implemented behavior. Implementation affecting operations must update
`/operations/version-and-release/`, `/operations/testing-and-proof/`,
`/hosts/creator-web/`, `/hosts/web-runtime/` and the changelog routes in the same
Task. New changelog route names must be declared when that feature is designed.
