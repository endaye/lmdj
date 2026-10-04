# Pad 的颜色按 stem 类别给、由用户自定义，还是两者结合？用哪套调色板？

- 范围：Creator
- GitHub Issue: #1821
- 来源：[Sequence 硬件界面修订](../decisions/2026-10-04-sequence-hardware-ui-revision.md) 结论第 3 项；Figma D02 Pad 矩阵（节点 88:1376）的五个类别色：DRUMS `#F3B580`、BASS `#DFF779`、MELODIC `#B49DE8`、VOCAL `#94D2DC`、TEXTURE `#E6ED98`。
- 为什么重要：
  - 同一个 Pad 要在 Pad 矩阵、上屏行和触控网格中用同一种颜色，但 Project 数据目前没有 Pad 颜色或类别。Creator 现在按 slot 编号轮换颜色，这个颜色没有含义。
  - 写进 Project Truth 属于 Contract 改动。
  - 另外要注意：BASS 的 `#DFF779` 和界面上表示选中的亮绿 `#DDF478` 几乎相同。
- 处理时点：在第一个给 Pad 上色的 Sequence 上屏、触控网格或 Pad 矩阵实施 Task 之前。
