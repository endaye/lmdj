# T4 service-scoped provider environment

Status: source implementation and correction verification complete; fresh
independent exact-head review, synthetic Linux systemd and live service
verification pending. Parent: #1153 / umbrella #1149.
Starting main: `a22dae478fba4e53ba9a5467dc1b9afe775c51e1`, including installer
PR #1191 at `3a8bf89518f556a4efc393b32de7a8095637fe79`. The prepared checkout
was fast-forwarded before implementation; the intervening Cardputer Task has
no overlap with this Task's declared files.

## Outcome and boundary

Use the existing approved `PR_AGENT_*_API_KEY` environment interface in the
dedicated PR-Agent systemd service. The owner chose this existing interface,
not a custom secret provisioning, TTY, encryption or balance subsystem.
Proactive supplier funding/quota management was withdrawn from this migration
wave; warning #1188 remains deferred. Existing USD, request, timeout, pricing,
identity, four-provider, quality and host acceptance requirements are retained.

This bounded source Task adds the ordinary service environment-file reference
and its regression/operations documentation. It creates no real secret file,
makes no host or provider call, and grants no production activation. Lead owns
specification/plan/acceptance; Luna owns implementation/tests and one commit.

## Declared files

- `scripts/ci/pr-agent/deploy-runner.sh`
- `tests/build/ci_pr_agent_runner_test.py`
- `docs/plans/2026-09-11-pr-agent-service-environment.md`
- `docs/quality/2026-09-10-pr-agent-netcup-operations.md`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`

No adapter, ledger, default model, dependency, workflow, inventory schema,
transport, secret writer, balance query or warning-feature change. Do not alter
the already merged installer history/durability contracts to accommodate this
one unit directive. No additional required CI check or changed threshold.

## Service contract

The generated unit declares exactly:

```ini
EnvironmentFile=-/etc/lmdj/pr-agent/provider.env
```

The path is fixed and outside the repository, archive and immutable revisions.
No variable value is interpolated into the generated unit. The optional-file
prefix preserves no-key inactive staging. An active attempt with a missing
selected key still fails through the existing adapter boundary; environment
presence never enables a disabled provider or establishes pricing/admission.

The operator, outside this source Task, owns the file: root:root, mode 0600,
regular non-symlink file below protected root-owned parents. It contains only
the approved provider variable names needed by the selected reviewed config.
The installer never reads, copies, hashes, logs, archives, creates or repairs
that file or its values. No new custom file parser/allowlist is implemented;
the approved-content restriction is an operator responsibility. In particular,
the file must not override Python/tooling environment or carry GitHub tokens.

Preserve every existing `UnsetEnvironment` name. systemd applies those removals
after environment-file assignments. Do not add manager-global environment,
`PassEnvironment`, shared-runner credential inheritance, inline secret-valued
`Environment=` directives or a custom credential producer/loader.

The existing immutable deployment revision binds the changed installer and
unit bytes. New installs use the new unit; rollback restores exact historical
unit bytes, including an older unit without this directive. Do not rerender,
rewrite or retrofit retained historical revisions or deployment receipts.

## Source verification and commit boundary

1. A focused unit contract checks the exact fixed directive, preserved blocked
   credential names and unchanged inactive fail-closed command.
2. A real local installer fixture with a synthetic provider environment value
   proves no such value enters generated unit/state/record/receipt/archive
   outputs. A no-key inactive stage still succeeds without fabricating active
   admissions. These are local byte/noncopy proofs, not systemd execution.
3. Preserve all existing positive and refusal cases, including the complete
   six-leg same-archive journey, current and previous fixed byte oracles,
   pending crash/retry, distinct-path rollback and renderer drift. Explicitly
   exercise old-unit-to-new-unit install and historical rollback with both
   expectations declared independently before effects; agreement among output
   copies is not the unit contract oracle.
4. Run the complete runner matrix: ordinary, outer `python3 -B -S`, caller
   umask 0002, installer child forced through the existing no-site wrapper, and
   explicit pinned-v14 archive test with zero skips. Retain default skip counts
   separately from that explicit archive lane. Run adapter/scope suites and
   `bash -n scripts/ci/pr-agent/deploy-runner.sh`.
5. Run `npm ci` in the portal and `bash scripts/docs-site.sh check` to actual
   successful completion before commit. A missing dependency is a repairable
   prerequisite, not permission to omit a declared gate. Keep dependency and
   build warnings visible; do not upgrade dependencies in this Task.
6. Inspect exact staged files and whitespace; commit the five-file Task only
   after verification succeeds, then verify committed inventory/clean status
   and exact-head portal facts. Retain literal stdout/stderr, every actual
   process exit and exact pass/skip counts. A shell pipeline's final command
   exit or an empty poll is not the test process's exit.
7. A fresh distinct complete exact-head independent review is required before
   push. Lead acceptance and ordinary guarded shipping follow that review.

## Separate Linux service acceptance

After source acceptance, the lead must separately verify a synthetic-only
Linux systemd service using the intended service-scoped file behavior. Prove
the synthetic provider value reaches the service without printing it, a
synthetic GitHub write-token assignment in that same file is removed, missing
file behavior is compatible with inactive/no-key execution, and no unrelated
service or manager environment is changed. Record exact service/host identity,
exit status and nonsecret far-side assertions. Temporary test resources need
exact ownership and recoverable cleanup accounting. This is not permission for
the implementation worker to create services or modify the live target.

Before actual credentials or real provider requests, verify protected file and
parent metadata without reading values into logs/tool output, the selected
candidate/config identity, isolation, capacity and existing spend admission.
At the earlier lead 2026-09-11 read-only checkpoint, the shell had no DeepSeek
key and the fixed file was absent on Netcup. The operator subsequently asked
where to configure it and received the fixed path, root:root 0600 instructions
and an explicit instruction not to start or restart the service yet. A later
lead metadata-only refresh observed that the fixed `/etc/lmdj/pr-agent/provider.env`
is a regular non-symlink file, `root:root`, mode `0600`, below protected
root-owned `0755` parents; its receipt is
`/tmp/lmdj-pr-agent-plan/t4-provider-file-metadata-2026-09-11.md`. This
metadata-only observation proves no file content, usable key, authentication,
provider response or service activation.
Neither GitHub Secret metadata nor a preflight step proves systemd received a
key. Never claim the source Task completes T4, T5 or T6.

## Security and upstream basis

Environment variables are not a secret-isolation primitive. Root and the
service can access values and child processes may inherit them; do not claim
absence from process memory, proc/debug interfaces or all IPC surfaces. Avoid
environment dumps, full unit-property dumps and shell tracing in evidence.

The design uses standard systemd v255 `EnvironmentFile` optional-file/read
timing and final `UnsetEnvironment` semantics. This is a design inference from
[the upstream execution contract](https://github.com/systemd/systemd/blob/v255/man/systemd.exec.xml),
not an upstream endorsement of environment variables for secrets.

## Version Management

Version impact: none
Reason: no Product Build, Module, Host, Provider or public Contract identity
changes. Installer/unit bytes produce a new ordinary deployment revision;
historical revisions and bundle identities remain immutable. The separate
adapter change still requires a new verified Linux bundle before real use.

## Documentation Impact

Documentation impact: required
Affected portal pages: /operations/testing-and-proof/
Reason: document the service-scoped provider environment entrance and the
separate source, synthetic service and real-key acceptance boundaries.

## Implementation receipt

Original implementation receipt (pre-correction) status: source implementation
complete; fresh independent exact-head review, synthetic Linux systemd
acceptance and real host/provider acceptance remain pending. Prepared base and
source HEAD before the Task were both
`a22dae478fba4e53ba9a5467dc1b9afe775c51e1`; the final committed HEAD and
complete command receipts are recorded in
`/tmp/lmdj-pr-agent-plan/service-environment-implementation.md`.

The renderer now emits exactly the fixed optional
`EnvironmentFile=-/etc/lmdj/pr-agent/provider.env` directive while preserving
all blocked GitHub environment names and the inactive `/usr/bin/false`
fail-closed command. The contract suite adds a synthetic provider-value
noncopy proof, no-key inactive stage proof, and an independently prepared
current/old unit oracle that installs a new unit and rolls back to retained
historical unit bytes lacking the directive; no provider file is read or
created. Operations and Portal guidance now record prior funding/balance
preflight observations as historical and document the operator-owned
`root:root` `0600` regular non-symlink file boundary without a service-start
instruction.

The original pre-commit verification receipts (all exit 0) remain preserved at
the raw paths listed in the implementation report: ordinary runner, outer
`python3 -B -S`,
caller `umask 0002`, installer-child no-site wrapper, pinned-v14 runner with
zero skips, adapter, change-scope, scope-policy parity, shell syntax, locked
portal `npm ci`, and complete `scripts/docs-site.sh check`. Runner lanes report
95 tests / 94 passed / 1 explicit v14 skip by default, and 95/95 with zero
skips for the pinned-v14 lane. These are source and local byte/noncopy proofs;
they do not establish Linux systemd behavior, real credentials/provider calls,
capacity, cutover or handoff acceptance.

The F1-F6 correction receipt is maintained outside the repository at
`/tmp/lmdj-pr-agent-plan/service-environment-f1-f6-correction.md`; it records
the corrected exact HEAD/base, each disposition, complete command exits and
raw stdout/stderr paths. The original implementation report and raw logs are
historical evidence and are not rewritten.
