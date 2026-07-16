# LMDJ Timing Analysis 与小节切分优化设计

日期：2026-07-16

状态：待评审

范围：Audio Worker 阶段 3 的 BPM、beat、downbeat 与候选 loop 分析

## 1. 背景

LMDJ 当前先通过 separator 生成 stems，再由 `PipelineFromStemsRunner` 完成阶段 3–6：候选 loop、小节与 sample 切分、MIDI 编排和 Patch 验收。

当前 timing 分析使用 `librosa.beat.beat_track` 检测 BPM/beat，并用和声变化、bass onset、kick 低频 onset 三路投票确定四拍中的 downbeat 相位。候选 loop 再按能量稳定度、首尾频谱相似度、onset 密度与切口干净程度评分。

这套方法适合当前以 4/4 拍 Hip-Hop 为主的 MVP，但存在一个架构性问题：`PipelineFromStemsRunner` 将 separator 输出重新相加作为 mix，并使用 separator 的 drums/bass 参与 timing 分析。更换 HT Demucs、SCNet 或 RoFormer 后，即使输入歌曲相同，也可能得到不同的 beat grid、downbeat 和候选窗口。这样既会让生产 Patch 随 separator 漂移，也会混淆多模型 benchmark——最终差异同时包含“分轨质量”和“切到了不同段落”。

## 2. 目标

1. 同一原始音频与同一 timing 配置必须产生稳定、可缓存的 timing artifact，不受 separator 选择影响。
2. 所有 separator 在 benchmark 和生产链路中共享同一组 beat、downbeat 与候选窗口，保证比较公平。
3. 识别 BPM 的 half/double tempo 歧义，不再只用 `max_bpm=130` 做单向折半。
4. 为 downbeat 和候选窗口提供可解释的分项、置信度与降级状态，不再静默接受弱判断。
5. 用合成 fixture、人工标注真实歌曲和跨 separator 一致性测试量化效果。
6. 第一版继续使用 librosa 与现有规则；只有评测证明规则方案达不到门槛时，才评估专用 beat/downbeat 模型。

## 3. 非目标

- 不改变 `lmdj.patch.v1`，Web、API 和 Patchify 不读取 timing artifact。
- 不在本阶段替换或重排 separator。
- 不重写鼓点聚类、sample 选择、MIDI 编排或 Patch 播放逻辑。
- V1 只正式支持固定 4/4 拍；3/4、6/8、变拍号歌曲必须标记为 unsupported 或 low confidence，不能伪装成可靠的 4/4 结果。
- 不把新功能写回冻结的 `references/demos/lmdj-song-pipeline/`。

## 4. 方案比较

### 4.1 方案 A：原始音频生成 canonical timing artifact（采用）

Audio Worker 在 separator 之前或与 separator 并行，从原始上传音频生成一次 timing artifact。后续所有 separator 与 `PipelineFromStemsRunner` 共用它。

优点：结果稳定、可缓存、模型比较公平；timing 分析与分轨职责清晰。缺点：需要新增内部契约，并调整 `PipelineFromStemsRunner` 输入。

### 4.2 方案 B：每个 separator 独立分析 timing（不采用）

保留当前方式，由每组 stems 自己检测 BPM/downbeat。

优点：改动小。缺点：separator 误差会放大成结构差异，benchmark 无法区分分轨质量和切点变化，不满足本设计目标。

### 4.3 方案 C：立即引入专用神经网络 beat/downbeat 模型（暂不采用）

优点：在复杂节奏、弱起或无鼓前奏上可能更稳。缺点：增加模型权重、运行时、设备兼容和新一轮 benchmark 成本；当前尚无数据证明 librosa 加规则无法达到产品门槛。

## 5. 总体架构

