# LMDJ Docs

这里是 LMDJ 脑暴阶段的文档工作区，用来快速迭代 PRD，而不是一次性写定稿。

## 工作方式

```text
source-materials.md  收外部输入和 demo 参考
  -> working-prd.md  快速收敛当前产品版本
  -> open-questions.md  暂存未决问题
  -> decision-log.md  固化已经确认的结论
```

每次新素材进来，先放进素材池；每次形成判断，更新工作版 PRD；每次拍板，写进决策记录。

## 核心文档

- [prd/working-prd.md](prd/working-prd.md)：当前工作版 PRD。这里可以直接重写，不需要保留每个旧想法。
- [prd/source-materials.md](prd/source-materials.md)：素材索引。高嘉丰 PRD、demo 工具、外部参考都先放这里。
- [prd/open-questions.md](prd/open-questions.md)：开放问题池。用于记录还没想清楚的产品、技术、内容和商业问题。
- [prd/decision-log.md](prd/decision-log.md)：决策记录。只放已经确认的结论和原因。
- [lmdj-web-prototype-spec.md](lmdj-web-prototype-spec.md)：2026-07-02 收到的 V1 web prototype PRD 素材，当前仅作脑暴参考。

## 状态标签

- `素材`：可参考，但未评审。
- `假设`：当前倾向，但还需要验证。
- `待决`：需要讨论或实验后再决定。
- `已确认`：进入 decision log，后续默认遵守。
- `废弃`：明确不再采用，但保留原因。

参考 demo 的运行说明放在 [../references/README.md](../references/README.md) 和各自 demo 目录内。
