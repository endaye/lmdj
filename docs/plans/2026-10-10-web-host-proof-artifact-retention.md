# Retain every Web Runtime Host proof invocation's artifacts

## Outcome and authority

Preserve Chromium failure evidence when the Host proof subsequently runs
WebKit. This is a diagnostic prerequisite for the Creator Desktop Final
follow-up Goal's acceptance failures; it does not accept those failures.
The existing Goal authorizes implementation, commit, push, PR, review and merge.
No release, deployment or remote cleanup is included.

## Refreshed premises

Initial inspection: `50d79fa894f3483d6593d50fafcfd3e1bff28ce0`.
Refreshed Task base: `864c0f061033a7f0c3488f1908a8817516cd3b62`.

- Still outstanding: all three Playwright invocations in
  `scripts/web-runtime-host.sh` omit `LMDJ_WEB_RESULTS_SLOT`. The shared config
  maps them to `test-results/default`; Playwright clears outputDir per run.
  Producer PR #1910's failed Chromium traces were overwritten by WebKit.
- Available positive control: Creator already supplies separate slots, and
  the shared production config maps those to distinct output directories.
- Available retention: the CI action uploads the entire
  `tests/platform/web/test-results` tree; distinct child directories require
  no workflow or upload change.
- No successor delivery: monitoring #1910 and fixture #1915 are now merged,
  alongside unrelated Creator layout and provider/Portal work. None changes
  the operator, PackageTest or shared outputDir configuration. The current
  Host invocations still use the shared default slot.

## Task and declared files

One Task, one Conventional Commit:

- `scripts/web-runtime-host.sh`: distinct slots for AudioWorklet conformance,
  packaged Chromium and packaged WebKit. Preserve the selected specs,
  deadlines, failure aggregation and owned-server lifecycle.
- `apps/web-runtime-host/test/package_test.py`: execute the real operator
  functions, locked Playwright CLI and production outputDir configuration.
  Use a browser-free spec that writes evidence, fails Chromium, then passes
  WebKit; assert all three invocations' bytes survive and the gate stays red.
- `apps/docs-site/docs/operations/testing-and-proof.mdx`: document the output
  slots and existing upload tree.
- `.agents/pitfalls/playwright-output-dir-overwrites-prior-invocation.md`:
  retain the external runner cleanup rule and its executable regression exit.
- This plan: record scope and actual verification.

## Verification

First run the regression against the unchanged operator and inspect its
missing-evidence assertion. Then add slots and run the complete PackageTest
suite, Host source-boundary suite, Web proof server contract suite, shell
syntax check and Portal check. Before commit, stage only declared files and
run the new-file ownership suite and staged diff check.

The regression invokes real Playwright workers and directory cleanup, but
does not launch browsers or exercise Wasm/audio: its oracle is retained file
bytes after all invocations, independent of comparing slot-name inventories.
The harness substitutes only audio fixture compilation with an empty owned
server root; real owned servers, health checks and runner invocation remain.
Full Host/browser acceptance is separate and must retain its actual outcome.
Run every selected batch-only lane on the committed inputs before merging.

### Precommit evidence

The unchanged operator failed the new regression at the retained Chromium-file
assertion: zero files after the passing WebKit invocation. The locked runner
created a Chromium trace before that later invocation. With separate slots,
the complete PackageTest suite passed (15 tests, 17.037 s), including the
original failed trace's SHA-256 after WebKit. The Host source-boundary check,
all five Web proof server contracts and shell syntax check passed. After
installing this isolated worktree's locked Portal dependencies, the complete
Portal check passed, including 50 routes and internal links.
These results verify retention; they do not claim complete Host acceptance.

### Review follow-up

Automatic review `37964799072/1` inspected the complete initial head. Its
fixture suggestions are addressed by parsing both project-flag spellings with
argparse and moving the generated harness into its TemporaryDirectory. Bind
only the harness's repository lookup to the inspected worktree, preserving
the real operator functions. The original `--project=chromium` argv element
already worked; robust parsing also admits the runner's spaced spelling.
The first complete Host run stopped at missing command-local toolchain PATH;
the correctly activated run was then interrupted to apply these review fixes.
Neither is passing batch evidence. Retain both logs and rerun the complete
lane on the amended committed inputs.

## Version Management

Version impact: none — operator diagnostics and tests only; product audio,
Host operations, persisted Contracts and active version identities are unchanged.

## Documentation impact

Documentation impact: required
Affected portal pages: /operations/testing-and-proof
Reason: document the corrected proof artifact retention behavior.

2026-10-10 local / 2026-10-09 UTC verification refresh: the complete Host lane
on `c0621e1afd35f5e2e00d4b61b68755e57f17557f` passed (1,155.6 s): real
AudioWorklet 29/29, native Host 3/3, Chromium 41 pass / 1 skip and WebKit
2 pass / 15 skip. Its retained batch key is
`11c295c8d9002e7268d142dddfd112ef464d7d8698a2b3cd94ae5d537e4b5237`.
This does not establish the cause of the earlier Candidate failures. CI Contract
`37967196394/1` failed only the ledger date check: the newly recorded recurrence
used the local calendar day, which was ahead of UTC. Use the actual observation
date 2026-10-09 UTC and run `python3 tests/build/ci_pitfall_ledger_test.py`;
retain the failed run and obtain a new exact-head review after amendment.
