# Native Realtime CoreAudio Probe Design

日期：2026-08-02

状态：用户已批准设计方向，等待书面规格复核

## 1. 目标

交付顺序中的 Native Realtime Host 先拆成一个可独立验收的 **5A Native
Realtime CoreAudio Probe**：建立产品中立的实时播放内核和 macOS/CoreAudio
输出适配，使用启动前准备好的固定 PCM 与程序化触发，证明实时回调、无锁事件
传递、预分配 Voice、过载遥测和可重复启停。

这个切片不依赖尚未通过的 Web/PWA 物理门槛，也不把
`apps/web-runtime-lab` 的临时播放引擎带入正式运行时。它为后续 **5B Formal
Native Realtime Host** 提供已经验证的实时数据面；5B 再通过 Application Facade
取得控制面状态和不可变 Runtime Snapshot。

## 2. 已选方案

采用 **共享 Audio Runtime + Apple 原生 Audio Unit + 平台测试探针**：

- 在 `packages/audio-runtime/` 增加跨平台、产品中立的实时 Engine；
- 在同一 Module 中增加仅 Apple 构建的 CoreAudio Default Output 适配；
- 在平台测试目录提供仅 Apple 构建的命令行探针；
- 不引入 miniaudio、RtAudio、JUCE 或 Objective-C/Swift 运行层；
- 不在本切片创建正式 `apps/` Host、Host Manifest 或 Product Assembly Host
  条目。

选择直接使用 Audio Unit，是因为当前目标只有 macOS/CoreAudio 输出验证，Apple
原生 C API 可以保持依赖最小，并让 render callback、buffer format 和设备过载
证据可直接检查。跨平台驱动抽象只保留实现所需的最窄边界，不提前设计 Windows、
Linux 或移动端后端。

## 3. 架构边界

```text
Control/Test Thread
  ├─ prepare immutable PCM bank while stopped
  ├─ enqueue TriggerEvent into fixed SPSC queue
  └─ read atomic telemetry / start / stop
                    │
                    ▼
packages/audio-runtime
  ├─ fixed-capacity SPSC Event Queue
  ├─ preallocated Voice Pool
  ├─ float32 realtime mixer
  └─ atomic Telemetry Counters
                    │
                    ▼
Apple CoreAudio Default Output Audio Unit
  └─ render callback supplies non-interleaved stereo buffers
```

本切片是 Package 与平台适配验证，不是绕过 Application Facade 的产品 Host：

- 测试探针可以直接调用 Package，就像其他 Module component/platform test；
- 探针不创建、读取、保存或解析 `.lmdj` Project Bundle；
- 探针不拥有 Authoring Project、Workspace Setting 或 Provider Policy；
- 正式 Native Host 仍必须通过 Application Facade 使用控制面；
- 正式实时触发和录音不能复用逐事件 JSON Command 路径，而要使用本设计建立的
  实时队列以及未来 Capture Ring；
- 本切片不加入 `products/lmdj/assembly.json` 的 `hosts`。

## 4. Realtime Engine

### 4.1 固定格式

第一切片冻结以下内部运行格式：

- sample rate：48,000 Hz；
- output：2-channel non-interleaved float32；
- Sample Bank：64 slots，对应未来四个 4×4 Bank；
- Trigger Queue：single producer / single consumer，对外保证可接受固定 1,024 条
  （内部环形存储可为区分 full/empty 多保留一个元素）；
- Voice Pool：固定 128 voices；
- one-shot playback only；
- 每个 Sample 在 Engine stopped 时准备为 mono float32；
- render 时把 mono Sample 复制到左右声道并按 `velocity / 127.0` 缩放。

这些值是内部 Module API，不是跨语言 Contract。后续改变公开产品语义前必须单独
评审；第一切片不会决定 Voice stealing、Loop、Pitch、Envelope、FX、Time-stretch
或多输出总线。

### 4.2 触发事件

实时事件只包含播放所需的固定宽度字段：

```cpp
struct TriggerEvent {
  std::uint64_t sequence;
  std::uint8_t slot;
  std::uint8_t velocity;
};
```

有效范围为 `slot < 64`、`1 <= velocity <= 127`。生产线程在入队前验证；队列已满
时返回失败并增加 `queue_drops`。Audio Thread 在下一次 callback 开始时消费事件，
不为事件分配内存，也不调用 Application Facade。

