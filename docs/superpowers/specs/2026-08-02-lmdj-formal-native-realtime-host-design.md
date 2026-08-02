# LMDJ 5B Formal Native Realtime Host Design

日期：2026-08-02

状态：实施目标已批准；产品级录音并发语义继续保持待设计评审

## 1. 目标

实现交付顺序中的 **5B Formal Native Realtime Host**：从真实 `.lmdj`
Project 经 Application Facade 准备不可变 Runtime Snapshot，把 Project 中已分配的
64 Pad Sample 发布给 5A 已验证的 Realtime Engine，通过 Apple CoreAudio 播放，
并把实际起音事件经 lock-free Capture Ring 写入可恢复 Take Journal。

5B 不再是 `tests/platform/` 下的程序化 Probe。它是产品中立、版本化、进入
Product Assembly 和分发包的正式 `apps/native-test-host` Host，同时保持
Headless：本切片不创建 Creator UI，也不把 Keyboard、Mouse、MIDI、Touch 或设备
选择器假装为已完成。

## 2. 完成后的纵向路径

```text
.lmdj Project Bundle
  → Application Facade typed prepare_runtime_snapshot
  → Project Cooker immutable RuntimeSnapshot
  → Audio Runtime PreparedSampleBank
  → callback-boundary atomic Sample Bank publication
  → single-producer Trigger Event Queue
  → Realtime Voice Pool
  → Apple CoreAudio Default Output

Audio Thread accepted starts
  → lock-free Capture Ring
  → Background Capture Writer
  → Application Facade typed append_realtime_take_events
  → Project-owned Take Journal
  → existing take.commit Authoring Command
  → new Project Revision
  → explicit Snapshot reload
```

这条路径必须同时证明以下边界：

- Host 不打开、遍历或解析 Project Bundle；
- Facade 和 Project I/O 不进入 Audio Thread；
- Trigger 不进入 Facade JSON Command；
- Audio Thread 不写文件、不分配、不释放、不加锁、不输出日志；
- Snapshot 发布失败继续播放上一份完整 Snapshot；
- Capture 不完整时禁止提交一个看似成功的 Take。

## 3. 已选范围

### 3.1 本切片交付

- `apps/native-test-host` 正式 Host target、Module Manifest 和 Assembly Host 条目；
- 真实 Project、Pattern 和 64 Pad Assignment 的 Runtime Snapshot；
- PCM16 mono/stereo 48 kHz 到 mono float32 的非实时准备；
- 运行中 Sample Bank 安全发布和退役资源控制线程回收；
- 单一 Host 输入生产路径、固定容量 Trigger Event Queue；
- Audio Thread 实际起音 Capture Ring；
- 后台批量追加可恢复 Take Journal；
- 显式 begin、stop、commit、reload、status、start、stop、quit Host 控制；
- Apple Default Output 真机播放；
- 非 Apple 和 Apple `--no-device` 确定性 Host 自动化；
- Product Build、Module version、Assembly lock 和分发包身份更新。

### 3.2 明确不在本切片

- Creator UI、Native GUI、菜单栏或托盘 UI；
- Keyboard、Mouse、MIDI、Touch、MIDI Learn 或 Controller Profile；
- Device picker、Bluetooth、aggregate device 或多输出路由；
- Pattern Transport、Loop、metronome、自动播放或 sample-accurate scheduler；
- 自动量化、swing、overdub、undo、Take 编辑或录音音频 Bounce；
- Audio Input、Immutable Audio Artifact、mic/line capture；
- Voice stealing、Pitch、Envelope、FX、Time-stretch 或 streaming；
- Web/WASM/AudioWorklet/OPFS；
- tag、GitHub Release、部署、Channel 晋级或公开发版。

Keyboard/MIDI/Pointer 的既有延期状态不因 5B 改变。Host 的 stdin 协议只是可重复的
输入 Adapter 和黑盒验证入口，不是实体输入验收替代品。

## 4. 模块与依赖边界

```text
authoring-domain
  ← project-cooker
  ← audio-runtime

project-io
  ← application-facade

application-facade + audio-runtime
  ← native-test-host

products/lmdj
  → links compiled Assembly into native-test-host
```