```text
原始上传音频
  ├─ TimingAnalyzer
  │    └─ timing.json (lmdj.timing.v1, 按 input/config hash 缓存)
  │
  └─ SeparatorRunner
       └─ canonical stems (lmdj.separation.v1)

timing.json + canonical stems
  → compatibility mapping (melody = vocals + other)
  → PipelineFromStemsRunner
  → samples / chart.mid / lanes.json / report.json
  → Patchify
```

`TimingAnalyzer` 只读取原始音频和显式 `bpm_hint`。它不得读取某个 separator 的 stems，也不得根据当前 production separator 改变结果。

`PipelineFromStemsRunner` 不再自行推断 beat/downbeat；它消费已经验证的 timing artifact，并继续负责候选窗口尝试、切片、MIDI 和 validation。旧的内部检测入口只保留到迁移与 parity 完成，不能留在最终生产路径。

## 6. `lmdj.timing.v1` 内部契约

该契约是 Audio Worker 内部 artifact，不是新的产品共享契约，也不进入 `patch.json`。

```json
{
  "schema_version": "lmdj.timing.v1",
  "status": "degraded",
  "reasons": ["tempo-ambiguity"],
  "input_sha256": "...",
  "analyzer": {
    "id": "librosa-rules-v1",
    "version": "...",
    "config_sha256": "..."
  },
  "audio": {
    "sample_rate": 44100,
    "duration_seconds": 180.0
  },
  "meter": {
    "beats_per_bar": 4,
    "source": "fixed-v1"
  },
  "tempo": {
    "bpm": 90.0,
    "source": "estimated",
    "candidates": [45.0, 90.0, 180.0],
    "confidence": 0.84
  },
  "beats_seconds": [0.31, 0.98],
  "downbeats_seconds": [0.31, 2.98],
  "downbeat": {
    "phase": 0,
    "phase_scores": [0.72, 0.11, 0.09, 0.08],
    "confidence": 0.61
  },
  "window_candidates": [
    {
      "start_seconds": 16.31,
      "end_seconds": 26.98,
      "start_beat_index": 24,
      "beat_count": 16,
      "score": 0.79,
      "detail": {
        "stability": 0.80,
        "seam": 0.76,
        "density": 1.88,
        "head_attack": 0.85,
        "head_quiet": 0.73,
        "tail_quiet": 0.74
      }
    }
  ],
  "alternative_grids": [
    {
      "reason": "tempo-ambiguity",
      "bpm": 180.0,
      "tempo_score": 0.71,
      "downbeat_phase": 0,
      "downbeat_confidence": 0.54,
      "beats_seconds": [0.31, 0.64],
      "downbeats_seconds": [0.31, 1.64],
      "window_candidates": []
    }
  ]
}
```

约束：

- 所有时间均为相对原始音频开头的秒数，使用 JSON number，不做毫秒整数与采样点混用。
- `input_sha256 + analyzer.id + analyzer.version + config_sha256` 构成缓存身份。
- `beats_seconds` 和 `downbeats_seconds` 必须严格递增并位于音频时长内。
- `window_candidates` 引用 beat index；不能由消费者重新计算另一套切点。
- `alternative_grids` 保存可执行的完整备用 timing grid，而不是只保存候选 BPM 数字；没有有效备用 grid 时写空数组。
- `status` 取 `passed / degraded / failed / unsupported`；非 `passed` 状态必须提供非空 `reasons`。
- `degraded` 允许进入下游多候选 validation，但必须保留原因且至少提供一个 `alternative_grids` 条目；`failed` 与 `unsupported` 不得进入切片。
- 失败 artifact 使用统一的结构化 `error.category / stage / message`，并保留 analyzer 及输入身份。

## 7. Timing 算法

### 7.1 输入与预处理

- 分析输入固定为原始歌曲的单声道版本。
- 第一阶段保持当前 44.1 kHz 与 hop length 512，先完成职责迁移和结果基线；降采样到 22.05 kHz 属于后续有数据支撑的性能优化，不能与职责迁移同时引入。
- 有 `bpm_hint` 时将其作为主 tempo，但仍计算对齐置信度并写入 artifact；hint 与音频严重不一致时标记 `degraded`，同时计算最佳估计 grid 写入 `alternative_grids`，不得静默修正。

