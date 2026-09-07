# LMDJ CI Capacity Redesign

日期：2026-09-07

状态：设计评审草案，待 Owner 确认。本文只做评审与方向决策，不授权任何 workflow、
branch protection、runner 或队列变更；每个阶段的 implementation 都需要独立的计划与授权。

## 1. 结论

LMDJ 的 CI 已经从"保护 `main`"漂移成"证明每一次合并在形式上无懈可击"。它有一个
极强的正确性模型，但没有任何一层为容量或反馈时间负责。2026-09-06 到 09-07 的拥堵
不是某个配置写错，而是这个取向在多 PR 并发下的必然结果：

- 一个 PR run 的 native heavy 阶段实际执行不到 8 分钟，却等待了超过 3 小时；
- 成功的队列合并耗时 67、95、107、110 分钟；
- 三个早已被超越的 `main` push run 仍在占用全仓库唯一的重型槽；
- 最贵的 native heavy 链在最近 45 次失败 run 里只抓到 9 次失败。

本文提出把 CI 重组为三层门——**Merge 门快而窄、Main 门慢而全且异步、Release 门保持
现有 exact-main proof**——并为每一层设定可测量的容量目标。现有每个 gate 都被归入
一层并给出处置。全局单槽只保留给实测需要独占机器的 TSan 与 stress。

## 2. 证据

### 2.1 一个 run 的完整时间线

PR #737 的 run `34062231152`，2026-09-06T21:49:57Z 起算，单位分钟：

| job | 创建 | 开始 | 结束 | 槽等待 | 实跑 |
|---|---|---|---|---|---|
| 前置 8 lane 全绿（关键路径 `creator-web`） | 0.8 | 23.0 | 46.2 | 22.2 | 23.2 |
| Pre-heavy Gate | 46.2 | 46.3 | 46.4 | 0 | 0.1 |
| Architecture Portal | 46.4 | 80.0 | 81.5 | 33.6 | 1.5 |
| core (ubuntu-latest) | 81.5 | 132.7 | 134.1 | 51.2 | 1.4 |
| Core package | 134.1 | 196.3 | 200.8 | 62.2 | 4.5 |
| core-coverage | 200.8 | 211 分钟时仍 pending | — | >10 | — |
| core-asan | 尚未创建 | | | | |

跨 13 个成功的重型 job 样本：实际执行平均 3.1 分钟，槽等待中位数 33.1 分钟、最长
71.4 分钟。等待是执行的十倍以上。

### 2.2 同一时刻的在途 run

2026-09-07 采样时共 9 个 `Core CI` run 在途，其中 4 个是 `main` push run：

| run | 事件 | 年龄 | 重型链状态 |
|---|---|---|---|
| 34059271071 | push main（head `8b62b4e9`） | 270 min | 4/5 完成，`core-asan` pending |
| 34059327353 | push main | 269 min | 3/5 完成，`core-coverage` pending |
| 34059777525 | push main | 259 min | 3/5 完成，`core-coverage` pending |
| 34069290849 | push main（当前 `ea0b8781`） | 65 min | 0/5，`portal` pending |
| 其余 5 个 | pull_request | 64–246 min | 各处于链的不同环 |

前三个 `main` run 验证的 SHA 已被 `ea0b8781` 超越，它们的剩余 5 环仍会逐个占用槽。

### 2.3 队列合并耗时

`merge-queue.yml` 最近四次成功的 controller run：PR #739 67 分钟、#735 95 分钟、
#730 107 分钟、#704 110 分钟。workflow 内注释记录的无拥堵基线是"about 33 minutes
per validation"。

### 2.4 失败分布

最近 45 次失败的 `Core CI` run 中真正报 failure 的 job（PR Gate 与 Pre-heavy Gate 是
聚合器，不计入）：

