# LMDJ Serialized Integration Queue Design

日期：2026-08-20

状态：规格已批准

## 1. 结论

LMDJ 在当前个人账户私有仓库中实现一个仓库拥有、标签授权、串行执行、默认
fail closed 的 Integration Queue。对 Pull Request 添加精确标签 `merge:queue`
就是一次可撤销的自动 squash merge 授权；队列一次只处理一个以 `main` 为目标的
同仓库 Pull Request，并且只在以下事实同时成立时合并：

- 入队操作者拥有 `write`、`maintain` 或 `admin` 仓库权限；
- Pull Request 仍然 open、非 Draft、同仓库、以 `main` 为 base，并且标签仍存在；
- Pull Request branch 已合入当前 exact `main` SHA；
- 一个由队列显式启动、绑定 exact base/head 与队列票据的 full `Core CI` run 完成且
  `PR Gate` 成功；
- 合并前重新读取的 `main`、Pull Request head、标签与验证 run 仍与已验证事实一致；
- GitHub 的受保护分支检查接受带 expected head SHA 的 squash merge 请求。

队列不把普通并发限制冒充合并正确性。PR 日常 CI 继续并行提供反馈；队列只串行化
最终 integration validation 与 merge mutation。普通 `main` push 仍按 exact SHA
独立运行，release 所需 exact-main full evidence 仍通过既有显式流程取得。

```text
write-capable actor applies merge:queue
                 |
                 v
       fixed main integration queue
                 |
                 v
       eligibility + live-state check
                 |
                 v
 update PR branch from exact current main
                 |
                 v
 dispatch exact full Core CI and receive run ID
                 |
                 v
 wait for same-run PR Gate + recheck live state
                 |
        +--------+--------+
        | drift           | stable
        v                 v
 re-sync and retry   squash merge exact head
   at most 3 times          |
                            v
                 verify merged PR/main/tree
```

## 2. 背景与约束

当前 `.github/workflows/ci.yml` 按 Pull Request number 隔离 PR concurrency，按 SHA
隔离 `main` concurrency。同一 PR 的新提交会取消旧运行，但不同 PR 与不同 `main`
SHA 可以同时执行。`main` 保护规则要求 branch up to date，但仓库没有原生 Merge
Queue，也没有 `merge_group` workflow 入口。结果是前一个 PR 合并后，后续 PR 需要
更新 base 并重新验证，而多个 PR/main run 同时争用有限的 self-hosted runners。

GitHub 原生 Merge Queue 当前只适用于组织拥有的公开仓库，或 GitHub Enterprise
Cloud 组织拥有的私有仓库；`endaye/lmdj` 是个人账户私有仓库，因此本设计不依赖该
功能。仓库未来迁移到可用组织后，可以用原生 Merge Queue 取代本控制器，但迁移前
两套队列不得同时拥有 merge authority。

本设计还受以下既有治理约束：

- `main` 必须保持 deployable，正常变更使用短生命周期 Task branch、PR 与 squash merge；
- Required Checks、PR Gate、exact-main Proof、release、deployment 与 Channel promotion
  是不同证据和授权边界；
- self-hosted runners 只运行可信同仓库 head；
- `main` 每个 SHA 的 CI 不自动取消，focused main CI 也不等于 release full evidence；
- workflow、scope classifier、PR Gate 与本地 preflight 必须保持一个闭合、可测试的
  CI control contract；
- 自动提交本地代码不授权 push、创建 PR、远端 label、branch protection 修改或启用
  自动合并能力。

## 3. 目标

- 用 `merge:queue` 标签建立明确、可审计、可撤销的自动合并授权。
- 让多个待合并 PR 在一个固定 queue 中有界等待，而不是同时占用 integration capacity。
- 自动把待处理 PR 更新到最新 `main`，并对 exact integration head 运行 full Core CI。
- 绑定队列票据、PR number、base SHA、head SHA、workflow run ID 与 same-run `PR Gate`。
- 在 base/head 漂移时重新同步并重新验证，绝不消费旧成功结果。
- 在冲突、CI failure、timeout、权限不足、标签撤销或 API 不确定状态时 fail closed。
- 只使用最小 `GITHUB_TOKEN` 权限，不引入长期 PAT、个人 cookie 或新的 secret。
- 保留现有 PR feedback CI、focused main CI 与 exact-main release evidence 语义。
- 给状态机、GitHub API 边界、workflow topology、权限与竞态提供确定性测试。

