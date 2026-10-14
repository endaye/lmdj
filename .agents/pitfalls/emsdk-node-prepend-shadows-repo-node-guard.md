---
id: emsdk-node-prepend-shadows-repo-node-guard
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-15
    occurrence: https://github.com/endaye/lmdj/pull/1306
    observed_by: Kimi Code
  - date: 2026-10-14
    occurrence: https://github.com/endaye/lmdj/pull/1349
    observed_by: Claude Code (Opus 5.5)
exit: gate:tests/platform/web/toolchain/toolchain_identity_test.py
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
they are not colocated. The scripts no longer prepend `EMSDK_NODE` at all:
`emsdk_env.sh` itself adds its bundled Node only when no `node` is on
`PATH`, and that bundled Node cannot satisfy the Node 26 guard, so even a
conditional fallback prepend could only reach the guard's failure. The
lane's real Node comes from the environment (`.node-version`, setup-node),
and `EMSDK_NODE` remains for Emscripten's own use
(`CMAKE_CROSSCOMPILING_EMULATOR`), not for the lane's `node`.

Changing one of the three scripts selects its owning lane via
`scripts/ci/scope_policy.json` exact rules, so a PR touching all three runs
`web_toolchain`, `web_runtime_host` and `creator` — that run is the gate
that catches this class; a green run of anything else says nothing.

## Second occurrence and exit

The Node 26 bump also missed `"node"` in `tools/web-runtime/emscripten.lock.json`,
which the Runtime identity generator projects into
`products/lmdj/generated/web-runtime-identity.*`. #1349 then left it at `22` on
the claim that it recorded the emsdk-bundled Node; the plan that introduced it
(`docs/plans/2026-08-03-lmdj-formal-web-runtime-host.md`, Task 0) defines it
beside Playwright as the Web lane's Node, and nothing compared it. The field
is the lane Node major, never `EMSDK_NODE`.

`tools/web-runtime/verify_emscripten.py`, which every Web lane runs, now fails
when the lock major differs from `.node-version`.
`tests/platform/web/toolchain/toolchain_identity_test.py` binds every
`scripts/*.sh` Node guard to that lock major and rejects any `EMSDK_NODE` use
in those scripts, so a stale guard or a prepend in a further script fails with
`why` and `remedy`.
