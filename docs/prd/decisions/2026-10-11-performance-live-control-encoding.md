# 技术提案：Performance 实时控制的初始状态、顺序与确认边界

- 日期：2026-10-11
- 状态：D0 技术设计 review 完成；Root 已通读完整三文档，独立复核确认 R1–R6 的设计处置。产品约束沿用既有 owner 决定，尾音仍 pending；实施与运行验收未完成。
- 产品依据：[D04 实时控制决定](2026-10-10-mixer-live-controls-and-meter.md)。
- 实施拆分：[producer／consumer 计划](../../plans/2026-10-11-performance-live-control-producers.md)。
- 复查 base：`4a2b26f03a1e628882e907c92a9b9411b48e110d`。
- 尚待 owner 回答：Mute 的共享效果尾音语义，见下文；M1 不得先行实现。

## 已批准的产品约束

独立滤波为 LP／HP／BP、Cutoff 20 Hz–20 kHz 对数调节、Resonance 0–100%；
初始 OFF、LP、20 kHz、0%。进入 FILTER 组不改声，停转／切组保持，
离 Perform 按已有 HOLD 释放。主组和 FILTER 组共用 Cutoff，ENC4 始终监听。
这三个参数完整随 Performance 录制／重放，不写工程或 Pad 的音色 Truth。

实时 Mute／Solo 覆盖 A01–D16，多个 Solo、Mute 优先；Bank／Pattern 切换保持，
离 Perform／换工程清空，HOLD 不保留 Pad 门控。它不修改 `playback.muted`。
录制必须包含起点状态及后续变化；重放第一个同 tick Pad 发声前必须已恢复起点。
后者是已批准录制起点要求的实现不变量，不另作一次产品问答。

MASTER、meter、400 ms authoring 提交、其他页方向键、Numeric 和键盘映射各属
其他 Task。本提案不扩展这些 Task，也不把静态审计当作 DSP／听感／设备验收。

## 当前实现及需要保留的兼容性

当前 `PerformanceEventKind`／variant 只有 0–6：PadHit、PatternLaunch、
FxEngage、FxMove、FxRelease、HoldOn、HoldOff。`canonical_performance_events`
按 `(tick, kind ordinal, fx-or-slot)` 稳定排序；既有测试明确锁定 0–6。
`lmdj.project.v5` 当前 schema Contract SemVer 为 **5.3.0**，Performance
reader、schema、checkpoint 都是闭合字段集，尚无初始实时状态。

旧 Filter 的 0–1000 值保留旧意义：500 bypass，其余值联合控制 LP／HP 深度。
`MasterFxChain::process_filter`、旧波形向量和旧事件必须保持原算法，不能把这个值
翻译成独立 Cutoff 或 Resonance，也不能让旧 `fx.filter` 事件变成 BP。
现有 listener monitor producer、旧 FX／HOLD admission 和实际 dequeue reset ACK
都是正向控制，不能因为没有新字段而重写它们。

## 建议采用 optional header 和两种录音 profile

在 Performance 上新增可选 `initial_live_state`。没有 header 的旧 Performance
继续用旧 profile：字段集、0–6、旧 canonical ordering、时间归一化、FX 算法不变。
旧 reader 遇到新语法继续拒绝，不能剥掉未知字段后播放一份变声的工程。
新 reader 必须接受所有旧有效工程；打开旧工程本身不自动改写录音或补造 header。

新录音保存 header，使用新 profile。header 是 begin fence 捕获的 **Core 接收状态**，
不是 Creator 的本地 percentage，也不是某次 UI status 请求读到的最新状态。
它只保存控制参数／开关，不保存滤波 delay-line、共享 FX 尾音、voice cursor 或
Runtime Snapshot。原始录制 PCM 仍是 capture／resample 的音频依据。

建议 header 的闭合 shape 如下；`other_fx` 的七个键固定为现有非 Filter FX。
`engaged`／`frozen` 沿用现有语义，实际 active 为两者的 OR。

```json
{
  "initial_live_state": {
    "hold": false,
    "filter": {
      "mode": "independent",
      "engaged": false,
      "frozen": false,
      "type": "lp",
      "cutoff_hz": 20000,
      "resonance_milli": 0
    },
    "other_fx": {
      "delay":   {"engaged": false, "frozen": false, "value": 0},
      "reverb":  {"engaged": false, "frozen": false, "value": 0},
      "stutter": {"engaged": false, "frozen": false, "value": 0},
      "gate":    {"engaged": false, "frozen": false, "value": 0},
      "reverse": {"engaged": false, "frozen": false, "value": 0},
      "crush":   {"engaged": false, "frozen": false, "value": 0},
      "cutter":  {"engaged": false, "frozen": false, "value": 0}
    },
    "muted_slots": [],
    "solo_slots": []
  }
}
```

另一种 Filter shape 是 `{"mode":"legacy","engaged":false,"frozen":false,
"value":0}`，没有独立参数。两个 shape 是严格 oneOf，不混收两套参数。
非 HOLD 状态不得有 frozen；其他 FX 0–1000 与原有尺度、释放行为完全相同。
捕获其他 FX／HOLD 的七个既有状态是为了让新 profile 不再依赖 begin 后异步补发
HOLD／engage 来伪造起点；不是增加新的效果参数或改旧录音。
checkpoint 从 header 初始化 HOLD 和当前新控制状态；engaged FX 的 logical gesture 配对
由下文 Core binding／begin mapping 初始化，不能从三个参数字段猜 Host gesture ID。
不重复写起点 engage，frozen-only 不建立 open gesture。

header 在 Replay begin 的控制阶段整体恢复，实际 apply ACK 后才允许调度第一个
Pad／Pattern，包括没有事件的 Performance。零事件时也先确认 header 恢复，再按
既有 Replay complete 规则确认 neutral；不能因 event_count 为零跳过新状态清理。
旧录音的 first-event tick 归一化保持；新录音同样不由 Host 补造 leading silence。

## 新事件、单位和 same-tick 顺序

保留旧 variant ordinal 0–6，末尾追加 7 `filter_change`、8 `pad_gates_set`。
新 profile 的**所有**耐久事件，包括原有 0–6，都带 `input_sequence`；旧 profile
没有该字段，也不能含新事件。不能混合缺失／存在的序号后偷偷 fallback 到旧排序。
序号由现有 Core `PerformanceInputSequencer` 分配，Host 不传 tick、frame 或排序号。