`native-test-host` 可以直接使用 `audio-runtime` 的实时数据面，但涉及 Project 的所有
加载、Cook、Take Journal 和 Authoring Command 只能调用 Application Facade。
Host Manifest 的直接依赖只有 `application-facade` 和 `audio-runtime`；模块图测试继续
禁止 Host 依赖 `project-io` 或读取其内部头文件。

不修改 C ABI、CLI/MCP JSON Operation、Project Contract 或任何跨语言 Contract。
新增 Facade 能力是 Monorepo 内的类型化 C++ Host API，不创建 `snapshot_id` 或进程级
Snapshot Registry。

## 5. Runtime Snapshot

### 5.1 Snapshot 内容

在现有 `RuntimeSnapshot` 中新增按 `bank,pad` 稳定排序的 `ResolvedPad`：

```cpp
struct ResolvedPad {
  domain::PadSlotId slot;
  foundation::ArtifactRef artifact;
  std::shared_ptr<const PcmSample> sample;
};

struct RuntimeSnapshot {
  foundation::ProjectId project_id;
  std::uint64_t project_revision;
  std::uint16_t bpm;
  std::uint8_t bars;
  std::vector<ResolvedPad> pads;
  std::vector<ResolvedEvent> events;
};
```

Cook 必须解析 Project 中每个已分配 Pad，而不只是当前 Pattern 已引用的 Pad。相同
Artifact hash 在一份 Snapshot 中只读取、校验和解码一次；Pad 与 Pattern Event
共享不可变 `PcmSample`。未分配 Pad 不出现在 `pads`，Realtime Bank 对应 slot 保持
empty。

完整 Snapshot 只有在以下条件全部成立时才返回：

- Project、Pattern、Pad Slot 和 Artifact metadata 合法；
- 每个已分配 Artifact bytes 的长度和 SHA-256 匹配；
- WAV 为现有已批准的 48 kHz PCM16 mono/stereo；
- Pattern Event 引用已分配 Pad；
- Pad 列表唯一且严格按全局 slot `bank * 16 + pad` 排序。

任一 Pad 失败会使新 Snapshot Prepare 整体失败；Host 保留上一已发布 Bank，不能
部分替换或清空仍可工作的 Pad。

### 5.2 类型化 Facade 准备

Application Facade 新增：

```cpp
struct RuntimeSnapshotRequest {
  std::filesystem::path project_path;
  foundation::PatternId pattern_id;
};

foundation::Result<std::shared_ptr<const cooker::RuntimeSnapshot>>
Application::prepare_runtime_snapshot(
    const RuntimeSnapshotRequest& request);
```

方法只接受 absolute、normalized Project path 和合法 Pattern ID，在调用线程加载
Project、Cook 并返回 `shared_ptr<const RuntimeSnapshot>`。它不持久化 Snapshot、
不生成公共 ID、不修改 revision，也不改变现有 `snapshot.cook` Query 的响应 Contract。

## 6. Prepared Sample Bank 与发布

### 6.1 非实时准备

`audio-runtime` 提供 move-only `PreparedSampleBank`。它在控制线程把每个
`PcmSample` 转成 48 kHz mono float32：mono 直接缩放，stereo 使用
`(left + right) * 0.5`，PCM16 `-32768` 精确映射到 `-1.0F`。输入已由 Cooker 保证
sample rate 和编码，转换仍拒绝空 Sample、非法 channel、非有限结果、重复 slot。

Bank 保存 Project ID、revision、64-bit availability mask 和最多 64 个 vector；准备
结束后只能 move 给 Engine，不能从 Host 取得可变 Sample view。

### 6.2 固定 Bank Slot

Realtime Engine 内部持有四个固定 Bank Slot。Sample vector 在控制线程 move/clear；
Audio Thread 只读取稳定地址。Bank Slot 状态为：

```text
empty → prepared → pending → current → retiring → reclaimable → empty
```

- stopped 时 publish 直接安装完整 Bank；
- running 时只有 Trigger Event Queue 已空才接受 publish；Queue 非空返回
  `events_pending`，避免不携带 Bank generation 的旧格式 Trigger 被错误地用新 Bank
  播放；Host reload 在主控制线程停止产生新 Trigger，并等待该短暂边界；
