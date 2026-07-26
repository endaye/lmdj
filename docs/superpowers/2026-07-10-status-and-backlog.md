# LMDJ 状态与 Backlog

初始日期：2026-07-10

最近更新：2026-07-26
用途：会话交接 / 下一步待办。记录已落地里程碑、当前可跑链路、延后的技术项、下一步候选。

## 已落地里程碑（均已合并 main）

| PR | 交付 | 落点 |
|----|------|------|
| #1 | 产品对象模型 + `lmdj.patch.v1` JSON Schema；Patchify Core（pipeline package → patch.json 适配器） | `packages/core-models`、`packages/patchify` |
| #2 | Patch View 工作台原型（8-pad，pattern 回放 + 触发 + 静音） | `apps/web` |
| #3 | Audio Worker（音频 → pipeline 子进程 → patchify → patch.json，status.json 状态机 + CLI） | `workers/audio` |
| #4 | App Backend（FastAPI：upload → job → status → patch 产物） | `apps/api` |
| #6 | Web 接入 API（浏览器传歌 → 轮询 → 玩到 patch，与拖目录/示例并存） | `apps/web` |
| #7 | Separation Phase 0（0A+0B）：`lmdj.separation.v1` contract / checkpoint registry / runner 协议（orchestrator 合成失败记录）+ `pipeline_from_stems`（阶段 3–6 逐字节迁移，专用 `.venv-pfs`，constraints 锁版本）+ frozen-stems parity 门槛（`scripts/dev.sh parity`，testsong 全项通过、两侧 patch_id 一致）。spec: `docs/superpowers/specs/2026-07-15-multi-separator-benchmark-design.md`；plan: `docs/superpowers/plans/2026-07-15-separation-phase0.md`。下一步：Phase 1A（HT Demucs + SCNet runners，registry 落真实条目）。 | `workers/audio/separation`、`workers/audio/pipeline_from_stems`、`config/` |
| #8 | Separation Phase 1A：HT Demucs（verified）+ SCNet-large（experimental）真实 runner 与 registry 条目，MPS 内存采样，`dev.sh separate` smoke（Mac MPS 验收 + canonical→compat→pfs→patchify 链路 sanity）。plan: `docs/superpowers/plans/2026-07-16-separation-phase1a.md` | `workers/audio/separation/runners`、`config/` |
| #9 | Separation Phase 1B：BS-RoFormer（SDR 9.65）+ Mel-Band RoFormer（SDR 8.22）四轨 runner 与 experimental registry 条目；MSST 家族共享实现抽取（scnet 薄壳化）；Mac MPS 验收。plan: `docs/superpowers/plans/2026-07-16-separation-phase1b.md` | `workers/audio/separation/runners`、`config/` |
| #10 | Separation Phase 1C-a：benchmark 执行层——manifest schema/loader、ffmpeg 输入归一化、orchestrator（全链 + 六元组缓存 key + resume + 单组合失败不中断）、`dev.sh bench` CLI；suno mini-run 真实验收。plan: `docs/superpowers/plans/2026-07-16-separation-phase1c-exec.md` | `workers/audio/benchmark`、`testdata/` |
| #11 | Separation Phase 1C-b：指标/评分/报告/盲听打包（museval SDR + 自实现 SI-SDR/一致性/泄漏，§9 权重与硬门槛，summary.json/csv + 跨平台 merge，匿名盲听包）。plan: docs/superpowers/plans/2026-07-16-separation-phase1c-metrics.md | workers/audio/benchmark |
| #23 | MUSDB18HQ manifest generator，支持从本地 MUSDB18HQ 目录生成 benchmark 数据集清单。 | `workers/audio/benchmark/musdb.py` |

## 当前可跑链路（浏览器已亲测闭环）

```text
浏览器提交（submission_id）→ apps/api(POST /uploads) → 单槽 FIFO JobExecutor
  → workers/audio(process_job)
  → 构建 API 时显式选择 runner：
      legacy → demo pipeline(子进程, demo 自有 venv)
      materials-v1 → Timing + 四轨分离 + Material Extractor
  → patchify
  → patch.json (lmdj.patch.v1) + samples 落 job 目录
  → apps/web 轮询 GET /jobs/{id}，刷新后按 Job/submission 恢复
  → GET /patch + /files/* → loadPatch
  → 固定 16-pad Creator Workbench 可播放/静音/触发
契约中枢：packages/core-models（模型 + JSON Schema，四方共同契约）
```