## 4. 非目标

本设计不包含：

- 将仓库迁移到 GitHub Organization 或购买 GitHub Enterprise Cloud；
- 启用 GitHub 原生 Merge Queue、Auto-merge 或 `merge_group`；
- 自动给任何 PR 添加 `merge:queue`；
- 把 review、产品验收、版本分配、release、deployment 或 Channel promotion 授权隐含在
  queue label 中；
- 运行或合并来自 fork 的代码；
- 绕过 Required Checks、branch protection、conversation resolution 或 exact SHA 校验；
- 取消旧 `main` CI、复用 PR CI 作为 release evidence，或弱化 exact-main Proof；
- 自动解决 merge conflict、修改 PR 产品代码、force-push 或重写共享历史；
- 在自动合并失败后回滚、force-update 或删除 `main` 历史；
- 批量合并多个 PR 为一个 Git commit；每个 PR 仍产生一个独立 squash merge commit。

## 5. 核心决策

| ID | 决策 |
| --- | --- |
| D1 | `merge:queue` 是唯一自动入队入口；添加标签就是自动 squash merge 授权，移除标签就是撤销授权。 |
| D2 | 控制 workflow 使用 `pull_request_target:labeled`，只 checkout 默认分支控制代码，不 checkout 或执行事件中的 PR 代码。 |
| D3 | 一个固定 `main` concurrency group 使用 `queue: max` 保留最多 100 个 pending runs；不使用 `cancel-in-progress`。 |
| D4 | 入队 actor 必须经实时 API 解析为 `write`、`maintain` 或 `admin`，PR 必须为同仓库、open、非 Draft、base=`main`。 |
| D5 | 队列用 update-branch API 的 `expected_head_sha` 把 current `main` 合入 PR branch，不创建临时 integration branch。 |
| D6 | 队列使用 2026-03-10 REST API 显式 dispatch `ci.yml`，直接接收并记录 `workflow_run_id`，不通过轮询猜 run identity。 |
| D7 | queue validation dispatch 必须是 full，并完整绑定 ticket、PR number、base SHA 与 head SHA；普通手动 dispatch 语义保持不变。 |
| D8 | validation run 必须在 same run 内成功产生 Change Scope、所有 full lanes 与 `PR Gate`；不拼接其他 run 的 check results。 |
| D9 | base/head 漂移最多重新同步和完整验证三次；三次后仍漂移是 terminal failure。 |
| D10 | 合并调用必须指定 exact expected head SHA 与 `squash`；调用前后都核验 canonical repository state。 |
| D11 | CI failure、conflict、timeout、撤权和不确定 mutation 一律不重试 merge；先 reconciliation，再输出稳定 failure code。 |
| D12 | 控制面只使用 `actions: write`、`contents: write`、`pull-requests: write`；不引入 PAT 或 GitHub App secret。 |
| D13 | `main` push 的 per-SHA、non-cancelling concurrency 与 release exact-main evidence 保持不变。 |
| D14 | actionlint 升级到已验证支持 `concurrency.queue` 的 `1.7.12`，继续校验下载 digest 与完整 workflow contract。 |

## 6. 组件与文件边界

### 6.1 Merge Queue workflow

新增 `.github/workflows/merge-queue.yml`，职责仅包括：

- 监听 `pull_request_target` 的 `labeled` activity，并只接受 label `merge:queue`；
- 在 GitHub-hosted Ubuntu 上进入固定 `lmdj-merge-main` concurrency group；
- 使用 `queue: max`，不取消 running 或 pending queue items；
- checkout canonical default-branch control code，`persist-credentials: false`；
- 将 event actor、PR number、event head SHA、repository 与 workflow run identity 传给
  queue controller；
- 授予 controller 所需的最小 workflow permissions；
- 将 controller 的结构化 report 写入 `GITHUB_STEP_SUMMARY`。

workflow 不解析产品文件、不运行 PR shell、不持有 deployment/release secrets，也不直接
在 YAML shell 中复制状态机。

### 6.2 Queue controller

新增 `scripts/ci/merge_queue.py`。它拥有全部 queue semantics，并通过一个窄的
`GitHubClient` 接口访问远端。核心接口返回闭合 report，而不是依赖异常文本作为状态：

```text
run_queue_item(request: QueueRequest, client: GitHubClient) -> QueueReport
```

