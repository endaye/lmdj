---
id: operator-only-deploy-script-faults
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-02
    occurrence: https://github.com/endaye/lmdj/pull/520
    observed_by: claude-fable-5-1
exit: gate:tests/build/web_runtime_deploy_workflow_test.py
---

# The deploy scripts' documented local `verify` step could not run on an operator machine at all, because three faults are invisible on GitHub runners and only fire off-runner.

## Why

Both deployment runbooks require a read-only local `verify` before any
`workflow_dispatch`. That step was unreachable on macOS for three independent
reasons, each of which a hosted Linux runner masks:

1. `with_gh_environment_removed` expands `"${unset_arguments[@]}"` on a
   possibly empty array. macOS ships bash 3.2, where that is an unbound
   variable under `set -u`. Runners always export `GITHUB_*`, which matches
   `GH*`, so the array is never empty there.
2. The same loop appended with `[[ test ]] && array+=(...)`. When the test
   fails the list returns non-zero, which `set -e` treats as fatal. Again, a
   runner's `GITHUB_*` names keep the test succeeding.
3. The GnuPG home lived under the owned temp directory, and a GnuPG home holds
   the agent socket. `<macOS TMPDIR>/lmdj-*-deploy.XXXXXX/gnupg/S.gpg-agent`
   is 105 characters against a `sun_path` limit of about 104, so `gpg` failed
   to connect to the agent and exited non-zero on a public-key import that had
   already succeeded (`imported: 1`). Linux runners use a short `/tmp`.

The first two produced `canonical origin remote is unavailable`, which points
at the network. The third produced `trusted Product signing key import failed`,
which points at the key. All three messages named a plausible wrong cause, and
each fault only appeared after the previous one was fixed. The class is the
same never-exercised-path family as [[release-authority-fetch-credentials]] and
[[github-draft-html-url-rewrite]]: CI green is not evidence that an
operator-facing path runs.

## How to apply

Any helper meant to run both on a runner and on an operator machine must be
exercised by a test that supplies an environment with **no** `GH*` variable, on
bash 3.2 semantics, under `set -euo pipefail`. Guard every possibly empty array
expansion as `${a[@]+"${a[@]}"}` and never append with a bare `&&` list under
`set -e`. Treat a GnuPG home as path-length constrained and bound its parent
before use. When a deploy script reports a network or key failure that its
suppressed `2>/dev/null` hides, re-run the failing command with stderr visible
before believing the message.
