# LMDJ Serialized Integration Queue Design

日期：2026-08-20；review 修订：2026-08-21

状态：规格已批准；implementation 与远端 PR/全绿后 squash merge 已授权

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
 bind + approve the exact generated PR CI run
 (or dispatch exact full CI when no sync was needed)
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

### 2.1 外部事实证据

以下外部能力是设计支点，证据于 2026-08-21 验证；远端启用前必须在 live repository
重新执行第 13 节 preflight，不能只依赖本表：

| 事实 | 官方证据 | 设计后果 |
| --- | --- | --- |
| `concurrency.queue: max` 保留最多 100 个 pending runs；默认 `single` 只有一个 pending 且新 run 会替换旧 run | [GitHub Actions concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency) | workflow 必须使用 `queue: max`；live probe 失败即不创建 label、不启用队列 |
| REST API version `2026-03-10` 的 workflow dispatch 成功响应为 `200`，body 含 numeric `workflow_run_id` | [Create a workflow dispatch event](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event) | controller 只绑定 response 中的 run ID；schema 不匹配时 `validation-dispatch-contract-mismatch`，不轮询猜测 |
| actionlint `1.7.12` 尚不能解析 `concurrency.queue`，会报告精确错误 `unexpected key "queue" for "concurrency" section` | [actionlint v1.7.12](https://github.com/rhysd/actionlint/releases/tag/v1.7.12)、[官方 checksums](https://github.com/rhysd/actionlint/releases/download/v1.7.12/actionlint_1.7.12_checksums.txt) 与 upstream [issue #657](https://github.com/rhysd/actionlint/issues/657)；真实 binary probe 复现该唯一 schema lag | CI pin 与 digest 一起升级；只忽略这一条精确错误，repository contract 另断言全仓恰好一个 `queue: max`，其余 actionlint 错误仍失败；upstream 支持后删除例外 |
| workflow 使用 `GITHUB_TOKEN` 更新 PR 时，`pull_request:synchronize` 会创建 approval-required run；`Actions: write` token 可调用批准端点 | [GITHUB_TOKEN event exceptions](https://docs.github.com/en/actions/concepts/security/github_token#when-github_token-triggers-workflow-runs)、[Approve a workflow run](https://docs.github.com/en/rest/actions/workflow-runs#approve-a-workflow-run-for-a-fork-pull-request)；2026-08-21 live rollout 以 PR #222/run `32436012836` 复现 | update-branch 后 controller 必须绑定 exact PR/head/bot run、显式批准并把它作为唯一 full validation；PR 已经 up to date 时才使用显式 dispatch |

GitHub 对 `queue: max` 的顺序保证是“按 run 开始等待的时间 FIFO”，不是事件产生或 API
dispatch 的绝对时间。本文的 FIFO 均指这个平台定义；controller 不声称提供跨平台事件的
更强全序。

## 3. 目标

- 用 `merge:queue` 标签建立明确、可审计、可撤销的自动合并授权。
- 让多个待合并 PR 在一个固定 queue 中有界等待，而不是同时占用 integration capacity。
- 自动把待处理 PR 更新到最新 `main`，并对 exact integration head 运行 full Core CI。
- 绑定 PR number、base SHA、head SHA、workflow run ID 与 same-run `PR Gate`；dispatch
  路径额外绑定 queue ticket。
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
| D6 | update-branch 产生的 approval-required `pull_request` run 必须按 exact PR/head/workflow/bot identity 唯一匹配、批准并记录 numeric run ID；未发生同步时才显式 dispatch，并直接使用 2026-03-10 response 的 `workflow_run_id`。两条路径都禁止按显示名称猜 run。 |
| D7 | 两种 validation 都必须由 same-run `ci-scope` 证明 full、trusted、exact base/head；dispatch 路径还必须完整绑定 ticket 与 PR number。普通手动 dispatch 语义保持不变。 |
| D8 | validation run 必须在 same run 内成功产生 Change Scope、所有 full lanes 与 `PR Gate`；同步路径不再追加第二次 dispatch，不拼接其他 run 的 check results。 |
| D9 | base/head 漂移最多重新同步和完整验证三次；三次后仍漂移是 terminal failure。 |
| D10 | 合并调用必须指定 exact expected head SHA 与 `squash`；调用前后都核验 canonical repository state。 |
| D11 | CI failure、conflict、timeout、撤权和不确定 mutation 一律不重试 merge；先 reconciliation，再输出稳定 failure code。 |
| D12 | 控制面只使用 `actions: write`、`checks: read`、`contents: write`、`pull-requests: write`；不引入 PAT 或 GitHub App secret。PR conversation comment 与 label mutation 均使用 `pull-requests:write`。 |
| D13 | `main` push 的 per-SHA、non-cancelling concurrency 与 release exact-main evidence 保持不变。 |
| D14 | actionlint 升级到 `1.7.12` 并继续校验官方 digest；由于 upstream issue #657 的 schema lag，只允许精确忽略 `unexpected key "queue" for "concurrency" section`，同时由 repository contract 固定恰好一个 `queue: max`，其他 lint 错误仍 fail closed。 |
| D15 | queue controller 的 hard timeout 为 360 分钟，但内部 mutation deadline 为 330 分钟；至少保留 30 分钟做 reconciliation/report。每次 validation wait 从剩余预算动态推导，不固定占满 120 分钟。 |
| D16 | PR head 中的 `ci.yml` 与 CI scripts 属于被审代码而非独立可信证据；修改 queue/CI authority 文件的 PR 不允许由本队列自动合并。 |
| D17 | duplicate queue run 发现 PR 已 merged 时以 `already-merged` 成功 no-op 结束，不评论、不制造失败 check。 |
| D18 | squash merge 显式发送 `commit_title="<PR title> (#<number>)"` 与空 `commit_message`，不依赖仓库默认 squash message 设置。 |

## 6. 组件与文件边界

### 6.1 Merge Queue workflow

新增 `.github/workflows/merge-queue.yml`。`pull_request_target` 只声明 `types: [labeled]`；
workflow-level 不声明 concurrency，职责拆成：

- 一个无 concurrency 的 hosted `route` job 精确判断 label `merge:queue`；
- 只有 `needs.route.outputs.accepted == 'true'` 的 hosted `queue-item` job 进入固定
  `lmdj-merge-main` job-level concurrency group；其他 label 只产生 route + skipped job，
  不占 100 个 pending slots；
- 使用 `queue: max`，不取消 running 或 pending queue items；
- checkout canonical default-branch control code，`persist-credentials: false`；
- 将 event actor、PR number、event head SHA、repository 与 workflow run identity 传给
  queue controller；
- 授予 controller 所需的最小 workflow permissions；
- 将 controller 的结构化 report 写入 `GITHUB_STEP_SUMMARY`。

同一 workflow 另有不共享 queue concurrency 的 `schedule` watchdog job。它每 15 分钟检查
带 `merge:queue` 的 open PR；若 label 已存在 20 分钟，但 label event 之后不存在关联该
PR 的 queued/in-progress queue run，则命中 `queue-stalled`，移除 label 并创建一次稳定
conversation comment。`queue-item` 的 downstream `finalize` job 使用 `if: always()`：若 worker
没有写出 report，就先 reconcile，再用 `queue-worker-aborted` 收尾。整次 workflow 被人工
cancel 时 finalizer 可能无法运行，因此 watchdog 是 cancel、平台 hard timeout 与 pending
capacity eviction 的最终 fail-closed 兜底。

workflow 不解析产品文件、不运行 PR shell、不持有 deployment/release secrets，也不直接
在 YAML shell 中复制状态机。

### 6.2 Queue controller

新增 `scripts/ci/merge_queue.py`。它拥有全部 queue semantics，并通过一个窄的
`GitHubClient` 接口访问远端；`scripts/ci/github_queue_api.py` 封装 transport/schema，
`scripts/ci/merge_queue_watchdog.py` 只负责 stall reconciliation。核心接口返回闭合 report，
而不是依赖异常文本作为状态：

```text
run_queue_item(request: QueueRequest, client: GitHubClient) -> QueueReport
```

`QueueRequest` 至少包含 canonical repository、PR number、event actor、event head SHA、
queue workflow run ID 与最大三次 validation attempts。`QueueReport` 至少包含 terminal
status、stable code、attempt count、observed base/head、validation run IDs、merge SHA、
message 与 reconciliation evidence。

`GitHubClient` 只暴露 controller 需要的操作：读取 repository/actor permission/PR/ref，
更新 PR branch，绑定并批准同步 run 或 dispatch workflow 并取得 run ID，读取
run/jobs/checks，读取 Git commit
tree，执行 exact-head squash merge，以及在 Pull Request 上移除 queue label、留下一个
conversation comment。HTTP transport、API version、bounded retry 与 response schema validation
全部封装在该边界内。

canonical `main` SHA 的唯一 authoritative 来源是 Git refs API 的 `refs/heads/main`；Pull
Request API 的 `base.sha` 只作诊断与 drift 证据，不替代 ref。

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
- PR base 为 `main`；canonical `refs/heads/main`、PR base SHA 与 `queue_base_sha` 的关系被
  分类，而不是把正常 base drift 混成普通 CI failure；
- PR head 精确为 `queue_head_sha`；
- `queue_base_sha` 是 `queue_head_sha` 的 ancestor；
- queue label 仍存在；
- requested lanes 为空，因此 manifest mode 为 `full`。

Change Scope 从实时 PR 响应输出文档影响检查需要的 PR body；Portal reusable job 在 queue
mode 中与普通 PR event 一样校验该 body 和 exact base/head diff。Manifest 记录 queue
metadata，使 `PR Gate` 可以验证 same-run manifest 与 dispatch inputs 一致。

Change Scope 无论成功或失败都以 `if: always()` 上传闭合的 `queue-validation.json`：

```json
{"classification":"valid|queue-base-drift|queue-head-drift|invalid","queue_ticket":"...","observed_base_sha":"...","observed_head_sha":"..."}
```

controller 只从已绑定 numeric run ID 下载该 artifact。`queue-base-drift` 或
`queue-head-drift` 仅在 controller 再读 canonical main ref 与 PR head、独立确认相同漂移后
映射到 D9 attempt retry；artifact 缺失、schema 不闭合、与 live state 不一致或其他 CI failure
都是 `validation-failed`。因此 Change Scope 仍 fail closed，同时正常排队期间发生的 main/head
前进不会被误判为 terminal validation failure。

Core CI 增加包含 queue ticket 的 `run-name`，但 controller 只信 dispatch API 直接返回的
numeric run ID。显示名称只用于人工诊断，不参与 identity 判定。

update-branch 使用 `GITHUB_TOKEN` 时，GitHub 会为 `pull_request:synchronize` 创建
approval-required run。controller 轮询 `ci.yml` runs，只接受同时匹配 exact PR number、
exact synchronized head SHA、`event=pull_request`、workflow path 与
`actor=github-actions[bot]` 的唯一 run；用 `actions:write` 批准后先 reconcile run state，
再等待它完成。该 run 的 `ci-scope-<head>` artifact 必须是 schema v2、full、trusted 且
base/head 精确匹配 attempt，因此同步路径不再额外 dispatch 一次重复 full CI。PR 原本已经
包含 current main 时，没有 synchronize run，才使用上述 queue-validation dispatch。

controller 验证被选 exact run 内存在当前 branch protection 要求的 check context 与 GitHub
App identity，至少包括
`core (ubuntu-latest)`、`core (macos-latest)` 与 `PR Gate`；不匹配时报告
`required-check-contract-mismatch`，不把最终 merge API 的拒绝含混归类为普通
`merge-rejected`。

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

requested
  -> already-merged
```

### 7.1 Requested and eligible

workflow 只在 label name 精确为 `merge:queue` 时进入 controller。Controller 重新读取 actor
permission 和 PR，而不是相信 event payload 的可变字段。以下任一条件使请求 blocked：

- actor 权限不在 `write|maintain|admin`；
- PR closed、Draft、base 不是 `main`、head 来自 fork，或 repository identity 不匹配；
- event head SHA 与 controller 首次读取的 PR head 不一致；
- queue label 已不存在；
- PR mergeability 是 conflict，或 GitHub 在有界等待后仍不能计算 mergeability。

如果 duplicate run 到达队头时 PR 已经 merged，controller 返回 `already-merged` 成功终态，
不移除 label、不评论、不产生红 check。closed 但未 merged 仍是 `ineligible-pr`。

若 PR diff 修改以下 merge authority/control-plane 路径，controller 以
`queue-control-plane-change` fail closed，要求人工受保护分支合并，避免 PR 用自己修改过的
workflow/controller 为自身制造证据：

- `.github/workflows/merge-queue.yml`
- `.github/workflows/ci.yml`
- `.github/actionlint.yaml`
- `scripts/ci/merge_queue.py`
- `scripts/ci/github_queue_api.py`
- `scripts/ci/merge_queue_watchdog.py`
- `scripts/ci/change_scope.py`
- `scripts/ci/pr_gate.py`
- `scripts/ci/scope_policy.json`

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

发生 update-branch 时，controller 使用 `actions: write` 批准同步事件创建的 exact
approval-required run，并以其 numeric ID 作为唯一 run identity；该 run 必须是
`event=pull_request`、exact PR/head/bot identity，且其 same-run `ci-scope` 必须是 full、
trusted、exact base/head。PR 无需同步时，controller 才对 PR head 显式 dispatch `ci.yml`，
空 `lanes` 加完整 queue inputs，并使用 GitHub REST API version `2026-03-10` response 的
`workflow_run_id`。随后只等待所选 run：

- run event 与路径符合其来源：同步为 `pull_request`，否则为 `workflow_dispatch`；workflow
  path 均为 `.github/workflows/ci.yml`；
- run `head_sha` 精确等于 attempt head；
- run completed/success；
- same run 的 `Change Scope` 与 `PR Gate` completed/success；
- manifest 为 full、trusted head、exact base/head；dispatch 路径还要求 exact queue ticket；
- full mode 所有正式 lanes 的 same-run result 通过既有 PR Gate adjudication。

queue worker job hard timeout 为 360 分钟，controller 从 job start 建立 330 分钟 internal
mutation deadline，剩余至少 30 分钟只允许 reconciliation/report，不再发 update、dispatch 或
merge mutation。每次 validation wait 的预算为：

```text
min(120 minutes,
    floor((mutation_deadline - now - 10 minute sync/reconcile reserve)
          / remaining_attempts))
```

预算不足 10 分钟时不开始新 attempt，报告 `queue-budget-exhausted`。validation timeout 从
run created time 计算，因此包含 runner 排队时间；report 同时记录 queue seconds 与 execution
seconds，运维人员可以区分 capacity wait 和 test execution。API 轮询使用有界间隔并尊重
rate-limit response；标签每轮都重新读取，标签移除立即转为 cancelled。

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
commit_title = <PR title> (#<PR number>)
commit_message = ""
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

移除 label 只保证在 controller 最后一次 pre-merge 读取之前可撤销；在该读取与 GitHub 接受
merge mutation 之间存在不可消除的短窗口。API 请求已被接受后，后到的 label removal 不能
撤销 merge；controller 仍必须完成 postcondition reconciliation 并报告这一事实。

## 8. Failure、取消与恢复

稳定 terminal code 至少包括：

- `unauthorized-actor`
- `ineligible-pr`
- `already-merged`（成功 no-op）
- `queue-control-plane-change`
- `queue-label-removed`
- `merge-conflict`
- `update-branch-timeout`
- `sync-validation-approval-failed`
- `validation-dispatch-failed`
- `validation-dispatch-contract-mismatch`
- `validation-timeout`
- `validation-failed`
- `required-check-contract-mismatch`
- `queue-budget-exhausted`
- `queue-worker-aborted`
- `queue-stalled`
- `unstable-after-three-validations`
- `merge-rejected`
- `merge-state-uncertain`
- `postcondition-mismatch`

`already-merged` 是成功终态；`queue-label-removed` 是用户取消。除此以外 terminal failure 会：

1. reconcile PR、main 与可能的 merge result；
2. 如果 PR 仍 open，移除 `merge:queue`，避免旧授权被无意复用；
3. 使用 `pull-requests: write` 创建一个 PR conversation comment，记录 stable code、queue run URL、
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
- workflow token 只授予 `actions: write`、`checks: read`、`contents: write`、
  `pull-requests: write`；无
  deployments、environments、packages、secrets、id-token 或 administration 权限。
- queue workflow 运行在 GitHub-hosted Ubuntu；PR 代码只在既有 trusted-head Core CI lanes
  中执行。
- validation run（同步产生的 PR run 或 dispatch）执行该 head 上的 `ci.yml` 与
  `change_scope.py`/`pr_gate.py`。这些 evidence 不是独立于 PR 的可信控制面；其完整性最终
  依赖代码 review、conversation resolution、branch protection 与“审批完成后才添加
  `merge:queue`”的操作纪律。control-plane diff 禁止自助 queue merge 是额外防线。
- workflow dispatch ticket 不是 secret。伪造 ticket 最多产生 CI，不会被 controller 接受，
  因为 controller 绑定 dispatch API 返回的 numeric run ID。
- merge mutation 依赖 exact expected head、strict branch protection 与 Required Checks；
  controller 不拥有绕过规则的管理员 token。
- conversation comment、summary 与 test fixture 不记录 token、authorization header 或私有 API body。

## 10. Verification strategy

实现严格使用 red-green-refactor。Queue controller 的每个状态转换先由 fake
`GitHubClient` 驱动失败测试，再写最小实现。测试不访问 live GitHub，也不产生远端 mutation。

最低自动化覆盖：

- authorized label request enters one fixed FIFO queue；
- unauthorized actor、fork、Draft、wrong base、missing label 全部 fail closed；
- expected-head update success、422 drift、conflict、timeout 与 uncertain response reconciliation；
- 同步产生的 approval-required run 按 exact PR/head/bot identity 唯一绑定，批准 mutation
  不确定时先 reconcile，且同步路径不再二次 dispatch；
- dispatch response 的 exact numeric run ID 被保存，其他同 SHA/同名 run 被忽略；
- queue validation inputs 全有或全无、full-only、exact base/head 与 PR body impact check；
- same-run Change Scope/PR Gate success 才能进入 ready；
- CI failure、timeout、cancel、head/main drift 与三次 attempt budget；
- 标签在 pending、sync、poll 和 pre-merge 时移除都不会 merge；
- exact-head squash request、strict rejection、successful postconditions 与 tree mismatch incident；
- mutation uncertainty 不会盲目重复 merge；
- workflow 使用 `pull_request_target:labeled`、fixed concurrency、`queue: max`、hosted runner、
  canonical checkout 与 exact minimal permissions；
- workflow 不监听 `synchronize`/`closed`，exact label route 位于 job-level concurrency 之前，
  非 queue label 不占 pending slot；
- duplicate runs 的 `already-merged` 幂等成功 no-op；
- dynamic attempt budget 保留 30 分钟收尾，worker abort finalizer 与 scheduled stall watchdog；
- Change Scope drift artifact 与 controller live-state 双重确认；
- control-plane change 禁止 queue self-merge；
- explicit squash title/message 与 required-check context/App identity contract；
- actionlint `1.7.12` archive digest、唯一精确 schema-lag exception、workflow syntax 与 literal self-hosted labels；
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

仓库代码合入本身不会启用队列。远端 rollout 分成独立授权与证据边界；本 Task 已获授权
完成 implementation push、PR 与 required checks 全绿后的 squash merge，但 label 创建、
branch protection 变更与首次自动 queue merge 仍是独立 mutation：

1. implementation PR 在 full CI 与 review 通过后，由单独授权 squash merge；
2. 验证 exact merged-main CI，不能从 PR CI 推断；
3. 在创建 label 前，用 `workflow_dispatch` 的 no-mutation preflight mode 连续发出三个
   `hold_seconds` probe，验证一个 running、两个 pending、无 replacement/cancellation，并核对
   FIFO start order；同时验证 dispatch 200 response 含 numeric `workflow_run_id`。任何一项失败
   都停止 rollout，保持 label 不存在；
4. 单独授权创建 label `merge:queue`，记录 exact name、description 与 color；
5. 单独授权确认 `main` strict required checks、conversation resolution 与 admin enforcement，
   不删除或弱化 Required Checks；分别核对同步路径的 approved `pull_request` run 与无需同步时
   的 dispatch run，确认 required context 的 exact name、GitHub App identity 和 same-run scope；
6. 用一个无产品风险、且不修改 control-plane 路径的同仓库 test PR 做首次 queue validation，
   只在 review/required checks 已完成后显式添加 label；
7. 记录 queue run ID、validation run ID、runner assignment、base/head、merge SHA、tree equality、
   resulting main CI 与 label state；
8. 验证 watchdog：构造带 label 且无活动 queue run 的安全 test PR，确认 20 分钟后以
   `queue-stalled` 摘 label 并报告；
9. 首次验收成功后才把 queue 作为日常 merge 路径。

Runbook 把“open PR 有 `merge:queue` label，但 label event 后没有 queued/in-progress queue run”
定义为 stall signature。排查顺序固定为 workflow run、pending capacity、manual cancel/platform
timeout、controller report；在 reconciliation 前不得直接重新添加 label。

任何边界失败都停止在当前状态。Implementation commit 不授权 push；push 不授权 PR；PR 不
授权 merge；merge 不授权 label/branch protection 修改；remote configuration 不授权首次
自动 merge；首次 merge 不授权 release、deployment、publication 或 Channel promotion。
