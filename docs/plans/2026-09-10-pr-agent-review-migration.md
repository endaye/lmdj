# PR-Agent review migration implementation plan

Date: 2026-09-10
Status: Implementation in progress; per-Task acceptance is recorded in the linked issues.
Umbrella: #1149. Task issues: #1150–#1155.

## Owner scope update — funding checks deferred

On 2026-09-11 the owner removed proactive balance/limit-management and native
funding admission from this wave and will check supplier accounts manually.
This update supersedes conflicting funding-proof prerequisites in the earlier
plan text; historical balance preflight and rejected source evidence are not
rewritten or treated as accepted. Do not run the balance preflight again merely
to satisfy an obsolete gate. The withdrawn native-funding branch is excluded
from the current candidate and its unfinished work is not a migration blocker.

Record actual supplier insufficient-balance/quota/limit failures and notify the
owner without exposing keys or raw account data. Automatic warning is deferred
as [#1188](https://github.com/endaye/lmdj/issues/1188), not a dependency of this
wave. Existing USD 1/20/20 accounting, request/timeout caps, verified pricing,
credential/model identity, four-provider/fallback and quality acceptance,
Netcup isolation, exact-head protection and cutover/handoff remain unchanged.

### Bounded follow-through Task: retire funding attestation activation gate

Status: implemented; declared verification passed before this amendment;
independent exact-head review remains pending. The initial implementation commit
is `4e08436113b39a2327cff0c630279dff0f158685`; postcommit verification repairs
acceptance after the original docs-site check failed before that commit.
Use a fresh isolated `fix/pr-agent-funding-gate` worktree from verified main,
not the withdrawn native-funding worktree. Lead owns this plan and acceptance;
Luna owns implementation/tests in one Conventional Commit.

Declared files:

- `scripts/ci/pr_agent_review.py`
- `tests/build/ci_pr_agent_review_test.py`
- `scripts/ci/pr-agent/config.toml` (inactive explanatory comments)
- `docs/design/2026-09-10-pr-agent-review-migration.md`
- `docs/plans/2026-09-10-pr-agent-review-migration.md`

Remove mandatory `funding_ref`/`funding_verified` from provider enablement and
normalized operational authority. Accept those legacy keys as ignored
compatibility inputs, without changing the config schema or other unknown-key
rejection. New fixtures omit them; explicit legacy true/false compatibility
tests cannot activate a disabled provider or bypass any other retained guard.
Do not invent proof of funds, query balances, add native bookkeeping or implement
the deferred warning. No installer/workflow/dependency/host/secret mutation.

Verification first reproduces the old no-funding-fields rejection with every
other activation input valid. Then prove valid activation without the fields,
ignored legacy inputs, retained negative pricing/credential/model checks, and
an actual pinned-handler fake-HTTP success with no balance GET. Preserve every
existing method/subcase, run ordinary and `-S` adapter tests, the complete shared
integration under `0022` and `0002`, complete change-scope and docs-site checks.
Inspect exact staged/committed paths and clean final head. An independent
complete exact-head review is required before push; no real API is called by
this source Task. Historical failed runs remain separate evidence.

Version impact: none for Product/Module/Contract. Changed internal adapter and
config bytes require a newly verified Linux bundle before deployment; never
relabel the v14 archive. Documentation impact: none, because this Task changes
internal design/plan and inactive configuration, not a current Portal route;
the documentation check remains required by the declared verification.

## Authority and coordination

The user authorized the complete umbrella implementation, task-local commit,
push, PR, independent current-head review and squash merge, plus deployment to
the existing Netcup server. The owner supplied a USD 20 monthly API cap on 2026-09-10. The design records
calendar-month accounting, a USD 20 cumulative first-pilot cap and a USD 1
per-PR cap. Credentials and supplier route eligibility remain unverified;
supplier funding is checked manually and is not an adapter activation gate.
No server purchase, paid hosted fallback, branch-protection change, product
release or unrelated cleanup is authorized.

The lead writes this plan and the [design](../design/2026-09-10-pr-agent-review-migration.md),
coordinates Orca workers, and accepts final evidence. Supervised workers perform
implementation and focused verification; separate workers review exact heads.
The lead selects the model and effort for the Task's difficulty, using high
effort for bounded implementation and xhigh for complex provenance, coverage,
publication or adversarial work. Escalate uncertain choices to the lead, who
asks the user only when authority, credentials, budget or product decisions
cannot be resolved from evidence. Do not expand nested worker fanout.

Create each implementation worktree from fresh main. Use `feat/`, `fix/` or
`docs/` branch names, including renaming Orca's default agent-prefixed branch
before any edit. One Task is one reviewable Conventional Commit; split a Task
before implementation if its independent behaviors require multiple commits.
Read `issue-done` for staging, path ownership, review and exact-head merge.

## Dependencies and file ownership

T1 → T2 → T3; T1 + T2 → T4; T3 + T4 → T5 → T6.
T3 and T4 can run concurrently once interfaces are fixed, in isolated worktrees.
T3 owns review protocol/consumers; T4 owns host deployment/limits. Changes to
shared policy or Portal files must be assigned to one owner and integrated
before another editor begins. Parallel readiness is not permission to write
shared files. No worker changes product source or unrelated control-plane state.

Current explicit source pin: PR-Agent
`53072488e4c3b5a6c9ae730fe6fb52fc5f09d06c`. T2 records the immutable Linux amd64 bundle SHA-256 and hash-locked transitive
dependencies; an optional container image has its own digest. The upstream
hook audit and read-only Netcup inventory are retained; T4 owns fresh access,
capacity and deployment acceptance. Declared file lists below are explicit.
No wildcard is an implementation mandate. T1 freezes the inactive supplier
activation contract; actual supplier health and deployment are T4/T5 evidence,
and must not be claimed by closing the design task.

## T1 — 制定 PR-Agent 接入设计、验收口径与费用预算 (#1150)

Dependencies: none.

将 umbrella 方案落为仓库设计和实施计划。确认固定 PR-Agent commit、部署 bundle SHA-256 的生成/验证契约、依赖锁定、API 端点/具体模型、主备顺序、总重试预算、单 PR 输出/费用上限和批次总预算。用户授权每月 20 美元按量 API 消费；DeepSeek Secret 已于 2026-09-10T03:45:18Z 配置，鉴权和余额尚未验证。DeepSeek 约 10 美元预充值余额未核实；Kimi 本周额度耗尽，暂不调用。订阅额度与通用 API 账户分别核对，只记录 secret 名称，不读取/输出密钥值。
明确 fixed base/head 输入、只读文件内容、上下文重建、禁止执行 PR 文件、trusted config、schema/覆盖回执、test_scope 建议和发布隔离。评估上游 plain-diff 内部异常/空输出不能被 exit 0 掩盖，以及嵌套重试倍增。
预先确定代表性历史样本和真实 PR 观察方案：至少包含 #1127/#1132 的固定 head、正常/删除/大 diff/文档治理/已知缺陷/干净样本；固定至少 6 个独立已知缺陷样本和 6 个干净对照；真实 current-head 观察集固定 20 次、至少 5 个不同 head，至少 19/20 在执行开始后 10 分钟内完整完成，排队 p95 不超过 5 分钟。所有准入 attempt 均计入分母，取消/过期/全失败不得删除或算成功，重复 head 相关性单列。样本/费用不足为验收缺口，不在看到结果后下调。明确定义分母、取消/过期/失败分类；样本不足不宣称生产稳定。
确定单机故障 RTO、排队/扩并发触发条件、何时才需要第二台独立主机。补明确切换、回滚和后续维护责任。

Declared files:

- `docs/design/2026-09-10-pr-agent-review-migration.md`
- `docs/plans/2026-09-10-pr-agent-review-migration.md`

Verification and caught defects:

设计逐条对照现有 producer/consumer；核实上游固定版本的能力与依赖；运行 scripts/docs-site.sh check。此 Task 不新增产品测试或生产 gate。

## T2 — 实现固定版本 PR-Agent 引擎、完整输入与有界 API fallback (#1151)

Dependencies: T1.

建立独立 runner/沙箱入口，通过供应商 API 调用，不再经 Claude Code/Grok 登录型 CLI。支持配置 GLM/Kimi/xAI/DeepSeek；实际主备按 T1 已验证配置执行，不四路同时付费评审。
输入固定 diff 和经核对的文件内容；解决 plain-diff 在 base checkout 下错误反向重建；不读取 PR 自带配置、skills、hooks 或执行 PR 代码。只读/隔离运行，不给 GitHub 写 token。
保留完整文件/hunk 覆盖清单；删除、二进制和无法覆盖的内容必须可见，不静默裁剪后宣称完整。首期只允许完整单 prompt；超预算大 diff 显式失败，付费分块试验后续另定完整覆盖与跨文件质量 oracle。
输出原始结构化结果、实际模型/版本、脱敏错误类别、HTTP/重试/耗时/token/费用、覆盖清单。认证/参数错误不盲重试；429/暂态网络按预算退避；消除框架与外层重试乘积。空预测/无 JSON/内部吞错/不完整覆盖不得伪造 reviewed。

Declared files:

- `.gitattributes` (only the two exact PR-Agent semantic YAML fixture exceptions)
- `scripts/ci/pr_agent_review.py`
- `scripts/ci/pr-agent/Dockerfile`
- `scripts/ci/pr-agent/requirements.in`
- `scripts/ci/pr-agent/requirements.lock`
- `scripts/ci/pr-agent/config.toml`
- `tests/build/ci_pr_agent_review_test.py`
- `scripts/ci/pr-agent/build-bundle.sh`
- `tests/fixtures/ci/pr-agent/valid-native-review.yaml`
- `tests/fixtures/ci/pr-agent/clean-native-review.yaml`
- `tests/fixtures/ci/pr-agent/complete-input.json`
- `scripts/ci/scope_policy.json`
- `docs/plans/2026-09-10-pr-agent-review-migration.md`

Other minimal malformed variants are generated by tests in temporary directories.
Acceptance quality fixtures are separately frozen in T5 before evaluation; these
adapter fixtures cannot serve as their independent quality oracle.

T2 also owns the exact `tests/fixtures/ci/pr-agent/` scope-policy prefix and
this plan amendment. Those new tracked fixtures must select `ci_contract`;
unknown-path handling remains fail-closed and unrelated fixture directories
retain their existing ownership.

### T2 clean-CI seam-proof amendment

The real upstream integration suite remains mandatory in both existing
`ci-contract` jobs and the matching local `ci_contract` lane. Run the existing
Python 3.11 contract discovery, then an additional shared entry point that
prepares an isolated Python 3.12 environment and executes the actual handler
suite. A pure-contract result alone never substitutes for this second result.
Keep both job timeouts, lane selection, trusted-head restrictions and branch
protection unchanged; this preparation does not activate production review.

Additional declared files:

- `scripts/ci/pr-agent/integration-test.sh`
- `.github/workflows/ci.yml`
- `.github/workflows/pr-contract.yml`
- `scripts/ci/local_lanes.json`

The preparation verifies a fixed upstream archive digest, independently binds
its source identity, and installs hash-locked runtime and source-build
dependencies in an isolated environment. It requires no Docker daemon. Both
CI jobs and the local lane invoke the same entry point and propagate failures;
missing local prerequisites are reported as not-runnable-here, never a pass.
No actual integration case may be omitted from the owning lane to make it green.

Verify the shared entry point from a clean temporary environment, retain its
exact source/runtime/dependency identities and full result, and run the actual
contract discovery command plus the source-coupled
`ci_workflow_topology_test.py`, `ci_runner_fallback_test.py` and
`ci_local_preflight_test.py` regression checks. Reuse the existing adapter test
file for any concrete preparation-boundary regressions; do not add unrelated
checks or widen timeouts. The lead owns this plan; implementation owners may
stage the approved amendment with the single T2 commit after verification.

Verification and caught defects:

python3 tests/build/ci_pr_agent_review_test.py：固定输入、删除/超长 diff、base/head 重建、注入配置、401/429/超时/无效输出、重试总预算、脱敏、覆盖缺失分别有最小反例；构建固定 Linux amd64 bundle 验证依赖；Dockerfile 仅为可选可复现构建工具，不要求 Netcup 安装 Docker。付费 live probe 只在预算明确后执行。

For the fixture ownership rule, run `python3 tests/build/ci_change_scope_test.py`
with the declared new files represented in the index, plus
`python3 tests/build/ci_scope_policy_consumer_parity_test.py` and
`python3 tests/build/ci_scope_policy_differential_test.py`. These checks catch
unowned tracked paths and disagreement between policy consumers. Run
`scripts/docs-site.sh check` for this plan amendment before commit.

At the real PR-Agent handler seam, assert that all required hunks and deleted
content reach the fake handler, immutable base/head bytes are used, and hostile
CWD content/config is never read. T2 owns RIGHT-side validation in
`pr_agent_review.py`: clean, deletion, rename, binary/unreadable, wrong-side and
outside-diff cases live in `ci_pr_agent_review_test.py`; invalid anchors fail
the entire attempt. Patch actual LiteLLM `acompletion` and assert at most two
calls per provider/eight total, per-call ledger admission, no nested retry,
unknown price denial and uncertain timeout reservation retention. Coverage
receipt/history fields follow the design's Receipt and compatibility interface.
Any chunk support must be offline-tested for union and missing-result failure;
it is not enabled for paid pilot evaluation.

### T2 accepted review correction contract

The independent review of PR #1175 at
`5ed6fa6adfe79d8689ca2c8da11b9263495a3151` found six unresolved defects in
configuration admission, actual request limits, runtime identity, native-output
validation, coverage identity and the clean Python 3.11 test boundary. Correct
these within the existing T2 declared files and retain the failed head and its
CI/review runs. A changed adapter or config requires a new matching Linux
bundle and new-head independent review. No supplier is activated by these fixes.

The closed coverage receipt keeps the design's exact top-level keys and has
no self-digest. Its nested `model` is a closed object with `requested`, `actual`,
`response_version` and `pricing_revision`. `actual` records the provider's
returned model identity, distinct from the requested alias. A reviewed receipt
requires a nonempty actual model matching the trusted priced response binding.
`response_version` is the provider-returned version when present, otherwise
null; it is never filled from a guessed or configured release name. Failed
attempts may retain null actual identity. T3 computes the digest over the complete
canonical receipt and preserves these identities in its v2 history path.

Each closed expected/observed segment entry has `id`, `path`, `old_path`,
`change_kind`, `old_blob`, `new_blob`, `patch` and `right_lines`. A blob object
has `object_id`, `sha256` and `byte_length`; an absent file side is null rather
than an invented empty blob. `patch` has `sha256` and `byte_length`. Verify Git
blob hashes, content hashes and lengths from the exact bytes and against the
fixed base/head collector inventory. Deletion and required zero-hunk content
remain represented. T2 does not gain GitHub access or execute PR code; T3 owns
authentication of the collector and control provenance at its consumers.

### T2 owner scope amendment: provider counting excluded

The owner's 2026-09-10 scope decision supersedes the earlier supplier-counter
prerequisite, including its 100,000-input-token gate. Remove `input_token_cap`,
`tokenizer_id`, `tokenizer_verified`, the custom counter registry and local
rendered-message counting preflight; reject obsolete config keys. Do not replace
these with another provider counting scheme or require counter certification.
Keep the pinned stock `o200k_base` asset only for upstream startup, with isolated
cache and no unexpected metadata/asset request. Complete unchanged rendered
messages, byte/file/hunk limits, output/request/deadline/retry caps, strict finish
reason, model identity, typed output and complete coverage remain required.

Implement the design's single-ledger monetary envelope before every physical
HTTP request, including the stock retry:
`context_token_limit * peak_input_rate + output_token_cap * peak_output_rate + fixed_request_charge`,
rounded upward. The trusted context ceiling bounds every possibly billed input
unit, including overhead and billed context rejection, without local counting.
Require `0 < output_token_cap < context_token_limit`; the output cap covers all
enabled charged output classes. Unknown/unbounded categories deny admission;
optional charged features stay disabled unless bounded. Price revision binds
these limits, rates, fixed charge, billable categories and priced response-model
identity in the durable reservation basis. Preserve USD 1 attempt,
USD 20 cumulative pilot and USD 20 Asia/Shanghai monthly caps. Supplier account
funding is checked manually and is not an adapter activation prerequisite.

Reconcile complete authoritative priced usage/model identity; otherwise finalize
exactly once uncertain and retain reservation. Direct monetary charge
reconciliation is unsupported. Ignore ambiguous LiteLLM response-cost headers:
they cannot override usage, refund reservations, fill missing usage, or create
an envelope hold by themselves.
Higher liability derived from complete trusted priced usage must be recorded.
Output, total-context or priced-usage monetary
envelope breach fails the review, stops all fallback in that attempt and poisons
later admission for that same `(provider, effective_model, price_revision)` until
operator review replaces/disposes it. Reuse existing append-only records and only
minimal internal basis data, with no second ledger or public receipt extension.
Detect valid integer output/context usage breaches before response-model checks
or monetary conversion. Model mismatch and nonrepresentable cost retain the
reservation and observed attempt usage with an uncertain terminal record and a
durable breach hold; they cannot escape finalization into stock retry or fallback.
Do not invent a finite actual charge; preserve higher priced liability whenever
it is representable.

The follow-up to rejected local commit `9e837bde` also fixes two test defects:
both strict deadline assertions measure the external interval from first actual
dispatch to return, retaining the 3-second bound, copied-at-return call snapshot
and delayed no-late-work assertions; the non-finite-ledger test starts from a
current-schema finite record proven valid and mutates only its amount to NaN.
Keep the native and emulated failures as historical evidence. Independently
review corrected source before authorizing the next bundle build.

Declared runtime/test follow-up paths (implemented in `0c196687`): this plan, the existing migration design,
`scripts/ci/pr_agent_review.py`, and `tests/build/ci_pr_agent_review_test.py`.
`scripts/ci/pr-agent/config.toml` was conditional on a concrete source-coupled
need; none arose and it is unchanged by this follow-up. Preserve the published 8148a1ec baseline
and its genuine failed evidence; make a new corrective commit. No workflow,
bundle machinery, dependency lock or receipt schema change is authorized absent
a concrete source-coupled need reviewed by the lead.

The subsequent scope/Progress coherence correction changes only this plan.
Verify its documentation and staged path inventory; runtime/test bytes and their
independent verification at `0c196687` remain unchanged. Bind the plan readback
to the new committed tree before authorizing the final bundle.

Tests must prove no supplier counter is needed; complete messages reach the real
pinned handler; an affordable context above 100,000 admits; unknown/unaffordable
or unbounded pricing denies before network; each retry reserves separately;
malformed/missing usage and model identity finalize uncertain once; and each
envelope breach preserves liability, stops fallback and holds future admission.
Retain all F7-F10 regression assertions and the original strict deadline bounds;
do not widen a host timeout to pass emulation. Run focused adapter tests, clean
Python 3.11 / pinned LiteLLM 1.100.0 Python 3.12 shared integration, declared-scope
checks and `scripts/docs-site.sh check`. Freeze source before one final Linux
bundle, bind its adapter/config/archive identities to the new commit, and obtain
independent current-head review. Documentation impact: none; unreleased internal
review infrastructure and design/plan only, no Portal route/projected identity
change. Version impact: none; no Product/Module/Contract identity changes.

T2 may complete when the adjusted engine works with eligible trusted config and
these technical gates pass. Supplier counting, live supplier qualification,
host access, shadow qualification and T3-T6 acceptance are not additional T2
gates. Defaults remain inactive; this amendment is not proof of live supplier
usability. Funding attestation is deferred and is not a T2 gate.

Use a detached `DEPLOYMENT_IDENTITY.json` to bind the final archive SHA-256 and
byte length, manifest, adapter, bundled default config and dependency lock.
Generate it after the archive digest is known; a bundle cannot contain its own
final digest. The engine verifies its actual extracted files against this
trusted runner/deployment input and computes the runtime configuration digest
and length separately. PR-supplied identity data cannot authorize execution.
T4 owns verification of the installed archive and protection of that deployment
identity. Runtime receipts retain the verified bundle and configuration identity.
The closed `engine.bundle` has `archive_sha256`, `archive_byte_length`,
`manifest_sha256`, `adapter_sha256`, `default_config_sha256` and
`requirements_lock_sha256`; `engine.runtime_config` has `sha256` and
`byte_length`. The detached identity has exactly `schema`, `archive` and `files`.
Its `archive` has `sha256` and `byte_length`; its `files` has `manifest`,
`adapter`, `default_config`, `requirements_lock` and `stock_tokenizer_asset`,
each with `path`, `sha256` and `byte_length`. T3 preserves these closed
identities; T4 verifies the archive and installs the detached identity through
its trusted deployment boundary.

Retain actual YAML/handler regressions in the pinned Python 3.12 boundary while
making the ordinary Python 3.11 contract independent of ambient PyYAML. Prove
both stages execute successfully in clean environments, without dropping the
missing-findings assertion, widening timeouts or skipping a required integration
case. Require a model-supplied summary for clean output and bound the whole raw
prediction before parsing, including all retained native fields. Run the
affected focused tests, staged ownership checks, required clean-CI proof, new
bundle proof and `scripts/docs-site.sh check` for this plan amendment.

### T2 second independent-review correction contract

The independent review of `5c0c0dd0` found four additional defects. Preserve
its negative probes and the previously accepted v11 artifact as historical
source-bound evidence; changed adapter bytes require a new final bundle.

- Authenticate an exact one-to-one partition of every diff file and hunk,
  rather than substring membership. Extra, omitted, duplicate or overlapping
  records fail before admission. Rename, deletion, binary and unreadable cases
  remain explicit; do not silently discard unsupported records.
- Enforce the engine deadline around the whole provider attempt, including
  upstream retry backoff, parsing and cleanup. Cancel/clamp waits to remaining
  time and prove no late dispatch or continued work after return.
- Store the two tiny native YAML fixtures as ordinary Git text via exact-path
  `.gitattributes` exceptions, following the existing actionlint exception.
  Renormalize only those two files. Prove the staged/committed Git blobs contain
  actual YAML, then run the real integration command from a checkout without
  LFS smudging. Do not enable repository-wide LFS hydration or rely on runner
  cache state; the workflows' existing invocation stays unchanged.
- Every post-dispatch malformed model/version identity must finalize the
  reservation exactly once as uncertain when trusted pricing is unavailable,
  retaining observed usage and conservative cost. A completed unpriceable
  response must not remain indistinguishable from an in-flight reservation.

Correction scope: `.gitattributes`, `scripts/ci/pr_agent_review.py`,
`tests/build/ci_pr_agent_review_test.py`, the two declared native YAML fixtures,
and this plan. Run focused partition/ledger tests, actual pinned-handler
backoff/cancellation/identity tests, the no-smudge clean integration proof,
staged scope/ownership and declaration checks, the final identity-bound Linux
bundle proof, and `scripts/docs-site.sh check`. A passing earlier broad suite
is retained with its exact scope; these new defects need their own negative
and far-side assertions. For that historical correction, no provider admission mode changed and the
registry stayed empty. Its supplier-counter completion prerequisite is superseded
by the owner scope amendment above; retain the baseline evidence without treating
the removed counter as an outstanding Task gate.

## T3 — 适配 LMDJ 评审协议、测试范围与所有下游消费者 (#1152)

Dependencies: T2.

将 PR-Agent 结构化输出映射为 LMDJ 当前协议，保留 summary/findings/test_scope、exact head、run/attempt、实际供应商与模型身份；不能将引擎名称冒充实际模型。
统一调整 backend 白名单/历史解析/评论 marker/等待器/liveness/scope policy/相关 canary 消费者；兼容读取历史 glm/kimi/grok 回执，不重写旧证据。测试范围缺失必须按正式协议显式保守处理，不能编造模型建议或错误缩减测试。
继续独立 publisher 鉴权和 source provenance，验证 changed RIGHT-side 行号，clean review 不创建虚假行内问题，重复事件幂等，过期 head 不发布。生产 workflow 仍使用旧入口；本 Task 交付可测试适配接口，切换归 T6。

Declared files:

- `scripts/ci/review_pipeline.py`
- `scripts/ci/review_scope.py`
- `scripts/ci/review_scope_codec.py`
- `scripts/ci/review_wait.py`
- `scripts/ci/test_scope.py`
- `.github/scripts/pr_review_target.py`
- `.github/scripts/advisory_review_liveness.py`
- `scripts/ci/review_failure_report.py`
- `scripts/ci/review_merge_map.py`
- `scripts/ci/review_merge_map_reader.py`
- `scripts/ci/review_discovery_runtime.py`
- `tools/canary/assessment.py`
- `tools/canary/assessment_runtime.py`
- `tools/canary/assessment_entry.py`
- `tools/canary/assessment_journal.py`
- `tools/canary/assessment_handoff.py`
- `tests/build/ci_review_pipeline_test.py`
- `tests/build/ci_review_scope_test.py`
- `tests/build/ci_review_scope_codec_test.py`
- `tests/build/ci_review_wait_test.py`
- `tests/build/ci_test_scope_test.py`
- `tests/build/ci_advisory_review_liveness_test.py`
- `tests/build/ci_review_failure_report_test.py`
- `tests/build/ci_review_merge_map_test.py`
- `tests/build/ci_review_merge_map_reader_test.py`
- `tests/build/ci_review_discovery_runtime_test.py`
- `tests/build/ci_canary_assessment_test.py`
- `tests/build/ci_canary_assessment_runtime_test.py`
- `tests/build/ci_canary_assessment_entry_test.py`
- `tests/build/ci_canary_assessment_journal_test.py`
- `tests/build/ci_canary_assessment_handoff_test.py`

T3 changes canary schema consumers only for compatibility; it preserves their
existing opt-in execution and model configuration. `tools/canary/executor_policy.json`
and `.github/workflows/canary-assessment.yml` remain unchanged. No automatic
assessment, host preparation or release becomes authorized by this migration.
`.github/workflows/advisory-review-liveness.yml` remains unchanged: its existing
trigger/routing stays in place; T3 changes the invoked reader only, covered by
`ci_advisory_review_liveness_test.py` and T6 workflow graph/topology regression.
`scripts/ci/review_discovery.py` remains unchanged: the pure reducer keeps its
existing event schema; receipt authentication belongs in the T3-owned runtime,
with `ci_review_discovery_test.py` as regression coverage. Any later change to
these boundaries requires an explicit file-ownership update before editing.
Regression-only files: `tests/build/ci_review_discovery_test.py`,
`tests/build/ci_review_discovery_storage_test.py`,
`tests/build/ci_review_discovery_workflow_test.py`,
`tests/build/ci_canary_preparation_test.py`,
`tests/build/ci_change_scope_test.py`,
`tests/build/ci_scope_policy_consumer_parity_test.py`, and
`tests/build/ci_scope_policy_differential_test.py`.

Verification and caught defects:

运行本 Task 列出的协议 Python test 文件及上述 scope/canary 最低层回归；真实路径覆盖 stale head、伪造来源、重复发布、错误行号、missing scope、旧回执兼容、全后端失败。不得把多个相同桩之间一致当跨边界验证。

## T4 — 部署 Netcup 单机专用评审槽位并验证资源与恢复 (#1153)

Dependencies: T1, T2.

先刷新 Netcup inventory、runner 标签、elastic controller/资源配置与当前负载；现有记录 16 cores/62 GiB 不等于空闲容量。设计并部署一个不抢占 heavy CI 所需预算的评审专用槽位，不能直接增加无资源预算的 runner 服务。主机修改使用仓库拥有的可审查部署入口，记录 exact targets、前后状态与回滚命令。
固定 bundle SHA-256 的 Python 环境以 systemd 隔离运行；现有主机不使用 Docker，不为此安装 daemon 或增加 Docker group 权限。运行用户、临时目录与凭据隔离；不暴露公网 webhook，不引入 Kubernetes/数据库。初期 1 并发，1 vCPU/2 GiB 硬上限，独立 sibling slice，保留 heavy slice 的 14 vCPU/48 GiB 和 elastic ceiling；仍需测量确认系统与同机业务余量。仅对已满足 trusted activation 条件的启用供应商验证 API 可达性、鉴权和具体模型，并使用 T1 已批准费用预算；disabled/null 供应商只记录缺失条件，不激活或探测。四家 API 成功运行与真实 fallback 仍须在 T5 通过，未通过不得进入 T6。
测量冷启动/峰值 RSS/CPU/磁盘/排队/重 CI 共存；验证进程退出后可恢复和任务可追踪，不得中断其他工作来模拟整机故障。同机双实例只算并发，不算主机冗余；第二主机/采购列后续触发，不实际执行。
Host mutation stops until approved operator access, runner 04 classification,
execution user, actual sibling/heavy slice CPUQuota/MemoryMax, current available
memory/pressure/swap and runtime filesystem isolation are read back. Record
normal co-running heavy jobs and peak review RSS/CPU/disk without disrupting
those jobs. Inventory total memory alone cannot satisfy admission.

所有评审相关 job 明确 self-hosted/Netcup 路由；保留 GitHub Actions 调度，不新增 hosted 计费执行。

Declared files:

- `scripts/ci/pr-agent/deploy-runner.sh`
- `scripts/ci/pr-agent/netcup-review.json`
- `tests/build/ci_pr_agent_runner_test.py`
- `docs/quality/2026-09-10-pr-agent-netcup-operations.md`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`

Existing elastic configuration is read-only input; no modification is declared.
T4 renders its own systemd unit from the deployment script and does not alter
heavy runner services. Reconcile runner 04 label drift through read-only receipts
and operator confirmation before host mutation.

Verification and caught defects:

部署脚本静态检查与 dry-run/幂等/回滚 fixture 测试；Netcup 只读 inventory、批准预算的连通性实测、受控进程恢复；验证专用槽位和 heavy 预算未互相超卖。记录 Actions 执行位置和存储开销。

## T5 — 运行 PR-Agent 影子评审并裁定质量、可靠性与成本 (#1154)

Dependencies: T3, T4.

创建显式手动触发的 shadow workflow，运行 T1 预注册样本/真实 PR 观察，不修改正式评审结果、labels 或 merge authority，不给模型写 token。旧三路继续作为现有正式路径。
回放 #1127 head 91f28ee2039a95d7c6c91e5943668e91c0e6cc14、#1132 head 85c129208f858bb1a8c3efc6100e8bd5f9cd8403；历史 head 只算回放，不冒充 current-head 评审。已知缺陷与干净样本有独立 oracle，发现质量不能用 JSON 合法性替代。
按原定分母报告有效评审率、覆盖、模型失败/备用恢复、端到端耗时与排队、token/费用、峰值内存、误报/漏报、取消/过期。故障注入与真实模型结果分开；记录读回/发布路径验证，可用专门 canary PR 验证 publisher，不写入无关 PR。
达到 T1 所有切换标准才 PASS；预算耗尽、样本不足、某 API 不可用或质量失败明确阻塞，并转入最小修复子项，不能为结案降低标准。

Declared files:

- `.github/workflows/pr-review-shadow.yml`
- `scripts/ci/pr_agent_shadow.py`
- `tests/build/ci_pr_agent_shadow_test.py`
- `docs/quality/2026-09-10-pr-agent-shadow-acceptance.md`

Verification and caught defects:

python3 tests/build/ci_pr_agent_shadow_test.py 验证只读/不改变正式 scope、分母/错误分类、费用与取消边界；实际 Netcup shadow runs 回读 artifact/source SHA/model/token，独立核验发现。运行 scripts/docs-site.sh check。

## T6 — 切换正式 AI review、验证回滚并交接运维 (#1155)

Dependencies: T5.

在 T5 正向验收后，刷新 main/保护/相关开放 PR，按 issue-done 将正式 PR Review 切到已验证 PR-Agent 引擎，移除生产 GLM/Kimi Claude Code 和 Grok CLI 调用。只保留必要历史回执兼容，不删除历史运行/失败证据或无关功能。
三个 job 的 exact input→review→publisher 和 merged-PR scope mapping 全链路验证；四家 API 支持与实际主备策略有清楚身份。正常/新 push/重跑/备用恢复/过期 head/重复发布/全失败均可观察；不放宽保护/独立评审/测试范围。
切换前准备明确的 revert/routing 回滚入口；原旧路径已知不稳定，回滚只能声明恢复旧配置，不能声称恢复健康，必要时进入可追溯 current-head 人工/agent 接管。受控验证回滚后恢复新路径，保留每次 exact evidence。
按 T1 观察窗口取得正式端到端证据，交接 secret 名称/轮换、费用告警、重试/恢复/更新 pin/扩容条件。关联 #939/#819/#836/#849/#712/#1089，但不自动关闭：逐项对照各自验收与遗留范围。umbrella 仅在整体交付和验收完成后结案。

Declared files:

- `.github/workflows/pr-review.yml`
- `tests/build/ci_review_pipeline_test.py`
- `tests/build/ci_pr_agent_cutover_test.py`
- `docs/quality/core-test-policy.md`
- `docs/quality/2026-09-10-pr-agent-netcup-operations.md`
- `docs/quality/2026-09-10-pr-agent-shadow-acceptance.md`
- `tests/build/ci_pr_review_workflow_test.py`
- `tests/build/ci_claude_review_workflow_test.py`
- `tests/build/ci_grok_review_workflow_test.py`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`

Retain `.github/scripts/grok_review.py`: the publisher still imports its transport
helpers. Remove production CLI invocation in the workflow, without deleting
this shared helper or rewriting historical evidence. T3 completes before T6
owns any cutover-specific edits to `ci_review_pipeline_test.py`. Preserve producer
job names and artifact naming; changing them requires declaring the affected
readers again. Run the T3 protocol suite as regression plus workflow event-graph
and topology checks; do not equate static workflow tests with real acceptance.

The four repeated paths have sequential ownership, never concurrent editors.
Before T6 dispatch, record the merged T3/T4/T5 heads and transfer these exact
paths to the T6 worker:

- `tests/build/ci_review_pipeline_test.py`: T3 owns protocol/history validation;
  T6 adds only production-routing integration and keeps T3 regression cases.
- `docs/quality/2026-09-10-pr-agent-netcup-operations.md`: T4 owns installation,
  capacity and isolated-slot evidence; T6 appends cutover, rollback and operator
  handoff receipts without replacing T4 measurements.
- `apps/docs-site/docs/operations/testing-and-proof.mdx`: T4 documents the
  installed shadow slot and source paths; after T4 merge, T6 alone updates the
  active production route and source paths after verified cutover.
- `docs/quality/2026-09-10-pr-agent-shadow-acceptance.md`: T5 owns the frozen
  cohort and all outcomes; after T5 merge, T6 appends links to cutover receipts
  without changing samples, denominator, thresholds or the T5 verdict.

The lead verifies these ownership transfers before dispatch; upstream Task
workers must have settled and stopped editing the transferred paths.

Verification and caught defects:

最低层 workflow/协议/cutover 回归与 scripts/docs-site.sh check；Netcup 正式 current-head 真实评审和发布读回、保守失败、scope mapping、幂等、受控回滚/恢复。无自动产品 release 或 full self-test 扩展。

## Acceptance and handoff

The design owns the preregistered quality oracle, cohort and thresholds. Freeze
input hashes, engine/config identity and budget before evaluation. Every Task
records passing and failed commands, exact revisions, limitations and artifact
identity. Read back GitHub state; a worker summary or an Issue closing is not
completion evidence. Verify all journey legs after each transition.

T5 cannot authorize T6 with an incomplete cohort or negative quality evidence.
T6 cannot close the umbrella with only mock API, static workflow or schema
checks. Production review, publication, scope propagation, failure recovery and
rollback/restoration need their own exact receipts. Historical failures remain.

## Version Management

Version impact: none — these Tasks concern CI tooling and operation, not product
or module manifests. Engine pin, dependency lock and container digest identify
the tool build. No Product Build, Portal snapshot or Release is allocated.

## Documentation Impact

Documentation impact: none
Reason: T1 is proposed design/plan only, with no current Portal behavior change.
Its declared verification still includes `scripts/docs-site.sh check`.

T2/T3 internal adapters remain inactive until explicitly wired. Reassess their
Portal impact against their final diff. T4 and T6 own documentation of actual
operation and must include `apps/docs-site/docs/operations/testing-and-proof.mdx`
and route `/operations/testing-and-proof/` when deployed behavior is documented.
Update page source_paths and run the check in that same Task. A docs/quality
file alone does not justify claiming that a Portal page was changed.

## Historical T4 prerequisite: dedicated credential preflight

This section records the earlier balance-preflight workflow and its evidence
boundary; it is retained as history, not a current candidate gate. Do not rerun
it merely to satisfy the retired funding-attestation requirement. The owner now
checks supplier accounts manually, and this migration adds no balance query or
funding authority.

The owner authorized completion of deployment admission and credential
verification on 2026-09-11 after selecting DeepSeek-V4.1-Flash (API name
`deepseek-flash`) instead of Pro. This does not waive a technical admission
condition or authorize other suppliers, larger budgets or production cutover.

One reviewable prerequisite Task adds owner-dispatched, main-only
`pr-agent-credential-preflight.yml` on existing Netcup `ci-general` capacity.
It performs only `GET https://api.deepseek.com/user/balance`, with no inference,
redirect, proxy environment, retry, secret export, artifact, host provisioning
or production review write. Its finite receipt establishes API authentication
and current supplier availability, not USD funding admission, model health,
runtime credential injection, full deployment or T5/T6 acceptance. Actual
balances and raw HTTP bodies/errors never enter the workflow log.

Declared files: `.github/workflows/pr-agent-credential-preflight.yml`,
`.github/actionlint.yaml` (register the live Netcup label),
`scripts/ci/pr_agent_credential_preflight.py`,
`tests/build/ci_pr_agent_credential_preflight_test.py`,
`scripts/ci/scope_policy.json`, this plan,
`docs/design/2026-09-10-pr-agent-review-migration.md`,
`docs/quality/2026-09-10-pr-agent-netcup-operations.md`, and
`apps/docs-site/docs/operations/testing-and-proof.mdx`.

Lowest-tier verification: the dedicated mocked-HTTP contract suite,
`python3 tests/build/ci_change_scope_test.py` after new-file staging, workflow
syntax validation, and `scripts/docs-site.sh check`. No new required merge gate.
The tests catch credential/response disclosure, redirected authentication,
malformed or unavailable balance accepted as passed, and automatic/untrusted
workflow execution. Live far-side evidence requires the merged workflow's
exact run/attempt and sanitized receipt; a local mocked response is not API
authentication. Subsequent paid model requests still use the existing engine,
full monetary reservation and durable ledger, never this read-only helper.

Version impact: none — CI operation only; no Product or Contract identity change.
Documentation impact: required
Affected portal pages: /operations/testing-and-proof/

## T4 prerequisite: deterministic protected installation modes

Correct the permissive-umask failure observed in PR #1184 contract runs
34517124144/1 and 34517599417/1. The installer sets `umask 022` for newly
created parents; existing unsafe owner/mode boundaries still fail without
repair. Positive test fixtures model protected installation bytes instead of
inheriting a checkout's writable mode. No engine/config/bundle identity changes.

Declared files: `scripts/ci/pr-agent/deploy-runner.sh`,
`tests/build/ci_pr_agent_runner_test.py`,
`tests/build/ci_pr_agent_review_test.py`, this plan,
`docs/quality/2026-09-10-pr-agent-netcup-operations.md`, and
`apps/docs-site/docs/operations/testing-and-proof.mdx`.

Lowest-tier verification: both focused Python suites under normal and `0002`
umasks, including clean `python3 -S` execution, `bash -n` on the installer,
and `scripts/docs-site.sh check`. Regression assertions cover new-parent
`0755` modes, repeat-install idempotence and rejection without mutation of
existing writable paths. No gate, timeout or security validation is relaxed;
real bundle/systemd/provider/coexistence acceptance remains separate.

Version impact: none — internal deployment behavior, no versioned identity.
Documentation impact: required
Affected portal pages: /operations/testing-and-proof/

## T2 follow-up: protected real-handler preparation

PR #1185 fixed the ordinary contract fixtures, but its exact-head run
34519528135/1 subsequently reached the pinned real-handler stage and failed
on generated source metadata and runtime fixture configuration modes under
the runner's permissive umask. Fix those preparation boundaries, preserving
all loader protection, timeout and actual-handler assertions. No runtime
engine, provider configuration, dependency or bundle identity change.

Declared files: `scripts/ci/pr-agent/integration-test.sh`,
`tests/build/ci_pr_agent_review_test.py`, and this plan.

Lowest-tier verification: reproduce the real shared integration entrypoint
under `0002`, then run corrected clean Python 3.12 preparation under both
`0022` and `0002` with every real-handler case enabled, plus clean `python3 -S`
ordinary adapter tests, shell syntax and `scripts/docs-site.sh check`. Keep
generated installation metadata protected without modifying original checkout
modes; do not suppress failures or omit the actual-handler leg. Retain the
original failed run and record exact source/runtime identities and counts.

Version impact: none — test preparation only, unchanged shipped engine.
Documentation impact: none
Reason: implementation plan and test-only preparation, no changed Portal facts.

## Progress

- T1 was merged through PR #1161 at `409a1a4d`; the earlier audit and failed
  receipts below remain historical evidence.
- T2 merged through [PR #1175](https://github.com/endaye/lmdj/pull/1175) at
  `ccda4381dfc25c75c1fa7d4f82056e216943b881` on 2026-09-10T15:06:42Z;
  #1151 is closed. The independently reviewed source head was
  `23cfb9f0a072cc5cc3bb16b080937d56a4317236`, tree
  `82ffb3f19e4f50edab449f69925a639a1e875bf9`, covering all 18 declared paths.
  The final v14 Linux amd64 archive is 361820160 bytes, SHA-256
  `4359addd2521847509b61c655a346e1a59e49ebec87934024f35c066eb3f26d3`;
  its detached identity SHA-256 is
  `a1f7f67b6ae9390a3a4117f0bf1bb96a7269306aef5b12433d06b6e62dc3d2c3`.
  Independent archive/member/source checks, the sole supported build exit 0
  and exactly one matching Linux clean-base marker bind it to the accepted
  source. Native pinned-handler 27/27 and shared entrypoint 42/42 passed;
  ordinary discovery was 69 cases with 40 passed and 29 explicit integration
  skips, not 69 passes. The independent ordinary script run was separately
  42 cases with 40 passed and 2 skips.
- Current-head takeover [record 5620843576](https://github.com/endaye/lmdj/pull/1175#issuecomment-5620843576)
  records distinct author/reviewer sessions and finding dispositions; the
  trusted review helper returned `eligible: true` before guarded squash merge.
  Live review threads were empty and protection unchanged. PR Review run
  `34492480810/1` failed during collection before provider execution; publisher
  was skipped. PR Contract `34492480824` subsequently ended cancelled. Neither
  is recorded as a pass. Rejected `9e837bde`, v13 extracted-suite failure/timeout,
  earlier timing/LFS/runtime failures and diagnostic audit-script errors remain
  historical evidence; clean-base import is not Linux extracted full-suite proof.
- T3 merged through [PR #1181](https://github.com/endaye/lmdj/pull/1181) at
  `5034f0dad60895333b389789c081e44a32533ca7` on 2026-09-10T17:15:00Z;
  #1152 is closed. Independently accepted source
  `0e8e3560fb926b11f056e578d5a68bf4e86c8a49`, tree
  `ba4fef7565599518d1c5ccddd968fb02770dd52a`, covers the complete 17-path
  protocol/consumer diff. The independent 22-suite run discovered 701 tests:
  699 passed, 2 existing environment guards skipped, 0 failed. The opt-in
  actual T2 `run_engine` integration separately passed under Python 3.12,
  with only completion injected; it traverses actual capture and finalize,
  checks persisted history/collector/config/coverage, and reaches publisher
  preparation. This is offline source integration, not real-provider review.
- T3's actual capture NameError, missing v2 waiter route and failure-collector
  import were corrected with far-side regression tests before acceptance.
  Distinct implementation/reviewer sessions and complete remote blob parity
  are adopted in [record 5622571018](https://github.com/endaye/lmdj/pull/1181#issuecomment-5622571018).
  The trusted helper returned `eligible: true` before guarded squash merge;
  live review threads were empty and protection unchanged. PR Review
  `34506513250/1` and PR Contract `34506513403/1` were still running at the
  recorded remote review; Cloudflare preview `34506513217` was skipped and
  Cursor checks were neutral. None of these is recorded as full CI or
  automated review success. Historical rejected heads and the corrected
  exploratory test-selector/shell-variable errors remain distinct evidence.
- T4 remains open; source development and local fixtures do not satisfy
  operational acceptance. Independent review of
  `537528ce3ba53fc08cf61b0f3a90bb56aa5de921` accepted the closed-state and
  receipt-semantic repairs, but rejected release-root mode/member-GID drift:
  changing the root to `0777` or a member GID still let repeat install return
  `idempotent`. Its ordinary runner result (30 passed, 1 skipped), opt-in v14
  result (31 passed), scope/parity results (71/5), and Portal result
  (116 tests/44 routes) did not discharge that reproduced defect. A later
  source head requires an explicit verified disposition and fresh independent
  review. The lead alone owns these design/plan status updates; T4 retains
  ownership of its five deployment/documentation paths.
- T4's strict read-only SSH refresh succeeded as `en` on `netcup01`; noninteractive
  sudo failed password-required. Runner 04 configuration matched baseline
  policy despite the extra API elastic label; operator classification remains
  pending. The observed heavy slice is 14 vCPU/48 GiB, but idle resource
  snapshots do not satisfy co-running admission. No host mutation or supplier
  activation has occurred. Administrator execution, isolation, headroom,
  process recovery and enabled-supplier qualification remain open T4 evidence.
- T5/T6 have not started, and #1149 remains open. Defaults keep all providers
  inactive. Four-supplier live success/fallback, independently frozen quality
  samples, 20 admitted current-head attempts across at least five heads,
  production publication/scope mapping and rollback/restoration remain required.
  AI-provider token counting is outside the entire migration scope by the
  owner's decision; there is no pending counting decision.

### Initial planning evidence (historical)

- T1: independent audit found B1 activation wording and B2 sequential ownership ambiguity; both now have explicit dispositions below and await shipping review.
- Initial docs-site check failed due to missing locked dependencies; retained as setup evidence.
- After locked dependency setup, docs-site check exited 0: 116 tests passed, build and 44 routes validated.
- The initial follow-up worker reached its Codex usage limit; after the owner reset usage, a replacement delivered the bounded disposition review.
- F2/F4/F6/F8 and technical F5 were independently resolved; the lead added explicit unchanged dispositions for the remaining two F3 paths.
- USD 20/month budget is authorized; DeepSeek secret presence is verified. Live authentication/funding and deployment access remain T4/T5 prerequisites; T1 final readiness review is pending.
- Fresh host inventory run `34426814461/1` passed at `66edc6559eef898005c82b300c95e353310607d1`; capacity acceptance remains open.
- T2–T6: not started.
- Key entry contract: GitHub Actions Secrets `PR_AGENT_DEEPSEEK_API_KEY`, `PR_AGENT_ZAI_API_KEY`, `PR_AGENT_KIMI_API_KEY`, `PR_AGENT_XAI_API_KEY`; DeepSeek presence confirmed, other three dedicated names not observed.
- DeepSeek is the first live candidate; Kimi is temporarily disabled, and subscription-only access is not counted as general API availability.
- Existing production review configuration and server services: unchanged.
