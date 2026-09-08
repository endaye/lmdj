# LMDJ Material Pipeline V1 设计

状态：设计讨论已批准，书面 Spec 待用户复核
日期：2026-07-26

## 1. 背景

当前正式上传链仍默认调用冻结的参考 demo pipeline。该 pipeline 先把分离结果兼容为
`drums / bass / melody` 三条逻辑轨，其中 `melody = vocals + other`；随后最多切出
6 个 sample。Patchify 再把同类 Element 聚合到少数语义 Pad，因此一首歌虽然可能
产出多个 wav，工作台通常只显示 Drums、Bass、Harmony 三个活跃 Pad。

Stage 1 已经把产品表面扩展为固定 16 个数据 Pad，但索引 `8..15` 在没有更多素材时
仍然是 Empty。要让 16 Pad 成为真正可演奏的素材系统，不能只提高
`max_samples`，也不能继续扩建 `references/demos/lmdj-song-pipeline/`。新的正式
链路需要在 Owned Product Boundary 内建立从规范四轨到独立素材的稳定契约。

## 2. 目标

对一首 MP3 或 WAV 自动生成最多 16 个高质量、位置固定、可独立演奏的 Material：

- 鼓使用 one-shot；
- Bass、Melody、Vocal 使用节拍对齐的 loop；
- Vocal 与 Other 独立，不再把 Vocal 合并进 Melody；
- 完整原曲乐句使用排他 loop；
- 素材数量服从内容和质量，不设置最低数量；
- 未通过质量门槛的位置输出真实 Empty Pad；
- 同一输入、模型、Timing 和配置产生确定性相同的产物与 `patch_id`；
- Web、API 和 Export 继续以 `patch.json` 为产品真相，不读取内部 Material 契约。

## 3. 非目标

本设计不包含：

- 为了填满 16 Pad 而生成低质量或合成素材；
- 生成式音色替换、AI Variation 或自动 Remix；
- Sampler Start/End、Chop、Swap、Roll 等用户编辑；
- Take 录制；
- 多 Scene 编排 UI；
- `.als` 等专有 DAW 工程文件；
- 在冻结的参考 demo 内增加正式产品功能；
- 新 pipeline 失败后在同一个 Job 内静默回退旧 pipeline。

## 4. 核心决策

### 4.1 新增正式 Material Package

在 Separator 与 Patchify 之间新增 `lmdj.materials.v1`。该契约由
`packages/core-models` 托管轻量模型与 JSON Schema，供 Audio Worker 写入、
Patchify 读取。

`lmdj.materials.v1` 是内部 producer/adapter 契约，不替代
`lmdj.patch.v1`。API 和 Web 仍然只消费 Patch 与 Export Source。

### 4.2 固定槽位而不是动态紧密排列

所有歌曲使用相同的角色与索引，保证键盘和 MIDI Controller 的肌肉记忆稳定。
未生成素材的位置保持 Empty，不把后续素材向前挤。

### 4.3 混合播放形态

- Kick、Snare、Hat、Percussion：one-shot；
- Bass、Melody、Vocal：1 小节或 2 小节 loop；
- Phrase：来自原始 Mix 的完整乐句 loop，使用排他播放组。

### 4.4 质量优先、数量开放

允许少于 6 个，也允许超过 8 个，但最多 16 个。素材数量本身不触发
`needs_review`；只有真实的 Timing、Separator 或音频质量风险才触发 Review。

## 5. 架构

```text
MP3/WAV
  ├─ Timing Analyzer ───────────────→ timing.json
  ├─ Separator ────────────────────→ drums / bass / vocals / other
  └─ Original Audio
                ↓
        Material Extractor
                ↓
  lmdj.materials.v1 package
  ├─ materials.json
  ├─ samples/*.wav
  └─ timing.json
                ↓
             Patchify
                ↓
     patch.json v1 + chart.mid
                ↓
       API / Web / Export
```

### 5.1 Timing Analyzer

Timing Analyzer 只从原始音频生成一份规范 Timing Artifact，至少包含：

- BPM 与置信度；
- 拍点和小节边界；
- 拍号；
- 16 分音符离散网格；
- 主时间窗；
- 可选的差异乐句候选窗。

