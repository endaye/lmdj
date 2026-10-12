# Creator Desktop Final：后续功能、缺陷修复与验收收尾

## Outcome and authority

逐项完成 Creator Desktop Final 后续范围：修复已确认缺陷，确认尚未决定的产品
行为并实现，验收四页交互，结算版本，再清理有完整保留证明的本地资源。
用户于 2026-10-09 授权执行本计划的 Goal，包括 Task 的 commit、push、PR、
当前 head 评审和 squash merge，以及证明安全后的相关本地工作区/分支清理。
本计划不授权 tag、Release、部署、Channel promotion、远端分支或云主机资源清理。

[原计划](2026-10-06-creator-desktop-final-ui.md) T1–T11（含 T1b、T5a）已完成。
用户明确确认以该计划为准完成原目标；本 Goal 不重做原任务。历史 Claude
会话的额度耗尽和 Goal 结束检查不构成产品未交付的证据。

产品决定优先于 Figma。Desktop Final 是桌面布局/视觉依据，不能凭图中的控件
推导运行时能力或持久化语义。Mobile/iPad 设计扩展不在本计划中；现有布局的
真实 Safari/iPad 输入与设备验收仍须保留适用证据。

## Facts and premise dispositions

初始调查绑定 `origin/main` = `0d7c178b2bc4d277ff34424bb5f42c78aee7ef9d`。
在每个 Task 开始、提交前和最终合并检查时刷新 main 及其相关继任交付。

| 前提 | 当前证据与处置 |
| --- | --- |
| 原 UI Task 未交付 | 已反证：相关实现 PR 全部 merged，最后 #1900 → `1f20e8f63`、#1901 → `0d7c178b2`；不重复实现。 |
| #1905 连续提交刷新丢失 | 已交付：#1907 → `0b333d3bd5c1a935a6c481551fb4d885abc78dc8`，Issue closed。旧代码从滞后 render ref 取刷新 revision，现由 grid/structure/colour 成功路径传入已提交 revision；回归测试检查最终画面，不重复修复。 |
| #1868 导入偶发停在 0 B | Issue open；尚未建立原因。R2 是条件调查，只有验收受阻时才启用，不把一次重跑通过当作修复。 |
| #1873 测试问题仍未修 | 已反证：Issue closed，相关修复已合并；本 Goal 不重做。 |
| #1822 其余控件映射已有决定 | 全页旋钮及三页普通方向映射已批准；I1a Sequence 导航已交付，新增三页导航待 K2。SHIFT + ←/→ 撤销／重做、SHIFT + ENC1–3 细调保持，SHIFT + ↑/↓ 不分配；其他 SHIFT 提案仍待决，Issue open。 |
| 400 ms 规则已正式确认 | 本计划初始调查时尚未确认；owner 现已批准立即预览、400 ms 合并 authoring 保存及明确的取消边界，见 I1b/I1c。 |
| D01/D03/D04 图示能力均可直接接线 | 部分反证：下文 C0 核实了可复用的复制与 Sample 编辑；新的 D04 复查确认 MASTER 可复用 ENC4 已交付监听 producer，独立滤波参数、live Mute/Solo 及作品电平投影仍需 producer 工作。D01 自动保存/复制语义已有决定，不重新设计。 |
| 合并/自动化可代替人工验收 | 不成立。原验收台账保留真实输入、听感、辅助技术和生命周期缺口；A1/A2 分开记录。 |

开放 PR #1904 是 audition golden 计划；开始涉及 audition 的 Task 时重新核对其
交付与文件范围。原 Claude 主会话没有进行中的实现任务；监视器不取得新 Task
工作区所有权。新 Task 使用自己的隔离工作区，不共享旧构建目录。

## Progress and order

| ID | 工作 | 当前状态 | 依赖/完成条件 |
| --- | --- | --- | --- |
| P0 | 本后续计划 | 已合并 | #1906 → `cd5fbf9290fba820139bfdc9d41b9166a7fe333b`；独立接管评审及修订已验证。 |
| R1 | #1905 连续 authoring 提交刷新 | 已合并 | #1907 → `0b333d3bd5c1a935a6c481551fb4d885abc78dc8`；red/green、完整 Creator lane、Portal 与当前头独立评审通过；不代表 A2 人工验收。 |
| C0 | D2–D5 当前能力及决定边界调查 | 调查已记录 | 绑定下文 inspected revision；只更新本计划，不批准产品提案或实现 I Task。 |
| R2 | #1868 导入稳定性条件调查 | 待调查（条件项） | 若阻碍本计划验收，保留 trace 并定位请求/读取/提交边界；证实原因后独立修复。 |
| D1 | #1822 统一原则及逐页映射 | 全页旋钮及三页普通方向映射已确认；导航待 K2 | 固定 ENC4 监听，ENC1–3 随页/组变化；Project 相邻／三列一行只选择，Sample 选 Pad／切子页，Perform 选 Pad／切三组保持效果；既有 SHIFT history／细调保持，SHIFT ↑/↓ 不分配。 |
| D2 | 400 ms 连续旋钮提交 | 已确认，包括 BPM 保持音乐位置；待完成实现验收 | Sample/BPM 立即预览、停转 400 ms 合并一次保存/Undo，脱离目标或取消时丢弃未提交预览；BPM 即时变速不重启 Pattern；Perform 保持效果并按 HOLD 离页释放。 |
| D3 | D01 Save / Save As / 未保存提示 | 已确认 DUPLICATE；现有入口符合 | owner 于 2026-10-10 选择 DUPLICATE；现有按钮复制新身份并打开副本，继续自动保存；整体 A1/A2 验收仍待完成。 |
| D4 | D03 audition/trim/browse/assign 与细调 | Assign 与精确数值编辑已批准；待独立实现 | 当前工程已有 Asset → 明确 A01–D16 目标，不移动来源、覆盖确认、取消不改 Truth；数值立即试听，Apply/Enter 一次保存/Undo，Esc/切目标取消。复用现有单位/边界与已批准旋钮细调，不改 touch slider 提交语义。 |
| D5 | D04 MASTER/滤波类型/Mute/Solo/电平 | 产品问答及共享尾音已批准；Contract 设计、实施与验收待完成 | MASTER 共用 ENC4；主效果 Cutoff/Delay/Reverb，新增 FILTER 类型/Cutoff/Resonance；独立滤波初始 OFF、LP/20 kHz/0%，Cutoff 20 Hz–20 kHz 对数、Resonance 0–100%，进组不改声，按实时 HOLD 规则并录制/重放全部参数。64 Pad live Mute/Solo 多个 Solo、Mute 优先，切 Bank/Pattern 保持、离 Perform/切工程清空，Performance 包含起点状态与后续变更。对应 Pad 当前／后续输入立即阻断，已进入共享 Delay/Reverb 的尾音自然衰减，其他 Pad 效果继续。Post-FX/Pre-ENC4 立体声 dBFS 峰值排除节拍器，L/R 独立、保持 1 秒、−60…0、静音 −∞、不可用明确显示。具体事件兼容、ramp 工程验证与 meter 投影仍由对应 Task 完成。 |
| I1–I5 | D1–D5 的对应实现 | I1b/I1c 已合并，原浏览器失败项及 BPM 可听预览仍未关闭；D4 待实现，D5 待设计和实现 | #1936 → `9b4d80c9e5ed965f5776c0321cf166d9d1f289ce` 交付 contextual consumer，不等于完整验收；每项追加精确 Task，独立实现和合并。 |
| K1 | #1960 四排键盘映射 | 已批准；实现与验收待独立 Task | 1234 → 13–16、QWER → 09–12、ASDF → 05–08、ZXCV → 01–04；Q 从 01 改为 09；MIDI note 36–51、Pad 身份与引用保持，见四排键盘决定。 |
| K2 | #1822 三页普通方向导航 | 已批准；实现与验收待独立 Task | 导航不触发 Pad、不写 Truth；上下文切换取消未提交预览。复用各页现有选择／子页状态，完整 Perform FILTER 导航依赖真实 producer／consumer。 |
| A1 | 四页自动化与视觉核对 | 待验收 | I1–I5、K1、K2 完成或 owner 明确取消相应范围；保留每个 journey 的 far-side assertion。 |
| A2 | 真实设备及人工验收 | 待验收 | 具体设备、来源、身份、步骤和结果；缺失 leg 保持未验收。 |
| V1 | 协调版本结算与 snapshot | 待实施 | 读取最终 manifests 和版本政策；独立 version Task、Portal snapshot 及合并后 provenance。 |
| C1 | 本地工作区/分支收尾 | 待调查 | 完整改动保留、干净（含 untracked）、未锁定且无人使用；逐个安全移除。 |

执行顺序为 P0 → R1，之后依次完成 D1/I1、D2/I2、D3/I3、D4/I4、D5/I5，
再 A1/A2、V1、C1；已批准的 K1 可在独立声明后并行准备，验收前完成。
人工等待时可推进不依赖该结果的调查或实施。R2 仅在
适用条件出现时加入。每个产品问题一次给出少量选项、建议及影响，收到明确
回答后记录 decision。决定不做可以完成该范围的处置；暂缓仍是未完成，除非
owner 明确同意移出本 Goal。

### 2026-10-10 — 已批准决定与 refreshed premises

本次决策记录检查 main：`e9dae833d1c609bb203030a62053dee39b9d8b61`。
owner 已明确批准：

- [BPM 旋钮即时变速保持当前音乐位置](../prd/decisions/2026-10-10-sequence-audible-tempo-preview.md)，
  继续播放并沿用停转 400 ms 一次保存／Undo。#1929 的
  [实施计划](2026-10-10-sequence-audible-tempo-preview.md) 不再把播放位置列为待决。
- [D03 Assign 与精确数值编辑](../prd/decisions/2026-10-10-sample-assign-and-numeric-editing.md)：
  已有工程 Asset 加明确目标、引用不移动、覆盖确认、取消不改 Truth；合法数值
  立即试听，Apply／Enter 一次保存／Undo，Esc／切目标取消。旋钮／touch slider
  保持各自已批准的提交方式。

未交付前提仍成立：Creator 的 `tempoPreview` 只改 readback，Web 完整操作
注册表尚无可逆 tempo preview；公开 Session 尚无 `assignPad`，Creator 尚无
已有 Asset 的完整 Assign 与通用精确数值输入 journey。已有 `project.inspect`
返回素材目录、`pad.assign` 持久化引用、Sample preview/update 与 Start/End
输入可复用。#1985／#1990 的实际范围是 Pattern switch 入口与特定 generation
fence，不能当作以上行为的交付。

#1984 的 Runtime 源文件仍与 BPM producer 重叠；先交付该前置，再开始独立
Runtime、Facade/Web、Creator Tasks。D03 已允许准备实施声明，开始实施前仍
按 Decision/implementation contract 刷新来源、声明精确文件及最低层验收。
四页 A1/A2、版本 V1 和未决定的 D04／方向键仍保持未完成。

**本次文档 Task declared files:** 两份上述新 decision、本计划、BPM 实施计划、
`docs/prd/questions/hardware-control-mapping.md`。按 canonical `decision-log.md`
和 `decisions/README.md` 使用独立 decision 文件，不回改历史决定或共享索引。
原 #1929 head `1d3e6a4e90540b7858196380b65492f33901f500` 在新隔离文档分支
中与 fresh main 普通合并；原 worktree 保留。PR 对 main 的差异仅为文档。

**Lowest-tier verification:** 声明路径与相对链接检查、staged new-file ownership
suite、`git diff --cached --check`、clean committed-head `docs_static`、PR body
lint 与 declaration/batch-only evidence check；不运行或声称产品音频验收。
**Version impact: none** — 决策/计划不改变 source 或 active identities。
**Documentation impact: none** — 仅 PRD/计划文件，不改当前 Portal 页或 source
facts；实际实现的 Portal 更新仍由各 Task 交付。**Pitfall impact: none** —
沿用已有决策存档、Task 分界与验收规则，不新增流程机制。

### 2026-10-10 — D04 已批准边界与 refreshed premises

本次独立 docs Task 检查 fresh main：
`314d1cadd8aab7504513b15a42cc96bb9c8742d8`。#1929 已真实合并为该 SHA，
仅交付 BPM／D03 决定与计划更新，不交付 D04 产品能力。
owner 对四项问答及 2026-10-11 三项补充的批准记录在
[D04 实时控制与作品电平决定](../prd/decisions/2026-10-10-mixer-live-controls-and-meter.md)：

- MASTER 与 ENC4 共用本设备监听音量，不写工程、不改变录音／重采样／导出。
- 真正独立的 LP／HP／BP 类型、Cutoff 和 Resonance，不用现有单值 Filter
  或 Sample Tone 冒充。
- 全部 64 个 Pad 的实时 Mute／Solo 随 Performance 录制／重放，不改变
  Project 内 Pad 的 `playback.muted`。
- meter 显示效果后、监听音量前的立体声 dBFS 峰值，排除节拍器；设备
  监听音量变化不改变作品电平。
- 2026-10-11 补充：主效果 ENC1=Cutoff／ENC2=Delay／ENC3=Reverb；新增
  FILTER 组 ENC1=LP／HP／BP 类型／ENC2=Cutoff／ENC3=Resonance，ENC4
  仍固定监听。两个组的 Cutoff 共用一个参数。
- 独立滤波停转／切组保持、离页按 HOLD 释放，类型／Cutoff／Resonance
  完整随 Performance 录制／重放，不写 Pad／工程音色参数。
- 多个 Solo 可同时启用；任一 Solo 时仅放行被 Solo 的 Pad，Mute 优先，
  Mute＋Solo 的 Pad 仍静音。

**Premise dispositions:** 当前 `MonitorOutputSession`、Web monitor gain、App
ENC4 与设备偏好存储已提供可复用的监听 producer；MASTER 只缺对应 consumer，
不重复其 producer。完整 Web operation 注册表、FX validator、Session type、
Domain Performance event variant、`MasterFxChain::process_filter` 及
`PerformOverview` 仍没有上述独立滤波、live Mute/Solo 事件或常驻作品 meter。
已有单值 FX、Sample persisted mute 与 capture-only PCM batch 不构成这些交付。
当时开放的 #1991 仅增加 owned Session inspection 和有关浏览器验证；
其实际文件范围没有上述 D04 producer，不把它视作对应能力已交付。

**当时的剩余设计与实施边界：** MASTER consumer 可以基于已批准共享
状态准备独立声明；当时待决的滤波默认值／参数范围／事件兼容模型、Mute/Solo
初始化／恢复／离页生命周期和 meter 峰值窗口／保持／不可用表现仍须补齐设计。
独立滤波已明确沿用 Perform 停转／切参数组保持、离页 HOLD 规则；触屏
slider release／blur 提交语义保持，不自动扩展到尚未定义的新状态。
后续 producer／事件模型与
consumer 分 Task，开始前刷新实际源码、声明精确文件与最低层验证；
真实听感、四页 A1/A2 和 V1 仍未完成。

**Task declared files:** 本计划、
`docs/prd/decisions/2026-10-10-mixer-live-controls-and-meter.md`、
`docs/prd/questions/hardware-control-mapping.md`。canonical 独立 decision 目录
承载决定，不回改旧决定或共享索引；其他方向键和 SHIFT 问题保留。
**Lowest-tier verification:** 相对链接与声明路径、staged new-file ownership suite、
cached whitespace／精确文件清单、clean committed-head `docs_static`、PR body
lint 与 declaration／batch-only check。不运行或声称产品音频验收。
**Version impact: none** — 无 source、Contract 或 active identity 改动。
**Documentation impact: none** — 仅 PRD／计划，不改当前 Portal source facts／图；
后续实现保留对应 Portal 责任。**Pitfall impact: none** — 沿用已有 Task 与
decision archive 机制，无新增流程缺陷或机制。

### 2026-10-11 — D04 剩余产品边界与四排键盘已批准

本次独立 Decision Task 初始检查 fresh main
`305b76608b5c6a19b718253604973d250a795765`；开始编辑前进一步刷新并将
新隔离 docs worktree fast-forward 到
`a98ae01c4f033c78221fc961f6207c7fe5cabfd7`。#1992 已真实合并为该 SHA，
实际 scope 是播放中 Pattern 切换和相关上屏，不交付本段新增 D04／键盘能力。
#1991 已合并为 `083ac62812564266721c664dd49915d636b94123`，其 owned Session
inspection 与浏览器验证也不等于 D04 producer 或四页 A1/A2 验收完成。

owner 本次真实问答确认：

- [D04 滤波](../prd/decisions/2026-10-10-mixer-live-controls-and-meter.md)
  初始 OFF、默认 LP／Cutoff 20 kHz／Resonance 0%；Cutoff 20 Hz–20 kHz
  对数调节，Resonance 0–100%；进入 FILTER 组不改变声音。
- live Mute/Solo 切 Bank／Pattern 保持，离开 Perform／切工程清空；
  Performance 捕获录制起点状态与后续变更，重放恢复。多个 Solo、Mute 优先
  及不修改 Pad muted Truth 的既有批准保持。
- stereo meter 的 L／R 独立、峰值保持 1 秒、显示 −60…0 dBFS、静音 −∞；
  真实读数不可用时明确 unavailable。沿用 Post-FX／Pre-ENC4、排除节拍器。
- [四排键盘映射](../prd/decisions/2026-10-11-creator-keyboard-spatial-mapping.md)
  为 1234 → 13–16／QWER → 09–12／ASDF → 05–08／ZXCV → 01–04。
  明确 Q 从当前 Bank 01 改为 09，MIDI note 36–51 与 Pad 身份不变。
  #1960 的 owner 确认前提已经满足，状态为 approved、implementation pending。

