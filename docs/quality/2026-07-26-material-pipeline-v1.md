# Material Pipeline v1 实现证据

日期：2026-07-26

分支：`codex/material-pipeline-v1`

状态：实现与自动化验证完成；尚未合并、推送、部署或晋升默认 Runner。

## 已落地

- `packages/core-models`：
  `lmdj.materials.v1` 数据模型、固定槽位、JSON Schema、关系约束、规范序列化
  与 identity bytes。
- `packages/patchify`：
  Material Package 安全 loader、固定 16 槽直接映射、Pattern → MIDI、
  Material identity → `patch_id`；legacy loader 保留。
- `workers/audio`：
  版本化 Timing/Extraction config、Timing Analyzer、鼓 one-shot、Stem loop、
  原曲 Phrase、质量/差异/静音/削波/泄漏门槛、显式 Empty 决策、
  `CreatorPipelineRunner` 与 `extracting` 状态。
- `apps/api`：
  `LMDJ_PIPELINE=legacy|materials-v1` 显式选择，默认 legacy；Export Source
  可盘点真实 Timing/Stems/Samples/MIDI；内部 `materials.json` 和
  `separation.json` 不通过文件路由公开。
- `apps/web`：
  `extracting` 处理阶段，普通素材 ↔ `full_mix_exclusive` Phrase 双向排他，
  loop 重触发替换旧 source，停止/换 Patch 回收全部 active source。

## 自动化验证

```text
packages/core-models: 18 passed
packages/patchify:     23 passed
workers/audio:         345 passed
apps/api:              69 passed
apps/web:              150 passed
web contract:          4 passed
web production build:  passed
legacy smoke:          passed
```

Worker 的确定性测试用同一合成原曲、四轨 Stem、Timing 与配置连续提取三次，并
比较：

- canonical `materials.json`；
- 每个 accepted sample 的 SHA-256；
- Pattern events；
- 16 个 slot decisions。

最初回归发现 FLOAT WAV 的 libsndfile `PEAK` chunk 带墙钟时间戳，导致内容完全
相同的 sample 文件 hash 漂移。实现改为确定性 PCM-24 WAV 后，三次结果一致。

`CreatorPipelineRunner` 的真实 Worker 测试（Separator 使用注入的规范四轨
fixture，不下载模型）覆盖：

```text
queued → separating → extracting → patchifying → completed
```

并验证最终 Export Source 包含四条真实 Stem、`timing.json`、Samples 和
`chart.mid`，pipeline provenance 为 `materials-v1`。

Legacy smoke 使用冻结 demo 的现有隔离 venv，重新生成 testsong 后得到：

```text
patch_id: testsong-6d0b984b
pads: 16
notes: 45 / 64 steps
status: passed
```

## 明确未完成的发布证据

以下发布门槛本轮没有运行，因此 `materials-v1` **没有**成为默认 Runner：

- 固定真实曲库（人声/器乐、简单/复杂鼓、电子/现场）的三次生产模型运行；
- 新旧 pipeline 的盲听与可演奏性对照；
- 实体 8-Pad Bank A/B；
- 原生 16-Pad Controller；
- Ableton Live 导入 Creator Export Smoke；
- 非开发者无指导完成全流程。

这些门槛只影响默认晋升，不否定本分支已落地的显式可选实现与自动化契约。
