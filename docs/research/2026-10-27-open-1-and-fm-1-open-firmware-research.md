# OPEN-1 多固件合成器概念与 FM-1 开放固件生态调研

> 调研日期：2026-10-27。
> 目标：弄清 RedtailWorks OPEN-1 是什么、它与 M-VAVE FM-1 自定义固件热潮及官方 FM1 Open 的关系，
> 评估其可信度，并记录对 LMDJ 有参考价值的部分。
> 证据范围：作者自己的项目页与源码仓库、厂商动向的媒体报道、社区固件索引；没有实物、原型、
> 源码构建或刷机实测。触发本次调研的是一张中文媒体截图，其内容（37 键、32 MB 内存、16 MB
> 固件闪存、目标价低于 $200、首发移植 HYP-1/LOF-1/ECO-1/GRAV-1）与 [S01] 一致。
> 文档性质：外部产品与生态研究，不是 LMDJ 的硬件选型、开源决定、Contract、实施计划或排期承诺。
> 第 4、5 节中标为“判断”的内容是作者推断，不是来源事实。

## 1. 结论

1. **OPEN-1 目前只是个人发起的概念项目，不是产品。** 作者页面原话是 “Not a product yet”，
   所有规格与价格都是 “a target, not a promise”。截至访问日，它处于 Daisy Seed 面包板原型和
   v0.4 beta 电路板设计阶段，没有融资、量产伙伴或开放的 SDK。[S02]
2. **媒体报道的规格已经过时。** [S01] 和中文转述描述的是 10 月 17 日的 37 键概念版；作者页面在
   10 月 18 日改为 27 键，10 月 20 日又改为 **不带键盘的 “Bring your own keys” v0.4 beta**：
   基于 Daisy Seed（STM32H750，480 MHz，64 MB），16 个 Cherry MX RGB pad，用 FM-1 或其他 MIDI
   键盘弹奏。4 天内换了 3 版设计。[S02]
3. **它是 FM-1 固件热潮的衍生物。** FM-1 是约 $70 的口袋 FM 合成器，社区在约三周内摸清了加载
   自有代码的方法，10 月 17 日已有 63 个社区固件项目；同日 M-VAVE 正式发布 FM1 Open（浏览器
   Workbench、GPL-3.0 应用源码、闭源二进制引擎 SDK）。[S07] OPEN-1 作者是其中一位固件作者，
   其代表作 HYP-1 本身 fork 自他人的 AMB-1，平台层来自 Felucca。[S04]
4. **判断：方向成立，执行风险高。** 多固件切换、大内存和“先模拟器后硬件”针对的都是 FM-1 的真实
   痛点；改成无键盘、复用现有 FM-1 当控制器也是务实的收缩。但一人项目、首批 1,000 台估算需要
   $100–120k、价格目标尚未按新设计重算、软硬件许可证均未声明，这些都还没有答案。
5. **对 LMDJ 的建议：只作观察，不作为硬件选型输入。** 值得借鉴的是“同一份源码同时编译到设备和
   浏览器”的开发入口，以及 FM1 Open 许可证争议给“分层开源”留下的教训（第 5 节）。

## 2. 背景：FM-1 自定义固件热潮与 FM1 Open

### 2.1 FM-1 硬件

| 项目 | 内容 | 来源 |
| --- | --- | --- |
| 定位 | 便携、电池供电的 FM 合成器，2026 年夏初发布 | [S06] |
| 价格 | 约 $70；[S06] 页面不同处另有 €60、$80 的说法 | [S07][S06] |
| 主控 | JieLi（杰理）AC791N；部分固件说明提到双核 pi32v2 | [S08] |
| 时钟与内存 | 240 MHz，约 432 KB 工作内存（用于与 OPEN-1 对比） | [S01] |
| 键盘与屏幕 | 27 键（16 白 11 黑），240×240 彩屏 | [S08] |

### 2.2 社区固件热潮

- 独立开发者用了大约三周，摸清了怎样往这台 $70 的 FM 合成器加载自己的代码；10 月 17 日
  FW Radar 统计到 **63 个社区固件项目**。[S07]