`sequence` 是供上层关联诊断的 opaque value；Engine 保留并消费它，但不要求单调、
不排序也不去重。Probe 自己使用从 1 开始的递增值。Engine 只在 running 时接受
Trigger；无效 slot/velocity、未加载 Sample、stopped/stopping 状态和 queue full
分别返回固定枚举结果，不通过字符串或异常报告。未加载 Sample 与无效字段增加
`invalid_events`；只有 queue full 增加 `queue_drops`。

第一切片不承诺事件的 sample-accurate frame offset。所有已消费事件从当前 callback
的 frame 0 起音；带 callback 内 frame offset 的事件格式留给 Snapshot/Transport
集成设计，不能在本切片悄悄加入。

### 4.3 Sample 所有权

Control Thread 只能在 Engine stopped 时加载或清除 Sample。Engine start 成功后，
Sample Bank 的 vector 容量和数据地址保持不变，直到 stop 完成。Audio Thread
只读取稳定指针和长度；不复制、释放或引用计数 Sample。

加载 Sample 必须拒绝：

- 空 PCM；
- 超出 64 slots；
- NaN 或 infinity；
- Engine running 时的变更。

固定探针 Sample 在进程启动时生成：880 Hz、25 ms、48 kHz、peak gain 0.12 的
mono sine。它不依赖仓库二进制资产或第三方声音授权。

stop 先确保 callback 已退出，再清空 Queue 和 active Voice，并分别记入
`cancelled_events` 与 `cancelled_voices`；Sample Bank 保留，供下一次 start 复用。
成功 start 会在对外进入 running 前清空 Queue/Voice，并重置本次运行的 telemetry，
因此 stopped 期间不会积累或在重启后重放旧 Trigger。

### 4.4 Voice 行为

每个有效 Trigger 占用一个空闲 Voice，保存 Sample 指针、frame cursor 和 gain。
render 完成 Sample 最后一个 frame 后立即释放 Voice。第一切片不实现 Voice
stealing；如果 128 个 Voice 全部占用，事件被明确计为 `voice_drops`，而不是静默
覆盖旧 Voice。这个行为是 Probe 的诊断策略，不是最终产品的 stealing policy。

每次 callback 先把所有输出 buffer 清零，再累加 active Voice。最终写出值限制在
`[-1.0, 1.0]`，避免探针输出超范围 float。产品级 limiter、headroom 与混音政策
仍属于后续 DSP 设计。

## 5. Realtime 安全规则

Audio Thread 和 CoreAudio render callback 中禁止：

- mutex、condition variable 或可能阻塞的同步；
- heap allocation、deallocation 或容器扩容；
- filesystem、network、Provider 或 Project I/O；
- JSON、异常传播、locale、日志或 stdout/stderr；
- Application Facade Command/Query；
- callback 内 Sample Bank 变更。

所有 callback 可见状态必须是启动前固定的存储或 lock-free/atomic 状态。测试必须
用 allocation counter 证明覆盖的 render 路径没有调用全局 allocation。

## 6. CoreAudio 适配

Apple 实现使用 Default Output Audio Unit：

- `kAudioUnitType_Output`；
- `kAudioUnitSubType_DefaultOutput`；
- `kAudioUnitManufacturer_Apple`；
- client format 为 48 kHz、stereo、non-interleaved float32；
- render callback 直接把 AudioBufferList 的左右声道交给 Realtime Engine；
- start 顺序为 create → configure → initialize → start；
- stop 顺序为 stop → remove overload listener → uninitialize → dispose；
- 任一步失败都返回结构化错误并清理已取得的资源；只有确认 callback 不会再进入时
  才恢复到 stopped。如果 cleanup 本身失败而无法证明 callback 已终止，适配器进入
  terminal failed、保留 Engine/Sample 存储、拒绝 restart；Probe 刷新结构化错误后
  以 2 立即结束进程，不执行可能释放 callback 状态的 stack unwinding；
- stop 必须幂等；成功 stop 后允许再次 start；running 时重复 start 返回固定
  `already_running` 状态，不重置设备或 telemetry。

