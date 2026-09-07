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

When a test fakes an external tool, every faked subcommand must reject the
invocations the real tool rejects (arity, required flags, mode conflicts) —
match by exact expected shape, never by command-name prefix. The enforcing
gate here is the hardened fake git in
`apps/web-runtime-host/test/deploy_command_test.py`, which now fails a bare
`cat-file <object>` exactly like real git. Apply the same strictness when
adding new subcommands to any fake tool.

When a test doubles an internal typed interface, the same rule applies to
return values: a method the double stubs must resolve what the real
implementation resolves. Give particular attention to any method the code
under test reaches by wall-clock — a poll, an interval, a retry — because no
test opts into it, so no test will notice that it returns nothing. A bare
`vi.fn()` for such a method is a lax stub, not a neutral one.

That half of the invariant has no gate. The deploy suite's hardened fake git
covers one Python suite's fake external tool and cannot see a TypeScript
double; a blanket "every stubbed method needs an implementation" test over the
Perform double would require settling a default return shape for about ten
methods that tests deliberately leave unmocked, which is not an invariant that
already holds. Escalation Issue
[#726](https://github.com/endaye/lmdj/issues/726) tracks the narrower
mechanism — gate only the wall-clock-reachable methods — and records that
analysis so no later Task ships the blanket version.