| job | 次数 | 所在层 |
|---|---|---|
| creator-web | 22 | 并行 web lane |
| core (ubuntu-latest) | 4 | native heavy 链（3 次为 golden `reference_render.py`） |
| Architecture Portal | 3 | native heavy 链 |
| core (macos-latest) | 2 | 并行 macOS lane |
| core-coverage | 1 | native heavy 链 |
| core-asan | 1 | native heavy 链 |
| deploy-contract / web-runtime-host / ci-contract | 各 1 | 并行 lane |

占用全局单槽的五环链合计抓到 9 次，其中 sanitizer 与 coverage 各 1 次。

### 2.5 控制面规模

| 度量 | 数值 |
|---|---|
| 产品代码（`packages/ apps/ providers/ products/ contracts/`） | 110,075 行 |
| CI 控制面（`scripts/ci/` + `.github/workflows/` + `tests/build/`） | 33,304 行 |
| `ci.yml` 2026-07-15 → 2026-09-07 | 103 → 1,356 行，53 次提交 |
| 最近 300 次提交中 ci / release / governance / pitfalls | 115 次（38%） |
| `fix(ci)` 提交数 vs 全部产品 `fix(*)` 之和 | 37 vs 28 |
| Pitfall 账本中 CI / release / runner 条目 | 35 / 49 |
| 自研 Integration Queue（含测试） | 约 4,500 行 |

## 3. 设计层根因

**R1 只有正确性模型，没有容量模型。** 2026-08-11 以来的八份 CI spec 都在论证什么不能
并行、什么必须 exact-SHA、什么必须 fail closed；没有一份写过"一天要合几个 PR、PR 到绿
多少分钟"。`lmdj-native-heavy` 使用 `queue: max`，是无界队列；到达率超过单槽服务率后
系统无感知地进入排队崩溃，watchdog 只监视 label 是否 orphan。

**R2 fail-closed 被扩展到了不该 fail-closed 的层。** 合并授权 fail closed 是正确的。
但 `main` push run 按 exact SHA 独立运行且永不取消、branch protection `strict: true`、
队列再做一次 update-branch 加 exact-SHA 全量重验——每一层各自保守，叠加后每合入一个
PR 会触发 O(N) 轮重验证，N 个并发 PR 即 O(N²)。

**R3 事故响应是"加一道门"，不是"减一个原因"。** 08-11 risk-based gating → 08-13 cost
hardening → 08-14 dedicated runner → 08-20 serialized queue → 08-31 heavy short-circuit
→ 09-07 daily sweep，每一份都在修上一份的后果。08-31 的 short-circuit 为省主机预算把
五个重型 job 串成链；其 spec 第 2.1 节接受了单 run 的延迟代价，但没有计算多 run 争用
下"每一环完成后重新排到队尾"的乘法效应，而这正是 2.1 节时间线里 33 → 51 → 62 分钟
逐环递增的来源。

**R4 控制面与产品挤同一条管道。** CI 自身的变更走同一个 `ci.yml`、同一个 Change Scope
与同一批 required checks，且控制面路径一律触发 full 分类。控制面占 38% 的提交，就
占走相应比例的验证容量。

**R5 自研了平台已提供的能力并把它做成了产品。** 约 4,500 行 Integration Queue 重新
实现 merge queue，并需维护 pitfall 账本承认的"8 处独立 evidence contract"。理由是
个人账户私有仓库无原生 Merge Queue；该前提在 rulesets 形态的 Merge Queue 面前需要
重新核实（见第 10 节 Q1）。

## 4. 目标

- 为 CI 设定可测量的容量目标，并让每个 gate 的存在以该目标为代价约束。
- 把 gate 分成 Merge / Main / Release 三层，每层有明确的问题域、时限与失败处置。
- 全局单槽只保留给实测需要独占机器的工作负载。
- 消除过期 `main` run 与 PR run 的重复验证。
- 为控制面增长设置"删除等价复杂度"的门槛。

## 5. 非目标

- 不放松 Release 门。exact-main proof、签名、Channel promotion 的授权边界不变。
- 不改变 Change Scope 对"哪些 lane 必须运行"的分类语义；本文只改变 lane 在哪一层、
  何时运行。
