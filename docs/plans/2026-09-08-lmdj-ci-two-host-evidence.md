# Two independent Host CI documentation Tasks and O1 evidence

Status: documentation preparation only. Neither Task authorizes an O1 dispatch,
state initialization/reset, merge window, automatic trigger switch or release.
Base for both Tasks: `6d50bf922f143d2d4a4f134cc2d3f368b269b0aa`.

## Task A — Creator CI proof boundary

Declared files: `apps/creator-web/README.md` and this plan. One Conventional
Commit on `docs/ci-creator-proof-boundary`; separate PR, merged before Task B
only when the root coordinator opens the actual O1 window.

Explain the actual CI action's complete proof, locked dependencies, browser and
Git LFS prerequisites. Do not change product code or shorten its proof. Verify
the prose against `ci.yml`, `web-ci-proof/action.yml` and `creator-web.sh`;
run docs-static, staged ownership and whitespace checks. Run Portal check for
the documented source facts and disclose unavailable dependencies.

Version impact: none — local verification documentation, no product identity.
Documentation impact: none — Host README and planning only, no Portal page or
current trigger behavior changes.

## Task B — Web Runtime Lab automated evidence boundary

Declared file: `apps/web-runtime-lab/README.md` only. One Conventional Commit
on `docs/ci-lab-proof-boundary`; separate PR references this Task definition.
The PR must follow A's merge; it does not add another plan or edit A's README.

Explain the actual Node/Python wrapper, independent CI path, and distinction
from device-guided measurement and Creator's browser proof. Verify against
`web-runtime-lab.sh`, its package scripts and `ci.yml`; run docs-static and
whitespace checks. Run Portal check and disclose missing dependencies. No new
tracked file is introduced by B; unchanged ownership still runs as a safeguard.

Version impact: none — explanation only, no Host implementation or identity.
Documentation impact: none — local README only, no Portal/current CI switch.

## Why these two Hosts

At the base above, real `scope_policy.json`, `test_scope_policy.json` and
`self_test_policy.json` give these deterministic dependency closures:

| Paths | Required suites |
| --- | --- |
| Creator README | creator, docs_static, portal |
| Web Runtime Lab README | web_runtime_lab, docs_static, portal |
| Both READMEs | creator, web_runtime_lab, docs_static, portal |

Each Host contributes a suite absent from the other's closure. This is unlike
Creator plus Web Runtime Host: the latter already reaches Creator transitively.
Shared docs/portal checks execute once in the combined batch. These are real
CI instructions, not empty commits, dummy product edits or hand-authored AI
receipts. Host READMEs have routed consumers and are not none exemptions.
This explanatory plan alone may be none, but cannot erase other interval work.

The four-suite set is conditional, not an unconditional promised run result.
Authenticated extra AI advice, historical policy closures and eligible debt
must be unioned. Missing AI evidence uses the complete Git/policy floor and
remains a review gap, not a clean review. Full advice or any full-rule change
in the complete interval requires full; incomplete history remains blocked.

## Actual O1 sequence and evidence placeholders

No row below is passed by these documentation commits or local fixtures.

1. Establish a genuinely processed baseline B through normal authenticated
   settlement. Main #807 may still include pending control-plane changes:
   those require full coverage selection, not a manually moved cursor. An
   isolated journal likewise needs separately authorized initialization and
   trustworthy baseline establishment, never a copied healthy conclusion.
2. During the coordinator's admitted batch/window, merge A then B as two real
   PRs before the next batch freezes its latest target T. Retain actual PR
   heads, squash SHAs and the complete first-parent interval `(B,T]`.
3. Retain the waiting observation: prior active claim unchanged, pending
   includes both new commits, no duplicate heavy executor.
4. After actual prior termination/settlement, retain exactly one new request,
   policy digest, target T and the complete union including advice/debt. If
   the interval is full or scope is expanded, record it honestly; do not label
   that result as the minimal four-suite demonstration.
5. Read real jobs and retained execution/needs/verdict: each selected suite's
   actual outcome appears once, both distinct Host suites are included, and
   unselected work is not counted as passed. Check persisted result reference,
   processed/pending/active state and debt/failure preservation after settlement.

Evidence still pending: B SHA/result; A PR/head/merge; B PR/head/merge; waiting
run/claim/pending; T request/policy/suites; executor run/attempt and artifact
identity; actual outcomes; final settlement/state. Do not replace these with
synthetic records, manually edited labels or a partial net diff.

## Local verification and limits

Task-specific results will be recorded in each PR body after actual execution.
No full Host proof is claimed from a Markdown-only Task, and local checks do
not prove platform callback ordering, locks, artifact visibility or O1 itself.
Pitfall impact: none — existing scope and evidence invariants are preserved;
unexercised platform legs remain explicit rather than shortened away.

## Version Management

Version impact: none
Reason: both Tasks only describe existing verification; no Product Build,
Assembly, Module, Host, Provider or Contract version changes.

## Documentation Impact

Documentation impact: none
Reason: these Host READMEs and this plan do not edit Portal pages or enable
automatic CI. T5's separate current documentation and trigger obligations remain.
