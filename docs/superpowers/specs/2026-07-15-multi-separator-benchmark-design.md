# LMDJ 多分轨模型 Benchmark 与生产选型设计

日期：2026-07-15
状态：用户已确认设计，待实施计划
范围：`workers/audio/` 正式产品边界；`references/demos/lmdj-song-pipeline/` 只作行为基线与迁移来源

## 1. 目标

LMDJ 同时支持并比较四个音乐源分离模型家族：

- HT Demucs；
- SCNet / SCNet-large；
- BS-RoFormer；
- Mel-Band RoFormer。

工作分两阶段：

1. 先建立可复现的内部 benchmark，在 MUSDB18HQ 与 LMDJ 真实歌曲集上比较分轨质量、最终 Patch 可玩性、可靠性和资源成本；
2. 只有通过硬门槛的 checkpoint 才能晋级生产，由 Audio Worker 和 API 选择使用。

模型选型的第一原则不是论文 SDR 最大，而是通过硬门槛后按综合分排序。综合分权重固定为：Patch 质量 40%、标准分轨质量 30%、性能成本 20%、可靠性 10%。

## 2. 非目标

- 不在第一阶段把模型选择暴露给普通 Web 用户；
- 不把四套模型依赖装进同一个 Python 进程或 venv；
- 不把模型权重、MUSDB18HQ 或真实歌曲提交到 Git；
- 不修改参考 demo 来承载新的正式产品功能；
- 不把来源、checksum、stem 契约或许可不明确的 checkpoint 标记为生产可用；
- 不在 benchmark 中静默把 MPS 失败改为 CPU；
- 不在本轮引入 CUDA，首轮目标平台是 macOS Apple Silicon MPS 与 Linux CPU。

## 3. 当前结构缺口与 Phase 0

当前参考 pipeline 的 `pipeline.py` 直接调用 `stems.separate()`，没有“传入已有 stems 后只运行 beat / loop / slicer / sequencer / validation”的正式接口。不同 separator 即使能输出 stems，也无法在不修改参考 demo 的情况下进入同一条下游链路。

因此多模型 benchmark 前必须先建立 LMDJ-owned 的 `PipelineFromStemsRunner`：

```text
canonical four stems
  -> compatibility mapping
  -> beat / loop detection
  -> slicer
  -> sequencer
  -> validation
  -> lanes.json / chart.mid / report.json / previews
  -> Patchify
```

阶段 3–6 的实现从参考 demo 迁移到 `workers/audio/`。参考 demo 保持冻结，只作为算法行为、fixture 和 parity 基线。

### 3.1 Parity 门槛

使用同一组固定 Demucs stems、固定 config 和固定随机种子，同时运行旧 pipeline 与 `PipelineFromStemsRunner`。除耗时字段外，必须满足：

- `report.status`、BPM、选中窗口、sample 数、note 数和 lane 名称一致；
- validation score 绝对差不超过 `1e-4`；
- `lanes.json` 和标准化后的 MIDI note events 一致；
- preview/sample 音频长度一致，数值最大绝对差不超过 `1e-5`；
- 两侧生成物都能被 Patchify 读取并通过 `lmdj.patch.v1` schema；
- parity 未通过时不得开始多模型排名。

## 4. 总体架构

```text
Dataset Manifest
  -> Benchmark CLI
  -> Benchmark Orchestrator
       -> Separator Registry
       -> isolated SeparatorRunner subprocess
            - DemucsRunner
            - SCNetRunner
            - BSRoFormerRunner
            - MelBandRoFormerRunner
       -> Canonical Stem Package (lmdj.separation.v1)
       -> PipelineFromStemsRunner
       -> Patchify
       -> Metrics + Report
```

建议代码边界：

```text
workers/audio/lmdj_audio_worker/
  separation/
    contract.py
    registry.py
    cache.py
    protocol.py
    runners/
      demucs.py
      scnet.py
      bs_roformer.py
      mel_band_roformer.py
  pipeline_from_stems.py
  benchmark/
    manifest.py
    orchestrator.py
    metrics.py
    report.py
    cli.py
workers/audio/config/
  separators.json
  benchmark-targets.json
workers/audio/tests/
  separation/
  benchmark/
```

模型 runner 只负责“输入音频 -> canonical four stems”。它不得调用 Patchify、修改 job 状态或了解 Web/API。

