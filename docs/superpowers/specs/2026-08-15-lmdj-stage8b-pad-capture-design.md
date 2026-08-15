# LMDJ Stage 8B Pad Capture Design — 2026-08-15

## 1. 结论

Stage 8B 在 Creator 与 Web Runtime Host 层实现麦克风 Pad Capture：用户对任意
稳定 Pad 录音（Host 内存缓冲最长 60 秒），裁剪到 ≤5 秒后，经 Stage 8 已交付的
`sample.import.*` 会话以 PCM16 WAV 提交为普通 Sample Artifact。Core Modules、
Application Facade 表面、传输协议、活动 manifest 与全部 Contract **零变更**；
录音只是既有导入边界的一个新字节来源。

本设计由 2026-08-15 的 brainstorming 会话批准，解决 S8-D13 与
`docs/prd/decision-log.md` 留下的 Stage 8B capture lifecycle 开放边界。

## 2. Approved Decisions

| ID | 决策 |
| --- | --- |
| S8B-D1 | v1 只使用系统默认输入设备，不做设备选择器。未来如需选择器，选择状态落 Workspace/Host 设置，永不进入 Project Truth。 |
| S8B-D2 | 首次按下录音手势时才调用 `getUserMedia`。拒绝产生显式、可解释、可重试的错误态；录音中权限被撤销则停止采集并保留已录缓冲。 |
| S8B-D3 | 录长后预裁剪：Host JS 层缓冲上限 60 秒，到顶自动停止；用户裁剪到 ≤240,000 帧（48 kHz 下 5.0 秒）后才进入提交。提交沿用现有 `imported_wav_bytes = 1,048,576` 与 `decoded_frames_per_pad = 240,000` 上限，manifest 不变。 |
| S8B-D4 | 无输入监听。录音期间以实时电平表与增长中的波形做视觉监控，输入永不接到音频输出，物理上消除啸叫风险。 |
| S8B-D5 | 页面 blur 与 hidden 一律停止采集（与 Stage 8 停 Voice 不变量一致），已录缓冲保留并进入裁剪态。（2026-08-15 修订：若中断发生在首批音频到达之前、缓冲为空，则没有可裁剪的内容——此时 `device-lost` 与 `permission-revoked` 进入可重试的 `permission-error` 并给出原因文案，`user`/`blur`/`hidden` 直接回到 `idle`。失败原因绝不静默丢弃。） |
| S8B-D6 | 录音期间不打开 Core 导入会话；`sample.import.begin` 在用户确认提交时才发起，`expected_revision` 取提交时刻的新鲜值。冲突显式报告、缓冲保留、用户手动重试；无 auto-rebase、无乐观成功。 |
| S8B-D7 | 采集约束关闭 `echoCancellation`、`noiseSuppression`、`autoGainControl`：音乐采样需要原始信号，不是语音通话处理链。 |
| S8B-D8 | 验收由 Chromium 假设备（固定 WAV 喂入）自动化测试把关；真麦克风听感、Safari 与 iPadOS 录音行为显式记入 deferred 台账，做了才计入。 |
| S8B-D9 | 采集管线使用 AudioWorklet 采集节点，挂在 Creator 自有的独立 `AudioContext({sampleRate: 48000})` 上；float→PCM16 WAV 编码在 Host 层于提交时完成。不使用 MediaRecorder（有损压缩）或已废弃的 ScriptProcessorNode。（2026-08-15 修订：审计确认引擎 context 位于 Emscripten 运行时内部、不向 Host 暴露，新增暴露面会违反本设计的零平台变更原则；独立 context 保留全部已批准属性——48 kHz 固定、浏览器重采样、输入永不接输出——且隔离与清理更干净。） |
| S8B-D10 | "共享 prepared-PCM 配额（单 Pad 最长约 60 秒、全 Bank 合计约 174 秒立体声）"立为具名后续阶段，记入 `docs/prd/open-questions.md`，与"Loop 素材 BPM Time-stretch"开放问题同一次设计评审处理。Stage 8B 不改资源模型，也不抬 512 MiB 固定堆。 |