序号为 uint64 的规范十进制字符串：`"1"` 至 `"18446744073709551615"`，不接受
正号、前导零、浮点或越界值。Core 用 uint64 运算；SDK 将其作为 opaque string。
同一 Performance 序号唯一，允许 gap：Pad release、取消的预留或其他内部 admission
不必各变成耐久事件。PadHit 使用对应 press 的序号，duration 仍由既有 release 配对；
PatternLaunch 使用原请求的序号和其真实 effective_tick。当前 source 是 launch ACK
时才 next（application.cpp:7333–7348）；P1 必须改为请求成功预留时冻结序号并耐久存入
pending launch，ACK 复用它。这是新 profile 的待实施变化，不是已有能力。
Stop／owner-loss 自动关闭多个 FX 时，Core 在同一 admission 锁下为各个新 release／
HoldOff 各 next 一次并冻结；PadHit 仍复用各自 press 序号，不能为全部 synthetic events
共用一个序号。Journal high-water 包含这些内部序号。

新 profile canonical key 为 `(event_tick, input_sequence)`。不同 tick 仍按音乐时间；
同 tick 按 Core 接收次序，不按新 kind 的 ordinal 或 Pad Slot 重排。
序号不要求在整个已排序列表中递增，因为预约未来 Pattern 的请求可能先于较早 tick
的后续控制。Journal 的 admission high-water 与时间排序分别验证，不能混为一个值。
旧 profile 原 tuple 和稳定 tie 保持，原 ordinal 测试不改。

仅加 header＋给新 kind 固定 sortRank 不足：同 tick `control(C) → Pad(P)` 必须保留
C 在 P 前，而 `Pad(P) → control(C)` 又必须保留 P 在 C 前。固定把 C 放在所有 Pad
之前或之后，总会失败一个反例；只给新 control 序号也无法和没有序号的 Pad 比较。
因此序号扩展限定于有 header 的新 profile 的所有事件，旧 kinds 的 payload 含义不变，
旧 canonical 函数继续服务 legacy profile，新 profile 在显式 profile-aware 路径排序。

分配顺序是：先验证身份/shape、查原 receipt、预留 queue cell，再由既有
`PerformanceClock::read_tick` 和 `PerformanceInputSequencer::next` 各读取一次。
Core 把此次 `(event_id, raw payload fingerprint, tick, input_sequence)` 固定为 pending
admission；它是 control-thread 接收顺序，不是 audio-applied 顺序。queue 拒绝发生在
分配前。Journal unknown 时冻结这个 tuple，同 identity exact retry/recovery 复用它，不能
再调用 next/read_tick；已接收 receipt 重放也不消耗序号。known-absent 失败取消该次
预留，允许序号成为 gap；不能把它伪装为成功事件或迫使后来音频追赶该 gap。
checkpoint 的 high-water 与下文新增 durable admission ledger 一起保存，恢复不能只扫描
最后一个 PadHit 的序号而忘记已接收的 release/预约/未知写入。现有 event_receipts 只是
内存 map；这里不能引用它为已有 durable identity。

begin/record 的既有 legacy receipt 和 fingerprint 必须按原字段读取/匹配：先查
同 command_id 的旧 receipt，才决定是否创建新 profile。不能在 exact retry 时根据
当前 DSP 状态补 header、增加新 fingerprint 字段并把旧请求判 collision。

```json
{
  "kind": "filter_change",
  "tick": 0,
  "input_sequence": "1",
  "phase": "engage",
  "type": "hp",
  "cutoff_hz": 800,
  "resonance_milli": 250
}
```

`phase` 为 engage／move／release。每次都带完整独立参数 tuple，Core 负责从单参数
intent 派生，不让 Host 的旧 projection 覆盖其他参数。engage 切到 independent
并开启；move 要求该 profile 有 matching active gesture；release 按 HOLD 冻结或
关闭，保留独立参数供 UI 读回，不能变成旧 filter 的 value=0。
旋钮第一次实际参数变化发送 engage，此后 move；停转和切组不 release。
触摸仍按既有 pointer-up／cancel／blur release。到边界而没有参数变化不自动 enable。
离页 release 亦录制，随后按既有停止流程结束录音。

Cutoff 的耐久值是整数 Hz 20–20000，Resonance 的耐久值是整数 0–1000，表示
0–100%（1000 对应 100%）。type 只收 `lp`／`hp`／`bp`；拒绝 NaN、隐式 clamp、
额外字段和百分比假装 Hz。UI 的对数位置与 SHIFT 细调先换成这些 typed 单位。
DSP 系数、Q、采样帧和滤波内部状态都不进入 Project Contract。

```json
{
  "kind": "pad_gates_set",
  "tick": 0,
  "input_sequence": "2",
  "muted_slots": [0, 63],
  "solo_slots": [8, 9]
}
```

Slot 在 wire／Project 上用升序、唯一的整数数组 0–63；拒绝重复、乱序、负数和 64。
Core 用 `uint64_t` mask、`uint64_t{1} << slot`，不能用 JS bitwise 或 Number mask。
两组允许交集；slot 0=A01、15=A16、16=B01、63=D16。每个事件保存两组完整 mask，
不是仅按钮 delta，Replay 不依赖上一次 UI 当前 Pad。

允许声音的公式为 `!truth_muted && !live_muted && (solo_mask == 0 || live_solo)`。
多个 Solo 合法；Mute 优先；Solo 不能覆盖工程本来 muted 的 Pad。
Sound Set audition 的非工程 Bank／slot=0 sentinel 不等于 A01，必须排除。使用现有
`is_audition_bank_slot` 的准确保留区间；不能用 `bank >= 0xf0`，因为 legacy 0xff
也满足该式却不是 audition。
真实 live／Pattern／Replay Pad 声部都适用；节拍器不经过此 Pad gate。

## 新 profile 保留全部控制变更，不做 FX move coalescing

直接禁用新 header profile 的 FX move coalescing，包括七个已有 FX、legacy-mode Filter
以及新的 independent Filter 完整 tuple。每个被接收且实际改变参数的 move 都保留其
真实 tick／input_sequence；不覆盖前一个 event，不使用 128-tick window/index。
相同参数的 no-op 可不产生 Project event，但仍推进 admission sequence 并保存 receipt；
release／HOLD／Pad／Pattern 不被省掉。旧 no-header profile 的原 128-tick 算法、
coalesced response 和 fingerprint 完全保持，不能用新规则重排或展开旧录音。