- running 时控制线程把 Bank 放入 empty Slot，并把 Slot index 写入固定 SPSC 发布队列；
- Audio Thread 在 callback frame 0 消费 pending Slot，原子切换 `current`；
- 新 Trigger 从切换后的 Bank 起音；已起音 Voice 继续引用旧 Bank；
- 每个 Voice 保存 Bank Slot index，结束时减少该 Slot 的 audio-thread voice count；
- retiring Slot 的 voice count 归零后只被标记 reclaimable；
- `reclaim_retired_banks()` 只能由控制线程清空 vector 并恢复 empty。

Audio Thread 不执行 `shared_ptr` 引用计数、不析构 vector、不 delete。四个 Slot 全部被
current/pending/旧 Voice 占用时，publish 返回 `bank_slots_full`，保留当前 Bank。
发布队列满返回 `publish_queue_full`，同样不能破坏当前 Bank。

### 6.3 兼容 5A

5A Probe 改为使用 `PreparedSampleBank::set_sample` 和 `publish_sample_bank` 准备固定
880 Hz Sample。现有 64 slots、1,024 Trigger、128 Voice、48 kHz stereo output、
无 Voice stealing 和 lifecycle 行为不回退。

## 7. Trigger 与单一生产路径

Host 主控制线程是唯一 Realtime Event Queue producer。所有当前 stdin Trigger 和
未来 Keyboard/MIDI Adapter 必须先规范化为同一个 `TriggerEvent`，再由该线程调用
`RealtimeEngine::enqueue`；未来 Adapter 不能各自直接成为 Queue producer。

Host 输入 slot 使用 `{bank,pad}`，边界转换为 `global_slot = bank * 16 + pad`。
Realtime Event 仍使用 5A 固定宽度结构：

```cpp
struct TriggerEvent {
  std::uint64_t sequence;
  std::uint8_t slot;
  std::uint8_t velocity;
};
```

事件在当前 callback frame 0 起音。5B 不加入 callback-relative frame offset；Capture
记录的是实际 dequeue/voice-start 所在的 Runtime frame，而不是 stdin 到达时间。

## 8. Capture Ring 与后台 Writer

### 8.1 Capture 状态

Engine 新增固定 4,096-event Capture Ring，producer 是 Audio Thread，consumer 是
唯一 Background Writer。Capture Event 为 trivially copyable：

```cpp
struct CapturedTriggerEvent {
  std::uint64_t sequence;
  std::uint8_t slot;
  std::uint8_t velocity;
  std::uint32_t frame_offset;
};
```

`arm_capture` 只发布 `arm_pending`；Audio Thread 在下一个 callback 边界保存
`capture_origin_frame` 并进入 `active`。`disarm_capture` 发布 `disarm_pending`；Audio
Thread 完成当前 callback 后进入 `idle`。Host 只有观察到 `active` 才接受录制中的
Trigger，只有观察到 `idle` 且 Ring 已 drain 才允许 commit。

只有成功占用 Voice 的 Trigger 才写 Capture Ring。`sample_unavailable`、queue drop
和 voice drop 不伪装成已录制起音。

### 8.2 frame offset 与溢出

`frame_offset` 等于 Voice 实际开始的 Runtime frame 减去 capture origin。超过
`uint32_t`、Capture Ring full 或 Writer 持久化失败都会把当前 Capture 标记
`corrupted`：

- 播放可以继续；
- telemetry 明确增加 drop/failure；
- Host 停止录制并等待 callback quiescence；
- 活跃 Journal 以 `capture_incomplete` 封存为 Recovery Candidate；
- `record.commit` 必须拒绝，不能生成不完整 RawTake/Pattern。

### 8.3 Background Writer

后台线程每次最多 drain 64 个事件，转换为：

```cpp
domain::RawTakeEvent{
  .slot = {captured.slot / 16, captured.slot % 16},
  .frame_offset = captured.frame_offset,
  .velocity = captured.velocity,
};
```

然后通过类型化 Facade API 批量追加：