**Premise dispositions:** 复查完整默认键盘映射、Creator input controller 与
PadSurface：仍为 Q–I／A–K 的两排默认输入，键帽从同一映射派生；已交付的
Pad 显示顺序与 MIDI 36–51 可保留。K1 尚缺四排 producer／键帽及相关测试、
Portal 表的实现。复查 MonitorOutputSession、App ENC4、MasterFxChain、
Domain Performance event variant、Web raw event／operation 注册表及
PerformOverview／capture worklet：共享监听 producer 仍可直接复用；独立
滤波、live Mute/Solo 事件及常驻作品 meter producer 仍未交付，不重复已有能力。

本 Task 只记录批准和开放问题状态。#1822 的其他页方向键、新 SHIFT 组合键
仍待 owner 决策；新事件编码／兼容策略、meter 测量窗口／显示衰减和投影接口
仍须对应 Task 明确，不能从本次回答推测。已批准的新滤波保持／HOLD 规则
不改变既有 touch slider release／blur 提交语义。D04／K1 实施、真实键盘
输入／听感、四页 A1/A2 和 V1 继续保持未完成。

**Task declared files:**

- `docs/prd/decisions/2026-10-10-mixer-live-controls-and-meter.md`：只追加本次
  已批准边界并解除对应未决状态，不改既有批准。
- 新 `docs/prd/decisions/2026-10-11-creator-keyboard-spatial-mapping.md`。
- `docs/prd/questions/hardware-control-mapping.md`：保留未批准的方向键／SHIFT，
  将本轮 D04／#1960 产品问答标记为已批准、待实现。
- 本计划：同步 D5／K1 状态与本次来源及验证声明。

**Lowest-tier verification:** 声明文件与相对链接、批准语义／未决边界人工核对、
staged new-file ownership suite、精确 cached list 与 whitespace、clean
committed-head `docs_static`、PR body lint、declaration／batch-only evidence
check。仅 docs 检查，不运行或声称产品／浏览器／音频验收。
**Version impact: none** — 无 source、Contract、manifest 或 active identity 改动。
**Documentation impact: none** — 记录已批准未来行为，当前 Portal 实现
source facts 未变；实际能力实现 Task 仍负责对应 Portal 更新。
**Pitfall impact: none** — 使用既有独立 decision 与 Task 验证机制，无新的流程缺陷。

### 2026-10-11 — 三页导航与共享尾音已批准（独立 Decision Task）

Fresh main / isolated Task base：`5d31f21bb7b5f91014881c05b0ef7f4708c03b29`。
保留完整七文件草稿和 source／index guards 后，Root 授权本 Task 的独立
worktree 快进整合实际 main `1e9a90c1055c8fc5c5df3fa878dda416b1d00a20`；
七路径 incoming 均未改变，草稿逐字保留，index 未新增暂存修改。
#2000 实际 merge `116280f9209245b4757a814fcf3155002b025269` 已交付 MASTER
consumer，完整 Creator 仍 pending；#2005 已合入 S0／S1 治理，原完整 Deploy
Contract 实际失败仍未关闭。不借上述 merge 或其他 Task 结果建立本 Task
PASS。此 Decision Task 无身份／Build 分配，不适用 allocation-cut 特殊前缀，
保留原完整 Portal check。
owner 实际批准的完整问答记录在
[三页导航与 live Mute/Solo 共享尾音](../prd/decisions/2026-10-11-creator-navigation-and-live-mute-tails.md)：

- Project 左右相邻选择、上下在三列列表移一行，只选择，OPEN 才打开。
- Sample 上下与 Sequence 一样选 Pad，左右切 Trim／Playback／Tone/EQ／Pad。
- Perform 上下选 Pad，左右切 PRIMARY／FILTER／MORE，并保持效果声音。
- 导航不触发 Pad、不写 Truth；切编辑上下文取消未提交的 400 ms 预览。
  SHIFT + ←/→ 撤销／重做，SHIFT + ENC1–3 细调，SHIFT + ↑/↓ 不分配。
- 对应 Pad 当前／后续输入立即阻断；已进入共享 Delay／Reverb 的尾音自然
  衰减，其他 Pad 效果继续，不扩大为每 Pad 效果发送／尾音隔离。

**Premise dispositions:** 实际 App 仅给 Sequence 接入普通方向导航；现有
Project selection、Sample 四子页和 Perform PRIMARY／MORE 可复用，但
新增三页接线与 FILTER producer／consumer 仍未交付。RealtimeEngine 尚无
live Mute/Solo masks。尾音问答前提已经满足；原 96-frame ramp／cursor
保留为工程提案，须满足已批准即时输入阻断，不是 owner 批准的宽限。
R1–R6、legacy 兼容、真实 applied／capture ACK、receipt 与 epoch 义务不缩小。

**后续工程边界：** K2 从已有页内选择／子页状态接线，不造第二份状态，保留
Project OPEN、完整 64 Pad 边界、400 ms 取消和 SHIFT history／细调。最低
mounted App 事实分别验证只选择不打开、上下三列一行、选 Pad 不触发／不改
Truth、切页取消未提交预览、Perform 切组保持及 SHIFT ↑/↓ 无动作；原完整
browser journeys 和 far-side 不缩小。完整 FILTER 导航仍依赖 D04 的
F1→M1→P1→W1→C1 实际交付，不能渲染假组充数。
M1 沿用 [producer 计划](2026-10-11-performance-live-control-producers.md) M1 节的十文件声明，
等待 F1 实际合并后顺序集成；最低真实 PCM 证明当前／后续 Pad 输入门控、
共享尾音自然衰减、其他 Pad 继续、多 Solo／Mute 优先以及 reset／旧 epoch
拒绝，执行原 allocation 和 concurrent stress 的预算。K2／M1 的产品验证
本 Decision Task 均未运行。

**Ownership:** K1 正在自己的隔离 worktree 验证四排键盘，拥有本计划／问题
文件及两个 Portal 页的并行修改。本 Task 仅编辑自己的新 docs worktree，
不改 K1 冻结源。后续 main integration 保留两者批准与各自 source audit，
不把 clean worktree 当作无人使用。K2 的 App／Sample／Perform／测试范围和
M1 的 engine 范围开始前仍须刷新其他 Task 实际交付与 owner；不并行写共享源。

**Declared files（恰好七个）：**

- 新 `docs/prd/decisions/2026-10-11-creator-navigation-and-live-mute-tails.md`。
- `docs/prd/questions/hardware-control-mapping.md`。
- `docs/plans/2026-10-09-creator-desktop-final-followup.md`。
- `docs/prd/decisions/2026-10-11-performance-live-control-encoding.md`。
- `docs/plans/2026-10-11-performance-live-control-producers.md`。
- `apps/docs-site/docs/platform/input.mdx`。
- `apps/docs-site/docs/hosts/creator-interactions.mdx`。

**Lowest-tier verification:** 声明路径／相对链接／批准来源核对，原 pitfall
ledger 15 cases 与 CI scope／ownership 77 cases、whitespace／精确文件清单；
新文件进入 index 后必须按原步骤重跑 ownership，预先执行不替代这项证据。提交前
canonical `scripts/docs-site.sh check` 校验两处 current 页面及链接，随后按
实际 committed head 完成 docs_static／PR body／declaration 与所选 batch-only
证据检查。不运行 native、Creator browser 或声称听音验收；当前实际验证
结果如下，staged ownership 与 committed-head shipping 证据另按步骤取得。

**Actual verification:** 本 Task 的七文件 Portal 输入冻结后，以普通 uid 501
在自己的 worktree 建立 APFS COW 依赖副本；不共享 writable symlink，不复制
donor `.cache` 或 generated build。36,747 installed entries 的源／目标完整
SHA-256 相同，regular inode 独立，所有 dependency symlink 留在各自树内。
使用 Node 26.8.1 与命令-local npm 10.9.3，原完整
`scripts/docs-site.sh check` 实际 exit 0，59.876405 秒：176/176 tests、52
pages、10 diagram sources／20 outputs、current facts／snapshot／type／
changelog／production build，以及 50 routes／internal links 全部完成。
child terminal 后再采 source／index、tool、donor tree 与 lock guards，均
与执行前一致。receipt：
`approved-navigation-and-fx-tail-decision-preparation-20261010T2238Z/portal-execution-20261010T225903Z/final-receipt.json`，
SHA-256 `8cf5ac77840c6735ff60a3f69de4d461039fd0e72dc67b9df685be6a41c79cf1`。
本段仅补真实结果，不改变已校验 Portal 页的状态或新增产品行为。
原 ledger 15 cases 和 scope 77 cases、33 个本地 relative targets／source
paths 及 whitespace 也已通过；未暂存阶段的 77 不代替新文件正式 ownership。
该结果仅为文档 Task 验证，不关闭 K1／K2／M1、原 Creator 失败、A1/A2 或 Goal。

**Version impact: none** — 只记录未来批准和 Portal 的批准／待实施状态，无
产品源码、Contract、active manifest、ABI 或 Build 分配。未来 K2／M1 及既有
ABI 债保留，由实现 Task 和 V1 按实际影响结算。
**Documentation impact: required** — `/platform/input/`、
`/hosts/creator-interactions/` 当前写了未决方向状态；同 Task 同步批准与
必要链接，明确实施／验收待完成。Portal 不扩写不存在的声音或导航能力。
**Pitfall impact: none** — 使用已有 Decision Task、所有权协调和验证机制。

历史段落中的方向／尾音 pending 仅表示其当时状态，由本段窄范围替代；
其他 SHIFT 提案仍未批准。#1822 不关闭，K1／K2／M1、A1/A2、V1 和 Goal
仍有未完成义务，#2002 的历史风险批准不转移到其他 Task。

2026-10-09 owner 已确认统一原则：旋钮 1/2 管视图位置，旋钮 3/4 管当前页
主要数值，方向键做导航，SHIFT 保留撤销/重做并支持粗调。此回答只确认
原则，具体页的参数、当前 Pad 与步长尚未批准；不以它推导完整映射。

## I1a — Sequence view and current-Pad navigation (#1822)

Owner 于 2026-10-09 回复「采用」，批准：ENC1 每格横向滚动一小节；↑/↓
按 A01–D16 选择当前 Pad，跨 Bank 同步 Bank 与上屏，在首尾停止；只高亮，
不发声、不改变音符选择或 Project Truth。其余页映射与粗调步长仍待决定。

**Premise disposition before implementation:** Task base 与 freshly fetched
`origin/main` 均为 `d4eb51161e8b97d33f2cb8cc7f4184696576caef`。Live #1822
open、无评论；当前 `PhysicalControls` 禁用 ENC1/↑/↓，App 只有 ENC2–4 与
左右 Pattern 绑定，Grid 仅有原生滚动，故本次批准的连接仍缺失。原 T6 已交付
ENC2–4/左右键，不重做。继任 #1907 只修复 authoring refresh，#1908 只更新
能力调查；唯一开放 PR #1904 是不重叠的 audition 计划。App 现有 Bank effect
清空音符选择；↑/↓ 必须绕开该清空，保留显式 Bank 键原有的清空语义。

**Declared files:**

- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/components/physical_controls.tsx`
- `apps/creator-web/src/components/sequence_grid.tsx`
- `apps/creator-web/src/components/sequence_touch_workspace.tsx`
- `apps/creator-web/src/components/sequence_overview.tsx`
- `apps/creator-web/src/components/overview_display.tsx`
- `apps/creator-web/src/components/pad_surface.tsx`
- `apps/creator-web/src/styles.css`
- `apps/creator-web/test/sequence_grid_edit.test.tsx`
- `tests/platform/web/creator/creator_web_sequence_grid.spec.mjs`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/platform/input.mdx`
- `docs/prd/decisions/2026-10-09-sequence-view-and-pad-navigation.md`
- 本计划。

**Lowest-tier verification and journey:** App component red/green 验证每格实际
小节宽度及横向两端；当前 Pad 首尾、跨 Bank 与上屏可见性；跨 Bank 后返回
仍保留所选音符，Truth/revision/trigger 调用保持原值；显式 Bank 键仍清空选择。
Packaged Chromium 从 EDIT 的真实滚动容器读取几何，验证滚动与 overview frame；
从音符框选经过 Pad 跨 Bank、边界及返回，逐段检查高亮、Bank、音符选择、
完整 Truth 与 history 不变；SETUP/离页禁用 ENC1，不积存隐藏的滚动命令。
完整 Creator lane 保留既有 ENC2–4、Pattern、SHIFT history 与 accessibility
到首个 Pad 的 journey。Portal check；新增文件 stage 后 scope Python suite；
clean committed head 的所有实际 batch-only lanes 与当前 head 独立评审。
真实 Safari/iPad/物理旋钮及听感未执行仍归 A2，不以自动化替代。

**Precommit evidence:** 再次 fetch main 后仍为上述 `d4eb51161`；继任记录与
源行为无变化。新增控件在未实现树上 2 red；CSS scale 0.5 的独立回归先显示
192 px 而非 384 px，再由 layout-pixel 修复通过。最终 App component 14/14、
TypeScript、Portal check（50 routes）通过。完整 Creator/batch lane、当前 head
独立评审与合并状态由本 Task PR 的验证记录承载；本记录不预先宣称这些已通过。

**Independent review follow-up:** #1909 初始头 `108c3d9b` 的独立评审在真实
Chromium 复现禁用旋钮仍累计 wheel 余量。已补 red（SETUP 半格 + EDIT 半格
误滚一小节）并修复：禁用时拒绝 wheel/pointer 起点，可用状态/参数切换清空
wheel/drag；同时保留启用后两次半格组成整格的正常行为。Packaged journey
使用原生 wheel 并等待事件送达后再断言，不能以 disabled 属性代替该边界。
初始完整 lane 为修改而主动中止，exit 143，保持未通过；新头重新验证。

**Packaged fixture pacing:** 第二次 lane 的新场景在首个音符前失败。保留的
trace 显示 resize 已写 Truth，但 EDIT 刚挂载时仍是 1-bar 投影且
`data-editing-disabled=true`；测试当时量取旧几何并点击被正确锁定的网格。
新场景改为先等待上屏实际呈现 4 bars 且投影允许编辑，再量取/点击；原有完整
Truth、history、trigger、选择保留与边界断言均保留，不增加 sleep 或超时。
此为测试前置条件修正，产品实现未改变；失败 trace 留存后，新场景使用
`eaaf6759` 已打包产品单独完整通过（1 test，15.3 s）。该诊断不替代最终
committed head 的完整 Creator lane；最终头仍重新执行该 lane。

**Version Management:** Creator 新交互积累 MINOR debt，留待本计划 V1 协调
结算；本 Task 不分配 Product Build。**Documentation impact: required** —
`/hosts/creator-web/`、`/platform/input/`，同时记录新的产品决定。

## I1b — Web monitoring output producer

Owner 已批准 [三个页面旋钮与固定监听音量](../prd/decisions/2026-10-09-contextual-encoders-and-monitor-volume.md)，
并分别确认 400 ms 取消边界、本设备音量记忆和 Perform 效果保持。
该决定替代 D1 原则中上排统一视图/SHIFT 粗调；D2 的产品语义已确认，
实现与验收尚未完成。其他页方向键、D3/D4/D5 其余问题不从此推导。

**Premise dispositions before implementation:** fresh main 与 Task base 为
`502932e345b621abc5533431e61adf0d0253a189`。#1909 已交付 Sequence 导航，
不重做；#1822 open，唯一开放 PR #1904 为 audition 计划。检查 Runtime Session
的实际 bootstrap、capture factory 与 processor-failure 分支：正常路径直达
AudioContext destination，失败恢复调用固定直连 destination 的 bridge；同一
注册表中 `registerAudioNode`/`startAudioWorklet` 已接入 tap，为正向控制。
Session 完整公开返回对象无监听音量/目标接口；Creator metronome 同样直达
destination。故监听 gain producer 仍缺失，须同步保持恢复路径和 capture 边界。

**Behaviour:** Session 提供 0–100 的监听音量（默认 100）、读取值与 Host
监听目标。可在 activation 前设置，AudioContext 创建时先应用，再连接任何
发声路径；运行中短 ramp 平滑调节。master capture 位于 gain 前，tap 故障
恢复也进入同一 gain；跨 context/无效目的地拒绝，重复恢复不叠加连接。
关闭后拒绝修改并断开 gain。设备记忆、metronome 路由与旋钮 UI 属于 I1c。

**Declared files:**

- `packages/audio-runtime/include/lmdj/audio/web/realtime_audio_worklet.hpp`
- `packages/audio-runtime/src/web/realtime_audio_worklet.cpp`
- `packages/web-runtime-platform/src/bridge.cpp`
- `packages/web-runtime-platform/src/web-runtime-pre.js`
- `packages/web-runtime-platform/web/runtime_session.mjs`
- `packages/web-runtime-platform/web/runtime_types.d.ts`
- `packages/web-runtime-platform/web/performance_master_capture.mjs`
- `packages/web-runtime-platform/test/runtime_session.test.mjs`
- `packages/web-runtime-platform/test/performance_master_capture.test.mjs`
- `tests/platform/web/audio/realtime_audio_worklet.spec.mjs`
- `tests/platform/web/host/web_runtime_host_lifecycle.spec.mjs`
- `apps/docs-site/docs/platform/web-runtime.mdx`
- `apps/docs-site/docs/core/modules/web-runtime-platform.mdx`
- `apps/docs-site/diagrams/web-runtime-platform.architecture.json`
- `apps/docs-site/static/diagrams/web-runtime-platform.html`
- `apps/docs-site/static/diagrams/web-runtime-platform.svg`
- `docs/prd/decisions/2026-10-09-contextual-encoders-and-monitor-volume.md`
- 本计划。