Benchmark Orchestrator 负责组合 dataset、checkpoint、device 和 repeat，执行 runner、下游 pipeline、指标计算与报告汇总。一个组合失败不得中止整批。

## 5. SeparatorRunner 协议

所有 runner 接受同一请求：

```text
input_path
output_dir
device = cpu | mps
checkpoint_id
seed / repeat_id
```

每个 runner 在独立子进程和独立 venv 中运行。Orchestrator 不 import 任何模型框架，只根据 registry 执行固定命令并读取结果文件。

runner 必须写出 `separation.json`，schema 版本为 `lmdj.separation.v1`，至少包含：

```json
{
  "schema_version": "lmdj.separation.v1",
  "status": "completed",
  "input_sha256": "...",
  "separator": {
    "id": "htdemucs",
    "family": "demucs",
    "checkpoint_sha256": "...",
    "runner_version": "..."
  },
  "requested_device": "mps",
  "actual_device": "mps",
  "stems": {
    "drums": "stems/drums.wav",
    "bass": "stems/bass.wav",
    "vocals": "stems/vocals.wav",
    "other": "stems/other.wav"
  },
  "audio": {
    "sample_rate": 44100,
    "channels": 2,
    "duration_seconds": 30.0
  },
  "performance": {
    "model_load_seconds": 0.0,
    "inference_seconds": 0.0,
    "wall_seconds": 0.0,
    "peak_rss_bytes": 0,
    "peak_device_memory_bytes": 0
  }
}
```

Canonical package 硬约束：

- stems 必须完整包含 `drums / bass / vocals / other`；
- WAV 为 44.1 kHz、双声道、32-bit float；
- 四个 stem 与输入时长误差不超过一个 sample；
- 不允许 NaN、Inf、空音频或绝对峰值大于 `8.0`；
- canonical stems 保存模型原始幅度，不做逐轨归一化或整数 PCM clipping，保证 SDR 与 mixture consistency 指标有效；
- runner 报告的 `actual_device` 必须与实际执行设备一致；
- 单目标 checkpoint 只有在 registry 明确定义四目标组合方案后才能形成 canonical package；组合的总耗时、内存与模型大小必须完整计入成本。

现有 pipeline 的兼容映射固定为：

```text
drums  = drums
bass   = bass
melody = vocals + other
```

为保持旧 pipeline parity，兼容层在进入阶段 3–6 前复制 canonical stems，并沿用旧实现的“单轨峰值超过 1.0 时缩放到 1.0”规则。客观分轨指标始终读取未归一化的 canonical stems；Patch 指标读取兼容层输出。两组音频不得复用同一文件，避免 benchmark 改写原始分轨结果。

## 6. Checkpoint Registry 与晋级状态

`workers/audio/config/separators.json` 是可运行 checkpoint 的唯一 registry。每个条目必须包含：

- 稳定 ID、模型家族和 runner 类型；
- 固定下载来源与不可变 revision；
- artifact SHA-256；
- 代码与权重许可说明；
- 输出 stem 列表、采样率与声道；
- 支持设备；
- runner 环境 lock/hash；
- 状态：`experimental / verified / production`。

状态语义：

- `experimental`：允许内部 benchmark，不允许产品 job；
- `verified`：来源、checksum、许可、四轨 contract 与双平台 smoke 均已验证；
- `production`：除 verified 条件外，还通过完整评测集和生产资源硬门槛。

首批家族策略：

| 家族 | 初始状态 | 权重策略 |
|---|---|---|
| HT Demucs | `verified` baseline | 官方 `htdemucs` checkpoint，记录当前实际下载 artifact 的 checksum |
| SCNet-large | `experimental`，双平台验证后升 `verified` | 官方仓库发布的 SCNet-large checkpoint |
| BS-RoFormer 4-stem | `experimental` | 只启用能追溯训练/发布来源、固定 revision、明确四轨与许可的 checkpoint |
| Mel-Band RoFormer 4-stem | `experimental` | 同上；单目标社区权重不得伪装成四轨模型，组合方案必须显式登记 |

架构 runner 可以先实现，但如果 RoFormer checkpoint 未通过来源或许可门禁，registry 校验必须拒绝启用和自动下载。用户提供的本地实验权重也必须登记 checksum、来源备注和 `experimental` 状态，结果报告要显示其非生产身份。