具体反例：Delay 初始 0 且 engaged，真实跨 quantum 接收 Move500@(16,10)、
PadPress@(32,11)、Move900@(64,12)。旧合并把500覆盖并移到tick64，Pad32失去500。
新 profile 保留两次 move，PadHit 使用 press序号11；Replay Pad32 前可观察值为500，
Pad64后为900。仅给留下的900换 sequence不能修复丢失值。owning Facade recording／
Replay oracle 同时覆盖这个反例、同tick C→P／P→C、预约 Pattern 原请求序号，
不要求参数事件重建 bit-identical 的录制 Wav。

## 单一滤波 stage 与 legacy 接管

Core 只有一个 Filter stage，mode 为 legacy 或 independent，不串联两个 Filter。
旧录音开始时明确选择 legacy neutral，再按原事件应用；不能沿用上次 independent
参数。新 header 选择其记录的 mode。新 control_epoch 初始 independent OFF；同 epoch
离页 HOLD 保留的 Filter 在再次进入 Perform 时读回，不重新初始化成 OFF。

实际 independent engage 原子切换 mode、完整参数和 active 状态，清除旧 Filter
的 engaged／frozen。相反，实际旧 `fx.filter` engage／move 接管为 legacy，沿用原
value 意义并释放 independent active 状态；旧 release 只释放其 legacy gesture，
不能拿旧 delayed release 消灭已经接管的 independent gesture。
新 typed Filter engage 返回 Core gesture generation，move/release 必须回传并匹配它；
过期 generation 明确拒绝或按既有 receipt 重放，不作新效果变更。generation 是 live
身份，耐久事件通过 profile/phase/input_sequence 的闭合配对重放，不把 runtime UUID
写入 Project Truth。Journal 中的 logical recording gesture 与 runtime generation 分开。
旧 wire 没有 generation，保留其原有 legacy 配对/排序；当当前 mode 为 independent 时
旧 release 不得改它。不能声称能识别无身份字段的任意历史 legacy release（例如旧
legacy→independent→新 legacy 后才到达）；新 Host 的 epoch/FIFO 与单 Filter owner
禁止这样混投，旧 Replay 只发自己的 legacy 流。不得为此偷偷修改旧 request fingerprint。

从 legacy 接管到 independent 时，如果 intent 仅改一个参数，其余参数从已批准
LP/20 kHz/0% 默认 tuple 开始；不使用无法从 legacy header 恢复的隐藏“上次独立值”。
有 independent 状态时则保持其余参数。legacy mode 的 status 不伪造已应用的 Hz/Q；
新界面说明当前 legacy 状态，实际新 engage 才接管。

建议 F1 使用独立的二阶 TPT SVF，LP／HP／BP 从同一 state 推导；Resonance
0–1000 暂建议映射 `Q = (1/sqrt(2)) * (10*sqrt(2))^(r/1000)`，即 0% Q≈0.707、
100% Q=10，BP 用 unity-at-center 标度。该映射是待设计 review 的 DSP 技术提案，
不是 owner 先前批准的听感曲线。只在 Core 固定 48 kHz 下计算系数；20 kHz 不偷降
UI 边界。OFF 要有 bit-identical bypass；独立 type／系数和 wet gate 的过渡建议复用
96-frame ramp，旧 legacy 没有新 gesture 时保持原 PCM。F1 必须用解析响应／固定
参考向量检验，不以两份同算法输出一致代替正确性；真实听感验收另记。

## Core admission、begin fence 与 applied ACK

复用现有 Facade control-thread `sequence_mutex`／writer admission，render 不取此锁。
一个 Engine owner 独占现有有界 master-control SPSC producer；Filter、mask、fence、
neutral 扩展这条队列，保持 1024 capacity，不新增无界队列或回调内文件 I/O。
旧 FX／HOLD 的成功 admission 也更新同一个 Core accepted shadow，才能可靠捕获
所有 header 字段。control sequence 与 recording input_sequence 是不同的 Core 概念。

新 typed command 绑定 Core 返回的 `control_epoch`：它含 Project UUID、Project open
generation 和 engine start_epoch 的身份，Host 只能回传，不能自造。重开同 UUID 也
必须换 epoch。Bank／Pattern／Truth revision 变化不换这个 epoch。
关闭／换工程／engine restart 先使旧 epoch 失效，旧 callback、receipt 或 marker
不能影响新工程。Core 的 state projection 区分 accepted state 与实际 applied sequence。

该身份由 existing EnginePerformanceAdapter/PerformanceGestureSink 的 typed retained-target
lifecycle hook 持有，P1 定义 bind/invalidate/read 边界，W1 在 ControlRuntime 当前
成功设置 `retained_project_path`/`project_id` 的 create/open/duplicate 分支绑定 Core 已
验证的 Project 身份，replacement/close 在旧 target 前先失效。`prepare_and_publish`
对同 Project 的 Bank/Pattern/新 revision 不能重新 bind；engine start_epoch 改变由 adapter
观察并换身份。status 是读操作，不能靠它隐式切工程/静音。Facade begin 的 project_path
必须经 Core load 对照这个 target UUID；Host 声明的 UUID/路径本身不是 engine 已绑定证据。
使用已有 gesture-sink wiring 加 typed hook，不另增 Product-specific wiring 或第二 adapter。

建议新 API 保持最小闭合集合：

- `performance.live.status`：返回 epoch、accepted state、accepted_control_sequence、
  applied_control_sequence、reset／begin 是否 pending；不可用不能假报 neutral。
- `performance.live.control`：携带 epoch、command_id、expected_control_sequence 和
  typed intent。intent 为单个 Filter 参数＋phase、已有 FX/HOLD、设置某 slot 的 Mute／Solo，或
  clear_pad_gates；从 Core 当前 state 原子派生完整新状态。已有录制路径复用相同
  admission kernel，并附既有 session_id／event_id，不双投 live 和 record。
- 扩展既有 `performance.record.begin`／status 和 Replay status 的 readiness：旧六字段
  begin request 继续选择旧 profile/响应/fingerprint，不强迫旧 client 认识 pending fence。
  新 SDK 在 begin 增加 `control_epoch` 回传 Core-issued 身份，选择新 profile；它不能
  提交 header。Core 验证 producer/epoch，并从自己的状态构造初始值。