**Lowest-tier tests and journeys:** Node Session tests bind pre-activation volume,
normal graph, tap initialization/processor failure, repeat connections, invalid
input and terminal cleanup to actual producer calls; master-tap controller tests
assert gain is downstream and batch bytes unchanged. Real rebuilt AudioWorklet
conformance exercises alternate same-context monitor destination, zero/half/full
output energy, rejection of cross-context nodes, idempotent fallback and audible
continuation. Existing activation/recovery/capture journeys remain intact. Run
Portal check and exact clean-head selected batch-only lanes under issue-done;
record platform-not-runnable and unperformed physical hearing honestly.

**Version Management:** additive Web Session capability and Web Audio routing
accumulate Web Platform/Audio Runtime MINOR debt for V1; no Product Build or
persisted Contract change. **Documentation impact: required** — `/platform/web-runtime/`,
`/core/modules/web-runtime-platform/`; update the source diagram in the same Task.

**Source-shell fixture correction:** the full Web Host proof reaches the existing
source-shell activation journey, whose injected AudioContext predates monitoring
and has no `createGain`, destination or node registration. This fails activation
at the newly required browser capability, before any lifecycle assertion. Keep
the failed trace and update only that fake's Web Audio surface; preserve every
activation, interruption, recovery and cleanup leg and the existing deadlines.

## I1c — Creator contextual encoders (dependent on I1b)

Deliver the approved per-page table, touch parameter groups and visible readback,
SHIFT fine steps, device-local ENC4 memory, and metronome monitoring routing.
Sample/BPM follow the approved 400 ms cancel/commit lifecycle; Perform uses owned
live gestures retained through rest and group switches and released on page exit
under HOLD. Consumer development base is `deebae1c3c99de1081e71647689bfebff7b83afc`, the
implemented I1b producer, while fresh main remains
`502932e345b621abc5533431e61adf0d0253a189`. I1b is independently source-reviewed
but not merged yet: this dependent branch must be based on its actual squash
before shipping. Inspection confirms the existing Sample preview/update and
Perform live/journal operations are reusable; current bindings only serve
Sequence, ENC4 is Swing, Project selection and FX groups are touch-only, and
metronome bypasses capture directly to destination. This Task adds consumers;
it does not reimplement those producer operations or the merged I1a navigation.

**Steps and state boundaries:** trim Start/End use 10 ms per detent (SHIFT one
source frame), Pitch 1 st (SHIFT 0.1 st), gain 1 dB (SHIFT 0.1 dB), Pan/Tone
10 units (SHIFT 1), FX 10/1000 (SHIFT 1/1000). BPM remains integer 1 BPM;
view/list navigation retains one bar/row/item. ENC4 is always one percentage
point. Bounds reuse Core-valid playback/loop limits; no new units or DSP.
Sample turns across parameters of the same Pad merge into one 400 ms update;
no-change turns save nothing. Touch slider commit semantics remain intact.
Target loss, System, Esc, history and recording/mutation locks cancel rotary
work before it can submit; sent authoring results retain normal acknowledgement
and refresh semantics. The current BPM consumer previews readback then uses existing publication on
save; this is an unfinished acceptance item until the audible preview producer
and consumer in PR #1929 are implemented. Perform rotary ownership persists through group/rest, shares the existing
FX gesture when touch and rotary target the same FX, and releases before leave
through existing HOLD semantics. Host preference restore precedes enabling
ENC4; later turns win, storage refusal cannot stop monitoring. Metronome enters
monitor downstream of capture. No alternate ENC4 or undeclared direction keys.

**Declared files:**

- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/runtime/runtime_types.ts`
- `apps/creator-web/src/runtime/metronome_click.ts`
- `apps/creator-web/src/state/sample_state.ts`
- `apps/creator-web/src/state/encoder_input.ts`
- `apps/creator-web/src/state/sample_encoder.ts` (new)
- `apps/creator-web/src/state/monitor_volume_preference.ts` (new)
- `apps/creator-web/src/state/perform_state.ts`
- `apps/creator-web/src/components/physical_controls.tsx`
- `apps/creator-web/src/components/pad_surface.tsx`
- `apps/creator-web/src/components/sample_surface.tsx`
- `apps/creator-web/src/components/project_surface.tsx`
- `apps/creator-web/src/components/perform_surface.tsx`
- `apps/creator-web/src/components/fx_slider_bank.tsx`
- `apps/creator-web/src/components/overview_display.tsx`
- `apps/creator-web/src/components/sequence_overview.tsx`
- `apps/creator-web/src/components/sequence_touch_workspace.tsx`
- `apps/creator-web/src/components/waveform_editor.tsx`
- `apps/creator-web/src/components/authoring_history.tsx`
- `apps/creator-web/src/styles.css`
- `apps/creator-web/test/hardware_console.test.tsx`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `apps/creator-web/test/sequence_grid_edit.test.tsx`
- `apps/creator-web/test/sample_encoder.test.ts` (new)
- `apps/creator-web/test/monitor_volume_preference.test.ts` (new)
- `apps/creator-web/test/metronome_click.test.ts`
- `apps/creator-web/test/perform_surface.test.tsx`
- `apps/creator-web/test/authoring_history.test.tsx`
- `tests/platform/web/creator/creator_web_sample_editor.spec.mjs`
- `tests/platform/web/creator/creator_web_sequence_grid.spec.mjs`
- `tests/platform/web/creator/creator_web_perform.spec.mjs`
- `tests/platform/web/creator/creator_web_sequence.spec.mjs`
- `tests/platform/web/creator/creator_web_hardware_layout.spec.mjs`
- `tests/platform/web/creator/creator_web_touch_fit.spec.mjs`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/hosts/creator-interactions.mdx`
- `apps/docs-site/docs/platform/input.mdx`
- `docs/prd/questions/hardware-control-mapping.md`
- 本计划。

**Lowest-tier verification:** typed helper tests pin per-parameter bounds,
fine steps, loop fitting, one merged save, no-change/cancel and stale target
refusal; IndexedDB tests pin default/corruption, serialized writes and bounded
restore. Component/controller tests exercise real registration, Project
selection-only/scroll, Sample cancel boundaries, all six FX/group persistence,
HOLD-aware leave, SHIFT events, monitor independence and history cancellation.
Metronome tests assert its actual downstream destination. Packaged browser
journeys use the real current bindings, explicit OPEN, Sample far-side Truth/
Undo and cancellation, and monitor preference reload; preserve all existing
journey legs including SETUP Swing. Check readback/8-row fit at console sizes.
Recording also covers rotary-to-touch takeover of one FX and verifies Core's
open-FX count returns to zero before the stopped recording is saved/reopened.
Run TypeScript, ownership on the staged new files, Portal and the exact clean
head selected batch lanes; independent full-diff/current-head review remains
required before squash. Physical knobs/hearing and Safari/iPad remain A2.

**Precommit refresh (2026-10-09):** fresh `origin/main` remains
`502932e345b621abc5533431e61adf0d0253a189`; no successor delivered the remaining
I1c bindings. New staged-file ownership tests pass (77), TypeScript passes,
and the independent new App/Perform group passes (15). The reverse FX handoff
regression fails before the fix at the second engagement, then passes with
one matching gesture; the prior grouped Project-selection timing failure is
retained and corrected by waiting for its actual enabled encoder. Portal passes its 175 tests and 50-route build. All 69 Creator test files / 1,164 tests and TypeScript pass. The clean build/package pass. Packaged Chromium passes the new hardware, Sequence binding, Sample merge/cancel/Undo/preference-reopen and rotary-to-touch Perform recording journeys. The status containment regression passes against the real rendered console and packaged CSS. Earlier browser failures are retained: report export entered System and correctly cancelled a pending turn; default seed Pad targets were unavailable; Truth acknowledgement preceded the history input unlock; zero playback fields are omitted by Core. Tests now observe the actual target, committed Truth, restored full playback and input availability without removing journey legs. Perform save also waits for its WAV binding before inspecting the artifact. The complete exact-head Creator lane is still pending; targeted passes do not replace that shipping obligation.

**Open acceptance finding (independent review, 2026-10-09):** the implemented
BPM preview updates readback only; playback tempo and metronome follow committed
Truth after 400 ms. The approved decision did not limit immediate preview to
readback. D2 is therefore not fully accepted: retain this finding until the
approved audible runtime tempo preview/clear producer is implemented and
consumed. The owner's pending playback-position choice is recorded in the
supplemental plan in PR #1929; it does not narrow the immediate-preview decision. No passing UI test proves
pre-commit audible tempo preview. The remaining contextual bindings and
monitoring work continue independently; this finding is not silently excluded.

**Version Management:** Creator MINOR debt and monitoring preference are Host
state, deferred to V1; no persisted Contract or Product Build allocation.
**Documentation impact: required** — `/hosts/creator-web/`,
`/hosts/creator-interactions/`, `/platform/input/`.
No corresponding Creator/input source diagram exists; update their current
control tables and retain I1b's shared audio graph. Other product questions
remain in #1822 and D3–D5.

2026-10-10 consumer integration refresh: monitoring producer #1910 is merged
as `9119a7f90262e1c8ada92ac6b894f5014a5c0cab`; strict fixture #1915 is merged
as `864c0f061033a7f0c3488f1908a8817516cd3b62`. Rebase the single consumer Task
onto that actual main, retaining the newly merged MPC Pad arrangement and
touch-panel layout. The only textual conflict is in the Creator Portal page:
retain main's Pad-order paragraph and the consumer's metronome gain routing.
The refreshed source passes all 69 Vitest files / 1,169 tests and TypeScript.
Full packaged/browser and physical acceptance remains outstanding. The BPM
readback still does not preview engine timing; the audible-tempo supplement
PR #1929 and the owner's playback-position choice remain required.