- 不新增 runner 硬件作为前提；本文的收益不依赖扩容。
- 不在本文内决定第 10 节列出的 Owner 问题。

## 6. 容量目标

以下目标是设计约束，不是 SLO 报警阈值。任何使其不成立的 gate 必须在自己的 spec 里
写明代价。

| 指标 | 目标 | 当前实测 |
|---|---|---|
| PR 提交到 Merge 门绿（p50） | ≤ 20 分钟 | 前置阶段 46 分钟，全部 200+ 分钟 |
| PR 提交到 Merge 门绿（p90） | ≤ 35 分钟 | >240 分钟 |
| 单个 PR 从入队到合并 | ≤ 15 分钟（已绿且不落后时 ≤ 3 分钟） | 67–110 分钟 |
| 每日可合并 PR 数（无人工干预） | ≥ 12 | 2026-09-06 由人工绕过 |
| `main` 变更到 Main 门结论 | ≤ 45 分钟 | 4+ 小时且随背压增长 |
| 重型槽等待 / 执行比 | ≤ 1 | ≈ 10 |

## 7. 三层门模型

```text
PR head ──► Merge 门（快、窄、并行，required）──► squash merge ──► main
                                                                  │
                                                  Main 门（慢、全、异步；最新 SHA 取消旧的）
                                                                  │
                                                  红 ──► revert 或阻断 Release 门
                                                                  │
                                              Release 门（exact-main proof，现有流程不变）
```

### 7.1 Merge 门

回答"这个变更是否明显破坏了产品"。必须满足：

- 只包含确定性、快速、可并行的检查；单 job 时限 ≤ 15 分钟，整门 ≤ 20 分钟；
- 不进入任何跨 run 的 concurrency group；
- 是唯一一组 required checks；
- 在 PR head 与当前 `main` 的 merge-base 一致时，其结论直接授权合并，不重验。

### 7.2 Main 门

回答"合入后的 `main` 是否仍可发布"。性质：

- 在 `main` push 上运行，concurrency group 固定为 `core-ci-main`，`cancel-in-progress:
  true`，最新 SHA 覆盖旧 SHA；
- 承载全部重型、慢速与统计型检查；
- 不是 required check，不阻断合并；红色结果的处置是 revert 或阻断 Release 门；
- 与 Release 门的关系不变：Main 门绿不是 release evidence，Release 门本来就要求显式
  exact-main proof。

`main` 因此可能短暂为红。"`main` 必须保持 deployable"的语义收敛为"Release 门只从
Main 门绿的 SHA 出发"，这与现有 release 流程一致（见第 10 节 Q2）。

### 7.3 Release 门

现有 `lmdj-release` 流程、`release-audit.yml`、`publish-release.yml` 与签名边界全部
不变。本文唯一的新增约束：Release 门的候选 SHA 必须有对应的 Main 门绿结论。

### 7.4 独占槽

`lmdj-native-heavy` 重新界定为**仅限实测需要独占物理机的负载**：`core-tsan` 与
`core-stress`（`core-nightly.yml`）以及 `ci-self-hosted-core-benchmark.yml`。理由在
`docs/quality/core-test-policy.md` 已有实测（run `33838737018`）。

asan、coverage、package 不需要独占机器，只需要不与 TSan 同跑。它们在 Main 门内以单
run 内的顺序执行，而 Main 门自身因 `cancel-in-progress` 天然只有一个活动 run，因此
不需要跨 run 的 group。若 Nightly 与 Main 门时间重叠，由 Nightly 所在的独占 group 决定
先后；Main 门的三个 job 加入该 group 的条件是 Owner 确认 Q3。

## 8. 现有 gate 归层与处置

