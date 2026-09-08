# Cloudflare migration implementation plan

Umbrella: https://github.com/endaye/lmdj/issues/873
Design: [approved migration design](../specs/2026-09-08-cloudflare-migration-design.md).
The user approved the design in this thread and identified the Cloudflare login
email on 2026-09-08. Email identifies the login, not a Cloudflare account ID.
Status: implementation planning; account access and pilot evidence pending.

## Execution order

Execute T1–T4 before Portal production cutover. T5–T7 cover both product Hosts;
they are not removed from scope by a successful Portal pilot. Preserve exact
source/version evidence at each transition. No production cutover or paid
service is inferred from design approval.

### T1 — Authenticate and establish account facts

Owner: migration agent, with user completing interactive login when required.
Declared files: update the audit/design evidence only; no credential files in Git.

1. Run Wrangler `whoami` outside the repository to avoid unintended project
   configuration or secret loading. If unauthenticated, start OAuth login with
   only the scopes required for the current account audit.
2. Confirm the supplied login email and enumerate actual accessible account IDs.
   Select the account only from the returned identity, never from the email.
3. Read effective plan, existing Workers/Pages projects, subdomain and repository
   integration. Capture non-secret inventory. Check domain ownership once the
   user selects production domains; assigned Preview domains suffice for pilot.
4. Prove Preview/production isolation. A Worker name is not a permission boundary.
   Reject any setup in which PR scripts inherit production mutation credentials.
5. Validate actual version upload, preview retention and headers constraints in
   T3; public documentation alone does not complete account verification.

Acceptance: authenticated identity matches the user's login; selected account,
access limits and safe publisher boundary recorded. Never print token material.

### T2 — Portal portable build and upload contract

Owner: migration agent. Depends on T1 identity/isolation decision.
Declared files: Portal package/lock/config, new Cloudflare config/build helper,
Portal tests and static header file, scope rules only if existing ownership fails.
Keep Netlify consumers working until T8.

1. Pin tested Node 22 and npm 10.9.3; pin a compatible Wrangler version.
2. Preserve full-repository inputs, facts generation and existing `check` command.
   Configure output as static SSG with a real 404 page and existing headers.
3. Keep official origin separate from assigned Preview URL; do not fabricate
   Worker/account/domain identities. Keep snapshots immutable.
4. Test asset counts/size and header rule bounds against candidate output;
   exclude tooling, credentials and source-only files from uploads.
5. Add relevant-path filtering only after table-driven producer/consumer cases
   demonstrate every facts/docs/diagram/snapshot dependency is covered. Unknown
   paths build. Avoid relying solely on the Portal directory prefix.

Validation: focused config/header/dependency tests, `architecture-portal.sh check`,
Wrangler dry-run for the pinned candidate, and staged-index scope ownership test.
No local success is represented as cloud acceptance.

### T3 — Exact-head Preview and GitHub smoke

Owner: migration agent. Depends on T2 and account publisher isolation.
Declared files: Portal smoke workflow/tooling/tests; cloud pilot settings tracked
as sanitized evidence, with actual cloud IDs rather than guessed values.

1. Limit the initial pilot to the migration branch. Capture actual Cloudflare
   event/check payload and SHA/version/URL mapping before selecting the observer.
2. Build PR code without production credentials. Use managed Workers Builds only
   if its actual access model satisfies the design; otherwise implement the
   approved trusted GitHub publisher alternative, using trusted workflow code.
3. Upload a candidate version without production promotion. Verify immutable URL,
   generated revision, all smoke routes, diagrams/snapshots, headers, 404 and links.
4. Write GitHub status against that exact PR head only after smoke; test an older
   completion arriving after a new head, foreign target URL and failed smoke.
5. Record real duration and queue delay. Recompute the seven-day demand model and
   activate broader previews only within the chosen budget/trigger policy.

Acceptance: live current-head Preview + correct content + exact-head GitHub
status. Preserve build and smoke evidence independently of cloud log retention.

