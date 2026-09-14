# PR-Agent Flash bundle inventory and bounded acceptance

Date: 2026-09-11 (Asia/Shanghai)

## Scope and exact files

This Task binds the already accepted, immutable Flash bundle to the inactive
Netcup operator inventory and records bounded environment evidence. Its exact
five repository paths are:

1. `scripts/ci/pr-agent/netcup-review.json`
2. `tests/build/ci_pr_agent_runner_test.py`
3. `docs/plans/2026-09-11-pr-agent-flash-bundle-inventory.md`
4. `docs/quality/2026-09-10-pr-agent-netcup-operations.md`
5. `apps/docs-site/docs/operations/testing-and-proof.mdx`

The initially named `docs/portal/...` path does not exist; the fifth path is
the repository's current Portal source. Versioned Portal copies are not in
scope. No builder, adapter, default config, installer, dependency, provider,
credential, CI trigger, publisher, budget, host, Docker, GitHub, service,
release, deployment, cutover or provider/account input is changed.

## Accepted immutable input

The archive build source is candidate
`f4f6ebf64eca70b3c5cc17267e61ece7e529c05f`. Separately, PR #1198 source head
`8952cdc98fd67d50341f728b0562c96563737432`, merged as
`374793290e881389bf2513ab23873d8647aca5ad`, is the accepted installer source
and synthetic systemd-test provenance; the installer is not inside this
archive. The current Flash archive is
`lmdj-pr-agent-linux-amd64-53072488e4c3b5a6c9ae730fe6fb52fc5f09d06c.tar`,
`361830400` bytes, SHA-256
`d43d11d489a879e8935b8a70d75665d311db3739f4c1c6907f159c6dcfcc6991`.
Its detached `DEPLOYMENT_IDENTITY.json` is `896` bytes, SHA-256
`0a04de3496b1519ba2b2d3276ce1d3b65c1cdafe9c282a2e1613dd3cbb8c67cd`.
The five detached members remain bound to their actual identities in the
trusted inventory. The artifact directory is
`/tmp/lmdj-pr-agent-packaging/artifacts-v15-flash.mjwNyB`; the repository does
not contain a copy. Lead artifact acceptance already passed from static
independent checks plus inspection of the author-owned clean-base execution.
The supplemental archive verifier is author-owned evidence, not independently
executed reviewer acceptance. Corrected builder stdout/stderr logs and
exported full envelopes are under
`/tmp/lmdj-pr-agent-packaging/artifacts-v15-flash.mjwNyB/`; the retained build
report is `/tmp/lmdj-pr-agent-plan/post-funding-bundle-build.md`.

Superseded v14 compatibility evidence remains historical: archive SHA-256
`4359addd2521847509b61c655a346e1a59e49ebec87934024f35c066eb3f26d3`,
`361820160` bytes; detached identity SHA-256
`a1f7f67b6ae9390a3a4117f0bf1bb96a7269306aef5b12433d06b6e62dc3d2c3`,
`896` bytes. It is not the current v15 operator candidate.

The committed inventory remains inactive, all admission flags are false, the
runtime path has null identity, and the default configuration has all four
providers disabled. The prior v14 archive lane and its evidence remain
historical compatibility evidence and are not relabeled as this candidate.

## Defects and minimum tests

The stale inventory identities could name different bytes than the accepted
Flash adapter/config. Updating only the archive, detached identity and five
member identities in the JSON, then asserting their exact shape and safe
inactive/admission/null-runtime invariants in the deterministic runner suite,
catches stale or hand-guessed identity, accidental activation, provider enable,
and schema drift.

The prior opt-in lane did not exercise the accepted bytes. A separate
`PR_AGENT_RUN_CURRENT_DEPLOYMENT_TEST=1` lane, with
`PR_AGENT_CURRENT_ARCHIVE`, compares the provided archive and detached identity
to the committed trusted inventory before install, fails when either is absent
or wrong, checks the release/current pointer and revision record, checks the
active unit's fixed optional EnvironmentFile and four blocked environment
names, and separately stages the inactive unit with `ExecStart=/usr/bin/false`.
The existing v14 test body and its explicit unavailable-artifact skip remain
unchanged. Ordinary tests run without either opt-in; the bounded extended run
enables both v14 and current lanes with their exact artifacts.

The old operations and Portal documentation could present v14 bytes as current
or overstate a synthetic systemd check. They now bind the Flash identities,
record separate archive-build versus installer/test provenance, preserve
historical failures and v14 evidence, and summarize both accepted synthetic
EnvironmentFile legs from
`/tmp/lmdj-pr-agent-plan/service-env-systemd-acceptance-receipt.md`. That
receipt proves the present leg reached the selected public marker with UID/GID
984/976 and all four blocked names absent; the optional-file-missing leg had a
successful process, selected variable absent, all four blocked names absent,
empty stderr and exact terminal properties. Both used unique temporary
EnvironmentFile/slice/probe paths, a no-adapter probe, PrivateNetwork=yes and
RemainAfterExit=yes. It does not prove production activation,
credentials/authentication, provider health/quality, measured
capacity/coexistence, restart/crash/ledger recovery, route/cutover or T4.
Supplier balance/funding attestation is withdrawn; USD1 per attempt, USD20
pilot/month, actual authentication/model/route/pricing, and all-four-provider
health/fallback/quality remain later gates. Kimi's no-call restriction and
Issues #1149/#1153/#1154/#1155/#1188 remain unchanged.

## Verification and evidence boundary

The bounded checks are local source/inventory tests only. Run the complete
ordinary `ci_pr_agent_runner_test.py` suite, then the complete suite with both
historical-v14 and current opt-ins and exact available archives. Run the
canonical change-scope/source checks for this five-path diff, documentation
impact checks, and `scripts/docs-site.sh check` with locked Portal dependencies
when available. Preserve actual command initial/poll/final tool envelopes and
stdout/stderr outside the repository; report process exits, warnings, skips,
and discovered-versus-executed counts. No full CI, host mutation, systemd
activation, provider request, credential authentication, deployment, release,
or T4/T5/T6 acceptance is implied.

## Version Management

Version impact: none. This Task changes only operational bundle identity,
tests, and documentation; it changes no Product Build, Core Module, Provider,
Contract, or product identity.

## Documentation impact

Documentation impact: required. Affected Portal route:
`/operations/testing-and-proof/`. The current source is
`apps/docs-site/docs/operations/testing-and-proof.mdx`; historical versioned
Portal copies are immutable and are not edited by this Task.
