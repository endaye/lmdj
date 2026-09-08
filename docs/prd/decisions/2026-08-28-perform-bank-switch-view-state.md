# 已确认：Perform 的 Bank 切换是瞬时 Host/Runtime 视图状态，不进 Project Truth、不记录事件；四个 user Bank 维持单代全驻留

- 日期：2026-08-28
- 解决的问题：`docs/prd/questions/perform-bank-switch-classification.md`
  （问题文件已按约定在本决策的同一个 Task 删除），GitHub Issue
  [#386](https://github.com/endaye/lmdj/issues/386)。
- 结论：
  1. **视图状态，不进 Project Truth。** 当前激活的 Bank 视图是 Host/Runtime
     瞬时状态，对齐「Provider 选择属于 Workspace/Host 设置」的既有分类先例。
     Project Truth 不保存「上次激活的 Bank」或任何 Bank 视图字段。
  2. **瞬时生效，无音乐边界。** Bank 切换改变的是手指所及的 Pad，不改变任何
     已调度的声音，因此不走 SR-D11 的 selection-request 边界机制，点击即生效。
     Koala 手册 §2.1 的 A/B/C/D 即时切签是产品对照。
  3. **不记录 bank_switch 事件。** Pattern 与 Performance 事件引用的 Pad Slot
     本身就是 Bank + Pad 位置（v3 §6.6 约定），事件自描述；Koala 的 Sequence
     同样跨 Bank 记音符而无 Bank 事件。Performance 事件词汇（见
     [同日 Performance 对象决策](2026-08-28-perform-performance-object-v4.md)）
     不含 Bank 切换。
  4. **单代全驻留是显式配额约束，作为 #357 的输入。** 全部 64 Pad / 4 Bank
     维持在一个 prepared generation 内物化（现行 Cooker 模型保留）：
     `decoded_float_pcm_bytes_total`（Web 档 128 MiB）约束**单个 generation 内
     四个 user Bank 的 prepared 字节总和**；每 Bank 仍受 64 MiB Bank 配额；
     发布瞬间的最坏情形是 live + pending 两代对 total 记账（D1 第 6 条既有
     语义）。Perform 的无缝 Bank 切换是维持全驻留的产品理由：懒加载
     per-Bank 会在演出中引入准备延迟与新的失败模式，被否定。
- 原因：Koala 的 Bank 是纯视图切签，无边界、无事件、无延迟；D1 的内存数学
  （4×≤64 MiB 且总和 ≤128 MiB，512 MiB 堆内两代共存）已经闭合，全驻留不需要
  抬堆；slot 自描述使 Bank 事件成为冗余的 Contract 面。
- 影响：本决策为纯文档权威，不改活动 manifest、Contract 工件、模块版本或
  Product Build。为 [#357](https://github.com/endaye/lmdj/issues/357) 提供
  「total 约束单代全 Bank 总和」的明确输入；#357 的记账决策不得推翻本条的
  全驻留结论，除非经新决策文件明确替代。Stage 10 设计规格草稿
  （`docs/design/2026-08-28-lmdj-stage10-perform-design.md`
  P10-D4）在同一 Task 去除待决标注。关闭 #386。
