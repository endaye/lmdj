# Merge Queue Diagnosability and Mixed-Path Hardening Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 Issue #230 记录的四个 Integration Queue 弱点：混合合并路径烧掉队列 attempt、终止失败码不可分辨、终止清理静默丢失、注定超时的 attempt 仍会 dispatch 全量 CI 且孤儿运行不被取消。

**Architecture:** 保持串行单槽队列、`lmdj-merge-main` + `queue: max` 的平台 FIFO、synchronize 运行复用（controller 绑定并批准 GitHub 自动创建的 `pull_request` 运行而不重复 dispatch）、三次 attempt 上限和 squash-merge 后置条件协议全部不变。Task 1 只改治理文本；Task 2-4 只改 `scripts/ci/merge_queue.py` 与 `scripts/ci/github_queue_api.py` 内部的分类、清理与预算逻辑，全部经由现有 `QueueClient` 协议注入的 fake 做无网络 TDD。PR #226（queue run `32454019824`，2026-08-21）的真实时间线是回归场景与验收证据的来源。

**Tech Stack:** Python 3 standard library、`unittest`、现有 `tests/build/ci_merge_queue_test.py` / `ci_merge_queue_api_test.py` fake 基础设施、GitHub REST（仅 Task 4 新增一个 cancel endpoint 调用）、Markdown 治理文档。

## Version Management

- Version impact: **none**。`scripts/ci/merge_queue.py`、`scripts/ci/github_queue_api.py` 与 `docs/governance/git-workflow.md` 都是 repository CI/治理工具，不属于任何 Core Module、Provider、Contract 或 Product Assembly；不产生 Product Build、Module SemVer 或 Contract SemVer 变化，不触碰 `products/lmdj/version.json`。

## Documentation impact

- Task 1: **required** — `docs/governance/git-workflow.md`（§Serialized Integration Queue）。Portal routes: none — 该文件不是 Architecture Portal 页面，不涉及 Product/Module/Host/Provider/Contract/Channel 身份或 manifest 派生内容；提交前仍运行 `scripts/architecture-portal.sh check`。
- Task 2-4: **none** — 控制器内部分类、清理与预算行为；`git-workflow.md` 中已有的队列描述（终止失败摘标签并留一条稳定评论、三次 attempt、超时语义）在变更后仍然为真，本计划反而使第 3 条承诺真正可靠。若实现中发现描述失真，在同一 Task 内修正该段落并升级声明。

## Regression scenario: the PR #226 timeline

所有 Task 的测试以下列真实事件为对照（Issue #230 有完整表格与 artifact 证据）：

| UTC | 事件 |
| --- | --- |
| 06:20:42 | queue item 启动；attempt 1 dispatch `mq:32454019824:1`（run `32454042424`）|
| 06:24:52 | #227 经普通路径合入 `main` → base drift 1，26 分钟验证作废 |
| 06:47:15 | attempt 2 复用 synchronize run `32455825672` |
| 07:00:47 | #228 经普通路径合入 `main` → base drift 2 |
| 07:10:19 | 终止：`required-check-contract-mismatch`、`attempts: 2`、evidence 仅 `cleanup-error:GitHubApiError`；标签已摘但 PR 上没有失败评论 |

验收证据：实现合并后，下一次真实队列终止失败必须在 PR 评论或 run summary 中直接给出可行动原因，无需下载 artifact 或阅读源码。

## Global Constraints

