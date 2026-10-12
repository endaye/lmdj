# P1 — Facade 一次 admission、录制起点和重放/neutral 闭合

状态：实施 Task 计划。本文件是
[producer/consumer 计划](2026-10-11-performance-live-control-producers.md)
P1 节的实施计划；P1 节是边界权威，本文件不扩大其 scope。

## Outcome and authority

在 Application Facade 闭合新 profile（header_input_sequence）的 Core 一次
admission kernel、record begin fence 与 actual applied state、Header
Replay-before-Pad、recording/live exact retry、stale epoch 与全部 neutral 终态。

**Authority:**

- [producer/consumer 计划 P1 节](2026-10-11-performance-live-control-producers.md)：
  declared files 与 defect oracles 的完整边界。
- [D0 编码决定](../prd/decisions/2026-10-11-performance-live-control-encoding.md)：
  R2 admission ledger、R3 binding/adoption、reserve→durable append→publish 两步
  持久化、exact retry 窗口、recovery-only closure/seal、neutral 终态。
- P0（`9555be7b`）已落地的消费面：project-io 的
  `PerformanceAdmissionLedger`/`complete_performance_admission`/
  `lookup_performance_admission`/`close_performance_transients_for_owner_loss`
  与 `BeginPerformanceDraftRequest{initial_live_state, initial_checkpoint}`；
  authoring-domain 的 headered profile、typed `filter_change`/`pad_gates_set` 与
  profile-aware canonical ordering；cooker 的
  `PerformanceReplayProjection::initial_live_state`。P1 不修改这些文件。
- F1（`a61ab819`）的 typed Filter engine 面（`enqueue_filter_gesture`/
  `filter_control_status`）与 M1（`7df1af16`）的 `enqueue_pad_gates`/
  `pad_gates_status`。

## Facts this Task relies on

Checked on `7df1af16df5e6d864ca7968626d63f84a5d9cb63`（本 worktree base）。

- Facade 现状：`performance_event` 先投 live gesture 再写 Journal（audio-before-
  journal），无 durable receipt（`event_receipts` 仅内存 map）；fx_move 有
  128-tick coalescing；PatternLaunch 序号在 ACK 时 `next()`（application.cpp
  service_performance_launch）；begin 无 header、无 fence、无 profile 分支。
- Engine adapter 是 master-control queue 的唯一 producer：所有 FX/Filter/pad-
  gates/tempo enqueue 都经 `PerformanceGestureSink`/replay sink/adapter 自身。
  因此 adapter 侧的 reserve = 容量检查（sole-producer 下精确），publish = 实际
  enqueue；不需要 engine 新增 reserve API。
- Engine 暴露的 drain 证据：`master_fx_telemetry()`（enqueued/dequeued gestures、
  filter controls、tempo）、`filter_control_status()` 与 `pad_gates_status()` 的
  accepted/applied sequence+epoch。四个计数同属一条 FIFO，求和即队列位置。
- `MasterFxChain::filter_live_state_after` 是公开纯函数，adapter 的 accepted
  shadow 与 audio applied 语义同源。
- 现有 reset_neutral 只等 `dequeued_gestures`，不证明 typed Filter 与 mask 清理；
  Replay controller 无 header 概念，零事件直接进 complete。
- Headless bridge（`make_headless_performance_runtime_bridge`）没有 engine；其
  header 保持不变（非 declared file），新 profile begin 在 headless 配置下明确
  返回 audio producer unavailable。

## Design

### 端口（performance_ports.hpp，新增；ABI MAJOR debt）

- `PerformanceLiveControlState`：`domain::PerformanceInitialLiveState`（控制参数
  全量）+ 按 FX ordinal 的 8 个 `optional<string>` runtime generation（仅
  engaged binding；不耐久）。
- `PerformanceLiveControlSnapshot`：accepted/applied 两份 state + 两个 Core
  control sequence + engine start_epoch。
- `PerformanceLiveControlIntent`（variant）：`filter_parameter{phase,parameter,
  value[,generation]}`、`filter_release{generation}`、`fx_parameter{phase,fx,
  value[,generation]}`、`fx_release{fx,generation}`、`pad_mute/pad_solo{slot,
  enabled}`、`clear_pad_gates`、`hold_on/hold_off`。单参数 intent 由 Core 从
  accepted state 原子派生完整新状态；release 参数值来自 Core state。
