# W1 — Web Host 和 typed SDK producer 接口

状态：实施 Task 计划。本文件是
[producer/consumer 计划](2026-10-11-performance-live-control-producers.md)
W1 节的实施计划；W1 节是边界权威，本文件不扩大其 scope。

## Plan amendment（已获 shipping owner 批准）

W1 节原 Declared files 漏列 `packages/web-runtime-platform/web/protocol.mjs`。
该文件是 JS 侧 operation 注册表（`HOST_OPERATIONS`/`OPERATION_SET`）加逐
operation payload/result 校验器：任何 Host 调用都经 `createRequestEnvelope`
校验，未注册的新 typed wire（`performance.live.status`/`performance.live.control`
及 headered `record.*` 新键）在 JS 侧即以 `HOST_PROTOCOL_MISMATCH` 被拒
（已在 base `d21ea97c` 实测证明）。同节 inventory 锁定测试
（`performance_protocol.test.mjs`）也因此必须同步。capability 不变，属
declared files 补全；修订已落回 W1 节列表。修订后 declared files 共 18 个。

同一类别的第二处遗漏在实施中发现：`packages/web-runtime-platform/src/bridge.cpp`
的 `supported_operation` 注册表是 ControlBridge.submit 的 native 入口门禁，
未注册的新 operation 在那里以 `HOST_PROTOCOL_MISMATCH` 被拒绝
（`test_bridge_admits_every_stage10_performance_operation` 实测红→绿证明）。
第三处是同模块的协议总锁定测试 `packages/web-runtime-platform/test/
protocol.test.mjs`（HOST_OPERATIONS 与 operation-class deadline 锁定随注册表
同改）。两者与 protocol.mjs 同属注册表/锁定补全，一并纳入本 Task 的改动与
说明，待 owner 在 review 确认（如需单列可拆分）。

## Outcome and authority

在 Web Host 暴露 P1 的 headered live-control producer：严格 Host
registration/validator、typed SDK serializer/status、有界 Runtime action
FIFO，以及真实 capture 的 started 应用 ACK 闭合协议。

**Authority:**

- [producer/consumer 计划 W1 节](2026-10-11-performance-live-control-producers.md)。
- [D0 编码决定](../prd/decisions/2026-10-11-performance-live-control-encoding.md)：
  R1 的 start/started ACK 协议与双 ready 边界、SDK 有界 FIFO（1 inflight +
  1 普通 waiting + 64 open Pad 各 1 release slot + 1 cleanup token）、
  live-only identity (epoch, expected_control_sequence, command_id)、
  typed wire exact keys 与 uint64 opaque 序号。
- P1（`d21ea97c`）落地的 Facade 消费面：`PerformanceLiveControlSink`、
  begin fence/mapping、admission ledger。W1 不修改 application-facade。

## Facts this Task relies on

Checked on `d21ea97c71da281f89ac78238f6fcceb8b03e638`（本 worktree base）。

- `control_runtime.cpp` 逐 operation 校验（:647 起）与注册表（:3321）；
  performance 命令经 `service_performance_adapter()` 后注入 retained
  `project_path` 转发 Facade。engine 生命周期（restart → start_epoch 变化）
  由 Facade adapter 失效旧 epoch，bridge 侧无需自证。
- `runtime_session.mjs` 的 `serializeRuntimeAction` 是无界 Promise tail；
  capture start（:1671）在 postMessage 后立即 resolve；worklet 协议只有
  start/stop/batch/stopped/failed。
- `protocol.mjs` 同时持有 operation 注册表与逐 operation payload/result
  校验器；inventory 锁定测试在 declared 的 `performance_protocol.test.mjs`。
- `performance_master_capture.mjs` 的 controller 已有唯一 active 记录、
  stop ACK 30s 预算、processor failure 与 close 语义；W1 在其上加
  pending-start 占有与 started ACK。

## Design

### protocol.mjs（JS 注册表 + 校验器）

- `HOST_OPERATIONS` 追加 `performance.live.status`、`performance.live.control`
  （按既有排序位置插入）。