模型权重缓存位置：

```text
${LMDJ_MODEL_CACHE:-~/.cache/lmdj/separators}/<checkpoint-id>/<sha256>/
```

下载采用临时文件、校验 SHA-256 后原子 rename；checksum 不符立即删除，不得运行。

## 7. 数据集

### 7.1 MUSDB18HQ

用于带 ground truth 的客观分轨评测，覆盖四个 stems。仓库只提交 manifest schema、公开 track ID 与相对路径，不提交数据集内容。

### 7.2 LMDJ 真实歌曲集

第一轮使用 10–20 首代表性歌曲，至少覆盖：

- 鼓密集、低频密集、人声突出；
- 电子、摇滚、hip-hop、氛围等不同风格；
- 干净录音与复杂母带；
- 30 秒片段与完整歌曲。

真实歌曲和包含私人文件名的 manifest 默认 gitignored。仓库提交匿名 manifest 示例和 schema；实际路径相对于 `LMDJ_BENCH_DATA_ROOT`，不得把绝对主机路径写入报告。

Manifest 每条记录包含：track ID、输入相对路径、split、标签、是否有 ground truth、ground-truth stem 相对路径。

## 8. Benchmark 执行与缓存

命令形态：

```bash
lmdj-audio-worker benchmark \
  --dataset musdb18hq.manifest.json \
  --dataset lmdj-real.manifest.json \
  --separators htdemucs,scnet-large,bs-roformer-4stem,mel-roformer-4stem \
  --device mps
```

Linux CPU 在目标服务器执行同一份 manifest snapshot；两个 run 可合并为一份跨平台报告。

输出结构：

```text
benchmarks/<run-id>/
  run.json
  manifest.snapshot.json
  registry.snapshot.json
  environment.json
  results/<dataset>/<track>/<checkpoint>/<device>/<repeat>/
  summary.json
  summary.csv
  listening-test/
```

结果缓存 key：

```text
input sha256
+ checkpoint sha256
+ runner version
+ config hash
+ device
+ seed/repeat ID
```

默认复用完整且 checksum 正确的缓存；`--fresh` 强制重跑。代表性稳定性子集每个模型、设备至少重复三次。缓存命中不得计入性能指标，性能指标读取首次真实 run 的记录。

盲听目录使用随机匿名 ID，评测者看不到模型名；映射只保存在汇总阶段读取的私有 key 文件中。

## 9. 指标、权重与硬门槛

### 9.1 可靠性：10 分

- 批次成功率：6；
- canonical contract 合规率：2；
- 三次重复运行的结构稳定性：2。

### 9.2 标准分轨质量：30 分

- MUSDB18HQ SDR：15；
- SI-SDR：10；
- mixture consistency 与 stem 泄漏指标：5。

所有指标同时报告四轨分项和平均值；平均值不得隐藏 bass 或 drums 的显著退化。

### 9.3 LMDJ Patch 质量：40 分

- Pipeline completed / passed rate：15；
- validation score：10；
- retry、鼓分类降级率、sample/lane 结构：5；
- 匿名盲听的串音、瞬态、低频清晰度与 Patch 可玩性：10。

### 9.4 性能成本：20 分

- real-time factor 与整链路墙钟时间：12；
- peak RSS / MPS allocated memory：5；
- checkpoint 大小与模型加载时间：3。

综合分只用于同一 run snapshot 内的模型排序。所有原始指标、分项、失败记录和置信区间必须保留。

### 9.5 生产晋级硬门槛

- canonical contract 合规率 100%；
- macOS MPS 与 Linux CPU smoke 全部通过；
- 完整评测执行成功率至少 95%；
- LMDJ Patch passed rate 不得比同 run 的 HT Demucs baseline 低超过 5 个百分点；
- checkpoint 来源、revision、checksum 和许可完整；
- Linux CPU 目标为 16 GiB VM，单 job peak RSS 不得超过 12 GiB；
- Mac 以 process peak RSS 与 `torch.mps` peak allocated memory 中较高者计算，不得超过目标机器物理内存的 75%；
- 任何硬门槛失败都不得用综合总分抵消。

## 10. 错误模型与设备策略

统一错误类别：

```text
download
checksum
license
unsupported_device
timeout
oom
inference
invalid_stems
downstream
metric
```

