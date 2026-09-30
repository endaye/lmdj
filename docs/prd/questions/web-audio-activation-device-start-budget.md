# 输出设备自身的启动时间是否应计入 Web 音频一秒 activation 预算？

- 范围：Web Runtime Platform 时序 Contract，Activate audio
- GitHub Issue: #1704
- 原迁移状态：待决
- 来源：#1696 与其修复 Pull Request（`fix/audio-activation-single-device-start`）
- 为什么重要：activation deadline 建立在 callback baseline 与 `AudioContext.resume()`
  边缘，值取自 `bridge.cpp` 的 `operation_deadline("audio.activate")`（一秒）。Control
  只在首个 open-gate audio callback 确认 activation，因此预算必然覆盖输出设备的启动。
  #1696 的修复去掉了 Chromium 在 Worklet module 就绪时对 running destination 的重启，
  首次激活从两次设备启动减为一次，但没有改变预算本身。
  - 2026-09-30 在 AirPods（A2DP）上，coreaudiod 记录的单次冷启动为 170–900 ms。
  - 修复后，冷链路激活的预算占用中位数为 372 ms，p90 为 529 ms，最大 620 ms（15 次）。
  - 在负载均值约 50 的主机上，7 次里仍有 1 次超时，Runtime 进入 `restart-required`。

  蓝牙耳机用户因此仍保留小概率的破坏性激活失败。
- 候选方向：
  1. 保持一秒覆盖整个 activation（含设备启动），即现状。
  2. Control deadline 从 `resume()` 后的首个 audio callback 起算，设备启动另设上限（数值
     待定，应来自实测分布）。
  3. 设备启动超时不再破坏性：首个 callback 之前尚未向 Control 提交任何请求，可以回到
     `audio-suspended` 并给出类型化、可重试的诊断，而不 seal Runtime。
- 处理时点：不阻塞当前 Koala parity 工作流；在把蓝牙输出列为已验证设备、或出现第二次
  现场复现之前裁决。