新 profile 的 begin-pending/active recording 对该 epoch 的控制只有 recording route。
sessionless live.control 或旧 fx.gesture 不能绕过 Journal 改声；缺少 recording identity
明确拒绝，不为外来调用猜 event_id。旧六字段 legacy recording 保留原 admission 规则。
新 SDK 的 Delay/Reverb/其他 FX 使用下文绑定后的新 recording event 分支，避免同时投
两个 sink；“复用 operation”不等于直接沿用缺少起点 gesture binding 的旧实现。

new wire request 的最小 shape 示例（opaque 身份均由 Core/SDK 对应状态持有）：

```json
{
  "operation": "performance.live.control",
  "control_epoch": "11111111-1111-4111-8111-111111111111",
  "command_id": "22222222-2222-4222-8222-222222222222",
  "expected_control_sequence": "12",
  "intent": {
    "kind": "filter_parameter",
    "phase": "engage",
    "parameter": "cutoff_hz",
    "value": 800
  }
}
```

`filter_parameter` 只允许 type/cutoff_hz/resonance_milli 与各自 enum/整数尺度；
engage 不带 generation，move 必须增加 `gesture_generation`（Core-issued UUID）。
`filter_release` 只带 kind 和 `gesture_generation`；`pad_mute`/`pad_solo` 各只带 kind、
slot 0–63、boolean `enabled`；`clear_pad_gates` 只带 kind。
已有FX的`fx_parameter`为kind/phase/fx/value，fx是原八名枚举，value 0–1000；
其中filter明确为legacy scalar，原语义不变；新Creator参数组只用independent intent。
engage 不带 generation，move 增加 `gesture_generation`；`fx_release` 为
kind/fx/gesture_generation。HOLD intent 为单键 kind=hold_on/hold_off。全部 exact keys。
Core 将 parameter intent 派生成上文的完整耐久 tuple，把 Pad intent 派生成两组完整
arrays；不能在 Host 展开一个旧状态后覆盖别的 Pad。release 的参数值来自 Core 当前
state，不从 Host 再传一套可能不一致的值。返回 receipt 给出同 epoch、Core control
sequence、accepted/applied 以及 Core generation（适用时）；序号的 wire 类型统一 opaque
十进制 string。status/receipt 不把 runtime epoch/generation 写进 Project Truth。
control sequence/expected sequence 允许初始 `"0"`；耐久 event input_sequence 则从 1 开始。

### 已有 FX 的 Core binding 与起点 adoption（R3）

Core accepted/applied live state 对七 FX 和当前 Filter 各保存一个 runtime generation
（固定大小UUID值，不在render分配）。成功 engage 分配，matching move 保留，release
关闭它；HOLD frozen-only 继续 active，却没有 open binding。旧 sessionless FX request
的 shape/响应不改；新 adapter 在其成功 admission 时跟踪自己的 generation，旧 move
不会伪造 engaged。新 Host 转换到 typed route 前经 status 获取同 epoch 的当前 binding。
不能把 Host 本地 openFxGestures 的 g 当成 Core 曾见过的身份。

Begin 在锁下捕获 header 与所有 engaged bindings，给每个 engaged FX 创建一个新的
**logical recording gesture UUID**，耐久写入 new-profile Journal begin checkpoint。
checkpoint 的 `open_fx[].gesture_id` 保存 logical UUID，effective_value 是 fence起点值，
pending_value=null；independent Filter 另有 typed open-filter checkpoint 的logical UUID及
完整tuple：new-profile checkpoint的`open_filter`为null或闭合
`{gesture_id,type,cutoff_hz,resonance_milli}`，只在independent engaged时非null；legacy
engaged Filter仍在open_fx，不能同时有两份Filter binding。该UUID与全部open Pad/FX
logical IDs互不重复。checkpoint还保留完整current live state供durable恢复，不能只留
起点header后丢后续frozen/masks。frozen-only FX只在header/currentstate中，不能写入
open_fx/open_filter。begin新响应/status
稳定返回（按既有FX ordinal排列、最多8项）：

```json
{
  "fx_bindings": [
    {"fx":"delay","gesture_generation":"33333333-3333-4333-8333-333333333333",
     "recording_gesture_id":"44444444-4444-4444-8444-444444444444"}
  ]
}
```

SDK 消费 mapping 后将当前同 epoch/generation 的 UI gesture 重绑定到 Core logical ID；
新recording event闭合分支如下：fx_engage为kind/fx/value，**不传Host gesture_id**，
Core生成并返回mapping；fx_move为kind/fx/value/gesture_id/gesture_generation；
fx_release为kind/fx/gesture_id/gesture_generation，Core验证二者与当前mapping相等。
filter_parameter的engage为kind/phase/parameter/value，move增加gesture_id和
gesture_generation；filter_release为kind/gesture_id/gesture_generation。
Pad press/release保留原Host Pad gesture的exact keys；hold及Pad mute/solo/clear使用
前述intent keys。只有新profile选择这些分支，旧event validator不扩大。start期间排队的输入
是在dequeue时取mapping、expected序号，不提前捕获一个错误的recording ID。Host local g
只作为UI pointer/rotary token；旧 g 不被自动接纳。Core已released又re-engaged的旧
callback因generation不匹配拒绝；同generation跨begin的callback若来自仍有效同一UI
gesture可按mapping转入recording route，关页/切工程后的callback由UI token/epoch拒绝。

Record后新的 engage：Core分配runtime generation和logical recording ID，在同一durable
admission中保存open-FX checkpoint，并在receipt返回mapping；first move/release等待它。
Record Stop后SDK只保留live runtime binding，不继续使用recording logical ID。group切换
不更换binding，不发release或假engage。HOLD下release使对应logical open gesture关闭，
header/currentstate可仍frozen；继续转动需新engage，新ID且沿原有reset-effect语义。

恢复时logical UUID由Journal重建；runtime epoch/generation绝不据它复活。丢失原runtime/
lease后的new-profile reattach只提供receipt查询及现有显式recovery/finalize收尾，不自动
恢复live录制输入、re-engage或启动capture；继续演奏须在有效新epoch另开录音。原process
仍有同一pending reservation/lease的exact retry不属这种失去producer的恢复。不把recording
UUID当Project authoring参数，不把runtime UUID写Project Truth。没有header的旧recording
wire及旧payload fingerprint原样分支，不以此接管它的配对。

例子：Record前Delay engaged500，Reverb在HOLD下frozen700。begin保存两个声音状态、只
返回Delay mapping；首个Delay move600/release用mapping可配对，Reverb无openID。
begin不执行MasterFxChain::engage（现实现会reset_effect），不补FxEngage event，
不清Delay/reverb buffer。P1/C1的owning oracle必须验证声音未因起点adoption重启。

