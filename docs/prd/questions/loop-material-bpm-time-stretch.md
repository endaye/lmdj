# 素材 BPM ≠ Project BPM 时，Loop 类素材是否/如何 Time-stretch 跟随全局 BPM（含 Pitch-shift）？

- 范围：新内核（Playable Beat Instrument）
- 状态：待决
- 来源：[2026-07-30 新内核设计](../../superpowers/specs/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md)评审
- 为什么重要：“完整歌曲变成可演奏素材”+ 全局 BPM/Key 几乎必然遇到速度不匹配；决定 Audio Runtime 的 DSP 范围和 Capability 清单（Koala 有 Time-stretch 作为对照）。
- 处理时点：Audio Runtime Contract 定稿前的设计评审。