- 每个 Task 是一个独立可评审的 Conventional Commit；**Task 1（治理规则）与 Task 2-4（控制器行为）是分开的提交边界与分支**，不得合并成一个提交。
- Task 2-4 修改 `scripts/ci/merge_queue.py` / `scripts/ci/github_queue_api.py`，属于控制平面变更：其 PR **不得**使用队列自合并，走普通保护合并路径（`git-workflow.md` §Serialized Integration Queue 控制平面条款）。
- 不改变：串行单槽设计、`lmdj-merge-main` 并发组、`queue: max`、FIFO 启动顺序、synchronize 运行复用、`MAX_ATTEMPTS = 3`、`MUTATION_WINDOW_SECONDS`、squash payload、post-merge reconciliation 协议、`QueueReport` 的 JSON 字段集合。
- 不修改 `.github/workflows/merge-queue.yml`、`.github/workflows/ci.yml`、`scripts/ci/change_scope.py`、`scripts/ci/pr_gate.py`、`scripts/ci/scope_policy.json`、`scripts/ci/merge_queue_watchdog.py`。
- 所有新失败证据字符串只包含：已知 check 名、稳定操作名（`remove-label` / `comment`）、异常类型名、整数秒数与 run id；禁止拼接 raw API response body、URL、token 或路径。
- 测试全部无网络：通过 `run_queue_item` / `finalize_aborted` / `run_cli` 的注入点使用 fake `QueueClient`、`FakeClock` 与注入 sleeper；`github_queue_api` 层用现有 `ci_merge_queue_api_test.py` 的 fake transport 风格。
- 不操作当前在队 PR（#229、重新入队的 #226），不取消 run `32455825672` 的 rerun，不 re-run、dispatch、approve 任何真实 workflow；对真实仓库只做只读观察。
- Local commit 不授权 push、Pull Request、merge、tag、Release、deployment 或 Channel mutation。

---

### Task 1: 收紧非控制平面 PR 的队列治理规则

**Branch:** `docs/issue-230-queue-mixed-path-rule`（独立于 Task 2-4 的实现分支）

**Files:**

- Modify: `docs/governance/git-workflow.md`（§Serialized Integration Queue，队列启用后的使用规则段落）

**Interfaces:**

- Consumes: 现有段落"After enablement, adding `merge:queue` is an explicit, revocable authorization…"与控制平面条款。
- Produces: 一个新的路径选择规则段落；不改变任何既有规则的语义，只补充缺失的一条。

- [ ] **Step 1:** 在"After enablement…"段落之后新增一段规则，内容要点（措辞融入现有文风，英文）：
  - 队列启用后，**队列是所有非控制平面 PR 合入 `main` 的默认路径**；
  - 当队列被占用（存在 queued 或 in-progress 的 `lmdj-merge-main` 队列项）时，**禁止对非控制平面 PR 使用普通手工合并**——每一次这样的合并都会给每个在队 PR 制造一次 confirmed base drift，消耗其三次 attempt 之一并作废一条进行中的全量验证；
  - 普通保护路径保留给：控制平面 PR（本已强制）、以及队列证明不可用时按 §emergency 语义显式记录的例外；
  - 引用 PR #226 / Issue #230 作为动机证据（一句话，不复制时间线）。
- [ ] **Step 2:** 校验该段与既有控制平面条款、watchdog 段落无语义冲突；`grep -n "merge:queue" docs/governance/git-workflow.md` 确认无重复规则。
- [ ] **Step 3:** 运行 `scripts/architecture-portal.sh check` 与 `scripts/local-ci.sh --list`（预期只选 docs/static 类 lane），按选择结果运行。
- [ ] **Step 4:** 单文件提交：`docs(governance): require the queue for non-control-plane merges while it is occupied`。检查提交文件列表与最终 worktree 状态。

**Tests:** 无代码测试；验证即 Step 2-3。

---

### Task 2: 区分 validation-failed 与合同错配，并输出 expected/observed 差异

**Branch:** `fix/issue-230-merge-queue-diagnosability`（Task 2-4 共用，每 Task 一个提交）

**Files:**

- Modify: `scripts/ci/merge_queue.py`（`_validation_contract_error`，约 261-287 行；调用点约 490-497 行）
- Test: `tests/build/ci_merge_queue_test.py`（现有 `test_validation_is_bound_to_exact_run_and_required_checks` 一族旁）

**Interfaces:**

- Consumes: `ValidationResult.required_checks`（`(name, app_id, conclusion)` 元组集合来源）、`REQUIRED_CHECKS`（`merge_queue.py:30`）、`GITHUB_ACTIONS_APP_ID`、`_stop(..., evidence=...)`。
- Produces: `_validation_contract_error` 返回类型从 `str | None` 变为 `tuple[str, tuple[str, ...]] | None`（code + evidence）；对外 `QueueReport` schema 不变，只是 `evidence` 现在被填充。

分类规则（新）：

