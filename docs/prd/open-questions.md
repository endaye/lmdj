# 开放问题

这里保留仍未确认的产品和技术问题的来源上下文。**每个迁移的问题是
[questions/](questions/) 目录下的一个独立文件**；文件包含 `GitHub Issue` 行以
链接活跃讨论，但不再拥有 live status。活跃讨论、优先级、依赖与开放状态由
GitHub Issue 负责。已经确认的结论按 [decision-log.md](decision-log.md) 的约定
写入决策文件目录，不以“待决”状态继续保留。

本文件只承载约定，不维护逐条索引：`questions/` 的目录列表即当前问题清单。
2026-08-18 之前的问题以表格形式记录在本文件的 git 历史中（`fbf263e9` 及
更早）；当时未决的 18 个问题已逐条迁移到 `questions/`，内容未改。

## 约定

- 新问题：通过 GitHub Question form 创建；需要保留来源上下文时，在
  `questions/` 新建 `<slug>.md`，slug 是小写 kebab-case 的主题名，并填写
  `GitHub Issue` 行。
- 已迁移问题的状态变化：只编辑 GitHub Issue；已迁移的问题文件不拥有 live status。未迁移的问题文件保留现有状态，直到替代 GitHub Issue 已创建并完成链接完整性验证。
- 问题解决：在写入决策文件（见
  [decisions/README.md](decisions/README.md)）的同一个 Task 里删除对应的
  问题文件，决策条目注明它解决的问题。
- 每个问题都应该写清为什么重要、处理时点和状态，避免藏在正文里。

## 文件格式

````markdown
# <问题本身，一句话，问号结尾>

- 范围：<新内核（Playable Beat Instrument）/ Stage 1 首条切片 / Stage 1 后续 / Stage 2–4 / …>
- GitHub Issue: #<number>
- 原迁移状态：<待决 / 待验证 / 待设计评审 / 待架构设计 / 待评审 / 已收缩 / 延后>
- 来源：<可选；引出该问题的评审或文档链接>
- 为什么重要：……
- 处理时点：……
````

原迁移状态词表沿用原表格：`待决`、`待验证`、`待设计评审`、`待架构设计`、
`待评审`、`已收缩`（首版收缩范围、后续再评估）、`延后`（明确排到后续
Stage）；它们只保留历史上下文，不表示当前状态。
