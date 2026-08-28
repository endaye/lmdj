# 已确认：ResamplePerformance v1 走现场捕获——演出录音 Artifact 上选区、经 D1 长源 commit 路径写入 Pad；离线重渲染立为具名后续能力

- 日期：2026-08-28
- 解决的问题：`docs/prd/questions/perform-resample-performance-authority.md`
  （问题文件已按约定在本决策的同一个 Task 删除），GitHub Issue
  [#385](https://github.com/endaye/lmdj/issues/385)。
- 结论：
  1. **权威音频源是现场捕获。** Resample 的素材是演出期间母线录制产物
     （见[同日 WAV 录制决策](2026-08-28-perform-stereo-wav-host-streaming.md)），
     捕获的就是用户听到的一切，含全部 Momentary FX。Koala 手册 §4.1 的
     resample 即此语义（"play a sequence while using live effects in perform
     screen to capture longer passes"），Koala 从不以离线重渲染实现 resample。
  2. **选区与提交完全复用 D1 长源裁剪模型。** 波形、试听、范围选择在 Host 层
     的录音源上完成；只有选区经 Facade commit 进入 prepared 配额，走与
     Capture/导入**完全相同**的路径与校验：同一 Bank 配额判定、同一
     `bank_quota_exhausted` 失败类别与非破坏拒绝、同一 expected-revision
     绑定（[D1 第 4/5 条](2026-08-26-long-material-quota-and-bpm-stretch.md)）。
     不为 Resample 发明第二条提交路径。
  3. **Lineage。** 派生 Asset 记录：源录音 Artifact 内容哈希、选区范围、
     以及存在时的 Performance 身份与录制时 revision。目标 Pad 由用户选择，
     永不自动覆盖（重设计规格 §5.2）。
  4. **v1 无新 Job 类别。** 录制本身在 Host 层进行（见 WAV 决策）；选区
     commit 是原子 Facade Command。`ResamplePerformance` 因此不是长任务，
     不进 Job/Attempt 面。
  5. **离线重渲染是具名后续能力。** 从 Performance Events 确定性重渲染
     （Koala 对位物：主菜单 "bounce sequence to pad"）留待后续设计评审；
     届时以 FX 决策第 5 条的确定性规则为前置，走离线渲染产出 Derived
     Asset，**永不进实时引擎**（对齐 D2 time-stretch 的同款边界）。
  6. **推论：FX 离线确定性不是 Stage 10 硬前置。** 现场捕获录下的即渲染
     结果，Stage 10 不依赖离线复现八 FX。
- 原因：Koala 的 resample 是现场捕获；D1 已把「录音/导入在 commit 汇合」的
  路径建成，Resample 作为第三个 ingest 源零新机制接入；离线重渲染把八 FX
  的离线复现变成硬前置并使首版范围翻倍，被否定为 v1 路线。
- 影响：本决策为纯文档权威，不改活动 manifest、Contract 工件、模块版本或
  Product Build。实施时支付：Facade 的选区 commit Command 扩展 Lineage
  字段（若需要）、Creator 的 Resample 表面；配额与失败语义零新增。Stage 10
  规格草稿 P10-D11 在同一 Task 去除待决标注。关闭 #385。
