# LMDJ Stage 10 Replay and Lineage Contract Repair — 2026-09-01

日期：2026-09-01

状态：**已确认（2026-09-01）**——Resample Lineage 持久化进
`lmdj.project.v4`，Replay 通过 Facade 注入的 Core controller 消费固定 revision
的不可变 projection。本文把实现前仍缺失的数据形状、身份、并发和失败语义锁定
为可执行 Contract；先交付 prerequisite #516，再恢复 Stage 10 Task 5（#431）。

关联权威：

- [`2026-08-28-lmdj-stage10-perform-design.md`](2026-08-28-lmdj-stage10-perform-design.md)
  P10-D10、P10-D11、P10-D20、P10-D25；
- [`2026-08-31-stage10-performance-contract-repair.md`](../../prd/decisions/2026-08-31-stage10-performance-contract-repair.md)
  §8；
- [`2026-08-31-lmdj-stage12-candidate-adoption-lineage-design.md`](2026-08-31-lmdj-stage12-candidate-adoption-lineage-design.md)
  S12L-D6 与 S12L-Q1。

## 1. 问题

Task 5 的开工预检发现两项无法从当前代码和批准文档唯一推导的边界：

1. P10-D11 要求派生 Asset 耐久记录源录音哈希、选区、Performance 身份和录制
   revision，但当前 `domain::Asset` 只有 `id + artifact`，Performance 没有录制
   revision，D1 `ImportAssignSampleBytesRequest` 也不接收 Lineage。Task 5 原文件
   清单只有 Project Cooker、Application Facade 与测试，无法诚实持久化 Lineage。
2. 外部 Replay request/status shape 已锁定，但 Core 内部没有 replay projection、
   progression authority 或 neutral-reset acknowledgement。若在 Task 5 内临时发明
   Facade 本地计时器、让 `status` 推进回放或把 Project path 交给 Runtime，会
   产生不同 Host 不同结果或第二份 Project truth。

同一预检还确认：`performance.resample.commit` 的锁定 request 没有
`asset_id`，因此派生 Asset 身份必须由 Core 确定性生成，不能新增 Host 字段。

## 2. 结论

### RLC-D1：Lineage 属于 Project Asset truth

`lmdj.project.v4` 的每个 Asset 增加必填 `lineage` 属性。普通导入、Capture 和
迁移得到的 Asset 写 `null`；派生 Asset 写一个封闭 typed Lineage 对象。Lineage
不放 Workspace sidecar、不只放 command receipt，也不只在 Facade response 中
瞬时返回。

原因：Project bundle 必须可移植地回答「这个声音从哪里来」；response-only 或
Workspace-only 记录会在重开、导出或跨 Host 后丢失，不能满足 P10-D11 的
“Derived Asset records Lineage”。

### RLC-D2：首个 Lineage variant 精确对齐 Stage 12 超集

Stage 10 首个可写 variant 的 JSON 形状固定为：

```json
{
  "source": {
    "kind": "asset_artifact",
    "artifact_sha256": "<64 lowercase hex>",
    "project_revision": 42
  },
  "derivation": {
    "kind": "resample",
    "range": {
      "start_frame": 4800,
      "end_frame": 9600
    },
    "performance_id": "<lowercase canonical uuid>"
  }
}
```

对象和所有子对象使用 exact keys，禁止自由文本 kind、挂钟时间、Host path、
原始音频 bytes、display name 或重复 Artifact metadata。`source.asset_id` 是
S12L-D6 允许的可选字段，但 Resample 源是 Performance 直接引用的录音
Artifact、不是 Project Asset，因此本 variant 不写 `asset_id`。

`range` 是 `[start_frame, end_frame)` 半开区间，单位是源录音的 48 kHz stereo
frame；必须满足 `start_frame < end_frame <= source_frames`。Lineage 保存用户
选择的源范围，不保存经过 Cooker preparation 后的 frame 数。