## 3. Stage Boundary

权威阶段序列不变：Stage 8B 是 microphone / audio-input Pad Capture，紧随
Stage 8。Stage 8B 的成功命题是：

> 用户可以在不绕过 Application Facade、不改变任何 Core Contract、不产生第二份
> Project Truth 的前提下，用麦克风为任意稳定 Pad 录制、裁剪并提交一段可靠可
> 复放的 Sample。

以下明确不属于 Stage 8B（见 §5）：自动切片（Stage 12）、Take/Pattern 录制
（Stage 9）、Sample library（Stage 2+ 开放问题）、长素材共享配额（S8B-D10
后续阶段）。

## 4. Scope

Stage 8B 实现：

1. Creator Sample mode 内的 Capture 入口：空 Pad 与已分配 Pad 均可录音
   （已分配 Pad 沿用 S8-D12 的替换确认语义）；
2. 首次录音手势触发的 `getUserMedia` 权限流程与错误态（S8B-D2）；
3. AudioWorklet 采集节点、48 kHz float 采集、Host JS 环形缓冲（≤60 秒，
   到顶自动停）；
4. 录音期间的实时电平表与增长波形（S8B-D4）；
5. 裁剪 UI：在已录缓冲上选择 ≤240,000 帧的区间，试听选区，提交或丢弃；
6. 提交路径：选区 float→PCM16 WAV 编码（48 kHz，声道数跟随输入流、上限 2），
   经既有 `sample.import.begin/chunk/commit/abort` 会话入 Core；
7. 全部中断语义（blur/hidden、权限撤销、设备消失、60 秒到顶）与单一所有者
   生命周期清理；
8. Chromium 假设备自动化验收与 deferred 实体证据台账。

## 5. Explicit Non-goals

- 设备选择器、设备热插拔 UI、多设备并发采集（S8B-D1）；
- 输入监听与任何监听音量/路由设置（S8B-D4）；
- 抬高 `imported_wav_bytes`、`decoded_frames_per_pad` 或任何 manifest
  resource limit；抬高 512 MiB 固定堆；共享配额资源模型（S8B-D10 后续阶段）；
- MediaRecorder、音频压缩、非 PCM16 的持久化格式；
- 未提交缓冲的持久化（OPFS/localStorage）：页面刷新丢弃未提交录音是接受的
  fail-closed 行为；
- 自动切片、静音检测、自动增益、录音量化；
- Take/Pattern/Sequence 录制与录音恢复；
- 系统音频/标签页音频采集（仅麦克风/音频输入设备）；
- 修改 Core Modules、Contracts、Facade 表面、传输协议或活动 manifest；
- 触碰退役的 `lmdj.patch.v1`、`lmdj.materials.v1`。

## 6. Architecture

### 6.1 分层与数据流

```text
麦克风 ──getUserMedia(S8B-D2/D7)──▶ MediaStreamAudioSourceNode
        ──▶ Capture AudioWorkletNode（48 kHz float，批量 port 消息）
        ──▶ Creator Host JS 环形缓冲（≤60 s，≈23 MB，浏览器 JS 内存）
                │ 用户裁剪 ≤240,000 帧（S8B-D3）
                ▼
        float→PCM16 WAV 编码（Host 层，确定性转换）
                │
        既有 sample.import.begin / chunk / commit / abort
        （command_id + expected_revision，有界 verified sidecar）
                ▼
        Core：staging（lmdj.sample-staging.v1）→ writer lease → 提交
             → Cooker 准备 → Bank 发布 →（既有）波形 / trim / 试听
```

提交完成后的一切能力（波形、trim、触发模式、试听）均为 Stage 8 已交付的
现成行为，Capture 不复制其中任何一层。

### 6.2 复用边界（2026-08-15 审计核实）

Capture 提交完整复用以下既有表面，不新增任何 Core 表面：

