# Patatap 与同类视听音乐产品调研

> 研究日期：2026-08-02
>
> 研究对象：[Patatap](https://patatap.com/)
>
> 研究性质：产品、交互、声音、视觉、商业与授权研究；不代表 LMDJ 已批准的视觉功能、产品范围或实施计划

相关研究：

- [Patatap × Incredibox × Seaquence × LMDJ 产品机制对照](./2026-08-02-patatap-incredibox-seaquence-lmdj-mechanism-comparison.md)
- [Koala Sampler 产品研究与 LMDJ 启示](./2026-07-28-koala-sampler-product-research.md)
- [LMDJ Preset / Sound Pack 采购与授权研究](./2026-07-30-sound-pack-sourcing-and-licensing.md)

## 0. 结论先行

Patatap 不是简化版 DAW、自动音乐 Visualizer 或 VJ 工作站，而是一个极度聚焦的
**即时视听乐器**：用户每次按键或触摸都会同时触发一个声音手势和一个全屏动画手势。

它最重要的产品价值不是功能数量，而是以下组合：

1. 打开后不需要注册、建工程、选择模板或阅读教程；
2. 任意输入都在极短时间内得到明确的声音与视觉反馈；
3. 声音素材经过严格约束，即使没有音乐经验、同时按很多键，也不容易产生严重冲突；
4. 视觉使用统一的二维几何、有限色板和短生命周期动画，允许叠加但不要求编辑；
5. 产品主动停在“演奏催化剂”，没有继续扩展成录音、循环、编序、工程和导出工具。

因此，Patatap 最适合作为以下问题的参考：

> 如何让一个从未使用过音乐软件的人，在第一次输入时就相信“这是我的动作产生的声音和画面”？

它不适合作为以下问题的完整参考：

- 如何组织 Pattern、Song 或 Timeline；
- 如何保存和恢复创作状态；
- 如何导入用户素材；
- 如何录制、重放、编辑和导出表演；
- 如何进行专业 VJ、投影映射或多屏输出；
- 如何取得可嵌入商业产品的声音与视觉资产授权。

---

## 1. 研究范围与证据方法

### 1.1 覆盖范围

本文覆盖：

- Patatap 的定位、历史与当前公开状态；
- 键盘、触摸和 MIDI 输入模型；
- 声音集合、视觉动画和二者的绑定方式；
- 首次体验、可学习性、可演奏性和留存机制；
- Web、App、开源代码、传播和商业模式；
- 隐私、无障碍、闪烁画面和授权边界；
- Typatone、Plink、Bloom、Kandinsky、Blob Opera、Incredibox、NodeBeat、
  Seaquence、Song Maker 等同类或相邻产品；
- 对 LMDJ 研究价值的边界判断。

本文不覆盖：

- Patatap 私有数据、收入、当前活跃用户和留存；
- 未公开后台或 App 原生容器的完整实现；
- 对声音、动画或用户作品授权的法律意见；
- LMDJ 视觉功能设计、交互稿或实施方案。

### 1.2 证据等级

| 标记 | 含义 | 使用方式 |
| --- | --- | --- |
| **官方事实** | 官网、官方 App Store、官方项目页与创作者公开说明 | 作为当前产品能力与定位的主要依据 |
| **代码证据** | Patatap 当前公开仓库、源文件和资产目录 | 用于核对输入、声音集合、色板、MIDI 和运行时行为 |
| **创作者说明** | Jono Brandel、Lullatone 的公开访谈 | 用于解释创作意图和声音设计原则 |
| **历史数据** | 创作者公布的访问与使用统计 | 只描述对应历史时间点，不冒充当前指标 |
| **分析判断** | 由多项公开事实推导的产品解释 | 明确与官方宣称分开 |
| **待验证** | 需要当前真机、书面授权或内部数据才能确认 | 不写成确定事实 |

### 1.3 本次实证边界

本次完成了：

- 检查当前官网、HTML 入口、动态加载结构和公开源码；
- 核对 `A–Z`、空格、触摸分区、Web MIDI 和 MIDI Note Mapping；
- 核对当前运行时使用的色板、声音集合和资产数量；
- 检查美国区 App Store 当前可用性、价格、系统要求和隐私声明；
- 检查 GitHub 当前分支、README 授权说明和最近维护记录；
- 读取创作者访谈、官方统计和同类产品一手资料。

本次没有：

- 在当前 iPhone、iPad、Android 或 MIDI Hardware 上做延迟测试；
- 逐一测量 156 个声音的音高、响度、时长和频谱；
- 对浏览器长时间运行、离线恢复、功耗和内存做性能测试；
- 向创作者确认声音、动画、商标和用户输出的独立商业授权。

---

## 2. 产品快照

| 维度 | 当前公开状态 | 证据 |
| --- | --- | --- |
| 产品类型 | 即时、样本驱动的二维视听乐器 | 官网 / 源码 |
| 公开发布 | 2014 年 3 月进入 Chrome Experiments | Google |
| 创作者 | Jono Brandel；声音由 Lullatone 合作制作 | 官网 / 访谈 |
| 输入 | Keyboard、Touch、Mouse Drag、Web MIDI | 源码 |
| 演奏事件 | 26 个字母事件；空格切换声音与配色世界 | 官网 / 源码 |
| 当前运行时 Sound Set | 6 套，每套 26 个声音 | 源码 |
| 视觉 | 全屏 Canvas、二维矢量/几何动画、有限色板 | 源码 / Two.js |
| 音频 | 预制短 Sample，通过 Web Audio API 解码与播放 | 源码 |
| 保存与工程 | 没有用户可见 Project Save / Load | 当前产品 |
| 录制与循环 | 没有内置 Record、Loop 或 Sequencer | 当前产品 / 创作者访谈 |
| 导入与导出 | 不支持用户素材导入，也不提供音频/视频导出 | 当前产品 |
| Web 商业模式 | 免费访问；周边、音乐、Newsletter 与付费 App 引流 | 官网 |
| iOS | 美国区 `US$1.99`，官方离线版，iOS/iPadOS 17.2+ | Apple |
| 代码 | README 标注 MIT；Two.js 也是 MIT | GitHub / Two.js |
| 当前维护 | 2026-01 有依赖和代码质量配置维护提交 | GitHub |

需要注意：仓库 `assets/` 中可以看到 `A–G` 七个目录，但当前运行时代码的
`updateAudio()` 只选择 `A–F` 六套声音；因此本文按当前可达运行路径记录 6 套，
不把未被当前路径选择的 `G` 计入现有产品能力。

---

## 3. 历史、定位与创作意图

### 3.1 从音乐可视化原型到可演奏工具

Jono Brandel 先进行了多年动画与音乐可视化实验，早期 Patatap 版本至少在 2012 年
于 Gray Area 场地展示。与 Lullatone 合作后，原本用于“显示音乐”的动画被重新组织成
可以由人直接演奏的工具。2014 年正式公开后，Patatap 进入 Chrome Experiments。

这个变化很关键：

```text
音乐发生 → 系统分析或显示
```

变成了：

```text
人的动作 → 声音和画面同时发生
```

前者是 Visualizer，后者是 Instrument。

### 3.2 作者对产品角色的描述

Jono 在 2014 年访谈中把 Patatap 类比为 Acoustic Guitar：它能让一个人开始成为
表演者，但不会自动让人完成所有音乐制作，也不是完整工具套件。作者使用的另一个
准确说法是：**a catalyst to perform**。

因此，没有 Record、Loop 和完整编辑器并不只是早期技术缺口，也与产品角色一致：

- 给用户即时的表达入口；
- 保留熟练演奏的空间；
- 不负责把表演自动整理成完成作品。

### 3.3 感官混合，而不是模拟传统乐器

创作者希望把听觉和视觉的混合带到任何人都能接触的格式中。Patatap 没有模拟钢琴、
鼓机或乐谱，而是为每个声音事件制作一个对应的视觉动作。

这使用户同时在做两种 Composition：

- 声音在时间中的组合；
- 图形在画面中的构图。

---

## 4. 核心交互机制

### 4.1 Desktop：QWERTY 变成 26 键乐器

桌面端把三排字母映射为内部二维索引：

```text
Q W E R T Y U I O P
 A S D F G H J K L
  Z X C V B N M
```

每个索引绑定一个 Animation Object，并在当前 Sound Set 下加载同名声音。输入后：

1. 找到该索引的动画；
2. 如果同一动画仍在播放，先 Clear；
3. 重启动画；
4. 停止并重放该动画绑定的声音；
5. 如连接了 MIDI Output，同时发出对应 Note On / Off。

这意味着：

- 不同按键可以在视觉和声音上叠加；
- 同一个按键不是无限堆积，而是具有明确的重新触发语义；
- 每次输入的声音和画面由同一个事件标识关联，而不是分别监听后猜测同步。

### 4.2 Space：切换整套世界，而不是换单个音色

空格不会触发普通声音，而是推进当前 Palette。Palette 变化时：

- 背景、前景、强调色等颜色逐渐过渡；
- 26 个动画对象切换到对应的下一组声音；
- 视觉动作类型基本保留，声音语境和整体色彩一起改变。

用户因此不是在音色浏览器里逐项选择，而是在多个已经配好的“声音 + 色彩世界”之间
切换。这是内容策划先于参数编辑的典型做法。

### 4.3 Touch：整块屏幕是不可见演奏面

移动端不复制 QWERTY 键帽，而是根据横竖屏把画面分成三组不可见区域。用户点击或
拖动手指经过新区域时触发对应事件。

优点：

- 视觉画面不被永久控件遮挡；
- 多点触控与滑动能形成连续探索；
- 手机和平板可以使用同一内容系统。

代价：

- 用户无法预先知道某个位置对应什么声音；
- 肌肉记忆依赖屏幕尺寸、方向和隐形分区；
- 产品更鼓励探索，而不是精确复现一段复杂表演。

### 4.4 MIDI：把 Web Toy 扩展成可连接乐器

当前代码请求 Web MIDI Access，并维护 MIDI Input、Output 和设备状态。官方提供
Keyboard-to-MIDI Note Conversion Table。MIDI Note On 被映射回 Patatap 的事件，
Patatap 输入也可以向连接的 MIDI Output 分发 Note On / Off。

这让它可以进入外部控制器和装置场景，但仍没有：

- Velocity 对声音或动画强度的连续映射；
- MIDI Learn UI；
- Clock、Transport、Pattern Sync；
- 可保存的 Controller Profile。

---

## 5. 声音设计机制

### 5.1 失败空间由内容约束，而不是教程约束

Lullatone 解释过，他们最谨慎处理的是：无论谁来演奏，都尽量保持可听。主要方法是：

- 把声音裁成较短、较简单的形态；
- 即使内部有多层音色，也避免大量声音同时出现后变得浑浊；
- 每套大致平分为 13 个旋律性声音和 13 个纯节奏声音；
- 避免整个集合被旋律元素占满，从而给节奏和空间留下位置；
- 在整体可兼容的集合里保留少量奇异声音，维持惊喜。

这说明 Patatap 的“新手友好”主要不是 UI 文案，而是 Content System：

```text
可以自由演奏
  ≠
所有声音都完全自由
```

产品先在音高、频段、包络、时长和音色密度上完成了大量设计，再把表面自由交给用户。

### 5.2 Sample，而不是实时 Synth

当前声音来自预制 MP3 Sample。每次 Palette 变化时，产品按动画名称加载对应 Set 中
的文件，并通过 Web Audio API 解码和触发。

选择 Sample 的产品效果是：

- 声音设计结果可以精确策划；
- 浏览器和设备间听感更稳定；
- 不需要向新用户暴露 Synth 参数；
- 每次触发的 CPU 成本和行为更容易控制。

相应代价是：

- 内容扩展依赖持续制作声音资产；
- 用户不能生成自己的音色；
- 原始声音的分发授权成为商业产品边界。

---

## 6. 视觉设计机制

### 6.1 统一视觉语法

公开源码中的动画包括 Bubbles、Clay、Confetti、Corona、Flashes、Glimmer、Moon、
Pinwheel、Pistons、Prisms、Spiral、Splits、Squiggle、Strike、Suspension、Timer、
UFO、Veil、Wipe、Zigzag 等。

这些动画虽然形式不同，但共享：

- 平面几何；
- 高对比有限色板；
- 短生命周期；
- 明确的进入、运动和退出；
- 适合全屏和叠加的构图；
- 不依赖写实素材、人物、视频或复杂 3D Scene。

### 6.2 一次事件，一次完整视觉语句

动画不是对声音频谱的逐帧分析，也不是给音频加一个通用粒子效果。每个事件都有预先
设计的运动结构，例如擦除、爆发、旋转、穿越、闪烁或散落。

这种方式的优势是：

- 因果关系明确；
- 画面有作者性；
- 输入节奏会自然成为视觉剪辑节奏；
- 不依赖复杂音频分析就能保持声音与画面的心理同步。

### 6.3 短暂叠加而非持久画布

Patatap 的画面不是用户要保存和继续编辑的 Composition Canvas。动画自行消失，
输入结束后画面回到背景。

这减少了：

- 图层管理；
- 删除和撤销；
- Scene 状态；
- Project Serialization；
- 输出一致性问题。

但也意味着用户的视觉作品只存在于表演过程和外部录屏中。

---

## 7. 首次体验与学习机制

### 7.1 五秒内完成闭环

首次进入只需要：

```text
加载当前 26 个声音
  → 显示“按任意键 / 触摸屏幕并打开扬声器”
  → 用户输入
  → 声音与画面立即出现
```

没有：

- 注册；
- Project Name；
- Genre 选择；
- Device Setup Wizard；
- 音乐理论说明；
- 新手任务清单。

### 7.2 探索就是教学

用户通过三个问题自然学习：

1. 这个按键会发生什么？
2. 两个按键叠加会发生什么？
3. 空格之后同样的按键会发生什么？

界面没有试图提前解释 26 个结果，而是把未知本身变成留存动力。

### 7.3 深度来自演奏，而不是参数

Patatap 的熟练度体现在：

- 记住各按键的声音角色；
- 控制输入时序；
- 有意识地选择叠加密度；
- 在不同 Sound Set 中切换；
- 与外部音乐或其他演奏者共同使用。

它没有通过更多面板建立深度，而是让同一个简单界面可以从乱按逐渐过渡到有意表演。

---

## 8. 成功、传播与商业模式

### 8.1 历史传播数据

Jono 在 2016 年公布：Patatap 发布后两年已经获得数百万 Pageviews，其中接近
90,000 次互动持续至少半小时，保守估计累计超过 45,000 小时。

这些数据只代表当时公开统计，不能当作 2026 年活跃用户或留存。但它们证明：一个
没有账号、工程和内容 Feed 的轻量网页，也可以通过即时体验产生大量深度使用时间。

### 8.2 自带录屏传播，但没有内置传播链路

Patatap 每次输入都会产生全屏视听结果，非常适合：

- 屏幕录制；
- 现场投影；
- 与其他音乐一起表演；
- 课堂演示；
- 媒体嵌入和社交分享。

然而产品自身没有 Mix URL、作品页、排行榜或社交图谱。这一点与 Incredibox、
Seaquence 明显不同：Patatap 的传播主要依靠外部平台承接。

### 8.3 免费 Web + 低价离线 App + 创作者支持

当前官网仍免费开放，并引导用户：

- 购买官方 iOS 离线版；
- 订阅 Newsletter；
- 购买或收听 Lullatone 音乐；
- 购买周边；
- 了解同团队的 Typatone 等项目。

2014 年访谈中，iOS 版最初被描述为一种低摩擦支持方式；当前美国区价格已经是
`US$1.99`。App 的核心价值仍是离线、原生容器和对创作者的直接支持，而不是功能升级。

---

## 9. 局限、风险与授权边界

### 9.1 创作无法保留

当前没有：

- 内置 Record / Replay；
- Loop / Overdub；
- BPM / Metronome / Quantize；
- Pattern / Timeline；
- Save / Load；
- Audio / MIDI / Video Export。

因此，用户的价值集中在“当下演奏”，作品留存依赖系统录屏、外部录音或其他开发者
制作的扩展。

### 9.2 输入可发现性与精确性

- Desktop 能看到提示，但看不到每个字母的角色；
- Touch 区域完全不可见；
- Sound Set 切换没有名称、风格和预览；
- MIDI Mapping 依赖外部表格；
- 没有 Velocity、力度或连续控制帮助形成更细致表达。

这种隐藏性有利于探索，但不利于精确复现和可访问性。

### 9.3 闪烁与无障碍

官网和 App Store 都明确警告含有闪烁画面。当前 App Store 页面显示开发者尚未声明
具体 Accessibility Features。

此外，产品核心依赖：

- 视觉与听觉同时可感知；
- 全屏快速运动；
- 不可见触摸分区；
- 颜色和图形差异。

因此不能把“所有年龄都能上手”等同于已经覆盖视听、运动或认知无障碍需求。

### 9.4 代码 MIT 不等于资产采购完成

Patatap README 写明项目按 MIT License 自由分发，Two.js 也使用 MIT。但本次检查
没有在仓库根目录发现独立 `LICENSE` 文件，也没有在官网找到声音、动画、商标、
用户表演输出的分别授权条款；官网标为 “terms” 的入口实际打开 Privacy Policy。

因此应区分：

1. 阅读、研究和改造公开代码；
2. 使用 Patatap 声音创作或录制作品；
3. 把原始声音、动画或近似资产嵌入 LMDJ；
4. 把这些资产继续分发给 LMDJ 终端用户。

如果要执行第 3 或第 4 项，应取得创作者书面确认，或者重新制作拥有完整来源、修改、
嵌入、终端用户使用和导出授权的独立资产。本文不把 README 的一句 MIT 声明解释成
已经完成 OEM / Embedded Redistribution 审查。

### 9.5 隐私与当前状态

官网使用 Google Analytics。Apple 当前隐私标签说明 iOS App 可能收集但不关联身份的
Usage Data 和 Diagnostics；该说明由开发者申报，Apple 未验证。

GitHub 在 2026 年仍有依赖维护，但当前产品主体仍保留 2014 年形成的功能边界。
更准确的描述是：**仍可使用、仍有基础维护，但不是持续扩张功能的平台型产品。**

---

## 10. 同类与相邻产品地图

### 10.1 分类原则

不能把所有“音乐 + 画面”产品放在同一竞品集合。至少要区分：

| 类别 | 关键问题 | 代表产品 |
| --- | --- | --- |
| 即时视听乐器 | 用户动作是否直接同时成为声音和画面？ | Patatap、Bloom、Plink |
| 文字/绘画音乐化 | 日常输入能否转成音乐结构？ | Typatone、Kandinsky |
| 辅助演奏角色 | 系统是否帮助用户保持音高或和声正确？ | Blob Opera |
| Loop 组合工具 | 用户是否在同步循环中组合角色和声音？ | Incredibox |
| 可视化音乐对象 | 视觉对象是否同时是 Synth、Sequence 或 Mixer 对象？ | NodeBeat、Seaquence |
| 入门编曲工具 | 是否保存音符网格并形成可分享作品？ | Song Maker |
| 自动 Visualizer | 系统是否主要响应外部音频而非用户演奏事件？ | APEXvj、Synesthesia |
| 专业 VJ / Media Server | 是否包含 Layer、Clip、Mapping、Output、DMX？ | Resolume、VDMX |

最后两类是相邻产品，不是 Patatap 的直接竞品。

### 10.2 逐产品概览

| 产品 | 核心动作 | 音乐保护方式 | 视觉角色 | 保存/分享 | 与 Patatap 的距离 |
| --- | --- | --- | --- | --- | --- |
| [Typatone](https://typatone.com/) | 输入文字，字母对应音符 | 预定 Letter-to-Note 关系 | 写作过程的声音伴奏与反馈 | 文本形成可保留状态 | 同团队、同为 QWERTY 转译，但目标从表演转向写作 |
| [Plink](https://experiments.withgoogle.com/plink-multiplayer-music-experience) | 移动鼠标决定音高，点击发声 | 有限音阶与乐器集合 | 显示自己和其他参与者的演奏位置 | 最多四人实时合奏 | 同样即时、低门槛；核心差异是多人同步 |
| [Bloom](https://generativemusic.com/bloom.html) | 触摸屏幕生成音符和扩散图形 | Mood、音阶和生成规则 | 每个音符成为扩散的视觉 Bloom | 主要保存当下体验；闲置后自动生成 | 最接近触摸式视听乐器，但偏氛围和生成音乐 |
| [Kandinsky](https://musiclab.chromeexperiments.com/Kandinsky/) | 画线和形状，再播放画面 | 形状、位置和有限音色映射 | 视觉图形同时是可播放内容 | 可重复播放当前画布 | 比 Patatap 更接近简单 Composition Canvas |
| [Blob Opera](https://artsandculture.google.com/experiment/blob-opera/AAHWrq360NcGbw) | 上下控制音高、前后控制元音 | ML 自动和声 | 四个角色直接表现声音状态 | 以表演和分享体验为主 | 连续、具角色性的辅助演奏，不是 Sample Trigger |
| [Incredibox](https://www.incredibox.com/) | 把 Loop 图标拖到七个角色上 | 预制、同步、调性兼容的 Loop | 角色服装、动作和 Bonus Chorus | 约三分钟 Mix、URL、榜单、MP3 | 把即时愉悦推进到作品记录、传播和商业产品 |
| [NodeBeat](https://www.nodebeat.com/) | 连接 Generator 与 Note Node | Scale、Key、Tempo 和连接规则 | Node 图直接显示音乐关系 | 保存、录音和分享 | 从瞬时触发进入可视化生成结构 |
| [Seaquence](https://seaquence.app/) | 创建游动生物；每个生物拥有 Voice + Sequencer | Scale、Tempo、Step Grid、Polyphony | 生物同时是声音、序列和空间混音对象 | Session、Galaxy、Remix、音视频录制 | 视觉对象与音乐模型结合最深，复杂度也最高 |
| [Song Maker](https://experiments.withgoogle.com/song-maker) | 在网格绘制旋律和节奏 | 固定 Grid、Scale、Tempo | 视觉主要承担音符表示 | 保存并生成分享链接 | 视觉表演弱，但补齐基础编曲和作品链接 |

### 10.3 最接近 Patatap 的产品

按产品机制而不是外观判断：

1. **Bloom**：最接近“触摸即产生声音和短暂图形”的乐器关系；
2. **Plink**：最接近“无需音乐知识即可即兴”，并加入多人；
3. **Typatone**：同一团队、同一字母映射思路，但用写作提供持久上下文；
4. **Kandinsky**：同样建立图形与声音对应，但把图形保留为可播放画布；
5. **Incredibox**：表面交互不同，却最清楚展示如何从即时愉悦进入记录和传播。

### 10.4 从即时乐器到创作系统的复杂度阶梯

```text
Patatap
  一次输入 → 一次视听事件
        ↓
Bloom / Plink
  连续控制或多人共同演奏
        ↓
Kandinsky / Typatone
  输入留下可再次播放或阅读的状态
        ↓
Incredibox
  同步 Loop + Performance Recording + Share
        ↓
NodeBeat / Seaquence
  可视音乐对象 + Sequencer + Session + Export / MIDI
        ↓
完整 Groovebox / DAW / VJ Workstation
```

这不是质量排名。每向下一层增加能力，都会增加对象、状态、编辑、保存、授权、错误恢复
和学习成本。

---

## 11. 对 LMDJ 的研究价值与边界

以下是研究判断，不是功能设计或已批准规格。

### 11.1 Patatap 能证明什么

- 同一个用户事件可以自然地同时驱动声音和视觉；
- 视听同步可以建立在共享事件上，而不必先做通用音频分析；
- 严格策划的声音集合可以显著降低新手演奏失败率；
- 全屏短视觉手势可以增强 Pad Trigger 的身体感和记忆；
- 一个不要求 Project 的即时入口也能形成长时间探索。

### 11.2 Patatap 不能证明什么

- 视觉状态应该如何进入 LMDJ Project Truth；
- Pattern 切换是否必须绑定 Visual Scene；
- Momentary FX 应如何共同调制音频和视觉；
- Performance Replay 是否需要确定性视觉重放；
- 用户导入视频、实时生成图形、摄像头和灯光控制之间应选择哪一类；
- 浏览器、iPad 和 MIDI Hardware 下的实际端到端延迟是否合格；
- 原 Patatap 资产是否可以进入 LMDJ 商业分发。

### 11.3 当前最准确的参考定位

Patatap 是 LMDJ 研究中的：

> **Event-to-AV Feedback Reference**

它不是：

> LMDJ 的完整 Visual Product Blueprint。

LMDJ 当前已经确认的产品模型包含 64 Pad、Sample / Sequence / Perform、Pattern、
Performance、Export 和 Resample；Patatap 没有这些对象。反过来，LMDJ 当前已确认
规格也没有批准一个 Patatap 式视觉层。两者只能在事件反馈和内容约束层比较，不能
把相似性写成已决定的产品范围。

---

## 12. 后续验证清单

如果要把本研究推进为可用于产品决策的实测，建议分别完成：

### 12.1 Patatap 设备实测

- Desktop Chrome / Safari 的 Key-to-Sound 与 Key-to-Frame 延迟；
- iPhone / iPad Touch 分区、方向切换和 Multi-touch 行为；
- Web MIDI Input / Output 与不同控制器 Note Mapping；
- 快速重复、同时按键和长时间演奏时的 Voice Stealing；
- Background / Foreground、锁屏、音频中断和恢复；
- 网络首次加载、缓存和弱网；
- Reduce Motion、色觉、闪烁与 Screen Reader 行为。

### 12.2 内容实测

- 6 套声音的调性、音域、时长、LUFS 和频段；
- 13 Melody / 13 Rhythm 的当前每套实际分布；
- 不同 Set 内同一 Key 的声音角色是否稳定；
- 26 个视觉动作与声音包络、音色和语义的匹配方式；
- 多事件叠加时的视觉遮挡和音频 Headroom。

### 12.3 授权确认

- MIT 声明是否明确覆盖仓库内音频和视觉资产；
- 是否允许把资产嵌入付费产品；
- 是否允许向终端用户分发独立 Sample；
- 用户录制的 Patatap 表演能否商业发行；
- Patatap 名称、Logo 和视觉识别的使用边界。

---

## 13. 主要来源

### 13.1 Patatap 官方与一手来源

1. [Patatap 官网](https://patatap.com/)
2. [Patatap - Experiments with Google](https://experiments.withgoogle.com/patatap)
3. [Patatap GitHub Repository](https://github.com/jonobr1/Patatap)
4. [Patatap README](https://github.com/jonobr1/Patatap/blob/main/README.md)
5. [Patatap Palette Source](https://github.com/jonobr1/Patatap/blob/main/src/animations/palette.js)
6. [Patatap Input / MIDI Source](https://github.com/jonobr1/Patatap/blob/main/src/index.js)
7. [Patatap Keyboard to MIDI Conversion Table](https://patatap.com/conversion-table.html)
8. [Patatap App Store](https://apps.apple.com/us/app/patatap/id880626868)
9. [Two.js](https://two.js.org/)
10. [Lullatone Apps](https://www.lullatone.com/apps/)

### 13.2 创作者说明与历史资料

11. [It’s Nice That：Interview with Jono Brandel](https://www.itsnicethat.com/articles/patatap-1)
12. [Hypebot / Evolver.fm：Interview with Jono Brandel and Lullatone](https://www.hypebot.com/patatap-really-is-as-fun-and-artsy-as-it-sounds/)
13. [Typatone Statistical Analysis](https://typatone.com/stats.html)
14. [Jono Brandel / IdN Interview](https://www.idnworld.com/creators/JonoBrandel)

### 13.3 同类产品官方来源

15. [Typatone](https://typatone.com/)
16. [Plink - Experiments with Google](https://experiments.withgoogle.com/plink-multiplayer-music-experience)
17. [Bloom](https://generativemusic.com/bloom.html)
18. [Chrome Music Lab Kandinsky](https://musiclab.chromeexperiments.com/Kandinsky/)
19. [Blob Opera](https://artsandculture.google.com/experiment/blob-opera/AAHWrq360NcGbw)
20. [Incredibox](https://www.incredibox.com/)
21. [Incredibox FAQ](https://www.incredibox.com/info/faq)
22. [NodeBeat](https://www.nodebeat.com/)
23. [Seaquence](https://seaquence.app/)
24. [Chrome Music Lab Song Maker](https://experiments.withgoogle.com/song-maker)

---

## 14. 研究边界与版本管理

- 产品、价格、平台和授权信息以 2026-08-02 可访问资料为准，后续可能变化。
- 历史使用数据不代表当前活跃用户。
- 本文不是法律意见，商业使用和资产再分发必须取得正式授权结论。
- 本文没有批准 LMDJ 的视觉来源、视觉对象、录制格式、交互或技术栈。
- Version impact: none。本文只增加研究资料，不改变 Product Build、Core Module、
  Provider、Contract 或公开产品行为。
