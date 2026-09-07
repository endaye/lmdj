# Web Runtime Host: local build and verification

Run these commands from the repository root. The stable entrypoint is
[`scripts/web-runtime-host.sh`](../../scripts/web-runtime-host.sh); it validates
the pinned Emscripten identity and required tools. Use the checked-in Web test
lockfile and matching Playwright browsers. See the repository
[build prerequisites](../../README.md#build) and
[testing and proof guide](../architecture-portal/docs/operations/testing-and-proof.mdx).

## Build, test and serve

```bash
scripts/web-runtime-host.sh build
scripts/web-runtime-host.sh test
scripts/web-runtime-host.sh serve --port 8080
```

Unlike Creator's separate `package` command, this Host's `build` configures when
needed, builds the native Web runtime, verifies the production source boundary
and packages `build/web/host/dist`. There is no separate `package` subcommand.
Both `test` and `serve` require the built distribution. Rebuild after source
changes before testing or serving it.

`test` runs nonbrowser Python/Node contracts and native Web CTest cases, checks
the distribution, generates browser fixtures, and runs the packaged browser
gate. It therefore needs browser dependencies too; it is not equivalent to
Creator's nonbrowser `test`. Internal shell functions such as
`run_nonbrowser_tests` are not public subcommands.

## Complete Host proof and evidence boundary

```bash
scripts/web-runtime-host.sh proof
```

`proof` additionally runs AudioWorklet conformance, compares two clean builds
for byte reproducibility, and exercises an isolated distribution with packaged
Chromium journeys and WebKit capability checks. Automated capability results do
not establish physical hearing, MIDI or device acceptance.

`scripts/web-runtime-host.sh clean` removes only the validated `build/web/host`
subtree, not source or Creator's build directory. Proof also rebuilds this
subtree; do not run conflicting local builds against it concurrently.

The local server and distribution are development/verification tools, not a
public deployment. A local Host pass is neither complete-project self-test
evidence nor release authorization. PR merge, complete candidate verification
and deployment remain separate boundaries under the
[Git workflow](../../docs/governance/git-workflow.md) and
[Runtime deployment guide](../../docs/deploy/web-runtime-host.md). No automatic
CI cutover or release is implied by these commands.