- `PerformanceLiveControlReservation`：reserve 的产物（翻译后的 engine 消息、
  派生后状态、engage 时新分配的 runtime generation、队列位置）。
- `PerformanceLiveControlSink`：`current_control_epoch()`（nullopt=未绑定/已
  失效）、`bind_control_target(project_uuid)`/`invalidate_control_target()`、
  `live_control_snapshot()`、`reserve_live_control(epoch, intent)`（含 epoch/
  形状/范围/binding 校验与 sole-producer 容量预留，零副作用）、
  `publish_live_control(reservation)`、`cancel_live_control(reservation)`、
  `begin_fence(epoch)`（捕获 accepted 快照为 header、返回 fence 队列位置；
  queue-full 失败）、`fence_readiness(token)`（pending/ready/diverged：applied
  位置越过 fence 且该位置的逐字段状态等于 header 且 epoch 未变；diverged 由
  adapter 的 per-position shadow 历史判定，不靠最新值猜）。

### Engine adapter（performance_engine_adapter.{hpp,cpp}）

- `EnginePerformanceAdapter` 末尾追加 `live_control` 成员（aggregate positional
  约定；`make_engine_performance_adapter` 一并创建，与 gesture_sink 共享同一
  实现对象，使旧 sessionless `fx.gesture` 的成功 admission 也更新同一 accepted
  shadow 与 generation 跟踪）。
- Adapter 内部：accepted shadow（hold/filter/7FX/masks + 每 FX runtime
  generation）+ 每条成功 admission 的 `(position, state)` 有限历史；applied
  位置 = 四通道 drain 计数求和。engine start_epoch 变化 → epoch 失效，下一次
  verified bind 换新 UUID；`bind_control_target` 只在 UUID 变化或失效后换新
  epoch（同 Project 的 Bank/Pattern/revision prepare 不 rebind）。
- UUID 由 adapter 以 random_device 生成（runtime 身份，不耐久）；Facade 的
  logical recording gesture id 由 begin command_id 派生（确定性，exact-retry
  安全，沿用 derived_asset_id 模式）。
- Replay sink 扩展（performance_replay.hpp 端口）：`apply_filter_change(phase,
  type, cutoff, resonance)`、`apply_pad_gates(muted, solo)`、
  `apply_initial_live_state(state)` + `initial_live_state_applied()` 进度；
  `reset_neutral` 扩展为 hold_off + 7 release +（independent 活跃时）typed
  filter release + `pad_gates(0,0)`，并等待全部四类 drain 证据；queue-full 保持
  pending（沿用现有 cursor 续传）；engine stopped 且 callback-drained 走
  quiescence 短路。

### Replay controller（performance_replay.cpp）

- projection 携带 `initial_live_state` 时：begin 立即经 sink 恢复 header（控制
  阶段整体恢复），`advance_to` 在 `initial_live_state_applied()` 确认前不调度
  任何 Pad/Pattern/FX 事件；零事件 Performance 同样先 header ACK 再按既有
  reset_neutral 规则 complete。kind 7/8 事件分别走 typed filter / pad gates
  sink。legacy projection 路径逐位不变。

### Facade kernel（application.cpp）

- 新 operations：`performance.live.status`（query）、`performance.live.control`
  （command），注册入 operation 表。live-only 不写工程：identity
  (epoch, expected_control_sequence, command_id) 的内存窗口（1 inflight + 最近
  1 completed），成功（含 no-op）推进 control sequence；reserve→publish→
  complete，known failure 零副作用可原身份重试。
- `performance.record.begin` 第七键 `control_epoch` 选择新 profile：Core load
  对照 bound target UUID → reserve fence cell（queue-full 不建 draft）→ 捕获
  header+bindings → `begin_performance_draft`（initial_live_state + 含 logical
  ID 的 initial checkpoint）→ 发布 fence → 响应 pending + `fx_bindings`
  mapping。Facade 不启动 Webtap、不宣称 host_capture_ready；
  `core_control_ready` 只在 fence ready 后由 status/service 置位。Pad/Pattern
  admission 在 ready 前明确拒绝；FX/mask 控制不受影响（fence 按位置对照，
  不受后续控制干扰）。旧六键 begin 的响应/fingerprint 逐字节不变。