- [S06] 的说法是社区先发现了一个 “backdoor”，再借助 AI 写出自定义固件；该文没有说明发现过程。
- 社区索引在访问日可见部分已列出 107 条，其中 Felucca 系 68、SLOOP 系 31、FoMni 系 5、独立
  引擎 3；页面被截断，实际总数更高。[S08] 同一索引中有安装器托管在 `chatgpt.site`、仓库名
  `Fm1dnbchatgpt`、条目链接到 Claude artifact 等迹象，**只能间接说明** AI 参与开发，不是统计。[S08]
- 刷机途径：官方 Web Workbench 直接 USB 刷写、macOS 更新程序、Python 刷写脚本、多数社区固件的
  WebMIDI 安装器；部分固件提供 USB Rescue Boot。[S08]
- 10 月 16 日，被许多社区固件作为底层平台的 Felucca 的维护者宣布退出主动开发。[S07]

### 2.3 官方回应：FM1 Open

| 日期 | 事件 | 来源 |
| --- | --- | --- |
| 10-14 | Elektronauts 用户贴出 `fm1_open` 仓库；Charles Vestal（X0X、FoMni 作者）当天提出 GPL 投诉 | [S07] |
| 10-16 | 仓库可见历史从 “Initial FM1 Open V12 release” 提交开始 | [S07] |
| 10-17 | M-VAVE 宣布 FM1 Open，仓库升至 V13 | [S07] |
| 10-20 | 媒体报道 SDK 链接到 GitHub release V14 | [S05] |

FM1 Open 包含：中英双语浏览器 Workbench（不接设备即可试用核心功能，也能管理样本、刷写固件）、
应用源码、配套二进制 SDK，以及一个官方替代固件。[S05][S06] 该固件把设备变成 8 轨乐器：
DX7 式 FM、303 式 bass、808 式鼓机、PSG chiptune、pluck、8 槽采样，64 步音序，每轨音量、
loop 长度、mute/solo 以及混响/延迟发送。[S05][S07]

构建工具链：设备固件需要 Windows x64 和 JieLi PI32v2 clang；Web 版用 WASI SDK 27 构建。[S07]

### 2.4 许可证与归属争议

| 部分 | 许可 | 来源 |
| --- | --- | --- |
| M-VAVE 应用代码 | GPL-3.0-only，附第 7 节许可，允许与 FM1 二进制 SDK 链接 | [S07] |
| 核心引擎 `libfm1_engine.a` | 专有；仅限在 FM1 设备上运行的固件免版税再分发；不提供源码 | [S07] |
| Boot、更新文件、V15 恢复镜像 | Apache-2.0 | [S07] |
| 第三方组件 | 保留各自许可：Open303、DaisySP、Plaits、stmlib、emu2149、Dexed/MSFA（文章称均为 MIT 或 Apache-2.0） | [S07] |

- Vestal 指控包括他本人代码在内的 GPL 代码与闭源二进制一起分发；M-VAVE 据报已下架相关内容进行
  许可审查。截至 10 月 18 日，[S07] 没有找到 M-VAVE 对许可或署名投诉的详细公开声明。
- [S06] 作者批评官方固件借用了其他固件却未披露，并称 M-VAVE 对 Dexed 也是如此。
- M-VAVE 没有采用签名 bootloader 封锁第三方固件。[S07] [S06] 的读者评论称刷入新官方固件后无法加载
  自定义固件、降级到 v15 可恢复；这是**评论，未经核实**。

## 3. RedtailWorks 与 OPEN-1

### 3.1 作者与现有 FM-1 固件

- Alexander Gaddis（RedtailWorks），波特兰电子音乐人。[S01] GitHub 账号 RustyPawz。[S03][S04]
- 五个 FM-1 固件（均声明 “free and open source”，安装风险自负）：[S03]

  | 固件 | 状态 | 内容 |
  | --- | --- | --- |
  | HYP-1 | Stable | 催眠 techno/acid：pad、drone、生成式 303 线、鼓上的 grain |
  | LOF-1 | Experimental | lofi groovebox：你弹主旋律，爵士乐队跟随 |
  | ECO-1 | Experimental | 三片叶子随光照与浇水触发音符，昼夜循环 |
  | GRAV-1 | Experimental | 暗黑氛围：彩色噪声恒星与至多六颗行星，每颗行星一个声部 |
  | CTY-1 | Experimental | 每次开机生成新城市，车辆、建筑、风暴变成音符 |

