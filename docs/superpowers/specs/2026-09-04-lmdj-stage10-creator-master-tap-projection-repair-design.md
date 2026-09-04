# LMDJ Stage 10 Creator Master-Tap and Projection Repair — 2026-09-04

日期：2026-09-04

状态：**已确认（2026-09-04）**——Stage 10 的产品决策不重判；本修复补齐
Task 9 开工 RED 证明缺失的 Web Runtime master-bus 接线与 Creator Project v4
投影边界。修复必须作为 #435 的前置交付，之后才可恢复 Creator Perform
surface。

关联权威：

- [`2026-08-28-lmdj-stage10-perform-design.md`](2026-08-28-lmdj-stage10-perform-design.md)
  P10-D1、P10-D12、P10-D13、P10-D17、P10-D18、P10-D25；
- [`2026-09-01-lmdj-stage10-host-runtime-session-design.md`](2026-09-01-lmdj-stage10-host-runtime-session-design.md)
  HRS-D1、HRS-D7、HRS-D9、HRS-D11；
- [`2026-08-31-stage10-performance-contract-repair.md`](../../prd/decisions/2026-08-31-stage10-performance-contract-repair.md)
  §5、§8；
- [`2026-08-29-lmdj-stage10-perform.md`](../plans/2026-08-29-lmdj-stage10-perform.md)
  Task 8–10。

## 1. 已证实的阻断

Task 9 的测试先行预检证明，当前文件边界无法完成批准的真实 Browser journey：

1. **Task 8 交付了 tap、队列、WAV writer 与 OPFS store，但没有实际音频图
   接线。** `runtime_session.mjs` 在闭包内私有创建 `AudioContext`；C++
   `RealtimeAudioWorklet` 私有创建 `lmdj-realtime-engine` node，并把唯一 stereo
   output 直接接到 `AudioContext.destination`。Creator 既拿不到 engine node，也
   不应获得可任意改线的裸 node/context。`MasterTapBatchQueue.connect()` 只接收
   已存在的 port，不能给无输入的 tap node 创造 master-bus 音频。
2. **Creator 的唯一 Project 投影仍是 v3-only。**
   `runtime/project_actions.ts::projectView()` 精确拒绝
   `lmdj.project.v4`，`ProjectView` 也没有 `patternSlots`。第一次合法
   `pattern.slot.assign` 会把 v3 Project 提升为 v4；随后 refresh、Sample replace
   或 reload 都会得到 `HOST_PROTOCOL_MISMATCH`。在 `perform_state.ts` 另写 parser
   或从 mutation response 拼槽位，会形成第二份 Host slot truth。
3. **Task 9 早于 Task 10，当前 `1.0.41.0` identity 没有 Perform 录音配额与
   distribution asset role。** Writer 正确地拒绝缺失参数；Task 9 不能硬编码
   默认值，也不能提前修改 active Assembly。测试与 source staging 必须使用同一
   future-candidate 配置边界，最终只由 Task 10 正式激活。

这三项是实现分解缺口，不改变 30 分钟、32 批、Host-layer tap、16 个持久槽或
Core 权威等既有产品决策。

## 2. 决策

### CMTP-D1：Web Runtime 拥有实际音频图，Creator 只持有类型化 capture lifecycle

Web Runtime platform 是 `AudioContext`、engine node 与 destination 的唯一图所有者。
当 Host 提供合法的 Perform tap 配置时，它必须在同一个、仍处于 suspended 状态的
context 中建立：

```text
lmdj-realtime-engine stereo output
  → lmdj-perform-master-tap (transparent stereo pass-through)
  → AudioContext.destination
```

engine node、Emscripten audio-object handle 与 `AudioContext` 不暴露给 Creator。
底层 Web bridge 可以在内部传递 opaque destination handle，使 C++ engine node 接到
tap node；这个 handle 不是 Application Facade、Project Truth 或公共 Host 输入。
没有合法 tap 配置的 Build 保持现有 `engine → destination` 路径。