### Core fence 与 Web capture 是两个独立 ready 边界（R1）

Begin的Core控制线性化点是预留的fence发布位置，不是UI点击或response：

1. 在既有control admission锁下验证target/writer lease，预留未发布queue cell。
   queue-full不创建draft、不消耗successful admission序号、不改accepted state。
2. 捕获前序accepted shadow及bindings，耐久写immutable header、begin fingerprint与
   logical checkpoint。render不等待磁盘，不发布半个header。
3. known-success后发布fence marker；response为`pending`，不能报applied:true。
   marker只确认前序队列状态，不重复engage/reset运行中音频。
4. render到marker后保留coherent applied snapshot及(epoch,control_sequence)；Core逐字段
   对照header与bindinggeneration，且epoch仍匹配，才报`core_control_ready:true`。
   Core不启动Web tap，也不知道postMessage是否已经被worklet处理。Core拒绝尚未
   control-ready的Pad/Pattern admission；SDK还负责下一条capture-ready门。
5. SDK先等Core fence及mapping，再调用真实capture start并等待worklet ACK。
   两者且同target/begin匹配才完成begin promise、开放setup FIFO中的recorded inputs。
   整段异步期间已接收输入保序，dequeue只走recording route、各记录一次，不能当作
   起点前preview、补header或静默丢弃。

现有captureStatus.ready仅表示tap可用。现有tap.start在postMessage后立即返回，
worklet没有started事件；这不是新start ACK的证据。W1新增如下闭合协议：
start消息为`{type:"start",generation,binding}`，binding为
`{control_epoch,session_id,begin_command_id}`；新begin必须非null，旧非D04 caller可以
binding=null。generation仍是controller的safe integer，和Core UUID不同。worklet在实际
处理start、设置generation并清sequence/frames后，在下次process之前发送同shape的
`type:"started"`。ACK只是证明这台tap已armed，不证明Core DSP，也不承诺尾音buffer重建。

Controller在发送前占有唯一pending start；RuntimeSession也在await前登记pending owner，
防止两个start穿过目前active=null窗口。start promise仅在严格匹配node/context owner、
generation与binding的started ACK后resolve。capture handle返回不可变started receipt；
RuntimeSession再次对照retained target、Core begin与其SDK session-generation，置
`host_capture_ready:true`。只有两ready成立的同一begin才放行first recorded Pad/Pattern。
不得以tap可用status、start已posted、任意后续batch或另一个capture ACK代替。

旧generation/node ACK忽略；当前generation但错binding、额外字段、重复started或batch
在started前属于协议失败，拒绝pending start并清理，保留原有batch sequence/stop ACK
严格性。Close/replacement/processorfailure及postMessage失败均使start reject，释放pending
ownership；不得把late ACK用于后续begin。start ACK的新增有界超时建议复用现有30s
stop ACK预算作为独立start failure timer，不改旧stop预算；超时不开放Pad gate。
capture失败不能回滚已耐久的Core begin；SDK以原session/begin身份调用现有stop/finalize
收尾，只有原begin到明确终态后才能另开；不能换ID自动重启或放行积压Pad。
关闭pending时请求matching stop并走现有有界stop清理；若不能证明旧processor已停止，
将该tap/context标unavailable直至callback-drained replacement，不能立即复用它。

Webcapture ready不是Facade承诺：headless/native Core只能证明control-ready。
SDK/Creator owning oracle须延迟真实worklet start处理：promise持续pending且首Pad未投；
交付actual started ACK后首个跨quantum Pad的PCM进入capture。失败/close/错epoch均
不能出现漏录首声或继承ACK。此文只指定oracle，尚未执行故障注入。

新控制接口只允许一个 inflight admission/receipt，并复用已有 FIFO；不得为 pending
fence/reset 另建无限 retry 队列。现有 Promise tail 的排序不构成容量证据，Web/Creator
Task采用最小有界consumer窗口：每个SDK/Creator controller一条inflight，最多一条普通
waiting input；另给已接收的最多64个Pad gesture各一条matching release slot，以及
一个cleanup token。pending满时新增普通输入明确拒绝，不合并已接收FX值、不丢release。
同时最多64个Host open Pad gesture，新增第65个press拒绝且不报告admitted，给每个
已接收gesture预留其release位置。cleanup取消尚未Core接收的waiting输入时明确reject其
promise，不静默丢弃；Core已admitted的release/Journal仍先完成。
这些是原FIFO的容量规则，不增另一套调度器；mapping/expected序号到dequeue才取。
W1/C1 owning压力oracle延迟begin/receipt并超额调用，验证普通pending≤1、已接收
Pad release仍完成、cleanup优先完成；不能把Host未接收的输入报告为Core admitted。

fence ACK 建议用一个 preallocated retained receipt slot（固定容量 1 的反向 SPSC），
存 epoch/token/完整控制 snapshot，直到唯一 control-thread owner 消费。普通旧 FX 的
latest telemetry 更新不能覆盖它；上一个 fence 未消费前不预留下一个 fence。render
写一次即继续，不等 consumer；Project replacement 的 stale ACK 被 epoch 拒绝，只在
已 callback-drained 的生命周期边界重置该 slot。它直接解决“轮询前状态已被后续控制
覆盖”的反例，不新增持久化层、无限 receipt 队列或 render lock。

header 的早期耐久写入只表示 prepared draft；applied 相等校验失败时保持未 ready、
recovery-required，不启用capture/首个Pad。一个预先 accepted 的参数值只有在这个
fence 的实际应用证明后才成为可用的录制起点，不能把 optimistic accepted 当已生效。

同一 quantum 中 DSP 沿用现有 master-control 在 voice mix 之前 drain 的规则。
ACK 表示状态已应用，不宣称每个连续旋钮值都已独立产生一个可听 sample。
新 profile 的 same-tick input 顺序用于确定性 admission／Replay 调度；渲染量化仍按
实际 engine quantum。测试必须用一次真正跨 render quantum 的 Pad PCM 判别“先于
首声生效”，不能只比较 enqueue 计数或两个 JS state。

参数事件 Replay 应证明控制到同一 DSP 的行为、次序、单位和清理；它不承诺从参数
重建 bit-identical 的录制 PCM。共享 FX 的起点 delay-line/正在响的旧 voice、实际
render/capture 调度都不在此 header 中；既有 master-capture Wav receipt 仍是录音
和 resample 的唯一音频依据，不能把重新渲染输出替换它。