- Facade 分块导入会话（`packages/application-facade/include/lmdj/facade/application.hpp`）：
  `begin_sample_import(SampleImportBeginRequest{import_token, project_path,
  meta(command_id, expected_revision), slot, asset_id, byte_length})` →
  `append_sample_import(token, offset, bytes, final)` →
  `commit_sample_import(token)` / `abort_sample_import(token)`；
- Web 传输操作（`packages/web-runtime-platform/src/control_runtime.cpp`）：
  `sample.import.begin`、`sample.import.chunk`、`sample.import.commit`、
  `sample.import.abort`，以及既有的令牌清理路径；
- Project I/O 暂存（`packages/project-io/src/project_store.cpp`）：
  `lmdj.sample-staging.v1` 标记、writer lease、同令牌崩溃回收与已用令牌拒绝，
  Capture 免费继承崩溃安全的幂等提交；
- 限值权威仍是活动 Web manifest 的 `resource_limits`，不在 Host 层复制第二份
  限值对象。

### 6.3 采集节点与实时边界

Capture AudioWorkletNode 挂在 Creator 自有的独立
`AudioContext({sampleRate: 48000})` 上（S8B-D9 修订：引擎 context 由
Emscripten 运行时内部持有，不向 Host 暴露），不接入引擎 render graph，输入
永不路由到输出（S8B-D4）。浏览器把输入流重采样到 context 的 48 kHz，因此
提交的 WAV 恒为 48 kHz，Cooker 准备时走免重采样路径。采集图整体（context、
stream、worklet node）由 capture controller 单一所有者创建与关闭。

"音频 render 路径零分配、无锁、无系统调用"的既有不变量约束的是引擎 render；
采集节点不属于 render 路径，但不得干扰它：采集帧在 worklet 内聚合为约 100 ms
的批次后经 port 消息发往主线程，禁止逐 128 帧发消息。电平表数值（peak/RMS）
随批次附带，主线程不做第二次全量扫描。

## 7. Capture 状态机

```text
idle ──录音手势──▶ requesting-permission ──granted──▶ recording
  ▲                     │ denied                        │ 停止手势 / 60 s 到顶 /
  │                     ▼                               │ blur / hidden /
  │               permission-error                      │ 设备消失 / 权限撤销
  │                     │ 下次手势重试                   ▼
  │◀──丢弃──────────────┴──────────────────────────  trimming
  │                                                     │ 提交（≤240,000 帧选区）
  │                                                     ▼
  │◀──成功（Pad 已赋 Sample）──────────────────────  committing
  │                                                     │ 冲突 / 失败
  │                                                     ▼
  └──丢弃─────────────────────────────────────────  commit-error
                                （缓冲保留，可改选区重试提交）
```

- 所有到达 `trimming` 的路径缓冲一律保留；仅显式丢弃或提交成功释放缓冲。
- 缓冲为空时（中断早于首批音频到达）没有可裁剪内容，不进入 `trimming`：
  `device-lost`/`permission-revoked` 进入可重试的 `permission-error` 并带原因
  文案，`user`/`blur`/`hidden` 回到 `idle`（S8B-D5 修订）。
- `recording` → `trimming` 的每个触发原因（停止手势、到顶、blur、hidden、
  设备消失、权限撤销）都在 UI 上可区分地呈现。
- 对正在发声的目标 Pad 开始录音属于打断性操作：停掉该 Pad 的活动与 latched
  Voice（沿用 Stage 8 中断规则）。
- 采集图（MediaStream、source node、worklet node）由 Creator 的 capture
  controller 单一所有者管理：进入 `trimming` 即停轨并释放 MediaStream
  （麦克风指示灯熄灭），与 Runtime Session 的 Voice 清理互不重复。

## 8. 权限与设备

- `getUserMedia({audio: {echoCancellation: false, noiseSuppression: false,
  autoGainControl: false}})`，无 `deviceId` 约束（S8B-D1/D7）。
