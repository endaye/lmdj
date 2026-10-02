# 已确认：Stem / Slice 复用 Provider 边界，功能参考 Koala

- 日期：2026-10-03。
- 确认依据：用户要求代理确定方案，随后确认「功能上你可以参考 koala，其他的按照你的这条路径继续」，并明确授权 push、PR、merge。
- 关联：#1163、#1164、#1172、#1670、#1654；总追踪 #472。
- 详细定义：[Contract 与功能边界](../../design/2026-10-03-stem-slice-provider-contract.md)。
- 实施顺序：[分阶段交付计划](../../plans/2026-10-03-stem-slice-provider-delivery.md)。

## 结论

1. Slice 与 Stem 是独立 Capability。算法、模型推理和编码放在 `providers/`；
   Artifact 验证与 Attempt 属于 SDK；结果展开、试听、采纳与恢复属于
   Facade / Workspace；产品注册只在 Assembly。评测工具继续放在 `tools/`。
2. Stem 首版一次 Attempt 返回一个 Candidate，具有 `drums`、`bass`、
   `vocals`、`other` 四个 required 输出端口，每端口恰好一路。角色完整、
   音频时间轴一致并全部通过消费方验证后才可采纳。缺失角色不能以 partial 成功。
3. 输出角色与内容身份分离：不同端口可绑定同一完整 ArtifactRef；同一端口
   的重复 binding 仍拒绝。相同 digest 但 media type 或 byte length 不同仍
   拒绝；输入 Artifact 唯一性维持既有规则。这是对旧输出去重行为的明确修订。
4. Creator 入口保持 Sample → Tools → Chop / Split Stems。先试听候选，再由
   用户确认采纳；默认保留原 Pad。界面可以按当前 Bank、后续 Bank 的空 Pad
   提出映射，但不在计算完成时自动写 Truth。确认时重新检查占位、源身份、
   revision 与配额；空间不足或目标已占用时整次拒绝，不隐式覆盖。
5. Chop 的完整功能目标包括瞬态、等分、播放时打点、手动调整标记、逐片试听。
   首个增量复用现有瞬态参考能力；其他模式、播放选项和编辑效果固化分别实施，
   不以首个增量替代完整功能验收。直接编辑标记是 Workspace 作者操作，
   不伪装成 Provider 输出，也不修改已完成 Attempt。
6. 共用 Job / Attempt 生命周期；Slice 与 Stem 保留各自封闭的结果及 Lineage
   类型。源内容、参数、Provider、模型、角色和输出身份均可追溯。预览不改 Truth。
7. Stem 首个实现走本地离线、隔离进程 CPU 路径；执行 owner 在 Provider API
   之外负责进程树、超时、取消和资源控制。Core 不加载任意第三方代码。
   云端和可安装 Provider 仍由 #1654 的信任、发布、选择与权限设计覆盖。
8. 首轮研究候选仍为已固定身份的 Open-Unmix `umxhq`；它不因此成为产品
   默认模型。真实评测环境、权重身份、质量证据与盲听继续由 #1172 交付。

## 与既有决策的关系

- 延续 [Slice 决策](2026-09-09-stage12-contract-candidate.md) 的单 SDK
  Candidate、Facade 所有 Job、显式采纳和完整 Lineage。
- 对 [多端口决策](../../architecture/2026-08-01-provider-multi-port-contract-decision.md)
  补充输出共享内容语义；输入的全局 Artifact 唯一性不变。每个 mint 的
  **binding** 在 Candidate 恰好出现一次，内容 blob 可被多个端口共享。
- 细化 [Creator 工作流基线](2026-09-29-creator-user-workflow-baseline.md)
  第 7 项：保留 Tools、空 Pad 顺序、保留原音频、后台执行；结果放置明确为
  「自动提出映射 + 用户确认采纳」。首版四路逐路选择允许一次只采纳一路，
  多路确认使用既有原子采纳原则。该细化是 LMDJ 的明确产品选择。
- 本地优先是交付顺序，不取消本地与云端的完整目标。#1654 与生产 checkpoint
  问题仍开放；本条不授权任意代码安装、付费服务、GPU、云上传或发布部署。

## Version Management

Version impact: none
Reason: 本 Task 只记录已确认的产品/架构决策；不修改 active Contract、
Module、Provider、Assembly 或 Product Build。实现时从活动清单分配身份。

## Documentation Impact

Documentation impact: none
Reason: retained 决策和后续设计，不改变 Architecture Portal 的当前功能事实。