- HYP-1 仓库：GPL-3.0-only；fork 自 `charlesvestal/fm1-amb`（AMB-1），README 称建立在其生成式
  和声、声部与平台工作之上；硬件、USB、更新加载、存储等平台层来自 Felucca（经 X0X、FoMni-1）。
  访问日 118 个提交、26 star。[S04]
- HYP-1 已有浏览器模拟器：`web/emu/build_clang.sh` 用普通 clang 把同一份代码编译到浏览器运行，
  并注明这个想法来自 Groove OS。[S04]
- 项目页声明 OPEN-1 “not affiliated with or endorsed by M-VAVE”。[S02]

### 3.2 OPEN-1 设计演变

| 日期 | 版本 | 要点 | 来源 |
| --- | --- | --- | --- |
| 10-17 | 概念发布 | 37 键、pad、旋钮、microSD 固件库，目标价低于 $200；同日砍掉蓝牙，键盘不带力度、pad 保留力度 | [S02] |
| 10-18 | Design 2 | 27 键、4×4 共 16 pad、16 个带灯按钮、按压编码器，约 320×230 mm；增加 4 路音频输入输出、MIDI A/B、同步、2 路 CV、踏板、USB-C host；零件成本记为约 $73 | [S02] |
| 10-20 | v0.4 beta | “Bring your own keys”：去掉键盘，面板兼作轴体定位板；原理图完成 | [S02] |
| 10-23 | 媒体报道 | 仍按 10-17 概念版报道：37 键、8 力度 pad、8 无级编码器、32 MB、16 MB 闪存、4″ 480×320 屏 | [S01] |

### 3.3 当前 v0.4 beta 目标规格

| 项目 | 目标 | 与 FM-1 对比 |
| --- | --- | --- |
| 主控 | Daisy Seed 上的 STM32H750，480 MHz Cortex-M7 | 2 倍时钟 |
| 内存 | 64 MB + 1 MB 片上 | 约 432 KB [S01] |
| 存储 | 8 MB 内置 + 一张 microSD（固件、样本、工程） | — |
| 键盘 | 不内置；外接 FM-1 或 USB/TRS MIDI 键盘 | 27 键内置 |
| Pad | 16 个 RGB pad（两排 8 个，Cherry MX 轴，可当键盘弹） | — |
| 菜单键 | 8 个 Cherry MX 键，由各固件在屏幕上标注功能 | — |
| 控制 | 4 个旋钮、2 条触摸条（默认 pitch/mod） | — |
| 屏幕 | 2.0″ 320×240 IPS | 240×240 |
| 音频 | 立体声线路输入；立体声输出与耳机 24-bit；内置喇叭 | — |
| MIDI/USB | TRS MIDI 输入输出（Type A）；USB-A host 接控制器；USB-C 连电脑与充电（二者同一时间只能用一个） | — |
| 其他 | LiPo 电池；仅有线、无蓝牙；约 161×96 mm | — |

以上全部来自 [S02]。多固件模型：多个固件同时安装，从菜单切换；每个固件在 SD 卡上一个目录；
每个固件自行为 8 个菜单键命名。[S02]

### 3.4 价格、资金与阶段

- 价格目标（美元，不含税和运费）：早鸟 $159，众筹 $179，零售 $199。页面注明这些价格是
  “set for the keyboard design”，之后会更新；beta 零件成本标为 TBD，正在重算。[S02]
- 面包板原型约 $80–250；**首批 1,000 台估算 $100–120k**。[S02]
- 当前资金来自 Ko-fi 打赏；页面欢迎合作、制造与固件方面的邮件联系。[S02]
- 阶段规划：之后才众筹；第 4 阶段为 “Emulator, SDK and firmware jam”，开发者在硬件出货前用浏览器
  开发固件，由社区投票选出首发固件包；首批 1,000 台预装社区固件包。[S02]
- 软硬件许可证均未声明，只提到 “open SDK”、“free toolchain” 和已分享的 KiCad 文件。[S02]

### 3.5 项目页自身的不一致

[S02] 各处说法尚未统一：内存倍数写作约 150 倍和约 75 倍（以 64 MB 规格为准）；内置存储写作 8 MB
和 16 MB；音频写作立体声输入输出和 4 进 4 出；零件成本写作约 $73 和 TBD；价格目标仍基于已经放弃的
键盘版设计。

## 4. 评估

### 4.1 成立的部分

