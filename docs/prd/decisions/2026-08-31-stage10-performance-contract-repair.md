# 已确认：Stage 10 以 Project Pattern 槽、耐久 Performance draft、Core 时间权威和两阶段 rebase 闭合实现 Contract

- 日期：2026-08-31
- 解决的问题：GitHub Issue
  [#488](https://github.com/endaye/lmdj/issues/488)。
- 替代范围：本文补充并在冲突处替代
  [`2026-08-28-perform-performance-object-v4.md`](2026-08-28-perform-performance-object-v4.md)
  的录制生命周期细节，以及
  [`2026-08-28-perform-momentary-fx-transient-gestures.md`](2026-08-28-perform-momentary-fx-transient-gestures.md)
  中把 quantum 合并归给 Host 的实现口径。未被本文触及的既有产品结论维持不变。

## 结论

### 1. Project Truth 拥有 Pattern Launch 槽

`lmdj.project.v4` 的 `pattern_slots` 是恰好 16 个有序、可空的槽。空槽编码为
`null`；占用槽编码一个 `PatternId`。占用的 ID 必须存在于同一 Project 的
`patterns`，且同一个 Pattern 不能同时占据两个槽。

v3→v4 总迁移把 16 个槽全部初始化为空。`pattern.slot.assign`、
`pattern.slot.clear` 与 `pattern.slot.move` 是带 `command_id` 和
`expected_revision` 的 Authoring Command：

- assign 要求目标槽为空、Pattern 存在且未占用；
- clear 要求目标槽已占用；
- move 要求源槽已占用、目标槽为空且两槽不同；
- 违反前置条件时 fail closed，不静默覆盖或交换；
- 同一 `command_id` 与同一指纹按既有 receipt 幂等重放，碰撞失败；
- 每次成功的语义变更只推进一次 Project revision。

Performance 的 `pattern_launch` 只保存 `pattern_slot: 0..15`。Replay 在开始时
固定当前 Project revision，并从该 revision 的 `pattern_slots` 解析 Pattern；
空槽或已被清空的槽产生非致命静默 gap。

### 2. `record.begin` 原子创建耐久 draft

`performance.record.begin` 在同一 Project writer lease 下：

1. 校验 `expected_revision`、录制互斥与稳定身份；
2. 以调用方提供的 `performance_id` 创建名称为 `Untitled Performance`、事件为空、
   `recording_artifact = null`、`created_bpm = Project.bpm` 的 Performance；
3. 发布 manifest/receipt，使 Project revision 只推进一次；
4. 以发布后的 revision 和 Performance fingerprint 创建 active Journal。

若第 4 步失败，恢复逻辑必须能从 begin receipt 精确补建 Journal；不得留下一个
无法判定归属的 Project 对象。相同 `command_id`、`session_id`、
`performance_id` 和指纹精确重试返回原结果；任一身份碰撞均失败。

每次 manifest-backed flush 把 canonical events 追加进同一个 draft，并通过稳定
`session_id + flush_seq + command_id` receipt 推进 revision。Journal-only-until-save
被拒绝，因为它会使已经成功的 flush 在 Project Truth 中不可见。

### 3. stop、save、discard、恢复与 WAV 绑定

- `performance.record.stop` 只把 session 置为 stopped 并耐久封存 tail，不修改
  Project，也不消费 revision。
- `performance.save` 只接受 stopped draft；它原子提交 tail、最终名称和可选的
  WAV `ArtifactRef`，然后清除对应 Journal。
- `performance.discard` 删除 draft 与它的 active/stopped/recovery Journal；Host
  在成功响应后删除尚未绑定的临时 WAV。
- `performance.recovery.apply` 只把 fingerprint 匹配的耐久 tail 提交回原 draft；
  `performance.recovery.discard` 只丢弃恢复 tail，保留此前已 flush 的 draft。
  两条路径都把 sealed recovery 转成 stopped draft Journal（apply 的 flush 已
  complete，discard 的 tail 已移除），使后续 `save`/`discard` 有耐久状态依据。
- `performance.recording.bind` 只允许给没有录音引用、且没有 active/recovery
  Journal 的 Performance 绑定一个已验证 Artifact；同一 Artifact 幂等，另一
  Artifact 不得静默替换。
- `performance.rename` 与 `performance.delete` 同样要求没有 active/recovery
  Journal。delete 只删除 Project 引用；Artifact 生命周期仍走既有 GC。

Facade 不接受 Host 文件路径或原始 WAV bytes。`recording_artifact` 的精确形状是
`{sha256, media_type: "audio/wav", byte_length}`；绑定前必须确认该不可变 Artifact
已存在于 Project 管理存储，并重新验证 digest 与长度。

### 4. Core 独占输入时间、顺序与幂等权威

`performance.record.event` 的精确 payload 是
`{project_path, session_id, event_id, event}`。`event` 只能是：

```text
pad_press  { gesture_id, slot: 0..63, velocity: 1..127 }
pad_release{ gesture_id, slot: 0..63 }
fx_engage  { gesture_id, fx, value: 0..1000 }
fx_move    { gesture_id, fx, value: 0..1000 }
fx_release { gesture_id, fx }
hold_on
hold_off
```

Host 不得提交 `tick`、`runtime_frame` 或 `input_sequence`。Facade admission 从
Core 注入的权威 Transport 读取 tick，并分配单调 input sequence。相同
`event_id` 与相同 payload 返回原结果；相同 ID、不同 payload 是碰撞。
`gesture_id` 只用于 raw press/release 配对，不进入 Project Performance。

非法配对返回 `INVALID_ARGUMENT`，但不封存会话。Pad press 的开放手势状态先
耐久写入 Journal；release 后才形成 canonical `pad_hit`。owner loss 时，开放
Pad 在 `max(onset_tick + 1, last_durable_tick)` 闭合，并按
`(slot, gesture_id)` 稳定排序后封存。

### 5. Pattern Launch 只记录真实生效的边界

`performance.record.launch-request` 的精确 payload 是
`{project_path, session_id, request_id, pattern_slot}`。Host 不提供 tick。Core
从权威 Transport 预约下一 Bar，并返回 `{request_id, state: "pending",
target_tick}`。

同一边界尚未被 Audio Runtime claim 时，最新请求覆盖此前请求；已 claim 的请求
不能被改写，后来请求顺延到下一 Bar。只有 Audio Runtime 确认该边界实际应用后，
Facade 才写 `pattern_launch {pattern_slot, effective_tick}`。空槽也走同一 ack，
记录事件但不改变当前播放；边界前取消、发布失败或 owner loss 不写事件。

### 6. FX quantum 合并与异常闭合归 Core

Core 是唯一语义合并权威。Host 可以批量传输，但不得决定保留哪一条输入。

- 每个 FX、每个 128-frame audio quantum 最多发出一条 `fx_move`；同一 quantum
  最后 admission 的值获胜；
- 与当前有效值或待提交值相同的 move 去重；
- engage、release、hold_on、hold_off 永不合并；
- release 先排出同一 quantum 的最后 pending move，再执行 release，使 HOLD
  冻结松手时的最终值；
- owner loss/崩溃恢复在最后耐久 tick 按固定 FX 链序补齐所有开放手势的
  `fx_release`；若 HOLD 开启，再补 `hold_off`，随后封存；
- Replay 结束或中止总是把所有瞬时 FX 重置为 neutral。

恢复闭合事件代表 Core 实际执行的 Runtime reset，因此进入恢复后的 Performance，
而不是仅写恢复元数据。

### 7. BPM、Quantize、Swing 使用两阶段耐久 rebase

Performance rebase 白名单仍为 BPM、Quantize、Swing。admission、Project mutation
与 rebase 协调都在同一个 writer lease 下：

1. Project 修改前写 `rebase_prepare`，包含稳定 `command_id`、命令指纹、
   `from_revision` 和预期 `to_revision`；
2. Project manifest/receipt 可见后写 `rebase_complete`，推进 Journal
   `expected_revision`；
3. BPM 建立新的 Core timing anchor，已经记录的 tick 不变；Quantize/Swing 对
   Performance raw timing 零变换。

如果 Project receipt 已可见而 completion 未落盘，会话进入
`recovery_required`，拒绝新 event/flush。精确重试按 command receipt 对账，只补
completion，不重复 Project mutation；完成后恢复 active。没有可见 receipt 时，
只允许同一不可变命令重试。command collision、未知 Authoring Command 都 fail
closed。Sample 类 Command（含 armed Pad capture commit）失败但不会封存录制。

### 8. Facade 操作集合、请求与返回

操作名无通配符：

```text
Queries:
  performance.list
  performance.inspect
  performance.record.status
  performance.recovery.list
  performance.replay.status

Commands/actions:
  performance.record.begin
  performance.record.event
  performance.record.launch-request
  performance.record.flush
  performance.record.stop
  performance.save
  performance.discard
  performance.recovery.apply
  performance.recovery.discard
  performance.rename
  performance.delete
  performance.recording.bind
  performance.replay.begin
  performance.replay.stop
  performance.resample.commit
```

外部直接发起的 Project mutation 带 `command_id + expected_revision`。session-owned
flush 是唯一例外：Host 只带 `session_id + command_id`，`expected_revision` 必须
来自 Journal。stop 与 recovery.discard 另带稳定 `request_id`，但不带 revision。
Replay 是只读 Runtime action：begin 带 `replay_id + performance_id`，stop 带
`replay_id + request_id`，status 带 `replay_id`。

返回形状：

- Performance 管理 mutation：`{performance_id, committed_revision, replayed}`；
- Pattern slot assign/clear：
  `{pattern_slot, pattern_id|null, committed_revision, replayed}`；move：
  `{from_slot, to_slot, pattern_id, committed_revision, replayed}`；
- `performance.resample.commit` 沿用 D1 的 `SampleMutationResult`，另含源
  `performance_id`；
- event：`{event_id, accepted_tick, input_sequence, coalesced, replayed}`；
- launch request：`{request_id, state, target_tick}`；
- record status：session/performance identity、`state`、Journal revision、下一
  flush sequence、pending event 数、开放手势、HOLD、pending launch 与最后
  一次实际 launch ack；state 枚举为 `idle|active|stopped|recovery_required`；
- recovery candidate：session/performance identity、reason、耐久/待提交事件数、
  fingerprint；
- replay begin/status：replay identity、state、开始时固定的 resolved revision、
  event cursor 与总数。

`list` 精确返回
`{performances:[{performance_id,name,created_bpm,recording_artifact,event_count}]}`；
`inspect` 返回 `{performance:{id,name,created_bpm,recording_artifact,events}}`。
stop 返回 `{request_id,session_id,performance_id,state:"stopped",
pending_event_count,replayed}`；recovery.discard 返回相同 identity/state 结构；
replay.stop 返回 replay status 字段加 `request_id,replayed`。Replay 在
begin 时固定当前 Project revision 并在其上解析所有 Pad/Pattern 槽；它不做恢复
fingerprint gate，也不修改 Project。

## 原因

这些补充把此前只写到产品叙述、却无法由 Facade、Project I/O 与跨 Host 测试唯一
推导的边界变成可执行 Contract。Pattern 槽解决「记录 slot 却没有 slot truth」；
耐久 draft 与两阶段 rebase 保证 receipt、恢复和 revision 不分叉；Core 时间、
合并与 boundary ack 保证不同 Host 无法产生不同的 Performance；显式操作名和
形状让 CLI、MCP、Native、Web 与 Creator 能做一一同构的黑盒验证。

## 影响

本文是纯设计修复，不修改活动 manifest、Contract 工件、模块版本或 Product
Build。实现分成两个独立前置 Task（Pattern-slot Contract 与 Performance
lifecycle/rebase Project I/O）以及后续 Facade/Host Tasks；版本仍由 Stage 10
实施计划已锁定的 `lmdj.project.v4` / module targets / Product Build
`1.0.41.0` 支付。Portal current truth 在 Stage 10 集成 Task 更新。