| gate / job | 现状 | 归层 | 处置 |
|---|---|---|---|
| Change Scope | 所有 lane 的前置 | Merge | 保留 |
| Docs / static | ci-general，≤10 min | Merge | 保留 |
| CI contract | ci-general，≤10 min | Merge | 保留 |
| Deploy contract | ci-general，≤15 min | Merge | 保留 |
| Chameleon Lab | ci-general，≤10 min | Merge | 保留 |
| web-toolchain-conformance | ci-web-heavy，≤35 min | Merge | 保留；时限压到 15 min，否则拆出慢速部分到 Main |
| creator-web | ci-web-heavy，≤35 min，实测 23 min | Merge | 保留；45 次失败中 22 次在此，是最有价值的 gate；需把 `web-ci-proof` 拆成快速 proof（Merge）与完整 proof（Main） |
| web-runtime-host | ci-web-heavy，≤75 min，实测 19 min | Main | 移层；75 分钟时限本身已说明它不是 Merge 门负载 |
| web-runtime-lab | ci-web-heavy | Merge | 保留 |
| core (ubuntu-latest) | ci-core，heavy 链 | Merge | 保留但**移出 `lmdj-native-heavy`**；`fast` tier（unit + component）实测 1.4 分钟 |
| core (macos-latest) / core-asan-macos | 自有 Mac，并行 | Merge | 保留 |
| Architecture Portal | ci-general，却在 heavy 链首环 | Merge | 保留，**移出 `lmdj-native-heavy`**；它不在争用主机上 |
| Core package | ci-core，heavy 链 | Main | 移层 |
| core-coverage | ci-core，heavy 链 | Main | 移层 |
| core-asan | ci-core，heavy 链 | Main | 移层 |
| Pre-heavy Gate | 为 heavy 链设的短路 | — | **删除**；heavy 链不再存在于 PR run |
| PR Gate | 聚合裁决 | Merge | 保留，裁决集合缩为 Merge 门 job |
| Claude review / Grok review | advisory，阻断 Pre-heavy Gate | Merge（advisory） | 保留但不再处于任何 gate 的 `needs` 路径；结论只写 comment |
| core-tsan / core-stress（Nightly） | 独占 | Main（定时） | 保留，独占 group 唯一成员 |
| daily main sweep（#724） | 定时 full | Main（定时） | 保留；Main 门本身已是每次 push 全量后可评估是否冗余 |
| Integration Queue（`merge_queue.py`） | 串行 update-branch + 全量重验 | Merge | 见第 9 节 |
| branch protection `strict: true` | 所有落后 PR 标 BEHIND | Merge | **关闭**；up-to-date 判定归队列 |

## 9. Integration Queue 的收缩

不论 Q1 的答案，队列都应收缩到以下语义：

1. PR 已 `merge:queue` 且 Merge 门在**当前 PR head** 上绿；
2. 若 PR head 的 merge-base 等于当前 `main` tip：直接 squash merge，不重验；
3. 若落后：update-branch 一次，等待新的 Merge 门（≤ 20 分钟），绿则合并；
4. 合并后不等待 Main 门。

这把每次合并的重验成本从"全量 5 环 heavy 链"降到"一轮 Merge 门"，且仅在落后时发生。
现有 3 次 attempt、drift 重检、post-merge reconciliation 语义保留。

若 Q1 确认原生 Merge Queue 可用，则自研控制器整体退役，由 `merge_group` 事件触发
Merge 门；两套队列不得同时拥有 merge authority（沿用 2026-08-20 设计的迁移约束）。

## 10. 需要 Owner 决定的问题

本文不在实现 Task 内静默解决以下任何一项。

- **Q1 原生 Merge Queue 可用性。** 现有文档记录"需要 public 仓库或 GHEC"。rulesets
  形态的 Merge Queue 在 GitHub Team 计划的组织私有仓库是否可用，需要以官方文档或实际
  开通为证据。若可用，第 9 节第二种路径成立，约 4,500 行控制面可退役。
- **Q2 `main` 是否允许短暂为红。** 第 7.2 节的 Main 门异步化意味着 asan / coverage /
  package 失败会在合并后而不是合并前暴露。需要 Owner 明确接受"`main` deployable"收敛
  为"Release 门只从 Main 门绿的 SHA 出发"，并确认 revert 是默认处置。