- `performance.record.event` 新 profile 分支（携带 control_epoch +
  expected_recording_sequence 规范十进制字符串）：identity
  (session, expected, event_id)，fingerprint = SHA256(canonical request 减
  project_path)。先查内存 frozen 窗口，再查 durable ledger
  （`lookup_performance_admission`）：exact→原 receipt/推进原 pending（complete
  metadata 重试零重复 publish）；collision/retry_expired/out_of_order/occupied
  分别拒绝且零 enqueue。fresh：reserve → read_tick/next 各一次 → 冻结 candidate
  → durable append（pending receipt, not_published）。known failure：取消
  reservation、保留 frozen tuple 供原 identity 重试（不二次分配 tick/seq）。
  unknown：冻结 session（recovery_required），cell 不发布，不假报 absent。
  known success：publish（engine refusal 如 not_running → result no_audio）→
  append `admission_complete`；complete 写入 unknown → 冻结并保留已发布事实，
  不回滚音频、不重投。
- 新 profile 禁一切 FX move coalescing：每个实际改变参数的 move 各留真实
  tick/input_sequence；no-op move 不产生 Project event 但推进 admission
  sequence 并保存 receipt（result no_audio，event_input_sequences 空）。
  PadHit 用 press 的 input_sequence；release admission 自身推进 high-water。
  Stop/owner-loss 的自动 FX/HOLD 关闭为每个合成事件各 `next()` 一次。
- `performance.record.launch-request` 新 profile：reservation 时冻结
  input_sequence 并耐久（空 events + pending receipt）；ACK 复用冻结序号产生
  PatternLaunch 事件并 `admission_complete`；cancelled/failed outcome 以
  no_audio complete。旧 profile 的 ACK 时分配不变。
- reattach：无内存 session 时新 profile 请求查 durable ledger——terminal
  prepared 只返回显式 unknown（零 enqueue）；recovery-only closure/seal 走 P0
  `close_performance_transients_for_owner_loss` 与既有 owner-lock/reconcile
  路径，Facade 不伪造 completion/applied ACK；新 Performance 的 begin 自带空
  ledger，不被旧 terminal pending 阻塞。
- `performance.record.status`：新 profile session 增加 `profile`、
  `core_control_ready`、`next_recording_sequence`；旧 session 响应不变。
- headless（无 live_control port）：新 profile begin/event 明确
  `performance_live_control_unavailable`，旧 profile 原样。

### 生命周期映射（oracle :302 的 Core 面）

- recording stop 只写 Journal 闭合，不动 live engine 状态（旧独立开关规则）。
- "leaving Perform" 的 Core 可证面：HOLD=true 下 `clear_pad_gates`/pad gate
  intent 不被 HOLD 冻结（mask 不是 FX），typed filter 在 HOLD 下按既有冻结
  语义保留；engine 生命周期（restart/换工程 → start_epoch 变化）使旧 epoch
  失效且 M1 start 已保证两组 mask 中性。
- resample/capture receipt 的原 Wav 仍是唯一音频依据；event Replay 只证明控制
  到达同一 DSP，不宣称重建 PCM（resample_performance 既有断言不动）。

## Declared files（完整边界，19 个）

- `packages/application-facade/include/lmdj/facade/performance_ports.hpp`
- `packages/application-facade/include/lmdj/facade/performance_replay.hpp`
- `packages/application-facade/include/lmdj/facade/performance_engine_adapter.hpp`
- `packages/application-facade/include/lmdj/facade/application.hpp`
- `packages/application-facade/src/application.cpp`
- `packages/application-facade/src/performance_replay.cpp`
- `packages/application-facade/src/performance_runtime.cpp`
- `packages/application-facade/src/performance_engine_adapter.cpp`
- `tests/core/facade/performance_operation_contract_test.cpp`
- `tests/core/facade/performance_gesture_admission_test.cpp`
- `tests/core/facade/performance_session_test.cpp`
- `tests/core/facade/performance_replay_test.cpp`
- `tests/core/facade/performance_engine_adapter_test.cpp`
- `tests/core/facade/performance_runtime_bridge_test.cpp`
- `tests/core/facade/resample_performance_test.cpp`
- `apps/docs-site/docs/core/modules/application-facade.mdx`
- `docs/plans/2026-10-12-performance-live-control-admission.md`（new，本文件）
- `apps/docs-site/diagrams/application-facade.architecture.json`
- `apps/docs-site/static/diagrams/application-facade.html`
- `apps/docs-site/static/diagrams/application-facade.svg`