后续 Stage 12 能在同一个 `Asset.lineage` Contract 上增加其他封闭 source /
derivation variants；不得另建第二套 Lineage 模型。

### RLC-D3：Performance 记录 begin-time revision

`lmdj.project.v4` 的 Performance 增加必填无符号整数
`recording_revision`。`performance.record.begin` 输入 `expected_revision = N` 时：

- 新 draft 的 `recording_revision = N`；
- begin 仍以一次 Project mutation 提交 draft 和 receipt，产生 revision `N + 1`；
- 后续 flush、rebase、save、rename、bind 不改 `recording_revision`；
- v3→v4 迁移仍产生空 `performances`，因此无需为历史对象猜 revision。

Resample Lineage 的 `source.project_revision` 必须等于所选 Performance 的
`recording_revision`。它不是 resample commit revision、save revision、最后一次
flush revision或当前 replay resolved revision。

### RLC-D4：Resample AssetId 从 command identity 确定性派生

`performance.resample.commit` 保持已锁定的 exact request：

```text
project_path, command_id, expected_revision, performance_id,
source_start_frame, source_end_frame, target_slot
```

Core 把 `command_id` 的 UUID 值转换为新 `AssetId`。CommandId 与 AssetId 是独立
类型命名空间，但共享同一个稳定 lowercase canonical UUID 值。Host 不供应第二个
身份，也不接收随机生成的 AssetId。

因此：

- 同 command ID、同 payload 精确重试命中原 receipt 和原 Asset；
- 同 command ID、不同 Performance/range/target 是 collision；
- 已存在同 AssetId 但没有匹配 receipt 时 fail closed；
- success response 仍是既有 `SampleMutationResult` 加 `performance_id`，不新增
  `asset_id` 字段。

### RLC-D5：Resample 只复用 D1 原子 commit

Facade 从 Project Store 加载所选 Performance，要求它已有非空、经管理存储
重新验证的 `audio/wav` recording Artifact。Project Cooker：

1. 解码该 WAV 并验证 PCM16、48 kHz、stereo；
2. 验证半开 frame range；
3. 只复制选区并编码为合法 PCM16 48 kHz stereo WAV；
4. 把 bytes、Core 派生 AssetId、target Pad 和完整 Lineage 交给扩展后的 D1
   `ImportAssignSampleBytesRequest`。

Project Store 在同一个 writer lease 和同一个 command receipt 下原子安装 Artifact、
Asset、Lineage 与 Pad assignment，并沿用现有 Bank/generation quota 判定、staging、
fault recovery 与 `BANK_QUOTA_EXHAUSTED` 错误。禁止先写 Lineage 后写 Asset，禁止
先覆盖 Pad 再补 receipt，禁止新 Job/Attempt 类别，也禁止离线重渲染 FX。

取消语义保持原子命令边界：Host 可在发出 commit 前取消选择，此时 Core 无调用、
无状态变化；commit 一旦被 Facade 接受，只返回完整成功或无副作用失败，不暴露
中途取消接口。测试中的 cancel witness 验证“未调用 commit”以及 Project、Asset、
Pad、revision 均不变。

### RLC-D6：Project Cooker 产出不可变 replay projection

Project Cooker 增加 `PerformanceReplayProjection`。它在 replay begin 读取一次
当前 Project revision `R` 并完成所有解析，然后以 `shared_ptr<const ...>` 交给
controller。Projection 包含：

- `performance_id`、`resolved_revision = R`、当前 Project transport settings；
- canonical Performance events；
- 64 个 Pad 在 R 上解析得到的 immutable prepared playback/material；
- 16 个 Pattern slot 在 R 上解析得到的 immutable Pattern projection；空槽为
  显式 `null` gap；
- event count 与稳定 cursor boundaries。

Projection 不包含 `project_path`、mutable Project、Project Store、Journal、Host
callback 或恢复 fingerprint。Begin 完成后修改 Pad、移动/清空 Pattern 槽、删除
Performance 或推进 Project revision，都不改变已交付 projection；新 replay begin
重新读取最新 current Project。