没有附着真实 Engine 的 headless recording 继续通过旧 begin 生成旧 profile；新 epoch
begin 明确返回 audio producer unavailable，不伪造 independent 已生效录音。
直接 Project I/O 的确定性 fixture 可构造新 header 测耐久，但不能当作 actual applied。
fence pending 的失败和 exact retry 保留原 command／session／Performance 身份，
不能在 pending 时重新分配 begin ID；Clock 仍由 Core anchor／read，Host 不提供时间。

## Queue-full、Journal 故障与 exact retry

新 typed 控制建议使用 `reserve → durable append（录制时）→ publish`。预留只是容量
与目标 lease；原有旧 FX 路径的 audio-before-journal 行为不作为“已经可回滚”的证明。
新路径不先让声音发生，再把 known Journal failure 包装成整个命令未发生。

| 阶段／结果 | 必须报告和保留的状态 | 再执行规则 |
| --- | --- | --- |
| shape／范围／epoch 不合法，或 reserve queue-full | 未 admitted；无 durable event、无新音频状态 | 明确失败；用户仍可用原身份重试未接收的请求 |
| Journal known failure，且 cell 未发布 | 无新音频；恢复 accepted shadow／checkpoint；保留原错误 | 原pending identity可重试；该窗口内不同payload为collision |
| prepared Journal unknown／可能已写 | 冻结该recording admission、标recovery-required；cell不发布；不假报absent | 先按新增 durable ledger/recovery 判定同一identity；不换ID自动再录一次 |
| prepared known success＋cell发布 | durable admitted；accepted更新；applied pending；complete metadata尚待耐久 | 同identity不再enqueue；仅推进同一complete metadata并独立读applied ACK |
| 发布后 epoch 消失／停止，或 ACK 不可取得 | durable receipt 不删；applied unknown／cancelled，保留实际 capture／故障 | 不把 accepted 回滚成“未发生”，也不向新 epoch 补投 |

持有的 epoch lease 将 Project/engine 的 control-thread replacement 与 reservation／
publish 串行化；render 始终 lock-free。stop 可以让已经发布的事件最终未产生 PCM，
因此 durable admitted 仍不等于 audible/applied。未知写入若恢复证明 absent，才允许
同 ID 重新 reserve/append；若证明 present 且从未 publish，只可在原 epoch 中完成
同一 pending admission。epoch 已失效则不补声，按已恢复的耐久状态收尾。

### 新增 recording durable admission ledger（R2）

现有application.cpp:2403–2426/7453–7467的event_receipts仅在内存，reattach初始化为空；
Journal tail/checkpoint不保存event_id/raw payload。因此以下是P0/P1新增能力，不能称已有
durable receipt。方案选择最小窗口：**每session最多1 pending + 最近1 completed**，
不是无限UUID历史。新增Core-issued `expected_recording_sequence`（初始"0"）区别于
音乐input_sequence和control_sequence；SDK只回传receipt/status中的opaque值。所有新
profile的event、Pattern请求都经过该identity窗口；旧wire/legacy内存receipt行为不变。

新record.event在旧外层键上增加control_epoch和expected_recording_sequence；Pattern
request相应增加同两字段。identity为(session_id,expected_recording_sequence,event_id)，
Pattern使用request_id；不能通过更换epoch或expected值冒充exact retry。完成一次
admission（含release/no-op/预约）使next_recording_sequence加一。SDK不提供input顺序，
expected字段只是Core串行compare-and-set前置条件。溢出拒绝新admission，不wrap。

新profile Journal begin与每次checkpoint/recovery snapshot添加严格`admission_ledger`：

```json
{
  "admission_ledger": {
    "next_recording_sequence":"2",
    "pending":null,
    "completed": {
      "request_id":"55555555-5555-4555-8555-555555555555",
      "expected_recording_sequence":"1",
      "request_fingerprint":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      "accepted_tick":32,
      "input_sequence":"11",
      "phase":"completed",
      "result":"published",
      "event_input_sequences":["11"],
      "binding_result":null
    }
  }
}
```

pending使用同一receipt字段，但phase="prepared"、result="not_published"；只在同process
保留的reservation证明not_published，磁盘这个result不是crash后的未发布证明。
result completed只为published/no_audio（recording metadata/no-op等），**不叫applied**。
event_input_sequences可为空（no-op/press尚未闭合），Pad release可引用早期press序号，
预约Pattern先为空、pending_launch另持original input_sequence、ACK产生相应事件。
binding_result为null或闭合{fx,recording_gesture_id}（仅新engage/adoption的logical结果）；
runtime generation不耐久保存。原lease仍在时exact receipt从Core对应live binding返回
其runtime generation；reattach只返回logical结果/runtime-binding-unavailable，不开放
新输入。两种响应均保留原admission结果，不能把缺少原runtime ACK伪造成新可用mapping。
整session/session+performance身份在既有Journal外层，不重复在每receipt。字段全部
exact keys，UUID及64位canonical string/sha256严格校验；pending/completed各最多1。

request_fingerprint为SHA256(canonical_json(完整严格request减project_path))，包含原
operation、session_id、request/event ID、expected、control_epoch和event所有字段。
它绑定实际原payload而非派生Fx tuple，epoch/generation只作为请求hash输入，不把
runtime UUID明文写Project Truth或靠其恢复producer。旧request `.dump()`比较及旧
performance_fingerprint preimage3575–3588继续原分支，不套新hash。

持久阶段是明确的两步，复用同一checksummed Journal，不另建数据库：

1. reserve/验证后冻结tick/input_sequence、candidate events/checkpoint、identity/digest。
   append新profile的tail，原canonical events/checkpoint与pending receipt一起耐久，
   high-water包含此次分配；no-op/release也保存receipt，不从Project event反推请求。
   一次prepared pending阻止普通外来admission和flush/finalize推进；真实producer已丢失后的
   recovery-only收尾是下文R5限定的例外，不能靠ACK超时或普通失败进入它。
2. known-success后更新accepted shadow并发布reservation（或no_audio）；随后append
   新record kind `admission_complete`，其闭合字段为kind/performance_id/tail_seq/
   expected_revision/receipt，receipt为completed shape。它不分配音乐序号或重新写
   events，不要求input high-water增长；只匹配唯一pending identity+fingerprint，将
   next_recording_sequence推进、completed替换最近一个、pending清空。成功后才返回
   completed admission receipt；published仍要独立read真实applied ACK。

