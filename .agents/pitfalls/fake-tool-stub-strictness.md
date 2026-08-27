---
id: fake-tool-stub-strictness
area: ci-release
status: absorbed
recurrences:
  - date: 2026-08-27
    occurrence: https://github.com/endaye/lmdj/issues/349
    observed_by: claude-code/fable-5
exit: gate:apps/web-runtime-host/test/deploy_command_test.py
---

# A fake tool stub that is laxer than the real tool certifies invocations the real tool rejects

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

## How to apply

When a test fakes an external tool, every faked subcommand must reject the
invocations the real tool rejects (arity, required flags, mode conflicts) —
match by exact expected shape, never by command-name prefix. The enforcing
gate here is the hardened fake git in
`apps/web-runtime-host/test/deploy_command_test.py`, which now fails a bare
`cat-file <object>` exactly like real git. Apply the same strictness when
adding new subcommands to any fake tool.