三条 patch 加载路（拖目录 / 内置示例 / API）汇入同一 `loadPatch`。本地开发：`scripts/dev.sh`（Python 侧）、各包 `npm test` / `pytest`。

## 贯穿的设计约束（改动时须遵守）

- `lmdj.patch.v1` 是 Web/CLI/Worker/API 四方唯一契约；schema 单一真相源在 `packages/core-models`，web 侧是 `npm run sync-contract` 生成物（`check-contract` 防漂移）。
- 契约纯度：消费方只认 `patch.json`，不读 `lanes.json`/`chart.mid`（truth 三段式，见 decision-log 2026-07-07）。
- golden fixture 方法论：消费外部产物的 loader，happy-path fixture 取自真实产物。
- `references/demos/lmdj-song-pipeline/` 是冻结的参考 demo，只作子进程/fixture/迁移来源，不加正式功能。
- 各正式包保持轻量：不把 demo 的 torch/numpy<2 锁带进来（worker/api 走子进程隔离）。

## 当前产品主线（2026-07-24）

最新 `approved-for-planning` PRD 将当前 Stage 收敛为 Creator Core。下一条纵向切片不再是单独扩展底层模型，而是：

```text
Upload
  → 16 Data Pads / 16-position UI
  → Keyboard + Generic MIDI Play / Bank A-B
  → Creator Export ZIP
  → Ableton Live Smoke Test
```

详细边界见 `docs/superpowers/specs/2026-07-24-stage1-creator-core-slice-design.md`。

## Material Pipeline v1 实现（2026-07-26，已合并 main）

PR #35 已合并 `lmdj.materials.v1`、Material Extractor、固定槽
Patchify、`CreatorPipelineRunner` 和队列集成。生产 API 在未显式设置时仍默认
`legacy`；`scripts/dev.sh dev` 仅在本地开发边界默认
`materials-v1 / htdemucs / mps`。

```text
original audio
  ├─ canonical Timing
  └─ canonical four-stem Separator
        → quality-gated Material Extractor
        → lmdj.materials.v1
        → fixed-slot Patchify + deterministic chart.mid
        → lmdj.patch.v1 / Web / Creator Export
```

- `lmdj.materials.v1` 只存在于 Worker → Patchify 内部边界；Web/API 仍只以
  `patch.json` 与结构化 Export Source 为产品真相。
- 固定 16 槽采用 Kick/Snare/Hat/Percussion/Bass/Melody/Vocal/Phrase 的 A/B
  布局；B 必须引用同角色 A，空槽不紧密排列。
- `CreatorPipelineRunner` 发射
  `queued → separating → extracting → patchifying → completed|failed`。
- `LMDJ_PIPELINE=legacy|materials-v1` 在 API 构建时显式选择；默认继续是
  `legacy`，新链失败不会在同一个 Job 内静默回退。
- Material 样本写为确定性的 PCM-24 WAV；这是为了避免 libsndfile FLOAT WAV
  `PEAK` chunk 的墙钟时间戳破坏 sample SHA-256 重复性。
- Web 从 Pad behavior 实现普通素材与 `full_mix_exclusive` Phrase 的双向排他，
  不读取 `materials.json`；API 也明确拒绝公开内部 Material/Separation
  manifest。

实现计划：
[`2026-07-26-material-pipeline-v1.md`](plans/2026-07-26-material-pipeline-v1.md)。
机器验证记录：
[`2026-07-26-material-pipeline-v1.md`](evidence/2026-07-26-material-pipeline-v1.md)。

该分支只完成实现与自动化验证，不代表默认 Runner 晋升。固定曲库盲听、实体
8-Pad/16-Pad Controller 和 Ableton Live Smoke 仍是发布门槛。

## 下一步候选（按产品证明排序）

1. **Release Evidence** —— 固定音频连续跑三次、盲听、实体 MIDI Pad
   映射、非开发者无指导完成流程、Ableton Live 导入 Smoke；通过前
   `LMDJ_PIPELINE` 默认仍为 `legacy`。
