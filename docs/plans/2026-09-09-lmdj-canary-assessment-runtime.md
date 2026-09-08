# T2d — Bounded assessment process execution

Part of the [result-driven delivery plan](2026-09-09-lmdj-result-driven-delivery.md).

## Declared files

- `tools/canary/assessment_runtime.py`
- `tests/build/ci_canary_assessment_runtime_test.py`
- This plan.
- `docs/plans/2026-09-09-lmdj-result-driven-delivery.md` (progress/evidence only).

Implement an internal callable execution adapter for the existing assessment
protocol. Trusted callers supply exact installed executable paths, requested
model identifiers and only explicit credential values. Never discover ambient
user credentials or install a CLI. GLM and Kimi use Claude Code against their
existing coding endpoints; Grok uses Grok Build. A fresh private directory per
attempt holds complete prompt input and ephemeral CLI config/auth. Child
environment is constructed, not inherited. No repository checkout is exposed
as cwd. Model tools are disabled/denied; no candidate code is run.

Use real POSIX process-group deadlines (300 seconds each), bounded combined
stdout/stderr, cleanup on success/failure/interruption, finite sanitized
diagnostics and strict CLI-envelope/output validation. Never execute advice.
Stop at first valid assessment, including compatibility uncertainty; all failed
attempts retain the existing stable Issue intent. A requested model alias is
not an attestation of the provider's resolved model.

This is not an OS sandbox: a trusted CLI and system-managed configuration still
run with the caller's OS identity. Activation requires a credential-isolated
execution environment and real provider acceptance. This Task adds no workflow
or supported operator command, Issue POST, version write, candidate allocation,
signing, release or deployment. Durable outbox integration, interruption replay,
authenticated input collection and complete version PR preparation remain
required before automatic use. No automatic API-key billing fallback is added
for Grok; only the existing explicitly supplied Build auth is used.

## Verification

Missing-module red, then real disposable process tests: stdin input, isolated
cwd/environment, bounded stdout/stderr, nonzero exit, timeout, descendants,
invalid envelopes, unavailable binaries/credentials, exact fallback order,
major/unknown stop, secret-safe diagnostics and temporary auth cleanup. Fixture
executables exercise process mechanics, not genuine provider/tool isolation.
Run complete canary/CI discovery, staged ownership, Portal check and final range
and PR declarations. Do not label unexercised provider or Issue legs passed.

CLI behavior references checked September 9, 2026:
[Claude CLI](https://code.claude.com/docs/en/cli-usage),
[Z.AI coding setup](https://docs.z.ai/devpack/tool/claude),
[Kimi coding setup](https://www.kimi.com/code/docs/en/third-party-tools/claude-code.html),
[Grok permissions](https://docs.x.ai/build/features/permissions) and
[Grok configuration](https://docs.x.ai/build/settings).
Claude `--restricted` requires a supporting installation (locally observed
2.1.263); Grok options were inspected on 1.0.13. Unsupported flags fail the
attempt, not trigger an unrestricted invocation.

The local CLI help also explicitly requires API-key authentication in `--bare`
mode: use the selected coding key in `ANTHROPIC_API_KEY` and retain Z.AI's
documented bearer header for GLM. Do not reuse a developer's Anthropic key.
Genuine endpoint/header acceptance still needs the isolated live exercise.

Local verification: 24 runtime tests and 133 canary tests passed. Complete CI
discovery ran 1,976 tests, OK with one optional actionlint semantic check skipped
because `LMDJ_ACTIONLINT` is unavailable. Staged ownership: 66 passed. Portal:
86 tests, 39 source pages, 10 diagram sources/20 outputs and 42 built routes
passed; this was not a snapshot allocation or deployment. The documentation
install reported 27 dependency advisories (9 moderate, 18 high); no dependency
upgrade or claim of a security-clean dependency tree is part of this Task.

## Version Management

Version impact: none
Reason: internal assessment execution; no active identity, manifest, Assembly
or snapshot is allocated or modified.

## Documentation Impact

Documentation impact: none
Reason: unactivated internal adapter only; no supported operator command,
workflow trigger, site or current Portal behavior changes. Document the live
coordinator and failure outbox before enabling it.
