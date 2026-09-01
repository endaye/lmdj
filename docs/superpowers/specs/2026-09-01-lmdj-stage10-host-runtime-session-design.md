# LMDJ Stage 10 Host Runtime and Session Repair — 2026-09-01

日期：2026-09-01

状态：**已确认（2026-09-01）**——Performance 的 tick/顺序/Launch ack/Replay
progression 权威是 Core 交付物，Host 只组合与转发；会话连续性走「进程内活跃
会话 + 跨进程耐久身份」双路径。本文把 Stage 10 Task 6（#432）开工预检发现的
不可实现边界锁定为可执行 Contract；先交付 prerequisite #523 → #524 → #525，
再恢复 Task 6。

关联权威：

- [`2026-08-28-lmdj-stage10-perform-design.md`](2026-08-28-lmdj-stage10-perform-design.md)
  P10-D13、P10-D20、P10-D21、P10-D22、P10-D25；
- [`2026-08-31-stage10-performance-contract-repair.md`](../../prd/decisions/2026-08-31-stage10-performance-contract-repair.md)
  §5、§6；
- [`2026-09-01-lmdj-stage10-replay-lineage-contract-design.md`](2026-09-01-lmdj-stage10-replay-lineage-contract-design.md)
  RLC-D7、RLC-D8、RLC-D9；
- Stage 9 acknowledgement 机制（#376，
  `packages/web-runtime-platform/src/control_runtime.cpp` 的
  `drain_sequence_bar_boundary` 谓词）。

## 1. 问题

Task 6 的开工预检确认五项无法从当前代码和批准文档唯一推导或根本不存在的
边界：

1. **三个 Performance 权威接口没有任何产品实现。**
   `PerformanceClock`、`PerformanceInputSequencer`、`PatternLaunchAcknowledger`
   只存在于两个 facade 测试文件的 fake 中；C API
   （`packages/application-facade/src/c_api.cpp:255`）、CLI
   （`apps/core-cli/src/main.cpp:366`）、Native Host
   （`apps/native-host/src/main.cpp:1053`）、Web bridge
   （`packages/web-runtime-platform/src/bridge.cpp:2607`）四个构造点全部注入
   `nullptr` 加 `make_unavailable_performance_replay_controller()`。因此
   `performance.record.event` / `.launch-request` 恒返回
   `performance_authority_unavailable` / `performance_launch_authority_unavailable`，
   `.flush` 传导性失败，`performance.replay.*` 恒不可用。P10-D21/P10-D22 又
   （正确地）禁止 Host 自造时间与顺序——两边相夹，Task 6 不可实现。
2. **CLI 每进程恰好一个请求，会话无载体。**
   `lmdj-core` 的 argc 必须是 6 或 8，无 stdin 路径；`Application::~Impl` 在
   进程退出时把 Performance journal 以 `owner_lost` 封存。`begin` 与 `event`
   无法出现在同一个 CLI 进程里。
3. **跨进程 flush 重放被内存态 owner guard 挡住。**
   `ProjectStore::execute_performance_flush` 对
   `PerformanceFlushIdentity{session_id, flush_seq, command_id, performance_id}`
   （持久于 `history/transactions/`）完全幂等，但 Facade 在触达它之前先检查
   进程内 `performance_sessions`（`application.cpp:5285`），新进程恒得
   "Performance flush owner does not match"。Task 6 要求的「MCP flush 由新
   CLI 进程重放得 `replayed: true`」因此不可达。
4. **`performance.recovery.list` 是 query 却会封存活跃 journal。**
   它经 `reconcile_performance_recovery`（`project_store.cpp:5351`）把带
   pending 状态的活跃 journal 封成 `owner_lost`；Sequence 的同名 query 从不
   封存。跨进程场景下，一个观察者进程的 list 会把另一个进程的活跃会话封掉，
   与 P10-D25 的 query 只读纪律冲突。
5. **Native Host 没有 pattern publication 路径，构造顺序阻断接线。**
   `apps/native-host/src/main.cpp` 中不存在 `publish_pattern_view` 调用（只发布
   sample bank）；`Application` 在拥有 `engine_` 的 `NativeHost` 之前构造；
   `RealtimeEngine` 只暴露可轮询的 `pattern_telemetry()` / `telemetry()`（无
   ack 回调）；仓库中不存在 frame→tick（`kBarTicks4x4 = 3840`）换算。