适配层在控制线程注册默认输出设备的 processor-overload 通知。该 listener callback
先进入与 render callback 共用的 lock-free 生命周期 gate，仅在 enabled 时用一次
relaxed atomic increment 记录 `device_overloads`，然后离开 gate 并返回；禁止分配、
锁、I/O、日志或其他工作。`AudioObjectRemovePropertyListener` 只证明取消后续通知，
不证明正在执行的 I/O-thread listener 已退出，因此成功移除 listener 和 dispose 后仍
必须最终 drain 共用 gate，才能进入 stopped、停止 Engine 或释放 callback context。
适配层同时记录 callback count、rendered frames、最大 callback frame count、callback
failures 和 deadline overruns。时间测量只能使用无分配的单调时钟；如果 callback
执行时间超过本 buffer 的音频时长，增加 `deadline_overruns`。

CoreAudio 与 Engine 控制面错误复用现有 `foundation::Result` / `foundation::Error`；
本切片不新增错误 Contract 或从 callback 传播异常。Probe 的 `status` 固定输出：

- `state`（`stopped` / `running` / `failed`）、`sample_rate`、`channels`、
  `queue_capacity`、`voice_capacity`；
- `enqueued_events`、`dequeued_events`、`queued_events`、`cancelled_events`；
- `started_voices`、`completed_voices`、`active_voices`、`cancelled_voices`；
- `invalid_events`、`stopped_rejections`、`queue_drops`、`voice_drops`；
- `callback_count`、`rendered_frames`、`max_callback_frames`；
- `device_overloads`、`callback_failures`、`deadline_overruns`。

每个累计计数在一次 successful start 后从零开始，并在该 run 内单调递增；
`queued_events` 与 `active_voices` 是可增减 gauge，`state` 是枚举。running 时的
status 是多个 atomic 的 best-effort snapshot，不承诺跨字段事务一致。停止并静止
后必须满足 `queued_events == 0`、`active_voices == 0`，以及：

```text
enqueued_events == dequeued_events + cancelled_events
dequeued_events == started_voices + voice_drops
started_voices == completed_voices + cancelled_voices
```

这些计数是运行诊断，不代替扬声器声学延时、真实 underrun 或发行设备验收。

## 7. Probe 接口

仅 Apple 构建 `lmdj-native-audio-probe`。默认启动后准备固定 Sample、打开默认输出
设备，并从 stdin 接受一行一个命令：

- `trigger`：以递增 sequence、slot 0、velocity 100 入队；
- `status`：在控制线程输出一行 privacy-bounded JSON telemetry；
- `stop`：停止并释放 Audio Unit；
- `start`：重新创建并启动 Audio Unit；
- `quit`：停止后以 0 退出。

未知命令输出结构化错误但不终止进程。EOF 等同 `quit`。启动失败或设备配置失败以
2 退出；命令用法错误以 64 退出。stdout 只由控制线程写，callback 永不输出。

探针还提供 `--no-device` 模式：使用同一 Engine 和固定 Sample，执行确定性 callback
模拟并输出 telemetry，供 macOS 自动化验证 CLI 行为。它保留同一 stdin 协议；每个
成功的 `trigger` 在返回控制循环前，以固定 128-frame blocks 驱动 Engine，直到该
one-shot 完成，因此随后的 `status` 可精确断言。该选项只属于 Apple Probe target；
Engine component test 仍保持跨平台。`--no-device` 不是 CoreAudio 或物理扬声器
证据。

## 8. 测试与验收

### 8.1 跨平台自动测试

Realtime Engine component test 覆盖：

- 64-slot 加载边界与 running 时不可变；
- velocity 和 slot 验证；
- 未加载或已清除 Sample 的 Trigger 拒绝；
- SPSC FIFO、1,024 条边界和 queue drop；
- 单 Voice 的精确 float 输出和结束释放；
- 多 Voice 累加与输出限制；
- 128 Voice 边界和显式 voice drop；
- callback 分块尺寸变化；
- stop/reset 后无旧 Voice 泄漏；
- stopped/stopping Trigger 拒绝，restart 后无旧 Queue/Voice 重放且 Sample 保留；
- telemetry 计数一致；
- render 路径零 heap allocation；
- producer/consumer stress 只进入 `stress` tier，不进入 Product Proof。

### 8.2 Apple 自动测试

macOS 构建必须证明：

