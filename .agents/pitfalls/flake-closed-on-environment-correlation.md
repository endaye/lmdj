---
id: flake-closed-on-environment-correlation
area: creator
status: open
recurrences:
  - date: 2026-09-01
    occurrence: https://github.com/endaye/lmdj/issues/443
    observed_by: claude-opus-5
exit: none
---

# An intermittent CI failure was closed as an environment effect on a statistical correlation, while the failure's own retained artifact recorded the real cause the whole time.

## Why

#443 tracked `creator_web_sample_editor.spec.mjs:429` failing with
`INVALID_PROJECT` where `REVISION_CONFLICT` was expected. It was closed on
2026-09-01 as "fixed by the shared-runner capacity work": every observed flake
fell inside the host-contention window, and the rate went from 4/22 to 0/41
across the capacity change. The correlation was real. The conclusion was not.

The Playwright trace retained for the 2026-08-31 failure (run `33354469762`)
already contained six `pageerror` events reading `RuntimeError: memory access
out of bounds`, with stacks through Asyncify's `doRewind` and the pthread
proxying `checkMailbox`. That is a Wasm memory-safety trap on the control
thread, which #551 traced to Asyncify re-entrancy in the Control bridge: a
second request's proxied thunk ran while the first request's dispatch was
suspended on OPFS. CPU contention widened the suspension window and so raised
the probability, which is why the correlation held -- but the defect was in
product code and returned the day after the capacity fix was declared to have
cured it (run `33574299117`, PR #544).

Two things made the wrong conclusion easy. The sanitizer at
`packages/web-runtime-platform/src/control_runtime.cpp` `safe_message`
collapses the Facade's real reason to `"project data is invalid"`, so the
assertion message pointed at the Facade rather than at the runtime. And the
Playwright harness did not fail on `pageerror`, so the trap was a console line
in an artifact nobody opened, not the headline of the failure.

## How to apply

Before closing an intermittent failure as environmental, open the retained
failure artifact for at least one occurrence and read its `pageerror` and
console-error events. A correlation with load, runner, or time of day explains
*when* a defect fires; it does not establish that there is no defect. Treat
"the rate dropped after an infrastructure change" as a hypothesis to test
against the artifact, not as a resolution.

When the assertion that failed sits downstream of a sanitizer or an error
normalizer, assume the message you see is not the cause and look one layer
below it before attributing the failure anywhere.

No mechanism exits this entry yet: the judgment "read the artifact before
attributing" is not mechanically decidable. #551 narrows the gap by asserting
`pageerror` is empty next to the refusal assertion in the Creator journey and
in the Web Runtime Host browser spec, so a runtime trap now fails the test in
its own words; and by making the OPFS storage layer refuse an Asyncify
re-entry instead of corrupting memory. If a second closure of this shape
happens, escalate to an issue-triage skill section.