Projection 中的 prepared playback/material 是 Runtime **实际渲染的材料**，不是只供
调度辨识的元数据。Replay Pad 与 Pattern Voice 必须读取 projection 固定的 PCM；
begin 后重新加载 live sample bank、替换 Pad、重新 cook 或发布新的 Runtime Snapshot，
都不得改变已排队或仍在发声（包括 release tail）的 replay。Controller、runtime sink
与 adapter 必须让 projection 的材料 owner 至少存活到对应排队事件和所有派生 Voice
完全 quiescent；禁止在 render 时按 AssetId、Pad slot 或当前 sample bank 延迟解析。

### RLC-D7：Facade 注入单一 Core Replay controller

Application Facade configuration 增加一个必填 `PerformanceReplayController`。
它只接收不可变 projection 与 stable replay identity，并提供三个 Core 内部动作：

```text
begin(replay_id, immutable_projection) -> ReplayRuntimeStatus
status(replay_id)                      -> ReplayRuntimeStatus
stop(replay_id)                        -> ReplayRuntimeStatus
```

`ReplayRuntimeStatus` 只包含锁定的 `state`、`event_cursor`、`event_count` 和
`resolved_revision`；Facade 负责包上 `replay_id`，stop 再包上 `request_id` 与
`replayed`。`status` 只观察，绝不推进时间或应用事件。

Controller 是 Core progression authority：它使用现有整数 transport tick，在每个
事件 boundary 应用 Pad、Pattern、FX 与 HOLD；同 tick 使用已锁定 canonical event
order。Pattern gap 静默推进 cursor，不改变当前 Pattern。所有 Runtime apply 成功
后才推进 cursor。

Task 5 提供可测试的 reference controller 和注入边界；后续 Host/Runtime Tasks
只能连接这条边界，不能重做 resolution、排序、cursor 或 neutral reset。

### RLC-D8：Replay lifecycle、并发与幂等

一个 Application Facade 实例同时最多一个 `playing` replay。Replay 是只读
Runtime action、不取 writer lease，Core 没有跨进程共享状态可实施 per-bundle
排他，因此排他边界是 Facade 实例而不是 Project bundle；跨进程并发 replay 不在
本 Contract 承诺范围，测试只须证明实例内排他。

已有 playing replay 时，不同 `replay_id` 的 begin 返回 `INVALID_ARGUMENT`，
`details` 锁定为 exact shape：

```json
{ "active_replay_id": "<lowercase canonical uuid>" }
```

使 Host 能把「replay 占用中」与请求畸形区分开。同 replay ID、同
`project_path + performance_id` 是 retry 并返回当前 status；同 ID、不同 payload
是 collision。

状态机固定为：

```text
begin -> playing
playing + last event applied -> complete
playing + explicit stop      -> stopped
complete/stopped + same begin identity -> return terminal status, no restart
```

若 begin 前 Performance 不存在、Project 无效或 projection 失败，不创建 replay
identity。Begin 成功后 Performance 被删除不影响已开始 replay。

Stop 的 `request_id` 独立幂等：同 request ID 重试返回原 terminal status 和
`replayed: true`；不同 request ID 对已经 stopped/complete 的 replay 返回当前
terminal status、`replayed: false`，但不重复 reset。相同 request ID 不能跨
replay ID 复用。

### RLC-D9：neutral reset 是 terminal acknowledgement 的前置条件

自然结束、显式 stop 和 Runtime apply failure 都必须无条件把八个 FX 与全局 HOLD
恢复 neutral。Controller 只有在 Runtime 确认 reset 完成后才能发布
`complete`/`stopped` terminal status；不得谎报 terminal，也不得由 Host 补
reset。

Runtime sink 的 reset acknowledgement 是三态而不是「入队即完成」：

```text
reset_neutral() -> Result<NeutralResetProgress>
NeutralResetProgress = pending | complete
```