- 权限仅在录音手势的调用栈内请求（S8B-D2）。拒绝 → `permission-error`，
  附浏览器无法区分"本次拒绝"与"永久拒绝"时的通用指引文案；再次手势重试。
- 录音中权限被浏览器/系统撤销：等价于设备消失——停止采集、保留缓冲、
  进入 `trimming`；若此时缓冲为空，则进入可重试的 `permission-error` 并说明
  原因（S8B-D5 修订）。
- 隐私边界：Sample Artifact 字节与 SHA-256 身份是唯一持久化产物；不持久化
  设备名、设备 ID 或权限状态；未提交缓冲只存在于页面内存。

## 9. 缓冲与内存预算

- 环形缓冲：48 kHz float32，声道数跟随输入（上限 2），60 秒立体声 ≈ 23 MB，
  驻留浏览器 JS 内存，不进入 512 MiB wasm 固定堆。
- 提交约束推导（现状不变）：`decoded_frames_per_pad = 240,000` ÷ 48,000 Hz
  = 5.0 秒；PCM16 立体声 5 秒 = 960,044 字节 < `imported_wav_bytes =
  1,048,576`。裁剪 UI 以 240,000 帧为硬性选区上限，字节上限因此自动满足。
- 长素材路径见 S8B-D10：共享配额可在不抬堆的前提下支持单 Pad ≈60 秒（prepared
  float 23 MB，装入 64 MiB 共享 Bank 预算），属后续阶段设计评审。

## 10. 提交与并发语义

- 提交时 Host 将选区编码为 48 kHz PCM16 WAV：float→int16 转换规则固定——
  clamp 到 [-1, 1]，乘 32767，向最近整数舍入（ties away from zero），无
  dither——同一输入帧序列产生逐字节相同的 WAV 与相同的 SHA-256。
- `sample.import.begin` 于提交时发起（S8B-D6），`expected_revision` 为当刻
  Project revision；空 Pad 走 import 语义，已分配 Pad 走 Replace 语义
  （S8-D12 确认对话在录音前完成）。
- 冲突（录音/裁剪期间 Project 被其他窗口修改）：显式报告，缓冲与选区保留，
  用户重试时以新的 `command_id` 与新鲜 `expected_revision` 重新提交同一字节。
- 提交后失败语义沿用 Stage 8：成功的 mutation 回执不被后续 preview 清理或
  inspect 失败覆盖；Cooker 失败报告为"已保存真相 + 过期 Runtime"，重试
  Prepare 显式。

## 11. 测试与验收证据

自动化（把关验收，全部确定性）：

- 单元/组件：状态机全转移矩阵；60 秒到顶自动停；blur/hidden/权限撤销/设备
  消失中断；环形缓冲边界；float→PCM16 编码确定性（固定输入 → 固定字节 →
  固定 SHA-256）；240,000 帧选区上限强制。
- Chromium 端到端（Playwright + `--use-fake-device-for-media-stream` +
  `--use-file-for-fake-audio-capture=<固定 WAV>`）：录→裁→提交→`sample.inspect`
  验证 Artifact 身份→触发回放；权限拒绝路径经 Playwright permission API；
  提交冲突路径经双会话修改 revision。
- 提交故障矩阵复用既有 `sample_after_staging` fault-injection 点。

Deferred 实体证据台账（S8B-D8，照 Stage 8 惯例，做了才计入）：

- 真麦克风录音→提交→回放听感（Chrome 桌面）；
- Safari 桌面与 iPadOS 的 `getUserMedia`/AudioWorklet 采集行为；
- 实体外置声卡输入。

## 12. Version Management

- 本设计文档提交本身：Version impact: none（纯文档，不触碰活动 manifest、
  Module 版本、Contract 或 Product Build）。