同一预检还确认两处必须补的契约缺口：三个权威接口的 header 零注释（tick 域、
单调性、每次 admission 恰好读一次的义务只由测试 fake 的 `.at()` 越界隐式
把守）；开放手势的耐久闭合路径 `close_performance_transients` 本身依赖缺失的
clock/sequencer，权威缺席时 owner-loss 闭合被静默吞掉。

## 2. 结论

### HRS-D1：Performance Runtime 权威是 Core 交付物

`PerformanceClock`、`PerformanceInputSequencer`、`PatternLaunchAcknowledger`
和 `PerformanceReplayController` 的产品实现是 application-facade（headless
bridge）与各 Host 内 Core-composed adapter（native）交付的 Core 代码。Host
构造点只做组合与注入，不实现时间、顺序、合并、slot 真相或 replay 语义。
P10-D21/P10-D22 的语义不变。三个权威接口补齐锁定注释：tick 域是 4/4 下
3840 ticks/bar 的音乐 tick；`read_tick()` 必须单调不减；幂等重放短路发生在
权威读取之前，因此每次成功 admission 恰好消费一次 `read_tick()` 与一次
`next()`；两者的失败按 `foundation::Result` 原样上抛。

### HRS-D2：headless transport 是合法的 Runtime 边界权威

P10-D22 的「只有 Audio Runtime 实际边界 ack 后才记录 effective tick」泛化为
「只有**已安装的 Core Runtime transport** 的实际边界 ack 才记录 effective
tick」。无音频设备的 Host（CLI、MCP/C API 默认组合）安装 Core 提供的
deterministic headless transport：steady-clock 源按 SR-D25 整数有理锚点映射到
tick；预约返回下一 Bar 且 `claimed` 恒为 false；未跨界前 latest-wins 替换；
transport 在 service 泵观察到 tick 跨过 `target_tick` 时以恰好 `target_tick`
为 effective tick 产生一次 `applied` outcome。Host 仍然不提供任何时间与顺序；
transport 的时间源可注入以获得确定性测试。claimed-defer 路径的 witness 属于
native/web adapter 与 facade fake，headless transport 不伪造 claim。

### HRS-D3：权威时钟的 BPM 锚点由 Facade 通知

`PerformanceClock` 接口增加锚点通知：Facade 在 `performance.record.begin`
成功后以 draft BPM 锚定，在白名单 BPM rebase 的 `rebase_complete` 可见后以
新 BPM 在当前 tick 重锚。锚点算术遵守 SR-D25 的整数有理规则；已记 tick 不动
（SR-D14）。测试 fake 同步实现该方法。

### HRS-D4：会话连续性 = 进程内活跃会话 + 跨进程耐久身份

活跃 Performance 会话（开放手势、event/launch receipts、pending reservation）
是单进程 Facade admission 状态，**不跨进程迁移、不从 Journal rehydrate**；
owner loss 按 P10-D21/P10-D23 确定性闭合后封存，这条既有语义不变。跨进程
连续性只由耐久身份承担：

- **flush 重放跨进程可答。** `performance.record.flush` 在无进程内会话时，
  不再直接以 owner mismatch 拒绝：若该 `(session_id, command_id)` 能在活跃
  journal 或 Project Truth 的 `performance_flush_identities` 中解析为已完成
  flush，返回原 receipt 与 `replayed: true`，Project 不变；身份不匹配返回
  既有 collision 错误；解析不到才返回 owner mismatch。
- **event/launch receipts 仍是会话生命周期状态**，跨进程重放 raw event 不受
  支持（其重放窗口 = 会话存续期），这是显式决定而非遗漏。
- 既有的 exact `record.begin` 重放 re-attach 路径（journal 存活且
  begin_command_id/session/performance 三元组精确匹配）保持不变，作为
  SIGKILL 后同身份恢复的通道。

### HRS-D5：`performance.recovery.list` 是纯 query

`performance.recovery.list` 与 `performance.record.status` 一律只读：列举
`recovery/sealed/` 候选并如实报告活跃 journal，不再调用会封存活跃 journal 的
reconcile 路径。孤儿活跃 journal（owner 已死、未封存）的封存归属 command
边界：`performance.recovery.apply` / `performance.recovery.discard` /
`performance.record.begin` 在遇到不可 re-attach 的孤儿 journal 时先按
`owner_lost` 完成封存再继续各自语义。这与 Sequence 的 list 只读先例对齐，
并消除观察者进程封掉活跃会话的跨进程危害。

