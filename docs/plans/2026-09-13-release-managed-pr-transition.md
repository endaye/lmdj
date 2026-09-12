# Managed publication PR transition

## Defect and scope

The outer release driver only observes unresolved intents. That is correct for
an opaque write with an unknown result, but cannot finish the existing durable
PR subcontroller after creation yields to current-head review. A later first
squash request is a different effect, not a retry of the PR POST.

Enroll only the concrete publication evidence PR subcontroller as a managed
`published_record` transition. Revalidate every preceding release receipt and
original authority before advancing this frontier. Its read-only API observes
live PR/source state without external writes. Initialize its private empty
state before the outer intent is persisted; a missing child state after that
point is unknown, not permission to restart. Bind child spec to the exact
parent request and operation. Child POST/PUT intents still precede each write;
unknown outcomes still forbid replay. Opaque transitions retain their existing
strict observe-only recovery. This does not assemble the complete production
backend or admit arbitrary user-supplied managed callbacks.

Declared files:

- `tools/release/orchestration_driver.py`
- `tools/release/evidence_pr.py`
- `tools/release/evidence_pr_transition.py`
- `tests/build/release_managed_pr_transition_test.py`
- `CMakeLists.txt`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-release-managed-pr-transition.md`

## Verification

Compose the actual outer driver, PR controller and GitHub client with the
existing fake API and separate far-side filesystem fixtures. Walk publication
→ PR creation → review pending → first merge → source verification → site
pending → both Hosts → promotion/final. Assert one POST/PUT, no republish,
no Host before site, and unchanged immutable prior evidence. Fault unknown
POST/PUT, parent/child crashes, missing state, request rebound, late prior
receipt failure and postmerge source drift. Observations must issue only GETs.
Run existing driver/PR/journal regressions, staged ownership, Portal check and
independent read-only review. Fixture gates are not real GitHub review, source,
signing, deployment or complete release acceptance.

### Local verification result

- Managed transition: 16/16, exit 0, including causal opaque-driver baseline
  and real fork/exit after POST and PUT; `/tmp/lmdj-managed-pr-tests-v3.log`.
- Driver 13/13, PR controller 23/23, journal 19/19 and staged ownership 74/74,
  all exit 0; `/tmp/lmdj-managed-pr-{driver,pr,journal,scope}.log`.
- Portal: 139/139 tests, production build and 47 routes/internal links passed,
  exit 0; `/tmp/lmdj-managed-pr-docs.log`.
- Independent read-only review of all seven files found no actionable finding;
  reviewer independently reran managed 16/16, driver 13/13 and PR 23/23.

Pitfall disposition: the controller-logic defect is fully expressed by the
causal baseline and recovery regressions; no separate process-only entry.

Unexercised: actual GitHub review/protection and mutations, trusted production
backend assembly, signing, live website/deployments and full release acceptance.
Local independent review is not an owner adoption record for shipping.

## Version Management

Version impact: none

Reason: internal release control flow; no Product Build or Assembly changes.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: distinguish managed subeffects from opaque-write recovery and document
the remaining production integrations.
