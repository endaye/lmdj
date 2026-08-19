# Provider SDK 的 Artifact 字节访问由谁提供：输入 resolver 与输出访问口分别落在哪一层？

- 范围：新内核（Playable Beat Instrument）
- 状态：待架构设计
- 来源：[2026-07-30 新内核设计](../../superpowers/specs/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md)评审
- 为什么重要：已批准的 `lmdj.capability.v2` 能用显式端口确定声明的 Schema 身份，但 `ArtifactRef` 不携带 Schema provenance，AttemptStore 也没有输入 Artifact resolver，不能把端口身份校验伪装成字节级 Schema 校验。2026-08-16 的 analysis-bench 原型进一步确认这个缺口是**双向**的：输出侧 SDK 同样没有读取已提交 Artifact bytes 的访问口，Host 只能按 `.lmdj-workspace/attempts/` 私有磁盘布局重建路径；原型的 Host 注入桥接是临时方案，不得直接毕业为正式接口（见 [decision-log](../decision-log.md) 2026-08-16 条目）。
- 处理时点：首个需要解析结构化 Artifact bytes 的正式 Capability 实现前，单独设计输入 resolver、输出字节访问口与验证器边界。
- 2026-08-19 补充驱动：确定性 Attempt 重放 Provider（见
  [计划](../../superpowers/plans/2026-08-19-lmdj-attempt-replay-provider.md)）
  是撞上同一面墙的**第二个独立消费方**，且它只需要**输入侧**读取口。它把缺口
  与 `CLAUDE.md` 的架构不变量直接对上了：不变量写的是「Provider code receives
  Artifact inputs and an Artifact output sink」，而 `Provider::run` 目前只收到
  写入用的 `ArtifactSink` 与不可读的内容寻址描述符，输入侧尚未实现。该计划同时
  给出一个不依赖本问题的退路（把 fixture 字节嵌进已被 source-package 哈希覆盖的
  `src/provider.cpp`），所以本问题不因它变得紧急；但它说明结论一旦落地，受益方
  不止一个。