- payload 校验：`performance.live.status` 空 payload；`performance.live.control`
  exact keys `{control_epoch, command_id, expected_control_sequence, intent}`，
  epoch/command_id 为 UUID，`expected_control_sequence` 为规范十进制字符串
  （无符号、无前导零、JS safe 范围由字符串语义承载，不转 Number 比较身份）；
  intent 逐 kind exact keys：filter_parameter（type 枚举 lp/hp/bp、
  cutoff_hz 20..20000、resonance_milli 0..1000）、filter_release、
  fx_parameter（fx 八名、value 0..1000）、fx_release、pad_mute/pad_solo
  （slot 0..63 safe integer、enabled 布尔）、clear_pad_gates、hold_on/off；
  generation 键为 UUID。
- headered 可选键：`performance.record.begin` 允许追加 `control_epoch`；
  `record.event`/`record.launch-request` 允许追加 `control_epoch` +
  `expected_recording_sequence`（同规范十进制）。event 的新 kind 校验
  （filter_parameter/filter_release/pad_mute/pad_solo/clear_pad_gates 及
  新形状的 fx_engage/fx_move/fx_release）只在两新键同时存在时启用；
  旧 profile 形状不变。
- result 投影同步注册两新 op 的闭合键（status：available/epoch/accepted/
  applied/序列/pending 位；control：command_id/epoch/control_sequence/
  gesture_generation/accepted/applied/replayed）。

### control_runtime.cpp（native registration/validator）

- `performance_operations` 注册 `performance.live.status`（query）与
  `performance.live.control`（command）；deadline 表入 1s 组。
- 校验器与 protocol.mjs 同规则（C++ 侧独立实现，作真正边界 oracle）：
  规范十进制由字符串解析校验（不转 double）；slot 0..63；intent exact
  keys。headered record.* 新键同形校验。
- 转发仍走既有注入 retained project_path 路径；epoch 与 Project 的绑定、
  stale 拒绝由 Facade/engine adapter 裁决（P1）。

### SDK（runtime_types.d.ts + runtime_session.mjs）

- 新类型：`PerformanceLiveControlIntent` 联合、`PerformanceLiveStatus`、
  `PerformanceLiveControlResult`、headered begin/event/launch 的扩展结果
  （`fxBindings`、`coreControlReady`、`nextRecordingSequence`、
  `inputSequence`）。
- 新 session 方法：`queryPerformanceLiveStatus()`、
  `applyPerformanceLiveControl(request)`（SDK 跟踪 epoch 与
  expected_control_sequence 窗口，exact retry 原样重发）；headered 录制经
  `beginPerformanceRecording` 的可选 `controlEpoch` 进入，event/launch 自动
  携带窗口字段；全部经有界 FIFO。
- 有界 Runtime action FIFO 取代无界 Promise tail：至多 1 inflight + 1 普通
  waiting + 每个 open Pad gesture 各 1 个 matching release slot（上限 64）+
  1 cleanup token。普通输入超额明确 reject；不合并已接收控制值；release 永不
  丢；cleanup 对未 admitted 的 waiting 输入显式 reject 其 promise。
- 双 ready 门：headered begin 后 SDK 轮询 record.status 至
  `core_control_ready`，再以 `{control_epoch, session_id, begin_command_id}`
  binding 调真实 capture start 并等 worklet `started` ACK；两端匹配同一
  target/begin 才放行 FIFO 中暂存的 recorded input。任一端失败/关闭/超时
  都走 bounded stop 清理；late ACK 不复用。

### Capture controller / worklet（started ACK）

- start 消息 `{type:"start", generation, binding}`；binding 为
  `{control_epoch, session_id, begin_command_id}` 或 null（旧 caller）。
- worklet 实际处理 start（设置 generation、清 sequence/frames）后、下个
  process 前回同 shape 的 `{type:"started", generation, binding}`。
- controller：发送前占有唯一 pending start；promise 仅在 owner/generation/
  binding 严格匹配的 started ACK 后 resolve，返回不可变 started receipt。
  旧 generation ACK 忽略；当前 generation 但错 binding/额外字段/重复
  started/started 前的 batch 均为协议失败：reject pending start 并清理；
  原 batch sequence/stop ACK 严格性不变。close/replacement/processor
  failure/postMessage 失败使 start reject 并释放占有；不能证明 tap 停下
  则该 tap/context 标 unavailable 直到 callback-drained replacement。
  start ACK 复用既有 30s 预算作独立 start failure timer。

