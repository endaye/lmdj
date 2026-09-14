---
id: fake-tool-stub-strictness
area: ci-release
status: open
recurrences:
  - date: 2026-08-27
    occurrence: https://github.com/endaye/lmdj/issues/349
    observed_by: claude-code/fable-5
  - date: 2026-09-06
    occurrence: https://github.com/endaye/lmdj/pull/730
    observed_by: Claude Code (Opus 5)
  - date: 2026-09-07
    occurrence: https://github.com/endaye/lmdj/actions/runs/34119041231
    observed_by: Codex
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/actions/runs/34151840695
    observed_by: Codex
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/pull/802
    observed_by: Codex
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/actions/runs/34124875948/attempts/2
    observed_by: Codex
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/issues/968
    observed_by: Codex
  - date: 2026-09-11
    occurrence: https://github.com/endaye/lmdj/actions/runs/34630800630
    observed_by: Codex
  - date: 2026-09-11
    occurrence: https://github.com/endaye/lmdj/actions/runs/34633148497/attempts/2
    observed_by: Codex
exit: gate:apps/web-runtime-host/test/deploy_command_test.py
escalation: https://github.com/endaye/lmdj/issues/726
---

# A test double laxer than the thing it stands in for certifies states the real implementation cannot produce

## Why

The deploy suite's fake `git` matched `cat-file` by prefix (`args[:1] ==
["cat-file"]`) and answered any arity, so `scripts/web-runtime-deploy.sh`
calling bare `git cat-file "$ref"` — which real git rejects with exit 129
(`only two arguments allowed in <type> <object> mode`) — passed all 50 suite
tests and then failed 100% of the time on real runners (#349, first observed
on the lmdj-v1.0.36.0 deployment preflight). A stub that accepts a superset of
the real tool's contract turns the suite into a certifier of invalid
invocations, and the gap only surfaces on the first genuine end-to-end run —
the same never-exercised-path failure mode as
[[release-authority-fetch-credentials]] and [[draft-release-read-visibility]].

On 2026-09-06 the same shape reached a TypeScript double of an internal typed
Contract, and arrived as a load-sensitive flake rather than a hard failure
(#713 shape A). `apps/creator-web/test/perform_surface.test.tsx` stubbed
`queryPerformanceReplayStatus` as a bare `vi.fn()`, so it resolved `undefined`
where the real session's `replayResult` always returns a frozen status object.
`PerformSurface` polls that method every 250 ms while a replay plays, so it is
reached by wall-clock rather than by a test step that opts into it — and no
test mocked it. Any step that outlasted one interval dispatched
`replay: undefined` into `state.replay`; the Replay status output guards on
`=== null`, so it dereferenced `undefined` and tore the surface down. It never
fired on an idle laptop and fired repeatedly on saturated runners, so it was
first read as a runner-capacity symptom.

Two properties made it expensive. The double's laxity was invisible at the
call site — `perform_state.ts` reads exactly like production. And the method it
weakened is the only one in that surface reached without a test asking for it,
so no test ever gave it a value.

The repair is not automatically "make the double answer what production
answers". Two sessions reached this root cause independently and proposed
different stubs, and the faithful-looking one was wrong: a default resolving
`state: "playing"` let a poll that was still in flight when `stopReplay`
landed resolve afterwards and overwrite the staged terminal state, so the
rendered replay test read `playing · resolved revision · 7` where it asserted
`stopped · neutral`. That is a second load-sensitive failure traded for the
first. The stub that shipped models a poll the Core has not answered yet, so it
cannot overwrite state a test staged, and a test that wants the poll answered
stages the answer itself.

That asymmetry is the reusable part: a double for a method the code polls must
be neutral with respect to state the test staged, which is a stronger
requirement than merely matching the production return type.

## How to apply

The self-test reporter takeover found the same gap in an external API response
fixture before rollout. Its fake Actions run always returned `name: Core CI`,
and the consumer treated that display string as workflow authority. A read-only
query of the occurrence above returned both `name` and `display_title` as
`Core CI / 757/merge`, while `workflow_id` and `path` identified Core CI. The
literal-name check would have skipped real dynamically named self-tests. This
was a fixture/consumer finding, not a claim that the unreleased reporter had
already dropped a production report. `tests/build/ci_self_test_report_test.py`
now uses dynamic display names and proves that only the independently checked
workflow ID/path and run provenance determine admission. The broader existing
escalation #726 remains open; this narrow regression does not absorb its
unresolved typed-polling scope.

For an external API double, verify representative response fields against the
real read-only endpoint or a source-backed fixture, including configurable
display fields. Do not promote a presentation value into an identity merely
because the fake always returns one literal.

The 2026-09-08 merged-review mapping fixture omitted another actual Actions
shape: after merge, an original PR review run can retain its exact PR head but
return `pull_requests: []`. Empty association is not absence of a PR, and also
is not proof by itself. `tests/build/ci_review_merge_map_test.py` now exercises
that shape while retaining exact-attempt head, live merged PR bot COMMENT,
trusted source/control/jobs, historical policy and actual same-run artifact
equality. Wrong head, wrong nonempty association and another PR's otherwise
valid artifact remain rejected. This narrow external API regression does not
close the broader escalation #726 or claim successful platform O1 acceptance.

When a test fakes an external tool, every faked subcommand must reject the
invocations the real tool rejects (arity, required flags, mode conflicts) —
match by exact expected shape, never by command-name prefix. The enforcing
gate here is the hardened fake git in
`apps/web-runtime-host/test/deploy_command_test.py`, which now fails a bare
`cat-file <object>` exactly like real git. Apply the same strictness when
adding new subcommands to any fake tool.

Independent review of the later scope fallback integration found that #802's
mapping reader expected `commit.paths`, while the real Git collector returns
`commit.changes[*].paths`. Its tests mocked collection with the invented shape,
so valid advice failed authentication in a real-shaped interval. Unconditional
full fallback had concealed the defect. The reader now derives the actual
per-commit path union and its regression runs real Git collection through the
reader and final selection, retaining valid extra AI advice. HTTP receipts in
that regression remain fixtures; this was an independent code/fixture finding,
not proof of a historical remote lost-advice incident. Escalation #726 remains
open for the broader polling-double scope.

A later read-only Actions inventory audit found that the exact-attempt API's
`created_at` need not equal the run-list timestamp: run 34124875948 attempt 2
is 59 seconds later, and run 34137319062 attempt 1 is one second later. The
discovery fixture returned the same object for both endpoints and certified an
equality gate that would strand such receipts. Discovery now preserves original
run time for inventory/frontier and accepts a valid attempt time at or after
that origin, without weakening exact run/attempt/repository/workflow/head or
the real collector's source/receipt authentication. The regression keeps both
attempts, queue-only persistence and fresh-process deduplication. This was a
shared Actions API finding using actual Core CI runs, not a claim of an observed
lost PR Review callback. The broader escalation #726 remains open.

When a test doubles an internal typed interface, the defect to avoid is the
same — the double resolving something the real implementation never resolves,
such as the `undefined` a bare `vi.fn()` yields for a method declared
`Promise<PerformanceReplayStatus>`. The *repair*, though, splits by how the
method is reached, and mirroring production is right for only one half:

- **A method a test invokes explicitly** — mirror production: resolve the shape
  the real implementation resolves, and let each test stage its own value.
- **A method the code reaches by wall-clock** — a poll, an interval, a retry —
  must instead be **neutral with respect to state the test staged**. Any value
  such a stub resolves can land late and overwrite state the test set up two
  steps earlier, which trades one load-sensitive failure for another rather
  than fixing anything; the reproduction in the Why section is exactly that.
  Model "the Core has not answered yet" — `vi.fn(() => new Promise(() => {}))`
  — and let a test that wants the poll answered stage the answer itself.

So do not read this entry as "always make the double production-shaped". For a
wall-clock-reached method a bare `vi.fn()` is a lax stub and a
production-shaped one is an unsafe stub; the neutral one is the fix. Give these
methods particular attention, because no test opts into them, so no test will
notice what they return.

That half of the invariant has no gate. The deploy suite's hardened fake git
covers one Python suite's fake external tool and cannot see a TypeScript
double; a blanket "every stubbed method needs an implementation" test over the
Perform double would require settling a default return shape for about ten
methods that tests deliberately leave unmocked, which is not an invariant that
already holds. Escalation Issue
[#726](https://github.com/endaye/lmdj/issues/726) tracks the narrower
mechanism — gate only the wall-clock-reachable methods — and records that
analysis so no later Task ships the blanket version.


The Cloudflare pilot exposed a further real Actions shape: after a PR push,
`run.head_sha` stays at the original build revision while the nested
`pull_requests[].head.sha` (and base SHA) updates to the current PR. A fixture
that changed only the independently fetched PR omitted this mutation and made
stale completion appear valid locally. #968 moves current-PR staleness handling
ahead of the mutable association-head assertion, while retaining repository,
workflow, event, pilot branch and PR-number checks first and exact association
head checks for publishable runs. Its regression asserts no download, Cloudflare
call, upload or status write for a real-shaped superseded run. The broader
escalation #726 remains open.

The PR-Agent cutover's producer retained three diagnostic JSON members, while
the reader fixture still manufactured only canonical receipts. A real run
completed review/publication but merge-time authentication rejected its member
inventory. `ci_review_wait_test.py` now builds the archive inventory from the
current workflow's upload paths and reaches the real reader, including negative
controls for missing/tampered canonical receipts, unknown paths, duplicate
members/keys, and malformed diagnostics. The only newly admitted members are
the three explicitly named optional v2 diagnostics; none supplies review
authority. Earlier invalid observations remain historical evidence. The broader
escalation #726 remains open; this repair does not settle typed polling doubles.

PR #1243 then exposed a different projection mismatch: the per-review comments
endpoint returns legacy `position` fields but omits modern `original_line` and
`side`. The fixture incorrectly returned the full detail shape there, so a
successful real review with findings was rejected. The reader now fetches each
listed numeric comment ID from the canonical detail endpoint, binds it back to
the complete review inventory, and compares its exact original RIGHT-side line
and body to the authenticated model artifact. The regression keeps list/detail
responses separate and rejects missing, forged, duplicate and mismatched
identities/locations. No line is inferred from legacy position and no finding
is omitted. The broader escalation #726 remains open.
