---
id: stale-node-modules-masks-broken-lockfile
area: ci-release
status: open
recurrences:
  - date: 2026-09-09
    occurrence: https://github.com/endaye/lmdj/issues/1053
    observed_by: Claude Code (Opus 5)
exit: none
---

# An existing checkout's `node_modules` can be older than the committed lockfile, so a green local build says nothing about whether a clean install builds

## Why

`npm ci` is the only step that makes the installed tree equal the committed
lockfile. Nothing else does — not `npm test`, not a Vite build, not
`scripts/creator-web.sh build`. A checkout that was installed before a
dependency bump keeps serving the old packages afterwards, and every local
command stays green on packages the repository no longer declares.

`require_dependencies` in `scripts/creator-web.sh` does run `npm ls`, which
*does* report the mismatch — but it reports it as an `ELSPROBLEMS` error about
a package name, with no hint that the remedy is a reinstall or that the
declared version has never been built here:

```
npm error code ELSPROBLEMS
npm error invalid: vitest@4.1.10 .../apps/creator-web/node_modules/vitest
```

Reading that as "my working copy drifted, reinstall and carry on" is the trap.
The reinstall is not a cleanup; it is the first time anyone builds what the
lockfile says. In #1053 that first clean install produced three TypeScript
errors and the Creator distribution could not be built at all.

Two conditions have to hold at once, and both are normal here:

- **Ordinary PRs do not run the owning lane.** `.github/workflows/ci.yml`
  declares only a `workflow_call` trigger; lanes run in admitted main batches.
  `scripts/ci/scope_policy.json` *does* map `apps/creator-web/` to lane
  `creator`, so this is not a lane-selection gap — the workflow that would
  consult that policy never ran on the PR. On the bump that caused #1053 the
  only completed checks were review/scope plus a skipped Cloudflare preview.
- **Everyone's checkout is already installed.** So between the merge and the
  next main batch, no human and no agent is running the one command that would
  fail.

## What to do

Before trusting any local evidence about a JavaScript lane, and always after
pulling a branch that changed a `package.json` or `package-lock.json`, run
`npm ci` in each affected prefix and note that you did. A build that follows an
incremental `npm install`, or no install at all, is evidence about your
machine's history, not about the commit.

When a bump does break the build, the fix is the patch release on the line that
builds, not a revert and not a lowered check. #1053's advisory
(`GHSA-82fw-gwwq-j7x9`) was patched in `4.1.11` as well as in `5.0.0`; reverting
to `4.1.10` would have restored the vulnerability, and adding `skipLibCheck` to
silence the third-party declarations would have retired the check for every
dependency at once.

## What this entry cannot tell you

It does not say a clean install is *sufficient*. It reproduces what the
lockfile declares on the machine doing the install, which still differs from a
runner by platform, by optional dependencies, and — as
https://github.com/endaye/lmdj/issues/1056 shows for `scripts/creator-web.sh`
— by which `node` ends up first on `PATH`.