tap node 在 Audio 激活时一次建立，录制 start/stop 不重接图。它在 idle、recording、
stopped、writer/backpressure failure 各状态都继续逐 quantum 原样复制左右声道；
录制状态只决定是否把 4,800-frame 批次送往 Host。这样 start/stop 不产生双路增益、
静音窗口或音乐边界语义。

Worklet module/node 初始化失败时，图所有者回退到直接输出并把 capture 标记为不可用；
live audio activation 不被伪装成成功录音。运行中的 `processorerror` 由 browser-main/
control 路径停止 capture、报告稳定错误并恢复直接输出，不能阻塞、回调或通知 render
函数。writer、OPFS、队列或 sink 失败只停止 capture 并封存耐久 WAV prefix，不改变
engine render 生命周期。

### CMTP-D2：Web-only capture API 是类型化 Host 能力，不是 Facade operation

Web Runtime session 增加 Web-only 能力，锁定语义如下：

```ts
interface PerformanceMasterCaptureLimits {
  readonly performRecordingFrames: number;
  readonly performRecordingQueueBatches: number;
}

interface PerformanceMasterCaptureSink {
  onBatch(channels: readonly [Float32Array, Float32Array]): void;
  onStopped(): void;
  onFailure(reason: "tap-failure", droppedFrames: number): void;
}

interface PerformanceMasterCapture {
  stop(): Promise<void>;
}

interface WebPerformanceCaptureSession {
  performanceMasterCaptureLimits(): PerformanceMasterCaptureLimits | null;
  startPerformanceMasterCapture(
    sink: PerformanceMasterCaptureSink,
  ): Promise<PerformanceMasterCapture>;
}
```

上述 TypeScript 名称、方法集合、字段与语义就是锁定的公开 Host API，不得在实现中
删改或扩大。这些方法不发 transport request、不进入 Application Facade、不推进
Project revision，也不携带 tick、runtime frame 或 input sequence。

`startPerformanceMasterCapture` 只在 Audio Runtime running、tap ready、无另一 capture
时成功；它先安装 sink，再让 worklet 从下一 render quantum 开始录制。`onBatch` 是
单向、同步投递入口，返回值和异常永不反馈给 render。`stop()` 幂等，等待 worklet
发布最后一个不足 4,800 frames 的批次与 stopped acknowledgement；随后由 Host queue
排空并封存 WAV。session close、audio interruption、visibility lifecycle 或 owner loss
也必须经同一 stop/failure 收口，不能遗留第二个 listener 或活跃 capture。

同一 session 可串行创建多次 capture。每次 start 都使用新的 Host sink/queue/writer，
worklet 的上一批 buffer、failure 与 stopped acknowledgement 不得泄漏到下一次录制。

### CMTP-D3：配额与 asset availability 只来自注入的 Product identity

`performanceMasterCaptureLimits()` 只有在以下条件同时满足时返回非 null：

- session 构造时注入的 `resource_limits` 同时含正整数
  `perform_recording_frames` 与 `perform_recording_queue_batches`；
- 注入了同源 `lmdj-perform-master-tap` distribution URL/processor 配置；
- AudioWorklet、OPFS 与既有 Web capability preflight 均满足；
- tap graph 已成功建立。

缺键、错型、额外默认、从 UI 常量回填或运行时猜测一律 fail closed。Task 8A 与 Task 9
的自动化使用显式 Stage 10 candidate identity/manifest fixture，通过与 production 相同的
session construction 路径注入锁定值 `86400000` 与 `32`；不得用
`window.__LMDJ_*` 后门、替换 transport 或伪造 sealed 状态。

