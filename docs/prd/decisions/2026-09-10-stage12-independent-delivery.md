# 已确认：Stage 12 按 Slice、Stem、Pattern 独立立项与验收

- 日期：2026-09-10。
- 确认依据：用户同意独立立项建议，并要求创建对应任务、更新核心重设计 §23 的整体计划列表。
- 结论：保留 Stage 12 总追踪，将交付拆为 12A Slice、12B Stem、12C Pattern Intelligence；先推进 Slice 验收，后两条先设计和评估。
- 原因：Stem 的模型/执行环境与音质评测、Pattern 的事件生成与采纳语义各自构成独立产品工作；不应使已实现的 Slice 参考链路无法独立验收。
- 影响：更新[核心重设计 §23](../../design/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md#23-交付顺序)、[任务计划](../../plans/2026-09-10-stage12-independent-delivery.md)及机器/人工台账入口。

## 确认边界

这是任务范围与顺序决策。Stage 0–11 编号不变，Stage 12 总目标仍包含三项；
12A 完成不代表 #472 完成，也不自动授予 Slice 生产质量或跨平台支持声明。
复用 Provider、Attempt、Artifact 基础设施；后续 Stem 结果与 Pattern 事件的
Contract、持久化和采纳规则需要各自获评审的设计，不能照搬 Slice recipe。

规则 Drum Groove/Fill、新 Pattern Slot 是 P1 的首版评审建议，尚未确认为
产品限制或实现规则。模型选择、付费算力、远程执行、Pattern Merge/替换与
模型直接生成事件均不由本决策批准；后者保留既有 #535。
既有 Slice Contract/Candidate 决策与失败时零 Project Truth 变更不变量继续适用。

## Version Management

Version impact: none
仅更新交付规划，不分配 Product、Module、Provider、Contract、Build 或 Channel 身份。

## Documentation Impact

Documentation impact: none
Reason: 保留的产品决策与整体计划更新，不改变当前 Portal 功能/身份；各实现和验收任务另列具体影响。