2026-10-10 Sample integration: rebase onto `1992e258b066152e7d08cf5382bf94d21f1d95d1`,
including the Sample contextual pages in #1930 and the owner's DUPLICATE decision
in #1932. Keep all four touch pages and Pad colour management; retain the approved
independent Trim / Pitch and Pad Sound encoder groups. Touch parameter takeover
cancels the rotary draft before the touch edit. Switching Sample subpages cancels
the pending rotary timer and its owned runtime preview before showing the new
page. A component regression first fails because the old timer saves Pitch after
leaving Trim; it must pass with no update and restored playback after the full
400 ms interval. This integration does not implement Assign, new numeric editing,
or the outstanding audible BPM preview. The integrated tree passes all 69
Creator test files / 1,174 tests, TypeScript, and the 50-route Portal check.
The expanded packaged journey retains the original commit, Pad cancellation,
Undo and device-volume reopen legs and adds the Sample subpage cancellation leg;
its browser execution and the complete selected Creator lane remain pending.
A later main refresh is `46df56797265942f760afb253c3e4ad2b3a13c80` (#1934),
a documentation-only interaction map; it does not implement contextual encoders
or the remaining audible BPM preview.

## D3 — record the approved DUPLICATE name

Owner 于 2026-10-10 选择「DUPLICATE（推荐，明确表示复制工程）」，保留
自动保存、复制新身份并打开副本的已有语义。决定见
[D01 DUPLICATE](../prd/decisions/2026-10-10-creator-project-duplicate-label.md)。

**Refreshed premise:** Task base 与 inspected main 均为
`864c0f061033a7f0c3488f1908a8817516cd3b62`。D01 的
`project_surface.tsx` 已显示 DUPLICATE，并用 `onDuplicate` 调用 App 的
`duplicateProject`：经现有 journey 复制，再打开副本；复制/打开失败保留
真实结果与可重试入口。9 月 29 日 workflow baseline 已批准自动保存与复制。
因此没有新的产品实现缺口，不重复修改按钮、存储或失败处理。
该判断不声称完成整体四页、真机或听感验收。

**Declared files:** 本计划；
`docs/prd/decisions/2026-10-10-creator-project-duplicate-label.md`。
**Lowest-tier verification:** 相对链接、源码/回调链与已有决定核对；stage 后
77-case ownership suite；staged diff check；committed-head docs_static；
PR body lint、declaration-only 与无 batch lane 的 evidence check。
**Version Management:** Version impact: none — 产品行为已存在，只记录命名决定。
**Documentation impact: none** — 只新增产品决策并更新计划，Portal 页面与事实不变。

2026-10-10 Perform integration: refresh onto `08c216647138ef9e1f7824a4a2624f82eef86cce`,
which includes #1935's Live / Slots / Takes / Replay pages and #1931's Host proof
result slots. Preserve page state, native pointer capture, navigation refusal
while a touch FX gesture is open, and recording/replay continuity. Keep the
approved three main FX and three more encoder mappings, HOLD semantics and
rotary/touch ownership. Extend the existing touch geometry journey to all
three main faders without removing any page, hit-area or first-screen assertion.
The previous complete lane on 4d558259 was stopped for this integration after
two failures (old-generation window listener retained; final project.inspect
request timeout in the full Perform capture journey). Logs and traces are
retained outside the worktree; no full pass or cause of the latter is claimed.
The encoder cancellation listener must be owned by the Runtime session and
rebound on replacement, verified by the unchanged packaged recovery journey.
The resolved integration passes 69 Creator test files / 1,179 tests, including
FX value retention through Live / Slots / Takes / Replay, TypeScript build,
77 staged ownership tests, and the 50-route Portal check. The three primary
faders share one row, preserving their original 44 px hit areas and 80 px
vertical travel. Packaged geometry, recovery and the complete lane remain
pending; these component passes do not settle those obligations or audible BPM.

2026-10-10 overview integration: refresh the single consumer Task onto actual
main `ec15f9adf3ca7c3fd09c06d61b53e0bcdf189fe6`, including #1938 Sequence
touch controls, #1940 Sound Set navigation and #1942 mode-specific overview.
Resolve the overview conflict by retaining the opened Project / selected Sample /
selected Sequence identity, qualified Perform feedback and the System details
boundary from main, alongside the four approved encoder function/value readbacks.
Keep the SYSTEM title while its overlay is open and the opened Project identity
available to assistive technology. Do not restore the removed generic Project
facts or build metadata to the editor screen. Every existing navigation, history,
capture and refusal journey remains in the consumer range. The original b07
complete Creator failure and its 14-view static/Figma comparison remain retained
outside this worktree; neither is a pass on this integration. This refresh does
not settle the audible BPM playback-position question, Assign, fine numeric
editing or the other pending product decisions. Exact integrated verification
and the original complete Creator lane remain required. The conflict-resolved
integration passes TypeScript, all 71 Creator component/helper files / 1,209
tests (173.96 s), and the staged 77-case ownership suite. Portal and the
committed-head complete Creator obligations still require their own results;
these component passes do not replace them.

2026-10-10 touch-preview integration: later main
`4281d5f54dd01ad73c18e876c2119a35b0229e0b` adds #1946's synchronous shared
touch drafts and rejected-gesture cleanup. Preserve its Project/Pattern/mode
and recording-lock boundaries, the Sample editor's controlled preview-active
signal and both sets of existing lifecycle regressions. Keep ENC4 assigned to
monitoring; do not restore the superseded Swing encoder. Extend the existing
touch timing journey in the declared `sequence_grid_edit.test.tsx` to verify
that ENC3's displayed value follows the same touch draft and cancellation as
the upper screen, without a Truth write. The Sample encoder cancellation
fixture publishes the running Host state after Project open, rather than only
changing diagnostics, and asserts that an audible preview actually begins
before each existing cancellation boundary. Keep the inactive-audio visual
preview and rejected-preview journeys from main unchanged. This refresh does not provide the
still-missing audible BPM producer. Retain the preceding ec15 integration
results as dated evidence; new source verification remains required.

2026-10-10 status/recovery integration: refreshed main
`42d86bfdf3c74785810ebaa0c5fe3e0e11e6e19f` includes #1947. Preserve its compact
default-sound recovery, recording ownership notice across modes/System, and
return-to-Takes Save/Discard workflow alongside I1c's contextual encoders and
FX gesture ownership. Both sets of existing Perform regressions and both CSS
blocks remain. Integrate in a separate short-lived worktree while the original
`bbd4433` complete proof retains its frozen source. That proof is evidence only
for its original head, and neither #1947's pass nor a clean merge substitutes
for fresh integrated-head verification. BPM audible preview and outstanding
product choices remain pending.

2026-10-10 Graphite/font integration: refreshed main
`d5554ed55f7ebc2d800285715cef79dcfed57c9a` includes #1948. Apply the prepared
#1947 integration in another isolated worktree, preserving its original frozen
verification inputs. Resolve the one overlapping CSS append by retaining both
#1948's compact action/font rules and I1c's encoder readbacks/group controls.
Keep main's neutral encoder icon, locked Space Grotesk dependency, stage clip,
font/geometry assertions and late-recovery layout observation unchanged. Preserve
#1947's recovery/recording workflows and all contextual encoder regressions.
The original 37-file declaration still bounds this Task; no mapping, DSP,
deadline, tolerance or unresolved product choice changes. TypeScript, complete
components at their original timeout, ownership, portal and fresh committed
Creator evidence remain required on this integrated input. Earlier runs on
`bbd4433` or `42d86bf` do not establish verification of this tree.
The integrated source now passes all 72 Creator test files / 1,230 tests at the
original 20-second case bounds (132.87 seconds), TypeScript, 77 staged ownership
tests, and the complete 50-route Portal check (82.27 seconds). The product and
test sources remain identical to those verified inputs; this paragraph records
terminal results only. Commit and replace the owned draft PR head with an exact
expected-head lease, retaining the earlier frozen branches and evidence. Fresh
committed-head browser proof and review, audible BPM preview and the outstanding
product choices remain incomplete; none of these component/Portal results is
complete Creator or device acceptance.

2026-10-10 producer integration: refreshed main
`a2a43cc088ab35e40297e80eecb7ef048923a154` includes the landed-overlay cutoff
(#1941), Candidate typed-byte proof (#1943), retained transport replay (#1950)
and matched-frame monitoring proof (#1949). Live PR metadata confirms each
merged source and introducing SHA. Carry I1c's same 36-file diff into another
isolated worktree; it applies without conflicts. Preserve all four producer
deliveries, #1947 recovery/recording and #1948 font/geometry behavior. The
Foundation immediate-depth-refusal repair remains a separate PR (#1956).
The earlier e74 Creator entry failed before tests because this owned checkout
lacked its locked Web test npm dependencies; retain that failed attempt and
provision each required package from its lockfile before fresh verification.
No mapping, product decision, deadline or assertion changes. Frozen earlier
results remain evidence for their own inputs. Verify this integrated source
before replacing the owned Draft PR head; audible BPM and the unanswered
product decisions remain pending.

This integrated input passed TypeScript, all 77 staged ownership checks, all
72 Creator test files / 1,230 cases at their original case bounds (159.87
seconds), and the complete 50-route Portal check (79.35 seconds). The source
and tests remain identical to the frozen verified inputs; only this results
paragraph was appended afterward. Commit the same 36 declared files and update
the owned Draft PR with an expected-head lease. Original complete Creator
browser proof, audible BPM preview, current-head review and the unanswered
product choices remain incomplete.

2026-10-10 stopped-Pattern producer integration: refreshed main is
`e14084f602448ee2046a9cd64e7dd3bf3bd2e7ea`, containing #1978's native
stopped-Pattern transport authority repair, #1956's Foundation depth refusal,
#1966's executable Creator proof build and #1977's VEL-tap regression. Merge
that actual main into the existing I1c consumer branch without conflicts;
retain all three shared touch/ENC3 BPM assertions alongside the new VEL test.
No contextual mapping, commit/cancellation boundary, HOLD rule, bound or
journey leg changes. The previous complete Creator result on `65b237cd`
was 112 passed, two failed and 11 skipped; retain its hardware-profile timing
failure and stopped-Record reconciliation trace as failed evidence. The
frontend reconciliation repair in #1970 remains an independent unmerged Task,
so this integration alone does not close that browser failure. Run the
unchanged complete consumer verification on the new input after coordinating
the browser/Portal build schedule. Audible BPM preview, physical acceptance,
current-head review and pending product decisions remain unfinished.
The newly refreshed interaction manual in main still describes ENC4 as Swing,
other pages' encoders as unassigned and rotary drafts as surviving page exit.
Add that existing Portal page to I1c's declaration and correct those current
source facts in this Task; retain the open audible-BPM finding and the existing
direction-key decisions. #1980 reorganizes the same handbook by page; retain its
new layout and anchors while updating the relevant control cards and appendix.
The earlier 03a integration and both successful Portal checks are retained as
dated evidence; fresh handbook verification is required. This adds one
documentation path, no product scope.

The integrated product/test inputs pass all 72 Creator files / 1,231 cases at
the original 20-second bounds (58.09 s) and TypeScript (1.54 s); all 32 owning
input hashes remain unchanged through the later handbook-only refresh.
Staged ownership passes 77 tests (6.03 s), official document validation passes,
and the final page-organized handbook passes the complete 50-route Portal check
(51.26 s). Its ConsoleDiagram and 39 anchors remain identical to #1980.
The final diff contains 37 of 38 declared paths. Record these results and push
the existing Draft PR; fresh committed-head Creator and independent review are
still pending. The separate frontend reconciliation repair must be integrated
before the consumer's complete browser acceptance; its predecessor's passing
Creator lane is not evidence for this consumer head. Audible BPM and the other
open product and physical acceptance obligations remain unfinished.

### 2026-10-10 — integrate the merged current-command repair

Fresh protected main is `4dde8e5e6b511c3ae2bd9c310f607f7d6148d2dc`, the actual
#1970 squash at 09:08:21 UTC. Its authenticated review and complete Creator
receipt belong to the repair's `46f6877b` input. They are not a pass key for
this contextual consumer. The preceding #1970-unmerged note is historical.

Merge that main normally into the clean pushed consumer `f2593fd...`; retain
its live Runtime/Project/session/command guards and all three mounted-App
late-error/current-error regressions alongside the approved ENC1–3 bindings,
global ENC4, Sample 400 ms cancellation and Perform HOLD/gesture ownership.
The merge has no conflicts; it imports the existing repair rather than
reimplementing it. Main's #1980 page-organized handbook, SVG, anchors and the
approved contextual-control corrections remain unchanged.

**Integration Task declared files:**

- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/runtime/pattern_transport_actions.ts`
- `apps/creator-web/test/pattern_transport_actions.test.ts`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `docs/plans/2026-10-10-creator-transport-current-observation.md` (exact main)
- This plan.

The three additional imported-main paths are already #1970's declared and
merged files; the consumer diff relative to actual main retains I1c's own
38-file declaration. Verify the combined full component set at its original
20-second bounds, TypeScript, exact staged ownership and committed docs_static.
Current Portal pages, diagrams, projected identities and source-facing facts
are byte-identical to the completed `f2593fd` Portal inputs; this internal
current-command repair restores existing semantics, so it adds no new Portal
fact or fresh full Portal build obligation. Record that comparison explicitly.
The I1c documentation-impact declaration remains required.

**Version impact:** no new identity allocation; retain the existing Creator
compatible MINOR debt, absorbing #1970's PATCH repair at Goal V1.
**Acceptance:** preserve the 65b complete failed run and original bounds.
After the Conventional integration commit and normal push of the same Draft
PR, run this consumer's own complete Creator lane when the parent's heavy-run
window is available. Audible BPM preview, open product choices, current-head
review, A1 visual comparison and A2 physical/hearing acceptance stay unfinished.

The combined staged source passed all 72 component files / 1,248 tests
(`npm --prefix apps/creator-web test -- --run`, 61.50 seconds including the
wrapper, 60.33 seconds reported by Vitest). TypeScript passed in 3.82 seconds;
the staged scope passed 77 ownership checks in 9.61 seconds. Source and test
hashes are retained with the staged-tree receipt in
`encoder-consumer-main-4dde8e5e` outside the worktree. The final plan-only
results update leaves those tested product inputs unchanged. Committed-head
docs_static and this consumer's complete Creator proof remain separate
verification boundaries; the earlier repair's receipt does not satisfy them.

### 2026-10-10 — expose device-volume restore readiness

**Premises:** PR #1936's authenticated exact-head review of
`367a14daa980e7106789d346023cdfb31837f0e9` found that musical controls can look
available while device-volume restoration is pending. Fresh main is
`785d36db27dc44fde7cceb4f6cb6da0956a795e1`; its changes after #1970 are
documentation reconciliation, not this consumer repair. The old session's
restore is already fenced by effect cleanup, but the current session's
`activateAudio` returns false until its preference arrives. Pad and transport
reachability omit that prerequisite and show no visible pending reason. This
remaining refusal is confirmed from the actual consumer source. Preserve the
original 367 complete Creator PASS and its seven browser groups as dated
evidence; it is not evidence for this subsequent repair.

**Declared files:**

- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/components/pad_surface.tsx`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- This plan.

**State boundaries:** show a visible and accessible `Restoring output volume…`
status. Pad, Play/Record and keyboard/pointer input share the current Runtime
session's monitor-readiness prerequisite. Temporarily disable musical Pad
input; other page and authoring controls retain their existing reachability.
Keep the Runtime's actual phase, restore-before-first-audio, bounded storage
fallback, remembered zero volume and stale-session cleanup. Do not queue or
replay a gesture after its browser activation window has expired.

**Lowest-tier verification:** a mounted App regression delays actual
IndexedDB read-success delivery after storing a device preference. While its
Runtime/Project are ready, pending status and musical disabled state must be
observable and a keyboard gesture must not activate or trigger audio. Release
the same session's read, verify restored zero, restored input reachability and
a positive musical input through the existing running-audio component seam.
A replacement-session case releases the old read first and verifies that it
cannot set the replacement's volume or clear its pending state. Record an
actual RED failure on unchanged product source before the fix, then GREEN;
keep the original case bounds. Run affected components, TypeScript, staged
ownership, Portal and fresh committed-head selected Creator evidence when the
coordinated resource window allows them. No old pass key satisfies the new
head's verification or authenticated review.

**Version Management:** compatible Creator PATCH repair absorbed by the
existing I1c MINOR debt at V1; no manifest or Product Build allocation.
**Documentation impact: required** — `/hosts/creator-web/`; document the
visible restoration/input boundary. The existing input diagram does not
describe this Host preference read, so no new diagram is required. Audible
BPM, D03/D04, S1 and A1/A2/V1 remain incomplete.

The mounted deferred-IndexedDB regressions first fail on the unchanged 367
product: the first case reports `disabled` false instead of true at
`workspace_shell.test.tsx:4317`, and the replacement case cannot find the
restore status. The first fixed-source attempt passes replacement but fails
the other case's mistaken `Play` locator; retain that fixture failure. Correct
the name to the existing `Play/Stop`, restore only the two owned old product
blobs, and rerun the corrected test: actual RED exit 1 (1.96 s). Restore the
fixed source with fresh mtimes; the identical corrected test then passes both
cases (1.98 s). The other 124 cases are unselected by this reduced command,
not a full component result. Receipts, source/test hashes and all logs remain
in `consumer-monitor-readiness-repair` outside the worktree. The deferred
events belong to actual stored `monitor-volume.v1` read requests, not a mock
preference function. The positive musical admission uses the existing running
component seam; it does not establish browser-trusted activation or hearing.
TypeScript first reports TS2683 for the new IndexedDB spy's untyped `this`.
Add only the erased `this: IDBObjectStore` annotation; TypeScript then passes
(1.73 s), and both reduced regressions pass again (2.40 s). Keep the original
type failure and the final test hash alongside the earlier RED/GREEN receipts.
The repaired input passes all 72 Creator component/helper files and 1,250
cases (53.56 s wrapper / 53.18 s Vitest) at the original 20-second case bounds.
All five declared input hashes remain unchanged during that run. Portal also
passes all 176 checks, current page/diagram validation and the 50-route build
with internal links (52.33 s); its source guards remain unchanged. The final
I1c declaration contains 39 unique paths, of which 38 change in the actual PR
merge-base range. This five-file repair preserves the earlier 367 complete
Creator result as dated evidence and allocates no identity. The final
results-only plan update does not change tested product, test or Portal page
inputs. Staged ownership, committed docs_static, this repair's fresh complete
Creator and authenticated current-head review remain separate boundaries.

## P0 — ship this bounded plan

**Declared files:** only `docs/plans/2026-10-09-creator-desktop-final-followup.md`。

**Lowest-tier verification:** 检查相对链接与 declared files；新增文件 stage 后运行
`python3 tests/build/ci_change_scope_test.py`；运行实际选择的 docs_static；
PR body lint 与 declaration-only 检查。本 Task 不改变产品事实或 Portal 页面，
不新增产品测试或 required gate。

## R1 — latest projection after consecutive authoring commits (#1905)

**Behaviour:** 连续 authoring 操作按 tail 顺序提交，后一次投影不能被 render ref
滞后丢弃。每次请求仍使用正确 expectedRevision，Project 切换后的旧结果仍被
拒绝；不放宽 reducer 的跨 Project/Pattern/token 身份保护。成功提交后的
刷新失败沿用现有 error/current 清空策略，authoring tail 保留已提交 revision，
不能重发已提交操作；本 Task 不改变失败投影的契约。

**Declared files:**

- `apps/creator-web/src/app.tsx`；
- `apps/creator-web/test/workspace_shell.test.tsx`；
- 若 reducer 复现需要，`apps/creator-web/test/creator_state.test.ts`，不预先改 reducer；
- `apps/docs-site/docs/hosts/creator-web.mdx`；
- 本计划（更新 R1 状态及验证证据）。

**Lowest-tier verification:** App component 测试先显示 red：两个同步进入 tail 的
颜色操作都已提交后，Pad 呈现第二个颜色；另外两种不同操作（例如 grid edit
和 Pad colour）连续执行后同时呈现最新事件和颜色。保留当前 stale token/
Project 切换拒绝测试。断言分别检查请求 revision、fixture Truth 和最终 UI，
不能只检查两个请求都成功。修复后这些检查通过，revert/mutation 证明失败
确实落在新显示断言。再执行 Creator unit/typecheck、Portal check，以及最终
committed head 实际选择的 batch-only creator lane。

**Documentation:** `/hosts/creator-web/` 描述成功 authoring 后投影刷新的一致性。
**Version:** Creator 修复至少欠 PATCH，纳入 V1；不在修复 Task 猜测身份。
**Pitfall:** 产品逻辑的回归测试是其出口；不为该逻辑错误新增流程 pitfall。

2026-10-09 R1 进度：两个同步颜色请求以 revision 3 → 4 → 5 成功提交，旧代码
仍画第一色（预期 `3`，实际 `2`）；颜色紧接 grid edit 的 fixture 使用真实
snake_case Project event 字段，旧代码同样在最终 UI 缺少音符的断言处失败。
恢复修复后，完整 Creator Vitest 67 files / 1,135 tests 与 `tsc --noEmit`
通过，现有 stale Project/Runtime 和失败清空投影测试继续通过；
`scripts/docs-site.sh check` 通过（50 routes）。修复仅让 grid、structure、
colour 三条成功路径先 dispatch 已提交 revision，再以该 revision 刷新；
settings 的现有显式 revision 刷新不变，reducer 不改。以上不代替最终提交头的
batch-only lane、当前头评审、实际 merge 或 A2 的人工验收。

2026-10-09 R1 完成证据：最终提交头
`3827b4614b50c20119d3438c2c511c5e3341d285` 的选中 Creator/docs_static lane
完整通过；Creator proof 包括两次干净产物一致性、1,135 单测及全部选中浏览器
分组，batch key 为
`efa97940870ca51b5be878429bf8588c96591008b15d43cd481ad790832acbcc`。
该 key 只证明 R1 当时的输入，不供后续 Creator 改动复用。自动评审
`37869819612/1` 因 service_error 未完成；独立会话审完完整四文件 diff 与验证，
无遗留 finding，owner 接管记录见
[#1907 comment](https://github.com/endaye/lmdj/pull/1907#issuecomment-6072499529)，
`review_wait.py` 确认有效后按 expected head squash merge，#1905 已关闭。
真实输入、听感和物理设备验收仍属于 A2。

## C0 — capability audit before product decisions

**Declared files:** only this plan.
**Lowest-tier verification:** 相对文件链接/声明范围核对、`git diff --check`、
实际选择的 docs_static、PR body lint 与 declaration-only；不新增产品测试或 gate。
**Version impact: none** — 只记录调查，未改变实现、Contract 或身份。
**Documentation impact: none** — 记录既有源码与决定供后续 Task 使用，不修改
Portal 或产品行为。以下建议均未获本次 owner 批准；不作为 I Task 实施授权。

Inspected revision: `0b333d3bd5c1a935a6c481551fb4d885abc78dc8`。
检查 Web Host 的完整 `bridge.cpp::supported_operation` 注册表，再读
`control_runtime.cpp` 实际 handler；以 `project.duplicate`、`sample.update_pad`、
`performance.fx.gesture` 这些已注册并实际分发的操作为正向控制。
同时检查 Runtime Session 方法、Creator consumer 和现有测试。
以下“无操作/投影”限定为本 revision 的 Web Host/Creator 公开路径，不表示所有
Core 内部均无相关算法。进入 I Task 前仍须刷新相关源码与继任交付。
以下 D2–D5 是该 revision 的历史调查；其中当时的待选择条目不覆盖后来批准的
旋钮决定、DUPLICATE，以及本计划上述 2026-10-10 BPM/D03/D04 决定。
尚未批准的补充设计继续保留，不能从已批准条目推导其产品语义。

### D2 — 400 ms 的已实现部分与未决定边界

- `apps/creator-web/src/state/encoder_input.ts::createEncoderTurn` 每格立即预览，
  最后一次输入后 400 ms 提交一次；回到起始值不提交；范围 clamp；前一请求
  尚未完成时从 requested value 继续。`cancel` 丢弃未提交 turn，`forget`
  在失败后忘记 requested value；两者不能撤回已经提交的 Truth。
- `app.tsx` 的 Tempo/Swing 范围分别为 40–240 BPM、50–75%。目前取消 effect
  绑定 `transportBusy || recording`；settings error 触发 `forget`。
  `selectMode`、`openSystem`、rail Undo/Redo 没有调用这两个 turn 的 `cancel`，
  encoder helper 也没有 Esc 监听。不能把 Sample slider 的取消机制当作 encoder
  已覆盖这些转移的证据。
- `test/encoder_input.test.ts` 七个案例覆盖合并、no-op、范围、取消、Truth 与
  in-flight 起点和失败回退；该 harness 手动触发 timer，不证明真实 400 ms
  边界，也不证明离页、Project 切换、Esc 或 Undo 集成行为。
- 待选择：是否保留 400 ms；离页/System/切 Project/失去所有权/卸载时对未提交
  preview 取消还是先提交；Undo/Redo 前先取消还是提交后再撤销；Esc 作用域。
  建议保留 400 ms，并对脱离目标的未提交 preview 取消；此建议尚未批准。
  已发出的请求仍须保留准确身份与真实结果，不得当作可取消的本地 preview。

### D3 — 已决定的 autosave / Duplicate，剩余是 D01 表达

[已确认的 workflow decision](../prd/decisions/2026-09-29-creator-user-workflow-baseline.md)
第 4 项已明确“全部自动保存，另存为即复制工程”，来自 #1652 →
`2abbb3fdaf718f1433b640ff954ce23d9664b31e`。#1684 已由 #1714 →
`206fcd571f60a0608fa3cded0e744b1e7ae1a84c` 交付；此处保留已有决定，不把
原 Desktop Final 的未渲染项解释为必须重新增加手动保存机制。

- Runtime `duplicateProject({sourceProjectId, projectId})` 经串行 Project action
  发送 `project.duplicate`，payload 严格为 `source_project_id, project_id`，
  无 sidecar；返回新身份、revision 0 的 summary。
- Host handler 调用 Facade `duplicate_project`；running、active Sequence 或
  Sample import 阻止复制；busy/unfinished-recording/identity/storage 拒绝由真实
  错误呈现。Host 只复制，不替换当前 Project、writer lease 或 Runtime。
  Creator `duplicateProjectJourney` 及 `app.tsx::duplicateProject` 随后单独打开
  副本并更新 remembered Project；打开失败仍保留、列出已复制的 Project。
- `project_overview.tsx` 已显示自动保存；`project_surface.tsx` 已有 Duplicate
  入口，D01 `hideSummary` 布局也渲染该入口。`project_create.test.tsx` 包含新身份、
  记住副本、拒绝、复制已存但 summary 无效、打开失败、旧 Runtime 拒绝等案例。
  Web Host 完整注册表没有独立 `project.save` / `project.save_as`；不能用
  `performance.save`（另一对象的操作）代替。
- 待确认仅是 D01 是否保持 Duplicate 名称/位置，或把相同已交付动作标作 Save As。
  若 owner 想引入手动保存、改名或导出，须明确改变既有语义并独立设计所需接口；
  不凭图添加“未保存”提示。现有自动保存/复制无需重复实现。

### D4 — Sample 的可复用编辑与新 Assign 的界线

- `sample_surface.tsx::runImportJourney` 统一文件/录音字节采用流程；已有 Pad
  替换确认、mutation 前 stop、expected revision、AbortSignal 和最终刷新。
  Slice/Candidate 的片段与明确目标选择是既有独立路径，不能据此推导一个
  未设计的新 Assign 按钮的对象与目标。
- Runtime `updatePad` → `sample.update_pad`，payload 为
  `command_id, expected_revision, slot, playback`，无 sidecar；Host 要求可用
  session，处理 mutation controls，Facade 检查 authoring admission、已分配
  Asset、音频边界与 expected revision，再执行持久化 `UpdatePadPlayback`。
  Preview 是 `sample.preview.set {slot, playback}`，清除是
  `sample.preview.clear {slot}`；两者不是 Truth 保存。
- `SampleControls` 已有 Volume −60…+6 dB / 0.1 dB、Pitch −24…+24 st / 0.1 st、
  Pan −100…100 / 1，以及 Attack、Release、Tone、EQ 等。Volume/Pitch/Pan 用
  `ParameterSlider` → `ValueSlider`；后者只有 range 与 output，没有通用数字
  输入框。它在 release/blur 提交，Esc/pointercancel 取消，不能静默改成 400 ms。
  `WaveformEditor` 已有 Start/End 秒数输入，步长 1/source sample rate，转换为
  frame；因此“细调编辑器完全缺失”不成立，须指定哪些参数、精度与入口仍缺。
- Host 已注册 `pad.assign`，严格 payload 为
  `command_id, expected_revision, slot, asset_id`（asset_id 可为 null），无
  sidecar；调用 Facade 并更新 Project revision。仅有此低层操作不等于 Creator
  已有素材浏览/选择/采用/Runtime 重建的完整 Assign journey。
- 待决定：Assign 是导入新文件、采用候选，还是将已保留 Asset 指向另一个 Pad；
  指定目标、替换确认与取消语义。细调需分别确定 Volume/Pitch/Pan 等是否可点数值
  输入、常规/SHIFT 步长；保留既有单位、边界、单次 commit、失败与 Undo 行为。
  audition golden PR #1904 当前仅是一文件计划，尚未合并；不重复其测试设计，
  也不把它视为已执行的音频验收。

### D5 — live controls 需要的 producer 工作

- `FxSliderBank` 已渲染 Filter/Delay，其他六种 FX 在 FX / MORE。
  Runtime type、Host validator、Facade handler 都使用八种 FX 的单一整数
  `value`（0…1000）；`performance.fx.gesture` payload 只有 `event`，无 sidecar。
  engage/move 是 `kind, fx, value`，release 是 `kind, fx`，hold 只有 `kind`。
  Facade 将其交给实际 master-bus gesture sink；无 sink 时失败。live gesture
  不写 journal，录音另经 `performance.record.event` 记录。
- `audio-runtime/src/master_fx.cpp::process_filter` 用同一 value 控制 LP/HP
  深度（500 bypass，小于 500 LP，大于 500 HP），coefficient/damping 从该值
  派生；没有独立的 type/cutoff/resonance 输入或 BP 输出选择。
  此算法不等价于 D04 的独立 LP/HP/BP + resonance 控件。
- 完整 Web Host 注册表、FX event validator 与 `runtime_types.d.ts` 不提供
  master gain、独立 filter 参数、live Pad Mute/Solo 操作。Sample 的 persisted
  `playback.muted` 已存在，但不等于 Perform live Mute/Solo 的状态与录制语义。
- `control_runtime.cpp::status` 提供 Project/Runtime/control generation、limits、
  audio/capture state 和 Pattern transport，没有输出 level 投影。
  `performance_master_tap_worklet.js` 的 PCM batch 只在 capture generation
  启动后发送给录音 sink，不能当作常驻电平接口；`PerformOverview` 没有电平读数。
  这些实际 producer 证明 Creator 尚无可直接绑定的输出 meter。
- 待决定：MASTER 作用于监听、录音、重采样的哪一段及是否持久化；滤波采用
  现有双向单值还是新增独立 type/cutoff/resonance；Mute/Solo 针对哪些 Pad，
  属于 Truth 还是 live session，是否进入录制/重放；meter 的测量点、单位和峰值
  保持。新增能力先做 Contract/Facade/audio/Web producer Task，再做 Creator
  consumer Task；不能用 Sample gain/mute 或合成电平代替这些决定。

## Decision and implementation Task contract (D1–D5 / I1–I5)

每个 D Task 在决定前核实真实源码与 dispatch/handler/payload/state 前提，
记录 inspected revision、已有能力、仍需实现和未确认部分。既有能力的正向
控制与实际 authoritative registration 必须先检查，再报告缺失。

Decision Task 声明自己的 `docs/prd/decisions/` 文件、decision-log/open-questions
更新、本计划，以及适用 Portal 页面；路径在该 Task 开始前锁定。决定之后，
在本计划追加实现 addendum，列出精确文件、最低层测试、每个状态/转移的
验收与影响。Core/Contract/Host producer 与 Creator consumer 有实际依赖时
分开 Task；未决定或未声明文件的 I Task 不进入实施。

## Acceptance (A1/A2)

**Declared evidence file:** `docs/quality/2026-10-09-creator-desktop-followup-acceptance.md`，
另加本计划；自动化发现的产品/测试问题使用独立修复 Task 声明文件。

四页分别覆盖正常、拒绝、失败、取消、Undo/Redo、reload/reopen。核对字体、
布局、缩放命中、键盘、控件状态与 Figma/decision；Figma fidelity 是实际
比较结果，不从功能测试推断。现有 journey 不删 leg、放宽阈值或伪造输入。
真实 Safari/iPad 输入、听感、辅助技术和生命周期分别记录；需要 owner 操作
时给出可执行步骤与预期结果，收到实际证据前保持未验收。

验收记录包含源码/Build/Host 身份（来自 manifests 或 report）、来源、设备、
浏览器、操作人/日期、逐 leg 观测和 report digest。未分配 Build 的源码验证
明确写源码 revision，不用旧 Build 证明新功能。V1 的 snapshot 不能倒推
此前人工验收绑定到新 Build；必要时在 V1 后复验身份敏感的验收。

### 2026-10-11 — MASTER/ENC4 局部真实浏览器观察（独立文档 Task）

Fresh main / isolated Task base 为
`82c010d0391b956f871d34ecb40720f9a7e0a8d7`。#2000 的 MASTER consumer 已合并，
无需重复实现。本 Task 将真实 native Chrome 观察登记到
[验收台账](../quality/2026-10-09-creator-desktop-followup-acceptance.md#2026-10-11--masterenc4-局部真实浏览器观察)：
实际 MASTER/ENC4 双向 UI 值同步、37% 跨页/System 保持，以及真实 Reload 在
Runtime ready 后恢复 37%。使用自身原 968 canonical 的 distribution；没有新
build，manifest 的既有 2.0.88.0 标签不消除 V1 版本债。原始 native 输入、AX、
截图、失败 SetValue、初始化读数及临时服务正常退出均保留。

**Task declared files:**

- `docs/quality/2026-10-09-creator-desktop-followup-acceptance.md`。
- 本计划。

**Premise dispositions:** MASTER 已交付，仅补局部观察；完整 A1/A2、人工听感、
录音/导出电平、Truth/Undo 语义、Safari/iPad 和 Figma 视觉仍未完成。本地无 Catalog
upstream，实际 16 个默认声音 NOT_FOUND，因此本 Task 不声称可听输出。
#2010 b62f 的原完整 Creator 已于 02:07 UTC 独立启动，结果另取真实终态；
#2012 的日常验证规则调整未产生 full PASS，也不把局部观察升级为完整四页、
最终来源或新 Build 证明。

**Lowest-tier verification:** 对照冻结报告逐 leg 检查两文件事实、长度与 digest；
检查完整 diff 与 Markdown/链接、两文件 ownership，运行 PR body lint 与
declaration-only check，再由独立 reviewer 审完整 Task。没有新产品测试、阈值或
gate；原完整 Creator、音频与设备验收另行完成。

**Version Management:** Version impact: none — 只登记既有来源的部分 UI 观察，
不更改 manifest、Contract、Build 或 version consumers。
**Documentation impact: none** — 仅计划与验收台账，Portal 产品事实/页面/图未变。
**Pitfall impact: none** — 遵循既有逐 leg、真实输入和来源边界，没有新的流程机制。
本 Task 不启动 Release/部署，不授权或执行额外缓存、worktree 或分支清理。

## Version Management

Version impact: none — P0 仅建立计划，不修改 active manifest、Build 或 Contract。

实现 Task 各自记录 PATCH/MINOR/Contract 兼容性，V1 按最终实际影响协调结算。
原计划已记载 Creator 及相关 Core/Web 模块的版本债务；读取现行 manifest 和
继任版本提交后再确定剩余债务，不手填旧版本或预分配号码。

V1 在执行前声明确切 manifests、消费者、测试、Build/Channel 与 snapshot 文件。
Product Build/Assembly 改动同步更新当前 Portal、生成不可变 snapshot，合并后
验证实际 introducing SHA 的 provenance；必要 witness 走官方 generator 的
独立后续 Task。此过程不启动 Release 或部署。

## Documentation Impact

Documentation impact: none
Reason: P0 只记录计划与进度，不修改 Architecture Portal 或宣称新产品事实。
R1 和各实现 Task 按实际影响更新 Portal；Build/Assembly Task 必须 required。

## Verification and completion

每个 Task 先证实原因和当前前提，再跑最低层测试。stage 仅声明文件，确认非
main、ownership、cached diff check，创建 Conventional Commit；在 clean committed
head 分类，执行所有实际选择的 batch-only lane，PR 记录 pass key。评审、修复、
最终 main/governance 刷新、完整 conversation/closing relation 和 expected-head
保护均按 issue-done。失败后端/旧 head/过期证据不是独立评审。

本 Goal 的每项范围均完成决定、实现、验证、合并和适用验收，或者经 owner
明确取消/移出后，才可结束。保留最终 PR/SHA、验证/人工证据、版本/snapshot
状态、清理结果与范围处置；等待、额度、PR 创建或一段 green journey 不表示完成。

## Pitfall Impact

Pitfall impact: none — P0 规划不引入新流程知识。执行中按 Task area 查阅 pitfall，
特别保留共享构建目录、环境相关性归因及真实输入完成证据的既有要求。


## I1d — ordinary Creator proof inspections share the owned Session lane

### Refreshed premises and bounded authority (2026-10-10)

- Isolated Task base and freshly fetched `origin/main`:
  `fb58ee897146c3e73426c3ba0b7cb66f69566a8f`, branch
  `fix/creator-owned-inspection`. No implementation was already present:
  the retained packaged Host exposes frozen `candidates` / `providers`, but
  has no `inspection` namespace; ordinary Creator Truth and Sample helpers
  still send raw requests outside the existing RuntimeSession request tail.
- #1936 is actually merged as `9b4d80c9e5ed965f5776c0321cf166d9d1f289ce`
  with frozen source head `4a76182c6b5dfbe7f7d4b6229dbcf538eb3e0410`.
  Its original complete Creator result remains 109 pass / 5 fail / 11 skip;
  the new diagnostic does not replace it or produce a Creator pass key.
- #1985 is actually merged as `da7da98ff27db8fa4c4e885631f0e4472faa64e0`.
  Its stopped/playing Pattern transport producer and tests are already on
  this base. This Task leaves those handlers, ownership and deadlines intact.
- The one instrumented original 90-case Chromium group retained all 15 specs,
  2 workers, journeys and budgets and finished 78 pass / 11 fail / 1 skip.
  Six strict accepted/deadline/terminal identities first expired in 1000 ms
  Recovery queries. The first native instance is linked to the resize
  activation helper by its actual successful raw Sample response UUID,
  `edfee179-711d-4871-9ed9-458c29b91c5a`; that raw Sample request overlapped
  `sequence.recovery.list` request `14f53672-1484-47b2-9614-bf371e2663d8`.
  The actual native dispatch/IO wait phase and original five root causes
  remain unknown. CDP observer effects and all coverage gaps are retained.
- Remaining behavior: expose the already-owned read methods through the
  ordinary packaged Host namespace and use them for normal proof reads,
  so those reads participate in the Creator Session's existing request tail.
  No second Session, private getter, raw fallback or fabricated response
  envelope. The methods keep current safety-query cancellation/retry,
  validation and typed failures; explicitly closing/closed owners refuse
  inspection before sending even when an injected transport would still
  accept it. Fatal cleanup preserves the native transport's retained
  `HOST_TIMEOUT` / `HOST_PROTOCOL_MISMATCH`, rather than recasting it as a
  closed-owner refusal; pre-start and recovery admission is unchanged.
- All ten tracked symlinks are real symlinks with existing targets. At Task
  start, dependency installation and verification had not run in this new
  worktree; their actual results are recorded below.

### Declared files (exactly eight)

- `packages/web-runtime-platform/web/runtime_session.mjs`
- `packages/web-runtime-platform/test/runtime_session.test.mjs`
- `tests/platform/web/creator/fixtures/creator_audio.mjs`
- `tests/platform/web/creator/creator_web_hardware_layout.spec.mjs`
- `tests/platform/web/creator/creator_web_perform.spec.mjs`
- `tests/platform/web/creator/creator_web_sequence.spec.mjs`
- `apps/docs-site/docs/platform/web-runtime.mdx`
- `docs/plans/2026-10-09-creator-desktop-final-followup.md`

### Behavior and minimum verification

The retained Host exposes frozen
`inspection: {inspectProject, inspectSample}` as the same Session closures,
without changing the raw transport. Project inspection returns the existing
complete Facade result. Sample inspection accepts a flat slot 0–63 and returns
validated fields including `slot`, `projectRevision`, `assetId`, `playback`
with `triggerMode`, `pan` and `tone`, metadata and waveform cache identity.
Ordinary helpers assert those actual fields; they do not invent `ok`/`result`
wrappers. Musical activation keeps the real trusted Pad input and accepted
trigger/voice far-side. Trigger, Stop, failure injection, old-owner and native
concurrency witnesses keep their original raw interfaces.

Lowest-tier tests: extend the original Node RuntimeSession suite with a
published namespace fixture and deferred real transport. A held inspection
must prevent a same-Session ordinary Recovery query from sending early;
release must observe both correct results, max one in flight and exact
1000/30000 ms options. Full Project Truth and normalized Sample slot/playback
must remain observable. Closed retained namespace methods must reject with
`HOST_STATE_INVALID` and produce no new transport send, both while native
close is pending and after a replacement publishes its own namespace. Fatal
cleanup tests preserve each retained native timeout/protocol error. Existing
namespace, Sample cancellation/retry and lifecycle tests remain selected. The
actual full-suite and discriminating mutation outcomes are recorded below.

The original five browser journeys remain whole, including every far-side:

| Journey | Required transitions and observations retained |
| --- | --- |
| Overview / hardware447 | Four modes × three viewports, read-only fit/screenshots → held Sample inspect LOADING → release settles SAMPLE → failure keeps complete Truth → recovery → delete EMPTY → Undo restores Sample/Pad → System/Details identity → Back → reload/reopen exact Project identity. |
| Stop Replay / perform1551 | Record and save → replay playing → Stop Replay stopped/neutral → neutral FX, HOLD and Pattern state from real projections. |
| Hard-left Pan / perform1595 | Activate → real witness import → Sample Pan change and complete Truth → Perform record/stop → master PCM with right-channel silence; no capture/sink substitution. |
| Tempo/Swing / sequence710 | Original continuous commit, cancellation, honest refusal, recording locks and Stop/reload/persisted Truth; no loss of failed or cancelled legs. |
| Sequence encoders / sequence931 | Rows, Tempo single commit, cancelled turn, device monitor volume without Project mutation, stopped Pattern navigation and original Play/Record ownership boundaries. |

Use the unchanged Task-relevant Node suite first, then committed-source
ownership/types/docs-static and `scripts/docs-site.sh check` as applicable;
final browser validation retains the original group configuration and all
journey legs. Do not widen a 1000/30000 ms Host budget or Playwright budget,
change lane selection, skip cases or treat a filtered pass as the full proof.
This Task removes the proved outside-tail inspection path; it does not by
itself close the original five failures, Overview/Replay uncertainty, A1/A2
or the overall Goal.

### Version Management

Version impact: Web Runtime Platform MINOR debt — additive ordinary public
inspection namespace and explicit closed-owner read admission. V1 settles
this actual merged delivery alongside the final Goal scope, using current
manifests and canonical generators. No version number, Product Build,
Assembly identity, snapshot, tag, release or deployment is allocated here.

### Documentation Impact

Documentation impact: required
Affected portal route: `/platform/web-runtime`.
Describe the same-owned Session namespace, validated shapes, queue, typed
closed-owner rejection and the boundary between ordinary queries and explicit
raw transport proofs. Do not present this Task or the instrumented diagnostic
as complete Creator/Goal or hardware acceptance.

### Verification state

Actual pre-commit verification on the eight-file Task draft based on
`fb58ee897146c3e73426c3ba0b7cb66f69566a8f`:

- Refreshed `origin/main` before commit preparation remains the same base;
  the inspection namespace and ordinary helper migration are still absent
  there. Independent draft2 source review covered all eight files and
  preserved the normalized shapes, raw witnesses and fatal error boundary.
- Node 26.8.1 ran the original RuntimeSession suite: baseline 161/161 PASS.
  Replacing only Sample inspection's owned `recoverableQuery` with the
  same-budget `dispatchBoundedRequest` produced an actual assertion RED at
  `runtime_session.test.mjs:6163`: Recovery and Project requests sent while
  the Sample gate was held. Fresh source restoration and a new Node process
  passed that same queue case. Removing only the normal close admission guard
  produced an actual `Missing expected rejection` RED at line 6212 for the
  retained old Project inspection closure. Fresh restoration then passed
  the original suite again, 161/161, including both native fatal causes.
  Neither RED was cancellation, a hang, missing namespace or syntax failure.
- The five-phase external runner actually exited 0 in 7.163092 seconds.
  All 49 input guards and the exact eight-file scope passed. SDK source
  restored to SHA-256
  `7907ee1b3f0b951372104cf75ad47dc8057c5e4ce604cf815d86b249dbf8aaf3`
  with a strictly fresh mtime. Each child terminal preceded post-guard and
  assertion classification. Retained Node execution receipt:
  `creator-owned-inspection-preparation/node-validation-execution-20261010T142059Z-8992db88/final-receipt.json`,
  SHA-256
  `af8526b32c40a3f0f084571a7627d0017cbc4758818c9065f4c52e8a68a75017`.
- Locked clean installation used Node 26.8.1 and the Portal's declared
  npm 10.9.3: canonical `scripts/docs-site.sh install`, Creator `npm ci`,
  and Web tests `npm ci` each actually exited 0. No old `node_modules` was
  copied, and all six package/lock inputs stayed byte-identical.
- Canonical `scripts/docs-site.sh check` actually exited 0 after its complete
  cold build in 160.367616 seconds: 176/176 tests, 52 pages, 10 diagram
  sources / 20 outputs, snapshot validation, typecheck, changelogs, production
  build and 50 routes / internal links. Retained verification terminal:
  `creator-owned-inspection-preparation/precommit-verification-20261010T142439Z-9c28b44b/terminal.json`,
  SHA-256
  `13e1bc6e0c66c2946cca942bb0f220da96bc832ae90ad3c069c9d9a6142b912e`.
- All six changed MJS files passed Node syntax checking. After staging exactly
  the eight declared files, `python3 tests/build/ci_change_scope_test.py`
  actually passed 77/77 in 10.713 seconds, including tracked-path ownership.
  No added files or undeclared paths were present; cached whitespace checks
  passed. Relevant open dependency, toolchain and Web proof pitfalls were
  read. This queue/owner defect is expressed by its behavioral regressions,
  so it introduces no separate process-pitfall entry.

No complete Web batch has run for this Task yet. The three selected batch-only
lanes (`creator`, `web_runtime_host`, `web_toolchain`) must run on the final
committed source; no earlier input's pass key is reused. The original five
browser failures, Overview/Replay uncertainty and A1/A2 remain open. No push,
PR, version allocation, tag, release, deployment or hardware acceptance has
occurred for I1d.


## N13 — 2026-10-12 actual SOURCE integration addendum

### Selected source, owner and premise dispositions

This is the actual initial SOURCE phase, dispatched by Root under Run
`run_caa371bb58ee`, Task `task_741b77b7f15a`, Dispatch `ctx_c96a4aee61e7`.
Worker terminal: `term_a90d95a5-8c22-4d84-ba2b-5703bb6aff7f`; coordinator:
`term_aa87d468-5319-4aef-9fe4-9d8c916dc810`. Own isolated worktree:
`/Users/endaye/orca/workspaces/lmdj/feat-creator-sample-numeric-main`, UID501.
Root's fresh local and ls-remote observation at 2026-10-12T01:49:53Z selects
protected main `02b7445ff035e48c43ea2a66c858f7c9282e6c79`, tree
`627ed86348f4641506ba14f0e15a8f6c4368548b`, sole parent
`59da4245ff659ee1ffa2b9cf8e81f44bbc65a196`. Own actual HEAD/tree/parent
match that selection; starting worktree is clean. Only the newly created own
branch was renamed from Orca's `endaye/feat-creator-sample-numeric-main` to
`feat/creator-sample-numeric-main`; no upstream existed or needed unsetting.
No Root main, foreign worktree, index or remote ref was updated.

Approved behavior comes from the current D03 decision
`docs/prd/decisions/2026-10-10-sample-assign-and-numeric-editing.md`; the
historical C0 undecided investigation does not reopen it. At selected main,
all six displayed values still use ParameterSlider/ValueSlider output without
a precise entry, and all five new feature paths are absent. This remains the
outstanding consumer behavior. Existing Sample preview/update/inspection,
Start/End frame input, touch gestures, rotary 400 ms/SHIFT rules, single
current-Pad selection, MASTER/ENC4 and SEQ SNAP are already delivered and
retained. No Assign producer dependency, Contract or DSP change is introduced.
The four modified production component bases are byte-equal old e220 to this
selected 02b. The old Portal is not copied; current main is its base.

Root supplied bounded fresh Run/Task and OPEN PR captures: no matching N13
active Dispatch or PR existed, and #1995 remained OPEN. This is supplied
launch ownership evidence, not a whole-machine worker census. K1 remains
frozen at `124110eb0476122963d2e959530dd5d7af67fc4c` with its own 24 files;
N13 is Root's sole newly admitted SOURCE writer for workspace_shell, both
Host Portal pages and this followup plan. N13 starts from 02b before K1
integration, imports no unmerged K1 source and claims none of its acceptance.
Root must sequence integration and review combined retention on those four
paths and the original browser journeys before N13 shipping.

### Exact declared files (13)

1. `apps/creator-web/src/components/parameter_slider.tsx`
2. `apps/creator-web/src/components/sample_controls.tsx`
3. `apps/creator-web/src/components/sample_parameter_editor.css`
4. `apps/creator-web/src/components/sample_parameter_editor.tsx`
5. `apps/creator-web/src/components/sample_surface.tsx`
6. `apps/creator-web/src/components/value_slider.tsx`
7. `apps/creator-web/test/sample_numeric_editor.test.tsx`
8. `apps/creator-web/test/workspace_shell.test.tsx`
9. `tests/platform/web/creator/creator_web_sample_numeric_editor.spec.mjs`
10. `apps/docs-site/docs/hosts/creator-web.mdx`
11. `apps/docs-site/docs/hosts/creator-interactions.mdx`
12. `docs/plans/2026-10-10-creator-sample-numeric-editor.md`
13. `docs/plans/2026-10-09-creator-desktop-final-followup.md`

No App/state/encoder/SDK/Assign/bridge/Core/DSP, generic modal, global CSS,
manifest/lock, wrapper/config/fixture or pitfall edit is included. No cosmetic
path-count edit is needed: each declared path owns feature, regression source
or required documentation. Existing App cancellation/history hooks provide
the numeric consumer boundary; no static scope/API contradiction was found
in the manual source review. Type/compiler compatibility remains UNRUN.

### Draft custody and source obligations

The read-only retained draft stays at
`/Users/endaye/Projects/lmdj-wt-creator-sample-numeric-editor`, branch
`feat/creator-sample-numeric-editor`, HEAD
`e220c98ca1b0f4a3c08646bfeb328ffa186a263d`. Its eleven staged originals and
working bytes, zero unstaged delta, binary index (417958 B SHA256
`9cf60484224a94761d749a286851bb2a2247e334f4928116a23521890be59482`),
full cached binary patch (84803 B SHA256
`41a2fd2113802b8efc350da61a0412f74d67d103e30fcacbf6635d4798e823ff`)
and complete five-entry shared stash list are guarded before/after externally.
No stash was created/applied/popped/dropped and no old lifecycle was resumed.
The four numeric stash OIDs remain
`67c780cf389e6797b1b9460bcfb1fca5dd4b234b`,
`6f7fdf05b467db21cf48ad40a6af592e5f528419`,
`a2b55113f4e30f1ee6fd6bc367fdd1b3bd2eb1de`,
`efa779f45ac4026da7df0a593d0af9d3cbab64fd`; the unrelated fifth entry is kept.
The numeric plan's full historical 25715 B SHA256
`dec728b6857176a8bf557fc91d058b69810071e7ecb268fbc59580ba4a065878`
is a byte-preserved prefix. All old results and negative/UNRUN boundaries
remain historical, not a fresh-head PASS.

The six-field saved-playback editor retains Volume -60..6 dB/0.1/1000,
Pitch -24..24 st/0.1/100, Pan -100..100/1/1, Attack 0..2000 ms/1/1,
Release 0..4000 ms/1/1 (one-shot disabled), Tone -100..100/1/1 with LP/HP
and -2..2 Off. The audio envelope's 2 ms floor does not change stored 0 ms.
Existing ModalDialog supplies labels, focus/return focus, inert background,
Escape and focus trap. Value button/input/actions have 44 px targets; range
keeps its single associated label and default ValueSlider consumers.

Legal step-aligned input immediately previews through the existing owned
Sample journey; invalid replacement clears its previous audition and permits
correction. Apply/Enter settles once, no-op/returned values do not author,
and pause/blur never save precise input. Render-time captured context guards
refuse queued preview/submit before passive cleanup. Target/context/page/
subpage/System/unmount retirement cancels only UNSENT numeric draft/audition;
SampleSurface uses existing contextual pending/cancel registration and App
history hook. Already-sent updates retain actual known commit, publication
failure, conflict or unknown response through existing actions/projection;
no new command identity, retry or cancellation of a dispatched save is added.
Native text Undo remains owned by editable input; modal background pointer
routes are inaccessible, and no in-dialog Project Undo shortcut is invented.

### Owning test source and later verification proposal — all UNRUN

| Full owning selection | Defect fixed by its assertions |
| --- | --- |
| `test/sample_numeric_editor.test.tsx` | Six scales/bounds, Apply/Enter once, no-op/invalid/no pause/blur, focus/cancel/one-shot/keyboard isolation, saved-base input, pre-effect queued stale submit and preview, Surface revision-fenced update/refresh/refusal and late preview cancellation. Complete retained test source plus one queued-preview case. |
| `test/sample_controls.test.tsx` and `test/value_slider.test.tsx` | Complete unchanged conditional controls, units/readouts/labels/focus/44 px and original range release/key/blur/Esc/pointercancel semantics. |
| `test/sample_encoder.test.ts` | Complete unchanged rotary step/clamp/shared 400 ms lifecycle; explicit numeric confirmation cannot become rotary autosave. |
| `test/sample_actions.test.ts` | Complete unchanged request normalization, known commit/publication failure/conflict/no automatic retry and authoritative inspection. |
| `test/workspace_shell.test.tsx` | Complete original file retained as prefix; mounted actual App preview acceptance then page/subpage/Pad/System/blur, Runtime restart and controlled Project/App replacement, old-owner clear and saved playback restoration, late preview/retired submit cannot revive, input text Undo separate from controller history clear-before-Undo, already-sent late published/publication-failed/conflict/unknown response survives page retirement/remount. |

The mounted forced background events are explicitly handler witnesses, not
native modal pointer reachability. Retired DOM submits prove post-retirement
ownership; retained component layout-effect cases separately cover the
pre-passive-cleanup interleave. Controlled different-Project replacement
uses two real App mounts with their own states/Sessions. Unknown-receipt
fixtures prove consumer error/no resend, not absence of a native commit.
Each transition has its own far-side assertion before the next transition.
No new runner, fixture framework, required gate, timeout or coverage reduction.

After Root separately grants concrete execution, propose from
`apps/creator-web` with the existing locked toolchain:

```text
node node_modules/vitest/vitest.mjs run test/sample_numeric_editor.test.tsx test/sample_controls.test.tsx test/value_slider.test.tsx test/sample_encoder.test.ts test/sample_actions.test.ts test/workspace_shell.test.tsx --maxWorkers=1
node node_modules/typescript/bin/tsc --noEmit
```

Dependency install, if needed in this skipped-hook worktree, requires separate
admission. Later Portal check remains `scripts/docs-site.sh check`. Later full
Creator verification remains the complete original `scripts/creator-web.sh proof`
with all eight groups: chromium, catalog-chromium, sample-chromium, webkit,
capture-chromium, capture-denied-chromium, sample-webkit, deployment-chromium.
Source-only untracked discovery/staging, committed-source binding and shipping
mechanics belong to later admission; no commit is made merely for discovery.

The complete retained 253-line packaged numeric case is byte-reused, including
original native forwarding/identity, immediate preview, invalid refusal, >400 ms
pause with no save, one Apply command/revision/Undo increment, Escape no save,
actual Undo and Redo, and full saved playback/Truth/history after persisted
reopen. Original import/quota/parity/tone/history/Delete/encoder/monitor journeys,
all budgets and far-side assertions are unchanged on this base. Native refusal
and manufactured-response seams retain their separate labels. Dedicated Sample
WebKit selection is its existing capability boundary, not proof this new
Chromium numeric journey ran on native WebKit. Automation does not establish
physical touch/MIDI/assistive technology, hearing, deployment or release.

## Version Management

Version impact: compatible Creator MINOR debt joins approved followup V1.
No Product Build, manifest/lock identity, allocation, tag or release is made;
final SemVer/Build values remain V1's separately admitted settlement. Existing
version debt is retained. No Contract or source-diagram topology change.

## Documentation Impact

Documentation impact: required
Affected portal pages: `/hosts/creator-web`, `/hosts/creator-interactions`.
Reason: six-field precise numeric entry and its distinct preview/save/cancel/
history boundaries are new current source facts. Sample 4.1/4.3/4.4,
source/test mapping and pending evidence reflect this subset. Current Portal
base, MASTER/SEQ SNAP, one-current-Pad and existing touch/rotary/K1 facts are
retained; Assign/BPM/D04/A1/A2/V1 still need their own delivery and acceptance.
Portal check is required in a later admitted phase, and remains UNRUN here.

### Observable SOURCE-ready handoff and HOLD

Source preparation accounts for all thirteen candidate paths and supplies the
missing mounted App test source. External evidence directory:
`/Users/endaye/Projects/lmdj-followup-evidence/2026-10-12-n13-source-task_741b77b7f15a/`.
It binds actual base/branch/UID/instructions, final file lengths/SHA256 and Git
blob IDs, complete binary diff including new-file bytes, finite status, plan
prefixes, preserved unchanged owning inputs and old before/after guards; the
source report maps behavior and test/documentation obligations to file/line.
Root must receive/freeze these actual bytes before deciding verification.

This is SOURCE-ready, not Task-complete or acceptance. All npm/Node/AST/
compiler/syntax/type/component/native/browser/Portal/proof/emulator/physical/
hearing/profile/install execution stays HOLD/UNRUN. No staging/commit/push/PR/
merge/GitHub mutation, Orca scheduling, Goal status change, cleanup or release
is authorized or performed. D03 native, Linux coverage and Mac evidence have
separate owners; their finish does not release this HOLD. Root receives one
blocking source-candidate/report/next-verification question; Task stays ACTIVE
and no succeeded worker_done is sent for unvalidated Source. Later verification,
combined K1 retention, shipping, A1/A2/V1/Goal and release remain separate.

## 2026-10-12 N13 Source repair addendum — 14 declared files, validation HOLD

This addendum supersedes the preceding initial13 Source scope and its broad
sent-result retention claim for the current candidate. It does not rewrite
historical outcomes. Independent Source review found a concrete P2: selected
main's SampleSurface Session-change effect erased operationPending and
reported operation-cancelled after updatePad was already invoked; the late
update journey then dropped a known committed/publication-failed result.
The initial mounted sent-result cases retired only the page, while Session
cases covered UNSENT drafts. Those cases did not establish sent Session
retention. The original13 candidate/report/full patch remain frozen externally.

Root approved Source repair in msg_882ba54fd407 and exactly one added path,
apps/creator-web/src/app.tsx, in msg_8583c5db6d2c. Task
`task_741b77b7f15a`, dispatch `ctx_c96a4aee61e7`, Run
`run_caa371bb58ee` and the same owned isolated worktree/branch remain ACTIVE.
Selected base is still HEAD `02b7445ff035e48c43ea2a66c858f7c9282e6c79`,
tree `627ed86348f4641506ba14f0e15a8f6c4368548b`, sole parent
`59da4245ff659ee1ffa2b9cf8e81f44bbc65a196`, branch
`feat/creator-sample-numeric-main`, UID501, no upstream. No main/ref update,
foreign process action, original draft/stash/index mutation or Goal change
is authorized by this Source repair.

### Exact revised declared source scope

1. `apps/creator-web/src/components/parameter_slider.tsx`
2. `apps/creator-web/src/components/sample_controls.tsx`
3. `apps/creator-web/src/components/sample_parameter_editor.css`
4. `apps/creator-web/src/components/sample_parameter_editor.tsx`
5. `apps/creator-web/src/components/sample_surface.tsx`
6. `apps/creator-web/src/components/value_slider.tsx`
7. `apps/creator-web/test/sample_numeric_editor.test.tsx`
8. `apps/creator-web/test/workspace_shell.test.tsx`
9. `tests/platform/web/creator/creator_web_sample_numeric_editor.spec.mjs`
10. `apps/docs-site/docs/hosts/creator-web.mdx`
11. `apps/docs-site/docs/hosts/creator-interactions.mdx`
12. `docs/plans/2026-10-10-creator-sample-numeric-editor.md`
13. `docs/plans/2026-10-09-creator-desktop-final-followup.md`
14. `apps/creator-web/src/app.tsx`

App is necessary because it unmounted SampleSurface on page retirement,
blocked even automatic same-Project recovery open on a pending update, and
its existing project-ready reducer reinitializes Sample pending/selection.
The added optional Surface callback carries consumer update ownership with
original Project, pending kind/slot/revision and source Session. It is not
proof of actual wire-send. One existing Surface stays mounted hidden while
that journey, receipt or projection is genuinely in flight; Capture and
Sequence conditions remain. Ordinary selector/create/import/new-Project and
history pending protection continue, including the transient reducer reset.
Only automatic open with requireSelector=false, the same Project, a different
Session and the specific original update pending receives the recovery
exception. No new App shortcut/history contract or second Surface is added.

Surface distinguishes an UNSENT preparation from the invoked update journey,
retains the original operation identity and result across Session replacement,
and restores its pending before the existing default selection effect after
same-Project reopen. It resumes readback/projection without an authoring
resend or fresh durable command identity. Successful/failure settlement keeps
ownership until the existing reducer/projection far side. A changed Project
fences the old result instead of projecting it into the new target; the
existing reducer handles a changed current Pad without installing the old
Pad's playback. A queued pre-mutation stop completion checks current Session
and Project before invoking an update. Native unknown receipt is not called
cancelled or inferred to mean no commit. Generic state/reducer/SDK/Modal,
encoder/Assign/Core/DSP/global CSS/wrapper/tool pins remain outside the edits.

All approved six numeric fields/scales/bounds, saved-base editing, immediate
legal preview, invalid clearing/correction, one Apply/Enter, no-op/no pause/
blur save, context/late-preview/queued-submit cancellation and input text Undo
remain. Original ranges, shared rotary400ms/SHIFT, ENC4 monitoring, exact
Sample selection and the complete253-line numeric browser source remain.

### Owning regression source and later checks — UNRUN

The entire original workspace file and first13 Source tests remain preserved
as prefixes. Five new mounted App cases use existing mutable Sample storage,
real App handlers and the actual RuntimeProvider restart-required route.
Four cover published/publication failure/conflict/unknown; the fifth saves
Pad A02 and verifies its result cannot become current Pad A01 playback.
Each observes exactly one original update, a post-authoring old-consumer
readback/clear boundary, real page retirement into Project, actual successor
open/reload of the same Project, ordinary Project-action refusal while owned,
no successor update/preview clear, and the final honest result/playback/Truth.
Known results additionally hold the successor projection and assert ownership
is not released merely on receipt arrival. Every transition has a far-side
assertion before the next one. Manufactured response/shared-storage seams do
not prove native Session/commit interleaving; that remains UNRUN. Unchanged
mock storage does not prove an unknown native request never committed.

Complete later light commands remain exactly the six whole owning files and
full tsc, from apps/creator-web, after separate Root GO:

```text
node node_modules/vitest/vitest.mjs run test/sample_numeric_editor.test.tsx test/sample_controls.test.tsx test/value_slider.test.tsx test/sample_encoder.test.ts test/sample_actions.test.ts test/workspace_shell.test.tsx --maxWorkers=1
node node_modules/typescript/bin/tsc --noEmit
```

No Node syntax/AST helper, filtered test/timeout/threshold change or additional
required gate is introduced. Portal check and complete original eight Creator
proof groups remain separate HOLD/UNRUN; all original Sample import/quota/
parity/tone/history/Delete/encoder/monitor journeys and transition assertions
remain. Sample WebKit's capability limit is not numeric Chromium execution.
Physical/hearing/touch/MIDI/assistive/deployment/release evidence remains
separate. Source repair is not a compiler/component/browser/native PASS.

### Explicitly admitted tooling setup only

Root msg_4af8b500bf7b independently admitted one own locked npm ci. Two distinct
empty external regular config paths corrected the original unrun duplicate
/dev/null proposal, based on actual npm config source. Hermes Node26.8.1 and
npm11.19.0 were read through their real CLI, naturally exiting0. The only
npm ci naturally exited0 at2026-10-12T03:19:01Z, adding112 packages with source
package/lock/tool pins unchanged. Normal npm default allowScripts withheld
optional fsevents2.3.3 installation script and warned devdir is unknown; no
script approval/helper/retry/update or alternate tool was run. This proves
installation completion only, not that the withheld script or any test/
compiler works. Source editing paused across setup; all four actual-current14
version/install guards match SHA256
`968425c0e138cc57f3af6cef2aba87e4a34cc3892b6ade39453a8f3a9a328e1e`,
including old11 staged/working bytes/index/full patches and all five stashes.
Installed TypeScript7.0.2 and Vitest4.1.11 metadata/entrypoint bytes are bound
in external readiness/setup-v2; the entrypoints have not executed.

### Frozen evidence, K1 and current acceptance boundary

Initial13 full diff142764 B SHA256
`6f865d65ecad0573b03bd24d76bc8d3caf6381bc0e0b83764ab1494dd26c55b5`,
manifest SHA256
`df12418b373d3c1a1c2347baa2e5639fde7b88021889af05595cefdc98103253`
and report SHA256
`9cc00dc1ded38f76a2d3daba3508308f0786f744a11ee9680d0de0756cca77ac`
remain immutable. Revised14 file bytes/full candidate/delta/guards/report are
frozen separately under the Task evidence directory's revision-2. The complete
old numeric plan25715 B prefix and initial plan addenda are retained, not
relabeled current PASS. Original workspace270529 B and initial13 workspace
285652 B prefixes, all old11 staged originals/full patch/index and shared
five stashes remain protected.

No K1 source is imported. Immutable Git path inspection finds App is not
changed by frozen K1 commit124110eb0476122963d2e959530dd5d7af67fc4c,
so the four original shared paths remain workspace, two Host pages and the
followup plan. Root still owns subsequent combined retention review and
integration sequencing, including K1 browser journeys/helpers; neither K1
lane receipts nor other owners' native windows accept N13.

## Version Management

Version impact: compatible Creator MINOR debt continues to join the approved
followup V1 settlement. The Source-only ownership repair adds no Product
Build, manifest/lock identity, tag, allocation, new Contract or guessed version.
Historical debt remains; setup does not settle V1 or release readiness.

Documentation impact: required — `/hosts/creator-web` and
`/hosts/creator-interactions`. Current Sample4.1 ownership/mount/retirement
rules and Source/test mapping include the bounded App path and initial P2;
4.3/4.4 numeric fields and existing MASTER/SEQ SNAP/touch/rotary/K1 facts remain.
No diagram boundary/topology change. Portal check remains required after
separate admission and UNRUN. Assign/BPM/D04/A1/A2, full Goal acceptance,
shipping and release remain separate. Task stays ACTIVE for independent
revised Source review; no staging/commit/push/PR/merge/cleanup or worker_done.

## 2026-10-12 N13 private automatic reopen Source repair — same14, execution HOLD

Root admission `msg_d34ffc850554` at04:12:29Z follows the frozen revised14
independent Source review (Root-provided19643 B SHA256
`d35d4d4632f73f9cc10d3d0721405ccb34167660f83bfd10ce185d5bbd5787f7`).
The prior revised14 candidate remains historical evidence, including its
P2/UNRUN findings, full source copies, patch, manifest and reports. This
addendum does not promote that candidate to acceptance or rewrite old results.

Task `task_741b77b7f15a`, dispatch `ctx_c96a4aee61e7`, Run
`run_caa371bb58ee`, UID501, own worktree
`/Users/endaye/orca/workspaces/lmdj/feat-creator-sample-numeric-main` and
branch `feat/creator-sample-numeric-main` remain unchanged and ACTIVE.
Selected HEAD is `02b7445ff035e48c43ea2a66c858f7c9282e6c79`,
tree `627ed86348f4641506ba14f0e15a8f6c4368548b`, sole parent
`59da4245ff659ee1ffa2b9cf8e81f44bbc65a196`; no upstream or integration
ref update. The resume actual14/index/old11/stash guard matched the previous
final guard exactly before Source repair.

### Concrete defect and bounded implementation

The prior App exception recognized recovery by kind=open and
requireSelector=false. Those arguments are also used by ordinary defaultSeed
install and capture commit. Once a successor Session reopens the same Project,
these ordinary writers could therefore inherit the retained Sample Update's
exception while its consumer outcome or projection was still owned.

App now accepts a private finite admission reason whose default is ordinary.
Only the existing retained automatic reopen branch passes
retained-sample-reopen. The exception additionally retains the existing open
kind, requireSelector=false, original Project, different Session and exact
original pending Update kind/slot/revision checks. Boot create/open and
ordinary defaultSeed/capture/open/create/import/duplicate remain ordinary
and retain their owner/pending fence. This changes neither default-seed or
capture product policy nor their SDK/reducer/public Contract/deadline.

Revised scope remains the same fourteen declared paths:
1. `apps/creator-web/src/components/parameter_slider.tsx`
2. `apps/creator-web/src/components/sample_controls.tsx`
3. `apps/creator-web/src/components/sample_parameter_editor.css`
4. `apps/creator-web/src/components/sample_parameter_editor.tsx`
5. `apps/creator-web/src/components/sample_surface.tsx`
6. `apps/creator-web/src/components/value_slider.tsx`
7. `apps/creator-web/test/sample_numeric_editor.test.tsx`
8. `apps/creator-web/test/workspace_shell.test.tsx`
9. `tests/platform/web/creator/creator_web_sample_numeric_editor.spec.mjs`
10. `apps/docs-site/docs/hosts/creator-web.mdx`
11. `apps/docs-site/docs/hosts/creator-interactions.mdx`
12. `docs/plans/2026-10-10-creator-sample-numeric-editor.md`
13. `docs/plans/2026-10-09-creator-desktop-final-followup.md`
14. `apps/creator-web/src/app.tsx`

This Source repair changes App, appends one mounted regression to workspace,
and appends necessary documentation to both Portal pages and both plans.
The other eight candidate paths remain byte-identical to prior revised14.
The prior five mounted recovery cases and complete295508 B workspace prefix
remain intact; both prior complete plans and Portal pages are also prefixes.
No cosmetic change is made merely to reach a filename count.

### Meaningful mounted regression source — UNRUN

The new workspace case renders actual App, RuntimeProvider restart and
defaultSeed controller with existing mutable Sample fixtures. It retains an
old known update's downstream readback, actually retires the Sample page and
reopens/reloads the same Project in a distinct successor Session. Only empty
A02 is a seed target: the controller itself retires the other fifteen occupied
targets. Active Product Assembly supplies the default identity, and the
existing manifest supplies the acquisition data rather than guessed identities.

Deferred ordinary acquisition becomes ready while the old result is held.
After its actual queued controller commit attempt, the case asserts no
install, no allocated seed request/receipt, exactly one original update, no
successor update and the ownership/pending UI fence. It then releases the
old consumer outcome while holding the successor projection and asserts
that ordinary install is still blocked through that second leg.

After releasing projection, the unchanged controller's ordinary retry must
install exactly once at the current revision, refresh Project Truth, publish,
reach ready and advance the projected revision to5 while retaining the saved
numeric playback. These positive far-side assertions catch a permanent fence.
Removing the private admission discriminator exposes the ordinary install
spy and request/journal assertions to a false admission; this failure ability
is a Source argument, not an executed mutation/RED receipt.

Consumer return values, acquisition and Project storage are controlled seams;
no native seed/capture commit interleaving, hearing or wire receipt is claimed.
Native capture dynamics remain UNRUN; its shared ordinary admission is
protected by the same source discriminator. No prior case, journey leg,
test selection, timeout or threshold is changed or skipped.

### Source custody and later review / verification

The next frozen Source cut contains all fourteen lengths/SHA256/Git blobs,
full main-relative binary patch with new file bytes, complete prior-revised14
delta, frozen source copies, finite changed/untracked list, history prefixes
and fresh own/old11/index/full-patch/all-five-stash guards. Parent evidence
remains unchanged. Root receives a peer-review request for that exact cut and
then separately decides whether to admit the original six complete Vitest
files and full tsc. The proposed commands remain UNRUN:

```text
node node_modules/vitest/vitest.mjs run test/sample_numeric_editor.test.tsx test/sample_controls.test.tsx test/value_slider.test.tsx test/sample_encoder.test.ts test/sample_actions.test.ts test/workspace_shell.test.tsx --maxWorkers=1
node node_modules/typescript/bin/tsc --noEmit
```

One earlier authorized locked npm ci exited0; Node26.8.1/npm11.19.0 and
four equal setup guards remain historical actual readiness. Default npm
allowScripts withheld optional fsevents install and devdir warned; no retry,
approval, second install, model/config change or helper ran for this repair.
Vitest/tsc/AST/syntax/Portal/browser/native/build/proof/stage/commit/push/PR/
merge/cleanup remain HOLD. All eight original Creator proof groups and full
numeric browser253-line source remain; heavy window, K1 four-path combined
retention review, A1/A2/V1/Goal acceptance and release remain Root decisions.

## Version Management

Version impact: compatible Creator MINOR debt remains in the approved followup
V1 settlement. This Source repair makes no Product Build, manifest/lock,
Module/Host/Provider/Contract identity, tag or allocation change.

Documentation impact: required — `/hosts/creator-web` and
`/hosts/creator-interactions`. Append-only Source notes identify the second
P2, the private recovery discriminator and mounted seed negative/positive
legs. Existing six-field rules, MASTER/SEQ SNAP/single-current-Pad/range/
rotary/ENC4 and other pending facts remain. No source-diagram topology change;
Portal check is required after later admission and remains UNRUN.

## 2026-10-12 N13 v4 original-six failure and minimal Source repair

Root `msg_bc0efdf6340a` at 05:44:46Z admits one bounded Source-only repair
under existing Run `run_caa371bb58ee`, Task `task_741b77b7f15a`, Dispatch
`ctx_c96a4aee61e7`, worker `term_a90d95a5-8c22-4d84-ba2b-5703bb6aff7f`.
Own isolated branch remains `feat/creator-sample-numeric-main`, without
upstream or staged delta; selected HEAD
`02b7445ff035e48c43ea2a66c858f7c9282e6c79`, tree
`627ed86348f4641506ba14f0e15a8f6c4368548b`, sole parent
`59da4245ff659ee1ffa2b9cf8e81f44bbc65a196` are unchanged. This append retains
the whole prior v3 followup plan prefix and every earlier acceptance boundary.
K1's source/receipts remain untouched; Root owns later combined integration.

The one separately authorized complete original-six-file Vitest run naturally
returned1: 5/6 files PASS, 289/292 cases PASS, three workspace failures. Original
Volume completion rejected duplicate pending; original update/reset remount
table left Reset disabled; the new seed test hit undefined localStorage before
fixture/render. Raw evidence leaves actual gesture and expanded `$kind`
variant UNKNOWN and new seed held/positive journey UNREACHED. Tsc was never
launched. Keep all eleven original light artifacts and full stdout/stderr;
prior Source acceptance and historical setup0 do not erase the failure.

Root fully read the independent17710 B cause report SHA256
`342170910e20470474e0238ea3bf2dcc934cdda7ed0f00659db37821ffed96f9`,
whole parsed41408 B receipt SHA256
`d88957449358f4180bc4ba8f9478f530889b1bfe0eec95fa7d4abd662ad8138f`
and author's11129 B DATA proposal SHA256
`c6179d6a8ce700c9e28e582ec91292588dc3a3a313cdd400003a88d9121fd1cd`.
The minimal Source response has only three local behavioral sites:

- `apps/creator-web/src/components/sample_surface.tsx`: bind settlement to
  the concrete update captured by the same render, checking current identity
  before pending reinstall, outcome dispatch or ownership clear. Preserve
  strict reducer initial admission and real successor restoration, original
  Session receipt/current Pad/revision fences, true failure/conflict/unknown
  outcome and no authoring resend.
- The same Surface: detect existing inactive-to-active Sample context only
  with an owned projection refresh, then restart its existing readback. Hidden
  settlement continues; exit adds no readback gate or restart. Preserve original
  four consistency attempts, 25/50/75 ms waits, cleanup, ready/publication and
  one-mutation boundaries. Required App hidden-retain mount remains exact v3.
- Only the new appended seed case in
  `apps/creator-web/test/workspace_shell.test.tsx`: give real App/controller
  a shared, locally owned Map-backed string/null writable journal using the
  existing Vitest global stub before all ambient Storage/App access. Finally
  unmount App before descriptor restoration, including assertion failure.
  Preserve acquisition0-to1, both independent held install0 far sides and
  processing/request-null/committedRevision-null checks, final ordinary
  install exactly1, saved ready/publication revision5 and A01 complete playback.
  Manufactured test storage does not establish persistent browser proof.

Only these two files plus append-only addenda in this plan and the numeric
plan differ from v3. All14 remain owned/accounted in the frozen candidate map,
full binary patch and v3 delta. Ten other candidates, including App SHA256
`95bef6a00fa1ad985fde45c565e05f2134430fd0ed0eb856f6c49ec576230943`,
both Portal pages and full253-line numeric browser source remain byte-equal.
Complete selected02b workspace270529 B and v2 workspace295508 B prefixes
including five Session cases remain exact; original whole Volume/update/reset
and every existing test body are preserved. New seed expect expressions keep
their exact bytes/order. No timer/assertion/timeout/selection weakening,
reducer relaxation, App/private-reason expansion, SDK/Assign/state/config/
lock/setup/Nodeflag/storagefile or new public product policy occurs.

V4 Source and fixes are UNRUN. Keep old numeric11 STAGED originals/index/full
cached patch/five shared stashes, own index, prior source cuts and failed raw
history. Six field scale/bounds/immediate preview/invalid clearing, one Apply/
Enter revision/Undo, no pause/blur save, unsent cancel/late context, full range
release/key/blur/cancel and rotary400ms/SHIFT/ENC4 behavior remain owned.
The complete six Vitest files still catch these and action/history/retained
result/projection regressions; no extra gate or short named subset is added.

After independent v4 Source review, Root may separately schedule the same six
whole Vitest files with maxWorkers1 and original20000/5000 ms budgets; only
their complete PASS admits full tsc --noEmit. Neither command ran in this v4
phase. Any failure must stop with full actual raw/natural-wait evidence. Portal
check, all eight original Creator proof groups, packaged numeric browser
preview/invalid/refusal/no400ms-save/oneApply/Esc/Undo/Redo/full persisted reopen
and original Sample import/quota/parity/tone/history/Delete/encoder/monitor
journeys remain complete and separately HOLD. Current committed-head/K1 four
shared-path retention review, native/physical/hearing, A1/A2/V1/Goal acceptance
and release/shipping are Root's later boundaries; a peer finishing grants no
execution window. No setup/install/helper/compiler/browser/native/Portal/proof,
stage/commit/push/PR/merge/cleanup, worker_done or Goal mutation is performed.

## Version Management

Version impact: compatible Creator MINOR debt still joins the approved followup
V1 settlement. No Product Build, manifest/lock/active identity, tag, allocation
or release is changed by this bounded Source repair.

Documentation impact: required — `/hosts/creator-web` and
`/hosts/creator-interactions`. Current user behavior and historical v3 Source
notes remain valid, so no additional Portal edit or diagram topology change
is needed for the internal recovery/fixture repair. Both Portal paths remain
in the14-file map and their required later check remains UNRUN; current
MASTER/SEQ SNAP/single-current-Pad/range/rotary/ENC4 and pending facts remain.


## Root continuation and current-main integration — 2026-10-12

The previous v4 Source-only notes are historical. Root assumed this isolated
Task after its prior dispatch stopped at its capacity fence; no old cache,
candidate, index, stash or failure evidence was discarded.

The unchanged complete six-file v4 Vitest selection actually passed on
02b7445ff035e48c43ea2a66c858f7c9282e6c79: 6 files, 292 tests, zero failures,
actual child exit 0 (69.90 s test duration). Full TypeScript --noEmit then
returned actual exit 0. Raw logs, PID/group natural exits and preservation
guards are retained in root-light-v4-original6-tsc-20261012T0814 under the
existing external N13 evidence directory. Earlier 289-pass/3-fail evidence
remains historical negative evidence, not a result for this candidate.

Root subsequently fast-forwarded this owned branch to current main
d21ea97c71da281f89ac78238f6fcceb8b03e638 with no autostash. All 45 intervening
paths were inspected; they change C++/Python source, tests and documentation,
but none of the Creator TypeScript, component-test or dependency inputs.
Those six-file and type-check results therefore remain bound to unchanged
inputs; they do not establish packaged browser or current Core acceptance.

Only the two declared Portal pages needed overlap resolution. Their reviewed
union retains current-main Pattern/Sequence/capture/navigation facts and this
Task's numeric-editor behavior. The other 12 candidate files and all five
shared stashes were byte-identical before and after integration. Complete
before/after manifests, preserved14 originals and actual FF exit0 receipts are
under n13-current-main-integration-20261012T0856 in Root's external checkpoints.

The next precommit boundary is the complete required Portal check, followed
by exact14 staging, the new-tracked-file ownership suite, whitespace/staged
inspection and the Task Conventional Commit. The stable Creator proof requires
a clean committed source; all original eight browser groups and the complete
new numeric preview/invalid/refusal/no400ms-save/Apply/Esc/Undo/Redo/persisted
reopen journey remain required after that commit, before delivery. None is
claimed run or passed here. No timeout, gate, assertion, lane or journey was
weakened, and no Product Build, release, deployment or cleanup is authorized
by this continuation.

Version impact: compatible Creator MINOR debt remains in approved V1 settlement;
this Task allocates no Product Build or manifest identity.
Documentation impact: required — /hosts/creator-web and
/hosts/creator-interactions; the complete Portal check remains pending.


## 2026-10-12 — exact a492 integration proposal and preserved verification boundaries

This section describes external review DATA prepared for Root. No Source, Git
index/ref/config, worktree or Orca lifecycle mutation and no test/build/setup
execution occurred during this reconciliation. It does not itself commit,
review, ship or accept a new product head.

The complete original N13 Task is committed as
`e4e0e6e7179862a36b448a53464458d66b372116` (parent
`d21ea97c71da281f89ac78238f6fcceb8b03e638`). The proposed exact base is
`a4923f20f78ba6780d1265882669b8a00a762de4`. All fourteen declared paths remain;
the complete numeric component/source files, 419-line component test,
583-line mounted App suffix and 253-line native/browser journey are retained.
Old failed results, Source-only UNRUN records, five recovery cases and the
ordinary default-seed positive/fenced recovery case remain historical evidence.

The new base includes #2058 four-row mapping, #2061 explicit Cmd/Ctrl+Z Pad01
conflict, #2065 manual corrections, #2067 journal recovery and #2068 direct
replay preflight. The workspace test keeps the whole current-main file before
appending the unchanged N13 suffix. Portal conflicts preserve letters AND
digits in ordinary dialogs, the precise form's own key propagation, main's
chapter-10 approved-feature organization and current #2014/#2037 references.
The current Cmd/Ctrl+Z limitation and open #2060 owner-decision boundary remain;
no K1 controller guard, modifier choice, additional shortcut or outside-scope
file is silently introduced here.

Root reports the old fourteen-file input actually passed all six complete
Vitest files (292 tests), full TypeScript (exit0), and full Portal check (176
tests, 52 pages, 10 diagrams/20 outputs, 50 routes). These are preserved old-input
results, not passes for this new base/proposal. The new integration's complete
six-file component checks, full typecheck and full Portal check are UNRUN.
The Task's existing complete eight Creator/browser groups, original fixtures,
far-side legs and new precise native command/preview/Undo/Redo/reopen journey
remain required and UNRUN; native/physical/hearing/deployment/release claims
remain separate. No timeout, assertion, lane or journey leg is weakened.

Ordinary PR verification follows the replacement AGENTS.md: Task-relevant
checks and declared owning journeys remain; a selected batch_only lane alone
does not require running every complete lane. The old K1 thirteen-selected /
ten-batch-only receipt obligation is historical, not an ordinary-merge gate.
Complete-candidate/full verification debt is still recorded separately.

### Version Management

Version impact: the existing compatible Creator MINOR feature debt remains for
the Goal's V1 settlement. Main's already-delivered incompatible shared-default
MAJOR/migration debt is not settled or allocated by this N13 integration.
No Product/Module/Host/Contract identity, Product Build, Assembly lock,
snapshot, tag, release, deployment or Channel is allocated or guessed.

### Documentation Impact

Documentation impact: required — `/hosts/creator-web/` and
`/hosts/creator-interactions/`; source facts and integration/evidence boundaries
are updated in the same fourteen-file proposal. Manifest-derived portal
identities are not hand entered. Run the original full `scripts/docs-site.sh
check` on actual admitted integrated Source before a future verified commit.


## 2026-10-12 — Root actual current-main Source integration

Root created an isolated owned worktree at exact
`43f41d2f1cf0f8294568e9964c058d141421aa46` and legal branch
`feat/creator-sample-numeric-current-main`, preserving the complete clean
`e4e0e6e7179862a36b448a53464458d66b372116` candidate, its worktree,
all five stashes and all earlier evidence. The external a492 proposal remains
historical review DATA. Fresh main includes actual merged #2070, a test-only
Replay neutral-reset audio-progress correction; all fourteen Task base files
are byte-identical a492 to43. No numeric implementation premise is delivered
by that successor, and its Host result is not numeric acceptance.

All fourteen declared paths were independently rehashed before actual Source
application. The seven numeric/app implementation files, complete419-line
component test, complete583-line mounted App suffix and complete253-line
native/browser journey retain their exact e4 bytes; the mounted App file
retains the complete current-main prefix. Both complete old plan prefixes and
all historical failures remain. Only current integration/evidence descriptions
are added here. #2060 modifier policy is still awaiting user decision and is
not implemented by this Task.

Six complete original component files, full typecheck, full Portal check and
all eight original Creator/browser groups remain UNRUN for this new actual
Source. Original deadlines, assertions, native command/preview/Apply/Undo/Redo/
Esc/context-cancel/reopen legs and physical/hearing boundaries remain intact.
This Source checkpoint is not a verification, commit, push, review, merge,
full-candidate, Product Build, snapshot, release or deployment claim.

Version impact: existing compatible Creator feature debt remains for V1;
no manifest, Contract, Assembly, Build or Channel identity allocated here.
Documentation impact: required — /hosts/creator-web/ and
/hosts/creator-interactions/; run the required full Portal check before commit.

## 2026-10-12 — Root current-main light verification

On the actual integrated fourteen-file draft at
`43f41d2f1cf0f8294568e9964c058d141421aa46`, branch
`feat/creator-sample-numeric-current-main`, the original complete six-file
Vitest invocation naturally exited0: six files and292 tests passed, with no
failure or omitted case. The reported Vitest duration was76.28s; the outer
recorded process elapsed77.921055s, from12:35:51 to12:37:09 UTC. Full
`tsc --noEmit` then naturally exited0 in2.215418s. Both ran with the pinned
Node26.8.1, private locked dependencies, ordinary UID501 and the unchanged
single-worker setting, assertions and20000/5000ms budgets. The existing Node
experimental localStorage warning remains in the original stderr.

Before/after all fourteen source bytes, modes and mtimes, branch/HEAD, raw
index, empty staged set, worktree status and all stash identities matched.
Full argv, stdout/stderr, process-start observations, actual exits and source
guards are retained outside the worktree under
`n13-current-main-light-20261012T1236` in Root's followup evidence. The later
documentation-only evidence update does not change implementation or tests.

Current full Portal and all eight original Creator/browser proof groups remain
UNRUN. No numeric packaged/native, physical/hearing, shipping, full-candidate,
V1, snapshot, release or deployment result is inferred from these component
and type checks. Historical failures and integration records remain intact.


## 2026-10-12 — Root current-main Portal verification

On the actual fourteen-file integration at
`43f41d2f1cf0f8294568e9964c058d141421aa46`, the complete stable command
`bash scripts/docs-site.sh check` naturally exited0, 13:39:06–13:40:22 UTC,
76.437596s, ordinary UID501 and Node26.8.1. All176 tests passed with zero
failures/skips;52 pages,10 diagram sources/20 outputs,50 routes and internal
links passed. The current locked Product Build's existing immutable snapshot,
Host/Release projections, generated source facts and full typecheck/build were
verified by that unchanged command. This allocates no identity/snapshot/Release
and does not establish production deployment or physical/hearing acceptance.

The actual whole fourteen-file bytes/modes/mtimes, branch/HEAD, raw index,
status, five retained stashes and ten pristine Git120000 links remained exact
before/after; the owned process group naturally became empty. Complete stdout
16754B SHA256`b1b2cdf963f2f86a8cd96faf099d8bfee4178915aea2c4fb6f55114aebd87f03`,
stderr1119B SHA256`8faf893639495e3981099bbb86841c9bf779462b4a3c4303ca7c9f6d531c6672`
and direct exit/guards are retained under
`/Users/endaye/Projects/lmdj-followup-evidence/2026-10-12-root-checkpoints-0634/n13-current-main-portal-20261012T1342/`.
Node's optional localStorage warning and npm's update notice are retained; no
install, global update or warning suppression was performed.

Only the two declared plans receive this factual append and the current N13
paragraph in`/hosts/creator-web/` records the actual result. This documentation
update requires another unchanged whole Portal check before commit. The eleven
other candidate paths, component/typecheck inputs, all original assertions,
20000/5000ms component budgets and complete253-line browser journey remain exact.
The eight original Creator proof groups and packaged numeric command/preview/
Apply/Escape/Undo/Redo/reopen far sides still require their own clean-head proof.
Physical/hearing,A1/A2,V1,guarded shipping and the overall Goal remain incomplete.

Version impact: the approved compatible Creator MINOR feature debt remains for
V1; this Task allocates no manifest,Assembly,Contract,Build or Channel identity.
Documentation impact: required — /hosts/creator-web/ and /hosts/creator-interactions/.

## 2026-10-12 — N13 Native journey and latest-main integration

The clean local Task commit `935428394d5d54b5a89ee7fc9b66e4c66a7cdb3d`
ran the unchanged `scripts/creator-web.sh proof`, 14:14:53–14:40:44 UTC.
Real Core/native fixtures, two byte-reproducible Release WASM distributions,
all75 Vitest suites (1365 tests), typecheck and the original eight browser
groups ran. The actual proof exit was1:118 browser passes,2 failures and11
existing capability skips. Complete logs, traces, source/index guards and
all14 negative-input files are retained outside the worktree. This is not a
complete Creator PASS.

One failure was the old hardware-layout Q hint, separately fixed by the
original owner in PR #2085. The new numeric spec's first preview oracle used
Project's Pad identity/color projection as though it contained playback.
It now derives all five native playback fields from authoritative
`sample.inspect`. Complete Project equality, full Sample playback equality,
revision, exact save payload/identity and every original transition remain;
no timeout, assertion, fixture, runner or journey leg was weakened.

The corrected complete numeric browser journey naturally passed1/1 in25.3s,
14:59:47–15:00:17 UTC, against the original clean935 application distribution
and corrected spec SHA256
`ba2124c3fbbeb35b914c77821e1655451edb590fa53798fe359cedd4bff67075`.
Preview, invalid clear, Apply, cancel, Escape, Undo/Redo and persisted reopen
all executed with real Native receipts. This focused PASS is not a fresh
clean-head full proof. Evidence roots are `n13-full-creator-proof-20261012T1418`,
`n13-full-proof-negative-retention-20261012T1456` and
`n13-browser-oracle-focused-20261012T1504` in Root's external evidence.

Root then integrated exact main
`f084f3e345b4122e0649907e30eb83f331546887` into this isolated, unpublished
Task via rebase. Original935/source14/index/spec patch and all existing
stashes remain retained. PR #2082's delivered shortcut guard and Portal facts,
#2084's separate deployment compatibility and #2085's one-line hardware
oracle remain intact; this Task does not repeat them. Its seven implementation
paths are unchanged by that integration. The live Issue remains #1995;
precise input still needs this Task's verification/review/shipping. Fresh
affected six-file/type/Portal checks and a clean integrated full Creator proof
are the next verification boundaries, not inferred from the earlier runs.

Version impact: no manifest or identity allocation; approved compatible
Creator feature debt remains for V1. Documentation impact: required —
/hosts/creator-web/ and /hosts/creator-interactions/. Physical/hearing, A1/A2,
full-candidate, V1/snapshot, release and deployment remain separate.