### HRS-D6：C API 组合 headless bridge，零新符号

`lmdj_engine_create` 默认组合 headless 权威与可用的 replay controller
（reference controller + headless progression sink）。C ABI 保持恰好五个
符号；config JSON 保持恰好 `workspace_root` [+ `assembly_path`] 两键，不新增
Host 可见旋钮。MCP 经既有五符号继承完整可驱动的 Performance 表面；MCP 的
23 个 tool 注册仍归 Task 6（#432）。

### HRS-D7：Replay progression 由 service 泵驱动，`status` 保持只读

headless bridge 的 replay progression 沿用 web runtime 的 request-driven 泵
先例：Host/C API 在每次请求分发前调用 bridge 的 service 泵，泵按 transport
时钟推进（`advance_to(elapsed_tick)`）并 drain launch outcomes。cursor 位置
是流逝时间的函数而非调用次数的函数，因此查询频率不改变声音或 cursor（RLC
拒绝项 8.3 的关切不适用）；`performance.replay.status` 与
`performance.record.status` 自身仍不推进任何状态。时间源可注入时整条链确定。

### HRS-D8：CLI 增加持久 session 模式，一次性模式不变

`lmdj-core --workspace W [--assembly A] session` 是第三种 mode：进程持有一个
`Application`，从 stdin 逐行读严格 NDJSON 请求
`{"surface": "command"|"query", "request": {…}}`，每行恰好写出一行既有
response envelope；超长行、非 UTF-8、非对象、缺键或多键 fail closed 且不
终止会话进程；stdin EOF 触发与今日析构完全相同的 owner teardown（开放会话
`owner_lost` 封存）。既有 `command`/`query` 一次性调用的行为与退出码不变；
usage 行仅把模式集合扩为 `(command|query|session)`。session 模式退出码：EOF
干净退出为 0，I/O 失败为 2。

### HRS-D9：Native adapter 移植 #376 谓词并拥有 frame→tick 换算

Native Host 建立 pattern publication 路径（`publish_pattern_view` +
`PatternReplacementAuthority`），acknowledger adapter 在控制线程轮询
`pattern_telemetry().current_generation == 保留 generation` 且
`telemetry().rendered_frames >= activation_frame` 的谓词，配 exactly-once
notified 闩（`Application::drain_performance_launches` 对每个 `applied`
outcome 耐久写一次 journal，重复 outcome 即双写）。frame→tick 换算由 adapter
拥有，按 SR-D25 整数有理锚点；`RealtimeEngine` 的双线程契约不变，render
线程不获得任何新入口。构造顺序修复：engine 先于 `Application` 构造或经
共享间接层安装 adapter，二选一由实现计划锁定，Host 不得为绕过顺序引入
第二份时间或 slot 真相。publication 失败、取消、被替换不产生 `applied`
outcome，无 ghost event（P10-D22 不变）。

## 3. Error and non-destructive rules

- 权威缺席保持既有 typed refusal：`performance_authority_unavailable`、
  `performance_launch_authority_unavailable`、
  `performance_input_authority_unavailable`、
  `performance_replay_runtime_unavailable`；不改错误形状。
- 跨进程 flush 解析失败（无 journal 记录、无 Project Truth 身份）返回既有
  owner mismatch `INVALID_ARGUMENT`；同 command_id 不同 payload 返回既有
  collision 错误；两者都不改 Project。
- session 模式的 framing 违规逐行返回 `INVALID_ARGUMENT` envelope，进程与
  已有会话状态不受影响；不可恢复的 stdout 失败按既有 write 失败路径退出 2。
- recovery.list/status 只读化后，任何 query 都不得改变 `recovery/active/`、
  `recovery/sealed/` 或 Project 字节。
- transport/adapter 的 outcome 必须 exactly-once；drain 后 journal append
  失败沿用既有全量回滚语义。

## 4. Task decomposition

### Task 1（#523，独立 Issue / Commit / PR）

Core Performance runtime bridge 与跨进程会话身份：三权威产品实现与锁定
注释、HRS-D3 锚点通知、HRS-D2 headless transport、HRS-D7 service 泵与
headless replay sink、HRS-D4 flush 跨进程可答、HRS-D5 recovery.list 只读化、
HRS-D6 C API 组合。

### Task 2（#524，独立 Issue / Commit / PR）

HRS-D8 CLI session 模式；CLI 进程内完整 headless journey 与跨进程
flush-replay / owner-loss recovery 旅程测试。