所有 Separator 共享同一 Timing Artifact。Material Extractor 不从某一条 Stem
重新计算独立节拍，从而避免更换 Separator 后 Pad、Pattern 和 Loop 边界漂移。

### 5.2 Separator

Separator 输出规范四轨：

```text
drums.wav
bass.wav
vocals.wav
other.wav
```

Separator 只负责分离和记录 provenance，不决定 Pad、Material 数量或素材边界。
缺少规范轨、文件损坏、采样率或声道契约无效时，Job 失败。

### 5.3 Material Extractor

Material Extractor 在 Worker 的 DSP 隔离环境内运行，职责为：

- 从鼓轨建立 one-shot 候选并分类；
- 从 Bass、Other、Vocals 建立 loop 候选；
- 从原始 Mix 建立 Phrase 候选；
- 对候选执行硬门槛、质量评分和 A/B 差异评分；
- 只写出 accepted 音频；
- 为全部 16 个槽位写出结构化决策；
- 基于主时间窗生成规范化 Pattern events；
- 写出 `lmdj.materials.v1` package。

### 5.4 Patchify

Patchify 新增 Material Package loader，将已经完成分析的 Material 确定性转换为
`patch.json`。Patchify 不读取原始音频、不运行 DSP、不重新评分。

旧 `lanes.json + chart.mid` loader 暂时保留，用于历史 fixture、显式 legacy
Runner 和一个发布周期内的回滚。

### 5.5 API、Web 与 Export

- API Job 只公开状态、Patch、素材文件和 Export；
- Web 只通过 `loadPatch` 读取 `patch.json`；
- Export Source 可以列出真实 Stems、Samples、MIDI、Timing 与 provenance；
- `materials.json` 不成为浏览器或 API route 的备用真相源。

## 6. 固定 16 槽布局

| Index | Pad | Role | Source | Kind |
| ---: | --- | --- | --- | --- |
| 0 | Kick A | `kick` | `drums` | `one_shot` |
| 1 | Snare A | `snare` | `drums` | `one_shot` |
| 2 | Hat A | `hat` | `drums` | `one_shot` |
| 3 | Percussion A | `percussion` | `drums` | `one_shot` |
| 4 | Bass A | `bass` | `bass` | `loop` |
| 5 | Melody A | `melody` | `other` | `loop` |
| 6 | Vocal A | `vocal` | `vocals` | `loop` |
| 7 | Phrase A | `full_mix_phrase` | `original` | `full_mix_phrase` |
| 8 | Kick B | `kick` | `drums` | `one_shot` |
| 9 | Snare B | `snare` | `drums` | `one_shot` |
| 10 | Hat B | `hat` | `drums` | `one_shot` |
| 11 | Percussion B | `percussion` | `drums` | `one_shot` |
| 12 | Bass B | `bass` | `bass` | `loop` |
| 13 | Melody B | `melody` | `other` | `loop` |
| 14 | Vocal B | `vocal` | `vocals` | `loop` |
| 15 | Phrase B | `full_mix_phrase` | `original` | `full_mix_phrase` |

约束：

- 每个槽位最多一个 accepted Material；
- B 必须引用同角色的 A，不能在 A 缺失时单独存在；
- Phrase 使用固定 exclusive group；
- 没有 accepted Material 的位置必须在 Patch 中成为 `action: "empty"`；
- UI 不补齐、不截断、不重新排列。

## 7. `lmdj.materials.v1` 契约

规范化结构：

