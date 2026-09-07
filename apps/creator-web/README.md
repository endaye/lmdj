# Creator Web: local build and verification

Run these commands from the repository root. The stable entrypoint is
[`scripts/creator-web.sh`](../../scripts/creator-web.sh); it validates the pinned
Emscripten identity and required tools. Use the checked-in lockfiles for Creator
and `tests/platform/web` dependencies and install the matching Playwright
browsers before browser proof. See the repository [build prerequisites](../../README.md#build)
and [testing and proof guide](../architecture-portal/docs/operations/testing-and-proof.mdx).

## Build, test and serve

```bash
scripts/creator-web.sh build
scripts/creator-web.sh test
```

`build` configures when needed, then builds the shared native Web runtime and
Creator UI. It does **not** assemble the distributable directory. `test` runs
Creator UI tests, package/server/deployment-smoke contracts, shared asset-role
parity and Web Platform Node tests. It does **not** run the packaged browser
journeys; a passing local `test` is not a complete Creator proof.

To inspect the packaged application, first commit the intended source changes:
the Creator packager requires a clean Git source tree so its recorded revision
describes the contents. Then run:

```bash
scripts/creator-web.sh package
scripts/creator-web.sh serve --port 8080
```

`package` requires the preceding build outputs and produces
`build/web/creator/dist`; `serve` requires that packaged directory. After changing
source again, rebuild and package again before inspecting the distribution.

## Complete Host proof and evidence boundary

```bash
scripts/creator-web.sh proof
```

From a clean source tree, `proof` creates real Core project fixtures, checks two
clean build/package outputs for byte reproducibility, runs local tests, and
executes packaged Chromium journeys plus the WebKit capability boundary.
Capability-limited automated cases are not physical device verification.

`scripts/creator-web.sh clean` removes only the validated `build/web/creator`
subtree, not source or another Host's build directory. Proof also rebuilds this
subtree; do not run conflicting local builds against it concurrently.

These are local verification and serving commands, not publication commands.
Their outputs are neither complete-project self-test evidence nor release
authorization. PR merge, complete candidate verification and deployment remain
separate boundaries under the [Git workflow](../../docs/governance/git-workflow.md)
and [Creator deployment guide](../../docs/deploy/creator-web.md). No automatic
CI cutover or release is implied by running them.