2. **Stage 1 第二切片** —— Sampler Edit + Take Recording，并将 Take 纳入 Creator Export。
3. **Separation / Timing 风险消除** —— 完成足以选择生产 baseline 的 Phase 1D benchmark、盲听和 Timing 评审；不阻塞首条 Creator 切片。
4. **Generation / Agent Orchestration** —— Creator 基础闭环成立后，再接 Prompt/Voice → Generation → 同一个 Patch Engine。
5. **apps/api 继续生产化** —— 当前单进程 FIFO 与重启中断语义合并后，再按真实产品流量引入鉴权/限流、对象存储、Postgres 与跨进程 durable workflow。

Stage 1 的上传任务可见性不等待完整 API 队列生产化；其最小需求见
[`2026-07-26-upload-job-visibility-requirement.md`](specs/2026-07-26-upload-job-visibility-requirement.md)。

## 延后的技术项（open follow-ups，非阻塞）

> 说明：以下为各任务/终审判为 ACCEPT 的延后项，已排除会话中后续修复掉的（stale GainNodes、catch-up 判别、audio input-copy zombie job、apps/api job_id 路径穿越——均已修并复核）。

### apps/api（已知接受风险，见其 spec）
- **进程崩溃可能遗留上传临时文件**：正常完成、失败或手动删除 queued Job
  已回收 `tempfile.mkdtemp()` 目录；进程在 executor finally 前崩溃时仍可能
  留下孤立的 `lmdj-upload-*`。

### apps/web
- **处理中无强制取消**：手动删除只支持 queued 与终态 Job；健康但慢的活跃
  Job 必须处理到终态后再由用户删除，不登记延迟自动删除。
- **spec 错误表待对齐**：patch-invalid-after-completed 实际路由到 uploading-error（非 landing），是计划已接受的取舍，spec 表述待更新。
- 杂项：`PAD_KEYS` 无 >8 pad 越界保护；pad 无 aria 属性；`fetchPatchBundle` 双解析 patch.json（无害）。

### packages / workers（测试覆盖 & 一致性）
- core-models：patch.json 顶层 key 顺序无测试断言；`Pattern.to_dict` 手写 vs `asdict` 不一致（cosmetic）；`LIVE_ACTIONS`/`RESERVED_ACTIONS` 常量定义未被引用（预期后续/文档用）；schema 未设 `additionalProperties:false`（有意的前向兼容选择，倾向 wontfix）；schema 边界（minItems/velocity 范围/resolution）除 3 个强制用例外未测。
- patchify：pitch-rejection 测试整体合成 chart.mid 而非破坏单字段；无显式 end-of-loop step-folding 测试；"lead 存在 + 2 harmonies → 跳过 fallback"分支未测；`cli.py` 省略 `--out` 时打印未 resolve 的路径（cosmetic）。
- audio worker：`TimeoutExpired.stderr` 未纳入 `stderr_tail`；`quality` 用 `or` 而非 `.get(default)`（空 status → "unknown"）；`_job_dir` 之外 `except` 略宽于 missing-audio（benign）。

### 仓库工程
- `packages/patchify/tests/fixtures/.gitattributes` 把该目录所有 `*.wav` 豁免 LFS——若将来提交大 golden 音频需重新审视。

### Separation（Phase 1A/1B 技术债 & 已知限制）
- `registry env_lock` 字段级覆盖 MSST constraints 文件（现靠 `test_msst_constraints_file_pinned` 漂移守护）
- `setup-sep-*` 后加 import-only smoke（mock 单测抓不到运行时依赖缺失，1B 验收实证）
- mel-roformer MPS driver 峰值 ~24.9GB，16GB 机器可能 OOM——batch 调优协议为既定 fallback；roformer 模型加载 ~40s 对 worker 延迟预算的影响待 1C 评估

## 关键文档索引

- 契约决策：`docs/prd/decision-log.md`（2026-07-07 一批）
- 当前产品摘要：`docs/prd/working-prd.md`（2026-07-24）
- 当前 Creator 切片：`docs/superpowers/specs/2026-07-24-stage1-creator-core-slice-design.md`
- 设计 spec：`docs/superpowers/specs/`（workstation / cloud-infra / patch-view / audio-worker / app-api / web-api-integration）
- 实施计划：`docs/superpowers/plans/`（patchify path-b / web-patch-view / audio-worker / app-api / web-api-integration）
- SDD 执行账本：`.superpowers/sdd/progress.md`（gitignored，本地）
- 协作约定：`CLAUDE.md` / `AGENTS.md`（双胞胎，保持同步）