```json
{
  "schema": "lmdj.materials.v1",
  "source": {
    "audio_sha256": "full-hex"
  },
  "provenance": {
    "separator_id": "separator-id",
    "separator_checkpoint_sha256": "full-hex",
    "separator_runner_version": "version",
    "timing_version": "version",
    "extractor_runner_version": "version",
    "extraction_config_version": "version",
    "environment_lock_sha256": "full-hex"
  },
  "timing": {
    "bpm": 112.0,
    "beats_per_bar": 4,
    "grid_per_beat": 4,
    "length_steps": 64,
    "artifact": "timing.json"
  },
  "materials": [
    {
      "material_id": "mat_kick_a",
      "slot_index": 0,
      "role": "kick",
      "variant": "A",
      "variant_of": null,
      "kind": "one_shot",
      "source_stem": "drums",
      "audio_path": "samples/kick-a.wav",
      "playback": {
        "quantize": "1/16",
        "exclusive_group": null
      },
      "quality": {
        "status": "accepted",
        "score": 0.91,
        "warnings": []
      }
    }
  ],
  "pattern": {
    "pattern_id": "pattern_primary",
    "length_steps": 64,
    "events": [
      {
        "material_id": "mat_kick_a",
        "step": 0,
        "velocity": 108
      }
    ]
  },
  "slot_decisions": [
    {
      "slot_index": 14,
      "status": "empty",
      "reason": "variant_not_distinct"
    }
  ]
}
```

### 7.1 必要一致性约束

- `schema` 必须等于 `lmdj.materials.v1`；
- `timing.artifact` 和全部 Material `audio_path` 必须是 package root 内的安全
  相对路径；
- `slot_index` 必须在 `0..15`，并且 accepted Material 间唯一；
- `material_id` 必须唯一；
- 每个 Pattern event 必须引用 accepted Material；
- event `step` 必须在 `0..length_steps-1`；
- `slot_decisions` 必须恰好覆盖 `0..15`；
- accepted 决策必须对应同索引 Material；
- empty 决策不能对应 Material；
- B 的 `variant_of` 必须引用同角色 A；
- one-shot 只能来自鼓轨；
- Vocal 只能来自独立 vocals Stem；
- Phrase 只能来自 original，并使用 `full_mix_exclusive`；
- 至少一个 Material 才能进入 Patchify。

### 7.2 Empty 原因

V1 使用稳定 reason code：

- `source_silent`
- `no_candidate`
- `classification_low_confidence`
- `quality_below_threshold`
- `variant_not_distinct`
- `no_valid_loop_boundary`
- `source_stem_unavailable`

人类可读说明可以作为附加 metadata，但测试和业务判断只依赖 reason code。

### 7.3 Pattern 边界

`pattern` 只描述主时间窗的默认演奏，不承诺多 Scene：

- 鼓 onset 归到距离最近的 accepted A/B 原型；只有 A 时全部归 A；
- 对应主时间窗的 Bass、Melody 和 Vocal A 可以在 step 0 触发；
- B loop 和 Phrase 默认是手动可触发素材，不因存在就自动进入主 Pattern；
- `chart.mid` 从规范 Pattern events 确定性生成；
- 后续多 Scene 需要独立设计，不在 V1 中隐式推断。

## 8. 素材提取

### 8.1 鼓 one-shot

从主时间窗的 drums Stem 检测 onset，对候选提取以下特征：

- 低、中、高频能量分布；
- spectral centroid；
- 瞬态斜率与峰值；
- 起音前静音；
- onset 到下一击的可用尾长；
- 底噪、削波和多击重叠。

候选分类为 Kick、Snare、Hat 或 Percussion。每类最高质量候选成为 A；第二候选
只有在自身质量和相对 A 差异都达标时成为 B。one-shot 最终时长限制为
`80–600ms`，只执行去直流、门限、短淡入淡出和安全峰值归一化，不进行生成式
处理。

### 8.2 Bass、Melody 与 Vocal loop

Extractor 从 Timing Artifact 提供的 1 小节和 2 小节窗口建立候选：

- Bass 只读取 bass Stem；
- Melody 只读取 other Stem；
- Vocal 只读取 vocals Stem；
- Vocal 不存在或不合格时保持 Empty，不合并到 Melody。

A 是质量最高且最具代表性的窗口。B 必须质量合格，并与 A 在节奏、音高轮廓或
音色特征上达到差异门槛。Loop 只允许节拍对齐的边界，并使用短 equal-power
crossfade 修整接缝。

### 8.3 Phrase A/B

Phrase 直接来自原始 Mix：

- A 选择质量最高的代表性完整乐句；
- B 来自不同候选段落，且与 A 达到差异门槛；
- Phrase 不宣称是独立 Stem；
- Phrase 使用 `full_mix_exclusive`；
- 触发 Phrase 时停止普通素材，触发普通素材时停止 Phrase，避免重音和相位叠加。