## Declared files（完整边界，18 个；含已批准的修订）

- `packages/web-runtime-platform/src/control_runtime.cpp`
- `packages/web-runtime-platform/web/runtime_types.d.ts`
- `packages/web-runtime-platform/web/runtime_session.mjs`
- `packages/web-runtime-platform/web/performance_master_capture.mjs`
- `packages/web-runtime-platform/web/performance_master_tap_worklet.js`
- `packages/web-runtime-platform/web/protocol.mjs`（修订追加，见上）
- `packages/web-runtime-platform/src/bridge.cpp`（同类注册表补全，见上）
- `packages/web-runtime-platform/test/protocol.test.mjs`（同类锁定测试补全，见上）
- `packages/web-runtime-platform/test/performance_bridge_test.cpp`
- `packages/web-runtime-platform/test/control_runtime_test.cpp`
- `packages/web-runtime-platform/test/performance_protocol.test.mjs`
- `packages/web-runtime-platform/test/runtime_session.test.mjs`
- `packages/web-runtime-platform/test/performance_master_capture.test.mjs`
- `packages/web-runtime-platform/test/performance_master_tap_worklet.test.mjs`
- `apps/docs-site/docs/core/modules/web-runtime-platform.mdx`
- `apps/docs-site/docs/platform/web-runtime.mdx`
- `docs/plans/2026-10-12-web-live-performance-controls.md`（new，本文件；
  覆盖 W1 节原文的 10-11 文件名）
- `apps/docs-site/diagrams/web-runtime-platform.architecture.json`
- `apps/docs-site/static/diagrams/web-runtime-platform.html`
- `apps/docs-site/static/diagrams/web-runtime-platform.svg`

## Lowest-tier verification / defect oracles

- `host.web_performance_bridge`（performance_bridge_test.cpp +
  control_runtime_test.cpp，真实 Facade Application）：两新 op 与 headered
  键的 exact 注册/校验；未知/额外字段、非法单位、64-bit 有损 mask 拒绝；
  绑定 retained Project + epoch 的 live 命令真实到达 engine 状态；
  replacement 后旧 target 命令 stale 拒绝。
- Node `performance_protocol`：camelCase↔wire 精确、注册表/校验器/结果投影
  闭合、inventory 计数同步。
- Node `runtime_session`：有界 FIFO 上限与 cleanup reject、同 identity
  原样重试、closed/replaced session 守卫、双 ready 前零投递。
- Node capture controller/worklet：start promise 在真实 started ACK 前
  pending；错 generation/epoch/binding、close、processor failure、超时均无
  放行或 late ACK 继承；正常 ACK 后 batch 严格序保持。
- mutation 证明 ≥1（如去掉 started ACK 的 binding 对照或 FIFO 的 waiting
  上限），rebuilt artifact RED 落在命名断言行。
- `scripts/docs-site.sh check`；TypeScript consumers 编译；
  `tests/build/ci_change_scope_test.py`。不跑完整 Emscripten proof：W1 不触及
  wasm 边界行为（bridge 的 C++ 校验层在 native 构建中验证）。

## Version Management

Version impact: web-runtime-platform MINOR——typed/JSON 追加兼容；无公开
C++ 布局变化（control_runtime.cpp 为 .cpp 内部校验）。capture
controller/worklet 协议新增 started 与 begin binding：部署必须 SDK/worklet
配套，旧 cached 工作流不得假成功。Module/Host 身份在 V1 结算，此处不猜。

## Documentation impact

Documentation impact: required——`/core/modules/web-runtime-platform/` 与
`/platform/web-runtime/`；源图与生成 HTML/SVG 同 Task 更新。

## Pitfall Impact

候选 pitfall：JS 侧 Host 协议是双注册表（protocol.mjs + control_runtime.cpp），
新增 operation 必须三处同改（两注册表 + inventory 测试）。shipping 前按
issue-done 评估登记。