Journal旧tail的严格input_sequence增长不能照搬到这个metadata record。P0显式解析该
new-profile record、checkpoint和recovery窗口；新Journal begin/recovery snapshot明确带
`live_control_profile:"header_input_sequence"`，null/未知profile拒绝；begin的ledger初始
next="0"、pending=null、completed=null。旧no-header Journal grammar不接收新字段或
metadata kind；discriminator不能凭任意新增字段隐式猜测。
现有read_complete+checked records会读整份Journal，没有bounded completed receipt空间
或无限耐久去重保证。本窗口只使retained logical receipt对象固定≤2，不声称整份录制
file/reader已变有界；旧torn-tail/checksum/validated-prefix与单次bounded rewrite规则保持。

known-absent prepared append取消cell，不更新accepted；同process保留pending tuple供
原identity retry，不能next/read_tick第二次。unknown冻结session并保留cell未发布；恢复
验证该exact prepared record present/absent（identity/digest/tick/seq/checkpoint全相等）后
同process且lease仍有效才能完成或原tuple重写。metadata complete写入unknown时**音频
可能已经发布**，冻结且保留written event/receipt，不回滚音频、不再publish；先核对
complete present/absent，再仅补相同complete metadata。

process/adapter丢失后的prepared recovery无法证明publish发生与否，返回accepted-durable/
applied-unknown、recovery_required，不自动补声，不把磁盘not_published当保证；保留
原Wav/Journal并经下文recovery-only closure/seal收尾。begin/header也不能因此重新从当前DSP
捕获。completed recovery返回原tick/seq/result、replayed=true/applied=unknown，无enqueue。
完全没有prepared记录且验证prefix证明absent，允许仍合法session的原请求重新reserve；
没有持久化过的tuple在process丢失后不承诺原tick/seq。corrupt/unreadable始终unknown。

receipt lookup先于epoch/expected拒绝：在pending/completed窗口内，同identity exact
返回原状态或推进原pending；不同fingerprint collision。未命中且expected小于next，
明确`recording_retry_expired`、结果unknown，禁止重新执行；大于next拒绝out-of-order。
当前expected的fresh request才可admit。该保证的identity含expected，不宣称跨窗口记录
所有UUID碰撞；客户端改expected即是新请求，不能被SDK当自动重试。closed/sealed session
没有可用ledger时只返回session-ended/不可查，不重新打开录制。active/sealed recovery
需要保留同一最新ledger直到既有journal/recovery清理；本Task不授权cleanup。

具体C1→C2→reattach：C1 expected0/seq10，C2 expected1/seq11，磁盘next2、completed=C2。
C2 exact返回原seq11；C2同identity改value拒绝collision；C1原wire返回retry_expired且
零enqueue，不假称能还原C1结果。新profile禁coalescing；no-op/release也按同窗口推进，
预约PatternACK仅补结果event、不改原request identity、不产生第二次音乐sequence。
P0/P1 owning fault/recovery oracle逐阶段证明present/absent、C1/C2、staleepoch零补声。

live-only不写工程，identity为(epoch,expected_control_sequence,command_id)，同样仅1
inflight+最近1completed；成功含no-op推进control sequence，超窗stale expected明确拒绝。
其receipt不会由recording ledger复活，不能把两种有界保证混为无限durable live history。

### Producer 丢失后的 recovery-only closure/seal（R5）

此例外只终止旧录制，不是重新取得其admission资格。须经现有exclusive writer与
ProjectStore owner-loss reconcile：取得原session的owner lock，证明原producer/lease已
丢失、旧control epoch已失效且旧audio callback已quiescent/drained。取得锁本身不证明
render静止；仅ACK超时、Journal返回unknown或UI离页均不足以进入例外。若同一producer
仍在，先走原pending identity的有界reconcile，不得用recovery-only绕过它。

在writer边界完整读取并验证checksummed prefix、Project/Performance/session身份与
原pending的request ID、expected、fingerprint、tick/input_sequence和candidate checkpoint。
corrupt/unreadable、prefix/身份不相等继续unknown并保留材料，不猜absent或terminal。
证明成立才允许关闭logical open Pad/FX/independent Filter/HOLD transients、追加canonical
closure tail/checkpoint并seal；这些是metadata-only耐久收尾，不向Engine enqueue、不触发
声音、不启动capture，不声称真实DSP已应用closure。原Wav与完整durable状态仍保留。

复用现有`tail`、checkpoint与checked sealed recovery snapshot，不为此新增record kind。
new-profile closure tail携带原样`admission_ledger`：原prepared pending、最近completed及
next_recording_sequence不被清掉或推进；pending的identity/result字段不改成completed。
只闭合logical transients并更新对应canonical events/checkpoint。内部closure事件序号从
已验证的durable high-water唯一派生并冻结，PadHit仍用原press序号；closure tick由原
checkpoint/事件界限派生，不读取Host时间。exact metadata retry复用整份closure candidate
和tail_seq，不二次分配序号。sealed snapshot沿已有owner_lost状态保存相同ledger。
磁盘prepared/not_published在lost-owner状态只投影accepted-durable/applied-unknown，
不能补造admission_complete、published/no_audio或applied ACK以便finalize。

closure与seal均可能present/absent/unknown。现有validated-prefix、checksummed记录及
Performance固定session sealed路径/完整bytes相等校验是证明边界：相同identity和完整
candidate已present则复用，验证前序prefix且candidate确实absent才可按同identity执行
一次bounded metadata-only重写；unknown继续冻结，保留active/sealed两端证据，不默认
成功、不盲目remove。closure已present不再追加，seal尚未确认时只重试相同seal；sealed
相等但active转出尚未完成时沿原canonical reconcile完成，不创建第二个候选或换ID。
legacy分支、checksum/torn-tail和单次bounded rewrite预算不变，不另建无限恢复队列。

只有closure及canonical seal/finalize结果已验证、旧active Journal/owner lock按规范转出，
才报告该录制terminal。终态保留的prepared receipt只可查询原身份未知结果或collision，
不能推进原pending、重开admission、复活generation/capture或自动换新ID补声。后续显式
recovery apply/finalize须在其canonical stopped/recovery表示中保留该ledger的未知事实；
不能把旧恢复路径当成已支持新字段。新Performance使用新的session/Performance/begin
身份及初始空ledger，旧terminal pending不再占用它的admission窗口；既有尚未解决的
writer/recovery冲突仍需解决，不能以新身份越过未确认的seal或corrupt prefix。