`pending` 表示同一逻辑 reset 已被 Runtime 接受、但尚未由实际运行路径
消费完毕；它不是 reset 失败，也不得重复入队。`complete` 才允许发布
terminal status。`foundation::Result` 的 failure 仅表示真实 Runtime 错误。
自然结束的 progression/service 可以轮询已接受 reset 的 `pending -> complete`
进度，但不得在 failure 后自动重发 reset mutation；真实失败仍只由
`performance.replay.stop` 请求按下述规则重试。`status` 在两种情况下都
保持只读。

Reset 失败时的协议精确固定为：

- 第一个触发 reset 的结束路径决定目标 terminal 状态（natural end →
  `complete`，显式 stop 或 Runtime apply failure → `stopped`），此后不再改变；
- replay 进入 reset-pending：cursor 冻结、不再应用事件，controller 保留该
  replay 的独占执行权；
- `status` 保持只读、不触发 reset 重试，且仍返回锁定的固定字段——`state` 为
  `playing`，`event_cursor` 为冻结值——不新增 error 字段（P10-D25 固定返回）；
- 每个 `performance.replay.stop` 请求（含同 `request_id` 重试）触发一次 reset
  重试；重试失败时该 stop 返回同一稳定 Runtime 错误，不产生 terminal
  acknowledgement，也不消费该 `request_id` 的幂等身份；
- stop 轮询到 `pending` 时返回当前 `playing` status，不写
  `replay_stop_receipts`、不消费 `request_id`；同 request ID 的下次调用仍
  必须进入 controller 轮询，直到 terminal 后才写 receipt。因此 terminal
  前每次返回都是 `replayed:false`，terminal 那次仍是 `false`，只有再次
  重放已写 receipt 才是 `true`；
- 重试成功后 controller 发布既定目标 terminal 状态，本次 stop 返回该 terminal
  status，其后 status/stop 按 RLC-D8 的幂等规则。

空 event stream 也是自然结束，不是 begin 失败。Begin 必须建立 replay
identity 并尝试同一 neutral reset；若 Runtime 返回 `pending`，begin 返回
`playing` 且保留独占权，后续 progression/service 只轮询该 reset 直到
`complete`。若 Runtime 返回 failure，返回稳定错误但仍保留 identity、
reset target 与独占权，不得回滚成「从未 begin」。

Progression 仍由 Core controller 拥有，Host 不新增异步错误字段或第二条
error channel。Bridge/adapter 的 `service()` 保持 `void`；`advance_to` 的 apply/reset
failure 必须留下 controller-owned reset target、冻结 cursor 与活跃 identity，
service 不得因为该 failure 清理 active latch 或继续施加事件。外部可见
恢复面仍是已锁定的只读 `status` 与 `stop` reset retry；Host 不得
为了暴露异步错误而改 response shape 或终止进程。

Imported/recovered event stream 即使以开放 FX 或 HOLD 结束，也执行同一 reset。
Reset 不写 Project、不写 Performance event、不消费 revision。

## 3. Error and non-destructive rules

- malformed UUID、额外/缺失字段、非法 range、无录音 Artifact、非 WAV、digest/
  length 不匹配：`INVALID_ARGUMENT` 或现有精确 Artifact 错误，Project 不变；
- missing Performance：`NOT_FOUND`，不创建 replay/resample identity；
- Bank quota：沿用 `BANK_QUOTA_EXHAUSTED` 及既有 detail shape；
- generation quota：沿用既有 Project/generation quota error；
- Project revision mismatch：沿用 `REVISION_CONFLICT`；
- replay Runtime apply/reset failure：按 RLC-D9 的 reset-pending 协议——
  `status` 仍返回固定字段（`state: playing`、cursor 冻结），`stop` 触发 reset
  重试并在失败时返回同一稳定 Runtime 错误，不改 Project；