当前 `1.0.41.0` identity 缺少这些键，因此 main 上尚未集成的 Perform mode 必须
保持 disabled；只有 playable Project、running Audio Runtime 与非 null capture limits
同时成立才启用，不暴露一个只能生成静音/假 WAV 的半成品。Task 10 将两项配额、
master-tap asset role、Host/module identities 与 Product Build `1.0.42.0` 一次性写入
active Assembly/generated identity/distribution manifest；同一套 Browser journey 必须
在正式 package 上重跑后才算集成完成。

### CMTP-D4：Creator ProjectView 是 v3/v4 的唯一严格投影

`runtime/project_actions.ts::projectView()` 保持 Creator 获取 Project Truth 的唯一
入口，`runtime_types.ts::ProjectView` 增加只读 `patternSlots`，恰好 16 项。

- 对 v3 inspection：必须确认 `pattern_slots` 与 `performances` 不存在；投影为冻结的
  16 个 null。这不是 UI 猜测，而是 `lmdj.project.v3 → v4` 唯一迁移定义的规范视图。
- 对 v4 inspection：必须确认 `pattern_slots` 恰好 16 项；每项为 null 或合法
  PatternId；非空项唯一且引用同一 inspection `patterns` 中存在的 Pattern。
- 任何未知 Contract、错长、重复、悬空引用或 revision 不一致都返回既有
  `HOST_PROTOCOL_MISMATCH`，不保留旧槽位继续操作。

open/import/refresh、slot assign/clear/move、record begin/flush/save/discard、Sample
replace 与 reload 后都通过既有 projection refresh 重新读取 far-side truth，再让 UI
settle。mutation response 只证明该 command receipt，不作为本地槽位真相。Pattern
Launch strip 只读 `ProjectView.patternSlots`；`perform_state.ts` 不解析 Project bundle
或 raw inspection。

### CMTP-D5：Task 9 只在前置接线合入后恢复，Task 10 才激活 Product Build

交付顺序固定为：

1. **Task 8A：Web Runtime master-tap graph prerequisite。** 交付 CMTP-D1–D3 的
   opaque graph wiring、Web-only typed lifecycle、可重复 start/stop、失败回退以及真实
   AudioWorklet Browser witness；不改 active Assembly、版本或 current Portal truth。
2. **Revised Task 9 / #435。** 扩大声明文件范围，交付 CMTP-D4、Perform surface、
   Host writer/store 组合与使用 Stage 10 candidate fixture 的完整 Browser journeys。
3. **Task 10 / #436。** 写入正式 resource keys、asset role、版本与 generated identity，
   在 production-shaped package 上重跑完整 journey，并更新 current Portal。

Task 8A 与 Task 9 各自仍是一个 reviewable Conventional Commit/PR。不得把 C++ graph、
Creator projection 与整个 surface 塞进同一 #435 commit，也不得把真实 WAV 验收推迟成
Task 10 才首次运行的测试。

## 3. 错误与非破坏性规则

- tap 配置或初始化失败：live audio 可回退直连；capture capability 为 unavailable，
  Record 不可用并展示可执行错误；不得创建 draft 或临时 WAV 后才发现无输入。
- 重复 start：返回既有 Host state 类 typed refusal，既有 capture、sink、writer 与图
  不变。重复 stop：返回同一完成结果，不发送第二个尾批或 stopped acknowledgement。
- sink callback 抛错、队列第 33 批、writer/OPFS failure：worklet 不等待；Host 停止
  capture，WAV 只保留最后耐久合法 prefix，Project 与 draft 按既有 save/discard 语义
  处理。
- Project v4 投影失败：不局部应用 slot receipt，不让 Pattern Launch 继续使用旧 Host
  cache；用户可重试完整 refresh 或重新打开 Project。
- capability-gated 的 1.0.41.0 不写新 manifest key、不宣称 Stage 10 Build 已集成；
  1.0.42.0 才能把缺失/错误配额视为 distribution/manifest gate failure。

## 4. 验收

书面修复及后续实现必须具备以下直接证据：