```cpp
foundation::Result<void> Application::append_realtime_take_events(
    const std::filesystem::path& project_path,
    foundation::TakeId take_id,
    std::span<const domain::RawTakeEvent> events);

foundation::Result<std::filesystem::path>
Application::seal_realtime_take(
    const std::filesystem::path& project_path,
    foundation::TakeId take_id,
    std::string_view reason);
```

Facade 调用新增的 `TakeJournal::append_batch`，一次 open/repair/write/fsync/close 追加
一批 canonical JSONL。空 batch 拒绝；任何 event 非法则整批在写入前拒绝；一次 syscall
部分写由既有 `write_all` 收敛，进程崩溃留下的未终止尾行仍由既有 repair 规则恢复。

`seal_realtime_take` 只接受固定 reason `capture_incomplete`，供 Host 在 Ring overflow、
frame offset overflow 或 Writer failure 后把活动 Journal 转为 Recovery Candidate。它不
成为新的 JSON/C ABI Operation，也不能被用于覆盖 revision conflict 的既有封存原因。

Host 用非 Audio Thread mutex 串行化同一 `Application` 的 Snapshot prepare、Capture
batch append 和控制 Command；该 mutex 永远不被 Realtime Engine 或 CoreAudio
callback 触碰。

## 9. 录音并发边界

5B 是正式内核 Host，但不是 Creator 用户录音产品。因此本切片明确复用 Headless
Core Proof 的严格规则：

- `record.begin` 锁定 `expected_revision`；
- Capture 期间任何 Project revision 变化都会让现有 `take.commit` 返回
  `REVISION_CONFLICT` 并封存 Take；
- 5B 不实现 selective rebase，不分类“无关 Command”，不修改 Sequence/Take
  Contract；
- Host 不自动量化 Captured Event。`record.commit` 必须接收调用者显式提供、符合现有
  `take.commit` 形状的 Pattern。

`docs/prd/open-questions.md` 中“产品级录音并发语义”继续保持待设计评审。未来 Creator
Take 或 Sequence 用户流程进入实现前，必须单独决定 dependency fingerprint、无关
Command 和 rebase 规则，不能把本 Host 的严格诊断行为当作产品答案。

## 10. Formal Host 接口

### 10.1 启动

正式 binary：`lmdj-native-host`。

```text
usage: lmdj-native-host \
  --workspace ABSOLUTE_PATH \
  --assembly ABSOLUTE_ASSEMBLY_JSON \
  --project ABSOLUTE_PROJECT_BUNDLE \
  --pattern UUID \
  [--no-device]
```

启动顺序固定为：验证参数 → 验证已安装 Assembly → 构造 Application → Prepare
Snapshot → Prepare/Publish Bank → Engine start → CoreAudio start（或 deterministic
no-device driver）→ 输出一行 `ready` JSON。

默认模式只在 Apple 启动真实 CoreAudio。非 Apple binary 仍构建、进入包并支持
`--no-device` 自动化；未带 `--no-device` 时返回 `UNSUPPORTED_AUDIO` 和 exit 2，不能
提供假成功 backend。

### 10.2 stdin JSONL

每行是一个最大 64 KiB、深度最多 32 的 UTF-8 JSON object。Host 固定支持：

- `trigger`：`slot:{bank,pad}`、`velocity`；进入唯一 Event producer；
- `snapshot.reload`：`pattern_id`；Prepare 完整新 Bank 后 publish；失败保留旧 Bank；
- `record.begin`：`take_id`、`expected_revision`；先 Facade `take.begin`，再启动 Writer
  和 arm Capture；
- `record.stop`：disarm、等待 idle、drain/join Writer；返回 captured/persisted count；
- `record.commit`：`command_id`、`expected_revision`、`pattern`；只在完整 stop 后调用
  现有 `take.commit`；
- `status`：输出 Host、Snapshot、Bank、Engine、CoreAudio 和 Capture telemetry；
- `stop`：先安全结束/封存活动 Capture，再停 CoreAudio 和 Engine；
- `start`：复用当前 Bank 重启 Engine/CoreAudio；
- `quit`：执行安全 stop 后 exit 0。