## 9. 质量模型

所有门槛和权重集中在带版本号的 `MaterialExtractionConfig`，并把版本写入
provenance。算法代码不得散落未记录的常量。

### 9.1 硬门槛

候选必须满足：

- 文件可解码；
- 非静音；
- 无不可修复削波；
- 时长在角色合法范围内；
- one-shot 有明确 onset；
- loop 有有效 Timing 边界；
- Stem 泄漏不超过拒绝线。

任一硬门槛失败即拒绝，不进入总分排序。

### 9.2 总分

通过硬门槛的候选得到 `0..1` 质量分：

- one-shot：类型置信度、瞬态清晰度、尾音完整度、洁净度；
- loop：边界连续性、Timing 对齐、有效能量、泄漏、代表性；
- Phrase：边界连续性、Timing 对齐、有效能量、段落代表性。

V1 接受线为：

```text
quality_score >= 0.70
```

B 变体额外要求：

```text
quality_score >= 0.70
normalized_difference_from_a >= 0.25
```

上线前使用固定曲库和盲听校准特征归一化与权重；一旦发布配置版本，该版本的
门槛、权重和特征实现必须冻结。后续调整使用新配置版本。

### 9.3 Patch 质量

- `passed`：所有 accepted Material 均无 review warning；
- `needs_review`：产物可播放，但 Timing、Separator 或边界修整有明确 warning；
- `failed`：零 accepted Material，或任一必要契约/文件校验失败。

素材少于 6、没有 Vocal、没有 B 变体都不是 warning。

## 10. Patchify 映射

Material loader 按 `slot_index` 直接映射，不再通过文件名猜测角色：

- accepted Material 生成一个 Element 和一个 live Pad；
- Empty 决策生成 `action: "empty"` Pad；
- one-shot Pad 使用 one-shot trigger；
- loop Pad 使用 loop trigger；
- Phrase Pad 写入排他播放 behavior；
- Pattern events 转换为 `lmdj.patch.v1` Note；
- Scene 继续覆盖全部 `0..15`；
- 未映射 Material 属于契约错误，不作为 metadata 静默保留。

旧 standard-profile mapper 只服务 legacy package，不参与 Material Package 路径。

## 11. Job 状态与错误处理

新的 `CreatorPipelineRunner` 发射：

```text
queued
  → separating
  → extracting
  → patchifying
  → completed | failed
```

### 11.1 状态职责

- `queued`：输入已通过 API preflight 并复制到 Job；
- `separating`：执行规范 Timing 和四轨分离；
- `extracting`：生成并验证 Material Package；
- `patchifying`：生成 Patch、MIDI、Export Source 和 metadata；
- `completed`：Patch 可播放，quality 为 `passed | needs_review`；
- `failed`：必要阶段失败，错误原子写入 `status.json`。

Web Processing UI 必须认识 `extracting`，不能把合法状态显示为 Unknown。

### 11.2 失败边界

以下情况失败：

- Timing 或 Separator 子进程失败、超时或产物无效；
- Material Extractor 崩溃或输出无效；
- 零 accepted Material；
- Schema、路径、引用或固定槽位约束失败；
- Patchify 或最终 Patch contract 校验失败。

Key 等非播放必要 metadata 仍可降级为 Export warning，不使可播放 Job 失败。

## 12. 确定性与身份

Material Package 和 Patch 的规范序列化必须稳定。新 Material 路径的
`patch_id` 为：

```text
{source_id}-{sha256(
  canonical timing
  + canonical accepted materials
  + canonical pattern events
  + extraction config version
)[:8]}
```

Separator checkpoint、runner、Timing、Extractor、环境锁和配置版本完整写入
provenance；它们的输出变化会通过规范内容影响 digest。同一输入、相同
checkpoint、相同环境锁和相同配置重复运行，必须得到相同：

- slot decisions；
- Material metadata；
- sample SHA-256；
- Pattern events；
- `patch_id`。

随机 Job ID、Job 目录和 status 时间戳继续保持 run-scoped。

## 13. Pipeline 选择与回滚

V1 使用显式配置为新 Job 选择 Runner：

```text
LMDJ_PIPELINE=legacy
LMDJ_PIPELINE=materials-v1
```

