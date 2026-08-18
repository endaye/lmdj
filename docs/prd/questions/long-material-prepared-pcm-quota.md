# 长素材（如 60 秒 Loop）采用什么 prepared-PCM 资源模型：每 Pad 均匀上限改为 Bank 内共享配额，还是抬高固定堆？

- 范围：新内核（Playable Beat Instrument）
- 状态：待设计评审
- 来源：[2026-07-30 新内核设计](../../superpowers/specs/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md)评审
- 为什么重要：Stage 8B 设计评审（S8B-D10）确认：现行每 Pad 240,000 帧上限源自 64/128 MiB prepared-PCM 预算，60 秒素材在均匀模型下需要 369 MB/Bank，超过 512 MiB 固定堆；而共享配额可在不抬堆的前提下支持单 Pad ≈60 秒、全 Bank 合计 ≈174 秒立体声。该变更波及 Cooker Bank 分配、audio-runtime PreparedSampleBank 布局（lock-free 发布路径）、manifest 语义、Facade 校验与"他人占用配额"新失败类别。抬 1 GiB 堆被 iPadOS 单页内存限制排除。
- 处理时点：与 [Loop 素材 BPM Time-stretch 问题](loop-material-bpm-time-stretch.md)同一次设计评审（长素材大多是跟 BPM 的 Loop）。