- 每个 `REQUIRED_CHECKS` 名字在 observed 中**存在、app 正确、但 conclusion 不是 `success`**（failure/cancelled/skipped/timed_out/None）→ code `validation-failed`，evidence 形如 `check:PR Gate=failure`。这是"CI 挂了"，不是合同问题。
- required check **缺失**、app_id 非 `15368`、或 observed 集合含非预期的重复项 → code 保持 `required-check-contract-mismatch`，evidence 形如 `missing:core (macos-latest)` / `app:PR Gate=12345` / `duplicate:PR Gate`。
- run 级字段（event/path/head/base/ticket/manifest_mode/trusted_head）与 run conclusion 的既有 `validation-failed` 判定不变，但补 evidence 命名失配字段，形如 `field:manifest_mode=focused`。
- 全部匹配 → 仍返回 `None`。

- [ ] **Step 1（RED）:** 新增测试：
  - `test_failed_required_check_is_validation_failed_and_named`：fake validation 返回 `("PR Gate", 15368, "failure")` → report code `validation-failed`，evidence 含 `check:PR Gate=failure`；断言**不再**是 `required-check-contract-mismatch`（#226 回归：attempt 2 的这类结果曾被报成合同错配）。
  - `test_missing_required_check_is_a_contract_mismatch_with_diff`：observed 缺 `core (macos-latest)` → code 不变，evidence 含 `missing:core (macos-latest)`。
  - `test_foreign_app_check_is_a_contract_mismatch_with_diff`：app_id 错 → evidence 含 `app:` 条目。
  - `test_run_field_mismatch_names_the_field`：`manifest_mode="focused"` → `validation-failed` 且 evidence 含 `field:manifest_mode=focused`。
  - 既有成功路径测试全绿（合同满足时行为不变）。
- [ ] **Step 2（GREEN）:** 实现上述分类与 evidence 构造；调用点把返回的 evidence 传入 `_stop`。
- [ ] **Step 3:** 断言 evidence 只含白名单词形（测试内正则），确保无 raw response 泄漏。
- [ ] **Step 4:** `python3 -m unittest tests.build.ci_merge_queue_test -v` 全绿；提交 `fix(ci): classify failed checks apart from contract mismatch and emit the diff`。

---

### Task 3: 终止清理加重试与退避，评论失败时可见降级

**Files:**

- Modify: `scripts/ci/merge_queue.py`（`_cleanup_failure`，约 211-236 行；`finalize_aborted` 约 619-634 行经同一路径受益）
- Test: `tests/build/ci_merge_queue_test.py`

**Interfaces:**

- Consumes: `QueueClient.remove_label` / `create_review_comment` / `get_pull`、注入的 `sleeper`（`run_queue_item` 与 `run_cli` 已有该注入点，需把它传递进 `_stop`/`_cleanup_failure`——保持默认参数向后兼容）。
- Produces: 行为变化——两个清理操作**各自独立** try + 至多 3 次尝试、固定退避（如 2s/4s，经注入 sleeper，测试中零耗时）；每个最终失败的操作以 `cleanup-error:<operation>:<ExceptionType>` 记入 evidence（替代现在不带操作名的 `cleanup-error:<ExceptionType>`）；一个操作失败不阻止另一个操作执行。`render_markdown` 增补一行 `- Evidence: ...`（仅在非空时），使 run summary 在评论丢失时仍然给出终止原因——这是降级通道。

- [ ] **Step 1（RED）:** 新增测试：
  - `test_cleanup_retries_transient_errors_with_backoff`：fake client 前两次 `create_review_comment` 抛错、第三次成功 → 评论最终存在，evidence 无 cleanup-error，sleeper 收到两次退避调用。
  - `test_comment_loss_never_blocks_label_removal_and_is_named`（#226 回归）：`create_review_comment` 永久抛 `GitHubApiError` → 标签仍被摘除，evidence 含 `cleanup-error:comment:GitHubApiError`，report 主 code 不被覆盖。
  - `test_label_removal_failure_still_attempts_the_comment`：对称场景。
  - `test_summary_carries_evidence_when_cleanup_degrades`：`render_markdown` 输出包含 evidence 行。
  - 更新既有 `test_finalize_aborted_is_idempotent_and_revokes_live_authority` 如其对旧 evidence 形状有断言。
