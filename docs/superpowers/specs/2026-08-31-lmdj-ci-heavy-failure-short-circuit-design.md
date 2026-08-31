# LMDJ CI Heavy Failure Short-Circuit Design

日期：2026-08-31

状态：设计已由 Owner 确认；implementation 待本规格复核与正式计划，push、Pull Request、
merge 与远端运行操作均待后续独立授权

## 1. 结论

LMDJ Core CI 改为两个显式阶段：现有非重型正式 lane 先并行收集反馈，只有本次 scope
选中的前置 job 全部成功后，才进入共享 Contabo 主机上的重型阶段。重型阶段按
`Portal -> Core Ubuntu -> Package -> Coverage -> ASan` 的固定顺序执行；任一已选重型 job
失败或取消后，后续重型 job 均不再启动。

前置阶段已经开始的并行 job 不会因兄弟 job 失败而被主动取消。它们继续保留日志与 failure
artifact，随后由 Hosted `Pre-heavy Gate` 拒绝重型阶段。最终 `PR Gate` 始终运行，并区分：

- 真正执行后失败或取消的原始 failure；
- 因前置或较早重型 failure 而跳过的 downstream job；
- 本次 Change Scope 本就没有选择的正常 scope skip。

本设计不调用 Actions cancel API，不增加 `actions: write`，不自动 retry，也不把失败原因猜测
成产品回归。操作者必须先检查 exact-SHA job log、retained artifact 与 Gate summary，再决定
修复或显式重跑。

## 2. 背景与问题

当前 `.github/workflows/ci.yml` 让所有正式 lane 直接依赖 `Change Scope`。Portal、Package、
Core Ubuntu、Coverage 与 ASan 虽共用 `lmdj-native-heavy` concurrency group，因此在所有 run
之间一次只执行一个，却彼此没有结果依赖。某个并行 Web lane 已经失败后，这些 pending
重型 job 仍会依次获得唯一 capacity slot。

2026-08-31 的 `main` run `33342850197` 已在 `creator-web` 出现确定 failure，但仍保留五个
pending native-heavy job。与此同时，已经合并的 PR #445 仍有一轮 queue validation 占用同一
重型 group。结果不是 runner 离线：两台 Contabo baseline runner 均 online，而是失败 run、
其他 PR 与 queue validation 的重型 waiter 在一个全局单槽内累积。

既有设计有意让 lane 直接 fan out，再由 `PR Gate` fan in，以获得最短绿色路径。自
`lmdj-native-heavy` 引入后，五个重型 lane 已经不能互相并行；继续保留无依赖 waiter 不再提供
重型并行收益，却会让一个确定失败的 run 消耗后续几十分钟的共享主机预算。本设计只改变该
成本边界，不改变 Change Scope 对“哪些 lane 必须运行”的判定。

## 3. 目标

- 任一已选前置 job 失败、取消或异常跳过时，不启动任何 native-heavy job。
- 已启动的前置并行 job 继续完成并保留其诊断证据。
- 重型 job 保持全局单槽，并在同一 run 内使用固定 cheap-to-expensive 顺序。
- 任一已选重型 job 失败或取消时，后续重型 job 不启动。
- 未选中的前置或重型 job 继续是合法 scope skip，不阻断后续已选 job。
- `Pre-heavy Gate` 与 `PR Gate` 都在 GitHub-hosted Ubuntu 控制面运行，不依赖被裁决的
  self-hosted pool。
- Gate 对缺失 manifest、未知结果、selected-but-skipped 与拓扑矛盾 fail closed。
- summary 将原始 failure、downstream blocked 与 scope skip 分开，避免级联 skip 被误报成
  新的产品 failure。
- 保留现有 failure logs、Playwright traces、Coverage reports 与其他 lane-owned artifacts。

## 4. 非目标

本设计不包含：

- 取消、重跑或修改任何已经存在的 GitHub Actions run；
- 增加、删除、启动、停止或重新标记 self-hosted runner；
- 放宽 Change Scope、PR Gate、required checks、test tier、coverage floor 或 sanitizer workload；
- 自动诊断、自动修复或自动 retry semantic failure；
- 使用 `actions: write` 从 workflow 内取消自身或兄弟 job；
- 修改 Integration Queue merge authority、branch protection、release evidence 或 deployment；
- Product Build、Module、Host、Provider 或 Contract 版本变更。

## 5. 执行拓扑

```text
Change Scope
    |
    +--> Docs / CI Contract / Deploy Contract / Chameleon --------+
    +--> Web Toolchain / Web Runtime / Creator / Web Lab ----------+--> Pre-heavy Gate
    +--> macOS selector / primary / fallback / adjudicators -------+         |
                                                                               | success
                                                                               v
                                      Portal -> Core Ubuntu -> Package -> Coverage -> ASan
                                                                               |
                                                                               v
                                                                            PR Gate
```