规则：

- 在 Job 创建前决定 pipeline；
- 实际 pipeline 写入 Job provenance；
- 新 pipeline 失败后不在同一 Job 内静默调用 legacy；
- 修改配置只影响新 Job；
- 已完成 Job 的产物和身份不变；
- legacy 保留一个成功发布周期，然后另行决定是否退休。

## 14. 实施切片

### Slice 1：Material Contract + Patchify

- 增加 `lmdj.materials.v1` 模型与 Schema；
- 建立真实结构的固定 Material Package fixture；
- 实现 Material loader 与固定 16 槽映射；
- 保留 legacy loader；
- 验证 Empty、A/B、Pattern、路径和 Phrase behavior。

### Slice 2：Material Extractor

- 使用固定原始音频、四轨 Stem 和 Timing fixture；
- 实现鼓 A/B one-shot；
- 实现 Bass、Melody、Vocal A/B loop；
- 实现 Phrase A/B；
- 实现评分、slot decisions 与 provenance。

### Slice 3：Creator Pipeline Runner

- 编排 Timing、Separator、Extractor、Patchify与 Export；
- 发射 `extracting`；
- 加入显式 pipeline 选择；
- API 默认值暂时保持 legacy。

### Slice 4：Web 播放语义

- Processing UI 支持 `extracting`；
- 16 Pad 严格按 Patch 渲染；
- 实现 Phrase 排他播放；
- Empty、缺失音频和 reserved action 继续安全 no-op。

### Slice 5：Release Evidence 与默认晋升

- 固定曲库重复性验证；
- 新旧 pipeline 盲听与可演奏性对照；
- 实体 8-Pad Bank A/B 和原生 16-Pad Controller；
- Creator Export 与 Ableton Live Smoke；
- 门槛通过后另行提交默认 Runner 晋升。

## 15. 测试与验收

### 15.1 Contract

- Schema happy path；
- 非法 slot、重复 slot、缺少决策；
- B 没有 A；
- event 引用不存在 Material；
- 越界 step；
- package root 路径逃逸；
- Phrase 来源或 exclusive group 错误；
- accepted/empty 决策与 Material 不一致。

### 15.2 Extractor

- 四类鼓 A 候选；
- 质量差时角色 Empty；
- B 差异不足时拒绝；
- Vocal 缺失不合并到 Melody；
- 1/2 小节 loop 对齐；
- 接缝、静音、削波和泄漏硬门槛；
- 少于 6 和超过 8 的合法产物；
- 最多 16；
- 零 accepted Material 失败。

### 15.3 Patchify

- 16 Pad、连续索引、固定角色；
- Empty no-op；
- Pattern 引用完整；
- Phrase 排他 metadata；
- legacy fixture 继续通过；
- Material 路径不读取 `lanes.json` 或重解析 MIDI。

### 15.4 Worker/API/Web

- 完整状态序列含 `extracting`；
- 每个状态原子落盘；
- pipeline 选择写入 provenance；
- materials-v1 失败不触发 legacy；
- Web 正确显示 extracting；
- Phrase 与普通素材双向排他；
- Export 只列真实存在的 Stem、Sample 和 MIDI。

### 15.5 Release Evidence

固定曲库至少覆盖：

- 有人声与纯器乐；
- 简单鼓与复杂鼓；
- 电子音乐与现场录音；
- 少于 6 个与超过 8 个 Material；
- 没有任何合格 Material 的失败案例。

每首固定测试音频连续运行三次，并比较 Material JSON、sample hash、Pattern events
与 `patch_id`。完成盲听、键盘、真实 MIDI Controller、Creator Export 和 Ableton
Live Smoke 后，才允许把 `materials-v1` 设为默认。

## 16. 最终验收条件

```text
1 <= accepted materials <= 16
固定 role 永远落在固定 slot
B 不得在 A 缺失时存在
所有 loop 对齐同一个 Timing Artifact
所有输出路径限制在 package root
少于 6 个素材仍可 completed
0 个素材必须 failed
同配置重复运行结果完全一致
Web/API 不直接读取 materials.json
旧 pipeline 可显式选择，但不静默接管失败 Job
```
