# 修复 — Replay neutral reset 批量入队次序（transport-after-replay rendezvous）

状态：实施 Task 计划。修复 P1（`d21ea97c`）引入的确定性回归：
`host.web_control_runtime` 的 transport-after-replay 旅程在 main
（`c2de40b6`）上以 HOST_TIMEOUT 失败。

## Defect and evidence

- 双向证实：pre-P1 `65c38f0b` 干净 build PASS；P1 merge `d21ea97c` 干净
  build FAIL；本 worktree（`c2de40b6`）干净 configure+build dev 后单跑
  `ctest --preset dev -R '^host\.web_control_runtime$'` 复现 RED：
  `control_runtime_test.cpp:7371` 的 transport dispatch 在 2s
  `AbsoluteRequestDeadline` 上得到 HOST_TIMEOUT。
- 机制：P1 把 replay `reset_neutral` 从"只等 legacy gesture 计数排空"扩展为
  全通道 drain ACK（gestures＋typed Filter controls＋Pad gates applied
  sequence）。但批量入队次序是 legacy gesture 突发在前、Pad gates 清理在
  后。rendezvous 测试（`dispatch_transport_after_replay`）的远端观测点是
  `master_fx_telemetry().enqueued_gestures`：第 9 个 gesture 一落队，测试
  主线程就做第一个 boundary render；此刻 gates 清理尚未入队，落在这次
  render 之后。reset pending 阻塞 dispatch 完成与 Pattern publication，
  而测试协议只在 publication 之后再 render——循环等待到 deadline。
  pre-P1 批量恰等于 9 个 gesture，观测点即批量完整点，同批一次 drain
  即够，所以同协议通过。
- 该测试协议本身不是缺陷：它编码的产品保证是"neutral reset 的控制批量
  对 Host 可观测时即完整，一个 render quantum 足以排空整个批量"。缺陷在
  产品侧批量入队次序违反了这一保证。本 Task 不改测试语义。

## Design

`packages/application-facade/src/performance_engine_adapter.cpp` 的
`reset_neutral`：把 Pad gates 清理与 typed Filter release 移到 legacy
gesture 突发**之前**入队。gesture 计数是批量唯一的外部可观测进度；它开始
移动时整个批量必然已完整入队，单个 audio drain 即 ACK 全部三个通道。

- 等待保证不缩小：`ResetTargets` 仍覆盖 gestures／filter controls／gates
  applied 三条通道，`reset_reached()` 不变。
- 游标阶段重排：0＝gates 清理，1＝typed Filter release（按 snapshot 条件
  发布），2..`legacy_gesture_count`+1＝gesture 突发；queue_full 仍返回
  pending 且游标续跑不重复入队。
- 音频线程应用次序变为 gates→filter→hold_off→releases：终态同为 neutral
  （HOLD 下 typed release 先记 frozen、hold_off 随后解冻，等价）。
- `tests/core/facade/performance_engine_adapter_test.cpp` 的
  `test_reset_queue_pressure_continues_without_duplicate_gestures` 按新
  次序更新 pacing 断言（4 个空槽下 gates 占第一槽，gesture 只得 3 个），
  并新增 gates 先于 gesture 批量完成的断言；被测性质（queue 压力下续跑
  不重复）保持不变。

## Lane audit（核查结论：无 lane 选择缺口）

- `scripts/ci/scope_policy.json`：`packages/application-facade/` 前缀规则已
  选中 `web_runtime_host`、`core_ubuntu`、`core_asan`、`core_coverage`、
  `core_macos` 等 lane；`web_runtime_host` lane 的
  `scripts/web-runtime-host.sh proof`（`run_nonbrowser_tests`）显式运行
  `host.web_control_runtime`；core lane 的 `full` tier 含 host tier。
- `scripts/ci/test_scope_policy.json`：`full_prefixes` 已含
  `packages/application-facade/`，变更即要求 complete 选择。
- 漏网原因不是 lane 选择，而是 Task 级本地验证只跑了
  `scripts/core.sh test dev fast`（unit＋component，207 项，按设计不含
  host tier）；quick lane 的 `ci_only` 备注本就声明 host/concurrency 由
  full lane 与日常风险策略保留。按 minimization principle 不为已覆盖的
  不变量增设冗余 gate，本 Task 不改 lane 文件。

## Declared files

- `packages/application-facade/src/performance_engine_adapter.cpp`
- `tests/core/facade/performance_engine_adapter_test.cpp`
- `docs/plans/2026-10-12-replay-reset-rendezvous-fix.md`（本文件）

## Tests

- Owning 证明：`ctest --preset dev -R '^host\.web_control_runtime$'`
  RED→GREEN。
- Revert 证明：stash 修复→重建（fresh mtime，build exit 0）→同一测试在
  同一行（`control_runtime_test.cpp:7371`）HOST_TIMEOUT 复红→恢复修复→
  重建复绿。
- `ctest --preset dev -R '^facade\.performance_engine_adapter$'`（component
  tier，fast lane 内）。
- `scripts/core.sh test dev fast`。

## Version Management

Version impact: application-facade Module SemVer PATCH 级行为修复——公开
C++ 布局、端口虚函数与 C ABI envelope 均不变，无 Contract 变化，无
Product Build allocation；随下一次版本结算计入。

## Documentation impact

Documentation impact: none — portal 的 application-facade 页陈述的是
"全通道 neutral 终态，各自等待真实 drain"的集合与 drain-ACK 保证，二者
本修复均不改变；批量内部入队次序不是已文档化的事实，且无 Product/Module/
Host/Provider/Contract/Channel/revision 身份变化。
