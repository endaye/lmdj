# Koala Sampler 产品研究与 LMDJ 启示

> 研究日期：2026-07-28
>
> 研究对象：[Koala Sampler](https://www.koalasampler.com/)
>
> 研究性质：竞品与产品工作流研究，不代表 LMDJ 已批准的功能范围或实施计划

## 摘要

Koala Sampler 是一款以移动触屏为原生交互环境的采样器、编序器和演奏工具。它受到 Boss SP-303/SP-404 一类硬件采样器工作流的明显影响，但没有简单复制硬件面板，而是把采样、编辑、编序、表演和重采样压缩成一条短而连续的创作链路。

Koala 的核心优势不是单项 DSP 能力，也不是功能数量，而是：

1. 用户可以用一次直接操作把声音变成可演奏的 Pad。
2. 编辑始终服务于“尽快回到演奏”，不会把用户长期留在参数界面。
3. Resample 是创作循环中的基础动作，而不只是最终导出。
4. 高级功能可以逐层增加，但不改变最初的 `SAMPLE → SEQUENCE → PERFORM` 心智模型。
5. 产品主动连接 Ableton、MIDI、AUv3 和 SP-404MKII，而不是试图独占完整制作流程。

Koala 是 LMDJ 值得持续研究的参考产品，但 LMDJ 不应成为网页版 Koala。两者的起点不同：

- Koala 从一段原始声音开始，由用户完成采样、切片和编排。
- LMDJ 从一首完成音乐开始，由 AI/音频管线生成带语义角色的 16 Pad Patch。

因此，LMDJ 更合适的方向是：**AI 先完成最费时间的拆分、筛选和映射，再提供 Koala 式的直接操作，让用户立即把结果变成自己的演奏。**

---

## 1. 产品定位

Koala 官方将产品定位为一款 pocket-sized sampler。更准确地说，它是一台以触屏为主要操作面的便携采样乐器，而不是缩小版 DAW。

它围绕三个核心页面组织工作：

1. `SAMPLE`：录音、导入、切片和调整 Sample。
2. `SEQUENCE`：实时演奏 Pad，并把演奏录成 Sequence。
3. `PERFORM`：切换 Sequence，使用实时效果完成表演和录制。

这三个页面不是传统软件中的功能分类，而是一个从声音到作品的时间顺序。用户不需要从工程、轨道、插件或路由开始，只需要先获得一个声音。

### 1.1 当前产品能力概览

根据 Koala 官方网站、官方手册和应用商店资料，截至研究日期，主要能力包括：

- 最多 64 个 Sample Pad，分为 A、B、C、D 四个 Bank。
- 32 个 Sequence Slot。
- 麦克风录音、音频文件导入和视频音频提取。
- 从应用自身输出进行 Resample。
- Start/End、Volume、Pitch、Pan、One-shot、Loop、Reverse。
- Attack、Release、Tone 和 6 个 Choke Group。
- 自动切片、Equal Chop、Transient Chop 和 MPC 式 Lazy Chop。
- 四轨 Stem Split：Drums、Bass、Vocals、Other。
- 16 个实时 Performance FX。
- MIDI 输入、Velocity、MIDI Learn 和外部 MIDI Clock。
- WAV、Stems、Koala Song、Ableton Drum Rack 和 Ableton Live Set 导出。
- iOS、Android、macOS、Windows、Linux 和 Raspberry Pi 版本。

这些能力使 Koala 可以承担三种角色：

- 随身声音采集器；
- Beat / Loop 创作工具；
- 进入 Ableton、硬件采样器或更大型制作环境之前的 sketchpad。

---

## 2. 核心创作工作流

Koala 的主要创作飞轮可以概括为：

```text
环境声音 / 文件 / 视频
        ↓
录制或导入一个 Pad
        ↓
裁剪、切片、变调和设置播放方式
        ↓
实时演奏 Pad 并录成 Sequence
        ↓
切换 Sequence + 使用 Live FX 表演
        ↓
Resample 到新的 Pad
        ↓
再次切片、叠加、编排
        ↓
导出 WAV / Stems / Ableton 工程
```

这条链路最重要的特征是闭环：任何阶段的结果都可以重新成为一个 Sample，继续进入下一轮创作。

### 2.1 Pad 同时是容器、录音按钮和乐器键

在 Koala 中，用户按住空 Pad 就能开始录音，松开后停止。声音随即落在这个 Pad 上并可以直接演奏。

这压缩了传统软件中的多个步骤：

```text
创建轨道 → 选择输入 → Arm → 录音 → 停止 → 裁剪 → 拖入 Sampler
```

在 Koala 中，这些步骤被缩短为：

```text
按住 Pad → 发出声音 → 松开 → 演奏
```

开发者 Marek Bereza 在访谈中把这种 immediacy 视为 Koala 的核心。他对传统软件 Sampler 的主要批评是：许多 Sampler 本身并不能直接采样，用户必须先在其他位置录音，再把文件拖入 Sampler。

### 2.2 Resample 是创作原语

Koala 允许用户把以下结果直接录回新的 Pad：

- Pad 演奏；
- Sequence；
- 实时效果处理；
- Mixer 处理后的总输出。

这是一种复杂度压缩机制。用户不需要理解复杂的 Bus、Freeze、Flatten 或非破坏编辑，也可以通过多次重采样构造复杂声音。

Resample 同时带来一种“做出决定并继续前进”的创作节奏。它牺牲了一部分可逆性，但减少了无休止微调。

### 2.3 Sequence 是可操作对象

Koala 不只允许编辑 Sequence 内部的 Note，也允许把整个 Sequence 当成对象拖动：

- 拖到空 Slot：复制。
- 拖到已有 Slot：合并两者。
- 使用 Add to End：把一个 Sequence 接到另一个之后。

这使基础 Arrangement 不需要先出现一条完整 DAW Timeline。Pattern 之间的关系通过拖拽即可建立。

### 2.4 Performance 是正式创作阶段

`PERFORM` 不是单纯的播放页面。用户可以：

- 切换不同 Sequence；
- 同时使用多个实时效果；
- Hold 效果状态；
- 录制演奏结果；
- 把表演重新采样。

因此，Koala 的作品并不只存在于 Sequence 数据中，也存在于用户对 Sequence 和 Effects 的实时操作中。

---

## 3. Sample 编辑模型

Koala 的 Sample Editor 提供了足够完成创作的高频控制，但没有一开始就展示完整参数面板。

### 3.1 基础控制

- `Start / End`：直接在波形上拖动播放区域。
- `Volume / Pitch / Pan`：按住控件后滑动修改。
- `One-shot`：点击后播放完整选区。
- `Gate`：只在按住时播放。
- `Loop`：循环播放，并支持 Hold 行为。
- `Reverse`：反向播放。
- `Attack / Release`：控制包络。
- `Tone`：快速低通/高通式音色调整。
- `Choke Group`：让相同组内的声音互相停止。

### 3.2 编辑工具

- Crop。
- Normalize。
- Trim Silence。
- Make Mono。
- Bounce 到新 Pad。
- 导出单个 WAV。
- Stem Split。
- Auto-chop。

### 3.3 高级切片

Samurai 内购提供多种切片方式：

- `TRANSIENTS`：根据瞬态自动识别切点。
- `EQUAL`：等长切片。
- `LAZY`：播放过程中由用户实时敲入切点。

Lazy Chop 尤其体现了 Koala 的设计方向：它优先把技术编辑转换成演奏动作。

---

## 4. Sequence、量化与 Piano Roll

Koala 默认鼓励实时录制：

1. 选择空 Sequence。
2. 设置长度、速度、拍号和量化。
3. 启动 Record。
4. 实时演奏 Pad。

Samurai 提供 Piano Roll，用于进一步编辑：

- Note 位置。
- Pitch。
- Velocity。
- Copy/Paste。
- Reverse。
- Stretch。
- Legato。

这个顺序值得注意：**Piano Roll 是演奏之后的精修工具，而不是开始创作之前必须理解的界面。**

这对 LMDJ 的 Take Recording 有直接启发：

- Take 的第一入口应当是实时演奏录音。
- 原始演奏 Timing 应作为事实记录保留。
- Quantize 更适合作为录音后的可选处理或派生版本。
- 逐 Note 编辑不应成为第一阶段录制能力的前置条件。

---

## 5. Performance FX 与 Mixer

### 5.1 Performance FX

Koala 提供 16 个面向实时演奏的效果。它们通过触屏区域快速控制，而不是通过传统插件参数面板操作。

这种设计强调：

- 立即可听；
- 可同时使用多个效果；
- 可通过 Hold 保留效果状态；
- 处理后的结果可以继续 Resample。

效果因此不是“混音完成后的修饰”，而是表演动作的一部分。

### 5.2 Mixer 内购

Mixer 扩展提供：

- 4 条 Bus Channel。
- 1 条 Main Channel。
- 每条 Channel 最多 5 个 Effect Slot。
- Mute、Solo、Fader 和 Meter。
- 29+ 内置效果。
- Sidechain 等较完整的混音能力。
- 在支持的平台上托管 AUv3、VST3 或 CLAP 插件。

Mixer 让 Koala 逐渐接近完整 Groovebox，但它仍保持为独立付费层，没有改变基础版本的核心工作流。

---

## 6. Stem Split 与 AI 的角色

Koala 可以把一个 Sample 分为最多四个 Stem：

- Drums。
- Bass。
- Vocals。
- Other。

Stem Split 在产品中的位置是 Sample Editor 内的一项工具。分离结果仍然回到 Pad 系统中，用户可以立即演奏、切片和重采样。

这与 LMDJ 的差异非常重要：

- Koala 把 AI 分离作为用户主动调用的局部工具。
- LMDJ 把音频理解、分离、Material 提取和 Pad 映射作为生成 Patch 的主要管线。

Koala 对 LMDJ 的启发不是“也做四轨分离”，而是：

> AI 处理完成后，结果必须立即回到统一、可触摸、可演奏的对象系统中。

如果 AI 结果只能查看、下载或重新提交处理，而不能马上演奏和改造，创作链路就会中断。

---

## 7. 导出与外部生态

Koala 没有要求用户必须在应用内完成整首作品。

### 7.1 导出层次

官方手册列出的主要导出包括：

- 当前 Sample。
- 全部 Sample ZIP。
- 当前 Sequence。
- 全部 Sequence。
- Mixed stereo。
- 逐 Pad Stem。
- `.koala` 项目文件。
- Ableton Drum Rack。
- Ableton Live Set。

Sample 导出还区分：

- Raw Sample：未应用编辑设置的原始声音。
- Edited Sample：包含选区和编辑处理的版本。

这种区分对 LMDJ 很有价值。LMDJ 的 Creator Export 可以继续明确区分：

- AI/管线产生的原始 Material。
- 用户编辑后的 Pad Asset。
- Take 的事件数据。
- Take 或 Pattern 的 Mixed WAV。
- 可以继续进入 DAW 的 Stem/MIDI。

### 7.2 Ableton

Koala 可以：

- 导出包含全部 Pad 的 Ableton Drum Rack。
- 导出 Ableton Live Set。
- 为 Live Lite 导出混合 Loop。
- 为完整版 Live 导出 Sequence Stems。
- 在支持平台上使用 Ableton Link 同步。

这说明 Koala 把 Ableton 视为继续 Arrangement 的目的地，而不是竞争对象。

### 7.3 MIDI 与硬件

Koala 支持：

- MIDI Note 触发 Pad。
- Velocity。
- MIDI Learn。
- MIDI CC 控制。
- MIDI Note Offset。
- 外部 MIDI Clock。
- 蓝牙 MIDI。
- Samurai 中的 MIDI Out。

Roland 从 SP-404MKII 4.04 系统开始提供 Koala Controller Mode。连接移动设备后，SP-404MKII 可以直接控制 Koala 的：

- Bank A–D。
- Pad 1–16。
- Gate。
- Loop。
- Reverse。
- Delete。
- Sample、Sequence、Perform、Edit 页面切换。
- 空 Pad 录音。
- 双向音频采样。

这是 Koala 产品成熟度的重要信号：硬件厂商已经把它视为可以进入正式音乐制作链路的工具，而不只是手机应用。

---

## 8. 商业模式

Koala 采用低门槛基础应用加模块化内购：

### 基础应用

基础应用已经能够完成：

- 采样。
- 基础 Sample 编辑。
- Sequence 录制。
- Performance FX。
- Resample。
- 导出。
- Stem Split。
- MIDI 控制。

### Samurai

Samurai 面向希望进行更深编辑和编曲的用户：

- Timestretch。
- Piano Roll。
- Auto-chop。
- 3-band EQ。
- Quokka Synth。
- MIDI Out。

### Mixer

Mixer 面向希望在 Koala 内完成更多混音工作的用户：

- 4 Bus + Main。
- 29+ 效果。
- 多效果槽。
- 外部插件托管。

这种分层的产品逻辑是：先让基础创作闭环成立，再对“编辑深度”和“混音深度”收费。它没有把第一次获得声音、第一次录制 Sequence 或第一次导出锁在高级版本之后。

---

## 9. Koala 的产品优势

### 9.1 极短的首次成功路径

用户不需要理解音轨、Clip、Bus 或插件，就可以在数秒内获得一个可演奏的声音。

### 9.2 统一对象模型

声音最终都落在 Pad；演奏最终都落在 Sequence；表演结果可以再次落回 Pad。产品中的对象数量有限，关系清楚。

### 9.3 直接操作

按住、拖动、捏合、双击等触屏动作承担了大量功能，减少了菜单层级。

### 9.4 创造性限制

Koala 鼓励用户做决定、Bounce 和继续演奏，而不是无限保留所有可编辑状态。

### 9.5 从简单到复杂

新用户可以只使用 Sample、Sequence 和 Perform；高级用户再逐步进入 Chop、Piano Roll、Mixer、Synth 和外部插件。

### 9.6 开放的制作链路

Ableton、MIDI、AUv3 和 SP-404MKII 集成使 Koala 可以成为大型工作流的一部分。

---

## 10. 局限与风险

### 10.1 隐藏手势的可发现性

长按、双击、拖动方向和 Settings 开关承载了大量能力。熟练后很快，但新用户可能无法自然发现。

### 10.2 功能膨胀

随着 Mixer、Quokka、插件托管和多平台桌面版加入，Koala 正在从简单 Sampler 变成完整 Groovebox。产品需要持续防止高级能力侵入基础工作流。

### 10.3 平台不一致

iOS、Android 和桌面端在以下方面存在差异：

- AUv3。
- 外部插件托管。
- Ableton Link 的版本历史。
- Stem Split 的运行模式。
- 系统文件和音频能力。

### 10.4 Resample 的不可逆性

Resample 能加速创作，但多次 Bounce 后，来源、参数和处理关系不如 DAW 中清晰。

### 10.5 复杂 Arrangement 不是强项

Sequence Slot 适合 Beat、Loop 和现场切换，但复杂歌曲结构、长时间线编辑和团队协作仍更适合 DAW。

---

## 11. Koala 与 LMDJ 的关键差异

| 维度 | Koala Sampler | LMDJ |
| --- | --- | --- |
| 起点 | 原始声音、文件、视频或麦克风 | 一首完成音乐 |
| 核心动作 | 采样、切片、演奏、重采样 | AI 分析、分离、Material 提取、Patch 映射 |
| 主要对象 | Sample、Pad、Sequence、Performance | Project、Patch、Pattern、Pad、Scene、Element、Render、Lineage |
| Pad 组织 | 64 Pad，四个 Bank | 稳定的 16 Pad 语义角色布局 |
| AI 角色 | Sample Editor 内的一项 Stem Split 工具 | Patch 生成主管线的一部分 |
| 编辑方式 | 用户从原始素材主动构建 | AI 先生成，用户再选择、修正和演奏 |
| 作品出口 | Koala Song、WAV、Stems、Ableton | Creator Export、Patch、Samples、未来 Take JSON/MIDI/WAV |
| 主要价值 | 让任何声音快速变成 Beat | 让一首歌快速变成可拥有、可演奏的乐器 |

两者最接近的地方不是 Stem Split，而是“处理结果最终落在 Pad，并且能够立即演奏”。

---

## 12. 对 LMDJ 的建议

以下内容是本次调研结论，不代表已经批准的产品规格。

### 12.1 第一优先级：采用直接的 Sample Edit 操作语法

建议重点参考：

- 波形上直接拖动 Start/End。
- Loop / One-shot 的明确切换。
- 高频 Volume、Mute 控制。
- Swap 后保持 Pad Slot、Role 和映射。
- Edited Sample Bounce 到新资产。

不建议第一阶段就复制 Koala 的完整 Sample Editor、EQ 和高级 Chop。

### 12.2 第二优先级：Take 首先是演奏录音

建议：

1. 用户按 Record 后直接演奏 16 Pad。
2. 系统保存原始事件时间和力度。
3. Quantize 作为可选的派生处理。
4. 导出同时保留 Raw Take 与 Quantized Take。
5. Piano Roll 或逐 Note 编辑放在后续阶段。

Koala 的顺序证明：实时录制可以先独立形成价值，不必等待完整编序器编辑能力。

### 12.3 第三优先级：把 Bounce 变成创作动作

可以研究以下动作：

- Pad Edit → Bounce New Asset。
- Pattern → Bounce Loop。
- Take + Pad 状态 → Bounce Stereo WAV。
- 用户编辑结果 → 新版本资产，同时保留 Lineage。

LMDJ 应保留比 Koala 更清晰的来源关系，避免 Bounce 后失去 AI Material、Pad Role 和用户修改之间的联系。

### 12.4 第四优先级：坚持固定 4×4 肌肉记忆

建议继续保持：

- Pad 位置不会因 AI 结果动态重排。
- 角色与 Slot 的关系稳定。
- 键盘、Web MIDI、触屏使用同一映射。
- 缺失 Material 显示 Empty，而不是移动其他角色补位。

Koala 的 Bank 可以扩展容量，但 LMDJ 当前没有必要因此引入 64 Pad 或多 Bank。

### 12.5 第五优先级：完善“出去继续做”的交付

Creator Export 可以继续向以下结构演进：

- Raw Material。
- Edited Pad Asset。
- Pattern/Take Event JSON。
- MIDI。
- Mixed WAV。
- Per-pad 或按角色组织的 Stems。
- 明确的 Lineage 和版本关系。
- 在 Ableton 等 DAW 中可以继续编辑，而不是只得到扁平音频。

### 12.6 处理云端等待与本地即时性的差异

Koala 的操作大多是设备本地即时完成；LMDJ 的 AI/音频管线存在上传、排队、分离和提取等待。

因此，LMDJ 不能只复制 Koala 的操作界面，还需要保留自身的状态表达：

- Uploading。
- Queued。
- Separating。
- Extracting。
- Patchifying。
- Quality Review。
- Failed。
- Partial Export。

处理完成后的目标应当是：用户第一次进入 Patch 时已经面对一个可以直接演奏的 16 Pad 乐器，而不是另一个需要配置的工程。

---

## 13. 暂不建议跟进的范围

短期不建议 LMDJ 跟进：

- 64 Pad 和四个 Bank。
- 完整 Piano Roll。
- 四 Bus Mixer。
- 29+ 内置效果。
- 第三方插件托管。
- 内置 Synth。
- 完整 Song Arrangement。
- 通用 Groovebox 工程格式。

这些功能会显著扩大产品边界，并可能弱化 LMDJ 最独特的路径：

```text
完成音乐 → AI Patch → 稳定 16 Pad → 立即演奏和再创作
```

---

## 14. 结论

Koala Sampler 最值得 LMDJ 学习的不是视觉皮肤，也不是功能数量，而是它对创作连续性的坚持：

1. 任何声音都能在一次动作后变成可演奏 Pad。
2. 编辑结束后立即回到演奏。
3. 录制和重采样是创作循环，而不是保存动作。
4. 高级能力逐层出现，但不破坏最初的工作流。
5. 产品允许用户把结果带到其他软件和硬件中继续完成。

Koala 的产品命题可以概括为：

> 让任何声音快速成为一首 Beat。

LMDJ 更适合形成自己的命题：

> 让用户快速拥有一首歌，并把它重新演奏出来。

---

## 15. 主要来源

### 官方来源

1. [Koala Sampler 官网](https://www.koalasampler.com/)

2. [Koala Sampler 官方完整手册](https://manual.koalasampler.com/one-page/)

3. [Samurai 功能说明](https://www.koalasampler.com/samurai/)

4. [Mixer 功能说明](https://www.koalasampler.com/mixer/)

5. [Koala 桌面版下载与平台说明](https://www.koalasampler.com/download/?p=win64)

6. [Koala Sampler Release Notes](https://cdn.koalasampler.com/builds/release-notes.html)

7. [Apple App Store 产品页](https://apps.apple.com/us/app/koala-sampler-beat-maker/id1449584007)

8. [Roland SP-404MKII Koala Sampler 更新说明](https://www.roland.com/global/support/by_product/sp-404mk2/updates_drivers/174cc2fc-ddb2-4128-87a0-848b882cdcea/)

9. [Roland SP-404MKII Koala Controller Mode 操作映射](https://static.roland.com/manuals/sp-404mk2_v4_koala_sampler/eng/164266033.html)

### 背景与开发者资料

10. [Synth Talk：Marek Bereza Creator of the Koala Sampler](https://www.synthtalk.net/articles/marek-bereza-creator-of-the-koala-sampler)

11. [MusicRadar：Shabaka Hutchings on Koala Sampler workflow](https://www.musicradar.com/artists/the-koala-app-is-amazing-its-the-best-sampler-and-the-deeper-you-go-the-madder-it-gets-shabaka-hutchings-on-his-journey-from-jazz-saxophone-to-ipad-beatmaking)

## 16. 研究边界

- 功能、平台和商业信息以 2026-07-28 可访问的官方资料为准，后续版本可能变化。
- 本文未进行长期实机使用测试，关于交互效率的判断主要来自官方工作流、开发者访谈和产品结构分析。
- 本文对 LMDJ 当前状态的引用用于竞品对照；具体实施仍需经过独立设计确认、规格评审和验证。
