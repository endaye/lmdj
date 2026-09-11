# LMDJ 三条并行产品主线与交付计划

日期：2026-09-11。规划依据：用户要求 Stage 12、Embedded / Cardputer Runtime、
Web Creator 三线平行推进。状态核对基线：main `2b6d490a`；GitHub Issue 当日状态。
本计划更新任务组织与推进顺序，不执行产品实现、设备操作或发布。

## 主线结构

```text
New Headless Core（共享 Core / Facade / Contracts）
├── A. Stage 12 Intelligence Providers — #472
│   ├── 12A Slice — #1163：验收与独立交付
│   ├── 12B Stem — #1164：场景、评测、选型、实现
│   └── 12C Pattern — #1165：产品语义、候选、预览、采纳
├── B. Embedded / Cardputer Runtime — #1104
│   ├── H1 #1107：正式 Host 生命周期与启动/停止静音
│   ├── R2 #1131 / CPU #1176：原口径容量与实时余量
│   ├── B1 #1110：固定 Build 与集成证据维护
│   └── A1 #1111：完整真机演奏、换内容与恢复旅程
└── C. Web Creator — #1207 / #522
    ├── W1：上下文、控件映射与现有能力审计
    ├── W2：状态、交互原型、适配与可访问性
    ├── W3：稳定四区布局与已有功能分批接入
    ├── W4：Project / Sample / Sequence / Perform 工作流
    └── W5：固定候选的浏览器、触摸、听感与可用性验收
```

Stage 0–11 保留原编号及未完成验收。三线是工作组织，不是三套 Core，
也不把四区硬件设计等同 Cardputer 的键盘/屏幕规格。
Stage 13 Audio Tagging #1189 是后续能力扩展，设计研究可并行；不成为三线
当前交付的统一前置。CI #1089/#1149 与 Cloudflare #873 是支撑工作流，
其部署、review 或环境证据按原任务处理，不据此扩大产品任务范围。

## 当前事实与下一步

| 主线 | 已有证据 | 下一步 | 完成边界 |
| --- | --- | --- | --- |
| 12A | K/L Slice 实现已交付；#1166–#1170 仍 OPEN | S1 固定验收包，然后 S2 Windows 人工与 S3 代表性评测并行 | S4 适用性裁定、阻塞修复重验、S5 核销；仅结算 Slice |
| 12B | #1164/#1171/#1172 OPEN | T1 场景、执行区与评测设计；批准后 T2 实测选型 | 后续 Contract、Provider、Facade/Creator 集成与音乐质量验收完整交付 |
| 12C | #1165/#1173 OPEN | P1 候选范围和安全采纳设计，复用 #535 产品问题 | 批准语义后实施、预览/采纳/保存重开及音乐性验收 |
| Embedded | B1 #1110 CLOSED，有目标构建记录；H1/R2/CPU/A1 OPEN | #1176 归因/修复后 #1131 同口径复测；H1 补齐静音与生命周期证据 | 固定候选完整 Host 负载、内容传输、30 分钟与 A1 真机旅程 |
| Web Creator | #1208 布局参考已合并；#1207/#522 OPEN，设计与开发线路已启动 | W1 明确上下文及交互边界，再 W2 原型；实施子项须先封闭范围 | 可工作的 Creator 与真实设备验收；静态设计不计作软件交付 |

B1 关闭不意味着 H1/R2/A1 通过。#1110 的后续记录仍明确 concrete USB/PTY 与
Facade export producer wiring、启动 click 和 combined-load/30-minute 缺口。
这些缺口在进入 A1 前由 #1104 核对具体责任：已有子项覆盖则回链；未覆盖则
另拆有界修复/集成 Task，不能重新执行整个历史 B1 或把 Closed 当作验收。
新固件/依赖修复后核对是否需新候选和快照；旧镜像结果不可回填新候选。

## A — Stage 12 执行顺序

复用[独立交付计划](2026-09-10-stage12-independent-delivery.md)的精确文件和测试：
S1 #1166 → {S2 #1167, S3 #1168} → S4 #1169 → 阻塞修复/重验 → S5 #1170。
同时推进 T1 #1171、P1 #1173 的设计准备；T2 #1172 等待批准的 T1。
12A 验收可用现有 Creator，不等待新四区 UI；新 UI 复用已验收 Facade 能力，
不以 Stem/Pattern 尚未实现为理由冻结整个 Creator。

## B — Embedded 执行顺序

复用[Host 计划](2026-09-10-cardputer-runtime-host.md)与 #1104 原验收范围。
CPU #1176 的修复源码 → R2 #1131 正向复测；H1 可推进不依赖正向容量的
问题归因与已有实现修复，正式容量准入仍等待证据。H1 与 R2 汇合后审计
全 Host 的 USB/LCD/input/DMA 成本、真实传输生产者/消费者和固定 B1 候选，
再执行 A1。不能以纯 Core 探针或可编译固件替代完整 Host 测量。

A1 保留装载 A → Pattern/Pad 播放 → stop/实际静音/drain → unload →
不同 B 内容/声音 → 坏输入拒绝 → 正确重试 → 断连/复位/重新装载 → 持续运行。
每腿记录转换后的状态、固件/内容身份、设备观测及真实听感；原 CPU reserve、
音乐 fixture、时长和声音目标保持不变。单台 Cardputer 的实验由一个操作者串行执行。