`PR Gate` 继续直接观察本次 run 的所有正式与 support result，并以
`always() && !cancelled()` 收尾。任何 phase failure 都不能跳过最终 adjudication。

### 5.1 前置阶段

前置阶段是现有正式 job 中除五个 native-heavy job 外的集合：

- `docs-static`、`ci-contract`、`deploy-contract`、`chameleon-lab`；
- `web-toolchain-conformance`、`web-runtime-host`、`creator-web`、`web-runtime-lab`；
- `select-macos-runner`、`macos-primary`、`macos-fallback`、`core-macos`、
  `core-asan-macos`。

这些 job 保留现有并行、runner、timeout、trust、fallback 与 artifact 行为。兄弟 job failure
不调用远端取消；已经 running 或 queued 的前置 job按正常语义完成。这样一次 run 可以保留
多个独立原始 failure，而不是只留下最先结束的一项。

`macos-fallback` 是 orchestration dependency，不是 `scope_policy.json` 中独立 required result；
Gate 等待它收敛，但其 semantic verdict 只通过现有 `core-macos` 与 `core-asan-macos`
adjudicator 进入 policy 判定。结果 JSON 不把它伪造成新的正式 job key。

### 5.2 Pre-heavy Gate

新增 Hosted `pre-heavy-gate` job。它 `needs` `change-scope` 与全部前置 job，并在 workflow
未被人工取消时始终运行。Gate 使用仓库脚本读取：

- exact Change Scope manifest；
- `Change Scope` 自身 result；
- 全部前置 `needs.<job>.result`。

Gate 必须从 `scripts/ci/scope_policy.json` 派生 expected set，不维护第二套 path ownership。
判定规则是：

1. manifest 与 policy 必须有效，base/head/trust 仍由既有 Change Scope/PR Gate 合同负责；
2. 本次 required 的前置 job 必须是 `success`；
3. 未 required 的前置 job 必须是 `skipped`；
4. selected `failure`、`cancelled` 或 `skipped` 都拒绝重型阶段；
5. 未知 result、缺失/多余 result key 或 selected/unselected 拓扑矛盾均 fail closed。

Gate 写入 Markdown summary，分别列出 primary failures、unexpected skips 与 scope skips；不复制
job log，也不将错误文本升级成根因结论。Gate 成功只表示“允许开始重型阶段”，不是 PR、
merge 或 release evidence。

### 5.3 重型阶段

重型 job 保持现有 `lmdj-native-heavy`、`queue: max` 与
`cancel-in-progress: false`，并增加显式 run 内顺序：

1. `portal`
2. `core-ubuntu`
3. `package`
4. `core-coverage`
5. `core-asan`

顺序按观察到的通常执行成本由低到高排列，使快速 Portal/Proof/package failure 尽早阻断
Coverage 与包含 stress tier 的 ASan。全局 concurrency 仍是跨 run 的主机 capacity authority；
run 内依赖只负责失败传播，不能用来增加并行度或绕过 capacity queue。

每个重型 job 必须：

- 仅在 `pre-heavy-gate == success`、自身 lane selected、trusted-head 条件成立时运行；
- 对所有更早重型 job，只有“该 lane 未选择”或“该 job success”才允许越过；
- 将 selected earlier `failure`、`cancelled` 或 unexpected `skipped` 传播为 downstream skip；
- 保留自身现有 failure artifact 与 `always()` cleanup/statistics steps。

直接条件必须读取同一个 Change Scope manifest，才能让 focused run 跳过一个未选前序 lane 后
继续运行后续已选 lane。不能只写单链默认 `success()`，否则合法 scope skip 会错误阻断后续
lane。

## 6. 失败分类与 PR Gate

`PR Gate` 的 pass/fail 语义不变：每个 selected job 必须成功，每个 unselected job 必须
skipped。展示层增加以下闭合分类：

| 分类 | 条件 | 例子 |
| --- | --- | --- |
| Primary failure | selected job 实际为 `failure` 或 `cancelled` | `creator-web=failure` |
| Unexpected skip | selected 前置 job 无上游 short-circuit 却为 `skipped` | selector/topology error |
| Downstream blocked | selected 重型 job 因 Gate 或更早重型 failure 而为 `skipped` | `core-asan` blocked by `core-coverage` |
| Scope skip | manifest 未选择且 result=`skipped` | docs-only run 的 ASan |

一个 run 可以有多个 primary failures，因为前置并行 job 不互相取消。Downstream blocked 只解释
为什么 workload 没有启动，不把 required check 变成成功；整次 `PR Gate` 仍失败。

