# LMDJ Stage 10 Perform Design — 2026-08-28

日期：2026-08-28

修订：2026-08-28 同日第二版——P10-Q1–Q5 已由五个决策文件解决（#383–#387），
按 Koala 官方手册核对后 FX 改为连续滑条手势流、HOLD 改为全局显式模式、串联
链序进 Contract、Replay 改为按当前 Project 回放。2026-08-29 设计评审——
逐节批准全文；裁决四项待评审事项为 P10-D14–D17（FX 名单定版 Roll→Cutter、
整数标度与合并密度、Perform rebase 白名单、表面布局）；`pattern_launch`
定为引用槽位 index；重设计规格 §7 勘误同 Task 落笔。2026-08-31 Contract
修复评审——#488 逐项确认 P10-D18–D25：Pattern 槽权威、耐久 draft、完整
Facade 操作面、Core 时间/合并/边界权威、owner-loss 闭合与两阶段 rebase。
2026-09-01 Replay/Lineage 修复评审——
[`2026-09-01-lmdj-stage10-replay-lineage-contract-design.md`](2026-09-01-lmdj-stage10-replay-lineage-contract-design.md)
锁定 Project v4 Lineage、begin-time recording revision、不可变 replay
projection/controller 及 reset-pending 协议；prerequisite #516 先于 #431。
2026-09-01 Host Runtime/Session 修复评审——
[`2026-09-01-lmdj-stage10-host-runtime-session-design.md`](2026-09-01-lmdj-stage10-host-runtime-session-design.md)
以 HRS-D1–D11 锁定 Core runtime 权威实现、headless transport 边界泛化、
跨进程 flush 身份、`recovery.list` 只读化、CLI session 模式与 Native
adapter；prerequisites #523/#524/#525 先于 Task 6（#432）。
2026-09-04 Creator master-tap/Project projection 修复评审——
[`2026-09-04-lmdj-stage10-creator-master-tap-projection-repair-design.md`](2026-09-04-lmdj-stage10-creator-master-tap-projection-repair-design.md)
以 CMTP-D1–D5 锁定 Web Runtime 对实际 master-bus tap 音频图的所有权、
Web-only typed capture lifecycle、future-candidate identity gate，以及 Creator 对
v3/v4 `pattern_slots` 的唯一严格 ProjectView 投影。该修复是 #435 的实现前置；
禁止用静音 tap、本地 slot cache 或测试后门替代。

状态：**已批准，2026-09-04 修复后重新确认**——2026-08-28/29 brainstorming
评审逐节批准，P10-D18–D25 由 2026-08-31 #488 逐项确认并固化到第六个决策文件，
Replay/Lineage 与 Host runtime/session 边界由 2026-09-01 两份修复 spec 确认。
Creator master-tap/Project projection 边界由 2026-09-04 CMTP 修复 spec 确认。
本文定义 Stage 10 Perform 的产品与 Contract 边界，不分配 Product Build，
不改产品代码。