### 7.2 Half/double tempo

没有 `bpm_hint` 时，从 librosa 的初始估计构造 `0.5x / 1x / 2x` 候选，去除超出 40–220 BPM 的值。每个候选重新跟拍，并按以下信息排序：

- beat 与 onset envelope 的对齐；
- beat interval 的稳定性；
- 四拍分组后的 downbeat 可分离度；
- 候选窗口能否满足长度与切口约束。

各项先归一化到 0–1，再取等权平均作为 tempo score；`tempo.confidence` 定义为最高与第二高 tempo score 之差。不再使用“超过 130 BPM 必定折半”的硬规则。若前两名 tempo 得分差小于 0.10，状态至少为 `degraded`，并把第二名的完整 grid 写入 `alternative_grids`，交给下游 validation 比较。

### 7.3 Downbeat

V1 保留当前三路特征，但所有特征均从原始音频导出：

- 和声变化：40%；
- 低频 onset（bass proxy）：30%；
- kick 频段 onset：30%。

每路特征分别计算四个相位的归一化分数，再合并为 `phase_scores`。`downbeat.confidence` 定义为最高相位与第二高相位的归一化分数差。

- confidence ≥ 0.15：`passed`；
- confidence < 0.15：至少为 `degraded`，保留最高两个相位的窗口候选；
- 无法形成足够 beat 或所有相位无有效信号：`failed`。

阈值是版本化 analyzer config 的一部分；后续调整必须产生新的 `config_sha256` 并重新跑 timing 评测。

### 7.4 候选窗口

默认枚举连续 16 beat（4 小节）的窗口，保留当前分项：能量稳定、首尾频谱相似、onset 密度、头部 attack、头尾边界能量。每个候选必须保留原始分项，不能只写综合分。

当前权重作为 `librosa-rules-v1` 基线，不在职责迁移阶段修改。权重优化必须基于人工标注“适合切 loop”的真实歌曲集，并与基线做离线对比。

`max_loop_seconds` 触发 16→8→4→2 beat 降级时，artifact 必须准确记录实际 `beat_count`，不得仍表述为“四小节”。

## 8. 下游消费与降级

`PipelineFromStemsRunner` 接收 `timing.json` 后：

1. 验证 schema、input hash、音频时长和时间边界。
2. 按 `window_candidates` 顺序尝试现有切片与 validation。
3. 对 `degraded` timing，必须覆盖排名最高的两个 tempo/phase 候选，再由现有 Patch validation score 选择最终产物。
4. 最终 `report.json` 记录 timing artifact 身份、使用的候选 index、timing status 和 confidence。
5. 如果所有候选都失败，job 进入现有 failed 状态；不能退回 separator-specific timing 检测。

多 separator benchmark 只能引用同一个 timing artifact hash。若某个 track 的不同模型报告了不同 timing hash，该 track 的 benchmark 结果无效。

## 9. 缓存与可复现性

- timing artifact 按内容和配置寻址，原始文件名、job id 和绝对路径不参与 hash。
- 写入采用临时文件加原子替换，读者不能看到半个 JSON。
- analyzer 版本、librosa/numpy 版本与关键配置进入 `config_sha256` 或环境快照。
- `--fresh` 只绕过缓存，不改变算法身份；相同输入与配置重跑必须得到相同 beat/downbeat/window 数组。
- benchmark report 保存 timing artifact snapshot 或其内容 hash，不能只保存运行时路径。

## 10. 测试设计

### 10.1 入库的合成 fixture

覆盖：

- 70、90、120、140、180 BPM；
- 90 BPM 配密集八分 hi-hat，防止误判 180；
- 弱起和一个小节的无鼓前奏；
- 稀疏 kick、无 bass、低能量片段；
- 曲长刚好够与不够 4 小节；
- `max_loop_seconds` 导致 16→8→4→2 beat 的每一级降级。

