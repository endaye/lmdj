# Perform Stereo WAV 录制在 Web/OPFS 上的有界资源模型是什么：capture ring 大小、OPFS 写带宽与背压、最大时长与产物身份？

- 范围：Stage 10 Perform
- GitHub Issue: #387
- 来源：[2026-07-30 新内核设计](../../superpowers/specs/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md) §7（Stereo WAV 录制、Replay、命名、导出）与 §11.4 录音路径；Stage 8B 采集缓冲有 60 秒上限（#241），Stage 8 输入契约为 PCM16 WAV 44.1/48 kHz（S8-D6）。
- 为什么重要：整场演出录制长达数分钟（PCM16 立体声 48 kHz 约 11.5 MB/min，float32 翻倍），在 512 MiB 固定 Wasm 堆内是第二条未计入 #357 记账的音频流。流式写 OPFS 需要明确背压语义（丢样本 / 干净停录 / 阻塞），且实时渲染路径绝不允许 glitch；SR-D17 的「溢出封存、已提交有效」是可参照的失败先例。macOS Safari 与 iPadOS 的 OPFS 持续写带宽无实测证据。产物是 Asset、Performance 属性还是仅导出，耦合 #384。
- 处理时点：Stage 10 实施计划之前；物理带宽 fixture 应并入现有物理验收积压。
