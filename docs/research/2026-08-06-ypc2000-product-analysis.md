# YPC 产品分析

> 研究对象：[YPC — finger-drum any YouTube video](https://ypc2000.fun/)
>
> 研究日期：2026-08-06
>
> 研究目的：判断 YPC 的产品定位、核心体验、增长与风险边界，以及它对 LMDJ Playable Beat Instrument 的参考价值
>
> 相关技术研究：[YPC 技术分析](./2026-08-06-ypc2000-technical-analysis.md)
>
> LMDJ 对照基线：[Playable Beat Instrument Core Redesign](../superpowers/specs/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md)
>
> 状态：外部产品研究与设计建议，不代表 LMDJ 已批准 YouTube 导入、外部媒体播放或本文提出的实验

## 0. 结论先行

YPC 的价值不是“在浏览器里复刻一台 MPC”，而是把一个非常容易理解的动作压缩成了可立即演奏的体验：

```text
粘贴一条 YouTube 链接
  → 自动得到 16 个时间点
  → 立刻用 4×4 Pad 演奏
  → 再按需要微调、编序和分享
```

它最成功的产品决策有五个：

1. **输入成本接近零**：无需注册、安装、下载或先整理本地音频。
2. **先出声，再编辑**：视频加载后先随机生成可玩的 Pad，不要求用户先理解波形、切片或工程结构。
3. **固定映射形成肌肉记忆**：`1234 / QWER / ASDF / ZXCV` 与 4×4 Pad 一一对应，MIDI 也从 Note 36 连续映射 16 个位置。
4. **复杂度按需出现**：默认界面能直接玩，精确时间、逐 Pad Slice、Rate、音序器和 JSON 数据能力都属于第二层。
5. **分享的是演奏配置而非音频**：URL 和 JSON 保存视频 ID、Pad 时间点与 Pattern，产品保持轻量，也主动停在“发现与草稿”而不是“完成与发行”。

但 YPC 并不是真正意义上的 Sampler：它没有取得、解码或持有音频，没有波形编辑、音频导出、离线渲染、音高独立控制或 Sample-accurate 调度。它控制的是三个 YouTube IFrame Player，Pad 实际上是“跳转到某个视频时间点并播放一小段”的遥控器。

因此，对 LMDJ 的总判断是：

> **把 YPC 当作首次体验和 Pad 编辑顺序的优秀参考，不要把它当作音频架构、项目模型或合规路径的参考实现。**

LMDJ 最值得吸收的是“任意素材 → 三分钟内可演奏”“先建立第一声，再逐步暴露编辑”和“稳定 Pad 位置”；必须拒绝的是 YouTube 运行时依赖、隐藏播放器复音、毫秒 UI 被误认为毫秒音频精度，以及没有 Source / Asset / Pattern / Export Truth 的轻量状态模型。

---

## 1. 研究范围与证据规则

### 1.1 覆盖范围

本文覆盖：

- 产品定位、目标用户和 Job to Be Done；
- 首次体验、演奏、编辑、编序和分享闭环；
- 视觉语言、信息架构、桌面与移动端取舍；
- 免费产品的传播、留存和潜在商业路径；
- YouTube 平台依赖、版权、隐私、品牌与可用性风险；
- 与 Patatap、Samplette、YouChop、Koala Sampler 及 LMDJ 的机制差异；
- 可直接转译为 LMDJ 产品实验的部分，以及明确不应照搬的部分。

本文不覆盖：

- YPC 的未公开用户量、留存、成本或收入；
- 创作者未公开的路线图、商业意图或法律意见；
- 对任何具体 YouTube 内容进行采样是否获得授权；
- MIDI Hardware、移动设备和所有浏览器的完整物理验收；
- 对 YouTube 合规性的最终法律判定。

### 1.2 证据等级

| 标记 | 含义 | 本文中的用法 |
| --- | --- | --- |
| **官方产品事实** | YPC 当前官网、可见交互和公开客户端资源 | 描述当前功能、文案与产品边界 |
| **公开实现证据** | 官网直接分发的 HTML、CSS 与 ES Modules | 核对随机化、映射、保存、音序和播放行为 |
| **平台规则** | YouTube、Web MIDI、Vercel 的官方文档 | 判断外部依赖和合规风险，不代替法律意见 |
| **媒体与用户反馈** | MusicRadar、社区文章和用户帖子 | 说明市场如何理解产品；不当作官方路线图 |
| **分析判断** | 由多项事实推导的产品解释 | 明确写成判断、建议或待验证假设 |

### 1.3 本次实证边界

本次完成了：

- 在桌面 Chrome 打开官网，核对默认视频、两套主题、16 Pad、编辑器与步进音序器；
- 核对线上 HTML、CSS、Manifest 和全部公开 JavaScript Module；
- 核对三个 YouTube Player、逐 Pad 参数、MIDI Note Mapping、Local Storage、URL 分享和 JSON 导入导出；
- 检查当前 HTTP 响应、Vercel 托管信号、Analytics 入口和安全 Header；
- 对照 YouTube IFrame API、Developer Policies、Web MIDI 标准及当前浏览器兼容资料；
- 读取 2026-07 的媒体报道和少量公开用户反馈。

本次没有：

- 接受 MIDI 权限或连接实体 MIDI Controller；
- 播放、录制或导出任何受版权保护的音频；
- 对 Pad-to-sound 延迟、抖动和长时间稳定性做实验室测量；
- 绕过 YouTube 登录、地区、嵌入或 Bot 验证限制；
- 找到可确认属于创作者的官方公开源码仓库或开源许可证。

---

## 2. 产品快照

| 维度 | 当前状态 | 证据性质 |
| --- | --- | --- |
| 产品类型 | 免费、免安装、无账号的 YouTube Pad Instrument | 官网 |
| 创作者 | Producer Halfpast；官网链接到 `@halfpast.life` | 官网 |
| 核心输入 | YouTube URL 或 11 位 Video ID | 官网 / 代码 |
| 默认体验 | 自动载入 Imogen Heap 的 `Hide And Seek` | 官网 / 代码 |
| 演奏面 | 16 Pad，4×4 布局 | 官网 |
| 电脑键盘 | `1234 / QWER / ASDF / ZXCV` | 代码 |
| MIDI | Note 36–51；Note On Velocity 映射音量 | 代码 |
| 鼠标 / 触控 | Pad `pointerdown`；时间线与 Jog 支持 Pointer | 代码 |
| 复音 | 最多 3 个 YouTube Player Voice | 代码 |
| Pad 时间 | 自动分布后可拖动、精确输入及 ±0.1s / ±1s 微调 | 官网 / 代码 |
| Slice | Global 或逐 Pad；Off、0.1–1.0s、2s、4s、8s | 官网 / 代码 |
| Rate | 0.25×、0.5×、0.75×、1×、1.25×、1.5×、2× | 官网 / 代码 |
| 音序器 | 每小节 16 Step；1 / 2 / 4 Bar；40–240 BPM；50–75 Swing | 代码 |
| Pattern 输入 | Step Input 或播放中实时量化录入 | 代码 |
| 保存 | 按 Video ID 保存 Pad 与 Sequence 到浏览器本地 | 代码 |
| 分享 | URL Fragment；可复制链接 | 代码 |
| 数据导入导出 | JSON Kit；当前导出版本 `2` | 代码 |
| 音频导出 | 不支持 | 官网 / 代码 |
| 账号 / 云工程 | 不支持 | 当前产品 |
| 移动端 | 可以浏览和触控，但官网明确标注“Best on desktop” | 官网 |
| 商业模式 | 当前免费，无可见付费层、广告位或账号体系 | 当前产品 |

一个需要纠正的媒体用词是“Time-stretch”。YPC 的 Rate 调用 YouTube Player 的播放速度接口；它没有自己的 Time-stretch DSP，也没有独立 Pitch 控制。更准确的描述是“改变 YouTube 播放速率”，而不是专业 Sampler 意义上的 Time-stretch。

---

## 3. 产品定位

### 3.1 它不是哪类产品

YPC 不是：

- 完整 DAW；
- 可持有音频资产的 Sampler；
- YouTube 下载器；
- 波形切片器；
- 音频插件；
- 以发布完成作品为目标的制作环境。

它更接近：

> **以 YouTube 视频时间轴为素材池的即时 Finger-drumming Sketchpad。**

这个定位解释了它为何同时拥有 MIDI、Sequencer 和 Share，却没有音频录制、混音、效果器和 Audio Export：产品想让用户快速“发现一段可以敲的东西”，而不是承担完整制作链路。

### 3.2 核心 Job to Be Done

主要 Job 可以写成：

> 当我在 YouTube 听到有趣声音时，我想不下载、不建工程就把不同片段分配到 Pad 上敲一遍，以便迅速判断它是否有节奏和重组价值。

次要 Job 包括：

- 没有硬件 Sampler 时体验基本 Chopping 和 Finger Drumming；
- 用熟悉歌曲做音乐互动和社交分享；
- 把一个视频的 Cue Point 和简单 Pattern 发给朋友继续改；
- 在购买或打开复杂工具前快速验证一个 Beat 想法；
- 用 MIDI Controller 获得比鼠标更接近乐器的操作感。

### 3.3 目标用户分层

| 用户 | 主要价值 | 主要阻力 |
| --- | --- | --- |
| 音乐好奇者 | 免费、无门槛、打开就能玩 | 不理解 Slice Off、焦点和嵌入限制 |
| 初学 Beatmaker | 快速理解 Pad、Cue、Step Sequence | 容易误以为能导出或正式制作 |
| 有经验 Producer | 快速预听 Chopping 可能性 | 延迟、精度、复音和版权边界太弱 |
| MIDI Hardware 用户 | 浏览器直接连接 16 Pad | 浏览器兼容、权限、无 MIDI Learn |
| 分享型创作者 | 一条链接传递同一 Kit / Pattern | 依赖原视频继续可嵌入和可访问 |

YPC 的核心用户不是追求精密编辑的专业制作人，而是处于“发现、玩、验证”阶段的人。媒体也主要把它评价为免费、有趣、容易消磨一段时间的工具，而不是专业生产系统。[MusicRadar 的首轮报道](https://www.musicradar.com/music-tech/this-free-browser-based-sampler-turns-youtube-into-an-mpc)直接把它描述为快速 Finger-drumming 乐趣，同时把 Audio Export 缺失视为最明显边界。

---

## 4. 核心体验与用户旅程

### 4.1 首次打开：先提供可玩的答案

官网默认填入一个 Video ID，并在 YouTube Player 准备好后自动加载。用户不需要先找自己的链接，也不面对空白工程。

视频时长可读后，系统按 16 个区段分配随机时间点：长于 12 秒的视频避开开头约 2 秒和结尾约 3 秒，再在每个等分区间内选一个随机点。结果既有随机惊喜，又不会把 16 个 Pad 全挤在同一片段。

这比“先展示 16 个空 Pad，请逐一设置”更适合第一次使用，因为产品先替用户完成了最昂贵的认知工作：从完整视频找到一组可以开始敲的入口。

### 4.2 演奏：输入模型清晰且稳定

4×4 Pad 使用：

```text
1 2 3 4
Q W E R
A S D F
Z X C V
```

这组映射与屏幕布局一致，也能自然对应常见 16-Pad Controller。Pad 被触发时同时成为当前选中项，用户可以立即编辑刚才听到的问题。

产品在这里建立了一条很好的闭环：

```text
听见结果
  → 选择对应 Pad
  → 调时间 / 长度 / 速度
  → 再次触发验证
```

### 4.3 编辑：从粗调到精调

YPC 为时间点提供了四种精度层：

1. Random 重新生成整组时间点；
2. Timeline 拖动到大致位置；
3. Jog 水平拖动或滚轮微调；
4. Exact Timestamp 与 ±0.1s / ±1s 按钮精调。

这套顺序很值得借鉴：用户不必一开始面对精密波形工具，但当耳朵已经听到问题时，能够逐步提高控制精度。

逐 Pad 还能：

- 重命名，最长 24 个字符；
- 继承 Global Slice 或单独设置长度；
- 设置播放 Rate；
- 使用一次 Undo 撤销 Random / Reset / Import 前的 Pad 快照。

明显缺口包括：

- 没有波形和瞬态；
- 没有 Start / End 双边界；
- 没有 Hold、Gate、One-shot 等清晰触发模式；
- Slice 设为 Off 后没有显式 Stop；
- 没有单 Pad 音量、Pan、Envelope、Filter、Reverse；
- 没有多选、复制、交换、Bank 或 Pad Role。

### 4.4 编序：够证明想法，不够制作歌曲

音序器是 16 行 × 16/32/64 Step 的二进制 Grid：

- 1 / 2 / 4 Bar；
- 40–240 BPM；
- 50–75 Swing；
- Step Input；
- 播放时把 Pad Hit 量化到最近 Step；
- Clear Pattern。

它没有：

- 多 Pattern Slot；
- Pattern Chain / Song Mode；
- Velocity、Probability、Microtiming 或 Parameter Lock；
- Metronome、Count-in、Loop Range；
- MIDI Clock、Ableton Link 或外部 Transport；
- Audio Bounce。

因此音序器的产品角色是“把一次好玩的敲击留下”，不是完整 Arrangement。

### 4.5 保存与分享：状态跟着视频走

Pad 和 Sequence 以 Video ID 为键保存在浏览器本地。用户再次打开同一视频时可以恢复状态。Share 把 Video ID、Pad 配置和 Sequence 编码到 URL Fragment；Export 则生成 JSON。

优点：

- 没有账号、数据库和同步成本；
- 链接就是可复现草稿；
- 接收者可以继续改；
- URL Fragment 不参与普通 HTTP 请求路径，服务端不需要保存 Kit 内容。

边界：

- 清理浏览器数据或换设备会丢失本地状态；
- 分享仍依赖原视频没有被删除、设为 Private、禁止嵌入或限制地区；
- JSON 保存的是控制状态，不包含声音资产；
- 没有工程列表、版本、冲突、缩略图或迁移 UI；
- 没有清晰区分“保存成功”“链接可长期复现”和“内容权利可使用”。

---

## 5. 信息架构与视觉设计

### 5.1 硬件隐喻帮助理解

桌面界面把屏幕分成：

- 顶部 Video Source 和状态显示；
- 左侧可见 YouTube Player、Selected Pad Editor 与 Timeline；
- 右侧 Program、Mode、Data、Edit、Global Slice 和 4×4 Pad；
- Seq 模式把左侧编辑区替换为 Step Grid。

两套主题按钮直接命名为 `Live` 和 `2000XL`。`2000XL` 使用米灰机身、LCD 蓝绿字、方形 Pad 与彩色丝印；`Live` 使用深色现代硬件语言。媒体普遍把这种视觉理解为对经典 Akai MPC 的引用。

硬件隐喻在这里不是纯装饰：

- `Bank / Program / Mode / Data / Edit` 把控件分组；
- 4×4 Pad 位置稳定；
- 状态区像硬件 LCD；
- LED、按下位移和高亮帮助确认输入。

### 5.2 渐进暴露做得好，但关键概念缺少解释

界面没有大段教程，这有利于快速进入。但一些概念仅靠硬件术语表达：

- `Slice Off` 实际意味着不自动停止，而不是静音；
- `Rate` 并不说明是否保持音高；
- `MIDI` 会触发浏览器权限，但没有设备映射说明；
- Share / Export 的差异没有可见解释；
- Random 与 Reset 的差异依靠结果猜测；
- 网址输入完成后焦点仍可能停在输入框，键盘演奏暂时无效。

[一篇 2026-07 的实测整理](https://note.com/beatmaking_guide/n/n5ca302b55f1b)也记录了输入焦点、Slice Off 停不下来、三复音和嵌入失败等容易误解的点。这些不是功能缺失，而是产品没有把运行语义及时转成用户语言。

### 5.3 移动端是“可用但非承诺”

CSS 在窄屏把页面重排为 Video、Pads、Controls，并隐藏部分精确编辑控件；官网同时弹出“Best on desktop”，说明移动性能仍在改进。

这种处理诚实，但也意味着：

- 触控是支持的输入，不等于移动端已经完成产品验收；
- 手机上最需要的精确时间编辑被收缩；
- Safari / iOS 缺少 Web MIDI，Hardware 路径不成立；
- YouTube 移动播放策略、手势和浏览器生命周期会继续影响体验。

### 5.4 可访问性有良好基础，也有明显冲突

正向信号：

- 表单、Pad、Timestamp、Timeline、Step Cell 均有可访问名称；
- 状态使用 `aria-live`；
- Mode、Theme、Transport 使用 `aria-pressed` / `aria-checked`；
- 有键盘焦点样式和 `prefers-reduced-motion`；
- 多数主控件满足约 44px 的触控高度。

问题：

- 两个屏幕外 YouTube Player 仍进入可访问树，重复出现视频标题和控件；
- 4×4 键位说明没有形成首次可见的帮助层；
- Sequence Grid 在 4 Bar 时会产生 1,024 个 Step Button，屏幕阅读器和键盘导航成本很高；
- 移动端隐藏部分编辑控件，桌面与移动能力不完全一致；
- 颜色 LED 承担较多状态表达，虽有 ARIA，但视觉用户仍可能需要更明确文本。

---

## 6. 传播、留存与商业边界

### 6.1 传播钩子

YPC 很适合被媒体和社交内容传播，因为一句话就能说明：

> “Paste a YouTube link and play it like an MPC.”

传播素材天然包含：

- 人人认识的 YouTube；
- 一眼可懂的 4×4 Pad；
- 复古硬件视觉；
- 熟悉歌曲被重新敲击的反差；
- 一条可直接打开的分享链接。

MusicRadar 在 2026-07-17 报道后，其他音乐与夜生活媒体很快转载或再解释；公开社区也已经出现用户拿特定歌曲制作并分享 YPC Kit 的帖子。这能证明产品具备可传播性，但不能推导出具体活跃用户、留存或收入。

### 6.2 留存机制

当前留存主要来自：

- 每个 YouTube 视频都是新的可玩素材；
- Random 带来重复探索；
- Local Storage 恢复上次配置；
- Share 让朋友继续修改；
- MIDI 和 Sequencer 提供从玩具到小乐器的进阶感。

留存上限也很清楚：

- 没有工程库和历史；
- 没有内容 Feed、挑战、模板或 Remix 关系；
- 没有个人资产积累；
- 没有可发布音频成果；
- 没有账号，无法跨设备持续使用。

### 6.3 当前商业模式

官网当前没有可见付费层、广告位、商店、账号或捐赠入口。更合理的判断是“个人创作者的免费实验 / 品牌入口”，而不是已经成立的 SaaS。

如果未来商业化，可能路径包括赞助、创作者品牌导流、合法素材包、离线本地素材版或高级编辑器；但直接对当前 YouTube 控制路径收费会放大平台政策、内容权利与可靠性风险，不能把“有传播”直接等同于“可收费”。

---

## 7. 竞争与相邻产品

| 产品 | 核心素材 | 第一价值 | 是否持有音频 | 编序 / 工程 | 输出能力 | 与 YPC 的关键差异 |
| --- | --- | --- | --- | --- | --- | --- |
| **YPC** | YouTube Video ID | 立刻把视频时间点变成 16 Pad | 否 | 单一简单 Pattern | URL / JSON，无音频 | 输入最轻，生产闭环最弱 |
| [Patatap](https://patatap.com/) | 内置声音与动画 | 任意按键都有统一视听反馈 | 是，内置 Sample | 无工程 / Sequencer | 无作品导出 | 更纯粹的即时乐器，不解决用户素材 |
| [Samplette](https://samplette.io/) | YouTube 发现流 | 随机 Crate Digging | 否或依赖外部工具 | 不是 Pad Instrument | 侧重发现 | 找素材优先，YPC 是演奏优先 |
| [YouChop](https://github.com/due-it-you/youchop) | YouTube IFrame | 手工设定 YouTube 切片 | 否 | 更轻 | 无音频 | 更像切点工具，YPC 用随机 Pad 先启动 |
| [Koala Sampler](https://manual.koalasampler.com/) | 用户拥有 / 导入 / 录制的音频 | 快速但完整的移动采样工作流 | 是 | 多 Sequence、Perform、Song | WAV、项目与多种导出 | 真正的采样、制作和导出系统，输入成本更高 |
| **LMDJ** | 用户音频、完整歌曲及 Provider 派生 Artifact | 把声音变成可演奏 Beat Project 并进入 Sequence / Perform / Export / Resample | 是，具有 Artifact 与 Lineage | 64 Pad、多 Pattern、Project Truth | 离线 Render 与 Creator 输出 | 目标是可持续创作和可验证输出，不只是草稿 |

YPC 的竞争优势不是功能更多，而是它把“素材准备”这一大段流程删掉了。Koala 和 LMDJ 的优势则是对声音、工程和输出拥有真实控制。两者不应在功能数量上直接竞争，而应分别守住不同承诺。

---

## 8. 优势、缺口与风险

### 8.1 产品优势

| 优势 | 为什么有效 |
| --- | --- |
| 一句话可解释 | 减少传播和首次理解成本 |
| 默认 Demo | 空状态直接变成体验状态 |
| 自动分布 16 个时间点 | 用户不用先学切片即可获得第一声 |
| 演奏与编辑同屏 | 听到问题后立即修改对应 Pad |
| 固定键位 / MIDI 连续映射 | 快速建立肌肉记忆 |
| URL / JSON 分享 | 不建后台也能复现控制状态 |
| 复古硬件视觉 | 提供品类识别和情绪价值 |
| 功能边界克制 | 没有快速膨胀为浏览器 DAW |

### 8.2 体验缺口

| 缺口 | 用户影响 |
| --- | --- |
| 输入框焦点阻断键盘演奏 | “粘贴后直接敲”的承诺出现停顿 |
| Slice Off 无显式 Stop | 声音持续播放且用户难以理解 |
| 仅三复音 | 和 16-Pad / Sequencer 的视觉预期不一致 |
| 无波形 | 精确找 Transient 依靠反复试听 |
| Rate 语义不清 | 容易被误认为独立 Time-stretch / Pitch-shift |
| 嵌入失败、登录和地区限制 | 任意 YouTube URL 并不真的都可用 |
| 无 Audio Export | 从有趣结果到真实作品出现断层 |
| 无项目库 / 版本 | 不适合长期积累和复杂创作 |
| 移动端未完成 | 触控价值没有转化为可靠移动乐器 |

### 8.3 平台与版权风险

“不下载音频”降低了技术和产品复杂度，但不等于自动解决平台条款或内容版权。

当前公开实现创建一个可见 Player 和两个移到屏幕外的 Player，以获得三复音。YouTube Developer Policies 明确限制未显示在用户当前页面、Tab 或屏幕中的 Background Player，并要求不得分离、隔离或修改音视频组件；官方 IFrame 文档还记录了 Player 最小 200×200 的要求。YPC 的隐藏 Player 为 160×90，因而至少存在需要正式 Compliance Audit 的高风险点。[YouTube 官方指南](https://developers.google.com/youtube/terms/developer-policies-guide)也建议不确定时申请 API Compliance Audit。

此外：

- 原视频版权仍属于权利人；
- 分享 Kit 不授予在作品中使用该声音的权利；
- 视频可随时被删除、Private、Geoblock 或禁止 Embed；
- 产品没有当前可见的 Terms、Privacy Policy 或 Sample Clearance 提示；
- “不导出”只是能力边界，不是版权许可证明。

本文不判断 YPC 已构成违规，而是认为其核心复音机制不适合作为 LMDJ 的合规先例。

### 8.4 品牌与视觉风险

`2000XL`、`Live`、MPC-style Meta Description 和整体硬件 Trade Dress 会让用户迅速联想到 Akai MPC。这提高了品类识别，也带来商标、命名和外观相似性审查需求。

对 LMDJ 的原则应该是：借鉴“稳定 Pad Grid + 清晰硬件分组”，不要复制具体机型名称、配色、面板比例、丝印、Logo 或外观资产。

### 8.5 隐私与信任风险

官网启用了 Vercel Web Analytics，并发送播放、MIDI、音序、分享、导入导出及 JavaScript Error 等 Custom Event。Vercel 官方说明默认 Page View 和 Event 可以匿名聚合，但 Custom Event 是否包含个人信息仍取决于应用传入的数据。

YPC 当前没有可见 Privacy Policy，也没有解释：

- 打开页面会连接 Vercel 和 YouTube；
- YouTube Embed 会带来独立的数据处理与 Cookie / 登录上下文；
- MIDI 需要浏览器权限；
- JavaScript Error Message 最多 200 字符会被上报。

即使产品免费且无账号，也应补充简洁的 Privacy / Third-party Services 说明。

---

## 9. 对 LMDJ 的启示

### 9.1 应直接吸收

| YPC 机制 | LMDJ 转译 |
| --- | --- |
| 默认即有可玩结果 | Demo Project 或自带合法素材，让用户不上传也能完成一次 Play → Record |
| 自动生成 16 个起点 | 导入后先给出可撤销的 Slice / Pad Candidate，不覆盖 Source Truth |
| 先演奏、后精修 | 首屏优先 Play，波形、参数和 Provider 结果按选中 Pad 展开 |
| 4×4 键盘直映射 | 每个 16-Pad Bank 保持固定键位和 Hardware Mapping |
| Timeline + Jog + Exact | 同时提供粗定位、听觉微调和数值输入，但必须基于真实音频时间 |
| Global + Per-pad Override | 默认全局行为，个别 Pad 再覆盖，减少重复设置 |
| Random + Undo | 所有生成候选可预听、可撤销、可保存为新状态，不静默替换 Project Truth |
| Share / Export 分离 | Share 面向协作状态，Export 面向可验证 Artifact 和 DAW |

### 9.2 应明确拒绝

| YPC 机制 | LMDJ 不应采用的原因 |
| --- | --- |
| YouTube IFrame 作为声音引擎 | 受外部播放策略、条款、网络、地区、Embed 和延迟控制 |
| 屏幕外 Player 实现复音 | 合规、资源、可访问性和稳定性风险 |
| `seekTo()` 作为 Sample Trigger | 不是 Sample-accurate，无法满足 Beat Instrument |
| `setTimeout` 作为最终音序时钟 | 不能提供 Audio-thread 级调度和离线一致性 |
| 只存时间点、不持有 Asset | 无法建立 Artifact、Lineage、Offline、Render 和 Export Truth |
| Share Link 即工程 | 缺少版本、资产完整性、迁移和可验证引用 |
| 无权利提示的任意媒体入口 | LMDJ 必须以用户拥有或获授权的素材为默认路径 |
| 三复音 LRU 抢占 | 64-Pad 和 Pattern Playback 需要显式 Voice Policy 与验收 |

### 9.3 值得验证的三个产品实验

#### 实验 A：First Sound Time

目标：从选择一个已有 Source 到第一次成功触发 Pad 的中位时间不超过 30 秒。

验证：

- 新用户无需阅读教程；
- 系统先给 Candidate，不要求先编辑；
- 第一次 Pad Trigger 有明确声音和视觉反馈；
- Candidate 不覆盖原始 Source，也不伪装成已保存 Project Truth。

#### 实验 B：Play-first Sampler Edit

目标：用户先通过演奏发现问题，再进入当前 Pad 的 Start / End / Trigger / Envelope 编辑。

验证：

- 选中 Pad 和活跃 Voice 状态分开表达；
- Timeline 粗调、Jog 微调、波形 / 数值精调一致；
- Edit 产生 Command，可 Undo / Redo；
- 真实 Audio Runtime 与离线 Render 结果一致。

#### 实验 C：Lightweight Pattern Share

目标：在不复制源音频的情况下分享 Pattern 意图，同时显式标记接收方缺失 Asset 的状态。

验证：

- Pattern Event 引用稳定 Pad Slot；
- Source / Asset Identity 可验证；
- 接收方缺失素材时显示 Offline，不自动换音；
- 分享状态与可发行授权分开说明。

### 9.4 对当前 LMDJ 路线的优先级判断

YPC 不改变 LMDJ 当前的核心排序：

1. 继续先证明 Headless 64-Pad Project、Sampler、Pattern Playback 和 Offline Render；
2. Web Creator 用真实 Audio Runtime 验证 Touch / Keyboard / MIDI 与生命周期；
3. 把“第一声速度”和“Play-first Edit”作为 Creator Editor 的体验门槛；
4. YouTube URL 只可作为未来单独研究的 Source Provider 候选，不能绕过用户素材授权、Artifact 边界或 Provider Contract；
5. 在获得平台书面/审计结论前，不把 YouTube Embed Chopping 写进产品承诺。

---

## 10. 最终判断

### 10.1 产品价值评分

| 维度 | 判断 | 说明 |
| --- | --- | --- |
| 概念清晰度 | **高** | 一句话即可理解和传播 |
| First-time Value | **高** | 默认视频 + 自动 Pad 直接出声 |
| 演奏可学习性 | **中高** | 固定 4×4 映射清晰，仍有焦点与 Stop 问题 |
| 编辑深度 | **低到中** | 时间、Slice、Rate 足够草稿，不足生产 |
| 创作闭环 | **低** | 无 Audio Asset、Render、DAW Export 和 Project Library |
| 分享效率 | **高** | URL / JSON 很轻，但依赖原视频 |
| 技术可控性 | **低** | 核心声音依赖 YouTube IFrame |
| 平台 / 合规确定性 | **低** | 隐藏 Player 和版权边界需要正式审查 |
| 对 LMDJ 产品参考价值 | **高** | 适合参考首次体验、Pad 映射和渐进编辑 |
| 对 LMDJ 技术复用价值 | **低** | 不符合真实音频、Project Truth 和离线输出要求 |

### 10.2 一句话建议

> LMDJ 应复制 YPC 的“快”，但不能复制它实现“快”的外部播放器捷径；我们要把同样短的首次体验建立在自有 Project、Artifact、Audio Runtime 和可验证输出上。

---

## 11. 主要来源

### 一手来源

- [YPC 官网](https://ypc2000.fun/)
- [YPC 在线入口 HTML](https://ypc2000.fun/)
- [YPC `app.js`](https://ypc2000.fun/app.js)
- [YPC Pad / URL 工具模块](https://ypc2000.fun/js/utils.js)
- [YPC 播放器池](https://ypc2000.fun/js/pool.js)
- [YPC MIDI 模块](https://ypc2000.fun/js/midi.js)
- [YPC Sequencer](https://ypc2000.fun/js/sequencer.js)
- [YPC Sequence UI](https://ypc2000.fun/js/seq-ui.js)
- [YPC 分享与导入导出](https://ypc2000.fun/js/share.js)
- [YPC Local Storage](https://ypc2000.fun/js/storage.js)
- [YouTube IFrame Player API Reference](https://developers.google.com/youtube/iframe_api_reference)
- [YouTube API Services Developer Policies](https://developers.google.com/youtube/terms/developer-policies)
- [YouTube Developer Policies Guide](https://developers.google.com/youtube/terms/developer-policies-guide)
- [Web MIDI API](https://www.w3.org/TR/webmidi/)
- [Vercel Web Analytics Privacy and Compliance](https://vercel.com/docs/analytics/privacy-policy)
- [Koala Sampler Manual](https://manual.koalasampler.com/)
- [Patatap](https://patatap.com/)
- [Samplette](https://samplette.io/)
- [YouChop GitHub](https://github.com/due-it-you/youchop)

### 二手来源与公开反馈

- [MusicRadar：This free browser-based sampler turns YouTube into an MPC](https://www.musicradar.com/music-tech/this-free-browser-based-sampler-turns-youtube-into-an-mpc)
- [Beatmaking Guide：YPC 实测与资料整理](https://note.com/beatmaking_guide/n/n5ca302b55f1b)
- [Midnight Rebels：YPC introduction](https://midnightrebels.com/ypc-free-browser-sampler-turns-youtube-into-akai-mpc/)
- [公开用户分享示例](https://www.reddit.com/r/boardsofcanada/comments/1v1b67q/discovered_ypc_used_father_and_son_source/)

所有“当前”描述均以 2026-08-06 可访问页面、线上资源和官方文档为准；YPC 是近期上线且无公开版本号的个人产品，后续行为可能变化。