## Lowest-tier verification / defect oracles

- `facade.performance_operation_contract`：两个新 operation 注册与 exact
  kinds/keys；Core-owned time/sequence（拒绝 Host tick/frame/input_sequence 键）。
- `facade.performance_gesture_admission`：新 profile 全事件语法（typed
  filter/mask/binding 双验证）；同 identity exact retry 一次；pre-write
  known failure 零副作用重试；post-write unknown 冻结 + 显式
  recovery_required；publish 后 complete metadata 重试零重复 apply（sink
  计数断言）；C2 exact/collision、C1 expired、stale epoch 均有 far-side
  零 enqueue 断言；禁 coalescing 的 Move500@(16,10)→Pad@(32,11)→
  Move900@(64,12) 反例；同 tick C→P 与 P→C 两序；预约 Pattern 冻结序号、
  ACK 复用；旧 profile 128-tick/fingerprint 原样。
- begin fence 确定性交错：pre-begin 变更入 header；begin-pending 期间的
  控制变更不改 header 且各出现一次；首个同 tick Pad 在 ready 前被拒、
  ready 后 admission；diverged → recovery_required。
- FX owning oracle：pre-begin engaged Delay500 + HOLD frozen Reverb700；
  mapping 只含 Delay；首 move/release 双绑定配对；旧 generation 拒绝；
  begin 不 fake engage、不 reset DSP（engine 侧 buffer 不变的直接断言）。
- `facade.performance_session_test`：producer 丢失后 prepared unknown 经
  recovery-only closure/seal 到 terminal；sealed 旧 retry 显式 unknown 且零
  enqueue；下一 Performance 新 ledger 不堵；owner 存活时拒绝例外。
- `facade.performance_replay_test` + `facade.performance_engine_adapter_test`：
  header（含零事件）先于任何 Pad/Pattern 恢复；type/cutoff/resonance 与
  mask 变更到达同一 DSP（adapter+真实 engine 的 PCM/status 断言）；
  complete/Stop/owner loss/reset queue 压力等待全通道 neutralized。
- `facade.performance_runtime_bridge_test`：headless 无 live-control port
  时新 profile begin 明确拒绝、旧 profile 不变。
- `facade.resample_performance_test`：原 Wav authoritative 断言不动。
- journal 故障注入（write 前/后 unknown）保留不可逆音频效果与显式
  unknown；mutation 证明 ≥1（如去掉 fence 的逐字段对照或 exact-retry 的
  零 enqueue 守卫），rebuilt artifact RED 落在命名断言行，恢复后 GREEN。
- `scripts/docs-site.sh check`；`tests/build/ci_change_scope_test.py`。

## Version Management

Version impact: application-facade ABI MAJOR debt — `ApplicationConfig` 追加
成员、`EnginePerformanceAdapter` 追加 `live_control`、
`PerformanceReplayRuntimeSink`/`PerformanceGestureSink` 端口虚函数增长，
公开 C++ 布局变化记入既有 ABI debt，V1 结算；C ABI envelope 不变，无
api_version 猜测。无 Project Contract/schema 变化（5.4.1 语法已在 P0 版本
化）；无 Product Build allocation。

## Documentation impact

Documentation impact: required — `/core/modules/application-facade/`；
`application-facade.architecture.json` 源图与生成 HTML/SVG 同 Task 更新。

## Pitfall Impact

候选 pitfall：audio-before-journal 旧路径不能当作新 profile 的证明（新路径
reserve→durable→publish）；fence  readiness 必须按队列位置的逐字段对照，
最新值比较在 begin-pending 交错下失真。shipping 前按 issue-done 评估登记。