合成 fixture 保持小体积并进入 Git。真实歌曲及标注 manifest 放在既有本地 testdata 边界，不提交受版权保护的音频。

### 10.2 真实歌曲评测

真实评测集至少覆盖当前目标风格中的弱起、无鼓前奏、切分节奏、密集 hi-hat 和明显段落切换。每首歌人工标注：

- 参考 BPM；
- 至少 16 个连续 beat；
- 至少 8 个 downbeat；
- 可接受与不可接受的 4 小节 loop 起点。

同一份标注和 manifest 必须用于所有 analyzer 版本。

### 10.3 自动化指标与门槛

- 合成集 BPM octave 准确率 100%；
- 真实集 BPM octave 准确率至少 98%；
- beat F-measure 至少 0.95，匹配容差 70 ms；
- downbeat F-measure 至少 0.90，匹配容差 100 ms；
- 人工可接受 loop 的 top-3 命中率至少 90%；
- 相同原始音频与 timing 配置跨 separator 的 timing artifact hash 一致率 100%；
- 现有 90 BPM smoke 与 frozen-stems parity fixture 不退化；
- 真实歌曲端到端 Patch passed rate 不得比当前基线低超过 5 个百分点；
- 所有 `degraded / failed / unsupported` 都必须带结构化原因，测试不得只断言“没有崩溃”。

如果真实集不足 50 首，百分比必须同时报告分子/分母和 Wilson 95% 置信区间，不能只报单点百分比。

现有 frozen-stems parity fixture 在 Phase 0 增加与 stems 同源的固定原始 mix 及其 timing golden；旧 demo 仍保持冻结。迁移 parity 比较的是“旧 pipeline 自行分析的结果”与“新 TimingAnalyzer artifact 驱动的结果”，不允许通过重新相加某个 separator 的 stems 伪造原始 mix。

## 11. 可观测性

每次 timing 分析至少记录：

- 输入、analyzer 与 config 身份；
- 初始 tempo、全部 tempo 候选、最终选择及得分差；
- 四个 downbeat phase 分数与 confidence；
- 候选窗口数量、过滤原因计数、top-N 分项；
- wall time、peak RSS、缓存命中；
- 最终状态及降级原因。

日志用于调试，`timing.json` 才是机器可读真相源。错误不能只存在于 stderr。

## 12. 实施顺序

```text
Phase 0  建立合成 fixture、真实标注 manifest 与当前算法基线报告
Phase 1  定义 lmdj.timing.v1、TimingAnalyzer 和内容寻址缓存
Phase 2  PipelineFromStemsRunner 改为消费 timing artifact，完成职责迁移
Phase 3  half/1x/double tempo 候选、downbeat confidence 与 degraded 双候选验证
Phase 4  校准候选窗口权重并跑真实集、四 separator 与端到端回归
Review   根据验收门槛决定 librosa-rules-v1 是否晋级 production
Phase 5  仅在未过门槛时，另写 spec 评估专用 beat/downbeat 模型
```

每个 Phase 独立提交和 review。Phase 0 基线完成前不能修改算法权重；Phase 4 报告完成前不能预先决定引入新的节拍模型。

## 13. 验收结果

本设计完成后，同一首原始歌曲无论选择 HT Demucs、SCNet、BS-RoFormer 或 Mel-Band RoFormer，都必须消费同一个 timing artifact。separator 只影响 stems 及其下游音质，不再改变歌曲被认为“从哪一拍、哪一小节开始”。

librosa 继续作为 V1 timing 引擎，但它被封装在可版本化、可替换、可评测的 `TimingAnalyzer` 后面。未来若引入专用模型，只需实现相同内部契约并通过同一套门槛，不改变 Patch、API 或 Web 契约。