`QueueRequest` 至少包含 canonical repository、PR number、event actor、event head SHA、
queue workflow run ID 与最大三次 validation attempts。`QueueReport` 至少包含 terminal
status、stable code、attempt count、observed base/head、validation run IDs、merge SHA、
message 与 reconciliation evidence。

`GitHubClient` 只暴露 controller 需要的操作：读取 repository/actor permission/PR/ref，
更新 PR branch，dispatch workflow 并取得 run ID，读取 run/jobs/checks，读取 Git commit
tree，执行 exact-head squash merge，以及在 Pull Request 上移除 queue label、留下一个
COMMENT review。HTTP transport、API version、bounded retry 与 response schema validation
全部封装在该边界内。

### 6.3 Core CI queue-validation mode

修改 `.github/workflows/ci.yml` 与 `scripts/ci/change_scope.py`，在既有
`workflow_dispatch` 上增加一组全有或全无的 queue inputs：

- `queue_ticket`
- `queue_pr_number`
- `queue_base_sha`
- `queue_head_sha`

普通操作者不提供这些 inputs 时，现有空 lanes=full 与显式 lanes=focused 语义完全不变。
一旦提供任一 queue input，Change Scope 必须 fail closed 地要求全部字段合法，并实时验证：

- dispatch ref 实际解析到 `queue_head_sha`；
- PR number 指向 canonical repository 的 open、非 Draft、同仓库 PR；
- PR base 为 `main` 且 base SHA 精确为 `queue_base_sha`；
- PR head 精确为 `queue_head_sha`；
- `queue_base_sha` 是 `queue_head_sha` 的 ancestor；
- queue label 仍存在；
- requested lanes 为空，因此 manifest mode 为 `full`。

Change Scope 从实时 PR 响应输出文档影响检查需要的 PR body；Portal reusable job 在 queue
mode 中与普通 PR event 一样校验该 body 和 exact base/head diff。Manifest 记录 queue
metadata，使 `PR Gate` 可以验证 same-run manifest 与 dispatch inputs 一致。

Core CI 增加包含 queue ticket 的 `run-name`，但 controller 只信 dispatch API 直接返回的
numeric run ID。显示名称只用于人工诊断，不参与 identity 判定。

### 6.4 Contract tests and governance

新增 `tests/build/ci_merge_queue_test.py`，覆盖 controller 与 workflow contract；扩展既有
`ci_change_scope_test.py`、`ci_pr_gate_test.py`、`ci_workflow_topology_test.py`、
`ci_runner_fallback_test.py` 和 local preflight contract，使 queue mode 不能绕过现有闭合
truth table。

修改 `docs/governance/git-workflow.md` 与 Portal current route
`/operations/testing-and-proof/`，说明标签授权、FIFO 边界、失败恢复、main CI 与 release
evidence 的区别，以及远端启用步骤。

## 7. 状态机与数据流

状态集合是闭合的：

```text
requested
  -> eligible
  -> synchronizing
  -> validating
  -> ready
  -> merging
  -> merged

requested|eligible|synchronizing|validating|ready
  -> cancelled | blocked

merging
  -> merged | blocked-after-reconciliation
```

### 7.1 Requested and eligible

workflow 只在 label name 精确为 `merge:queue` 时进入 controller。Controller 重新读取 actor
permission 和 PR，而不是相信 event payload 的可变字段。以下任一条件使请求 blocked：

- actor 权限不在 `write|maintain|admin`；
- PR closed、Draft、base 不是 `main`、head 来自 fork，或 repository identity 不匹配；
- event head SHA 与 controller 首次读取的 PR head 不一致；
- queue label 已不存在；
- PR mergeability 是 conflict，或 GitHub 在有界等待后仍不能计算 mergeability。

标签是 merge authorization，不是 review approval。Branch protection 的 review、conversation
resolution 与 Required Checks 仍由 GitHub 在最终 merge API 上强制执行。

### 7.2 Synchronizing

每次 attempt 先读取 current `main` SHA 与 PR head SHA。若 current main 不是 head 的
ancestor，controller 调用 update-branch，并传入 `expected_head_sha`。202 response 只表示
mutation accepted；controller 必须轮询 PR，直到 head 更新且 captured main 成为 ancestor，
或有界超时。若 head 在请求前已变化，422 被分类为 drift，并从实时状态开始下一 attempt，
不能盲目重发 mutation。

同步完成后记录：

```text
attempt N
base_sha = exact current main
head_sha = exact synchronized PR head
head_tree = Git tree of head_sha
ticket = mq:<queue-workflow-run-id>:<attempt>
```

