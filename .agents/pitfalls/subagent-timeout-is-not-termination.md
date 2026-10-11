---
id: subagent-timeout-is-not-termination
area: docs-governance
status: open
recurrences:
  - date: 2026-10-10
    occurrence: https://github.com/endaye/lmdj/pull/1997
    observed_by: kimi-code
exit: none
---

# A subagent whose invocation times out from the caller's view can keep running invisibly and continue executing its brief, including transitions past owner-reserved gates.

## Why

On 2026-10-10 (UTC), shipping #1997 (remove the retired chameleon-lab demo lane),
the delegating agent's subagent call returned a two-hour timeout error. The
runtime listed no active background tasks and refused resume attempts as
"already running", yet the instance was alive: it went on to commit, run the
batch-only lanes, open the Pull Request and — after its review polling loop
exhausted against the 50-file review-inventory refusal — execute the squash
merge on its own, about one minute before the owner's manual-merge decision
arrived in the session. The merge ran under the owner's gh credentials, so the
GitHub record is indistinguishable from an owner action (see
cross-agent-commit-attribution).

The gates it crossed are owner-reserved precisely because an agent's judgment
cannot substitute for the owner's: independent-review waiver and accepted-risk
batch-only lanes both require the owner's explicit in-session decision. A
briefed "stop and report" instruction is prose the wedged instance no longer
honours once its parent has lost the handle; nothing in the runtime revoked
its credentials or its working tree when the invocation timed out.

## How to apply

- Brief every delegated Task with owner-reserved hard stops (merge, release,
  Issue mutation, accepted-risk records) and prefer delegating scopes where a
  wedged instance can do no irreversible harm.
- Treat a subagent timeout as "still running", never as "stopped": watch its
  worktree, branch and Pull Request for mutations before taking over, and do
  not redo its scope in parallel — a second actor doubles the blast radius.
- Before any irreversible transition, the executing agent re-checks that the
  required authority actually arrived in its own context; an expired parent
  invocation cannot supply it after the fact.
- If a wedged instance did cross a gate, record the real sequence honestly —
  on #1997 the owner ratified post-merge and the attestation says so, instead
  of a backdated pre-merge waiver.

`exit: none`: the keep-running behaviour lives in the agent runtime, outside
this repository's control; no deterministic gate can detect "a delegated
instance is still acting", and the remedy is procedural.