未知 operation、额外 key、非法范围或过大行返回稳定错误 JSON，进程继续。EOF 等同
`quit`。stdout 只由主控制线程写；stderr 只用于 invocation usage。callback 和 Writer
都不直接写输出。

`--no-device` 中每个 accepted trigger 由同一 Engine 以固定 128-frame block 驱动，
直到当前 one-shot 完成，所以黑盒测试可断言 status 与 Capture。它不证明 CoreAudio
设备或物理延时。

## 11. 状态与失败恢复

Host status 至少包含：

- Product Build、Host version、platform backend 和 Host lifecycle state；
- Snapshot Project ID、revision、Pattern ID、resolved/available pad count；
- current/pending/retiring Bank generation 和 publish failure counts；
- 5A Engine/CoreAudio telemetry；
- Capture state、captured、persisted、ring drops、writer failures；
- active Take ID（无活动 Take 时为 null）。

Snapshot reload、publish 或 Writer 失败不能崩溃或进入 callback 日志路径。控制线程以
现有 `foundation::ErrorCode` 映射错误。若 CoreAudio cleanup 不能证明 callback 退出，
继续沿用 5A terminal `failed` 与 `_Exit(2)` 规则，不能释放可能仍被 callback 访问的
Engine/Bank/Capture 存储。

## 12. 测试与门槛

### 12.1 Project Cooker / Facade

- 64 Pad 唯一稳定顺序、共享 decode、mono/stereo 和 empty slot；
- 任一已分配 Artifact 缺失、hash 错误或 unsupported audio 整体失败；
- typed prepare 不持久化、不改 revision、不创建 snapshot ID；
- batch append 一次持久化多事件，非法 batch 原子拒绝，crash tail 可恢复；
- JSON CLI/MCP/C ABI 公开 Operation 与响应形状不变。

### 12.2 Audio Runtime

- mono/stereo PCM16 精确转换和 64-bit availability；
- stopped publish、running callback-boundary publish、失败保留旧 Bank；
- 旧 Voice 跨 Bank swap 自然结束，新 Trigger 使用新 Bank；
- 四 Slot backpressure 和 control-thread reclaim；
- render 路径零 allocation/deallocation/lock；
- Capture arm/disarm 边界、实际 voice-start offset、4,096 capacity、overflow corruption；
- Trigger Queue、Publish Queue、Capture Ring SPSC stress；
- ASan 和 TSan full/stress 分别通过。

### 12.3 Host / Assembly / Distribution

- `--no-device` 启动真实 fixture Project，trigger、reload、record、commit、restart；
- failed reload 保持旧 Sample 可播放；
- Capture overflow/writer failure 封存 recovery，commit 被拒绝；
- Host source/link graph 不含 `project-io`；
- Assembly source、compiled catalog、lock 和 `module.json` 精确一致；
- macOS/Ubuntu package 包含 `lmdj-native-host`，非 Apple device mode 明确失败；
- `scripts/core.sh proof` 继续排除 stress 并通过。

### 12.4 Apple 物理 Gate

在当前 Mac 默认内置或有线输出使用真实 fixture Project：

1. 启动 Host，确认 ready 的 Project revision/pad count；
2. 触发至少 20 次两个不同 Pad，每次只听到对应 one-shot；
3. 运行中 reload 到替换 Sample 的新 Project revision，新 Trigger 使用新 Sample，旧
   Voice 不被截断；
4. record begin 后触发 20+1 次，stop/commit 成功，重新查询 Project 能看到 RawTake
   与 Pattern；
5. stop 后 Trigger 明确拒绝，start 后恢复且没有旧事件重放；
6. status 中 queue/voice/capture/publish drop、CoreAudio overload/failure 均为 0；
7. quit 正常退出。

物理 Gate 证明当前 Mac 的 Project→Snapshot→CoreAudio→Capture 闭环；它不证明
Keyboard/MIDI/Pointer 延时或 Beta/Stable 发行质量。

## 13. Realtime 安全复核

CoreAudio render callback 与 `RealtimeEngine::render` 禁止：

