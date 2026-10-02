# 已确认：Pad 回放与音色参数对齐 Koala；实时引擎允许 varispeed 变调，保音高 time-stretch 仍离线；新参数为可选字段，缺省即现状

- 日期：2026-09-30
- 关联：Umbrella [#1658](https://github.com/endaye/lmdj/issues/1658) 的
  P2.1 [#1666](https://github.com/endaye/lmdj/issues/1666)（reverse、pitch、
  pan、loop 模式）与 P2.2 [#1667](https://github.com/endaye/lmdj/issues/1667)
  （attack / release、tone、3 段 EQ）；产品基线
  [2026-09-29 Creator 用户流程](2026-09-29-creator-user-workflow-baseline.md)
  第 7 条"Sample 的编辑能力以 Koala Sample Editor 为基准"；实施计划
  [`docs/plans/2026-09-30-creator-sample-parity.md`](../../plans/2026-09-30-creator-sample-parity.md)。
- 部分取代：
  - [2026-08-26 D2](2026-08-26-long-material-quota-and-bpm-stretch.md) 第 8 条中
    "Project Truth 不为 Asset / Pad 增加……速度字段"与第 9 条"实时引擎零 DSP、
    不引入任何 stretch/pitch DSP"——仅就 **varispeed 变调**取代；第 10 条
    保音高 time-stretch 的离线烘焙路线、"修改 BPM 永不改变任何 sample 的
    播放速度或音高"维持不变。
  - [2026-08-24 渲染斜坡决策](2026-08-24-render-path-amplitude-ramp.md) 中
    "循环接缝 crossfade（选项 b）暂不实施"——改为用户可控的循环 crossfade；
    2 ms 去爆音斜坡本身维持不变。
  - [Stage 8 设计](../../design/2026-08-08-lmdj-stage8-sample-editor-design.md)
    "Stage 8 不实现"中的 Reverse、Pitch、Pan、Attack、Release、Tone 条目。
    Time-stretch、Choke Group 等其余条目不受本决策影响（Choke 属
    [#1668](https://github.com/endaye/lmdj/issues/1668)）。
- 结论：
  1. **Pitch 是实时 varispeed。** Pad 的 `pitch_cents` 通过重采样改变播放
     速率 `2^(cents/1200)`，时长随音高变化，对应 Koala Pad Management 的
     PITCH。保音高的 time-stretch 仍是
     [#347](https://github.com/endaye/lmdj/issues/347) 的逐 Pad、离线烘焙
     opt-in 能力，永不进实时引擎；全局 BPM 仍只驱动 Sequencer。v1 不做
     pitch-up 抗混叠滤波，这是已知限制。
  2. **参数归属不变：属于 Pad Slot 的 `PadPlayback`，不属于 Asset。** 所有
     新字段都是**可选**字段，缺省值等于今天的行为；Project Truth 与线上
     传输**省略取缺省值的键**，未使用新功能的工程字节不变。
  3. **参数表（Contract 值域）。** Koala 手册（4.7、4.8、Pad Management）
     未给出任何数值；下表为 LMDJ 的取值，与 Koala 的差异按 Umbrella 要求
     显式列出。

     | 字段 | 值域 | 缺省 | 语义 |
     | --- | --- | --- | --- |
     | `reverse` | bool | `false` | 读头从 `end` 走向 `start` |
     | `pitch_cents` | 整数 −2400..+2400 | `0` | 播放速率 `2^(cents/1200)`；半音或微调只是界面步进 |
     | `pan` | 整数 −100..+100 | `0` | 等功率声像，居中为单位增益，硬偏时远端声道为 0 |
     | `loop_mode` | `forward` \| `ping_pong` | `forward` | 仅 `loop_gate` / `loop_toggle` 生效 |
     | `loop_start_frame` | 源帧整数，位于 `[trim_start_frame, trim_end)`，或 `null` | `null`（等于 `trim_start_frame`） | 首次从 trim 起点播放，之后回卷到循环点 |
     | `loop_crossfade_frames` | 源帧整数，≤ 循环长度的一半 | `0` | 等功率接缝交叉淡化；只用于 `forward`，与 `ping_pong` 同时非缺省时拒绝 |
     | `attack_ms` | 整数 0..2000 | `0` | 线性淡入；实际长度取 max(用户值, 2 ms) |
     | `release_ms` | 整数 0..4000 | `0` | 线性淡出；实际长度取 max(用户值, 2 ms) |
     | `tone` | 整数 −100..+100 | `0` | 负值为低通（截止频率按对数从 20 kHz 扫到 100 Hz），正值为高通（按对数从 20 Hz 扫到 8 kHz），12 dB/oct；\|tone\| ≤ 2 旁通 |
     | `eq.low` | `{kind: shelf \| cut, freq_hz: 20..2000, gain_millidb: −18000..+18000}` | 旁通 | `shelf` 为低架；`cut` 为该频率的高通，忽略增益 |
     | `eq.mid` | `{freq_hz: 100..10000, gain_millidb: −18000..+18000, q_milli: 100..10000}` | 旁通 | 钟形；极端 Q 即陷波 |
     | `eq.high` | `{kind: shelf \| cut, freq_hz: 1000..20000, gain_millidb: −18000..+18000}` | 旁通 | `shelf` 为高架；`cut` 为该频率的低通，忽略增益 |

     Koala 的"低架拖到底变高通、高架拖到底变低通"在 Contract 中用显式的
     `kind: cut` 表达，不用魔法增益值；界面仍按 Koala 的拖拽手势映射。
  4. **固定 DSP 顺序：读头 → 包络 → tone → EQ → pan → gain。** 读头负责
     reverse、varispeed、循环点、ping-pong 与 crossfade；ping-pong 在边界
     反射，不重复边界帧。任何 stage 取缺省值时被旁通；全部取缺省值时，
     输出与今天逐样本一致。
  5. **包络与触发模式。** Attack 作用于每次触发。Release 作用于 voice 的
     停止事件（gate / loop_gate 松开、loop_toggle 再次按下、将来的 choke）；
     `one_shot` 忽略松开，自然播完仍用 2 ms 结尾淡出——Koala 手册未写明
     one-shot 的 release 行为，这是显式差异。Release 尾音期间 voice 继续
     占用 voice 容量；容量满时沿用现有 `voice_capacity` 结果，不引入 voice
     stealing。
  6. **同一段 DSP 代码，多条路径。** 实时演奏、Sample 预览、Pattern 播放、
     Performance Replay 与离线渲染都执行同一份逐 voice DSP 内核（与
     [Perform FX 决策](2026-08-28-perform-momentary-fx-transient-gestures.md)
     第 5 条同一原则）。所有新参数都取缺省值的事件继续走现有离线整数
     路径，已有 golden 渲染保持不变。实时路径仍是 mono 下混；离线路径对
     立体声源保留立体声，这一既有差异不在本决策内改变。
  7. **realtime 安全不放松。** 系数在每次触发时计算一次，`render` 保持
     零分配、零锁、`noexcept`；CPU 预算按全部 stage 打开、满 voice 的最坏
     情形验证，不因新 stage 放宽任何 deadline。
  8. **Host 可观测性。** Reverse 时向 Host 发布的 `source_frame` 是物理
     源帧，playhead 随之反向移动；ping-pong 同理。
  9. **Cardputer 不承载新参数。** `lmdj.runtime-content.v1` 的 Pad 记录不
     扩展；encoder 遇到任何非缺省新参数时明确拒绝（fail-closed），不静默
     丢弃。设备端支持另开 follow-up issue，由 Cardputer 内存预算决定。
- 原因：
  - 2026-09-29 基线确认 Creator 先对齐 Koala；Koala 的 PITCH 是随手可调的
    实时 varispeed，要求用户为每次音高调整等待一次离线烘焙，会破坏"约
    3 分钟得到可演奏 Pad"的承诺。D2 当时的约束对象是 time-stretch 与
    BPM 耦合；varispeed 不引入 BPM 语义，也不改变"sample 无 BPM"的结论。
  - 可选字段、缺省即现状、省略缺省键，使旧工程与旧 reader 不受影响，
    Contract 只需 Minor 升级，不必为已有 v5 文件做迁移。
  - 共享 DSP 内核避免"试听与导出不一致"，也是将来导出 Stems
    （[#1675](https://github.com/endaye/lmdj/issues/1675)）的前提。
- 影响：本决策为纯文档权威，不改活动 manifest、Contract 工件、模块版本或
  Product Build。实施按上述计划支付：
  - `lmdj.project.v5` 增加可选字段：#1666 的字段为 Contract Minor 5.1.0，
    #1667 的字段为 5.2.0（按
    [version-management](../../governance/version-management.md) "向后兼容的
    可选字段增加 Contract Minor"）；使用了新字段的工程会被旧 reader 拒绝，
    先例为 `lmdj.project.v4` 4.1.0。
  - `authoring-domain`、`project-io`、`project-cooker`、`audio-runtime`、
    `application-facade`、`web-runtime-platform`、`creator-web`、`core-mcp`
    各自的 SemVer 级联、Assembly 与新 Product Build，以及 Portal 路由，由
    实施计划的 Version Management 与 Documentation Impact 声明。
  - `lmdj.runtime-content.v1` 不变。
  - 不关闭 #1666、#1667；两者由各自的实施 PR 与验收证据关闭。

## 补记：2026-10-02，#1780 独立审查后 Owner 确认

#1667 的 Core 实现（[#1780](https://github.com/endaye/lmdj/pull/1780)）经独立审查实测，发现两处结束方式问题，Owner 在会话中做出以下两项决定。

1. **第 4 条补充：带滤波 voice 的结尾 declick 在 EQ 之后再做一次。**
   - 问题：包络在滤波器之前，包络归零时滤波器仍在响；voice 若在这一帧直接关闭，输出会从约 −2 dB 跳到 0（实时与导出相同）。
   - 规则：开了 tone 或 EQ 的 voice，最后 96 帧的结尾 declick 在 EQ 之后对输出再乘一次（release 尾音与非循环 voice 的结尾都适用）。voice 仍在原来那一帧结束。
   - 不变的部分：第 4 条的其余顺序不变；不开滤波的 voice 不受影响，输出逐位不变。
   - 代价：共鸣很强的 EQ 尾巴会在最后 2 ms 被淡出截断。
2. **第 5 条澄清：只有 release 事件才走 Pad 的 release。**
   - 走 Pad release 的事件：gate / loop_gate 松开、loop_toggle 再次按下、Pattern 与 Performance Replay 的 note-off，以及将来的 choke。
   - 只用 2 ms declick 的停止：`stop_all`、`stop_slot`、Pattern 切换与 transport 停止、audition 停止。
   - 依据：Owner 要求"和 Koala 一致"。Koala 手册没有写明停止时的行为，最接近的官方说明是"要停止一个很长的 one-shot，可以双击播放键停止 sequencer"，即停止表示立即静音。

同一轮审查还修正了两处实现，属于对本决策原有含义的落实，不改变决策：

- Attack 期间开始的 release，从 attack 当时的电平线性淡出，不会在松开后继续变响。
- 第 5 条已规定 one_shot 忽略 release，所以 one_shot 的 release 解析为 0。只设置了 release 的 one_shot 仍是中性的，Cardputer 不会因此拒绝它。