### 7.3 Validating

controller 使用 `actions: write` 对 PR head branch 显式 dispatch `ci.yml`，空 `lanes` 加完整
queue inputs，并使用 GitHub REST API version `2026-03-10` 返回的
`workflow_run_id` 作为唯一 run identity。随后只等待该 run：

- run `event=workflow_dispatch`、workflow path=`.github/workflows/ci.yml`；
- run `head_sha` 精确等于 attempt head；
- run completed/success；
- same run 的 `Change Scope` 与 `PR Gate` completed/success；
- manifest 为 full、trusted head、exact queue ticket/base/head；
- full mode 所有正式 lanes 的 same-run result 通过既有 PR Gate adjudication。

validation attempt 上限为 120 分钟，queue worker job 上限为 360 分钟。API 轮询使用有界
间隔并尊重 rate-limit response；标签每轮都重新读取，标签移除立即转为 cancelled。

### 7.4 Ready and drift handling

validation 成功后，controller 重新读取 current main、PR head、label、PR state 和 validation
run。若 main 或 head 与 attempt 不同，不允许合并；在还剩 attempt budget 时回到
synchronizing，否则以 `unstable-after-three-validations` blocked。Draft、closed、label
removed 或 base changed 直接终止，不自动修改用户选择。

只要所有事实稳定，controller 进入 ready。它不会把以前的普通 PR run、另一个 full run、
同名 check 或旧 main run 替代当前 validation run。

### 7.5 Merging and postcondition verification

controller 使用 `contents: write` 调用 Pull Request merge API，明确指定：

```text
merge_method = squash
sha = exact validated PR head SHA
```

调用前最后一次读取 main/head/label；调用由 branch protection 原子裁决。如果 main 在最后
读取与 mutation 之间前进，strict branch protection 应拒绝 behind head，controller 先
reconcile remote state，再决定进入下一 attempt 或 blocked，不能假设请求失败就表示没有
mutation。

成功 response 后必须验证：

- PR `merged=true` 且 merge commit SHA 等于 response SHA；
- canonical `main` ref 指向该 merge SHA；
- merge commit 是验证 base 的后继；
- merge commit tree 等于 validation head tree；
- queue label 不再构成任何后续 merge authority。

postcondition 不一致发生在 mutation 之后，不能自动回滚或 force-update main；controller
报告 `blocked-after-reconciliation`，保留 exact response、PR/main SHA 与 tree evidence，交由
incident owner 处理。

## 8. Failure、取消与恢复

稳定 terminal code 至少包括：

- `unauthorized-actor`
- `ineligible-pr`
- `queue-label-removed`
- `merge-conflict`
- `update-branch-timeout`
- `validation-dispatch-failed`
- `validation-timeout`
- `validation-failed`
- `unstable-after-three-validations`
- `merge-rejected`
- `merge-state-uncertain`
- `postcondition-mismatch`

除用户主动移除标签导致的 `queue-label-removed` 外，terminal failure 会：

1. reconcile PR、main 与可能的 merge result；
2. 如果 PR 仍 open，移除 `merge:queue`，避免旧授权被无意复用；
3. 使用 `pull-requests: write` 创建一个 `COMMENT` review，记录 stable code、queue run URL、
   validation run URL、observed base/head 与安全重试方法；
4. 以 non-zero 结束 queue workflow。

安全重试只能在问题修复后重新添加 `merge:queue`。Controller 不自动重新加标签，不把失败
转换为 manual merge，也不更改产品代码。

读取 API 的 transport failure、5xx 与 secondary rate limit 可以有界重试。任何 mutation
调用发生 timeout、连接断开或不确定 response 时，必须先通过读取 canonical state 判断操作
是否已经发生，再决定下一步；禁止无 reconciliation 的重复 update 或 merge。

## 9. Security model

- `pull_request_target` 只执行已合入默认分支的 workflow/controller，不 checkout PR head。
- fork PR 在任何 self-hosted 或 mutation 操作前被拒绝。
- event actor、repository、PR、base/head、label 与 run identity 全部实时验证。
- 用户可控字符串不拼接 shell command；GitHub API 参数使用结构化 JSON。
- workflow token 只授予 `actions: write`、`contents: write`、`pull-requests: write`；无
  deployments、environments、packages、secrets、id-token 或 administration 权限。