### T4 — Portal production and rollback

Owner: migration agent and authorized account/domain operator. Depends on T3.
Declared files: Portal official URL, governance and current Portal operations
pages/diagrams, deployment runbook and smoke integration.

1. Review actual production domain, known prior deploy and budget before cutover.
2. Apply the approved Git-triggered production flow, then verify source SHA,
   platform version/deployment IDs, Product revision and full HTTP/content smoke.
3. Demonstrate rollback to retained prior content with identity revalidation;
   define an observation window before retiring Netlify previews.
4. Keep old netlify.app routes available through an explicitly chosen transition.
   DNS cannot repoint the provider-owned netlify.app hostname.

Acceptance: separately authorized production transition and rollback evidence.

### T5 — Shared Host deployment adapter and evidence

Owner: single migration agent for shared files. Depends on approved account model.
Declared files: shared Host deployment/API/recovery tools, serialized evidence
Contracts when required, API/command/header tests and their scope ownership.

1. Map existing Netlify evidence fields to Cloudflare semantics explicitly; decide
   Contract versions before emitting a different serialized format.
2. Preserve signed release archive verification, byte digest/length checks,
   exact Host identity, candidate readiness, same-version promotion and recovery.
3. Test never-deployed target, wrong account/Worker, expired version, timeout,
   upload mismatch, concurrent operator change and failed rollback.
4. Keep Creator/Runtime independent; no main-push automatic product deployment.

Acceptance: meaningful API/command regression tests and a non-production cloud
exercise of the complete candidate/promote/recover sequence when authorized.

### T6 — Creator migration

Owner: Creator integration owner. Depends on T5.
Declared files: Creator deploy integration, relevant assembly/header assets,
Creator host current documentation, acceptance evidence and runbook.

Preserve signed archive bytes, MIME, COOP/COEP, cache and Service Worker behavior.
Assess origin-scoped Project storage and provide an explicit export/import handoff
if required. Test browser audio/permissions and record human-only acceptance
separately. Cut over only after authorized candidate and rollback acceptance.

### T7 — Runtime migration

Owner: Runtime integration owner. Depends on T5; shared files remain owned by T5.
Declared files: Runtime deployment integration, relevant headers/assets, Runtime
current documentation, acceptance evidence and runbook.

Verify signed release identity, WASM MIME, cross-origin isolation, immutable asset
caching, entry refresh and runtime browser behavior. Repeat candidate and rollback
validation independently of Creator. Channel promotion remains separate.

### T8 — Retirement and umbrella closeout

Owner: migration agent. Depends on each affected site's acceptance.
Declared files: unused Netlify dependencies/config/hooks/tests, current governance
and runbooks, approved issue status updates.

Inventory remaining Netlify consumers before removal. Retire only superseded
integrations, preserve old deployment history and rollback evidence, verify no
stale failure status remains. Explicitly update #867 alternative acceptance;
never mark its historical failed Netlify deploys successful. Audit every #873
checkbox against live evidence. Any Host deferral needs an explicit decision and
follow-up Issue; it cannot silently disappear from scope.

## Version Management

Version impact: none for this plan and approval record. Each implementation Task
assesses its own manifests and evidence Contracts. Product Build/Assembly changes
require the governed version allocation and immutable Portal snapshot.

## Documentation Impact

Documentation impact: none for this planning-only commit; current behavior is
unchanged. T4–T8 have required documentation impact, covering current operations
and Host routes and source diagrams in the same owning Task. Run Portal checks
when editing documented source facts or those pages/tooling.

## Local verification and shipping

Each task uses an isolated short-lived branch, exact-path staging and a precise
Conventional Commit after its declared tests. New tracked files run the staged
ownership suite. Review live repository policy and existing session authority
before push/PR/merge; design confirmation does not itself authorize production
routing, billing changes, Release publication or Channel promotion.