P0/P1 owning oracle须覆盖prepared耐久后、publish之前/之后、complete之前崩溃：lost
owner→validated reconcile→closure/seal/terminal→旧exact retry为unknown且零enqueue，
随后新身份begin有独立空ledger；closure写入与seal各自present/absent/unknown、重复
reconcile、晚旧callback都保持原身份/序号/结果，不伪造完成或复活producer。尚未执行。

reset/neutral 是同队列的一个有界命令，包含旧 HOLD/FX neutral、independent OFF
以及两组空 mask。Replay Stop／complete／owner loss 只有在该 epoch 的实际 ACK 后
才到终态；queue-full 保持 pending，用现有 service/status 有界推进，不能 busy-spin。
engine stopped 且 callback-drained 才可用 quiescence 证明完成。旧 “8 release 已 dequeue”
计数不能证明新 Filter／mask 清理。新的 default parameters 不等于已 ACK neutral。

## 生命周期与待答的尾音选择

录制 Stop 仅停止记录，不清 live 控制；Pad 门控在 Bank／Pattern 切换仍保留。
离 Perform 先确认两组 mask 清空，再执行既有 FX release／HOLD 和 transport／录制
finalize。HOLD 可保留 Filter，但不能保留 mask。切工程／关闭 session／engine
replacement 让旧 epoch 失效并在新 engine 初始 neutral，不把 live mask 写 localStorage。

**Pending — owner 尚未选择 Mute 尾音语义。** 推荐在每个工程 Pad 声部进入共享
Master FX 之前乘 live gate：96-frame gain ramp 到零，cursor／gate duration 继续前进；
解除 Mute／Solo 恢复当时声部，不重触发。已进入共享 Delay／Reverb 的尾音自然衰减，
不清共享 delay-line，也不删除别的 Pad 的效果尾音。
这是一条最小 per-voice gain＋64-bit gate Task，保持现有 shared-FX 架构。

如果 owner 要求每个 Pad 连其历史尾音立即单独静音，现有共用总线无法区分尾音来源；
需要另立 per-Pad send／FX state 或 tail attribution 的架构、CPU／内存与 resample
验证 Task。不能在 M1 静音整个 shared FX 或全局清 buffer 伪装实现，因为会伤其他 Pad。
在实际回答到达前，推荐不构成批准，M1 和依赖其声音验收的 Task 不启动。

## 设计 review 的最小反例

1. legacy fixture 原样 round-trip；0–6 和旧 Filter PCM golden 不变；新录音不得夹杂
   missing sequence，超范围/重复 Slot、无效 mode、序号溢出必须拒绝。
2. 起点已有 Mute A01、Solo D16、独立 HP；begin 期间再改 Resonance；首个同 tick
   A01/D16 Pad 在 begin applied 前不能进 engine，之后 PCM 符合起点与唯一后续变更。
3. same-tick Pad 与 control 在不同接收顺序下得到各自确定的 Replay boundary；未来
   Pattern effective_tick 不错误强迫全列表 input_sequence 单调。
4. 在 reserve、耐久写前/后、publish、render ACK、Project replacement 之间插入确定
   interleaving，逐一判别 known failure、unknown recovery、exact retry 和 stale epoch。
5. 延迟worklet处理start，Core已ready但capture尚未ACK时firstPad不投；错generation/
   epoch/close的ACK不能放行，actual ACK后首跨quantum PCM被捕获。
6. 起点engaged Delay＋HOLD frozen Reverb：begin mapping只为engaged，first move/release
   配对成功、无假engage/reset音效；晚callback与newgeneration不串。
7. 新profile Move500@(16,10)→Pad@(32,11)→Move900@(64,12)均保留；旧profile128tick
   规则保留。C1→C2→reattach的C2exact/collision与C1expired均零重复apply；prepared
   和completed写入unknown按各自publish边界恢复。
8. HOLD=true 离 Perform 仍清两组 mask；queue-full 的 reset 不能先宣称 complete；
   零事件 header Replay 也必须完成 initial apply 和 neutral ACK 两端。
9. prepared后、publish前/后崩溃并失去producer：经exclusive validated recovery-only
   closure/seal进入terminal，原pending仍unknown且旧retry零enqueue；下一Performance
   空ledger不被旧terminal pending阻塞。closure/seal未知不能当成功，ACK超时不能冒充lost owner。

以上是后续最低层测试的 defect oracles；D0 文档 review 本身不产生这些测试的 pass。

## Version Management

Version impact: none — D0 仅技术草稿，不修改 schema、source、manifest 或 Build。

实施 P0 时，Project v5 optional syntax 可作为 MINOR **候选**，条件是新 reader 接受
全部旧有效输入、旧 profile/Filter 语义和 ordinal 不变。旧 reader 拒绝新格式不自动
等于新 Contract major；删除旧合法数据、改旧含义则必须 major/新 ID。当前真实起点
为 5.3.0，schema metadata 与 conformance expectation 必须一起结算，不无版本落新语法。

JSON 的兼容扩展不等于 C++ ABI 兼容：Performance variant/struct、ProjectState、
I/O request/checkpoint与新增ledger、ReplayProjection、RealtimeEngine layout、virtual ports/adapter
增长都可能要求各 Module MAJOR。按实际改变检查下游 public ABI 和 Assembly locks；
Facade C ABI envelope 不变不能掩盖其 C++ ABI。API surface version 只按实际表面变化，
不因 MINOR/MAJOR 猜一个 api_version。独立 V1 结算 Module/Host/Assembly/Build，
不得在这里猜身份或借未发布ABI debt声称无影响。当前source内部Performance Journal/
recovery ID是v1常量，未找到独立Contract SemVer manifest；P0新增profile discriminator
`live_control_profile: "header_input_sequence"`明确分支，保留v1 legacy reader/preimage。
内部耐久grammar迁移必须在P0实际记录并review，不能把Project schema MINOR当其
自动版本证明或仅扩闭合集合；Portal只投影实际登记identity，不在D0先分配新ID。

## Documentation Impact

Documentation impact: none — 这是未实施的 PRD 技术提案，未改变当前 Portal source
facts、manifest 或 diagram。各实现 Task 必须同 Task 更新其当前 Portal routes 和
源图／生成图；具体清单见 producer 计划。D0 不运行 Portal build 或生成 Build snapshot。