- **Q3 Main 门是否加入独占 group。** 若 Nightly TSan 与 Main 门的 asan / coverage 同跑
  会污染 TSan 结论，则 Main 门三个 ci-core job 加入 `lmdj-native-heavy`；代价是 Nightly
  窗口内 Main 门被推迟最多 90 分钟。
- **Q4 coverage 门的位置。** `docs/quality/core-test-policy.md` 把 coverage floor 当作
  Release 证据的一部分。移到 Main 门后它仍在每个 `main` SHA 上评估，但不再阻断合并。

## 11. Rollout 阶段与停止条件

每个阶段一份独立计划与授权，以第 6 节的指标为验收。任一阶段未达成其验收即停止，
不进入下一阶段。

**Phase 0 止血**（不改变任何正确性边界）

- `main` push 的 concurrency group 改为 `core-ci-main`，`cancel-in-progress: true`；
- `portal` 移出 `lmdj-native-heavy`。

验收：重型槽等待中位数下降到 ≤ 15 分钟；在途 `main` run 任何时刻 ≤ 1。

**Phase 1 Merge / Main 分层**

- `core-ubuntu` 移出 heavy group 并保持 Merge 门；`package`、`core-coverage`、
  `core-asan`、`web-runtime-host` 移到 `main` push 触发路径；
- 删除 Pre-heavy Gate；PR Gate 裁决集合缩为 Merge 门；
- advisory review 移出 `needs` 路径；
- `scope_policy.json`、`change_scope.py`、`pr_gate.py`、`local_preflight.py` 与对应
  `tests/build/ci_*` 同步收缩。

验收：PR 到 Merge 门绿 p50 ≤ 20 分钟；Main 门结论 ≤ 45 分钟。

**Phase 2 队列收缩**

- 关闭 branch protection `strict`；
- `merge_queue.py` 实现第 9 节语义；
- 若 Q1 成立，改为原生 Merge Queue 迁移计划。

验收：已绿且不落后的 PR 入队到合并 ≤ 3 分钟；每日合并 ≥ 12 无需人工。

**Phase 3 控制面冻结**

- 在 `docs/governance/` 增加控制面变更规则：新增 gate 的 spec 必须包含容量代价与
  删除等价复杂度的说明；
- 控制面路径的验证从产品 Merge 门中拆出，走独立的轻量 workflow。

验收：连续四周控制面提交占比 ≤ 15%。

## 12. 放弃了什么

- asan、coverage、package 的失败从合并前推迟到合并后 ≤ 45 分钟。2.4 节表明这三者
  在 45 次失败中合计 3 次，且 `main` 可通过 revert 恢复。
- `main` 逐 SHA 的全量证据不再自动产生。Release 门的 exact-main proof 本来就是显式
  获取，此项对 release 无影响。
- Pre-heavy Gate 节省的主机预算。Main 门只有一个活动 run，该预算问题不再存在。

## 13. Documentation Impact

Documentation impact: none for this spec itself. It changes no active manifest, Product
Build, Module, Host, Provider, Contract or Channel identity, and it is not a portal page.

Implementation Tasks in Phase 1 through Phase 3 must each declare their own impact; the
following routes are expected to change and must be updated in the same Task that changes
the behaviour they describe: `docs/quality/core-test-policy.md`（tier 与 gate 归层）、
`docs/governance/git-workflow.md`（合并前提与 `strict` 语义）、
`docs/governance/github-work-management.md`（`merge:queue` 语义）。

## 14. Version Management

Version impact: none. This spec adds no Product Build, Core Module, Provider or Contract
change. Phase 1 through Phase 3 change CI control-plane files only; none of them alters
`products/lmdj/version.json`, any Module SemVer or any Contract SemVer.

## 15. 授权与 rollout 边界

本文的 commit 只授权 spec 文本进入 Task branch。push、Pull Request、merge、branch
protection 修改、runner 标签变更、workflow 变更与队列语义变更各需独立授权。Phase 0 是
第一个可授权的实现 Task，其计划应引用本文第 11 节的验收指标作为 Task-specific 验证。