已解决的关联问题：
[#383](https://github.com/endaye/lmdj/issues/383)
[#384](https://github.com/endaye/lmdj/issues/384)
[#385](https://github.com/endaye/lmdj/issues/385)
[#386](https://github.com/endaye/lmdj/issues/386)
[#387](https://github.com/endaye/lmdj/issues/387)
[#488](https://github.com/endaye/lmdj/issues/488)

## 1. 结论

Stage 10 把已经能录 Sequence 的乐器变成能**演出**的乐器：在 Perform 表面上
现场演奏 Pad、按音乐边界切换 Pattern、瞬时切换 Bank、以连续滑条手势施加
瞬时 FX，并把整场演出记录为「事件流 + 母线 WAV」双轨的 Performance——
事件流可按当前 Project 回放，WAV 是演出的冻结版本与 Resample 素材。

Stage 10 的成功命题是：

> 用户可以在不绕过 Application Facade、不产生第二份 Pattern 真相、不打断
> 实时渲染的前提下，现场演出一段 Beat，事后完整回放它，并把它（或其中一段）
> 变成新的 Pad 声音。

新内核规格 §7 是范围权威。Stage 9 交付的三块地基——整数有理数传输时钟
（SR-D25）、音乐边界提交的 selection request（SR-D11/D23）、Project 级
录音会话机制（SR-D20–D22）——Stage 10 全部复用而非平行发明。

Koala 官方手册（§2/§4/§5/§6/§9，2026-08-28 核对）是产品对照权威：Perform
FX 是作用于全混音的连续滑条、HOLD 是全局按钮、Record a Song 绑定
transport、resample 是含 live FX 的现场捕获、Bank 是即时视图切签。

## 2. 继承的既定约束（不需要重新评审）

| 来源 | 约束 |
| --- | --- |
| 新内核规格 §7 | 八种首版 FX 名单（2026-08-29 勘误后含 Cutter）；`Hold` 显式状态；Resample 闭环 `Sound → Pad → Pattern → Performance → New Sound`。 |
| 新内核规格 §8 | Performances 是用户可见 Beat Project 的一部分。 |
| 新内核规格 §6.3 | Pattern 切换在 Beat / Bar / Pattern End，默认下一 Bar。 |
| 新内核规格 §6.6 | Pattern 事件引用 Pad Slot（Bank + Pad 位置）；冻结声音属于 Resample。 |
| 新内核规格 §12.1 | `ResamplePerformance` 是 Facade Command，原子并带 Expected Project Revision。 |
| SR-D25 | 整数有理数传输时钟是权威；Performance Events 时间戳禁止浮点。 |
| SR-D11 / SR-D23 | 音乐边界提交的 selection request 与「禁止记录点和生效点分离」。 |
| 2026-08-24 斜坡决策 | 渲染路径零分配 / 零锁 / `noexcept`。 |
| 2026-08-26 D1 + 2026-08-28 记账修正案 | ingest（Host 层）/ prepared（Core 层）两层素材模型；Bank/Project/驻留三个命名量（`maximum_user_bank_bytes` / `maximum_generation_bytes` / `maximum_resident_bytes`）；选区 commit 与 Capture/导入同路径。 |
| 2026-08-26 D2 | time-stretch / pitch 永不进实时引擎（与 Stage 10 引入 FX DSP 并存，互不推翻）。 |
| CLAUDE.md 不变量 | Host 只用 Facade；Runtime Snapshot 永不持久化为 Project Truth；Provider 失败属 Attempt 状态。 |

## 3. 已解决的问题绑定

| ID | Issue | 决策文件 |
| --- | --- | --- |
| P10-Q1 | #383 | [`2026-08-28-perform-momentary-fx-transient-gestures.md`](../../prd/decisions/2026-08-28-perform-momentary-fx-transient-gestures.md) |
| P10-Q2 | #384 | [`2026-08-28-perform-performance-object-v4.md`](../../prd/decisions/2026-08-28-perform-performance-object-v4.md) |
| P10-Q3 | #385 | [`2026-08-28-perform-resample-live-capture.md`](../../prd/decisions/2026-08-28-perform-resample-live-capture.md) |
| P10-Q4 | #386 | [`2026-08-28-perform-bank-switch-view-state.md`](../../prd/decisions/2026-08-28-perform-bank-switch-view-state.md) |
| P10-Q5 | #387 | [`2026-08-28-perform-stereo-wav-host-streaming.md`](../../prd/decisions/2026-08-28-perform-stereo-wav-host-streaming.md) |
| P10-Q6 | #488 | [`2026-08-31-stage10-performance-contract-repair.md`](../../prd/decisions/2026-08-31-stage10-performance-contract-repair.md) |

决策文件是产品权威；本文与其冲突处以决策文件为准并回评审勘误。

## 4. Approved Decisions

| ID | 决策 | 依据 |
| --- | --- | --- |
| P10-D1 | Stage 10 启用 Mode Rail 的 Perform 模式，继承 Stage 7 Creator Shell 与完整 4×4 Pad 平面；Sample / Sequence 行为不变。 | 规格 §4 |
| P10-D2 | Pattern Launch 复用 SR-D11/D23 selection request：默认下一 Bar 生效，生效前仍听旧 Pattern。首版仅暴露 Bar 边界；Beat / Pattern End 保留给后续（Koala SEQ SNAP 有 OFF/BEAT/BAR/SEQ END 四档，LMDJ 首版收缩）。 | 规格 §6.3；#376 机制 |
| P10-D3 | Perform 演奏与 Launch 的对象就是同一批 16 个 Pattern 槽与 64 个 Pad；不创建「演出版 Pattern」副本。 | 单一 Project Truth |
| P10-D4 | Bank 切换是瞬时 Host/Runtime 视图状态：不进 Project Truth、不走音乐边界、不记录事件（slot 自描述）；四个 user Bank 维持单代全驻留（与 2026-08-28 记账修正案 A1 一致：一个 generation 物化全部 64 Pad）。 | #386 决策 |
| P10-D5 | 八种 FX 是母线级瞬时状态，Project Truth 零 FX 配置。每个 FX 是连续滑条：手势事件为 `engage/move/release` 带整数量化参数值，时间戳取整数 tick 时钟 admission 读数；节拍锁定类按拍分段解释，双向类以带符号中点偏移编码。 | #383 决策 1/2 |
| P10-D6 | HOLD 是一颗全局显式模式按钮：开启时松手的 FX 冻结当前值，关闭时全部释放；事件为全局 `hold_on`/`hold_off`。无逐 FX latch，无长按计时。 | #383 决策 3 |
| P10-D7 | 八 FX 以 Contract 钉死的固定顺序串联；全部可同时激活；DSP 状态与缓冲在 Snapshot/引擎准备阶段预分配，`render` 保持零分配零锁 `noexcept`；CPU 预算按八效全开取最坏情形。live 与 Replay 跑同一段 DSP，给定相同 Snapshot、事件流与链序输出样本级一致。 | #383 决策 4/5 |
| P10-D8 | Performance 是 `lmdj.project.v4` 的命名事件流对象（Pad 击打、Pattern Launch at effective tick、FX 手势与全局 HOLD；无 Bank 事件），并引用录音 Artifact；`recording_revision` 固定为 record.begin 输入 revision。v3→v4 总迁移，旧 Project 得空 `performances`，既有 Asset 得 `lineage: null`。 | #384 决策 1/2/3；2026-09-01 Replay/Lineage 修复 |
| P10-D9 | Performance 录制会话按 session kind 泛化 Stage 9 机制（writer-lease admission、耐久 journal 链、幂等 flush、封存、指纹门控恢复）；一个 Project 同时至多一个录制会话——Perform 与 Sequence 录制互斥，后到 begin 返回 `INVALID_ARGUMENT`。 | #384 决策 4 |
| P10-D10 | Replay 是只读回放，按**当前** Project 状态重放（Sampler 惯例，SR-D4 延伸）：换采样出新声音、被删/空槽的 Launch 该段落空并非致命提示。Replay 不做指纹门控；指纹门控只在写回真相的恢复路径。冻结版本由 WAV 承担。 | #384 决策 5 |
| P10-D11 | ResamplePerformance v1 = 现场捕获：在演出录音 Artifact 上选区，经 D1 长源路径 commit（同配额判定、同 `BANK_QUOTA_EXHAUSTED`、同 revision 绑定），Project Asset Lineage 记源哈希+半开 frame 范围+Performance 身份+录制 revision；无新 Job 类别。离线重渲染立为具名后续能力，届时也永不进实时引擎。 | #385 决策；2026-09-01 Replay/Lineage 修复 |
| P10-D12 | Stereo WAV 录制是 Host 层母线 tap（镜像 Stage 8B worklet 的 4,800-frame 批量模式，走 JS 堆）流式写 OPFS，PCM16 48 kHz stereo；录制待命后由 PLAY 启动、停播即停录、停录后显式命名保存或丢弃。Host manifest `resource_limits.perform_recording_frames = 86400000`，即单次最多 30 分钟；`resource_limits.perform_recording_queue_batches = 32`，即最多积压 153,600 frames / 3.2 秒 / 1,228,800 bytes 的 Float32 stereo 数据。达到时长上限、队列第 33 批到达、写手出错或 OPFS 失败时，按 SR-D17 先例封存最后已耐久帧形成的合法 WAV、丢弃未耐久 tail、显示可操作错误；tap 永不等待写手且永不阻塞或反向通知 `render`。30 分钟的 PCM payload 是 345,600,000 bytes，标准 44-byte RIFF/WAV 文件上限是 345,600,044 bytes。 | #387 决策；#426 plan refresh |
| P10-D13 | CLI、MCP、Native、Web Runtime、Creator 通过同一 Facade 表面暴露 Perform 语义；无 UI 的 Host 能完整驱动录制、回放与 Resample commit（Web 的 WAV tap 除外，属 Host 层能力）。 | 规格 §10.2；2026-09-01 Host Runtime/Session 修复 |
| P10-D14 | **FX 名单定版（2026-08-29 评审，2026-08-30 口径澄清）**：Filter（中点双向 HP/LP 共振）、Delay（节拍同步立体声，Koala TEMPO DELAY 行为对位）、Reverb、Stutter（节拍同步 beat repeat，½–1/64 bar）、Gate（阈值门）、Reverse、Crush（降采样 bitcrush）、**Cutter**（原 Roll 更名，节拍同步静音门，1–1/64 bar，Koala CUTTER 行为对位）。Koala 手册 §9.1 只提供产品行为与方向，不公开 DSP 系数或算法；首版实现因此是满足本 Contract、可测试且确定性的 **LMDJ reference DSP**，不宣称复制或等同 Koala 的专有声音算法。DUB 式长反馈 delay 留作后续 FX 扩展。 | 2026-08-29 评审；#426 plan refresh |
| P10-D15 | **值标度与密度（2026-08-29 评审，2026-08-31 权威修复）**：FX 参数值为整数 0–1000，双向类以 500 为中点、带符号偏移解释。`move` 在 Core admission 记录；同值去重与每 FX 每 128-frame quantum 最多一条的 last-write-wins 合并均由 Core 执行，Host 不决定事件取舍。 | 2026-08-29 评审；#488 决策 6 |
| P10-D16 | **Perform rebase 白名单（2026-08-29 评审）**：Perform 会话的选择性 rebase 白名单 = {BPM、Quantize/Swing}。BPM 同 SR-D14（已记 tick 不动）；Quantize/Swing 可 rebase 但对 Perform 事件**零语义作用**——演出记录原始 timing，不吸格、不烘焙。武装 Pad capture 提交在 v1 Perform 白名单中**排除**，按 Sample 类处理（Command 失败、录制继续、不封存，Host 须先停录）；未知 Authoring Command fail closed。 | 2026-08-29 评审 |
| P10-D17 | **表面布局（2026-08-29 评审）**：中部 Surface 自上而下 = Pattern Launch 槽条（16 槽，含 pending 切换指示）→ 八根竖向 FX 滑条（视觉顺序即 Contract 链序，左→右）→ HOLD 按钮在 FX 区底部（Koala 同位）。WAV 录制状态与停录命名入口在顶部 transport；底部 4×4 Pad 平面不变。像素级细节归实施评审。 | 2026-08-29 评审 |
| P10-D18 | **Pattern 槽权威**：Project v4 持久化恰好 16 个有序 nullable `pattern_slots`；占用项保存存在且唯一的 PatternId。v3→v4 初始化全空；assign/clear/move 是 revision-bearing Command。Performance Launch 只记录 slot，Replay 从开始时固定的当前 revision 解析。 | #488 决策 1 |
| P10-D19 | **耐久 draft 生命周期**：`record.begin` 在同一 writer lease 原子创建 Untitled Performance 与 active Journal；flush 写回 draft；stop 只封存 session；save 原子消费 tail、名称与可选 WAV；discard 删除 draft/Journal。恢复始终指向 draft fingerprint。 | #488 决策 2 |
| P10-D20 | **完整 Facade 操作面**：list/inspect、record begin/event/launch-request/flush/stop/status、save/discard、recovery list/apply/discard、rename/delete/recording.bind、replay begin/stop/status、resample.commit 均使用固定名称和严格 request shape；无 `performance.replay.*` 通配符。 | #488 决策 6/8 |
| P10-D21 | **Core 输入权威**：raw Pad/FX/HOLD 输入带稳定 event/gesture ID，但 Host 不提供 tick、runtime frame 或 input sequence；Core admission 分配时间与顺序。开放 Pad 在 owner loss 时以最少 1 tick 耐久闭合。 | #488 决策 7；2026-09-01 修复 HRS-D1（权威实现是 Core 交付物） |
| P10-D22 | **Launch acknowledgement**：Host 只提交 slot。Core 预约下一 Bar；只有 Audio Runtime 实际边界 ack 后才记录 effective tick。未 claim 可由最新请求覆盖，已 claim 后来请求顺延；失败、取消或 owner loss 不产生 ghost event。 | #488 决策 3；2026-09-01 修复 HRS-D2（边界权威泛化为已安装 Core Runtime transport） |
| P10-D23 | **FX 合并与 owner loss**：Core 每 FX/quantum last-write-wins；release 先排 pending move；owner loss 按链序补 release，必要时再补 hold_off；Replay 结束/中止无条件 reset neutral。 | #488 决策 5 |
| P10-D24 | **两阶段 Performance rebase**：白名单命令在同一 writer lease 下先写 `rebase_prepare`，Project receipt 可见后写 `rebase_complete`。中间失败进入 recovery-required 并阻止新输入；精确重试只对账补全，不重复 Project mutation。 | #488 决策 4 |
| P10-D25 | **Mutation/Artifact/response 纪律**：外部 Project mutation 带 command ID 与 expected revision；session flush 的 revision 只来自 Journal。WAV 绑定只接受 Project 管理存储中经 digest/length 验证的 `audio/wav` ArtifactRef。所有 mutation/event/launch/status/recovery/replay 返回固定字段。 | #488 决策 8 |

## 5. 设计评审裁决记录（2026-08-29）

原「待 spec 评审事项」五项全部裁决：

1. Roll 更名 Cutter、Delay 取节拍同步 → P10-D14（规格 §7 勘误同 Task）。
2. 整数标度 0–1000 与 quantum 级合并密度 → P10-D15。
3. rebase 白名单适用性与武装 capture 排除 → P10-D16。
4. 表面布局要素与相对位置 → P10-D17。
5. `pattern_launch` 引用**槽位 index（0–15）**而非 `pattern_id`：Replay 启动
   当下占据该槽的 Pattern，与 P10-D10、Koala 槽位模型、SR-D4 惯例自洽；
   空槽 Launch 落空静默（非致命）。Stage 9 切换 journal 内部使用
   `PatternId` 属恢复写回路径，用途不同，不冲突。

### 2026-08-31 Contract 修复评审

Task 4 开工门发现「事件引用 slot、Project 却没有 slot mapping」以及 Performance
生命周期、rebase、时间注入与 API 形状仍需实现者猜测。#488 按一个问题一次确认
的方式裁决了八项修复，完整权威见
[`2026-08-31-stage10-performance-contract-repair.md`](../../prd/decisions/2026-08-31-stage10-performance-contract-repair.md)。
本修订以 P10-D18–D25 收录全部裁决，并把实现拆成 #498 Pattern-slot Contract、
#499 Performance lifecycle/rebase 两个独立前置 Task；#430 必须等待两者合入。

## 6. 身份与数据

持久化（Project Truth，v4）：

- `pattern_slots`：恰好 16 个有序 nullable `PatternId`；非空 ID 必须存在于
  `patterns` 且在槽数组中唯一。迁移自 v3 时 16 项全部为 `null`。
- Performance：id、名称、创建时 BPM 锚点、事件流、录音 Artifact 引用
  （可空：允许只录事件不开 WAV，或 WAV 被封存后丢弃）。
- 事件：`pad_hit {slot, onset_tick, duration_tick, velocity}`、
  `pattern_launch {pattern_slot(0–15), effective_tick}`、
  `fx_engage/fx_move {fx, value(0–1000), tick}`、`fx_release {fx, tick}`、
  `hold_on/hold_off {tick}`。
- 引用一律指向 Slot（Pad Slot 或 Pattern 槽位），不指向 Asset 或
  `pattern_id`（§6.6 口径与 P10-D10/§5.5 裁决）。
- raw press/release、event/gesture ID、pending Launch 与 rebase intent 只在 Journal
  中耐久，不进入 Project Performance；只有 canonical 事件经 flush/save 写入。
- `move` 事件经 Core 同值去重与 quantum 级合并（P10-D15/P10-D23）后进
  journal 与 flush。

持久化（Artifact，非 Project 字段）：

- 演出 WAV：不可变、内容哈希；绑定只接受 Project 管理存储中重新验证过
  sha256/byte_length 的 `audio/wav` ArtifactRef。Resample 派生 Asset 记 Lineage
  （源哈希、范围、Performance 身份、录制时 revision）。

不持久化到 Project：

- 当前 Bank 视图、FX 触点瞬时状态、全局 HOLD 的当下开关、录制会话、
  journal、未确认恢复件、任何 Runtime Snapshot 派生物。

## 7. 会话与数据流

```text
record.begin(command/session/performance identity, expected revision)
  → 同一 writer lease 创建 Untitled draft + active Journal
  → Project Revision + receipt

raw 演奏输入（Pad / Launch request / FX 手势 / HOLD；无 Host 时间戳）
  → Facade/Core admission（权威 tick + input sequence）
  → gesture/launch 状态机与 Core quantum 合并
  → Performance Journal（开放手势、pending request、canonical tail 均耐久）
  → manifest-backed flush（Journal 自带 expected revision）
  → draft Performance + Project Revision + receipt

record.stop
  → stopped Journal（Project 不变）
  → save：原子消费 tail + final name + optional verified WAV ArtifactRef
     或 discard：删除 draft + Journal

并行（WAV 录制开启时，Host 层）：
Web Runtime 在同一 suspended `AudioContext` 内建立并拥有
render stereo output → transparent Worklet tap → destination；tap 将 4,800-frame
Float32 stereo 批次单向交给 Creator 有界队列 → OPFS 流式写手。Creator 只持有
CMTP-D2 类型化 capture lifecycle，不获得裸 engine node 或 AudioContext。
```

Host 不提供 `tick`、`runtime_frame` 或 `input_sequence`。raw event 通过稳定
`event_id` 幂等，press/release 通过 `gesture_id` 配对；这些 ID 均不进入 Project。
Pattern Launch request 只有在 Audio Runtime 对预约 Bar 做实际 ack 后才转成
canonical event。stop 本身不 flush；save 才原子消费 stopped tail。

Facade 的精确操作名、request/response 字段以 P10-D20/P10-D25 和第六个决策
文件 §8 为唯一权威。`performance.replay.*`、`performance.record.*` 之类通配
写法不能出现在实现或测试清单中。

## 8. 并发分类

- Perform 录制会话沿用 Stage 9 分类框架，白名单按 P10-D16：BPM 与
  Quantize/Swing 可 rebase（后者零语义作用）；Sample 类 Command（含武装
  Pad capture 提交）在 Perform 录制中失败但录制继续、不封存；未知
  Authoring Command fail closed。
- 白名单 mutation 在同一 writer lease 下先写带命令指纹与 from/to revision 的
  `rebase_prepare`，Project receipt 可见后写 `rebase_complete`。Project 已保存
  但 completion 失败时进入 `recovery_required`，拒绝新 event/flush；精确重试
  只补 completion，不能重复 mutation。
- Perform 录制 vs Sequence 录制：互斥（P10-D9）。
- 录制中的 Pattern Launch 既是被记录的事件也是真实 Runtime 切换，共享同一
  effective boundary（SR-D23 的 Perform 版）；未实际 ack 的请求不写事件。
- FX/Pad raw 手势不占 Project revision；开放 Pad/FX 与 HOLD 在 owner loss 时按
  P10-D21/P10-D23 的确定性顺序闭合后封存。
- Bank 切换不进 admission（纯视图，P10-D4）。

## 9. Contract 影响

- `lmdj.project.v4`（major）：新增 `pattern_slots`、`performances` 与事件词汇；
  v3→v4 确定性总迁移同时得到 16 个空 Pattern 槽与空 Performances；跨语言
  golden vectors 覆盖迁移、引用完整性与事件不变量。
- FX 链序、0–1000 标度、事件边界与合并规则是 Contract 不变量，须有跨语言
  测试向量。
- Pattern-slot assign/clear/move 与完整 Performance Facade 操作名/严格 JSON
  request/response shape 是 Application Facade public contract；CLI、MCP、Native、
  Web 与 Creator 只能一一转发，不能扩展 Host-only 语义。
- 无 Project 级 FX 配置字段；`lmdj.patch.v1` / `lmdj.materials.v1` 仍禁止
  复活。

## 10. 测试清单（实施计划再展开为逐条 RED-GREEN）

1. v3→v4 迁移得到 16 个空 `pattern_slots` 与空 `performances`；错误长度、重复
   PatternId、悬空 PatternId 均被 schema/domain gate 拒绝。
2. assign/clear/move 的成功、前置失败、revision、receipt replay 与 collision
   各有跨语言/Project Store witness。
3. Perform 模式启用且 Sample/Sequence 回归不变。
4. `record.begin` 从崩溃矩阵每一点恢复为「draft + Journal 都存在」或完全无效，
   不出现孤儿 draft；Perform/Sequence 第二 begin 为 `INVALID_ARGUMENT`。
5. raw event 拒绝 Host tick/frame/sequence；event ID 幂等，gesture ID 配对；
   owner loss 把开放 Pad 以至少 1 tick 闭合。
6. Pattern Launch 默认下一 Bar；未 claim latest-wins，已 claim 后来请求顺延；
   只有实际 ack 写 effective tick；失败/取消/owner loss 无 ghost event。
7. Bank 切换瞬时、无准备延迟、无 glitch、不占 revision、不产生事件。
8. 每种 FX（含 Cutter）可闻、release 还原；Core 同值去重与每 FX/quantum
   last-write-wins；release 排 pending move；Host 不做语义合并。
9. 全局 HOLD 冻结最终值；owner loss 按链序 release 后 hold_off；Replay
   结束/中止 neutral reset；同 Snapshot + 同 canonical stream 样本级一致。
10. 八效全开 CPU/underrun stress 与 render 零分配/零锁/`noexcept` 守卫。
11. Performance flush 幂等：重复 command ID 返回原 receipt；stop 不改 Project；
    save 原子消费 tail/name/optional WAV；discard 删除 draft/Journal。
12. recovery apply/discard 的完整 far-side witness；fingerprint 不匹配保留恢复件；
    rename/delete/bind 在 active/recovery Journal 存在时 fail closed。
13. BPM、Quantize、Swing 在每个 `prepare → Project receipt → complete` 故障点
    可恢复；可见 receipt 不会重复 mutation；recovery-required 阻止新输入。
14. Sample 类命令失败但录制继续；未知 Authoring Command fail closed。
15. 所有 P10-D20 操作逐一验证 kind、exact keys、缺字段、额外字段、范围、返回
    字段；CLI/MCP/Native/Web schemas 与 Facade 一一同构。
16. Replay 固定 begin 时的当前 revision：换采样出新声音；移动 Pattern 后跟
    当前槽；空槽静默 gap；中途 Project 变更不改变本次 resolved revision。
17. WAV Artifact 绑定拒绝路径、raw bytes、缺失/错误 digest 或 length；相同
    ref 幂等，冲突 ref fail closed。
18. WAV 长录制流式落 OPFS；0/上限/上限+1、队列第 33 批、writer/OPFS 失败均
    封存合法耐久前缀，render 不等待。
19. Resample 录音选区经 D1 commit；Lineage 完整；取消/失败/配额耗尽不改
    Project、Asset、Pad 或 revision。
20. CLI/MCP 黑盒完成 begin→raw events→ack launch→flush→stop→save→replay→
    resample，并另走 owner-loss→recovery apply/discard 与 WAV delayed bind。
21. Creator Browser 旅程完整覆盖 Pad/Launch/FX/HOLD/Bank/stop/save/replay/
    resample；OPFS 持续写物理 fixture 覆盖 macOS Safari 与实体 iPadOS。

## 11. Version Management

Version impact: none（本文与其引用的六个决策文件均为纯文档权威；本修订不
触碰任何 Contract 工件）。实施时支付在 Stage 10 实施计划
的 `## Version Management` 精确分配：预计含 `lmdj.project.v4`（Contract
major）、audio-runtime（FX DSP）、authoring-domain / project-io /
project-cooker / application-facade / web-runtime-platform 及各 Host 的
SemVer 级联、`resource_limits` 新键（manifest 级，触发 Product Build 与
Portal 快照义务）、新 Product Build。

## 12. Documentation Impact

本批准修订合入：Documentation impact: none（不改 Portal current 页与活动
manifest；这是尚未集成能力的设计权威修复）。实施：required——Perform 相关
Portal current 页与源图在实施 Task 内更新；manifest / Product Build 变更
必须做 immutable snapshot。

## 13. 拒绝的替代

### 13.1 为 Perform 建平行的「演出 Pattern」副本

违反单一 Project Truth；Koala 也是演同一批 Sequence。

### 13.2 FX 建模为开关 + 回放时重算

Koala 的 FX 是连续滑条，开关模型无法还原演出；回放时重算与 SR-D27 同款
教训，破坏确定性。作用点在渲染，不在事件改写。

### 13.3 逐 FX latch 或长按计时阈值的 Hold

Koala 的 HOLD 是全局按钮；逐 FX latch 与计时阈值在触屏与 MIDI 上不可预测
且不可测试。

### 13.4 Replay 做指纹门控或引用 pattern_id

把「换个采样/挪个槽」变成整场演出不可回放，违背 Sampler 惯例（SR-D4）；
冻结需求由 WAV 承担。门控只留给写回真相的恢复路径。

### 13.5 第二套 Performance 专用时钟或浮点时间戳

SR-D25 已裁决整数时钟唯一权威。

### 13.6 录制 WAV 全量驻留内存再一次性写盘

512 MiB 固定堆下数分钟录制必然越界。必须流式（P10-D12）。

### 13.7 引擎级音频 capture ring（v1）

改实时代码、需 stress 层验证、扩大 Stage 10 范围；Host 层 tap 复用 Stage
8B 已交付模式即可。Native Host 到来时再评估统一 ring 的价值。

### 13.8 离线重渲染作为 v1 Resample 权威

使八 FX 离线复现成为硬前置、范围翻倍；Koala 的 resample 本就是现场捕获。

### 13.9 保留 Roll 名字或另行发明 Roll DSP

名字不变但用 CUTTER 语义会造成永久的文档-对照错位。首版采用经 Contract
钉死、可自动验证的 LMDJ reference DSP，并以 Koala 手册描述的产品行为作为
方向对照；不声称复刻手册未公开的系数、算法或专有声音身份（P10-D14）。

### 13.10 Performance 事件受 Quantize 吸格

演出的身份是真实手感；吸格烘焙与「WAV 录的就是听到的」相悖（P10-D16）。

### 13.11 让 Host 提供时间戳、排序或 FX 合并结果

不同 Host 的 callback、MIDI 与 pointer 调度不同，结果会生成不同 Performance。
Host 只能提交 raw identity/value；Core admission 是唯一时间、顺序和取舍权威。

### 13.12 stop 隐式 flush，或直到 save 才创建 Performance

前者使声明为非 Project mutation 的 stop 暗中消费 revision；后者使成功 flush
没有 Project Truth。耐久 draft + stopped tail + explicit save/discard 同时保留
receipt、恢复和用户生命周期的可证明边界。

### 13.13 Project mutation 后才写单条 rebase 记录

进程若在 manifest publication 与 Journal append 之间崩溃，Journal 无法证明
哪个命令推进了 revision。两阶段 prepare/complete 与 stable command receipt
是唯一可无重复 mutation 对账的方案。

### 13.14 Pattern Launch 槽只存在于 Host 或 Runtime Snapshot

Performance 记录 slot 且 Replay 按当前 Project 解析；若 Project Truth 没有槽
mapping，Host 就会成为第二份 Pattern 真相，迁移、移动槽与无 UI Host 都无法
得到同一结果。

## 14. 实施入口（前置条件）

原始 Task 1–3 已分别由 PR #445、#484、#485 合入；Task 4 start gate 随后发现
#488 所列 Contract 缺口，因此 Task 4 暂停。**恢复实现**必须依次满足：

1. #488 的本 spec/plan 修复合入并通过 docs/static/Portal gate；
2. #498 Pattern-slot Contract 与 #499 Performance lifecycle/rebase 各以独立
   Task/PR 合入并接受；两者可在 #488 后并行，但 #430 同时依赖二者；
3. #430 只能实现本 spec 锁定的操作名与形状，不得再次在代码中补设计。

历史上，**撰写**实施计划只需原前置 2、3、5；Task 1 起的原始实现与版本锁定
还需原前置 1 与 4。
（2026-08-29 勘误：原文把撰写与动工绑为同一道门，使设计定稿后计划无法起草；
版本分配对 remediation 的真实依赖记在
[实施计划](../plans/2026-08-29-lmdj-stage10-perform.md)的
`## Version Management`，由一个具名的 plan-refresh Task 承担。）

前置条件全集：

1. Stage 9 remediation 关闭：#371（伞）、#372–#376，及 #379/#380 的版本
   整合与快照——评审已裁定修复前 1.0.37.0 不得越过 canary。**门禁动工与
   版本锁定，不门禁撰写。**
2. ~~P10-Q1–Q5 决策文件合入~~——已于 2026-08-28 完成（见 §3）。
3. ~~本文 brainstorming 评审逐节批准~~——已于 2026-08-29 完成（见 §5）。
4. 实施回归每 Task 一个 PR 的模型（Stage 9 评审的流程结论）。
5. ~~#357 的记账决策合入且与 P10-D4 一致~~——已于 2026-08-28 完成
   （PR #389，修正案 A1「一个 generation 物化全部 64 Pad」与 P10-D4
   一致；实施计划采用 A1 定死的 `RuntimePreparationLimits` 字段名）。
6. ~~#488 Contract 修复逐项批准~~——已于 2026-08-31 完成产品裁决；以本
   文档、实施计划和第六个决策文件合入为实现恢复 gate。
7. **Task 9 新前置（2026-09-04）**：CMTP Task 8A 先交付 Web Runtime
   master-tap graph 与 typed capture lifecycle；#435 同时扩大 Project projection
   文件边界并只从严格 v3/v4 `ProjectView.patternSlots` 读取槽位。Task 10 才把
   resource keys、tap asset role 与 `1.0.42.0` active identity 一次性集成。
