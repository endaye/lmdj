# PRD 迭代系统

这个目录用于脑暴阶段的快速产品迭代。目标不是一次写完最终 PRD，而是把输入、假设、问题和决策拆开管理，让版本可以快速收敛。

## 文档分工

- [source-materials.md](source-materials.md)：素材池。记录外部 PRD、demo 工具、参考产品、访谈输入和技术样例。
- [working-prd.md](working-prd.md)：当前工作版 PRD。优先保持清晰、可改、可讨论。
- [open-questions.md](open-questions.md)：开放问题池。每个问题都应该有负责人、下一步和状态。
- [decision-log.md](decision-log.md)：决策记录。只记录已经确认的结论、原因和影响范围。

## 推荐迭代节奏

1. 新素材先进入 `source-materials.md`，不要直接当作结论。
2. 从素材里抽取对当前版本有价值的假设，更新 `working-prd.md`。
3. 所有不确定点进入 `open-questions.md`，避免藏在正文里。
4. 讨论后确认的结论写入 `decision-log.md`，再回填到 `working-prd.md`。
5. 每轮脑暴结束时，只保留一个最新工作版 PRD；旧观点用决策记录或问题池追踪。

## 写作口径

- 用“假设 / 待验证 / 已确认”区分确定性。
- 工作版 PRD 不追求完整叙事，优先清楚表达产品判断。
- 技术 demo 只作为证据或灵感，不默认等于最终实现。
- 能落到用户行为、系统边界、输入输出和验收标准的内容优先写。
