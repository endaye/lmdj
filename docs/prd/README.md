# PRD 迭代系统

这个目录用于产品输入、工作版 PRD、开放问题和已确认决策的持续迭代。当前路线图依据是 2026-07-18 的 [LMDJ Software MVP Stage 1–4 Memo](https://fcn8wuu8uotg.feishu.cn/docx/ZK5eduti6oE9Dox8Pkbc8r0vnPb)；仓库内的设计与计划负责把它收敛成可执行切片。

## 文档分工

- [source-materials.md](source-materials.md)：素材池。记录外部 PRD、demo 工具、参考产品、访谈输入和技术样例。
- [working-prd.md](working-prd.md)：当前工作版 PRD 摘要，反映最新 Stage Memo 和已经确认的本地收缩决策。
- [open-questions.md](open-questions.md)：开放问题约定。每个未决问题是 [questions/](questions/) 目录下的一个独立文件，写清为什么重要、处理时点和状态。
- [decision-log.md](decision-log.md)：决策记录入口。2026-08-16 及更早的决策存档在该文件内；自 2026-08-18 起每条新决策是 [decisions/](decisions/) 目录下的一个独立文件，只记录已经确认的结论、原因和影响范围。
- [Stage 1 Creator Core 首条纵向切片设计](../superpowers/specs/2026-07-24-stage1-creator-core-slice-design.md)：当前下一条可执行产品切片的边界、数据流和验收。

## 推荐迭代节奏

1. 新素材先进入 `source-materials.md`，不要直接当作结论。
2. 从素材里抽取对当前版本有价值的假设，更新 `working-prd.md`。
3. 所有不确定点按 `open-questions.md` 的约定进入 `questions/`，每个问题一个文件，避免藏在正文里。
4. 讨论后确认的结论按 `decision-log.md` 的约定写入 `decisions/`，每条决策一个文件，再回填到 `working-prd.md`；被解决的问题文件在同一个 Task 里删除。
5. 每轮脑暴结束时，只保留一个最新工作版 PRD；旧观点用决策记录或问题池追踪。

## 写作口径

- 用“假设 / 待验证 / 已确认”区分确定性。
- 工作版 PRD 不追求完整叙事，优先清楚表达产品判断。
- 技术 demo 只作为证据或灵感，不默认等于最终实现。
- 能落到用户行为、系统边界、输入输出和验收标准的内容优先写。