1. Audio 激活前后的图只存在一条可闻 stereo 输出路径；tap 输入来自实际
   `lmdj-realtime-engine` FX 后 output，不是 oscillator、麦克风、另一个 AudioContext
   或测试合成 batch。
2. 真实 Browser 录下的 WAV 为 PCM16/48 kHz/stereo；确定性左右声道 fixture、Pad 与
   FX 变化能在 WAV frame 中找到对应 witness；idle tap 与 stop 后不再产生录音 batch，
   live audio 仍继续。
3. 连续两次 capture 无 listener/buffer/failure 串线；normal stop、backpressure、
   writer fault、tap fault、audio interruption 与 session close 都收口且 render 不等待。
4. 缺少或破坏任一 resource key/tap asset 的 candidate 启动 fail closed；注入正确
   Stage 10 candidate identity 后走同一生产 session construction 并开放能力。
5. v3 Project 打开后得到 16 空槽；第一次 assign 后 refresh 为 v4；move、Sample replace、
   reload 与重新打开后仍读取同一权威槽位。错长、重复与悬空 v4 全部拒绝且零 UI
   本地提交。
6. #435 的完整 main journey 与所有独立异常 journey 使用真实 Web Runtime、真实
   OPFS、真实 Project inspection/status/replay witness；没有 transport stub、Host timer、
   本地 slot reducer 或 `__LMDJ_*` production/test hook。
7. Task 8A 和 Revised Task 9 各自的 focused、Creator unit/accessibility、Web Runtime、
   Playwright、full Core 与 Architecture Portal gates 通过；Task 10 再以正式 package/
   identity 重跑并记录 run IDs、revision 与 artifact digest。

## 5. Version Management

Version impact: no new allocation.

本修复不改已经锁定的 Stage 10 版本目标：audio-runtime `3.0.0`、
web-runtime-platform `3.0.0`、creator-web `3.0.0`、web-runtime-host `3.0.0` 与
Product Build `1.0.42.0` 支付新增图接线、Host capture API、Project v4 投影和
distribution identity。Task 8A 不修改 manifest；Task 10 开工前仍必须执行 fresh
allocation audit，任何目标已被占用都停止并刷新主计划。

## 6. Documentation Impact

Documentation impact: none for Task 8A and Revised Task 9.

理由：两项任务只补尚未由 active `1.0.41.0` Assembly 启用的 Stage 10 source 与测试
边界；capability gate 保证 current Portal/Product Truth 不提前变化。Task 10 仍负责
`/core/modules/audio-runtime/`、`/core/modules/web-runtime-platform/`、
`/hosts/creator-web/`、`/platform/web-runtime/`、`/product/workflows/` 与其余已列
Portal routes，Task 11 负责 immutable snapshot。

## 7. 拒绝的替代

### 7.1 Creator 捕获另一个 AudioContext、麦克风或系统输出

拒绝。它不等于实际 engine FX 后 master bus，会产生权限、时钟与设备差异，并绕过
Web Runtime 图所有权。

### 7.2 monkey-patch `AudioNode.connect` 或暴露裸 engine node/context

拒绝。前者依赖浏览器实现细节，后者让 Creator 获得任意改线能力，破坏 Host/runtime
边界且无法形成稳定 Contract。

### 7.3 从 Pattern 列表或 mutation receipts 在 UI 拼 16 槽

拒绝。Pattern 集合不携带槽位顺序，单次 receipt 也不能恢复其余槽位；两者都会建立
第二份 Host truth。

### 7.4 在 Task 9 硬编码 `86400000` 与 `32`

拒绝。Task 8 已锁定 writer 必须读取 Host 参数；默认值会掩盖缺失/错误 Assembly，
使 1.0.41.0 被误报成已集成 Stage 10。

### 7.5 先让 #435 用静音 tap 或 fake sealed UI 通过，再在 Task 10 补实接线

拒绝。它把完整 Browser journey 变成 UI/mock 证据，不能证明 WAV、失败封存、bind、
replay 或 resample 的真实 far-side truth。