每次失败记录 model/checkpoint/device/track/stage、退出码、stderr tail 和已用时间。一个组合失败后继续其他组合。

Benchmark 必须强制所请求设备，不允许以下行为：

- MPS 不可用或运行失败后静默改用 CPU；
- 四轨 checkpoint 缺轨后用原混音伪造缺失 stem；
- checkpoint 下载失败后改用同家族另一个权重；
- 下游失败后只保留分轨指标并把整个 run 标为成功。

生产阶段同样默认不静默换模型。fallback/retry 若未来引入，必须产生新的 attempt，记录真实 checkpoint/device，并保持用户可见与可审计。

## 11. Phase 2：生产接入

只有 registry 状态为 `production` 的 separator 可以处理产品 job。

`POST /uploads` 增加可选 multipart 字段 `separator_id`：

- 未指定时使用 `LMDJ_DEFAULT_SEPARATOR`，初始默认仍为 HT Demucs；
- unknown、experimental 或 verified 但未晋级的 ID 返回 400；
- 旧客户端不传字段时行为不变。

增加 `GET /separators`，只返回 production 条目的安全展示字段：ID、名称、四轨能力和性能档位，不暴露本地缓存路径。

Job status、`report.json` 和最终 Patch metadata 记录：

- separator ID、family；
- checkpoint revision 与 SHA-256；
- requested/actual device；
- runner version。

第一版 Web 不必展示选择器；API 和 worker 先支持可复现选择。产品需要时再根据 `GET /separators` 增加高级选项，不在前端硬编码模型列表。

## 12. 测试与验收

### 12.1 自动测试

- `lmdj.separation.v1` contract 的成功和错误边界；
- registry schema、状态转换、未知字段、重复 ID、许可/checksum 缺失；
- 缓存 key、checksum 损坏、atomic download、`--fresh`；
- 四个 runner 的 fake-process 成功、timeout、OOM、stderr 映射；
- canonical stem 时长、采样率、NaN、峰值、缺轨验证；
- 固定 stems 的旧/新 pipeline parity；
- benchmark resume、repeat、单组合失败不中断和跨平台 merge；
- 评分权重总和、硬门槛不可被总分绕过；
- API 默认模型、合法显式选择、拒绝非 production 模型；
- 现有不传 `separator_id` 的 API/Web 回归。

### 12.2 真实验收

1. Mac Apple Silicon：四个已启用 checkpoint 各跑一首 smoke，确认 actual device 与 MPS 一致；
2. Linux 16 GiB CPU VM：同一输入跑四个 checkpoint，记录 RTF 与 peak RSS；
3. MUSDB18HQ 完整 benchmark；
4. 10–20 首真实歌曲完整 benchmark 与匿名盲听；
5. 晋级 checkpoint 通过真实 API 上传、轮询、Patchify、Web Patch View 播放端到端；
6. 发布的 report 能从 manifest/registry/environment snapshots 重建实验身份，不包含绝对主机路径。

## 13. 实施顺序

```text
Phase 0A  lmdj.separation.v1 + registry + runner protocol
Phase 0B  PipelineFromStemsRunner + frozen-stems parity
Phase 1A  HT Demucs + SCNet runners
Phase 1B  BS-RoFormer + Mel-Band RoFormer runners与checkpoint门禁
Phase 1C  dataset manifests + metrics + report + blind listening package
Phase 1D  Mac MPS / Linux CPU 双平台完整 benchmark
Review    根据原始报告与硬门槛批准 production checkpoint
Phase 2A  Audio Worker 接入选定 separator
Phase 2B  API selector + status/metadata + GET /separators
Phase 2C  真实上传到 Patch View 的端到端验证
```

每个阶段独立提交和 review。Phase 1D 报告出来前不得预先决定替换 Demucs；Phase 2 只消费明确批准为 `production` 的 registry 条目。

## 14. 参考资料

- [Demucs 官方维护 fork](https://github.com/adefossez/demucs)
- [SCNet 官方实现与 checkpoint](https://github.com/starrytong/SCNet)
- [BS-RoFormer 论文](https://arxiv.org/abs/2309.02612)
- [Mel-Band RoFormer 论文](https://arxiv.org/abs/2310.01809)
- [Music-Source-Separation-Training](https://github.com/ZFTurbo/Music-Source-Separation-Training)
- [python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator)