Gate summary 必须给出 exact job display name 与 result。具体 root cause 继续由 job log、step
failure 与 retained artifact 提供。仓库不根据 `failure` 字符串自动修改代码，也不自动重跑；
重新执行必须是检查证据后的显式操作。

## 7. 文件与组件边界

预计 implementation 只触及以下边界：

- `.github/workflows/ci.yml`：新增 `pre-heavy-gate`、前置 fan-in、重型顺序与 PR Gate result
  输入；
- `scripts/ci/phase_gate.py`：纯判定核心与 summary rendering，不访问网络、不执行 workload；
- `scripts/ci/pr_gate.py`：保留 verdict，增加 primary/downstream/scope 分类展示；
- `tests/build/ci_phase_gate_test.py`：Gate 的表驱动单元测试；
- `tests/build/ci_workflow_topology_test.py` 与
  `tests/build/ci_build_acceleration_test.py`：固定前置集合、重型顺序、Hosted 控制面、全局
  capacity lock 与稀疏 scope 传播；
- `tests/build/ci_pr_gate_test.py`：固定 failure 分类，不弱化既有 selected-success 合同；
- 当前 CI/testing 操作文档：说明两阶段 short-circuit 与诊断边界。

不修改 `scripts/ci/change_scope.py` 的 ownership 规则，不增加 workflow permission，不触碰
runner 配置、merge queue controller 或产品源码。

## 8. 测试合同

implementation 必须按 TDD 先建立失败测试，再修改 workflow/script。最小场景包括：

1. 所有 selected 前置 job success，Gate success；
2. 一个或多个 selected 前置 job failure，Gate 列出全部 primary failures；
3. selected 前置 job cancelled，Gate failure；
4. selected 前置 job skipped，Gate 作为 unexpected skip failure；
5. unselected 前置 job skipped，Gate 接受为 scope skip；
6. unselected 前置 job 意外运行，Gate fail closed；
7. manifest/result 缺失、多余、未知或畸形时 Gate fail closed；
8. workflow exact heavy order 为 Portal、Core、Package、Coverage、ASan；
9. 中间 heavy lane 未选择时，后续 selected lane仍可运行；
10. 中间 heavy lane failure/cancelled/unexpected-skip 时，后续 selected lane blocked；
11. PR Gate 同时报告 primary failure 与 downstream blocked，但 verdict 保持 failure；
12. 原有 focused/full/draft、trusted-head、macOS fallback、queue metadata 与 failure artifact
    合同全部继续通过。

Task-specific verification 至少包括：

```bash
python3 -m unittest \
  tests.build.ci_phase_gate_test \
  tests.build.ci_pr_gate_test \
  tests.build.ci_workflow_topology_test \
  tests.build.ci_build_acceleration_test
bash tests/build/test_active_tree.sh
scripts/architecture-portal.sh check
```

若 repository CI contract 另有更窄的 pinned actionlint entrypoint，implementation plan 应把它
加入验证。远端 PR CI、merge、main CI 与实际 queue drain 是后续授权和独立证据，不由本地
测试替代。

## 9. Documentation Impact

Documentation impact: required

Reason: 本设计改变正式 Core CI 的阶段、失败传播、共享重型容量使用与 Gate 诊断语义，当前
testing/operations 文档必须与可观察 workflow 一致。

Affected portal pages:

- `/operations/testing-and-proof`

同时更新相关 source documentation；若该 Portal 页面当前从 governance 文档派生，则以现有
source boundary 为准。CI-only 变更不分配 Product Build，不创建 immutable Portal snapshot。

## 10. Version Management

Version impact: none

Reason: 变更只影响 GitHub Actions 编排、诊断与测试合同，不改变 Product Assembly、Product
Build、Core Module、Host、Provider、Contract、Channel 或 release identity。

## 11. 授权与 rollout 边界

设计文档提交只授权本地 docs commit。implementation 必须在用户复核本规格、批准正式计划后
作为独立 Task 执行。local implementation commit 不授权 push、Pull Request、merge、取消
远端 run、修改 branch protection、部署、release 或 Channel promotion。

首次远端验证必须单独证明：

- 一个故意失败的可信测试分支在保留前置 failure evidence 后跳过全部重型 job；
- 一个 full green run 依固定重型顺序通过；
- 一个 focused run 能越过未选重型 lane，而不会被合法 skip 错误阻断；
- same-run `PR Gate` 正确区分 primary、downstream 与 scope skip；
- job logs 识别实际 runner，且 `lmdj-native-heavy` 仍保持跨 run 单槽。

这些 probe、push、PR 与 merge 均是文档提交之外的远端 mutation，必须另行授权。