## C — Web Creator 分阶段规划

复用[四区设计参考](../design/2026-09-11-lmdj-hardware-ui-layout-reference.md)。
#1207 承接本轮四区与上下文迭代，#522 保留整体视觉语言责任。
W1–W5 是规划编号，尚不是新建 Issue 或已批准实现范围。

| 阶段 | 交付与依赖 | 文件边界与最低层验证 |
| --- | --- | --- |
| W1 交互及能力矩阵 | 可立即准备；列模式×对象×操作阶段、Pad 选择/触发、四旋钮/方向键映射、返回/未保存/确认/撤销；逐项区分现有 Facade、仅设计和待决策能力 | 建议独立 `docs/design/2026-09-11-creator-context-matrix.md`；对照 Facade 公开接口和现有产品决策逐格审查；未决语义列问题，不代替用户裁定 |
| W2 原型和状态 | 依赖 W1 已批准交互；补空/加载/禁用/失败/恢复、键鼠/触摸、焦点与非颜色提示；真实触摸预验可提前发现问题 | 独立原型与设计/验收记录，开始时锁定文件和节点；逐腿观察选择→操作→反馈→取消/返回，校验上屏无需触摸、Pad 空间身份不变 |
| W3 布局骨架 | W1/W2 稳定区域获批后，接入现有 Creator，保持 Facade 边界；不一次性重写全部页面 | `apps/creator-web/` shell/style/对应组件测试，实施子 Task 必须列精确文件；最低层验证布局、焦点顺序、输入归属及模式切换，不用截图冒充行为证据 |
| W4 工作流纵向交付 | 基于 W3，建议先 Project/Sample 核心旅程，再 Sequence/Perform；每项独立 Task。阶段内互不争用文件才并行 | 每个工作流的组件/reducer 与对应 browser spec 精确清单；验证实际 Facade 回执、失败/取消、保存重开以及音频状态。新 Core/Contract 能力另立前置 Task |
| W5 固定候选验收 | 对每个已集成切片持续验收，最终汇总；等待具体候选及对应自动化证据 | 独立 `docs/quality/` 报告与 evidence 目录；稳定入口 `scripts/creator-web.sh proof` 加实际触摸/键鼠/听感/恢复和非开发者可用性旅程 |

上述目录是拆分边界，不是可执行的无限文件清单。W1/W2 可产出设计稿；
W3/W4 启动前必须建有界子 Issue，列 exact files、最小复现/测试、API/ABI、
版本和实际 Portal 路由。新增检查必须指出捕获的缺陷。
四区图中的滤波曲线、参数值域、下一小节切换、标签类别均不自动变成新 DSP/Contract。
Stage 13 的置信度/自动采用与用户确认的真相写入关系，须在该能力设计中消除歧义。

## 并行规则与交付节奏

1. 现在：A 推 S1，B 推 CPU/静音问题与证据补齐，C 推 W1；T1/P1 可做独立设计准备。
2. 下一轮：A 的 S2/S3、B 同口径 R2、C W2/获批的 W3 可并行；物理设备占用先排期。
3. 集成轮：各线按自身证据固定候选，单独验收。12A 不等 12B/12C；
   Creator 已有功能不等新 Provider；Embedded 首版不要求设备端编辑或 AI。
4. 每线都达到自身边界后分别结算；总 Stage 12 等三分支完整交付，
   #1104 等完整真机闭环，#1207 等其交互实现与设备验收，#522 按自身范围结案。

共享 `application-facade`、Contracts、Creator shell、Assembly/manifests 和 Portal
由一个 Task 持有重叠文件；先合并生产者再接消费者。不同分支/目录不是独立性的证明。
实施使用隔离短期 worktree，一 Task 一 Conventional Commit；不接管其他活动 worktree。
原 Stage 6/8/9/10 的 MIDI、Safari、iPadOS、导出与非开发者验收继续留在
[人工台账](../quality/2026-08-17-manual-verification-todo.md)，可在身份匹配时共用会话，
必须逐项留证，不能靠新版 UI 或新 Build 批量核销历史缺口。

## 本次规划 Task 与验证

本次声明文件仅四项：本文件、核心重设计 §23、machine-task-todo、manual-verification-todo。
核对 GitHub 父任务及关键子任务、相对链接、staged ownership、文档差异与 PR 声明。
不新增产品测试或 required gate；不重跑与规划无关的产品全量测试。

## Version Management

Version impact: none — 本 Task 只调整计划，不分配任何产品/模块/Host/Contract 身份。
后续实现按实时 manifests 核定 API/ABI 与消费者，固定测试 Product Build 与不可变
Portal snapshot 同 Task；发布操作仍由单独的发布授权启动。

## Documentation Impact

Documentation impact: none — 本次只改设计/计划/质量台账，不改变已实现产品事实或
Architecture Portal 页面。后续实现同步实际受影响 Portal；Product Build/Assembly
必须 required，不得用本计划的 none 沿用免责。
