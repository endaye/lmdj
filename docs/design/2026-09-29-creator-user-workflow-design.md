# Creator 用户操作流程：现状与目标对照（内部版）

日期：2026-09-29

状态：目标流程已由产品负责人在 2026-09-29 的 workflow 评审中确认；本文**不实施**任何产品代码、Contract、Facade 或 Host 接口。已确认的结论同时记录在
[决策文件](../prd/decisions/2026-09-29-creator-user-workflow-baseline.md)；面向用户的写法见
[用户版](2026-09-29-creator-user-workflow-guide.md)。

关联：[UI 迭代 Umbrella #1207](https://github.com/endaye/lmdj/issues/1207)、
[U0 功能映射 #1214](https://github.com/endaye/lmdj/issues/1214)、
[硬件布局参考](2026-09-11-lmdj-hardware-ui-layout-reference.md)、
[U0 source-backed 设计稿](../superpowers/specs/2026-09-11-creator-hardware-migration-design.md)。

## 0. 证据口径

- **现状**一栏来自对 `apps/creator-web` 及其 Host 的只读代码盘点，基线 revision
  `37eb7394`；与本文所在分支的基线 `f84c8ee6` 相比，`apps/creator-web/src`、
  `packages/web-runtime-platform/web`、`packages/project-io/src`、
  `packages/authoring-domain` 无变更。现状是代码阅读结论，**没有**逐项在真实浏览器里验收；未能确认的点单列在 §14。
- **Koala** 一栏引用 Koala Sampler 官方手册移动版
  （`https://manual.koalasampler.com/mobile/`，第 4、5、6、7 章，2026-09-29 访问）。手册只是**参照**，不是本仓库的决策；手册未写明的行为在正文里标为"手册未写明"。
- **目标**一栏是本次评审确认的结论。实现时仍需各自的 Task、测试与验收，不能因本文合并而宣称已实现。

## 1. 原则

1. **先对齐 Koala，再做 LMDJ 自己的优化。** 某个交互或功能没定时，默认按 Koala 的做法；功能全部到位之后，再针对 LMDJ 用户做体验优化。
2. **LMDJ 与 Koala 的差异必须显式列出。** 本文涉及的差异：多出的 Project 标签（进出口 + 工程库 + 内容包）、System 次级入口、账号与云同步、可安装 Provider、资产服务器下载的默认 Sound Set。
3. **架构不变式不因对齐 Koala 而放松。** Provider 的 closed world、Project Truth 与 Runtime Snapshot 的分工、Pattern 事件只引用 Pad Slot、失败属于 Attempt 状态而非 Project Truth，都照常适用；与 Koala 做法冲突时标出冲突，而不是悄悄照搬。
4. 目标用户接近 Koala 用户但更偏新手（[重设计 §3.1](2026-07-30-lmdj-playable-beat-instrument-core-redesign.md)）；约 3 分钟内得到可演奏 Pad 并亲手录出第一个 Beat 的承诺不变。首版仍不做新手引导。

## 2. 信息架构与导航

### 2.1 一级页面

页面键保持四个：**Project │ Sample │ Sequence │ Perform**（与硬件布局参考一致）。切换页面**不停止** transport（现状已如此：`app.tsx:1390-1403`）。

| 页面 | 关于什么 | 目标内容 |
| --- | --- | --- |
| Project | 这首作品 | 工程库（本机 + 云端）、当前工程卡片（名称、同步状态、最近修改）、**进**（导入 `.lmdj` / 他人分享的工程、安装内容包）、**出**（导出与分享，见 §8） |
| Sample | 创作：声音 | 选中 Pad 的编辑（对齐 Koala Sample Editor，见 §5），含 Tools：Chop、Split Stems |
| Sequence | 创作：节奏 | 全局 transport、叠录、网格编辑、Resample Loop（见 §6） |
| Perform | 创作：演奏 | FX 随时可用、HOLD、Pattern 切换、演奏录音（见 §7） |

### 2.2 System 次级入口

System **不占页面键**，是一个次级入口（形态待 UI 设计），承载与作品无关、使用频率低的内容：

- 账号：登录 / 登出、云同步开关与状态；
- 设置：通用设置、错误上报开关（见 §9.2）；
- 设备：MIDI 开关与设备选择、音频输入设备；
- Provider：选择与安装（见 §10.3）；
- 诊断：版本信息、手动导出诊断报告（备用）。

依据：Koala 把设置、帮助、工程管理都放在主菜单，不占一级页面（手册第 7 章）；硬件布局只有 4 个页面键，另外 4 个是 Bank A–D。

MIDI 例外：设置放在 System，但连接状态在上屏常驻指示，演奏时不必离开当前页。

现有 System 按钮行（Activate audio、Enable MIDI、Sound Sets、Slice）按本节拆分：Activate audio 被 §3 的"首次触碰激活"取代；Enable MIDI 进 System；Sound Sets 进 Project 的"进"；Slice 并入 Sample → Tools（§5.2）。

### 2.3 社区

Koala 没有社区。首版只在 Project → 出 提供"分享"操作；社区是否独立成页面，等社区功能真正立项时再决定。

### 2.4 数据归属规则

**放在哪个页面 ≠ 属于哪份数据。**

- 属于**工程**（进入 Project Truth、随工程同步）：Pad、Pattern、Sample 参数、tempo / swing / quantize、已安装进 Bank 的内容。
- 属于**账号或设备**（不进 Project Truth）：登录状态、设置、MIDI 与音频设备、Provider 选择、"我装过哪些内容包"的素材库、错误上报开关。

内容包在界面上属于 Project，但"素材库里有哪些包"是账号级，"把某个包装进本工程的 Bank B"是工程级操作。这与既有不变式"Provider selection belongs to Workspace/Host settings, not Project Truth"一致。

## 3. 首次使用与启动

| 步骤 | 现状 | Koala | 目标 |
| --- | --- | --- | --- |
| 打开 | 停在 Project 页，提示 "Import a .lmdj bundle to begin"（`project_surface.tsx:118-124`）；**不能新建工程**（`project_overview.tsx:37-39`） | 启动时自动打开上次的歌（7.2） | 首次：自动新建工程并停在 **Sample** 页；之后：自动回到上次工程 |
| 记住上次工程 | 无；刷新后要重新 "Open local"（`creator_state.ts:165-170`） | 自动 | 记住并自动打开 |
| 激活音频 | 必须先打开工程，再点 "Activate audio"（`app.tsx:1481-1489`） | 首次触摸即可 | **第一次点 Pad、按键或开始录音时顺带激活**，不设单独按钮 |
| 默认声音 | 无 | 有示例内容 | **预装默认 Sound Set**（§3.1） |
| 保存 | 无 New / Save As | Save / Save As；iOS 持续后台保存（7.3） | **自动保存**；"另存为" = 复制工程 |

### 3.1 默认 Sound Set

- 默认 Set **不随程序打包**，放在独立的资产服务器上；打开 Creator 时（网页版打开时必然在线）开始下载，**不需要等音频激活**。
- 装进 **Bank A**；B / C / D 留空，给用户自己的声音。
- **每个 Pad 独立下载、独立显示进度**，下完一个能用一个。
- 每个 Pad 下载完成的那一刻才原子地写进工程；下载中的状态只是界面上的临时状态，属于 Attempt，不进 Project Truth。
- 资源按内容哈希寻址，下载后校验；写入后存进本机，之后打开该工程**不再下载、离线可用**。
- 首次预装跳过现有 Sound Set 安装流程里的"预览映射 → 保留 / 替换 → 安装 N/16"对话框。
- 默认 Set 必须是 LMDJ 有权随产品分发的素材（见 [Sound Set 版权与映射决策](../prd/decisions/2026-09-06-sound-set-rights-and-mapping.md)）。
- 现状：Sound Set 目录与安装流程已存在（`soundset_surface.tsx:245-490`），但默认页面里的目录服务器配置被注释掉（`apps/creator-web/index.html:22-23`）。

## 4. Pad 状态与手势

所有触发模式都是**按下时开始出声**，区别只在何时停：`one_shot` 播到结尾；`gate` 按住播放、松开停止；`loop_gate` 按住循环、松开停止；`loop_toggle` 按一下开始循环、再按一下停止（`packages/authoring-domain/include/lmdj/domain/project.hpp:44-49`）。没有"松开才出声"的模式。

| Pad 状态 | 点 / 按住 | 删除 | 编辑 |
| --- | --- | --- | --- |
| 空 | 点：导入文件；**按住：录音**（§4.1） | — | — |
| 下载中 / 处理中 | 不出声，只显示进度 | ✅ 取消下载或处理，Pad 变空 | 完成后可用 |
| 下载失败 / 处理失败 | 显示重试标记；不出声 | ✅ Pad 变空 | — |
| 有声音 | 按触发模式演奏 | ✅ 直接删、可撤销；**保留 Pattern 事件** | ✅ 进入 Sample 编辑 |

- "按住录音"**只对真正空的 Pad 生效**。下载中的 Pad 不算空；想在它的位置录音，先删除。已有声音的 Pad 要覆盖录音，走 Sample 页里的 Record 入口。
- **删除**与**编辑**是触控屏上针对当前选中 Pad 的两个按钮，不做 Pad 上的删除手势（Pad 手势全部用于演奏）。
- 删除后 Pattern 事件保留：事件引用 Pad 位置而不是 Asset，给该 Pad 放新声音后，原节奏直接用新声音播放（"换声音不换节奏"）。
- 被删声音的 Asset 只是不再被 Pad 引用；物理清理是后台工作，规则与云端版本历史一并确定（§11）。
- 现状：**没有 Pad 删除能力**。领域命令只有 `AssignPad`、`UpdatePadPlayback`、`ResetPadPlayback`（`packages/authoring-domain/include/lmdj/domain/commands.hpp:25-43`），Host 只有 `pad.assign`；界面只有 Replace Sample 与 Reset Pad to Defaults（`sample_controls.tsx:167-254`）。删除是新增的核心能力，涉及领域命令、Facade 与 Web Host 接口。
- Koala：点一下确认删除，或按住 DELETE 连点多个 Pad（手册 4.x Pad Management）。

### 4.1 按住空 Pad 录音

- 录音来源可选：**麦克风**或**当前主输出（重采样）**；在录音界面切换，记住上次选择。对应 Koala 把重采样当作录音来源之一（手册 4.1）。
- 第一次按住只触发浏览器的麦克风授权，提示再按住一次开始录音；授权后即按即录。
- **松开即写入该 Pad**，自动去掉开头静音，不弹窗；精修去 Sample 编辑，反悔用撤销。
- 沿用现状的单次 60 秒上限（`capture/capture_buffer.ts:2`）与"完全静音不写入"规则（`capture_panel.tsx:27-32`）。
- Sequence 正在播放时按住空 Pad，录的是**音频**，不是 Pattern 事件；它与 Sequence 的 Record（录 Pad 触发）是两件事，界面上必须能明显区分。
- 现状：录音必须经 "Record Sample" 打开弹窗，流程是 Record → Stop → Crop → Commit / Discard（`capture_panel.tsx:723-770`）。

## 5. Sample

### 5.1 编辑能力：以 Koala Sample Editor 为基准

| 能力 | Koala（手册章节） | 现状 |
| --- | --- | --- |
| 裁剪 / 裁切到选区 | ✅ 4.7 | ✅ `waveform_editor.tsx:540-609` |
| One-shot / Hold | ✅ 4.7 | ✅ |
| Loop（普通 / ping-pong / 循环点交叉淡化） | ✅ 4.7 | 仅普通 Loop |
| 反向 | ✅ 4.7 | ❌ |
| 音量 / 音高 / 声像 | ✅ Pad Management | 仅音量（−60 至 +6 dB） |
| Attack / Release / Tone | ✅ | ❌ |
| 三段参数 EQ | ✅ 4.8 | ❌ |
| Choke 组（6 组） | ✅ | ❌ |
| 复制 / 合并 / 交换 Pad | ✅ 拖拽 | ❌ |
| 删除 Pad | ✅ | ❌（§4） |
| 录音输入效果（8 种） | ✅ 4.1 | ❌ |
| 静音 | Mute / Solo 4.12 | Mute ✅（`sample_controls.tsx`） |
| 时间伸缩 | ✅ 4.11（SAMURAI 付费扩展） | ❌（开放问题 [#347](https://github.com/endaye/lmdj/issues/347)） |
| 导出单个声音 | ✅ 7.6 | ❌ |

"编辑"按钮的目标能力等于 Koala 的 Sample Edit；表中缺口逐项开 Issue 补齐（§12）。

### 5.2 Tools：Chop 与 Split Stems

- Koala：Sample Editor → **TOOLS** 下拉 → AUTO-CHOP（4.9，SAMURAI 付费）/ SPLIT STEMS（4.10，最多 4 轨：鼓、人声、贝斯、其他；本机运行，需单独开启以下载约 150 MB 模型；仅独立模式可用）。手册未写明分轨结果放到哪些 Pad。
- 目标：
  - Sample 编辑里加 **Tools**，放 Chop（对应 Stage 12A Slice）与 Split Stems（对应 Stage 12B Stem）。
  - **去掉单独的 Slice 模式**（现状：System 按钮进入，`app.tsx:1516-1525`，流程为选 Provider → 授权 → 选来源 → 分析 → 映射 → 采纳，`candidate_surface.tsx:82-266`）。
  - 导入整首歌 = 普通的导入 Pad，然后对该 Pad 执行 Tools；Project 不设单独的"导入歌曲"入口。
  - 结果**依次放到当前 Bank 的空 Pad**，不够时放到下一个有空位的 Bank；原 Pad 默认保留（对应 Koala 的 KEEP ORIGINAL）；空位不足先提示，不自动覆盖。
  - 运行位置：Chop 在本机；Split Stems 支持本机与云端，由 System 里的 Provider 选择决定；本机模型从资产服务器首次下载。具体取决于 Stage 12B 评测（[#1171](https://github.com/endaye/lmdj/issues/1171)、[#1172](https://github.com/endaye/lmdj/issues/1172)）。
  - 处理在后台进行，用户可继续演奏；目标 Pad 显示进度，行为同 §4 的"处理中"，删除即取消。

## 6. Sequence

| 能力 | Koala（手册第 5 章） | 现状 | 目标 |
| --- | --- | --- | --- |
| 播放 / 录音 / 叠录 | ✅ 5.1 | ✅ 默认开启全局 transport（`main.tsx:103`） | 保持 |
| Pattern 数量 / 最大长度 | 32 个 / 64 小节 | 16 个 / 1-2-4-8 小节 | 维持既有收窄决策（[Sequence 录音语义设计](2026-08-22-sequence-recording-semantics-design.md) §3），是否扩展另议 |
| Tempo / Swing / Quantize | 拖动、tap、加减 5.3 | ✅ 直接调节：拖动预览、松手提交一次，±1 步进与 Tap Tempo（#1672，2026-10-02） | 对齐 |
| 节拍器 | ✅ | ✅ 设备级开关，播放/录音中可闻，不进任何录制（#1672，2026-10-02） | 对齐 |
| **网格编辑**（增删音符、拉长、多选） | ✅ 5.7 | ❌（`sequence_overview.tsx:70-72`） | **高优先级** |
| **撤销** / 清空 | ✅ | ❌ | **高优先级**（§12 前置能力） |
| 拖拽复制 / 合并 Pattern | ✅ | 部分（Perform 槽位 Assign / Clear / Move） | 对齐 |
| Resample Loop（渲染当前 Sequence 为干净循环放到下一个空 Pad） | ✅ 7.5 | ❌ | 放在 Sequence 页 |

- 刷新或失败后的重试现状：对 `HOST_STATE_INVALID` / `HOST_TIMEOUT` / `ABORTED` 以同一 command 重发最多 12 次（`app.tsx:1033-1098`）。错误以原始代码显示（`sequence_touch_workspace.tsx:168-173`），目标改为人话（§9）。
- 方向键、±键与四个旋钮现状全部未分配（`physical_controls.tsx:94-106,147-152`），映射由 U0/U1 设计另定。

## 7. Perform

| 能力 | Koala（手册第 6 章） | 现状 | 目标 |
| --- | --- | --- | --- |
| FX 数量 | 16 | 8（Filter、Delay、Reverb、Stutter、Gate、Reverse、Crush、Cutter，`perform_state.ts:27-30`） | 数量是否扩展另议 |
| **FX 可用时机** | 随时 | **只在演奏录音进行中**（`perform_surface.tsx:192,210,231,236`） | **随时可用**；录音与 FX 是两个独立开关 |
| 施加方式 | 按下生效、松开取消，多指叠加 | Filter / Delay 为推子，其余在 FX / MORE 下 | 对齐 Koala |
| HOLD | ✅ | ✅ | 保持 |
| Pattern 切换 | ✅（SEQ SNAP：OFF / BEAT / BAR / SEQ END） | ✅ 下一小节生效（BAR） | 保持；其余档位另议 |
| 带 FX 重采样到 Pad | ✅ | 回放已存演奏后手输起止帧号（`perform_surface.tsx:82-157`） | 按住空 Pad、来源选"主输出"（§4.1） |
| 录整首歌 | 7.4 | ✅ 演奏录音 + 导出 WAV（上限约 30 分钟） | 保持在 Perform |

FX 只在录音中可用可能有技术原因（例如 FX 链挂在演奏录音的 controller 上）；实现 Task 需先查明再改。

## 8. 导出与分享（Project → 出）

以 Koala 主菜单（手册第 7 章）为准：

| 能力 | Koala | 现状 | 目标位置 |
| --- | --- | --- | --- |
| 新建 / 打开 / 另存为 | 7.1–7.3 | 仅导入 `.lmdj` 与打开本机工程 | Project → 工程库（自动保存，另存为 = 复制） |
| 导出 Stems（每 Pad 一个 WAV，或混为一个立体声） | 7.6 / 7.7 | ❌ | Project → 出 |
| **Ableton Drum Rack（.adg）与 Live Set** | 7.6 / 7.7 | ❌ | Project → 出（PRD 首要目标，高优先级） |
| 分享工程文件 | `.koala` | ❌（只能导入） | 导出 `.lmdj`；登录后改为云分享（§10） |
| 从视频导入音频到空 Pad | 7.9 | ❌ | Pad 导入 |

现状能下载的只有 Perform 录音 WAV（`perform_state.ts:816-827`）与诊断 JSON（`app.tsx:959-967`）。所有导出只从 Project Truth 派生，与既有 Export 决策一致。

## 9. 出错与恢复

### 9.1 场景

| 场景 | 现状 | 目标 |
| --- | --- | --- |
| 窗口失焦（页面仍可见） | 视为中断：清除按住输入、退出 Perform、音频挂起，需重新激活（`runtime_session.mjs:2185-2254`、`app.tsx:495-513`） | **不中断**。若某浏览器确有限制，只在该浏览器中断；实现前先查明当初把失焦视为中断的原因 |
| 切走标签页 / 最小化 / 锁屏 | 同上；演奏录音与麦克风录音停止 | 播放停止并记住位置；回来后**第一次触碰自动恢复音频** |
| 录音中被中断 / 录音设备拔出 | 麦克风录音停止并提示；Sequence 录音进入待恢复列表 | **保留已录部分**：叠录保留到中断时刻，麦克风录音按已录长度写入，均可撤销 |
| 输出设备变化 | 未确认 | 自动切到新的默认输出继续播放 |
| 同一工程开第二个标签页 | `PROJECT_BUSY`（`error_panel.tsx:35-97`） | 提示已在别处打开，提供"在这里继续"接管；原标签页变为只读或提示已被接管 |
| 崩溃 / 关闭时正在录音 | 重开后 Sequence 可恢复列表（恢复到原 / 其他 Pattern 或丢弃，`sequence_touch_workspace.tsx:133-166`） | 重开时主动问一次是否保留，默认保留；恢复到其他 Pattern 收进"更多" |
| 音频引擎出错 | 自动替换一次，之后 "Retry runtime"（`runtime_context.tsx:157-174`） | 保留自动重启一次；再失败时说人话、给重试，并明确工程数据不受影响 |
| 存储空间满 | "why / remedy" 配额信息 | 用户语言 + 直接给处理入口 |
| 断网（云端上线后） | — | 离线标记，照常创作，恢复后自动同步；只有云功能不可用 |
| 错误信息 | 原始错误码 | 界面说人话，错误码进入诊断 |

相关 Issue：[#741](https://github.com/endaye/lmdj/issues/741)、[#1440](https://github.com/endaye/lmdj/issues/1440)、[#625](https://github.com/endaye/lmdj/issues/625)。本节规则确定后，这些 Issue 的验收标准需要按新规则复核。

### 9.2 错误上报

- **自动上报**与**用户提示**是两个独立的系统功能：上报把错误日志自动上传到错误服务器并在服务端分类；提示在本地酌情显示给用户，内容不同。
- 手动"导出诊断报告"降为备用手段。
- 自动上传涉及隐私：System 设置里提供开关，首次使用时告知；日志不包含音频与工程内容，只含错误与环境信息。具体隐私边界待定（§13）。

## 10. 账号、云同步与协作

### 10.1 登录

- **不登录也能完整创作**：Sample / Sequence / Perform、本机自动保存、导出到 DAW 全部可用。
- 云功能受限：云同步、跨设备、分享链接、协作、云端 Provider 需登录（云端 Provider 对未登录用户不可用或限量）。
- 未登录时的工程，登录后可**认领**到账号下并自动上云。
- 受限功能必须明确显示"需登录"，不能静默消失（与 working-prd §3、重设计 §24.5 的"不静默降级"一致）。

### 10.2 离线

**离线必须可用**：首次打开需要联网（网页加载与默认 Sound Set 下载）；之后工程、已下载的声音与本机 Provider 在离线时照常工作；需要网络的功能明确显示不可用。

### 10.3 可安装 Provider

"插件"指**可安装的代码**与 Provider 选择，放在 System。它与现有 closed world（Provider 链接期装配、不做运行时动态加载）冲突；可行方向是运行在隔离的进程外 Provider Host（`workers/` 已为此预留）或服务端，通过既有 Provider Contract 通信，Core 仍保持 closed world。发布、签名、审核与选择的存储层级需独立决策（§13）。

### 10.4 协作分阶段

| 阶段 | 内容 | 对应 |
| --- | --- | --- |
| 1（对齐） | 单人；导出 / 分享 `.lmdj`，对方导入得到独立副本 | Koala 分享 `.koala` |
| 2（登录后） | 同一人多设备自动同步；分享链接得到自己的副本（fork） | BandLab fork |
| 3（以后） | 多人协作：先异步合并，实时同屏按需 | — |

用户可见行为：

1. 冲突：参数类（Pad 参数、tempo）以最后一次修改为准、不打扰用户，同时保留**版本历史**可回退；Pattern 事件**两边都保留**（按事件合并）。
2. 长时间离线后联网：自动合并，不弹审阅；不满意用版本历史找回。
3. 撤销：只撤销自己在本设备上的操作。
4. 演奏中远端改了 tempo 或 Pattern：**下一小节生效**，沿用 Koala SEQ SNAP = BAR 的思路与现有小节边界发布规则。Koala 无协作，没有直接对应。此条属于并发语义，需在协作 Contract 的决策记录中正式确定，实现 Task 不得自行定。

工程格式从阶段 1 起按"可同步"设计。调研材料见
[工程同步与协作格式调研](../research/2026-09-29-project-sync-collaboration-research.md)；格式本身是开放问题（§13）。

## 11. 工程文件与声音资源分离

- 现状：`.lmdj` 包打包整个工程目录，即 Project Truth 与 `assets/<sha256>.wav`；每个条目带 SHA-256 校验；单条目 ≤ 64 MiB、总计 ≤ 512 MiB、≤ 4096 条目（`packages/project-io/src/project_bundle_transfer.cpp:32-34,330-360`、`packages/project-io/src/project_store.cpp:309`）。音频**已按内容哈希命名**。
- 目标：工程文件只含 Project Truth 并以哈希引用音频；声音资源单独存放，本机 OPFS 作为缓存，云端对象存储作为权威副本，同一声音只存一份；`.lmdj` 降级为导出 / 归档格式，离线分享或备份时把引用到的音频一并打包。
- 这是 Contract 级改动（`lmdj.project.v5`、`lmdj.project-bundle.v1`），需走决策记录；Asset 的清理规则（无工程或历史版本引用时才删除）与版本历史保留期一并确定。

## 12. 前置能力与缺口清单（待开 Issue）

**前置能力**（多条目标流程依赖，优先）：

1. 撤销 / 重做（删除 Pad、按住录音写入、网格编辑都依赖）。现状无任何 Undo 实现，且决策 S8-D4 明确 Stage 8 不引入通用 Undo/Redo；本次评审要求把它提前。撤销上线前，删除用确认框过渡。
2. 新建工程、记住并自动打开上次工程、自动保存。
3. Pad 删除（领域命令 + Facade + Host）。

**流程缺口**（按页面）：

- 首次使用：首次触碰激活音频；默认 Sound Set 资产服务器 + 逐 Pad 下载与进度 + 原子写入。
- Pad：按住空 Pad 录音（含来源切换、首次授权、松开即写入、去开头静音）。
- Sample：§5.1 表中全部 ❌ 项；Tools（Chop、Split Stems）；移除 Slice 模式。
- Sequence：网格编辑、撤销 / 清空、节拍器、直接调节 tempo / swing、拖拽复制 / 合并 Pattern、Resample Loop。
- Perform：FX 随时可用、按下即生效的 FX 交互、重采样改为按住空 Pad。
- 导出：Stems、Ableton Drum Rack / Live Set、导出 `.lmdj`、导出单个声音、从视频导入。
- 出错与恢复：§9.1 表中全部目标行；错误信息人话化；错误自动上报。
- 导航：System 次级入口；上屏 MIDI 状态；现有 System 按钮行按 §2.2 拆分。

开 Issue 前先与已有 Issue 对照，避免重复（#1207、#1214、#1221、#773、#799、#341、#961、#1230、#1163、#1164 等）。

## 13. 待开的 Question Issue

按 [open-questions 约定](../prd/open-questions.md)，以下未决问题应通过 GitHub Question form 建 Issue：

1. 工程同步与协作格式（按属性同步 + 草稿层、`.lmdj` 降级、协作 Contract 版本；调研见 §10.4 链接）。
2. 可安装 Provider 的发布、签名、审核、运行位置与选择存储层级（§10.3）。
3. 撤销 / 重做系统的范围与语义（本机 vs 跨设备、与协作"只撤销自己"的关系），及其对 S8-D4 的替代。
4. 错误自动上报的隐私边界与同意方式（§9.2）。
5. 演奏中远端修改的生效时机（§10.4 第 4 条，并发语义）。

## 14. 与现有文档的出入与未确认项

与现状不符、实施时需更正的文档说法：

- [UI 迁移计划](../plans/2026-09-11-creator-ui-migration.md) 写"opt-in 新壳、默认保留旧布局"；现状硬件控制台是唯一布局。
- U0 设计稿 §3 提到 Mode Rail，G02 称进入 Sample 会停止 Sequence 录音，G05 称 Slice 在 "More modes"；现状分别是物理键 + System 按钮、切页不停 transport、Slice 是 System 按钮。
- U0 设计稿 §5 / §7 描述 `beginSequence/stopSequence` 与"公开面缺 Pattern 播放状态"；现状已改为全局 transport intent。
- [working-prd](../prd/working-prd.md) §3 称 Creator Export ZIP 已实现、以 Ableton 为目标；现状均不存在（该文件的 2026-08-26 注记已标为历史）。
- Sound Set 界面注释 "This surface plays nothing"、Project 页文案 "Perform mode arrives in Stage 10" 已过期。

未能从代码确认、实现前需验证的点：部署构建是否注入 Sound Set Catalog 端点；启动后是否总会先到达 `audio-suspended`；Perform 采集配置在真实浏览器上的条件；从 stopped 直接 Record、循环边界时序与 owner-lost 后恢复的实际行为（仅来自设计文档与提交信息）。

## Version Management

Version impact: none
Reason: 本文只记录目标用户流程与现状对照，不改变 Product Build、Core Module、Provider、Contract 或 Channel 身份。

## Documentation Impact

Documentation impact: none
Reason: 本文是 `docs/design/` 下的设计记录，不修改 Architecture Portal 页面、图或投影身份。