### Task 3（#525，独立 Issue / Commit / PR）

HRS-D9 Native Host adapter：pattern publication 路径、acknowledger/clock/
replay sink、构造顺序修复、`--no-device` 确定性黑盒覆盖。

### Revised Task 6（#432）

三个 prerequisite 合并后恢复：MCP 注册 23 个 tool、三 Host schema 集合等价
门、跨 Host journey 与 `cross_host_performance_idempotency_test.py`。#432 不再
承担任何 runtime/session 基础设施。

## 5. Version Management

Version impact: no new allocation.

本修复发生在 Stage 10 Task 10 启用版本集成之前，全部由既锁定目标支付：

- application-facade 仍由既定 `3.0.0` 支付（新公共 bridge header 与接口注释、
  锚点通知方法）；
- project-io 仍由既定 `2.0.0` 支付（recovery reconcile 边界移动）;
- core-cli 仍由既定 `3.0.0` 支付（session 模式）；
- native-host 仍由既定 `3.0.0` 支付（adapter 与构造顺序）；
- C ABI 保持 `lmdj_core_c@1` 五符号不变；
- Product Build 仍由既定 Stage 10 target `1.0.41.0` 支付。

若 Task 10 开工前 fresh allocation audit 发现任一身份已被占用，仍按 Stage 10
主计划停止并刷新，不在本修复中静默改号。

## 6. Documentation Impact

Documentation impact: none for the three prerequisite Tasks.

理由：它们修正尚未由 active Assembly 启用的 Facade/Host 实现边界，不改
active manifest、Product Build 或 Portal current truth。Stage 10 Task 10 仍
负责所有受影响 Portal routes 与 source diagrams，Task 11 负责 immutable
snapshot。

## 7. Acceptance

书面修复通过须满足：

1. 三个权威接口带锁定契约注释，产品实现全部是 Core 代码，四个 Host 构造点
   无一实现时间/顺序/合并/slot/replay 语义；
2. headless transport 的 ack 只在实际跨界发生，effective tick 恰为
   `target_tick`，latest-wins 与 no-ghost-event 有 witness；
3. 新进程对已完成 flush 身份得 `replayed: true` 且 `project.inspect` 字节
   一致；raw event 跨进程重放明确不支持且有 fail-closed witness；
4. 一切 query（含 recovery.list、record.status、replay.status）零磁盘变更；
5. CLI session 模式完成完整 headless journey；一次性模式行为逐字节不变；
6. Native adapter 在 `--no-device` 下有确定性 launch-ack 与 replay 黑盒
   witness，render 线程零新入口；
7. full Core、coverage 与 Architecture Portal checks 通过且不降低 floor。

## 8. Rejected alternatives

### 8.1 Host 提供 tick、frame 或 input sequence

拒绝。P10-D21/#488 §90/§103 已锁定 Core admission 是唯一时间与顺序权威；
本修复把权威实现补成 Core 交付物，而不是把权威让给 Host。

### 8.2 把 #432 收缩成「只注册 23 个名字」

拒绝。P10-D13 要求无 UI 的 Host 完整驱动录制、回放与 Resample commit；
只注册名字让 schema 门通过而 journey 造假或缺失，违背已批准决策。

### 8.3 单路径会话连续性（只有 daemon 或只有 Journal 恢复）

拒绝。只有 daemon 则任何进程退出都丢失跨进程幂等，Task 6 的跨进程重放
不可测；只有 Journal 恢复则活跃 admission 状态（开放手势、receipts）需要
全量持久化，把 P10-D21 的进程内 admission 语义改写为分布式状态机，超出
Stage 10 范围且无产品需求。

### 8.4 跨进程 rehydrate 开放手势与 event receipts

拒绝。开放手势的确定性闭合语义（P10-D21/P10-D23）已把 owner loss 定义为
闭合边界；rehydrate 会制造两个进程同时认为自己持有开放手势的二义性。

### 8.5 acknowledger 做成 render 线程回调

拒绝。`RealtimeEngine` 双线程契约明言 render 不加锁不分配不阻塞；ack 由
控制线程轮询派生是 #376 已修复并验收的机制，native adapter 移植同一谓词。

### 8.6 为 headless replay 引入第二套时钟或按调用次数推进

拒绝。按调用次数推进使查询频率改变 cursor（RLC 8.3 同款教训）；第二套
时钟违反 SR-D25 单锚点纪律。progression 是流逝时间的函数，时间源可注入。
