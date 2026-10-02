# 已确认：Web 音频激活中，输出设备启动单独计时，超时不封死 Runtime

- 日期：2026-10-01
- 解决的问题：[#1704](https://github.com/endaye/lmdj/issues/1704)（原 `docs/prd/questions/web-audio-activation-device-start-budget.md`，本 Task 删除）。
- 结论：
  1. 显式激活（用户手势）从 `AudioContext.resume()` 边缘到首个 AudioWorklet
     回调，属于输出设备启动，单独以 5 秒为上限（`runtime_session.mjs` 的
     `AUDIO_DEVICE_START_BOUND_MS`），不再计入 Control 的一秒 activation 预算。
  2. 一秒 Control 预算仍取 `operation_deadline("audio.activate")`，与 `trigger`、
     `audio.suspend` 相同，但改为从首个回调起算，覆盖 `audio.activate` 及其
     generation 确认。
  3. 显式激活中，`resume()` 在上限内未 settle（浏览器尚未允许 context 启动时会
     一直 pending），或设备在上限内未回调，此时都尚未向 Control 提交任何请求，
     因此是拒绝而不是封死：Runtime Session 把 context 重新挂起（仍 pending 的
     resume 也以 `suspend()` 撤回），保持 `audio-suspended`，
     并在 diagnostics 的 `activation_refusal` 记为 `audio_output_start_timeout`；
     `error_code` 不变，下一次手势照常重试。下一次尝试开始时清除该字段。
  4. 自动恢复沿用同一个 5 秒设备上限与回调后的一秒 Control 预算。由于 Control 已
     先行 park，设备仍未回调时照旧 fail closed（`HOST_TIMEOUT`，然后
     `restart-required`）。改为可重试需要新的恢复状态转换，不在本决策内。
  5. Worklet bootstrap（module 加载、master tap 构造、`startAudioWorklet`）仍不
     计入任何预算，也仍没有总上限。是否为 bootstrap 设上限是 #1704 评论中补充的
     范围，转为后续问题 [#1729](https://github.com/endaye/lmdj/issues/1729)，
     不在本决策内。
- 原因：
  - #1696 的实测表明，蓝牙 A2DP 冷启动单次就要 170–900 ms。
  - #1707 去掉了 Chromium 的二次启动，此后冷链路激活的预算占用中位数为 372 ms、
    p90 为 529 ms，但负载均值约 50 时仍有超时。超时会让 Runtime 进入
    `restart-required`，对一个只是慢一些的设备来说，这是破坏性后果。
  - Control 在首个回调后几毫秒内即确认，一秒预算要约束的控制路径因此不受影响。
  - 5 秒是观测最坏值（约 0.9 s）的数倍余量，并短于 bootstrap 等待 Runtime
    初始化的 30 s。
- 影响：
  - web-runtime-platform 的激活时序与 diagnostics 新增 `activation_refusal`
    字段，属于向后兼容的行为与诊断变化，并入该模块下一次版本切点欠下的 MINOR。
  - Creator 暂不展示 `activation_refusal`。"下一次手势即重试"的交互由 #1662
    负责。
  - 门户 `/platform/web-runtime/` 同步更新。
  - 真实 Safari 上的激活仍未自动化验证。
