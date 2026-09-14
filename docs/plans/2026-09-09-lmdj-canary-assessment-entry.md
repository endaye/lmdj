# T2h — Manual authenticated assessment workflow

Part of the result-driven delivery plan; source implementation locally verified.
Live activation and end-to-end platform acceptance remain unclaimed.

## Declared files

- `.github/workflows/canary-assessment.yml`
- `.github/actionlint.yaml` (declare the new dedicated routing label)
- `scripts/ci/batch_runtime.py`
- `scripts/ci/scope_policy.json` (exact ownership of the new workflow)
- `tools/canary/assessment_entry.py`
- `tools/canary/executor_policy.json`
- `tests/build/ci_canary_assessment_entry_test.py`
- `docs/plans/2026-09-09-lmdj-canary-assessment-entry.md`
- `docs/plans/2026-09-09-lmdj-result-driven-delivery.md`
- `apps/docs-site/docs/operations/version-and-release.mdx`

Connect manual init/claim/settle/report to the real authenticated Runtime,
assessment Journal, bounded process executor, exact artifact handoff and durable
outbox. The existing scheduler workflow remains unchanged. Allow a trusted
Runtime subclass to bind its own fixed workflow/job identity without broadening
the production scheduler's accepted source or configuration schema.

Use separate assessment and assessment-report Issues, never the production
scheduler/outbox. Explicit initialization handles one reserved empty Issue per
invocation. No automatic initialization or Issue creation. Claim an explicit
main-history interval once, upload complete input as an artifact and release
the short writer lock before the model job starts. The executor checks its
exact run/attempt/control and recollects complete Git input. It uses only
root-owned preinstalled binaries matching reviewed SHA-256 pins and private
verified copies, with only the existing explicitly supplied coding credentials.
Unknown/missing binaries fail their backend; never run an unverified fallback.

The producer retains a valid blocked assessment as well as successful advice.
A separate visibility job marks blocked advice red without destroying the
producer's successful artifact receipt. A subsequent fresh manual settle/report
observes the original terminal run; it never reruns a model, resets its claim,
automatically repairs/closes an Issue or admits metadata/deployment.

The manual workflow has no push, schedule or completion trigger. Execution is
off unless `CANARY_ASSESSMENT_EXECUTION_READY=true` and uses the dedicated
`lmdj-ai-isolated` runner label and `canary-assessment` Environment. Labels and
the variable are routing assertions, not OS-isolation proof. An operator must
accept a dedicated disposable VM/microVM boundary, absence of other job or
deployment credentials, protected Environment and binary provisioning before
enabling it. No such infrastructure change or live model call is authorized by
this source-only Task. Automatic result-driven coordination remains later work.

## Verification

Red missing-entry test, then actual temporary Git/Runtime/Journal fixtures for
fresh claim → serialized input → process execution → uploaded result → terminal
settle → fresh-process replay/report. Preserve actual API identity and unknown
POST reconciliation coverage from T2g. Check rejected mixed/malformed inputs,
reserved storage aliases, disabled execution before any claim, wrong head/run/
attempt, mutated input, binary digest/ownership/mode refusal, isolated explicit
credentials and no model execution during recovery. Inspect parsed workflow
permissions, triggers, lock boundaries, upload names and blocked visibility.

Run complete canary and CI-contract discovery, staged/committed ownership,
version verification, Portal check, exact-head PR review and squash inventory.
Local fixtures do not prove live runner isolation, provisioning, storage setup,
model acceptance, automatic recovery or delivery; keep these gaps explicit.

Local evidence (2026-09-09): missing module import failed before implementation;
25 focused entry tests, 235 complete canary tests and 2100 CI-contract tests
passed with the pinned actionlint available (no optional parser skip).
The focused workflow also passed actionlint 1.7.12 with explicit ShellCheck
0.9.0; only the existing exact `concurrency.queue` schema-lag exception applies.
Full Portal check passed 112 tests and all 44 routes/internal links after the
fresh worktree's locked dependencies were installed. Version tests and active
version verification passed. The staged-index ownership check caught the new
workflow's missing exact rule; its CI-contract mapping and regression are now
included, with all 66 ownership tests passing. Existing paths and lane routing
remain unchanged.

The fixtures exercise complete serialized claim → actual bounded child process
→ exact producer artifact → fresh Runtime/Journal settlement → separate real
Journal outbox → business receipt and replay. They also exercise blocked
credentials, rejected upload, lost claim/complete acknowledgements and unknown
business POST recovery without model or POST replay. A fresh OS process reloads
the complete simulated remote journals and recovers the original business
receipt without any parent cache, result ZIP, model invocation or POST.
Root ownership is tested
as metadata refusal separately from the native-byte copy/process fixture; no
synthetic ownership override is described as live isolation or provider proof.
No qualifying new process pitfall: the local test-discovery module-identity
failure was corrected in fixture import ordering, without changing production
error handling or weakening the existing recovery assertions.

## Version Management

Version impact: none
Reason: workflow/tooling only; no Product/Host/Module/Assembly identity,
allocation, snapshot, tag, release or Channel change.

## Documentation Impact

Documentation impact: required
Affected portal pages: /operations/version-and-release
Reason: document manual assessment commands, readiness prerequisites and the
separate post-run settlement/report boundary. Product architecture and source
diagrams are unchanged.

## Binary provenance

Claude Code native Linux x64 `2.1.265`: publisher manifest at
`https://storage.googleapis.com/claude-code-dist-86c565f3-f756-42ad-8dfa-d59b1c096819/claude-code-releases/2.1.265/manifest.json`,
SHA-256 `e14738e3a58d1fc6ccc23b9c919451b4846bc27074a3fb48db976a7d595bdeeb`,
also matched against the installed native binary, without a model invocation.
Grok Linux x86_64 `1.0.13` reuses the independently verified existing PR-review
pin. The workflow does not download or install either binary, discover ambient
auth, use an Anthropic billing key or add a Grok API billing fallback.
