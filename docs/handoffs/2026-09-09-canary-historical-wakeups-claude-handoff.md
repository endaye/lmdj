# Canary 历史唤醒修复：跨机器 Claude 交接

记录日期：2026-09-09，Asia/Shanghai。实现者：Codex。
仓库：`endaye/lmdj`。本文是交接时点的状态，不替代接手时的实时查询。

## 1. 先做什么

接手 [PR #1082](https://github.com/endaye/lmdj/pull/1082)，实际审阅它的最新完整 diff，
处理发现、记录当前 head 的独立接管审阅，再按仓库规则完成 squash merge。
实现和本地验证已完成；上一轮停在“自动审阅没有有效结果”，不是产品测试未完成。
不要从头重写规划器，也不要把交接误当成部署或发布指令。

- 远端任务分支：`fix/canary-historical-wakeups`。
- 实现提交：`699fc66850a39a22e2396452521747e578e8afcd`。
- 实现分支起点：`bb99f11982450f77ca7f2309776197482690cfa8`，不是当前 main 的保证。
- 编写本文前复核：PR 为 OPEN、非已合并，head 是上述实现提交，mergeable 为 MERGEABLE。
- 本文会作为后续独立文档提交推送到同一 PR，因此接手时 head 应重新读取，不能硬用上述 SHA 合并。
- 原机器工作树：`/tmp/lmdj-canary-historical-wakeups`；这不是另一台机器需要复用的路径。
- 本轮只交付文档，不启动另一个代理、不合并、不清理原机器工作树。

## 2. 必须保留的规则与授权边界

先读接手时仓库内的 `AGENTS.md`、`docs/governance/git-workflow.md`、
`.agents/skills/issue-done/SKILL.md`、`docs/governance/minimization-principle.md`。
不要拿旧 handoff 中的旧队列／全 CI 门禁或逐次授权规则覆盖当前 AGENTS。

用户此前要求继续该 Task，当前 AGENTS 的 standing Task authorization 覆盖完成
commit、push、PR、current-head review 和 squash merge；本次用户要求把后续工作交给另一台机器上的 Claude。
独立接管必须真的读当前 diff，并在 PR 留下 reviewer、精确 head、发现及处置、限制与接管原因。
不是复制本文后就称“review passed”。若 Claude 又修改实现，需要对修改后的 head 重新取得有效审阅。

只在隔离 worktree 的短期 `feat/*`、`fix/*`、`docs/*` 分支工作，不在 main 上编辑。
保留其他人的未提交改动；不强推、不 reset、不为追逐 main 无故重写已发布分支。
普通 PR 无全 CI 绿色或 strict-update 要求，但 Task 验证、当前 head 审阅、冲突和讨论保护仍必须满足。
接手时重新读取实时保护；配置漂移则报告，不绕过、不改保护。

本次交接不授权以下操作：

- 开启 `CANARY_PLANNING_AUTOMATIC_READY` 或评估执行 readiness；
- 初始化／采用真实 journal、重置 scheduler、清空失败或验证债务；
- 配置主机／runner／隔离环境，增加付费额度或复制凭据；
- 分配 Product Build、修改版本／changelog、打 tag、发布、部署或 Channel promotion；
- 清理原机器或其他会话的分支／worktree。

后续 release 审计／操作必须另按 `.agents/skills/lmdj-release/SKILL.md` 和实际用户授权办理。

## 3. 修复的原因与实现边界

已合并的 [PR #1080](https://github.com/endaye/lmdj/pull/1080) 提供手动首次版本基线采用。
批准依据由 `tools/canary/first_version_baseline.json` 与 [PR #1071](https://github.com/endaye/lmdj/pull/1071) 保存，
应从它们读取历史 revision／Host 身份，不从本文推导当前版本。
采用只改变 `version_accounted`，站点和 formal 指针仍为空。

旧问题：`reconcile-next` 按持久 admission 顺序发现结果；首次遇到基线之前的成功结果，
`plan_after_result()` 会尝试收集“版本基线 → 更旧目标”的倒置区间，失败并阻塞后续发现。
上一 Task 刻意保留此拒绝，要求单独审阅历史协调策略；#1082 是这个后续策略。

当前行为：

1. 先沿用完整 scheduler replay、request／terminal／保留 verdict 的身份和语义校验。
2. 有真实采用收据，且成功 auto/bootstrap 目标严格早于该首次基线时，证明目标、基线、
   control 属于观测 main 的第一父链；仅当 progress 仍是该初次采用状态、所有站点与 formal 为空才适用。
3. 持久化 `action: historical`、完整测试来源身份、完整 `baseline_receipt` 和 `plan: null`。
   它不是 `ignore`，不占 active/pending，不推进任何进度，也不是部署或测试覆盖证据。
4. 一次调用完成一条观察；后续调用继续发现下一条。写入丢响应先恢复冻结 intent／完整决策，
   不重复未知 POST。完成后的观察能在新进程中直接重放。
5. 等于基线的目标正常规划：版本区间为空，首次站点仍是 bootstrap/full。
   较新目标保留完整版本区间与全部站点测试下限。
6. 无收据仍拒绝倒置区间；损坏证据、改变的收据／进度不能被当作“历史”跳过。
   failed、missing、not-required 和显式 candidate 的原有非规划语义不变。

主要文件：

| 文件 | 审阅重点 |
| --- | --- |
| `tools/canary/planning.py` | 历史分类在 verdict 校验之后；严格第一父链先后关系；可选采用收据；不缩小 site floor |
| `tools/canary/planning_journal.py` | 收据／初始 progress 绑定；closed decision schema；historical slot；重放与完成时收据一致性 |
| `tools/canary/planning_entry.py` | 原始观察和恢复都使用 journal 中的收据；输出 historical；不改变请求输入权限 |
| `tests/build/ci_canary_planning_entry_test.py` | 实际 CLI、真实临时 Git、HTTP 协议 fixture、新 OS 进程恢复和后续发现 |
| `tests/build/ci_canary_planning_journal_test.py` | 不覆盖 active/pending；拒绝错误收据／资格／slot；完整重放 |

实现还更新了 `apps/docs-site/docs/operations/testing-and-proof.mdx`，以及：

- `docs/plans/2026-09-09-lmdj-canary-historical-wakeups.md`：本 Task 的声明与证据；
- `docs/plans/2026-09-09-lmdj-result-driven-delivery.md`：总计划和仍未完成的远端验收；
- `docs/plans/2026-09-09-lmdj-canary-baseline-adoption.md`：前序 Task 的历史边界。

## 4. 已完成验证：不要混淆证据范围

下列结果对应实现提交；本文的后续提交只增加交接文档。

| 验证 | 结果 |
| --- | --- |
| 新回归 red-first | 修复前准确失败于倒置版本区间 |
| `python3 -m unittest discover -s tests/build -p 'ci_canary*_test.py'` | 319 项通过 |
| 真实 depth-one clone，`ci_canary_planning*_test.py` discovery | 118 项通过 |
| 完整 `ci_*_test.py` discovery，提供 pinned actionlint | 2,224 项，仅 1 个继承失败；不是全绿 |
| 新文件暂存后的 `python3 tests/build/ci_change_scope_test.py` | 66 项通过 |
| `scripts/docs-site.sh install` 后 `scripts/docs-site.sh check` | 114 项测试、生产构建、44 条路由及内部链接通过 |
| `python3 tests/build/version_test.py` | 通过 |
| `python3 scripts/version.py verify --version-file products/lmdj/version.json` | 通过，未修改版本 |
| 最终提交范围分类 | focused：`ci_contract docs_static portal`，无未归属诊断 |

唯一继承失败是 `ci_pitfall_ledger_test.LedgerLintTest.test_every_entry_in_the_ledger_passes`：
`.agents/pitfalls/snapshot-page-pin-only-fires-at-freeze.md` 使用未知 `area: docs`。
[Issue #1078](https://github.com/endaye/lmdj/issues/1078) 保留该问题，交接时仍 OPEN。
本 Task 未修改该条目或 validator，不借本次交接修复它，也不删除／跳过测试。

验收旅程覆盖采用 → 历史观察 → 新进程重放 → failed/missing 观察保留 → 后续完整计划 → idle，
每段都断言远端 fixture 持久结果；完整 scheduler state、failure/debt 和独立 progress 字节保持不变。
还覆盖 intent/blob/complete 丢响应恢复。fixture 不证明真实 Actions 凭据、锁、配额、存储启用或部署验收。

环境注意事项：

- 原机器 Node `22.23.1`；门户使用锁定依赖 `npm ci`，不要把旧 `node_modules` 当成验证。
- CI YAML 语义测试需要 actionlint。原验证用 `1.7.12`，下载 archive 的 SHA-256
  为 `8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8`，与当时 CI pin 一致。
  接手时以 `.github/workflows/ci.yml` 的 pin 为准；设置 `LMDJ_ACTIONLINT` 指向经过校验的工具。
  语义测试显式关闭 ShellCheck；本 Task 没改 workflow shell，不能把该结果说成 shell 分析通过。
- 原仓库共享 `core.symlinks=false`。六个门户链接曾被检出成普通文件；在确认这些路径未修改后，
  仅在本工作树用命令级 `core.symlinks=true` 恢复。不要修改共享 Git 配置或复制替代 snapshot 树。
  参见 `.agents/pitfalls/worktree-checkout-flattens-symlinks.md`。
- 原机器 `/tmp/lmdj-historical-portal.log`、`/tmp/lmdj-historical-ci.log` 等仅为辅助日志，
  不随 Git 传输。本文、PR body、版本化计划和可重跑命令是跨机器入口。

## 5. 审阅阻塞的精确证据

[PR Review run 34339147361 / attempt 1](https://github.com/endaye/lmdj/actions/runs/34339147361)
对实现 head `699fc66850a39a22e2396452521747e578e8afcd` 的最终结果：

- `Resolve review target`：success；`Review fallback`：failure；`Publish review and scope`：skipped。
- artifact 名：`pr-review-result-699fc66850a39a22e2396452521747e578e8afcd-34339147361-1`。
- artifact ID：`10099354610`；读取时未过期。以后是否仍可下载需实时核验。
- `history.json`：GLM、Kimi、Grok 全部 `status: failed`、`error_class: runtime_failure`、`review: null`。
- `failure.json`／`result.json`：`status: not-reviewed`。此分类不足以断定三个后端各自的具体根因。
- 两个 Cursor NEUTRAL check 明确写着试用额度耗尽、未启动，不能当作独立审阅或批准。

失败已写入 PR body。不要重复旧 run 期待它成为当前 head 的审阅；文档推送可能触发新 run，
接手时先检查最新状态。如果新 run 真正完成并发布当前 head 的有效审阅，读取其发现并处置即可。
否则 Claude 应按 `issue-done` 的人工／代理接管程序实际审阅完整当前 diff，并明确记录上述接管原因。
没有有效审阅时保留 PR OPEN，不伪造 bot 身份、check 或 approval。

## 6. 另一台机器的接续步骤

在已获授权、已自行配置 GitHub 登录的机器执行；不要从原机器传 token 或私钥。
下面假设当前目录是该仓库、指定本地分支及 sibling 路径均不存在；如已存在，先核对占用，
不要为了使用命令而删除／覆盖现有资源。

```bash
gh auth status
git status --short
git worktree list
git fetch origin main fix/canary-historical-wakeups
# 在支持符号链接的文件系统上创建独立工作树。
git -c core.symlinks=true worktree add -b fix/canary-historical-wakeups ../lmdj-canary-historical-wakeups origin/fix/canary-historical-wakeups
cd ../lmdj-canary-historical-wakeups
git status --short
git rev-parse HEAD
gh pr view 1082 --json state,isDraft,headRefOid,mergeable,statusCheckRollup,reviews
git diff --stat origin/main...HEAD
git diff origin/main...HEAD
```

逐文件实际检查完整 diff，而非只看 summary。重点核对 §3 的资格边界、receipt 绑定、
完整 source 验证、未完成写恢复和 site full floor；本文也属于新的完整 diff。
先跑轻量且相关的规划测试，必要时补完整 canary；不要因换机器就重跑全部产品重负载 lane：

```bash
python3 -m unittest discover -s tests/build -p 'ci_canary_planning*_test.py'
python3 tests/build/ci_change_scope_test.py
git diff --check origin/main...HEAD
```

如修改代码，声明文件范围、按风险重跑相关测试；影响门户时运行门户 check。
完成后按 AGENTS 自主提交、推送；所有新 push 都重新绑定 current-head review。
记录接管 reviewer 的真实身份与精确 SHA，说明范围、发现、处置与未覆盖的远端验收。
可用 `gh pr review 1082 --comment --body-file <review-file>` 发布真实接管记录，
但须确认该 review 绑定自己实际审过的当前提交；不要写成自动审阅已成功。

最终读取实时 branch protection、PR mergeability 及全部未解决 review threads。
本次最初读到 required checks 为空、strict=false、required approvals=0、conversation resolution=true，
但这些只是历史观察。若出现权限错误／UNKNOWN，不能当作无保护或无冲突。

只在验证、审阅、冲突／讨论条件满足且当前权限允许时，以精确 head 防竞态合并：

```bash
review_head="$(git rev-parse HEAD)"
test "$(gh pr view 1082 --json headRefOid --jq .headRefOid)" = "$review_head"
# 以下不是绕过前述审阅／保护检查的快捷方式。
gh pr merge 1082 --squash --match-head-commit "$review_head"
gh pr view 1082 --json state,mergedAt,mergeCommit,headRefOid
gh issue view 1078 --json state,title
```

报告实际 merged SHA；只发出 merge 请求或 armed auto-merge 不算完成。
不添加 `--admin` 或 `--delete-branch`。清理须另有适用授权和完整 patch 保留证据。
本 Task 没分配 Build 或 snapshot，不需要人为补 freeze／witness。

## 7. 合并后的边界

合并完成只表示这项源码修复交付，不表示线上历史积压已协调。
下一轮以总计划 `docs/plans/2026-09-09-lmdj-result-driven-delivery.md` 的最新 acceptance ledger
为准：独立真实存储、首次基线采用、历史积压观察、readiness、后续版本／站点协调器和部署验收
仍需分别确认。先只读检查，明确选择下一个 Task；不要直接初始化 Issue、切开关或部署。

## 8. 本次交接文档 Task

Declared files: `docs/handoffs/2026-09-09-canary-historical-wakeups-claude-handoff.md` only.

最低层验证：核对引用的仓库文件和已读取 GitHub 状态；暂存后运行 ownership suite、
`git diff --cached --check`，提交后检查文件清单、clean status 与最终范围分类。
本轮不重跑不受文档影响的产品测试，也不引入新 gate。

## Version Management

Version impact: none

Reason: 仅新增交接说明；不修改任何活动身份、版本、Assembly、changelog 或发布状态。

## Documentation Impact

Documentation impact: none

Reason: 本轮只增加 `docs/handoffs/` 交接记录，不改变 Architecture Portal current 页面或源码事实。
注意：整个 PR #1082 的既有实现包含门户页面，因此 PR 级声明仍必须为 required，不能被本段覆盖。

Pitfall impact: none — 记录已存在的验证边界和审阅故障，没有在此文档 Task 修复新机制。