- **需求真实存在。** 63 个社区固件和官方被动跟进，说明“便宜硬件 + 可刷固件”有开发者与用户需求。[S07]
- **设计针对真实痛点。** FM-1 一次只运行一个固件 [S02]，刷机需要专门流程 [S08]，内存约 432 KB [S01]；
  OPEN-1 用菜单多固件切换、microSD 固件库和 64 MB 内存分别回应这三点。
- **判断：转向无键盘设计是务实的收缩。** 去掉键盘减少了机械与成本风险，也让 OPEN-1 从 FM-1 的竞品
  变成可以接 FM-1 的“计算盒”，复用 FM-1 现有用户。Daisy Seed 是现成模块，FM1 Open 自己也引用了
  Daisy 生态的 DaisySP [S07]，DSP 层的移植路径比从零设计主板短。
- **判断：“先模拟器后硬件”是正确顺序。** 作者已有能在浏览器运行的 HYP-1 模拟器 [S04]，FM1 Open 也把
  浏览器 Workbench 作为主入口 [S05]；生态冷启动最便宜的地方是浏览器。

### 4.2 主要风险

- **判断：仍处于反复修改的早期。** 4 天 3 版设计 [S02] 适合点子阶段，但说明还没有任何规格被冻结。
- **资金缺口。** 首批 $100–120k 的估算 [S02] 与 Ko-fi 打赏之间差距很大；众筹尚未开始。
- **价格目标尚未成立。** $159–199 基于已放弃的键盘版，新设计的零件成本仍是 TBD。[S02]
- **判断：“移植”不是搬运。** HYP-1 等固件的平台层是 Felucca 为 JieLi 芯片编写的 [S04]，换到
  STM32H750 需要重写硬件抽象层；能直接复用的是 DSP 与交互逻辑。浏览器模拟器能跑说明代码已有一定
  分层，但设备端移植工作量仍未知。
- **许可证空白。** OPEN-1 页面没有声明任何许可证 [S02]，而首发候选固件 HYP-1 是 GPL-3.0-only 的
  fork 链 [S04]。判断：FM1 Open 的争议 [S07] 已经表明，“GPL 应用 + 闭源 SDK”在这个社区会立刻遭到
  质疑；OPEN-1 若想做开放平台，许可证需要先于 SDK 确定。
- **单人项目与上游维护。** 作者是固件和声音设计者，硬件、量产、售后都是新领域；作为 HYP-1 平台层
  上游的 Felucca 已经降低维护强度。[S07]

### 4.3 判断

值得关注，不应视为可采购或可规划的产品。它更接近“FM-1 社区里一位活跃固件作者的公开硬件实验”。
第 6 节列出能判断它是否进入下一阶段的信号。

## 5. 对 LMDJ 的参考

1. **同一份源码同时面向设备与浏览器。** FM1 Open 的 Web 版用 WASI SDK 27 构建 [S07]，HYP-1 用 clang
   把同一份代码编译到浏览器 [S04]。LMDJ 已经通过 Emscripten 提供 Web Runtime Host 与 Creator Web；
   这次热潮从外部印证了浏览器既是开发入口也是试用入口，不需要据此改变现有方向。
2. **多固件切换不等于 LMDJ 要开放第三方组装。** OPEN-1 的“多固件”是整机级切换；LMDJ 的产品专属
   连接属于 Product Assembly。本文不据此提出改变 Provider 组装方式的建议。
3. **嵌入式内存门槛的参照点。** [Cardputer Adv 可行性分析](./2026-09-03-cardputer-adv-feasibility-analysis.md)
   认为，若要 64 Pad 长样本、完整 Master FX 或设备端创作，需要至少 8 MiB PSRAM 的 ESP32-S3 板卡或
   更高内存的平台。OPEN-1 采用的 Daisy Seed 级平台（64 MB）[S02] 越过了这条线。若 LMDJ 将来重启
   嵌入式 spike，它可以作为对照候选之一；这是研究建议，不是选型。
4. **分层开源的许可证教训。** [开源就绪度评估](./2026-09-02-lmdj-open-source-readiness-assessment.md)
   建议从 `contracts/` 开始分层、选择性开源。FM1 Open 的争议 [S07][S06] 说明：一旦开放 SDK 而核心
   保持闭源，链接例外、第三方 DSP（如 Plaits、Dexed/MSFA）的许可义务和署名，都必须在发布前理清，
   否则社区会先讨论许可证，而不是讨论产品。