- [ ] **Step 2（GREEN）:** 实现独立重试、操作名 evidence 与 summary 降级；`finalize_aborted` 无需改动即经 `_stop` 获得同样行为，用测试证明。
- [ ] **Step 3:** `python3 -m unittest tests.build.ci_merge_queue_test -v` 全绿；提交 `fix(ci): retry queue cleanup independently and surface degraded evidence`。

---

### Task 4: 提高 attempt 最低预算，超时后取消孤儿验证运行

**Files:**

- Modify: `scripts/ci/merge_queue.py`（`MINIMUM_ATTEMPT_SECONDS`，24 行；`validation-timeout` 终止路径，约 466-471 行；`QueueClient` 协议）
- Modify: `scripts/ci/github_queue_api.py`（`GitHubQueueClient` 新增 cancel 方法）
- Test: `tests/build/ci_merge_queue_test.py`、`tests/build/ci_merge_queue_api_test.py`

**Interfaces:**

- Consumes: 实测全量验证时长（#226 attempt 1 = 26m13s；迁移后全量 ~15-26 min）、`validation_budget_seconds()`（177-189 行）。
- Produces:
  - `MINIMUM_ATTEMPT_SECONDS = 30 * 60`——低于实测 P90 上界的 attempt 不再启动（`MUTATION_WINDOW_SECONDS = 330*60` 下三次 attempt 预算依旧充裕：`(330-10)/3 ≈ 106 min/attempt`）。
  - `QueueClient.cancel_validation(run_id: int) -> None` 协议方法；`GitHubQueueClient` 实现为 `POST /actions/runs/{run_id}/cancel`（best-effort：取消失败只追加 evidence `cancel-error:<ExceptionType>`，不改变终止 code）。
  - `validation-timeout` 终止路径在 `_stop` 之前对**本次 attempt 的 run_id** 调用 cancel。仅取消 controller 自己 dispatch 的 `workflow_dispatch` 验证运行；**synchronize（`pull_request`）运行不取消**——它属于 PR 事件本身，后续 attempt 或人工诊断可能还要读它。
  - `queue-budget-exhausted` 语义不变（该路径尚未 dispatch，无可取消对象）。

- [ ] **Step 1（RED）:** 新增/更新测试：
  - 更新 `test_dynamic_budget_reserves_reconciliation_time` / `test_budget_exhaustion_starts_no_mutation` 的时钟常量以匹配 30 分钟下限，并新增 `test_attempt_below_measured_validation_floor_never_dispatches`：FakeClock 使剩余预算为 29 分钟 → `queue-budget-exhausted`，fake client 记录零次 dispatch。
  - `test_validation_timeout_cancels_the_dispatched_orphan`：dispatch 路径超时 → fake client 记录一次 `cancel_validation(run_id)`，code 仍为 `validation-timeout`。
  - `test_validation_timeout_never_cancels_a_synchronize_run`：synchronize 路径超时 → 零次 cancel。
  - `test_cancel_failure_is_evidence_not_a_new_code`：cancel 抛错 → evidence 含 `cancel-error:`，code 不变。
  - `ci_merge_queue_api_test.py`：`cancel_validation` 发出确切的 `POST /repos/<repo>/actions/runs/<id>/cancel`，非 2xx 抛 `GitHubApiError`。
- [ ] **Step 2（GREEN）:** 实现常量、协议方法、API 调用与超时路径接线。
- [ ] **Step 3:** `python3 -m unittest tests.build.ci_merge_queue_test tests.build.ci_merge_queue_api_test -v` 全绿；提交 `fix(ci): raise the attempt floor to the measured validation cost and cancel orphans`。

---

## 完成与验收

- [ ] 四个提交各自通过 `scripts/local-ci.sh`（按 change scope 自动选 lane；Task 2-4 预期含 CI contract lane），提交前逐一执行 §4 的 staged-diff 检查清单。
- [ ] Task 2-4 的 PR body 声明 `Documentation impact: none`（理由如上）与 `Version impact: none`，并显式声明**不使用队列自合并**。
- [ ] 验收证据（合并后，只读观察）：下一次真实终止失败的 PR 评论/run summary 直接可读出失败操作与 check 差异；出现混合路径合并的教育案例时引用 Task 1 的规则段落。
- [ ] Issue #230 在四个 PR 全部合并、且验收证据出现后关闭。