- 任一失败不得留下新 Asset、orphan Artifact、Lineage-only record、被覆盖 Pad、
  新 revision 或假的 replay cursor。

## 4. Task decomposition

### Contract prerequisite（独立 Issue / Commit / PR）

在恢复 #431 前，先交付：

- Project v4 `Asset.lineage` 与 `Performance.recording_revision` schema/domain/
  migration/serialization；
- Project Store begin-time revision 写入；
- D1 `ImportAssignSampleBytesRequest` 的 optional typed Lineage、transaction codec、
  receipt fingerprint、fault matrix 与 exact replay/collision；
- Stage 12 S12L-Q1 回填为“Project Asset truth”。

此 Task 不实现 replay、不实现 resample operation、不修改 active manifests 或
Product Build。

### Revised Task 5（#431）

Contract prerequisite 合并后，Task 5 交付：

- Project Cooker selection WAV 与 immutable replay projection；
- Facade controller boundary/reference controller；
- exact replay begin/stop/status 和 resample commit；
- replay resolution/lifecycle、Lineage、D1 quota/idempotency/fault tests。

## 5. Version Management

Version impact: no new allocation.

本修复发生在 Stage 10 Task 10 启用 v4 writer 与发布模块版本之前：

- `lmdj.project.v4` 仍由既定 `4.0.0` 支付；
- authoring-domain 仍由既定 `2.0.0` 支付；
- project-io 仍由既定 `2.0.0` 支付；
- project-cooker 仍由既定 `1.1.0` 支付；
- application-facade 仍由既定 `3.0.0` 支付；
- Product Build 仍由既定 Stage 10 target `1.0.41.0` 支付。

若 Task 10 开工前 fresh allocation audit 发现任一身份已被占用，仍按 Stage 10 主
计划停止并刷新，不在本修复中静默改号。

## 6. Documentation Impact

Documentation impact: none for the repair and prerequisite Tasks.

理由：它们修正尚未由 active Assembly 启用的 v4/Facade 实现边界，不改 active
manifest、Product Build 或 Portal current truth。Stage 10 Task 10 仍负责所有受影响
Portal routes 与 source diagrams，Task 11 负责 immutable snapshot。

## 7. Acceptance

书面修复通过须满足：

1. 不存在占位文本、未定义 identity、未定义 range 边界或 response-only Lineage；
2. Project v4 round-trip/migration、command receipt、fault matrix 能证明 Lineage
   与 Asset/Pad/revision 同原子边界；
3. replay begin 固定 revision，status 只读，controller 独占 progression；
4. active replay 对中途 Project 变更稳定，新 replay 解析新 current truth；
5. natural end、stop、apply failure 都有 neutral-reset acknowledgement witness，
   且 reset 失败路径证明 `status` 固定字段冻结与 `stop` 重试协议；
6. resample invalid range、Artifact mismatch、cancel-before-commit、quota failure、
   command collision 均证明 far side 零变化；
7. full Core、coverage 与 Architecture Portal checks 通过且不降低 floor。

## 8. Rejected alternatives

### 8.1 Response-only or Workspace-only Lineage

拒绝。它不能随 Project bundle 重开、迁移和跨 Host，无法成为 Derived Asset 的
可移植来源事实。

### 8.2 新增 `asset_id` Host request 字段

拒绝。锁定 request 已足够由 command identity 确定性派生，新增字段扩大跨 Host
surface 并制造第二个 collision 维度。

### 8.3 `status` 调用推进 replay

拒绝。查询频率会改变声音与 cursor，不同 Host 会产生不同结果。

### 8.4 Runtime 持有 Project path 或每个 event 重新解析

拒绝。它破坏 begin-time fixed revision、使 Runtime 越过 Facade/Project Cooker
边界，并让中途 Project mutation 改变正在进行的 replay。

### 8.5 Resample 离线重渲染 Performance events

拒绝。P10-D11 已锁定现场 WAV 选区；离线重渲染是后续能力，且永不进入实时
引擎。