- queue workflow 运行在 GitHub-hosted Ubuntu；PR 代码只在既有 trusted-head Core CI lanes
  中执行。
- workflow dispatch ticket 不是 secret。伪造 ticket 最多产生 CI，不会被 controller 接受，
  因为 controller 绑定 dispatch API 返回的 numeric run ID。
- merge mutation 依赖 exact expected head、strict branch protection 与 Required Checks；
  controller 不拥有绕过规则的管理员 token。
- review comment、summary 与 test fixture 不记录 token、authorization header 或私有 API body。

## 10. Verification strategy

实现严格使用 red-green-refactor。Queue controller 的每个状态转换先由 fake
`GitHubClient` 驱动失败测试，再写最小实现。测试不访问 live GitHub，也不产生远端 mutation。

最低自动化覆盖：

- authorized label request enters one fixed FIFO queue；
- unauthorized actor、fork、Draft、wrong base、missing label 全部 fail closed；
- expected-head update success、422 drift、conflict、timeout 与 uncertain response reconciliation；
- dispatch response 的 exact numeric run ID 被保存，其他同 SHA/同名 run 被忽略；
- queue validation inputs 全有或全无、full-only、exact base/head 与 PR body impact check；
- same-run Change Scope/PR Gate success 才能进入 ready；
- CI failure、timeout、cancel、head/main drift 与三次 attempt budget；
- 标签在 pending、sync、poll 和 pre-merge 时移除都不会 merge；
- exact-head squash request、strict rejection、successful postconditions 与 tree mismatch incident；
- mutation uncertainty 不会盲目重复 merge；
- workflow 使用 `pull_request_target:labeled`、fixed concurrency、`queue: max`、hosted runner、
  canonical checkout 与 exact minimal permissions；
- actionlint `1.7.12` archive digest、workflow syntax 与 literal self-hosted labels；
- local preflight、scope policy、Portal impact 与 workflow CI contract 保持一致。

Task-specific verification 至少运行：

```bash
python3 tests/build/ci_merge_queue_test.py
python3 tests/build/ci_change_scope_test.py
python3 tests/build/ci_pr_gate_test.py
python3 tests/build/ci_workflow_topology_test.py
python3 tests/build/ci_runner_fallback_test.py
python3 tests/build/ci_local_preflight_test.py
bash tests/build/test_active_tree.sh
bash scripts/verify-core-dependencies.sh
scripts/architecture-portal.sh check
```

实施 PR 必须选择 full CI，因为它改变 central CI control、workflow permissions 与 merge
authority。Local tests、commit、push、PR、CI、远端 label 创建、branch protection 修改、queue
启用和首次自动 merge 分别报告，不互相推断。

## 11. Version Management

Version impact: none。

原因：该 Task 只改变 GitHub/CI integration control 与治理，不改变 Product Build、Core
Module、Host、Provider、Contract、Product Assembly、public API 或运行时行为，不分配任何
Product Build，也不创建 Architecture Portal snapshot。

## 12. Documentation Impact

Documentation impact: required

Affected portal pages: `/operations/testing-and-proof/`

Reason: Integration Queue 改变 Pull Request CI、自动 merge authority、失败恢复与证据边界。
实施 Task 必须同步更新 `docs/governance/git-workflow.md` 与上述 current Portal route；不修改
冻结的历史版本页面，不创建 Product Build snapshot。

## 13. 远端启用与验收边界

仓库代码合入本身不会启用队列。远端 rollout 分成独立授权与证据边界：

1. implementation PR 在 full CI 与 review 通过后，由单独授权 squash merge；
2. 验证 exact merged-main CI，不能从 PR CI 推断；
3. 单独授权创建 label `merge:queue`，记录 exact name、description 与 color；
4. 单独授权确认 `main` strict required checks、conversation resolution 与 admin enforcement，
   不删除或弱化 Required Checks；
5. 用一个无产品风险的同仓库 test PR 做首次 queue validation，只在显式添加 label 后启动；
6. 记录 queue run ID、validation run ID、runner assignment、base/head、merge SHA、tree equality、
   resulting main CI 与 label state；
7. 首次验收成功后才把 queue 作为日常 merge 路径。

任何边界失败都停止在当前状态。Implementation commit 不授权 push；push 不授权 PR；PR 不
授权 merge；merge 不授权 label/branch protection 修改；remote configuration 不授权首次
自动 merge；首次 merge 不授权 release、deployment、publication 或 Channel promotion。
