# 已确认：prepared-PCM 采用 Bank 共享配额（数值由 Host manifest 注入）；sample 无 BPM，全局 BPM 只驱动 Sequencer，Time-stretch 立为后续离线 opt-in 能力

- 日期：2026-08-26
- 解决的问题：`docs/prd/questions/long-material-prepared-pcm-quota.md`（D1）与
  `docs/prd/questions/loop-material-bpm-time-stretch.md`（D2）（两个问题文件已
  按约定在本决策的同一个 Task 删除），GitHub Issue
  [#237](https://github.com/endaye/lmdj/issues/237)（S8B-D10 具名后续阶段）。
  两问题按 S8B-D10 的既定安排在同一次评审解决：长素材大多是跟 BPM 的 Loop。
- 结论：

  **D1 长素材资源模型**

  1. **模型定在 Core，数值定在 Host。** 配额模型——校验规则、失败类别、
     发布记账——是 Host 无关的 Core 语义；具体数值是每个 Host/Product
     manifest 的 `resource_limits` 参数（现有
     `lmdj::audio::RuntimePreparationLimits` 注入结构保留并扩展）。512 MiB
     固定 Wasm 堆与"抬 1 GiB 被排除"是 **iPadOS Safari 单页面**约束，属于
     Web Host 数值层；原生 App Host 将来声明自己的更大数值，不需要再开一次
     资源模型评审。
  2. **Bank 共享配额，无单 Pad 上限。** 取消 `decoded_frames_per_pad`
     每 Pad 均匀上限；每 Bank 一个共享 prepared-PCM 字节配额，单 Pad 允许
     吃满整个 Bank 配额。Web 档数值不变：`decoded_float_pcm_bytes_per_bank
     = 67,108,864`（48 kHz float 下 ≈174.76 s 立体声 / ≈349.5 s 单声道），
     `decoded_float_pcm_bytes_total = 134,217,728`，堆维持 512 MiB。
     **Web 最大支持素材时长 = 单 Pad ≈174.76 s 立体声**（同 Bank 其余 Pad
     为空时）；均匀 60 s×16 模型（369 MB/Bank）在该堆下数学上不成立，故被
     否定。
  3. **两层素材模型：ingest（Host 层）与 prepared（Core 层）。** 录音与
     导入是同一资源模型的两个 ingest 源，上游不同、在 commit 汇合：
     - 录音（Capture）：Host 层采集缓冲（Web 沿用 S8B-D3 的 60 s 缓冲与
       到顶自动停），裁剪上限不再是 240,000 帧，而是目标 Bank 剩余配额与
       缓冲长度的较小者；
     - 导入（文件）：Host 层解码长源。Web 用浏览器 `decodeAudioData`，
       解码驻留 JS 堆，**不占 512 MiB Wasm 堆**；源侧上限是 Host 声明的
       ingest 数值（Web 档拟 ≤100 MiB 源文件，精确值在实施计划定死），
       不是 Core 配额。
  4. **长源裁剪模型。** 导入允许超过配额的长源文件（整首歌）；波形、试听、
     选区裁剪全部在 Host 层的源素材上完成；只有选区经 Facade commit 进入
     prepared 配额。提交的选区 Artifact 即 Pad 的 Asset（与 Capture 提交
     完全一致的路径与校验）。完整源文件的保留与事后再裁剪（Project Bin）
     不在本决策内——归
     [`project-bin-storage-model.md`](../questions/project-bin-storage-model.md)
     开放问题；在其解决前，重新裁剪需重新导入。
  5. **确定性校验与失败行为。** Facade 提供只读"Bank 剩余配额"查询，
     裁剪 UI 用它预先画出可选上限；commit 校验按
     `Bank 配额 − 同 Bank 其他 Pad prepared 字节` 确定性判定。新增失败
     类别 **`bank_quota_exhausted`（配额被其他 Pad 占用）**：拒绝提交、
     Project Truth 与现役 Bank 不变（非破坏，对齐
     [2026-08-24 拒绝音频激活非破坏决策](2026-08-24-refused-audio-activation-non-destructive.md)
     的口径）、错误载荷携带剩余配额（帧/字节）与该 Bank 各 Pad 的占用
     清单，呈现方式归 Host。
  6. **lock-free 发布不变式不变。** `PreparedSampleBank` 由每 Pad 定长
     步幅改为变长偏移表；仍是离线构建、原子发布，live/pending/retiring
     三态对 `decoded_float_pcm_bytes_total` 记账；实时读路径无锁性质不变。
  7. **manifest 语义。** `decoded_frames_per_pad` 退役；`imported_wav_bytes`
     语义改为"提交选区 Artifact 字节上限"，并抬到不先于 Bank 配额生效的值
     （Web 档拟 67,108,864）。精确键名、数值与迁移在实施计划的 Version
     Management 定。

  **D2 素材 BPM 与全局 BPM**

  8. **sample 无 BPM 属性；全局 BPM 只驱动 Sequencer。** Project Truth 不为
     Asset / Pad 增加 BPM 或速度字段；全局 BPM 只影响 sequencer tick 时钟、
     节拍器、Quantize/Swing 与 Pattern 切换；修改 BPM 永不改变任何 sample
     的播放速度或音高。对标 Koala 默认行为（官方手册 4.11：STRETCH 是逐
     sample 的付费 opt-in，开启后才 "locked to the song's tempo"；关闭时
     song tempo 不触碰 sample）。
  9. **v1 无 time-stretch，实时引擎零 DSP。** Audio Runtime 实时路径维持
     prepared PCM 播放 + 现有 trim/trigger/gain/mute；不引入任何
     stretch/pitch DSP；本决策不向 Capability 清单添加条目。BPM 不匹配的
     Loop 素材在 v1 按原速播放。
  10. **Time-stretch 立为具名后续能力：逐 Pad opt-in、离线烘焙。** 将来
      实现时走 Capability/Provider 离线渲染产出 Derived Asset（Koala 同样
      把 stretch 烘焙进重采样副本），**永不进实时引擎**；保音高与 REPITCH
      变调两类模式、支持比例与品质预期、实时/离线责任细分由该后续能力的
      设计评审定。Sound Set 携带的 BPM/Key 仍是浏览与映射元数据，不构成
      播放耦合。

- 原因：内存账确定了模型——60 s 均匀模型需 369 MB/Bank，超出 512 MiB
  Safari 单页堆，而 Bank 共享配额在不抬堆的前提下支持单 Pad 长素材；
  ingest/prepared 分层让"浏览器专属的数值限制"留在 Host 层，Core 只保留
  Host 无关的配额模型，原生 App 天然获得更大数值空间。取消单 Pad 上限是
  产品选择：一个 Pad 放整段长 Loop 是合法用法，代价（同 Bank 其余 Pad
  配额收窄）由剩余配额查询与确定性错误显式暴露。BPM 语义以 Koala 为对照
  证实：sample 本身无速度语义、stretch 是烘焙式 opt-in，这与现有
  `PadPlayback`（无 rate/pitch 字段）和实时引擎零 DSP 现状自洽，v1 零
  实现成本。
- 影响：本决策为纯文档权威，不改活动 manifest、Contract 工件、模块版本或
  Product Build。实施时支付：`audio-runtime`（PreparedSampleBank 变长
  布局）、`project-cooker`（Bank 分配）、`application-facade`（配额校验 +
  剩余配额查询）、`web-runtime-platform`（manifest gate 与 resource_limits
  键变更）各自的 SemVer；错误 Contract 新增 `bank_quota_exhausted` 失败
  类别；**无 Project Contract schema 变更**（Pad/Asset 不加字段）。
  resource_limits 属产品 Assembly 身份，实施 Task 触发 Product Build 与
  portal 快照义务；Portal 路由影响由实施计划声明。重设计规格首部的
  Time-stretch 开放问题指针在同一 Task 以勘误更正。实施 Issues 在本决策
  合入后创建（umbrella + Tasks），随后关闭 #237。