- Stage 8B 实现（实施计划扩展时落实）：
  - Product Build：`1.0.22.0` 之后的下一个 Build，经 portal/version 工具在
    版本集成 Task 分配，不手填；
  - `creator-web` minor bump；`web-runtime-host` 仅在其文件实际变更时 bump
    （2026-08-15 审计：采集与提交路径全部落在 creator-web 内，预期不触碰
    web-runtime-host）；
  - Core Modules、`web-runtime-platform` 的 Facade/传输表面、全部 Contract、
    manifest `resource_limits`：零变更（若实现中发现必须变更，即为设计冲突，
    退回设计评审，不得就地弱化）。

## 13. Documentation Impact

Documentation impact: required——Portal 的 Creator 与 Web Runtime Host 当前页
在实现 Task 中更新；`docs/prd/decision-log.md` 增记 S8B-D1–D10（随本设计
提交）；`docs/prd/open-questions.md` 增加共享配额后续阶段行（随本设计提交）。
Stage 8B Product Build 分配时须制作不可变 Portal snapshot。

## 14. Rejected Alternatives

### 14.1 MediaRecorder 采集

拒绝。输出 webm/opus 有损压缩且跨浏览器容器不一致，与 PCM16 Artifact 身份
和确定性准备直接冲突。

### 14.2 v1 输入监听

拒绝。笔记本场景麦克风与扬声器物理相邻，监听几乎必然啸叫；抑制策略与监听
路由把 8B 显著变大。电平表与增长波形已提供录音置信度。

### 14.3 v1 设备选择器

拒绝。`enumerateDevices` 标签权限、热插拔与选中设备消失回退把 8B 变大；
Firefox 原生弹窗已含设备选择，Chrome/Safari 可在系统层切换。未来选择器落
Host 设置的路径已由架构不变量预留。

### 14.4 抬 manifest 上限到 10 秒

拒绝（本阶段）。数学上可行（480,000 帧/2 MiB，双 Bank 峰值 122.9 MB 贴
128 MiB 预算），但把版本影响从 2 个 Module 扩大到 manifest 源头、
`manifest_gate` 精确校验、Facade 强制点与测试矩阵，且贴顶预算需要新的内存
余量验证。长素材需求由 S8B-D10 的共享配额阶段一并解决更彻底。

### 14.5 固定堆抬到 1 GiB

拒绝。`ALLOW_MEMORY_GROWTH=0` 下堆在启动时全额分配，1 GiB SharedArrayBuffer
在 iPadOS Safari 的单页内存限制下会分配失败或被系统终止；512 MiB 是照顾
iPad 级目标设备的既定保守值。抬堆是"承诺的最低设备"级产品决策，不属于 8B。

### 14.6 共享配额并入 8B

拒绝。共享配额波及 Cooker Bank 分配、audio-runtime PreparedSampleBank 内存
布局（经 stress 验证的 lock-free 发布路径）、manifest 语义、Facade 校验与
全新的"他人占用配额"失败类别，是独立阶段的体量，且资源 Contract 语义变更
必须走自己的设计评审（S8B-D10）。

## 15. Acceptance Checklist

- [ ] Creator 仅通过 Web Runtime Platform / Application Facade 提交录音；
      Capture 不新增任何 Core 表面、Contract 或 manifest 变更；
- [ ] 权限仅在录音手势内请求；拒绝可解释、可重试；撤销停采集保缓冲；
- [ ] 60 秒到顶自动停；blur/hidden 停采集且缓冲保留；采集图单一所有者释放，
      进入裁剪即熄麦克风指示灯；
- [ ] 裁剪选区硬性 ≤240,000 帧；提交 WAV 恒为 48 kHz PCM16，字节与 SHA-256
      确定性可复现；
- [ ] 提交携带新鲜 `expected_revision`；冲突显式、缓冲保留、重试用新
      `command_id`；无 auto-rebase；
- [ ] Chromium 假设备端到端（含权限拒绝与冲突路径）绿色；
- [ ] 真麦克风、Safari、iPadOS 证据在 deferred 台账中如实标注；
- [ ] `docs/prd/decision-log.md` 含 S8B-D1–D10；`docs/prd/open-questions.md`
      含共享配额后续阶段行。
