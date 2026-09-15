---
id: emsdk-node-prepend-shadows-repo-node-guard
area: ci-release
status: open
recurrences:
  - date: 2026-09-15
    occurrence: https://github.com/endaye/lmdj/pull/1306
    observed_by: Kimi Code
exit: none
---

# The emsdk-bundled Node prepend in Web proof scripts shadows the repository Node guard, and a Node major bump must sweep every `activate_toolchain`

## Why

emsdk pins its own Node (`node/22.16.0_64bit` at emsdk 6.0.5) and exports it
as `EMSDK_NODE`. The Web proof scripts (`scripts/web-runtime-host.sh`,
`scripts/creator-web.sh`, `scripts/web-toolchain-conformance.sh`) used to
prepend that directory to `PATH` unconditionally, so `node` inside the lane
was always the toolchain Node, never the repository-pinned one. Two failures
hide behind that:

- **The guard becomes tautological.** Before the Node 26 unification the
  guard asked for 22 and the prepend supplied 22.16, so the check could never
  fail and never described the environment.
- **A bump breaks every lane at once.** #1306 raised the guard to 26 but kept
  the unconditional prepend, so the prepended 22.16 made the guard exit 2 on
  every invocation — locally and in CI. Nothing noticed because ordinary PR
  lanes are scope-selected and no run executed a Web lane between the bump
  and the discovery; the last green Web lane predated the bump and ran under
  Node 22 declarations.

#1306 also missed one guard entirely: `web-toolchain-conformance.sh` still
asked for Node 22 after the unification, so that lane verified the toolchain
under the old major while every sibling lane demanded 26.

## How to apply

After any repository Node major bump, or any emsdk bump (its bundled Node
major moves independently), grep for every `activate_toolchain` and every
`Node .. is required` guard under `scripts/` — there is more than one, and
they are not colocated. The prepend must stay conditional (only when no
`node` is already on `PATH`); the lane's real Node comes from the
environment (`.node-version`, setup-node), and `EMSDK_NODE` remains for
Emscripten's own use (`CMAKE_CROSSCOMPILING_EMULATOR`), not for shadowing
the lane.

Changing one of the three scripts selects its owning lane via
`scripts/ci/scope_policy.json` exact rules, so a PR touching all three runs
`web_toolchain`, `web_runtime_host` and `creator` — that run is the gate
that catches this class; a green run of anything else says nothing.

## Why there is no exit yet

The conditional prepend makes the shadowing impossible, but nothing fails
when a *fourth* script grows an unconditional prepend or a stale guard.
A mechanical lint (forbid `PATH="$(dirname "$EMSDK_NODE"):$PATH"` without
the `command -v node` precondition) would close it; until someone adds that
gate, the entry stays open as the checklist for the next bump.
