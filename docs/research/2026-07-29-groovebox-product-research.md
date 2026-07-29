# Groovebox 产品研究与 LMDJ 启示

> 研究日期：2026-07-29
>
> 研究对象：[Groovebox - Beat Synth Studio](https://apps.apple.com/us/app/groovebox-beat-synth-studio/id1242847278)
>
> 开发者 / Seller：Focusrite Audio Engineering Ltd.；产品品牌属于 Ampify / Novation 体系
>
> 研究性质：竞品、工作流与产品设计研究；不代表 LMDJ 已批准的功能范围或实施计划

## 0. 结论先行

Groovebox 是一款 **Synth / Drum Machine / Pattern-first 的移动音乐草图工具**。它不是
完整 DAW，也不是以用户采样为核心的 Sampler。产品最擅长的是让用户在几分钟内获得一段
“已经好听”的电子音乐循环：

```text
新建 Project
  → 添加 Drumbox / Synth Track
  → 选择音色和预制 Pattern
  → 用 Pad / Scale Keyboard 演奏，或在 Note Grid 画音符
  → 调整少量高价值 Macro
  → 录制参数 Automation
  → 用 Sections 切换不同 Pattern 组合
  → 导出 Mix / ZIP / Ableton Live Project
```

它的核心产品价值不是功能深度，而是四件事的组合：

1. **第一次触摸就有完成度较高的声音。**
2. **Pattern 既是内容，也是新用户的创作脚手架。**
3. **演奏、编序、音色调整和自动化始终围绕同一个 Instrument 展开。**
4. **产品主动把“完成制作”交给 Ableton Live 等外部环境。**

它的长期短板也很集中：

- `Sections` 更接近需要用户手动触发的 Scene / Pattern Matrix，不是自动播放的 Song
  Arrangement；
- 官方不提供 Project File 的跨设备传输或云同步，只有整机 iCloud
  Backup / Restore 路径；
- 第三方 MIDI Controller 没有手动 Mapping，深度控制主要绑定 Novation Launchkey；
- App Store 仍宣传已被 Apple 在 iOS 13 废弃的 Inter-App Audio，同时没有公开
  AUv3 能力；
- 当前公开版本 `2.10.5` 发布于 2024-04-30。到研究日已超过两年没有新的 App
  Binary，但 2025 年仍有更新过的硬件支持文档，因此更准确的状态是
  **低频维护 / 存量经营**，不能仅凭版本日期断言已经停产。

### 对 LMDJ 最重要的启示

LMDJ 不应复制 Groovebox 的封闭 Synth + Soundpack 商业模式，但值得吸收它的
**低摩擦创作入口**：

- AI 生成 Patch 后，不应先把用户带进文件、参数或分析结果，而应先让 16 Pad 和一个
  默认 Pattern 立即发声；
- 默认 Pattern 应是可删除、可覆盖、可继续编辑的脚手架，而不是不可解释的自动播放；
- 高级编辑应围绕当前 Pad / Role 逐层展开，不改变
  `Upload → Patch → Play → Export` 的首层心智模型；
- `Scene`、`Pattern`、`Arrangement`、`Performance Cue` 必须分清，不能像
  Groovebox 一样用 `Sections` 同时暗示“编曲”和“现场切换”；
- Project 可恢复、跨设备历史和开放 Export 是创作信任的一部分，不能只作为基础设施
  细节处理。

---

## 1. 研究范围与证据方法

### 1.1 覆盖范围

本研究覆盖：

- 产品定位、历史、当前公开状态；
- 用户、场景与核心 Jobs to Be Done；
- Instrument / Pattern / Section 工作流；
- 触屏演奏、Note Sequencer、Automation、Mixer；
- Soundpack / Pro Feature 商业模式；
- MIDI、Ableton Link、Ableton Export 与 iOS 音频生态；
- 项目保存、跨设备、导出与声音授权；
- App Store 用户反馈；
- 与 LMDJ 当前 Creator Core 的差异及可借鉴点。

不覆盖：

- Groovebox 私有 Synth Engine、DSP 实现或源代码逆向；
- 通过真实 iPhone / iPad 安装后的延迟、CPU、稳定性和听感测试；
- 所有历史 Soundpack、Preset、Pattern 和内购项目的完整目录；
- 收入、转化率、活跃用户和留存；
- 对用户作品授权的法律意见。

### 1.2 证据等级

| 标记 | 含义 | 使用方式 |
| --- | --- | --- |
| **官方事实** | Apple、Focusrite、Novation、Ampify、Ableton、Apple Developer 文档 | 作为当前公开能力的主要依据 |
| **官方历史资料** | Ampify 官方 Vimeo、Focusrite 历史公告、历史版本说明 | 只说明当时已公开的能力 |
| **用户反馈** | Apple App Store Reviews | 说明体验主题，不自动视为产品规格 |
| **第三方资料** | 有日期、作者和具体测试对象的评测或报道 | 补充历史和体验，不能覆盖官方资料 |
| **分析判断** | 由多个公开事实推导的产品解释 | 明确与官方宣称分开 |
| **待验证** | 官网缺失、资料冲突或需要真实设备确认 | 不写成确定事实 |

### 1.3 本次实证边界

本研究做了：

- 读取当前美国区 App Store 页面；
- 读取 Apple iTunes Lookup API 的版本、发布日期、评分和截图资产；
- 逐张检查 9 张 iPad 和部分 iPhone 官方商店截图；
- 检查 Novation 当前产品页和 Ampify 当前帮助中心；
- 检查 Ableton Link / Export 和 Apple iOS Audio 官方边界；
- 抽取 Apple 美国区 RSS 中研究日可见的 50 条最近评论，做关键词辅助的主题归类。

本研究没有在真实 iOS 设备安装 `2.10.5`。因此涉及实际触摸手感、音频中断、具体
IAP 价格、Project 内最大 Track / Section 数、导出文件结构和当前 Bug 的内容仍需
真机复核。

---

## 2. 产品快照

| 维度 | 研究日公开状态 | 证据 |
| --- | --- | --- |
| 产品类型 | iPhone / iPad 独立 Groovebox / Music Sketchpad | Apple / Novation |
| 首次发布 | 2017-06-13 | Apple Lookup API |
| 当前公开版本 | `2.10.5` | Apple |
| 当前版本日期 | 2024-04-30 | Apple |
| 最低系统 | iOS / iPadOS 15.0 | Apple |
| 价格 | 免费下载 + App 内购买 | Apple |
| 当前美国区评分 | 约 4.74 / 5，4,735 个评分 | Apple Lookup API，随时间变化 |
| 核心乐器 | Drumbox、RetroBass、Poly-8、MiniMon、Horizon | Apple / Novation |
| 输入 | 触屏 Pad / Keys、Note Grid、MIDI Controller | Apple / Ampify |
| 编曲 | Pattern + Sections | Apple / Ampify |
| 自动化 | 可录制 Synth Parameter Automation | Apple / Novation |
| Mixer | iPad 多通道 Mixer；iPhone 为 Instrument-focused 控制 | Apple / Ampify 历史资料 |
| 同步 | Ableton Link | Apple / Ampify / Ableton |
| 导出 | Mix、批量 ZIP、Ableton Live Export | Apple / Ableton |
| 跨设备 Project | 无 Project File 传输；仅通过整机 iCloud Backup / Restore | Ampify Support |
| 订阅 | Groovebox 不支持 Ampify Premium / Launchpad Premium | Ampify Support |
| 深度 MIDI 控制 | 主要支持 Novation Launchkey；无通用手动 Mapping | Ampify Support |
| 当前公开语言 | English | Apple |

Apple 页面将 Seller 标为 Focusrite Audio Engineering Ltd.，Novation 当前官网将
Groovebox 放在其 iOS Software 下，Ampify Help Centre 继续承担产品支持。它不是三个
彼此独立的产品方，而是 Focusrite Group 内部的品牌与产品关系。

---

## 3. 产品定位

### 3.1 它解决什么问题

Groovebox 的主要 Job 不是：

> “让我在手机上完成一首拥有完整 Timeline、Audio Track、Plugin、Routing 和
> Mastering 的作品。”

而是：

> “当我有几分钟时间时，让我立刻得到一个好听的鼓、Bass 和 Synth Loop，并能继续把
> 它带到更大的制作环境。”

这使它同时承担三种角色：

1. **Idea Generator**：Preset + Pattern 快速提供起点；
2. **Playable Instrument**：Pad、Scale Keyboard 和实时 Macro 让它不是纯 Loop
   Browser；
3. **DAW 前置 Sketchpad**：用 Ableton Export、ZIP 或 Mix 把结果交给外部环境。

### 3.2 它不是什么

根据当前公开资料，Groovebox 不是：

- 用户录音、导入、切片、重采样为中心的 Sampler；
- 可加载第三方 AUv3 Instrument / Effect 的 Host；
- 以 AUv3 Plugin 形式运行在其他 iOS DAW 内的 Instrument；
- 拥有线性 Timeline 和自动 Section Chaining 的完整 Song Arranger；
- 跨 iPhone / iPad 自动同步 Project 的 Cloud Workspace；
- 为所有 MIDI Controller 提供 MIDI Learn 的开放控制环境。

Ampify 的 Audio Import 帮助文档只列出 Launchpad 和 Blocs Wave，没有把 Groovebox
列入支持对象。Apple 当前产品说明也没有记录 Audio Import / Recording / Sampling。
因此更准确的产品分类是 **基于内置 Drum / Synth Engine 和内容包的 Groovebox**。

---

## 4. 核心对象与信息架构

根据官方截图、产品说明和用户反馈，可以把 Groovebox 的公开心智模型还原为：

```text
Project
├─ Global Music Settings
│  ├─ Tempo
│  ├─ Key
│  ├─ Scale
│  └─ Swing
├─ Track / Instrument 1..N
│  ├─ Instrument Type
│  ├─ Soundpack
│  ├─ Preset / Kit
│  ├─ Pattern per Section
│  │  ├─ Notes / Drum Hits
│  │  └─ Automation
│  └─ Channel Level
└─ Sections
   └─ Track × Section Pattern Matrix
```

### 4.1 Project

Project 是保存创作内容的顶层对象。官方说明支持 Rename、Duplicate 和 Delete。
Ampify Support 明确表示当前不能导出 Project File 并发送到另一设备。

### 4.2 Track 与 Instrument

主界面把每条 Track 直接表现为一种 Instrument，使用稳定颜色区分：

- Drumbox：橙黄；
- Horizon：紫色；
- MiniMon：绿色；
- RetroBass：青色；
- Poly-8：橙红。

这种颜色同时出现在 Track Tab、Instrument Editor、Piano Roll Note、Mixer 和
Section Matrix 中。颜色不是装饰，而是跨页面维持对象身份的导航系统。

2017 年 Ampify 官方介绍曾明确记录 iPad 为 8-track Mixer；当前 Apple / Novation
页面只写“multi-channel mixer”，没有再次明确最大 Track 数。是否仍固定 8 条需真机
确认。

### 4.3 Pattern

Pattern 是 Track 在一个循环内的 Note / Hit 数据。用户可以：

- 从 Soundpack 选择现成 Pattern；
- 用 Pad 或 Scale Keyboard 录制；
- 在 Note Grid / Piano Roll 画入和编辑 Note；
- 记录 Instrument Parameter Automation；
- 删除自动生成的 Pattern 后重写自己的内容。

这里最有价值的设计是：**内容购买得到的不只是声音，还包含如何使用这个声音的音乐行为。**

### 4.4 Section

iPad 官方截图把 Section 表现为二维矩阵：

- 列：Track / Instrument；
- 行：Section；
- 单元格：该 Track 在该 Section 中使用的 Pattern。

官方把它描述为“build a song structure”。但当前公开资料没有证明它可以按
`A × 1 → B × 2 → C × 1` 自动线性播放。多条 App Store 评论持续要求 Song Mode，
并描述 Section 需要手动切换。

因此更准确的分析是：

> Groovebox 的 Section 是 Scene / Pattern Combination Launcher，而不是完整的
> Timeline Arrangement。

部分用户还报告 Instrument、Tempo、Key、Mute 等状态在 Section 之间是全局共享，而
不是每个 Section 独立。这个行为对编曲影响很大，但属于用户反馈，必须用当前版本真机
验证后才能写成正式规格。

### 4.5 Preset 与 Soundpack

Soundpack 同时承担：

- Sound / Kit；
- Preset；
- Rhythm / Melody Pattern；
- Genre / Mood Discovery；
- App 内付费商品。

Pro Features 则进一步开放 Instrument 的高级参数和自定义 Preset 保存。它让同一
Instrument 同时服务两类用户：

- 新用户：选声音、选 Pattern、立即播放；
- 高级用户：继续进入 Oscillator、Envelope、Filter、Effects 等参数页。

---

## 5. 五种乐器

| Instrument | 公开角色 | 交互与能力 | 证据边界 |
| --- | --- | --- | --- |
| **Drumbox** | Drum Machine | Drum Pad、Kit / Pattern、每个声音的 Waveform 和 Macro、Effects | 官方截图和产品说明；底层是纯 Sample、Synth 或 Hybrid 未公开 |
| **RetroBass** | Analogue-style Bass Synth | 面向 Bassline，支持 Pattern、Keys、Macro、Automation、Pro 参数 | Apple / Ampify 官方介绍 |
| **Poly-8** | 八声部 Polyphonic Synth | Chord / Melody、Macro、Automation、Pro 参数 | Ampify 官方历史介绍 |
| **MiniMon** | Mono Wavetable Synth | Bass / Lead，Wavetable Modulation，Pattern、Macro、Pro 参数 | Ampify 官方 Vimeo |
| **Horizon** | Polyphonic Ambient Digital Synth | Pads、Dreamy Melody、Analogue Organ 方向 | Apple / Novation |

### 5.1 “乐器”而不是“音轨插件”

每个 Track 的编辑页同时包含：

- 上半部分：Instrument Controls；
- 下半部分：可演奏 Pad / Keyboard；
- 顶部：Track Switcher、Transport 和编辑入口。

用户调整参数后不需要退出 Editor 才能试听。这个布局把
`选择声音 → 修改声音 → 演奏声音` 保持在一个触摸上下文中。

### 5.2 Macro-first，Deep-later

商店截图显示，默认页只暴露少量高影响控制，例如：

- Filter；
- Reverb / Delay；
- Detune / Colour；
- Voice Mix；
- Gain / Pitch；
- Drum Shape。

Pro Features 再展开 Oscillator、Envelope、Filter 等更深页面。这个 Progressive
Disclosure 的优点是首屏可理解，代价是高级控制与“完整乐器”被商品化。

### 5.3 Automation 是 Instrument 的一部分

Automation 不是独立 DAW Lane 的首层入口，而是从当前 Instrument 参数进入。官方截图
显示用户可以从 Automation 菜单选择 Oscillator、Filter 等参数并记录变化。

这符合 Groovebox 的整体原则：先保持演奏流，再逐步增加表达，不先要求用户理解完整
DAW Automation Architecture。

---

## 6. 核心创作工作流

### 6.1 路径 A：由 Pattern 快速得到可用循环

```text
新建 Project
  → 添加 Instrument
  → 浏览 Soundpack
  → 选择 Preset / Kit
  → 选择或随机获得 Pattern
  → 添加第二、第三条 Track
  → 调整 Tempo / Key / Scale
  → 播放
```

这个路径适合：

- 没有明确旋律的用户；
- 只想快速获得风格方向的 Producer；
- 在通勤、候机或短休息中记录想法的人；
- 需要一个可以继续修改而不是只播放 Loop 的起点的人。

### 6.2 路径 B：直接演奏

```text
选择 Track
  → Drum Pad 或 Scale Keyboard
  → Record
  → Quantized / Unquantized Performance
  → 回放 Pattern
  → 必要时进入 Note Grid 修正
```

Scale / Key 限制降低了在小屏触控上演奏错误音的概率。外接 Launchkey 后，官方支持还把
Pad、Keyboard、Knob、Fader、Transport、Mute、Track Select 和 Section Up / Down
整合成硬件工作流。

### 6.3 路径 C：画 Note

官方 iPad 截图显示一个全屏 Note Grid：

- 纵轴是 Pitch；
- 横轴是 Time；
- Note 使用当前 Instrument 颜色；
- 底部保留 Pattern Overview。

它的产品角色不是完整 MIDI Editor，而是当实时演奏不够准确时，对 Pattern 进行直接
修正。

### 6.4 路径 D：实时调整并录制 Automation

```text
播放 Pattern
  → 打开 Instrument
  → 转动 Macro / Parameter
  → Record Automation
  → Pattern 内产生动态变化
```

这一步把静态 Preset 变成用户自己的表演。它也是 Groovebox 从“Loop Pack Player”
走向“Instrument”的关键。

### 6.5 路径 E：用 Sections 扩大想法

```text
复制当前 Section
  → 替换部分 Track 的 Pattern
  → 增加 / 删除 / 移动 Section
  → 在播放过程中手动切换
```

它可以建立 Intro / Main / Break 等差异，但没有足够证据表明可以保存一个自动播放的
完整 Song Order。这解释了为什么官方称它能 Build Songs，而长期用户仍持续要求
Song Mode：两者使用了不同的“Song”定义。

### 6.6 路径 F：离开 Groovebox

公开出口包括：

- 导出当前 Mix；
- 批量导出为 ZIP；
- Ableton Live Export；
- 通过 Ableton Link 与同网络应用同步 Tempo、Beat 和 Phase；
- 使用 Audiobus / Inter-App Audio 与其他 iOS App 连接。

需要区分：

- **Ableton Link** 只负责音乐时间同步，不传输 Track、MIDI、Preset 或 Project；
- **Ableton Export** 生成可交给 Live 的 Project / Set 和相关音频；
- **Audio / ZIP Export** 是开放文件交付；
- **Inter-App Audio** 已被 Apple 在 iOS 13 废弃，不应再视为现代 iOS
  Integration 的长期方向。

---

## 7. UX 与视觉设计

### 7.1 Instrument-first Canvas

Groovebox 不从 File Browser、Timeline 或 Mixer 开始，而从可演奏 Instrument 开始。
用户进入 Track 后，屏幕主要空间给：

- 可听见结果的 Macro；
- 可直接触发的 Pad / Key；
- 当前 Track 的颜色和身份。

对移动音乐工具来说，这比“桌面 DAW 等比缩小”更适合触屏。

### 7.2 固定对象颜色

颜色在不同页面保持稳定，降低了切换页面的认知成本：

```text
Track Tab
  = Instrument Editor
  = Notes
  = Mixer Channel
  = Section Cell
```

LMDJ 当前已经给不同 Sound Role 使用视觉身份。Groovebox 的启示是：颜色和图标需要
跨 Pattern、Pad、Inspector、Export 状态保持一致，才能成为真正的对象导航。

### 7.3 下半屏永远可演奏

多个官方截图都把下半屏保留给 Pad / Keys。用户浏览 Preset、调 Filter 或修改
Envelope 时仍然可以立即试听。

这是一条很强的交互原则：

> 编辑面板不应把乐器从用户手里拿走。

### 7.4 iPhone 与 iPad 不是简单缩放

官方资料明确区分：

- iPad：多 Track Tab、全屏 Mixer、全屏 Section Matrix；
- iPhone：纵向 Track List、单 Instrument Focus、压缩后的 Section 交互。

它证明响应式音乐工具不能只做 CSS Reflow，还需要根据设备宽度调整任务分解。

### 7.5 内容浏览也是创作界面

Soundpack Browser 不是单纯 Store：

- Pack Artwork 提供风格线索；
- Preset 名称帮助想象声音；
- Pattern 让用户不必先写 Note；
- Preview 让购买和创作共用一条试听链路。

这种设计商业效率很高，但也会让“继续创造”与“继续购买”过于接近。Apple 用户评论中
同时存在“内购便宜且值得”和“免费入口过度依赖购买”两种反馈。

---

## 8. 商业模式

### 8.1 免费核心 + 永久内购

Groovebox 当前是：

```text
Free App
  ├─ 基础 Instruments / Essentials Packs / Patterns
  ├─ Soundpacks
  ├─ Instrument Expansion
  └─ Pro Features
```

Ampify Support 明确说明，Ampify Premium 和 Launchpad Premium 不适用于
Groovebox。由此可判断它不是订阅产品，而是以 Apple ID 绑定的永久 IAP 为主。

研究日美国区 App Store 公开的示例价格包括：

- 多个 Soundpack：`$0.99` 或 `$1.99`；
- Horizon Expansion：`$6.99`。

App Store 只展示动态选出的部分 IAP，不足以证明完整 Catalogue 和 Pro Features 的
当前价格。精确价格必须在当前地区的 App 内确认。

### 8.2 商品不只是声音

Groovebox 的 Content Pack 可以同时带来：

- 新 Kit / Preset；
- 新 Melody / Rhythm Pattern；
- Genre 定位；
- 对当前五种 Instrument 的再利用。

这让开发者可以在不扩展核心 App 架构的情况下持续增加商品。但长期也会出现一个风险：

> 内容在增长，工作流能力却不再增长。

2024–2026 的多条用户评论正是在表达这种不平衡：用户仍认可声音，但希望开发资源转向
Song Mode、Project Portability、AUv3、MIDI Out、Bug Fix 和更现代的 Sequencer。

### 8.3 声音授权

Ampify Support 表示：

- Ampify Sounds 为 Royalty-free；
- 大多数可以用于商业发行；
- 不能把单个声音原样作为独立素材公开；
- 历史 Ninja Tune Artist Series 有不同授权限制，相关作品不能按普通 Pack 规则
  商业发布。

因此不能把产品简单描述为“所有 Pack 都可无限商用”。使用具体 Pack 前仍应检查其
Licence。

---

## 9. 生态、导出与硬件

### 9.1 Ableton Link

Ableton 官方定义 Link 同步：

- Beat；
- Tempo；
- Phase；
- 可选 Start / Stop。

它不会传输：

- Audio；
- MIDI Note；
- Automation；
- Track；
- Project。

Groovebox 把 Link 作为 Jam / Sync 能力是正确的，但它不能替代 Export 或 Cloud
Project。

### 9.2 Ableton Export

Ableton 官方说明，支持 Ableton Export 的 iOS App 可以生成：

- `.als` Live Set；
- Set 所需的 Audio Files；
- 一个可传到桌面 Live 的 Ableton Live Project。

这让 Groovebox 可以把自身限制在快速创作，而不用承担完整 DAW 的混音、插件和交付。

LMDJ 当前的
[Stage 1 Creator Core 设计](../superpowers/specs/2026-07-24-stage1-creator-core-slice-design.md)
选择通用 Creator Export ZIP，而不直接生成 `.als`。Groovebox 证明“一键进入 Live”
有明显用户价值，但不意味着 LMDJ 应立即采用私有工程格式。对 LMDJ 当前 Stage 1，
更重要的是：

- ZIP 内容完整；
- Stems / Samples / MIDI / Metadata 清楚；
- Ableton Live 真实导入 Smoke 通过；
- 后续再决定是否增加 `.als` Convenience Layer。

### 9.3 MIDI Hardware

Ampify 2025-07-03 更新的 Support Article 显示，Groovebox 对多代 Launchkey 提供
不同程度的 iPad / iPhone 支持，包括 MK2、MK3、MK4。

官方历史演示中的深度映射包括：

- Drum Pad；
- Scale Key；
- Instrument Macro；
- Channel Volume；
- Play / Stop；
- Track Select；
- Mute；
- Section Up / Down。

同时官方明确：

- 其他 Controller 不能控制 Instrument / Effect Parameter；
- App 内没有手动 MIDI Mapping。

这是一种典型的生态策略：软件免费或低价，深度体验服务于自家硬件。但它降低了用户对
通用 Controller 的可配置性。

LMDJ 当前的 Generic MIDI + MIDI Learn 方向比 Groovebox 更开放，应保留这一点，不应
因为参考 Novation 的硬件整合而退化为厂商白名单。

### 9.4 Inter-App Audio 与 AUv3

Apple 官方文档明确：

- Inter-App Audio 在 iOS 13 已废弃；
- AUv3 是当前 iOS 第三方 Audio Instrument / Effect 的主要扩展模型。

Groovebox 当前 App Store 仍宣传 Inter-App Audio，但没有公开 AUv3 Instrument /
Host 能力。Apple 评论中也持续出现 AUv3 请求。

这说明其生态描述已经带有历史包袱。产品仍可独立使用，但与现代 iOS Music Production
Stack 的组合能力落后于活跃维护的 AUv3 产品。

---

## 10. 保存、恢复与用户信任

### 10.1 官方 Project Portability 边界

Ampify Support 在 2024-02-20 明确表示：

- 不能导出 Project File 并发送到另一设备；
- 只能把整个设备备份到 iCloud；
- 在另一设备恢复该 Backup 前，需要抹掉设备内容；
- 第三方 Backup App 不保证能恢复 Project。

这不等于“支持 iCloud Project Sync”。它只是 Groovebox 数据被纳入 Device Backup。

### 10.2 为什么这是严重的产品问题

创作 App 的价值会随 Project 数量持续积累。用户一旦拥有几十或几百个 Idea，设备迁移
就不再是边缘场景。

最近评论中出现了：

- 换手机 / iPad 后 Project 丢失；
- 多设备分别积累，无法合并；
- 不知道如何把大量 Sketch 继续发展；
- 担心 App 停止支持后作品不可恢复。

这些反馈说明：

> 音频文件能导出，不等于创作状态可持续。

### 10.3 对 LMDJ 的直接提醒

LMDJ 当前 “My Songs” 依赖浏览器拥有的 Submission / Job 恢复，不代表 Account-level
Asset Library 或跨设备历史已经成立；这一边界已经记录在
[LMDJ 状态与 Backlog](../superpowers/2026-07-10-status-and-backlog.md)。

Groovebox 的教训是：如果用户开始把 LMDJ 当作长期 Creator Workspace，Project
Portability 必须在以下三个层面说清楚：

1. 原始上传是否仍可访问；
2. Patch / Take / Edit State 是否可恢复；
3. 是否能在另一台设备继续编辑，而不是只能下载最终 ZIP。

---

## 11. 用户反馈样本

### 11.1 样本方法

本次读取 Apple 美国区 Customer Reviews RSS 在研究日返回的 50 条最近评论。

限制：

- 只覆盖美国区；
- “最近”不等于随机抽样；
- 高低分用户的发言概率不同；
- 关键词主题可以重叠；
- 用户可能把 Launchpad、Groovebox 或其他 Ampify 产品能力混淆；
- 评论描述的 Bug 未经本次真机复现。

因此下面只用于识别重复主题，不用于计算产品真实满意度或 Bug 发生率。

### 11.2 星级分布

| 星级 | 50 条最近评论中的数量 |
| --- | ---: |
| 5 | 30 |
| 4 | 10 |
| 3 | 7 |
| 2 | 1 |
| 1 | 2 |

这个结果与整体约 4.74 的高评分一致：产品即使多年缺少大更新，仍然拥有一批持续认可
声音与创作速度的用户。

### 11.3 主题计数

使用保守关键词对 50 条评论做重叠归类：

| 主题 | 命中评论数 | 典型含义 |
| --- | ---: | --- |
| 简单、好玩、快速获得灵感 | 18 | 最稳定的正面价值 |
| 音色或 Synth 质量 | 9 | 多次被评价为超出免费 App 预期 |
| 更新、Bug 或维护担忧 | 11 | 页面消失、Audio Cut、Automation、长时间未修 |
| Launchpad / AUv3 / MIDI / Output 等 Integration | 6 | 希望进入现代 iOS / Hardware Workflow |
| Song Mode / Section / Pattern Length | 5 | 希望自动编排完整歌曲 |
| 跨设备、迁移或备份 | 3 | Project Continuity 风险 |

### 11.4 正面反馈

重复出现的正面评价包括：

- 上手快；
- 很适合短时间写 Sketch；
- Preset / Random Pattern 能帮助突破空白页；
- Synth 声音在手机扬声器上也有完成度；
- 免费基础能力已经能创作；
- 内购 Pack 单价低；
- 不追求完整 DAW 反而让移动端更好用。

### 11.5 负面反馈

重复出现的负面评价包括：

- 缺少自动 Song Mode；
- Section 切换不够可预备、量化或自动化；
- Project 无法跨设备同步；
- 没有 AUv3；
- 没有 MIDI Out、通用 MIDI Learn 或多路 Audio Output；
- Note Editor / Time Signature / Pattern Length 受限；
- Synth Parameter Page 在部分设备出现黑屏或消失；
- Audio Voice、Kick 首拍、Volume Automation 被个别用户报告异常；
- 用户认为 Soundpack 更新多于 Workflow 改进。

这些负面反馈不能全部视为已确认 Bug，但它们共同指向一个产品结构问题：

> Groovebox 的第一小时体验优于第一百小时体验。

---

## 12. 产品状态判断

### 12.1 仍然活着的信号

- App Store 仍可下载；
- 2026 年仍有新评论和长期用户；
- 美国区整体评分仍高；
- Novation 当前官网仍保留 Groovebox 产品页；
- Ampify Help Centre 仍在线；
- MIDI Hardware 支持文档在 2025 年更新，并列出 Launchkey MK4。

### 12.2 进入低频维护的信号

- 当前 App Binary 仍是 2024-04-30 的 `2.10.5`；
- 2022–2024 的版本历史主要是兼容和 Bug Fix，而不是工作流扩展；
- 2017–2020 形成的主要产品结构至今没有公开的 Song Mode、Cloud Project、
  AUv3 或开放 MIDI Mapping；
- App Store 营销仍包含被 Apple 废弃的 Inter-App Audio；
- 最近评论持续询问是否仍在开发。

### 12.3 结论

现有证据支持：

> Groovebox 是一个有稳定长尾用户、声音资产和品牌入口的成熟存量产品，目前呈现低频
> 维护状态。

现有证据不支持：

- “Groovebox 已正式停止开发”；
- “Groovebox 已停止销售 Soundpack”；
- “所有当前 iOS 设备都存在某个评论中的 Bug”；
- “Focusrite 已决定放弃 Groovebox”。

---

## 13. 与 Koala、LMDJ 的边界比较

| 维度 | Groovebox | [Koala Sampler](./2026-07-28-koala-sampler-product-research.md) | LMDJ 当前方向 |
| --- | --- | --- | --- |
| 起点 | 内置 Instrument + Preset / Pattern | 用户录音或导入 Sample | 用户上传完成歌曲 |
| 核心转换 | Pattern 让 Synth / Drum 立即成曲 | Sample → Chop → Sequence / Resample | Song → Separation / Materials → 16-pad Patch |
| 主要对象 | Track / Instrument / Pattern / Section | Sample Pad / Sequence / Performance | Project / Patch / Pattern / Pad / Scene / Element |
| 声音来源 | 封闭的内置 Engine / Soundpack | 用户素材优先 | 用户歌曲经 AI / Audio Pipeline 产生 |
| 创作安全网 | Key / Scale / Preset Pattern | Direct Sampling / Resample / Optional Quantize | Semantic Role、固定 16 Slot、默认 Pattern |
| 编排 | Section Matrix，偏手动 Scene Launch | Sequence Slot + Performance | Pattern 已有，Scene / Take 仍需继续定义 |
| 高级入口 | Pro Instrument Parameters | Samurai / Mixer 等扩展 | Sampler Edit / Take Recording 后置 |
| 外部交付 | Mix / ZIP / Ableton Export | WAV / Stems / Ableton 等 | Creator Export ZIP + Ableton Smoke |
| 跨设备 | 无 Project Sync | 各平台能力需另查 | 当前非 Account-level / Cross-device |
| 商业逻辑 | Soundpack / Instrument IAP | App + Feature IAP | 尚未由本研究决定 |

三者最重要的区别是：

- Groovebox 帮用户 **从没有音乐到一个好听的 Pattern**；
- Koala 帮用户 **把自己的声音变成可演奏 Sample**；
- LMDJ 帮用户 **把一首完成音乐变成可编辑、可演奏、可继续制作的 Playable Layer**。

因此 LMDJ 不应变成“Web Groovebox”或“AI 自动填满的 Loop Pack Store”。

---

## 14. 对 LMDJ 的可执行启示

### P0：直接吸收

#### 14.1 Patch Ready 后先给可演奏结果

Groovebox 的第一价值是立即发声。LMDJ 的 Patch Ready 页面应确保：

- 16 个位置稳定；
- 可播放 Pad 不需要继续配置；
- 默认 Pattern 能直接开始；
- 用户可以马上 Mute、Trigger、Play；
- Quality Warning 不隐藏，但不把用户永久困在状态解释中。

#### 14.2 默认 Pattern 是脚手架，不是接管

建议把默认 Pattern 明确设计为：

- 可见；
- 可停止；
- 可删除；
- 可覆盖录制；
- 可另存为新 Pattern；
- 清楚标记是 AI / Pipeline 生成还是用户 Take。

Groovebox 用户会先用 Random / Preset Pattern 获得灵感，再删掉 Note 写自己的内容。LMDJ
也应允许“先听懂，再夺回控制权”。

#### 14.3 编辑时保留演奏面

进入 Pad Inspector、Sampler Edit、Envelope 或 Chop 时，至少保留：

- 当前 Pad Trigger；
- Keyboard / MIDI 输入；
- Loop Context；
- A/B Before / After；
- 清楚的返回路径。

不要让用户为了修改一个参数离开乐器状态。

#### 14.4 保留 Generic MIDI 与 MIDI Learn

Groovebox 的 Launchkey 深度整合很完整，但厂商绑定限制明显。LMDJ 应继续：

- 默认支持标准 Note Mapping；
- 允许 8-pad Bank A/B；
- 提供 MIDI Learn；
- 保存完整有效 Mapping；
- 设备断开时保留 Keyboard / Mouse。

未来可以增加 Controller Profile，但不应取代开放 Mapping。

### P1：先定义，再实施

#### 14.5 明确 Pattern / Scene / Arrangement / Take

Groovebox 的最大产品歧义来自 `Sections`：

- 官方称为 Build a Song；
- 用户却把它理解成不完整的 Song Mode。

LMDJ 在扩展 Scene 前应先确认：

| 对象 | 建议职责 |
| --- | --- |
| Pattern | 一个循环内的 Pad Event |
| Scene | 一组 Pattern / Pad State 的可召回快照 |
| Arrangement | Scene / Pattern 的有顺序、有时长结构 |
| Take | 用户实际演奏产生的时间事件事实 |
| Performance Cue | 现场触发下一个状态的指令 |

如果 Stage 1 只实现 Pattern 和 Take，就不要让 UI 暗示已经可以完整编曲。

#### 14.6 建立可信的 Project Continuity

在用户开始积累 Take 和 Sampler Edit 前，应设计：

- Project ID 与 Patch Version；
- Server-side 保存边界；
- Browser Local State 失效后的恢复；
- Export 是否包含可重新导入的 Project State；
- 登录后跨设备历史是否进入哪一个 Stage；
- 原始上传、Patch、Take、Edit、Export 的生命周期。

Groovebox 证明：Project 丢失会直接破坏用户对创作工具的信任。

#### 14.7 把 Export 当作产品主路径

继续保持 Creator Export 的开放结构：

- `manifest.json`；
- `patch.json`；
- `stems/`；
- `samples/`；
- `midi/`；
- 后续 `takes/`。

先完成真实 Ableton Smoke，再评估 `.als`。不要为了“一键进入 Live”牺牲
`lmdj.patch.v1` 和开放文件边界。

### P2：需要验证后再决定

#### 14.8 内容商品化

Groovebox 证明 Preset + Pattern + Soundpack 可以降低启动成本并形成收入，但 LMDJ 的
核心素材来自用户自己的歌曲，不能直接照搬。

LMDJ 如果以后引入内容层，更合适的方向可能是：

- Performance Style；
- Pattern Template；
- Scene Template；
- Sound-role-aware FX Preset；
- Creator / Artist Pack；
- AI Variation Recipe。

在版权、可解释性和用户素材 ownership 没有定义前，不应把它放进当前 Stage。

#### 14.9 厂商硬件深度整合

可以研究 Launchkey / Launchpad / Ableton Push 等 Profile，但应满足：

- Generic MIDI 仍是 baseline；
- Profile 只增加 LED、Transport、Macro 等便利；
- 不改变 16 Pad Contract；
- 没有硬件时功能仍完整；
- 真机验证与浏览器支持单独记录。

---

## 15. 不建议从 Groovebox 复制的内容

1. **不要复制“Section 就等于 Song”的模糊命名。**
2. **不要把高级参数全部放进付费层后才允许用户形成自己的声音。**
3. **不要依赖整机 Backup 代替 Project Portability。**
4. **不要用 Vendor-specific MIDI Profile 取代 Generic MIDI Learn。**
5. **不要继续宣传已经废弃的平台 Integration。**
6. **不要让 Content Catalogue 的增长掩盖 Workflow 的停滞。**
7. **不要把 LMDJ 变成只消费内部声音资产的封闭 Instrument。**
8. **不要因为移动端要简单，就省略明确的 Export、Recovery 和 Object Semantics。**

---

## 16. 后续真机验证清单

如果要把本研究推进为可用于产品决策的竞品实测，建议在当前 iPhone 和 iPad 各做一次：

### 16.1 首次使用

- 从安装到第一段可听 Loop 的时间；
- 是否强制注册；
- 免费可用的 Instrument / Pack / Pattern；
- Store 是否在首次创作前打断；
- Random / Pattern 推荐逻辑。

### 16.2 演奏与编序

- Touch Latency；
- Quantize On / Off；
- Pattern Length；
- Time Signature；
- Piano Roll 的 Zoom、Move、Velocity、Copy；
- Swing 的作用粒度；
- 同一 Track 的 Voice Stealing；
- Bluetooth Audio 延迟提示。

### 16.3 Section

- Section 是否按 Bar Boundary 切换；
- 是否可预选下一 Section；
- 是否可自动 Chaining；
- Instrument / Preset / Mute / Volume / Tempo / Key 哪些是 Global；
- Section 上限；
- Duplicate / Move / Delete 行为。

### 16.4 Automation

- 可自动化参数列表；
- Automation 是否可编辑、删除、覆盖；
- Automation Resolution；
- App Store 评论所述 Volume Automation 问题能否复现。

### 16.5 导出

- Mix 格式、Sample Rate、Bit Depth；
- ZIP 实际目录；
- 是否包含 MIDI；
- Ableton Export 的 Track / Clip / Audio 布局；
- Reverb / Delay Tail 是否被截断；
- 是否支持 AirDrop / Files；
- 是否能重新导入 Groovebox。

### 16.6 保存与恢复

- 强退恢复；
- App 更新恢复；
- iCloud Backup 后恢复；
- Quick Start / Device Migration；
- 删除 App 后重装；
- IAP Restore；
- 大量 Project 的 Storage 和管理。

### 16.7 MIDI 与生态

- Generic MIDI Note Input；
- Launchkey MK3 / MK4 映射；
- MIDI Out；
- AUv3 Instrument / Host；
- Audiobus；
- Inter-App Audio 在当前 iOS 的实际状态；
- Ableton Link Start / Stop 和 Tempo Change。

---

## 17. 来源

### 17.1 官方与一手来源

- [Apple App Store：Groovebox - Beat Synth Studio](https://apps.apple.com/us/app/groovebox-beat-synth-studio/id1242847278)
- [Apple iTunes Lookup API：App ID 1242847278](https://itunes.apple.com/lookup?id=1242847278&country=us)
- [Apple Customer Reviews RSS：美国区最近评论](https://itunes.apple.com/us/rss/customerreviews/page=1/id=1242847278/sortBy=mostRecent/json)
- [Novation：Groovebox for iOS](https://novationmusic.com/software/groovebox-ios)
- [Ampify Support：Groovebox Tutorials](https://support.ampifymusic.com/hc/en-gb/sections/5033663642258-Groovebox)
- [Ampify Support：How To Build a Song Using Sections](https://support.ampifymusic.com/hc/en-gb/articles/360006108479-Groovebox-How-To-Build-a-Song-Using-Sections)
- [Ampify Support：How to sync with Ableton Link](https://support.ampifymusic.com/hc/en-gb/articles/4887465638930-How-to-sync-to-other-apps-and-Ableton-Live-with-Ableton-Link)
- [Ampify Support：Project access on another device](https://support.ampifymusic.com/hc/en-gb/articles/360005266740-How-do-I-access-my-Launchpad-Groovebox-Blocs-Wave-projects-on-my-other-device)
- [Ampify Support：MIDI hardware support](https://support.ampifymusic.com/hc/en-gb/articles/360010537299-What-MIDI-hardware-is-supported-in-Ampify-apps)
- [Ampify Support：Subscriptions](https://support.ampifymusic.com/hc/en-gb/articles/360022047819-What-subscriptions-do-we-offer-and-how-do-they-work)
- [Ampify Support：Can I release the tracks I make?](https://support.ampifymusic.com/hc/en-gb/articles/360012176699-Can-I-release-the-tracks-I-make)
- [Ampify Support：Soundpack usage restrictions](https://support.ampifymusic.com/hc/en-gb/articles/360006519939-Which-Ampify-sound-packs-have-usage-restrictions-on-them)
- [Ableton：Link features and functions](https://help.ableton.com/hc/en-us/articles/209776125-Link-features-and-functions-FAQ)
- [Ableton：Exporting an Ableton Set from an iOS app](https://help.ableton.com/hc/en-us/articles/206430084-Exporting-an-Ableton-Set-from-your-iOS-app)
- [Apple Developer：Inter-App Audio Entitlement](https://developer.apple.com/documentation/bundleresources/entitlements/inter-app-audio)
- [Apple Developer：Audio Unit v3 Plug-Ins](https://developer.apple.com/documentation/audiotoolbox/audio-unit-v3-plug-ins)
- [Ampify Vimeo：Groovebox for iOS - A Beats & Synths Studio](https://vimeo.com/220923020)
- [Ampify Vimeo：MiniMon](https://vimeo.com/251823753)
- [Ampify Vimeo：Build Songs with Sections - iPad](https://vimeo.com/236928074)
- [Ampify Vimeo：Pro Features Collection](https://vimeo.com/302059765)
- [Ampify Vimeo：Novation Launchkey Support Overview](https://vimeo.com/260457958)
- [Focusrite 2017 Full-year Results](https://www.investegate.co.uk/announcement/rns/focusrite--tune/final-results-for-the-year-ended-31-august-2017/5211063)

### 17.2 第三方补充

- [MusicRadar：Groovebox launch coverage, 2017](https://www.musicradar.com/news/groovebox-is-a-free-novation-powered-beats-and-synths-studio-for-ios)
- [MusicTech：Ampify Groovebox Review](https://musictech.com/reviews/ampify-groovebox-review/)
- [Sound On Sound：Groovebox launch news](https://www.soundonsound.com/news/groovebox-new-studio-app-launchpad-makers)
- [Synthtopia：MiniMon and Pro Features launch](https://www.synthtopia.com/content/2018/01/26/ampify-intros-minimon-wavetable-synthesizer-for-groovebox/)

---

## 18. 最终判断

Groovebox 最值得研究的不是它有五个 Instrument，也不是 Soundpack 数量，而是它如何把：

```text
高质量默认声音
+ 可直接使用的 Pattern
+ 触屏演奏
+ 少量高价值 Macro
+ Pattern Automation
+ 外部 DAW 出口
```

压缩成一个移动端可理解的创作循环。

对 LMDJ 来说，真正应吸收的是 **“结果先于配置、演奏先于编辑、默认内容可被用户夺回、
复杂度逐层展开、出口保持开放”**。

真正应避免的是 **“对象语义模糊、Project 不可迁移、平台生态老化、内容更新替代工作流
演进”**。

这份研究只形成产品输入。是否把 Pattern 脚手架、Scene 定义、跨设备 Project 或特定
Controller Profile 纳入 LMDJ，仍需要分别进入 PRD 讨论和决策流程。