## 6. 后续观察信号

以下任一项发生，才值得重新评估 OPEN-1：

- 公开浏览器模拟器或 SDK，并声明许可证；
- 第一块定制电路板做出来，并公开音频与输入实测；
- 规格冻结，并按无键盘设计重新给出零件成本与价格；
- 发起众筹或公布制造伙伴；
- 至少一个首发固件在 STM32H750 上跑起来，而不只是浏览器模拟。

## 7. 证据边界与未解决问题

- 没有接触实物或原型，没有构建或运行任何相关源码，也没有刷写 FM-1。
- MATRIXSYNTH 的 OPEN-1 与 FM1 Open V14 两篇报道在访问日被重定向到 Google 验证页，未读取正文，
  因此不作为本文来源。
- FM-1 的芯片、价格、发布时间来自媒体与社区索引，未见 M-VAVE 官方规格页。
- 社区固件数量是两个不同时间点、不同统计口径的快照（[S07] 的 63 个项目与 [S08] 的可见 107 条），
  不能直接比较。
- OPEN-1 页面属于作者自述，访问日之后可能继续大幅修改；本文第 3 节是访问日快照。

## 8. 来源登记

下表访问日均为 **2026-10-27**。网页是当日快照；短引文用于辨认原始主张，不能保证网页以后保持不变。

| 编号 | 资料与定位 | 关键原文或证据用途 |
| --- | --- | --- |
| S01 | [Synthtopia：OPEN-1 Promises To Be One Synth For Every Firmware][S01]，2026-10-23 | “just a design concept”；10-17 概念版规格；FM-1 240 MHz、约 432 KB |
| S02 | [RedtailWorks：OPEN-1 项目页][S02]，作者自述 | “Not a product yet”；“a target, not a promise”；v0.4 beta 规格、价格、build log、“not affiliated with or endorsed by M-VAVE” |
| S03 | [RedtailWorks：Five firmwares for the M-VAVE FM-1][S03] | 五个固件及其状态；“All free and open source” |
| S04 | [GitHub：RustyPawz/fm1-HYP1][S04] | GPL-3.0-only；fork 自 `charlesvestal/fm1-amb`；Felucca 平台层；浏览器模拟器构建脚本 |
| S05 | [Synthtopia：M-VAVE Officially Opens FM-1 Firmware To Developers][S05]，2026-10-20 | “an official open-source firmware project”；Workbench、SDK、V14、官方固件功能 |
| S06 | [Synth Anatomy：M-VAVE FM-1 Open][S06]，2026-10 | “backdoor” 与 AI；GPLv3 加 SDK 链接例外；归属批评；读者关于刷机与降级的评论 |
| S07 | [The Synth Source：FM1 Open][S07] | 时间线；63 个社区固件项目；许可分层；工具链；GPL 投诉；Felucca 维护变化 |
| S08 | [GitHub：aroum/fm1-custom-fw][S08]，社区固件索引 | JieLi AC791N、27 键、240×240；刷写途径；固件分系统计；AI 参与的间接迹象 |

## Version Management

Version impact: none

Reason: 本 Task 仅新增外部产品与生态研究文档，不更改 Product Build、Core Module、Provider、Host、
Contract、Assembly 或 Channel 身份，也不选择发布候选。

## Documentation Impact

Documentation impact: none

Reason: 本文位于 `docs/research/`，记录外部资料与研究判断；没有更改 Architecture Portal 页面、源图、
工具或现有产品行为，不触发 Product Build 快照。

[S01]: https://www.synthtopia.com/content/2026/10/23/open-1-promises-to-be-one-synth-for-every-firmware/
[S02]: https://rustypawz.github.io/fm1-HYP1/open1/
[S03]: https://rustypawz.github.io/fm1-HYP1/
[S04]: https://github.com/RustyPawz/fm1-HYP1
[S05]: https://www.synthtopia.com/content/2026/10/20/m-vave-officially-opens-fm-1-firmware-to-developers-with-new-workbench-sdk/
[S06]: https://synthanatomy.com/2026/10/m-vave-fm-1-open-the-green-light-for-custom-firmware-and-community-hacks.html
[S07]: https://thesynthsource.com/fm1-open/
[S08]: https://github.com/aroum/fm1-custom-fw
