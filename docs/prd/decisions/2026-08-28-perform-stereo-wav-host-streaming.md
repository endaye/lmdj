# 已确认：Perform Stereo WAV 录制是 Host 层母线 tap 流式写 OPFS（PCM16 48 kHz），上限归 Host manifest，写手落后按 SR-D17 先例封存；实时渲染永不受累

- 日期：2026-08-28
- 解决的问题：`docs/prd/questions/perform-stereo-wav-recording-bounds.md`
  （问题文件已按约定在本决策的同一个 Task 删除），GitHub Issue
  [#387](https://github.com/endaye/lmdj/issues/387)。
- 结论：
  1. **Host 层 ingest，引擎零改动。** 母线录制属 D1 两层模型的 Host 层
     ingest：Web 端在 AudioWorklet 内 tap 渲染输出，镜像 Stage 8B capture
     worklet 的批量投递模式（Float32 批经 JS 堆传出，**不占 512 MiB Wasm
     堆**——与 D1 对 `decodeAudioData` 的记账口径一致）；`RealtimeEngine`
     不加音频 capture ring。Native Host 到来时在其输出回调自建 tap。
  2. **流式写 OPFS。** 有界内存队列 + 后台写手持续落盘；不做「全量驻留
     内存、停录一次性写盘」。存储格式 PCM16 48 kHz 立体声
     （≈11.5 MB/min），与 S8-D6 输入契约兼容、可直接重导入。
  3. **绑定 transport。** 对照 Koala 手册 §6.2 Record a Song：进入录制
     待命后由 PLAY 启动录制，停止播放即停录；停录后显式命名保存或丢弃。
  4. **上限是 Host manifest 数值。** 录制最大字节/时长与队列深度是
     `resource_limits` 的 Host/Product manifest 参数（D1 第 1 条「模型定在
     Core、数值定在 Host」同款分层）；Web 档精确键名与数值在实施计划的
     Version Management 锁定。
  5. **失败契约：封存，不 glitch。** 写手落后越限、OPFS 写错误或达到上限
     时，录制在最后已耐久帧封存（SR-D17 先例）：已写前缀是合法 WAV 并可
     保存，尾部丢弃并明示用户；tap 只丢录制批次，**永不阻塞或干扰
     `render`**（零分配/零锁契约不变）。
  6. **物理证据义务。** Stage 10 验收前在物理验收集合中新增 OPFS 持续写
     带宽 fixture（macOS Safari 与实体 iPadOS 各一行，记录测得带宽、
     队列水位与封存触发阈值）；浏览器自动化不是物理证据。
  7. **产物身份。** 保存的录音成为不可变 Artifact，由 Performance 引用
     （[同日 Performance 对象决策](2026-08-28-perform-performance-object-v4.md)
     第 3 条），或在用户只要文件时直接导出。
- 原因：引擎级音频 ring 把实时代码改动与 stress 层验证拉进 Stage 10 范围，
  而 Host 层 tap 复用已交付的 Stage 8B 模式且天然符合 D1 的 ingest 分层；
  PCM16 较 float32 体积减半且可重导入；「录满内存再写」在数分钟录制下
  必然越界 512 MiB 堆。
- 影响：本决策为纯文档权威，不改活动 manifest、Contract 工件、模块版本或
  Product Build。实施时支付：`web-runtime-platform` 与 Creator 的录制
  管线、`resource_limits` 新键（manifest 级，触发 Product Build 义务）、
  物理验收账本新行。为 [#357](https://github.com/endaye/lmdj/issues/357)
  提供「录制流走 JS 堆、不进 Wasm 堆记账」的口径输入。Stage 10 规格草稿
  P10-D12 在同一 Task 去除待决标注。关闭 #387。