- heap allocation/deallocation、`shared_ptr` retain/release 或 vector mutation；
- mutex、condition variable、sleep 或可能阻塞的系统调用；
- filesystem、Project Store、Take Journal、Provider 或 network；
- JSON、exception、locale、iostream、stdout/stderr 或 logging；
- Application Facade 方法；
- Sample conversion、Bank reclamation 或 journal append。

测试 allocation counter 只覆盖实际 render 路径；code review 还必须检查析构、错误
分支、Bank swap、Voice completion 和 Capture overflow 分支。

## 14. Version Management

Canonical policy：`docs/governance/version-management.md`。

| Domain | Current | Target | Reason |
| --- | --- | --- | --- |
| Product Build | `1.0.10.0` | `1.0.11.0` | 新增 Assembly-listed Formal Host，并改变 Cooker、I/O、Facade 和 Audio Runtime 集成能力。 |
| `project-cooker` | `0.1.0`, API 1 | `0.2.0`, API 1 | 向后兼容扩展 Runtime Snapshot，使其包含全部 resolved Pad。 |
| `audio-runtime` | `0.2.0`, API 1 | `0.3.0`, API 1 | 新增 Bank prepare/publication/reclaim 与 Capture Ring；保留 5A Engine 行为。 |
| `project-io` | `0.2.0`, API 1 | `0.3.0`, API 1 | 新增向后兼容、批量持久化 Take Journal API。 |
| `application-facade` | `1.0.1`, API 2 | `1.1.0`, API 2 | 新增向后兼容的 typed Snapshot 和 realtime Take batch Host API。 |
| `core-cli` | `1.0.1`, API 2 | `1.0.2`, API 2 | 精确 Facade dependency 更新；CLI 行为不变。 |
| `core-mcp` | `1.0.1`, API 2 | `1.0.2`, API 2 | 精确 Facade dependency 与 Python package identity 更新；MCP 行为不变。 |
| `native-test-host` | none | `1.0.0`, API 1 | 首个正式、版本化、Assembly-listed Headless Native Host。 |
| Contracts | unchanged | unchanged | 不改变 wire、Project persistence、C ABI、error 或 Assembly schema。 |
| Providers / Models | unchanged | unchanged | 不改变 Capability、Provider 或 Model identity。 |

`project-cooker` 和 `audio-runtime` 保持 `api_version: 1`，因为新增 API 不删除或改变
现有调用；`application-facade` 保持 `api_version: 2`，因为 C ABI/JSON facade contract
不变。Channel 保持 `canary`。

潜在未来 tags 为：

- `module/project-cooker/v0.2.0`；
- `module/audio-runtime/v0.3.0`；
- `module/project-io/v0.3.0`；
- `module/application-facade/v1.1.0`；
- `module/core-cli/v1.0.2`；
- `module/core-mcp/v1.0.2`；
- `module/native-test-host/v1.0.0`；
- signed Product tag `lmdj-v1.0.11.0`。

这些 tag 只能指向未来通过保护分支与全部 Gate 的 `main` merge commit。本设计不授权
创建或 push tag、GitHub Release、部署、发布或 Channel 晋级。

## 15. 完成定义

只有以下证据全部成立，5B 才能称为完成：

- Formal Host 真实存在于 `apps/`、Product Assembly 和分发包；
- Host 对 Project 的所有访问都经 Facade，module/link/source graph 有自动证据；
- 真实 Project 的 64 Pad Snapshot 可以安全发布，运行中失败不破坏旧 Bank；
- Trigger 和 Capture 都走固定 SPSC realtime 路径，callback 无 lock/allocation/I/O；
- 完整 Take 可后台持久化和显式 commit，不完整 Capture 只能 recovery；
- Cooker、I/O、Facade、Runtime、Host、Assembly 和 distribution 自动测试通过；
- dev、ASan full、TSan full+stress、Coverage 和 `scripts/core.sh proof` 通过；
- 当前 Mac 完成 Project playback、live reload、20+1 Capture/commit 和 restart 物理 Gate；
- Product Build/Module/Assembly identity 全部是本设计的目标版本；
- Web 和实体 Input 延期证据没有被覆盖或美化；
- 没有未经授权的 push、PR、merge、tag、Release、部署或 Channel 晋级。
