# 已确认：长素材配额记账修正——total 约束单 generation、驻留是独立命名量、Web 摄取内存包络与物理验收阈值定死

- 日期：2026-08-28
- 解决的问题：GitHub Issue
  [#357](https://github.com/endaye/lmdj/issues/357)（#341 2026-08-27
  readiness audit 发现的实现前记账缺口）。本文件是
  [2026-08-26 D1 决策](2026-08-26-long-material-quota-and-bpm-stretch.md)
  的修正案（amendment）：不推翻 D1 的产品语义，只补齐 D1 未指明的
  所有权域、发布记账、Facade 精确表面、Web 解码内存包络与物理验收
  阈值。实施计划
  [`2026-08-27-lmdj-long-material-quota.md`](../../superpowers/plans/2026-08-27-lmdj-long-material-quota.md)
  的 "Provisional Quota and Ingest Inputs" 全部由本文件定死。
- 结论：

  **A1 命名量与所有权域（三个命名量，域互不重叠）**

  1. **`decoded_float_pcm_bytes_per_bank` = 67,108,864（64 MiB，数值不变，
     域定死）。** 约束对象是**单一 Project revision 下每个 16-Pad 用户
     Bank（bank 0–3）的 prepared-PCM 字节和**。它是 Project Truth 层的
     确定性创作配额，与运行时发布状态无关。失败类别
     `BANK_QUOTA_EXHAUSTED`。
  2. **`decoded_float_pcm_bytes_total` = 134,217,728（128 MiB，数值不变，
     域定死）。** 约束对象是**同一 Project revision 下全部四个用户 Bank
     的 prepared 字节总和**。由于一个 generation 物化整个 Project 的
     64 个 Pad，它同时就是任何单个 `PreparedSampleBank` generation 的
     字节上界——"total 约束 Project revision" 与 "total 约束单
     generation" 是同一件事。它同样是 Project Truth 层确定性配额。
     失败类别 `PROJECT_QUOTA_EXHAUSTED`（新增，见 A6）。
     推论：**四个 Bank 同时全满（4 × 64 MiB = 256 MiB）不被支持**；
     这不是本修正案新加的收敛，而是 D1 已批准的 128 MiB total 数值的
     内在含义（见 A3 内存账）。D1 的主场景——单 Pad 长素材吃满一个
     Bank——不受影响。
  3. **`decoded_float_pcm_bytes_resident` = 268,435,456（256 MiB，新命名
     量）。** 约束对象是**发布驻留**：live、pending、retiring 全部未回收
     generation 的 prepared 字节和，加上候选 generation。由发布所有者
     记账（Web 控制运行时既有的 `reserved_live_bytes`
     回收→预留→发布台账保留，仅上界从 134,217,728 改为本值；将来
     原生 Host 的发布所有者承担同一责任）。取值 = 2 × total，因此
     **任何合法 generation 在前一 generation 声部排空回收后总能发布**
     ——驻留超限是 Attempt 级瞬态背压（可重试），按构造不会永久失败。
     它**不是** Contract 配额错误，不写入 Project Truth，永不使用 A6
     的两个配额错误码（对齐"Provider/发布失败归 Attempt 状态"不变式）。
  4. `lmdj::audio::RuntimePreparationLimits` 字段定死为：
     `maximum_artifact_bytes`（保留）、`maximum_user_bank_bytes`（新增，
     = per_bank）、`maximum_generation_bytes`（由
     `maximum_prepared_bank_bytes` 改名，= total）、
     `maximum_resident_bytes`（由 `maximum_live_bank_bytes` 改名，
     = resident）。`maximum_decoded_frames_per_pad` 与
     `allows_decoded_frames_per_pad` 删除。这是公开结构的破坏性变更，
     audio-runtime `1.0.0 → 2.0.0` 确认（见 A10）。

  **A2 记账口径（字节精确）**

  5. 每 Pad 记账字节 = `prepared_frames × 4`（48 kHz 单声道 float），
     其中 `prepared_frames = ceil(source_frames × 48000 /
     source_sample_rate)`（与现有 44.1 kHz 重采样进位口径一致）。
     Trim 不减少记账——整段 Asset 的 prepared 帧驻留，播放裁剪只是
     start/end。Bank 用量 = 其 16 个 Pad 记账和；Project 用量 = 四个
     Bank 之和。提交校验**不计目标 Pad 当前占用**（赋值即替换，被
     替换 Asset 的字节在同一 revision 变更中释放）。

  **A3 512 MiB Wasm 堆内峰值与稳态内存账**

  6. 记 G = 134,217,728（total/generation 上界）、B = 67,108,864
     （单 Bank 上界，也是单 Pad 可能的最大记账）、A = 68,157,440
     （提交选区 Artifact 上限，见 A8）、H = 536,870,912（堆，不变）。
     快照源为 48 kHz 立体声 PCM16 时源字节 = prepared 字节（帧 × 2 声道
     × 2 B = 帧 × 4 B），是最坏情形；44.1 kHz 或单声道更小。逐阶段
     峰值（静态占用之外）：
     - 稳态：live generation ≤ G = 134,217,728。
     - Cook 阶段：live G + 构建中快照解码 PCM16 ≤ G + 单 Pad artifact
       瞬态 ≤ A → ≤ 336,592,896（≈321 MiB）。
     - `from_snapshot` 阶段（全程最坏点）：live G + 快照 G + 构建中
       bank ≤ G + 单 Pad 临时 mono 向量 ≤ B → **3G + B = 469,762,048
       （448 MiB）**。
     - 发布窗口：retiring G + 新 live G + 快照 G（发布后释放）→ 3G =
       402,653,184（384 MiB）；快照释放后驻留 ≤ resident =
       268,435,456。
     - 静态包络（Wasm 代码/栈/WASMFS 缓存/捕获缓冲 ≤ 23,040,000
       （60 s × 48,000 × 2 声道 × 4 B）/杂项）：**≤ H − 469,762,048 =
       67,108,864（64 MiB）**。#346 的自动化验收记录实测静态占用；
       #359 的物理证据验证最坏 fixture 不触发页面回收（见 A9）。
     - 反证：若 total 允许 4 × B = 256 MiB 的 generation，仅
       `from_snapshot` 峰值即 3 × 256 MiB + 64 MiB = 832 MiB ≫ 512 MiB，
       数学上不成立。这就是 total 必须约束单 generation 的原因。
     - 备注：`set_sample` 现以拷贝落库（临时 mono 与 bank 内副本共存
       贡献了 +B 项）；Task 1 可改为移动语义把全程峰值降到 3G =
       402,653,184，属可选优化，不是本决策的义务。

  **A4 发布/记账策略**

  7. lock-free 三态发布（current/pending/retiring/reclaimable，实时读
     路径无锁）**保持不变**。全部配额校验发生在 Project Truth 提交
     边界（确定性、非破坏：拒绝时 Project Truth 与现役 generation
     字节不变，对齐
     [2026-08-24 非破坏拒绝决策](2026-08-24-refused-audio-activation-non-destructive.md)）。
     发布驻留由发布所有者的既有"先回收、再预留、后发布"台账负责
     （顺序不变，上界改 resident），并新增一条**cook 前置预检**：
     发布所有者在开始昂贵的 cook/准备之前必须先回收，且满足
     `reserved ≤ resident − total`（即已驻留 ≤ 134,217,728）才可开始；
     否则直接以同一瞬态背压类别拒绝，不进入 cook。候选 generation
     恒 ≤ total，因此该预检保证 A3 的 448 MiB 峰值账在任何时序下
     成立（无预检时，retiring 未排空 + 候选构建可达 576 MiB，超堆）。
     驻留背压与发布槽位背压
     （`bank_slots_full`）保持现有 Attempt/Host state 语义：Web 层
     报 `WEB_RUNTIME_RESOURCE_LIMIT`，`resource` 由 `live_bank_bytes`
     改名 `resident_pcm_bytes`，文案含 why+remedy（"等待播放排空后
     重试"），可重试，且**永不**映射为 `BANK_QUOTA_EXHAUSTED` 或
     `PROJECT_QUOTA_EXHAUSTED`。

  **A5 Facade 查询与提交绑定（精确表面）**

  8. 新查询 operation：**`sample.quota`**（query 类）。请求恰含
     `{"operation", "project_path", "slot"}`，`slot` 是既有
     `{"bank": 0–3, "pad": 0–15}` 目标 Pad 身份（Bank 由 slot 派生）。
     结果载荷（成功信封内）：

     ```json
     {
       "project_revision": 41,
       "slot": {"bank": 1, "pad": 3},
       "bank_quota_bytes": 67108864,
       "bank_used_bytes": 55108864,
       "bank_remaining_bytes": 12000000,
       "project_quota_bytes": 134217728,
       "project_used_bytes": 98217728,
       "project_remaining_bytes": 36000000,
       "effective_remaining_bytes": 12000000,
       "effective_remaining_frames": 3000000,
       "consumed": [
         {"slot": {"bank": 1, "pad": 0},
          "prepared_bytes": 40108864, "prepared_frames": 10027216},
         {"slot": {"bank": 1, "pad": 7},
          "prepared_bytes": 15000000, "prepared_frames": 3750000}
       ]
     }
     ```

     语义定死：`bank_used_bytes` 与 `project_used_bytes` **不含目标
     Pad 当前占用**（A2 的替换口径）；`consumed` 列出目标 Bank 内全部
     非空 Pad（含目标 Pad 现值，供 Host 呈现）；
     `effective_remaining_bytes = min(bank_remaining_bytes,
     project_remaining_bytes)`；`effective_remaining_frames =
     effective_remaining_bytes / 4`（配额是 4 的倍数，整除无余）。
  9. **revision 绑定与竞态前置条件。** 查询结果只对返回的
     `project_revision` 有效。Capture 与 Import 提交共用
     `sample.import.begin` 既有的 `expected_revision` 字段承载绑定；
     revision 漂移走既有 `REVISION_CONFLICT`，不产生虚假配额承诺。
     配额纯由 Project Truth 派生，发布驻留状态不进入查询与提交裁决，
     因此"预留漂移"按构造不存在——发布背压是提交成功之后的
     Attempt 级瞬态（A4）。
  10. **一致性保证。** revision 不变时查询与提交逐字节一致：恰
      `effective_remaining_frames` 的选区提交成功；
      `effective_remaining_frames + 1`（= +4 prepared 字节）以 binding
      类别拒绝。Host 只经 Facade 消费该查询，不解析 Project bundle、
      不复算配额。

  **A6 错误类别（两个新枚举，判定规则定死）**

  11. `lmdj.error.v1` 一次新增**两个**枚举成员：`BANK_QUOTA_EXHAUSTED`
      与 `PROJECT_QUOTA_EXHAUSTED`（Contract SemVer `1.0.0 → 1.1.0`，
      加法变更）；`lmdj::foundation::ErrorCode` 增加对应成员。判定
      规则：binding 约束 = remaining 较小者；两者相等时报
      `BANK_QUOTA_EXHAUSTED`（Bank 内补救同时修复两者）。全局失败
      **永不**伪装成 Bank 枯竭；两个码**永不**用于发布驻留背压。
      载荷最小形状：Bank 类按实施计划既有示例（bank、requested/
      remaining/quota 字节与帧、`consumed` 清单）；Project 类同构，
      携带 `project_used_bytes`/`project_quota_bytes`/
      `project_remaining_bytes` 与四个 Bank 的用量汇总。两类文案均
      含 why+remedy（缩短选区 / 释放 Pad / 换 Bank；Project 类补
      "释放任意 Bank 的 Pad"）。

  **A7 Web 摄取前置准入（Host 层，先拒后解码）**

  12. **支持容器/codec（按内容嗅探判定，fail-closed，不看扩展名）：**
      WAV（RIFF/WAVE：PCM16/24/32、float32）、MP3（MPEG-1/2 Layer
      III，允许 ID3）、MP4/M4A（AAC-LC/HE-AAC）、FLAC（`fLaC`）。
      其余（OGG/Opus/WebM/AIFF/…）拒绝；AIFF 因目标浏览器解码
      支持不一致排除，保证判定跨浏览器确定。
  13. **Pre-decode 守卫（元数据可判定时必须在解码前拒绝）：**
      源文件字节 > 104,857,600（`ingest_source_bytes`，读文件内容前按
      `File.size` 判）拒；声道数 > 2 拒；折算 48 kHz 的预计解码帧 >
      43,200,000（`ingest_decoded_frames`，15 分钟）拒。WAV（fmt/data）、
      FLAC（STREAMINFO）、MP4（mdhd）元数据精确；MP3 优先
      Xing/VBRI 头，无则按 CBR 码率估算；估算不可判定时放行至
      post-decode 精确检查。
  14. **解码与 post-decode 精确检查（必做）：** `decodeAudioData` 在
      48,000 Hz 的 `OfflineAudioContext` 上执行——解码输出即 runtime
      帧率，驻留 JS 堆，不占 512 MiB Wasm 堆。解码后强制检查：
      `numberOfChannels ≤ 2`、`length ≤ 43,200,000`（`sampleRate ==
      48000` 由构造保证）；超限立即释放并拒绝。
  15. **释放生命周期与 JS 堆包络：** 源 `ArrayBuffer` 在
      `decodeAudioData` 启动即被 detach（规范行为），Host 不得保留
      第二份源副本；解码 `AudioBuffer` 是唯一驻留副本，波形、试听、
      选区裁剪全部在其上进行；在以下点释放其全部引用——提交成功
      （选区 Artifact 编码完成后）、取消、替换/开始新导入、Project
      关闭、页面后台驱逐恢复。选区编码缓冲在提交响应后释放。JS 堆
      稳态 ≤ 43,200,000 × 2 × 4 = 345,600,000 字节；瞬态峰值 ≤
      104,857,600 + 345,600,000 = 450,457,600 字节。
  16. **失败载荷：** 每类拒绝（不支持的容器 / 源过大 / 过长 / 声道
      过多 / 解码失败 / post-decode 超限）携带 observed/limit 与
      why+remedy 文案（对齐 `gate-failure-readability` pitfall）。
      #346 的 Vitest/Playwright fixtures 覆盖每个守卫的
      boundary/boundary+1 对，并断言可判定格式的拒绝发生在解码之前、
      释放发生在第 15 条的点位。

  **A8 `imported_wav_bytes` 重定标**

  17. `imported_wav_bytes` = 68,157,440（65 MiB），语义 = 提交选区
      Artifact（PCM16 WAV）字节上限：full-quota 立体声选区
      16,777,216 帧 × 2 声道 × 2 B = 64 MiB payload + header 允差。
      约束顺序：Bank/Project 配额先于此上限生效，此上限只是编码
      合法性护栏。`maximum_artifact_bytes` 取同值。Capture 提交走
      完全相同的路径与上限。

  **A9 #359 物理验收（fixtures、测量方法、证据字段、阈值）**

  18. **Fixtures（#346 生成并入库 sha256）：**
      - `LM-OK-SONG`：≈3:30 立体声 44.1 kHz MP3——正常整首歌导入
        裁剪提交路径；
      - `LM-OK-BOUNDARY-INGEST`：FLAC 48 kHz 立体声恰 43,200,000 帧
        ——最大可解码源；
      - `LM-REJ-FRAMES`：FLAC 48 kHz 立体声 43,200,001 帧——
        pre-decode 拒；
      - `LM-REJ-SOURCE`：104,857,601 字节 MP3——读内容前拒；
      - `LM-REJ-CH`：6 声道 AAC——pre-decode 拒；
      - `LM-OK-COMMIT-BOUNDARY` / `LM-REJ-COMMIT-PLUS-4B`：对空 Bank
        裁剪至恰 `effective_remaining_frames` 提交成功 / +1 帧（+4
        字节）报 `BANK_QUOTA_EXHAUSTED`；
      - 生命周期序列：取消、替换、重新导入、页面后台/恢复清理各一。
  19. **测量方法：** macOS Safari 用 Web Inspector Timelines 的
      Memory 仪表并同时记录对应 WebContent 进程的 Activity Monitor
      footprint；物理 iPadOS 用 macOS 远程 Web Inspector 附加物理
      iPad 同法测量。每个 fixture 记录 baseline（导入前）、peak
      （解码/提交过程峰值）、post-release（释放点后 30 秒内）三值。
      浏览器自动化与桌面模拟不构成物理证据。
  20. **证据字段（`docs/release-evidence/` 逐行）：** 设备型号、OS 与
      Safari 版本、Product Build、完整 Git SHA、fixture 名 + sha256 +
      编码/解码维度、baseline/peak/post-release 字节、页面是否
      reload/终止、测量仪器与读数来源。
  21. **Pass/fail 判则：** (1) 全部 OK fixtures 完成全流程且页面无
      reload/无进程终止；(2) 全部 REJ fixtures 在规定边界前拒绝且
      文案含 why+remedy；(3) `LM-OK-BOUNDARY-INGEST` 的 peak ≤
      baseline + 536,870,912（450,457,600 瞬态上界 + 允差）；
      (4) 每个释放点后 30 秒内 post-release ≤ baseline + 67,108,864；
      (5) Wasm 堆恒为固定 512 MiB 身份，Host 侧源长度不得误报为
      Wasm 驻留。任一不满足即记 `unverified` 并阻塞 #341 关闭。
  22. **失败回退旋钮定死：** 物理证据不达标时，指定回退是**下调
      `ingest_decoded_frames`**（以新决策文件记录新值），不抬堆、
      不改配额模型、不改容器白名单。

  **A10 manifest 键集与版本分类（实施 Task 复制，不再裁量）**

  23. Web manifest `resource_limits` 键集定死：删除
      `decoded_frames_per_pad`；保留 `decoded_float_pcm_bytes_per_bank`
      = 67,108,864（语义改为 16-Pad 用户 Bank）、
      `decoded_float_pcm_bytes_total` = 134,217,728（语义 = Project
      revision 总量，即 generation 上界）；新增
      `decoded_float_pcm_bytes_resident` = 268,435,456、
      `ingest_source_bytes` = 104,857,600、`ingest_decoded_frames` =
      43,200,000、`ingest_channels` = 2；`imported_wav_bytes` =
      68,157,440。这是破坏性 manifest 迁移。
  24. 版本分类确认：audio-runtime `1.0.0 → 2.0.0`（A1 第 4 条字段
      删除/改名，破坏公开面）；application-facade `2.0.0 → 2.1.0`
      （加法查询 + 新错误类别，无破坏面）；project-cooker **无版本
      影响**（配额校验位于 Facade 回调与 `from_snapshot`，cooker 自身
      公开面不变；Task 1 审计确认后如有出入回到产品评审）；
      `lmdj.error.v1` `1.0.0 → 1.1.0`（一次加两个枚举）；
      web-runtime-platform `1.0.0 → 2.0.0`（第 23 条迁移）；
      web-runtime-host、creator-web 各 minor；core-cli/core-mcp/
      native-host 仅在透传新查询/新错误面时 minor，否则不动。
      Product Build 在 Task 4 整合边界按计划分配。

  **A11 Capture 对齐**

  25. 录音裁剪上限 = min(捕获缓冲帧数, `effective_remaining_frames`)
      （同一 `sample.quota` 查询、同一 revision 绑定）；creator-web 的
      `COMMIT_MAX_FRAMES` 常量删除。捕获缓冲保持 S8B-D3 的 60 秒与
      到顶自动停。

- 原因：128 MiB 的 total 数值在 D1 已批准，它与"四 Bank 各 64 MiB"
  能同时成立的唯一一致解释就是 total 约束单一 revision/generation、
  per-bank 是其内部的分域配额——A3 的内存账证明任何把 total 解释为
  跨 generation 驻留、同时允许 256 MiB generation 的组合都超出
  512 MiB 堆。把驻留拆成独立命名量并取 2 × total，使发布背压按构造
  瞬态化，从而配额裁决可以纯由 Project Truth 派生——这是"查询与
  提交逐字节一致"能够成立的结构性前提，而不是靠把发布状态塞进
  查询结果。Web 摄取的先拒后解码与单副本释放纪律，把不可控的
  浏览器解码膨胀限制在可计算的 450,457,600 字节 JS 堆包络内，剩余
  风险交给 #359 的物理阈值裁决，并预先指定失败旋钮避免二次评审。
- 影响：本决策为纯文档权威，不改活动 manifest、Contract 工件、模块
  版本或 Product Build；全部支付发生在 #343–#346 实施 Task（分类见
  A10）。实施计划的 provisional 输入区在同一 Task 由本文件的定值
  替换；#341/#343–#346/#359 的 Issue 正文在本决策合入后同步替换。
  `docs/prd/questions/project-bin-storage-model.md` 维持开放，不受
  本修正案影响。D1 其余条目（两层素材模型、长源裁剪模型、确定性
  校验与非破坏失败、sample 无 BPM）全部维持原样。
