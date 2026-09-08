# Patatap × Incredibox × Seaquence × LMDJ 产品机制对照

> 研究日期：2026-08-02
>
> 对照对象：[Patatap](https://patatap.com/) × [Incredibox](https://www.incredibox.com/) × [Seaquence](https://seaquence.app/) × LMDJ
>
> 研究性质：逐项产品机制对照；暂不进行功能设计、范围决策或实施规划

相关研究：

- [Patatap 与同类视听音乐产品调研](./2026-08-02-patatap-and-visual-music-product-research.md)
- [Playable Beat Instrument 与新内核设计](../design/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md)
- [LMDJ 产品决策日志](../prd/decision-log.md)
- [Koala Sampler 产品研究与 LMDJ 启示](./2026-07-28-koala-sampler-product-research.md)

## 0. 结论先行

四者不是同一层级的直接竞品：

- **Patatap** 是 Event-first 的即时视听乐器；
- **Incredibox** 是 Content-first 的同步 Loop 组合、表演记录和传播产品；
- **Seaquence** 是 Object-first 的可视多声部 Synth + Sequencer + Spatial Mixer；
- **LMDJ** 的已确认方向是 Material-to-Instrument 的 64-Pad Playable Beat Instrument，
  通过 Sample、Sequence、Perform、Export 和 Resample 形成创作闭环。

它们分别回答四个不同问题：

| 产品 | 首要问题 |
| --- | --- |
| Patatap | 怎样让一次输入立即成为声音和画面？ |
| Incredibox | 怎样让不会编曲的人组合出持续、同步且可分享的 Mix？ |
| Seaquence | 怎样让声音、序列、运动和混音成为同一个可视对象？ |
| LMDJ | 怎样把任意声音或完整歌曲变成用户可以亲手演奏、录制和继续制作的乐器？ |

最重要的对照结论是：

1. Patatap 的复杂度主要藏在声音与动画资产里；
2. Incredibox 的复杂度主要藏在预制 Loop、同步、角色状态和传播服务里；
3. Seaquence 的复杂度主要显式存在于 Voice、Sequencer、Synth、Physics、Mixer 和
   Session 对象中；
4. LMDJ 的复杂度主要来自用户素材、Asset Lineage、稳定 Pad Slot、Raw Take、
   Pattern、Performance、Resample 和开放导出；
5. “加入视觉”不能被当成给四者寻找共同皮肤。真正需要比较的是：视觉是否只是反馈，
   是否代表可持久对象，是否进入表演记录，以及是否成为 Project Truth。

本文只把差异说明清楚，不据此批准 Visual Pad、Visual Scene、AV Resample、视频导入、
实时生成图形或其他功能。

---

## 1. 对照范围与证据边界

### 1.1 本文比较什么

逐项比较：

- 产品角色和目标用户；
- 首次输入与第一成功时刻；
- 声音来源与音乐容错；
- 输入、触发、连续控制和多点触控；
- 时间、同步、Pattern 和 Sequence；
- 视觉反馈、视觉对象和视听绑定；
- Project、Session、Mix 和状态持久化；
- Performance、Record、Replay、Resample；
- Export、Share、Community；
- 商业模式、内容扩展和授权；
- 学习成本、失败模式和产品边界。

### 1.2 本文不比较什么

- 私有 DSP、后端、服务器容量和收入；
- 未公开算法和完整源代码；
- 四者主观“谁最好”；
- LMDJ 视觉功能的 UI、数据结构、技术选型或开发排期；
- 未经真机确认的触摸延迟、音频稳定性和 CPU 性能。

### 1.3 LMDJ 列的含义

Patatap、Incredibox 和 Seaquence 列描述当前公开产品。LMDJ 列主要依据：

- 2026-07-30 已确认的产品决策；
- Playable Beat Instrument 与新内核设计；
- 当前仓库中的产品对象和工作流定义。

LMDJ 列描述的是**已批准产品方向和设计语义**，不是已经发布、真机验证或面向用户
可用的完整产品。任何视觉相关内容如果没有进入 Decision Log，均记为未决定。

### 1.4 证据等级

| 标记 | 含义 |
| --- | --- |
| **官方事实** | 产品官网、App Store、官方 FAQ、Guide、Press Kit |
| **代码证据** | Patatap 公开源码；LMDJ 当前仓库设计与产品文档 |
| **历史数据** | 官方在特定时间公开的访问、下载和作品数量 |
| **分析判断** | 由公开产品机制推导的比较结论 |
| **未决定** | LMDJ 尚未批准或公开资料不足，本文不代为选择 |

---

## 2. 四个产品的最小模型

### 2.1 Patatap

```text
Input Event
  → One-shot Sound Sample
  + One-shot Visual Animation
```

核心对象是瞬时 Event。声音和动画结束后，不留下用户可编辑 Project State。

### 2.2 Incredibox

```text
Sound Icon
  → Costume / Loop Role
  → Avatar Slot
  → Synchronized Ensemble
  → Recorded Mix Actions
  → Share URL / MP3
```

核心对象是角色槽中的同步 Loop 状态，以及用户在约三分钟内对这些状态执行的动作序列。

### 2.3 Seaquence

```text
Creature
  = Synth Voice
  + Step Sequencer
  + Visual Body / Motion
  + Spatial Mixer Position
```

核心对象是持久化 Creature / Voice。视觉外形、游动方式、声音、音符和空间位置共同
构成 Session。

### 2.4 LMDJ

```text
Source Sound / Song
  → Asset / Derived Asset
  → Stable Pad Slot
  → Raw Take
  → Pattern
  → Performance
  → Export / Resample
```

核心对象是用户素材、稳定 Pad Slot 和用户演奏事实。视觉对象目前没有进入已确认模型。

---

## 3. 产品定位与用户价值

| 维度 | Patatap | Incredibox | Seaquence | LMDJ |
| --- | --- | --- | --- | --- |
| 产品类型 | 即时视听乐器 | Loop 组合游戏 / 工具 / AV 体验 | 可视多声部 Synth、Sequencer、Spatial Mixer | 64-Pad Playable Beat Instrument |
| 核心承诺 | 任意输入立即产生好玩的声音和画面 | 拖入角色即可形成完整、同步的 Beatbox Mix | 用游动生物建立可持续、可调的多声部音乐 | 三分钟内把任意声音或歌曲变成 Pads 并亲手录下 Beat |
| 目标用户 | 全年龄、无需音乐经验、即兴表演者 | 全年龄、儿童、学生、休闲创作者、社区用户 | 新手到熟悉 Synth / MIDI 的探索型音乐人 | 有节奏感和表演欲、不想先学习完整 DAW 的新手创作者 |
| 用户拥有的材料 | 官方预制声音和动画 | 官方预制 Loop、角色与 Bonus | 用户创建的 Synth Voice 和 Step Sequence | 用户录音、导入音频、完整歌曲及其派生素材 |
| 第一成功时刻 | 第一次按键或触摸 | 第一批角色开始同步演唱 | 第一只 Creature 发声并与其他 Voice 叠加 | 第一批 Pad 可演奏，用户亲手录下第一个 Beat |
| 主要深度来源 | 时序、组合、熟练演奏 | Loop 选择、角色组合、Mute/Solo、Bonus、录制 | Voice 参数、Step、Scale、空间、Physics、MIDI | Sample、Pad、Take、Pattern、Perform、Resample、Export |
| 明确非目标 | 完整创作和工程 | DAW 式自由音频编辑 | 采样、完整线性 DAW | 完整 DAW、AI 替用户完成 Beat、首版多人协作 |

---

## 4. 首次使用与启动摩擦

| 机制 | Patatap | Incredibox | Seaquence | LMDJ |
| --- | --- | --- | --- | --- |
| 启动前选择 | 无 | 选择音乐 Version / Style | 可加载 Preset Session 或创建 Voice | 创建/打开 Beat Project，取得或处理声音素材 |
| 注册 | 不需要 | Demo 不需要；分享与学校服务有相应在线状态 | App 可本地使用；分享进入 Galaxy | Project 身份与账户边界由 LMDJ 自身产品定义 |
| 教程依赖 | 一句话提示 | Drag-and-drop 角色隐喻承担教学 | 视觉隐喻直观，但深层编辑需要 Guide | 已确认首版不做登录新手引导和 YouTube 教学弹窗 |
| 首次等待 | 加载当前 26 个 Sample | 加载一套角色、声音和动画内容 | 启动 Synth / Session | 用户素材分析、切片或处理可能产生可见等待 |
| 空状态 | 直接是可演奏画布 | 七个空 Avatar Slot | 空/预设 Mixing Dish | Beat Project + 空或已分配 Pad Slot |
| 失败暴露 | 加载或音频不可用时体验中断 | 在线 Demo、保存和分享有网络依赖 | 本地音频与 Session；分享功能另有依赖 | Provider、Job、Artifact、Partial Failure 必须显式呈现 |

### 4.1 对照判断

Patatap 和 Incredibox 能做到极短启动，是因为用户不带入原始材料：产品已经准备好
声音、视觉和兼容关系。Seaquence 虽允许用户从对象开始构造，但声音引擎仍完全内置。

LMDJ 的起点不同：用户素材是产品价值的一部分。因此 LMDJ 的首次体验不能只用
“像 Patatap 一样快”衡量，还必须处理导入、分析、Provider、Candidate、失败和来源
保留。这里是产品输入条件不同，不是单纯 UI 优劣。

---

## 5. 声音来源与音乐容错

| 机制 | Patatap | Incredibox | Seaquence | LMDJ |
| --- | --- | --- | --- | --- |
| 声音来源 | 6 套官方短 Sample | 官方制作并预先同步的 Beatbox Loop；2025 起纳入精选社区 Mod | 内置 Polyphonic Synth，Voice 参数由用户编辑 | Captured、Imported、Derived、Sound Set Asset |
| 音乐单位 | One-shot / 短 Gesture | 持续 Loop | Synth Voice + Step Sequence | Sample / Slice / Loop 在 Stable Pad Slot 中演奏 |
| 调性保护 | 每套声音共同设计，旋律与节奏约 13/13 | Loop 已预先调性与节奏兼容 | Scale、Key、Transpose、Step 和 Synth 参数约束 | BPM、Key、Role、Range 可用于分析、候选和确定性映射 |
| 时间保护 | 无 Quantize；用户触发时间直接生效 | Loop 自动同步，角色加入/移除保持整体节拍 | Sample-accurate Clock、Tempo、Step Subdivision、Swing | Raw Timing 保存；Pattern 支持非破坏 Quantize 和 Swing |
| 密度控制 | 短包络、少浑浊、同事件重触发 | 最多七个 Avatar Slot；Mute / Solo | 可创建 64 Voice，最多听到邻近的 8 个 | 64 Pad / 4 Bank；Pattern 与 Voice/Runtime 共同控制发声 |
| 用户声音设计 | 无 | 无 Sample / Synth 编辑；主要选择内容 | 深度 Synth、Envelope、Filter、Waveform、Delay | Sample Edit、Slice、Stem、Resample；Provider 辅助派生 |

### 5.1 Patatap：资产级容错

它让用户自由决定时间，但提前限制声音本身。新手友好来自短、兼容、不过密的声音集合。

### 5.2 Incredibox：同步 Loop 级容错

用户不是自由演奏每个 Note，而是在兼容的长 Loop 之间进行状态组合。产品把音高、节奏、
长度和同步问题在内容制作阶段解决。

### 5.3 Seaquence：规则和参数级容错

用户拥有更大自由，但 Scale、Step Grid、Polyphony 和同时发声 Voice 数量提供边界。
容错从“固定资产”转向“可编辑规则”。

### 5.4 LMDJ：用户素材与结构共同决定

LMDJ 不能假设所有输入素材天然兼容。它需要在保持用户来源的同时，通过分析、角色、
候选、Pad Mapping、Pattern 和非破坏处理帮助用户形成可演奏结果。其问题比三款内置
内容产品更接近 Sampler / Groovebox。

---

## 6. 输入、触发与表达粒度

| 机制 | Patatap | Incredibox | Seaquence | LMDJ |
| --- | --- | --- | --- | --- |
| 离散输入 | 26 Letter、Touch Cell、MIDI Note | Sound Icon 加入/移除 Avatar；Mute、Solo、Bonus | 创建、选择、编辑 Creature；Step On/Off | Pad Trigger、Pattern Launch、Bank Switch、Command |
| 连续输入 | Touch Drag 穿过区域；无力度映射 | 拖放主要用于状态设置，不是连续音高控制 | 拖动 Voice 改空间位置；曲线、参数和 Multi-touch | Velocity、Pitch/Playback 参数、Momentary FX |
| 多点触控 | 支持多个触点落在不同隐形区域 | 多角色状态，不以同时手指演奏为核心 | 最多 11 个 Touch Point | 首发 Desktop / Tablet Web/PWA，支持 Touch |
| Keyboard | A–Z + Space | 非主要产品隐喻 | 非主要产品隐喻 | 支持 Keyboard |
| MIDI | Web MIDI Note In / Out，固定 Mapping | 不是核心公开工作流 | Note / CC / Clock In / Out，Assignable Mapping | 支持 Web MIDI；具体 Profile 属独立产品/验证问题 |
| 力度 | 当前触发未使用 Velocity 表达 | Loop 状态没有 Note Velocity | MIDI 和 Synth Voice 可形成更细表达 | Raw Take 保存 Velocity |
| 输入结果 | 一次视听事件 | Ensemble State Change | Persistent Voice / Sequence / Position Change | Project Command、Take Event、Runtime Action |

---

## 7. 时间、Sequence 与 Pattern

| 机制 | Patatap | Incredibox | Seaquence | LMDJ |
| --- | --- | --- | --- | --- |
| 主时间模型 | 人的实时输入时序 | 所有内容处于同步 Loop 时间 | Global Tempo + Per-voice Step Sequencer | Transport + Raw Take + Pattern + Performance |
| BPM | 不显示、不设置 | 用户不需要处理 BPM | 1–360 BPM、Tap Tempo | Project BPM / Key 是全局音乐状态 |
| Quantize | 无 | Loop 资产本身已对齐 | Step Grid；Complete 版含 Swing / Subdivision | Quantize / Swing 非破坏应用于 Pattern |
| Sequence | 无 | Mix 记录用户状态动作，不开放 Note Sequencer | 每个 Creature 拥有 16×16 Step Matrix | Raw Take 与可循环、可编辑 Pattern 分离 |
| Pattern Slot | 无 | Version / Mix，不是 Pattern Slot 模型 | Session 中多 Voice Sequence | 首版 16 个 Pattern Slot |
| Pattern 切换 | 无 | 通过角色和 Loop 状态变化形成编排 | Session 内 Voice 共同运行 | Beat / Bar / Pattern End 切换，默认下一 Bar |
| Arrangement | 仅当下演奏 | 约三分钟动作序列形成 Mix | 非线性、多 Voice 持续系统 | Performance 记录 Pattern、Bank、FX 等操作；不等同完整 DAW Timeline |
| 原始演奏保存 | 无 | Record 保存用户操作序列 | Session 保存对象和序列；录屏保存演出 | Raw Take 原子进入 Project Truth，并要求中断恢复 |

### 7.1 核心差异

Patatap 没有音乐时钟，表达完全来自人的输入时间。Incredibox 几乎把时间问题全部
封装在 Loop 里。Seaquence 把时间显式交给每个 Voice 的 Step Sequencer。LMDJ 同时
保留人的 Raw Timing 和可循环 Pattern，是四者中最强调“演奏事实与编辑结构分离”的模型。

---

## 8. 视觉角色与视听绑定

| 机制 | Patatap | Incredibox | Seaquence | LMDJ |
| --- | --- | --- | --- | --- |
| 视觉主要作用 | 瞬时表演反馈 | 角色化显示当前 Loop、类别和组合；Bonus 提供奖励动画 | 视觉对象本身就是 Voice、Sequence、Motion 和 Mixer Position | 当前确认工作台以状态化 Surface、Pad、Transport 为主；视听乐器层未决定 |
| 视觉生命周期 | 数百毫秒到数秒后消失 | Avatar 状态持续到用户移除；Bonus 有独立动画 | Creature 持续存在于 Session | Pad、Pattern、Performance 是持久产品对象；Visual Object 未进入确认模型 |
| 视听绑定键 | 同一 Event ID 绑定 Sample 与 Animation | Costume / Sound Icon 绑定 Loop 与 Character State | Creature ID 绑定 Synth、Notes、Body、Motion、Position | Pad Event 绑定 Pad Slot / Asset；视觉绑定语义未决定 |
| 音频反应 | 不是通用频谱 Visualizer | 角色动画与预制 Loop 同步 | Motion 由 Synth / Sequencer 参数和 Physics 关联 | 未批准自动 Audio-reactive、事件驱动或混合方案 |
| 用户编辑视觉 | 无 | 通过选择 Costume / Loop 间接改变角色 | 编辑 Voice 和位置会直接改变视觉/运动 | 未决定 |
| Visual Scene | Palette + Sound Set 切换，但不保存为用户 Scene | Version 提供整体世界；Mix 记录角色状态 | Session / Mixing Dish 是持久视觉环境 | `Scene` 作为视觉产品对象尚未批准进入新 64-Pad 模型 |
| 视觉输出 | 依赖外部录屏 | 分享 Player 重放角色和 Mix；App 可导出 MP3 而非通用视觉工程 | Apple ReplayKit 音频/视频记录 | Stereo WAV、Replay、Export 已在音频/表演模型中；视觉录制格式未决定 |

### 8.1 三种完全不同的视觉模型

```text
Patatap：Visual Feedback
Incredibox：Visual State + Character Performance
Seaquence：Visual Domain Object
```

这三个词不能互换：

- Feedback 可以不进入 Project；
- State 必须能随 Mix Replay 恢复；
- Domain Object 必须参与编辑、持久化、复制、分享和版本关系。

LMDJ 当前没有决定视觉要停在哪一层。因此本对照只提供语言，不替产品做选择。

---

## 9. 对象、状态与持久化

| 机制 | Patatap | Incredibox | Seaquence | LMDJ |
| --- | --- | --- | --- | --- |
| 顶层对象 | 无用户 Project | Version + Mix / Mixlist | Session | Beat Project |
| 内容对象 | 预制 Animation / Sound Set | Sound Icon、Avatar State、Bonus | Creature / Voice、Sequence、Preset | Asset、Pad、Take、Pattern、Performance、Provider Attempt |
| 用户可编辑对象 | 当前 Palette 和当下演奏 | 角色槽状态、Mute/Solo、录制动作 | Voice 参数、Notes、Position、Global Session | Pad Slot、Derived Asset、Raw Take、Pattern、Performance |
| Save / Load | 无 | Paid App Mixlist；Public / Private Mix | Local Session Preset + Online Share | Save / Load / Duplicate / Export 是 Beat Project 能力 |
| 不可变/派生 | 无显式 Lineage | 官方内容不可由用户深度编辑 | Session Share 保留 Remix History Link | Runtime Snapshot 不持久为 Project Truth；Derived Asset 记录 Lineage |
| 冲突与恢复 | 页面刷新即回到默认 | Mix 在线保留受产品规则影响 | Session 本地保存；社区链接另有服务依赖 | Raw Take 中断恢复、Revision、Provider Attempt 有明确边界 |
| 外部素材引用 | 无 | 无用户 Sample Import | 内置 Synth，不依赖外部 Sample | Artifact 输入、Derived Asset、Provider Sink 和 Export 都是正式边界 |

### 9.1 状态复杂度排序

```text
Patatap Event
  < Incredibox Mix Action State
  < Seaquence Session Graph
  < LMDJ Project + Asset Lineage + Runtime Snapshot + Attempt Evidence
```

这里的“大于”表示状态种类和恢复责任更多，不表示产品价值更高。

---

## 10. Performance、Record、Replay 与 Resample

| 机制 | Patatap | Incredibox | Seaquence | LMDJ |
| --- | --- | --- | --- | --- |
| Live Performance | 26 Event 即兴叠加 | 加入/移除 Loop、Mute/Solo、Bonus | 移动 Voice、编辑 Step/参数、实时混音 | Pad、Pattern、Bank、Momentary FX |
| Record | 无 | 记录约三分钟内的全部 Mix Action | ReplayKit 录制 Audio / Video | Raw Take、Performance Events、Stereo WAV |
| Replay | 无 | 分享页按动作重放 Mix | Session 可重新运行；录制结果可播放 | Performance Replay 是已确认能力 |
| Edit After Record | 无 | Mix 主要作为完成记录管理，不是自由 Timeline | Session Object 可继续编辑 | Raw Take 与 Pattern 分离；Pattern 可编辑、复制、Quantize |
| Resample | 无 | 无把 Mix 变成新可演奏素材的产品原语 | 无 Sample-based Resample 主循环 | 完整演出或片段可 Resample 成新 Asset 并进入 Pad |
| FX | 无用户参数；声音已设计 | Loop / Bonus 内容内置，不开放通用 FX 编辑 | Filter、Envelope、Delay 等 Synth / Voice 参数 | Filter、Delay、Reverb、Stutter、Gate、Reverse、Crush、Roll |
| Hold | 按键重复触发，不是正式 Hold State | Loop 持续到移除；Mute/Solo 是显式状态 | Voice / Sequence 持续运行 | Momentary FX 的 Hold 必须是显式状态 |

### 10.1 对照判断

Incredibox 的 Record 解决“把一次好玩的组合变成可传播作品”；Seaquence 的 Session
解决“让生成系统可以继续编辑和再次运行”；LMDJ 的 Raw Take / Pattern / Performance /
Resample 则把人的演奏、可编辑循环、现场操作和新声音派生分成不同对象。

Patatap 没有这些对象，所以它只能证明即时反馈，不足以证明 LMDJ 的表演记录边界。

---

## 11. Export、Share 与 Community

| 机制 | Patatap | Incredibox | Seaquence | LMDJ |
| --- | --- | --- | --- | --- |
| 本地保存 | 无 | Paid App Mixlist | Session Preset | Beat Project |
| 音频导出 | 无 | Paid App MP3 | ReplayKit Audio | Stereo WAV、Samples、开放 Creator Export |
| 视频导出 | 无，依赖系统录屏 | 分享 Player 有动画重放；FAQ 主导出为 MP3 | ReplayKit Video | 未决定视觉输出 |
| 结构化导出 | 无 | Mix URL 表达动作重放，但不作为开放制作格式 | Session Link / MIDI | Project / Pattern / MIDI / Artifact Export 边界由 LMDJ 定义 |
| 分享链接 | 无作品链接 | 每个保存 Mix 获得 URL | Session Link | 未定义面向公众的作品分享服务 |
| Public / Private | 无 | Paid App 可选；Safe Mode 强制 Private | Share 到 Galaxy | Project 隐私与发布不是本对照的已确认范围 |
| 社区发现 | 无 | Live、Top 50、投票、Incredimods | Galaxy、Remix History | 首版不做多人实时协作；Marketplace 也不是首版 |
| 内容回流 | 创作者单向更新 Sound Set | 官方 Version + 精选 Community Mod | 社区 Session 可浏览和 Remix | 用户素材、Sound Set 和 Provider 结果边界分开 |

### 11.1 传播机制差异

- Patatap：体验天然适合录屏，但传播完全交给外部平台；
- Incredibox：作品 URL、播放器、投票和榜单是产品飞轮的一部分；
- Seaquence：分享的不是扁平音频，而是可继续运行和 Remix 的 Session；
- LMDJ：当前首要出口是用户继续制作所需的开放音乐资产，不是社区 Feed。

---

## 12. 商业模式与内容扩展

| 机制 | Patatap | Incredibox | Seaquence | LMDJ |
| --- | --- | --- | --- | --- |
| 入口价格 | Web 免费；iOS `US$1.99` | Web / Mobile Demo；全平台 Paid App `US$4.99` | App 免费；Seaquence Complete 单次内购 `US$9.99` | 未由本研究改变 |
| 主要收入结构 | 低价离线 App、周边、音乐、创作者支持 | 付费 App、学校服务；免费 Web 依靠广告覆盖运营 | 单次 Complete 解锁支持两人工作室 | Product / Content 商业模型不由本文决定 |
| 内容扩展 | 官方固定 Sound / Palette Set | 官方 Version、未来 Version、精选 Incredimods | Preset、用户 Session、Synth 深度 | 用户素材、Derived Asset；Sound Set 只做已规划 Catalog，不做首版 Marketplace |
| 微交易 | 无 | Paid App 无广告、无微交易 | 单次 IAP | 未决定 |
| 社区内容 | 无内置入口 | 2025 起将精选 Mod 纳入 Paid App | Galaxy Session 与 Remix | Provider 和用户素材不能自动等同 Marketplace Content |
| 内容成本 | 每套声音 + 视觉策划 | Loop、角色服装、动画、Bonus、完整风格世界 | Synth Engine、Preset、Session Infrastructure | 音频处理、Lineage、Provider、Project、Export 和未来内容授权 |

### 12.1 公开规模信号

这些是官方在特定时间公开的数据，不是当前活跃用户：

- Patatap：2016 年公布数百万 Pageviews，接近 90,000 次半小时以上互动；
- Incredibox：2025 Press Kit 记录免费 Demo 自 2009 年超过 106M 玩家，Paid App
  超过 3.3M 下载；
- Seaquence：官方 About 记录原 Flash 社区累计超过 300,000 个 Composition；
- LMDJ：没有可与这些公开消费产品直接比较的已发布用户规模。

---

## 13. 授权与用户作品边界

| 机制 | Patatap | Incredibox | Seaquence | LMDJ |
| --- | --- | --- | --- | --- |
| 代码/产品声明 | README 写明 MIT；没有发现独立 Asset License | 所有 Music / Design / Code 明确受版权保护 | 闭源 App；官网未提供普遍资产再分发许可 | Contract、Code 与 Content License 分开治理 |
| 用户输出 | 官网没有找到清晰的商业输出授权 | 官方明确 Mix 只可用于私人、非商业和教育项目 | 官网说明可录音录像和分享；商业输出边界未在本次找到明确条款 | 用户素材 Ownership、Sound Set License、Export Rights 必须可追踪 |
| 嵌入第三方产品 | README 不能自动证明音频/动画 OEM 边界 | 明确禁止在商业 App、Game、Website、音乐或商品中使用内容 | 需要另行获得 Okaynokay 书面授权 | 普通 Royalty-free 不足；需要 OEM / Embedded / End-user Export 权利 |
| 社区内容 | 无 | Incredimods 通过官方选择和 mod.io 进入 App | 用户 Session 公开分享和 Remix | 未来用户/创作者内容需要独立 Contract 和 Moderation 边界 |

### 13.1 关键判断

“用户可以在软件里做音乐”与“用户可以商业发行结果”不是同一权利；“代码可查看或 MIT”
也不自动等于“声音可以随另一个乐器分发”。

Incredibox 是本组中边界最明确的例子：即使 Paid App 允许导出 MP3，官方仍明确限制
Mix 只能用于私人、非商业和教育项目。LMDJ 若要以 Creator Export 为核心，必须避免
让产品能力和内容授权发生这种隐性冲突。

---

## 14. 学习成本、自由度与失败方式

| 维度 | Patatap | Incredibox | Seaquence | LMDJ |
| --- | --- | --- | --- | --- |
| 初始学习成本 | 极低 | 极低 | 低，但深层参数较高 | 目标低于完整 DAW，但素材处理和对象更多 |
| 音符自由度 | 中：用户自由决定时序，声音固定 | 低：组合预制 Loop | 高：Voice、Step、Scale、Synth 可编辑 | 高：用户素材、Timing、Velocity、Pattern、FX、Resample |
| 视觉自由度 | 低：动画固定，只决定触发时序 | 低：角色状态固定，组合可变 | 高：对象、位置、运动和参数共同变化 | 未决定视觉自由度 |
| 作品可恢复性 | 无 | Mixlist / URL | Session | Project Truth、Journal、Revision、Artifact |
| 最常见失败 | 加载、无声、闪烁不适、无法保留表演 | 组合不满意、网络分享、内容授权限制 | 参数复杂、旧版本维护、Session 服务依赖 | Provider Failure、输入质量、映射、实时性能、Project Recovery |
| 产品膨胀风险 | 很低 | 内容、Mod 和社区治理 | Synth / MIDI / Session 功能复杂度 | Sampler、AI、Pattern、Perform、Provider、Export 同时扩张 |

### 14.1 自由度不是单轴

Patatap 允许自由时序，却不给声音设计自由；Incredibox 给组合自由，却不给 Note 编辑
自由；Seaquence 给对象和参数自由，却不处理用户采样；LMDJ 给用户素材和演奏自由，
但必须用稳定 Slot、Project Truth、Candidate 和 Runtime Snapshot 管理复杂度。

---

## 15. LMDJ 在四者中的位置

### 15.1 LMDJ 不是 Patatap Plus

LMDJ 的核心价值来自：

- 任意声音或完整歌曲；
- 捕获、导入和派生 Asset；
- A–D 四个稳定 16-Pad Bank；
- 用户 Raw Take；
- 可循环、可编辑 Pattern；
- Pattern / Bank / FX Performance；
- Export 和 Resample；
- AI / Provider 辅助材料处理和候选，而不是替用户完成 Beat。

这些都不是 Patatap 的对象。Patatap 只能作为即时 AV Feedback 的研究参考。

### 15.2 LMDJ 不是 Incredibox 的用户素材版

Incredibox 的核心安全感来自完全预制、同步并经过策划的 Loop。LMDJ 必须面对来源不一、
长度不一、质量不一的用户素材，并保留 Lineage、错误和可恢复状态。

Incredibox 最有比较价值的机制是：

- 角色状态如何让 Loop 组合可读；
- Record 如何把状态操作变成可重放 Mix；
- Share URL、Player 和榜单如何形成传播闭环；
- 明确授权如何限制用户输出用途。

这些是比较结论，不是 LMDJ 已批准功能。

### 15.3 LMDJ 不是 Seaquence 的 Sample 版

Seaquence 的视觉对象拥有声音、序列、运动和空间位置，是完整 Domain Object。LMDJ
当前 Pad 引用 Sound Asset，Pattern 引用 Pad Slot，Runtime Snapshot 与 Project Truth
分离。直接把视觉属性塞入 Pad 会改变对象语义，不能通过竞品相似性默认发生。

Seaquence 最有比较价值的机制是：

- 一个对象如何同时承担声音、序列、视觉和混音语义；
- Session 如何保存可继续运行的生成系统；
- 分享如何保留 Remix History；
- MIDI 和内部 Audio Engine 如何保持可替换关系。

同样，这些只是研究输入。

### 15.4 当前最准确的组合描述

如果只描述机制来源，而不转成功能建议：

```text
Patatap
  提供 Event-to-AV Feedback 参照

Incredibox
  提供 Guardrailed Loop State + Performance Replay + Sharing 参照

Seaquence
  提供 Persistent Audiovisual Domain Object 参照

LMDJ
  已有 User Material + Stable Pad + Raw Take + Pattern + Performance + Resample 主轴
```

---

## 16. 本对照刻意不回答的问题

以下问题需要独立产品讨论、规格和验证，本文不作选择：

1. LMDJ 的视觉来源是用户导入媒体、实时生成图形、摄像头、自动 Audio-reactive，
   还是多种来源并存？
2. 视觉是一次性 Feedback、可重放 State，还是 Project 中的 Domain Object？
3. Pad、Pattern、Performance 与视觉之间是否存在一对一绑定？
4. Pattern 切换是否对应 Visual Scene 切换，以及切换边界是什么？
5. Momentary FX 是否共享音频与视觉参数？
6. Performance Replay 是否要求视觉结果逐帧确定性复现？
7. 视觉结果是否需要视频导出、直播输出、外部 VJ 协议或灯光控制？
8. 视觉资产的版权、OEM 嵌入、终端用户商用与导出权如何定义？
9. 视觉能力属于首版 Creator、后续 Product Assembly，还是独立 Host？

列出这些问题的目的，是防止在机制对照中悄悄把它们写成结论。

---

## 17. 主要来源

### 17.1 Patatap

- [Patatap 官网](https://patatap.com/)
- [Patatap GitHub](https://github.com/jonobr1/Patatap)
- [Patatap - Experiments with Google](https://experiments.withgoogle.com/patatap)
- [Patatap App Store](https://apps.apple.com/us/app/patatap/id880626868)
- [Jono Brandel Interview](https://www.itsnicethat.com/articles/patatap-1)
- [Jono Brandel and Lullatone Interview](https://www.hypebot.com/patatap-really-is-as-fun-and-artsy-as-it-sounds/)
- [Typatone Statistical Analysis](https://typatone.com/stats.html)

### 17.2 Incredibox

- [Incredibox 官网](https://www.incredibox.com/)
- [Incredibox App Features](https://www.incredibox.com/app)
- [Incredibox FAQ](https://www.incredibox.com/info/faq)
- [Incredibox Press Kit](https://www.incredibox.com/info/press)

### 17.3 Seaquence

- [Seaquence 官网与 Feature List](https://seaquence.app/)
- [Seaquence Guide](https://seaquence.app/guide)
- [Seaquence About / History](https://seaquence.app/about)
- [Seaquence App Store](https://apps.apple.com/us/app/seaquence/id1106270489)

### 17.4 LMDJ 当前权威资料

- [Playable Beat Instrument 与新内核设计](../design/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md)
- [LMDJ 产品决策日志](../prd/decision-log.md)
- [LMDJ Version Management](../governance/version-management.md)
- [LMDJ Preset / Sound Pack 采购与授权研究](./2026-07-30-sound-pack-sourcing-and-licensing.md)

---

## 18. 研究边界与版本管理

- 第三方产品事实以 2026-08-02 可访问的官方资料为准，后续版本、价格和服务可能变化。
- Patatap、Incredibox 和 Seaquence 均未在本轮完成当前多设备真机实测。
- LMDJ 列描述已批准方向和设计语义，不宣称所有能力已经发布或产品验证。
- 本文没有批准任何视觉来源、Visual Pad、Visual Scene、AV FX、录制格式或技术栈。
- 本文不是法律意见；内容嵌入、用户商用和导出权必须单独审查。
- Version impact: none。本文只增加机制研究，不改变 Product Build、Core Module、
  Provider、Contract、Project Truth 或公开产品行为。