- CoreAudio adapter target 能编译和链接 Apple frameworks；
- start/stop 状态机的错误路径可通过注入的 Audio Unit operations 测试；
- `--no-device` Probe smoke 输出确定 JSON，且不声称物理通过；
- 非 Apple 构建不编译 Apple source，也不存在假成功的 CoreAudio stub。

### 8.3 macOS 设备验收

实现完成后在当前 Mac 默认内置或有线输出上运行：

1. 启动 Probe；
2. 连续执行至少 20 次 `trigger`，每次听到恰好一个短音；
3. 执行 `status`，确认 enqueue/process 一致且 drop/overload/failure 为 0；
4. `stop` 后触发必须被拒绝；
5. `start` 后再次触发，必须恰好一个起音；
6. `quit` 后进程正常退出。

该验收证明 Native CoreAudio 输出和生命周期，不证明正式 Host、Project Snapshot、
实体 MIDI、录音 Capture Ring、Touch-to-Sound 门槛或发行质量。

## 9. 明确非目标

- Creator UI 或任何 Native UI；
- 正式 `apps/native-test-host`；
- Application Facade / Project / Runtime Snapshot 集成；
- Project Bundle 解析或持久化；
- Keyboard、Mouse、MIDI 或 Touch 实体输入；
- Capture Ring、录音、Resample 或 Audio Input；
- Loop、Pitch、Envelope、FX、Time-stretch 或 Sample streaming；
- WASM、AudioWorklet、OPFS 或 Web Host；
- Device picker、Bluetooth、aggregate device 或多输出路由；
- Product Assembly Host 注册、发布、部署或 Channel 晋级。

## 10. 后续切片

5A 通过后，单独设计 5B Formal Native Realtime Host：

- Host 只通过 Application Facade 加载/查询 Project；
- Facade 在非 Audio Thread Cook 并验证 Immutable Runtime Snapshot；
- Snapshot 在安全音频边界原子发布；
- 外部输入通过单一实时生产路径进入 Event Queue；
- 录音事件经 lock-free Capture Ring 到后台 Writer，再通过 Authoring Command
  提交；
- Host 不解析 Bundle，Facade 不进入 realtime callback；
- 真实设备与物理延时另设平台 Gate。

Web 物理矩阵仍保持当前状态：Safari Pointer 已有不满足批准 p95 的证据；Chrome
Pointer/MIDI 与 iPadOS Safari Touch/lifecycle 延期且未验证。5A/5B 不修改、覆盖或
默认通过这些结果。

## 11. Version Management

- Product Build：`1.0.9.0` → `1.0.10.0`。原因是 Product Assembly 所列的正式
  `audio-runtime` Module 发生功能性变化，即使 Probe 本身不进入 Assembly。
- `audio-runtime` Module SemVer：`0.1.0` → `0.2.0`，新增向后兼容的 realtime
  Engine 与 Apple output API；`api_version` 保持 `1`。
- `application-facade` Module SemVer：`1.0.0` → `1.0.1`。Facade 公开 API 与
  `api_version: 2` 不变，但其精确 `audio-runtime` 依赖必须更新到 `0.2.0`，新的
  source-package identity 需要 Patch 版本。
- `core-cli` 与 `core-mcp` Host SemVer：各从 `1.0.0` → `1.0.1`。两者公开 Host
  API 与 `api_version: 2` 不变，只把精确 `application-facade` 依赖更新到 `1.0.1`。
- `products/lmdj/assembly.json` 锁定上述新 Module/Host 版本，随后由版本工具重建
  `assembly.lock.json`；Probe 本身不加入 `hosts`。
- Provider SemVer：不变。
- Contract SemVer：不变，不新增或修改跨语言 Contract。
- Channel：保持 `canary`；本切片不授权 tag、发布、部署或晋级。

## 12. 完成定义

只有同时满足以下证据，5A 才完成：

- Realtime Engine 与 Apple adapter 按上述边界实现；
- 跨平台和 macOS 自动测试通过，stress 不进入 Product Proof；
- `scripts/core.sh proof` 通过且 Assembly lock 与新版本匹配；
- 当前 Mac 默认内置或有线输出完成设备验收；
- Audio Thread 零 lock/allocation/I/O/log 规则有代码审查和测试证据；
- Probe 明确保持测试身份，不被 Product Assembly 或 Creator UI 消费；
- Web 物理矩阵状态没有被改变或美化。
