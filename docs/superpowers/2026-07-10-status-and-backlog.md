# LMDJ 状态与 Backlog

日期：2026-07-10
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

## 当前可跑链路（浏览器已亲测闭环）

```text
浏览器传歌 → apps/api(POST /uploads) → workers/audio(process_job)
  → demo pipeline(子进程, demo 自有 venv) → patchify
  → patch.json (lmdj.patch.v1) + samples 落 job 目录
  → apps/web 轮询 GET /jobs/{id} → GET /patch + /files/* → loadPatch
  → 8-pad 工作台可播放/静音/触发
契约中枢：packages/core-models（模型 + JSON Schema，四方共同契约）
```

三条 patch 加载路（拖目录 / 内置示例 / API）汇入同一 `loadPatch`。本地开发：`scripts/dev.sh`（Python 侧）、各包 `npm test` / `pytest`。

## 贯穿的设计约束（改动时须遵守）

- `lmdj.patch.v1` 是 Web/CLI/Worker/API 四方唯一契约；schema 单一真相源在 `packages/core-models`，web 侧是 `npm run sync-contract` 生成物（`check-contract` 防漂移）。
- 契约纯度：消费方只认 `patch.json`，不读 `lanes.json`/`chart.mid`（truth 三段式，见 decision-log 2026-07-07）。
- golden fixture 方法论：消费外部产物的 loader，happy-path fixture 取自真实产物。
- `references/demos/lmdj-song-pipeline/` 是冻结的参考 demo，只作子进程/fixture/迁移来源，不加正式功能。
- 各正式包保持轻量：不把 demo 的 torch/numpy<2 锁带进来（worker/api 走子进程隔离）。

## 下一步候选（优先级建议）

1. **`workers/generation`（云架构 Phase 2 入口）** —— idea/creative brief → 音乐材料 → 接 Audio Worker/Patchify，实现"一句话生成 patch"。产品叙事上的下一个大跳。
2. **Patch View 增强（纯前端，schema 已预留）** —— Scenes 切换、量化触发（`behavior.quantize` 目前读取不执行）、trigger_group 组员展开。
3. **apps/api 生产化前置** —— 队列（Redis/RQ，infra 待决）、鉴权/限流、对象存储、Postgres（jobs/patches/elements/lineage）。infra spec 已有蓝图。

## 延后的技术项（open follow-ups，非阻塞）

> 说明：以下为各任务/终审判为 ACCEPT 的延后项，已排除会话中后续修复掉的（stale GainNodes、catch-up 判别、audio input-copy zombie job、apps/api job_id 路径穿越——均已修并复核）。

### apps/api（已知接受风险，见其 spec）
- **上传体积无上限**：`POST /uploads` 无 max-bytes，网络可达时磁盘耗尽 DoS 面；归入限流范畴，生产化时随鉴权/限流加 413。
- **上传临时文件不清理**：`tempfile.mkdtemp()` 产物不回收（进程级临时目录）。

### apps/web
- **UploadingView 对未知/失败态脆弱**：后端 `STATES` 含 `generating/extracting/rendering`（v1 未发射），若发射则 `currentIndex=-1` 全阶段变 pending；失败时也把已完成阶段 collapse 成 pending（可改为在失败点冻结进度）。
- **处理中无取消/返回**：`uploading` 态仅在 error 时给"返回"，健康但慢的 job 最长锁 300s。
- **spec 错误表待对齐**：patch-invalid-after-completed 实际路由到 uploading-error（非 landing），是计划已接受的取舍，spec 表述待更新。
- 杂项：`PAD_KEYS` 无 >8 pad 越界保护；pad 无 aria 属性；`fetchPatchBundle` 双解析 patch.json（无害）。

### packages / workers（测试覆盖 & 一致性）
- core-models：patch.json 顶层 key 顺序无测试断言；`Pattern.to_dict` 手写 vs `asdict` 不一致（cosmetic）；`LIVE_ACTIONS`/`RESERVED_ACTIONS` 常量定义未被引用（预期后续/文档用）；schema 未设 `additionalProperties:false`（有意的前向兼容选择，倾向 wontfix）；schema 边界（minItems/velocity 范围/resolution）除 3 个强制用例外未测。
- patchify：pitch-rejection 测试整体合成 chart.mid 而非破坏单字段；无显式 end-of-loop step-folding 测试；"lead 存在 + 2 harmonies → 跳过 fallback"分支未测；`cli.py` 省略 `--out` 时打印未 resolve 的路径（cosmetic）。
- audio worker：`TimeoutExpired.stderr` 未纳入 `stderr_tail`；`quality` 用 `or` 而非 `.get(default)`（空 status → "unknown"）；`_job_dir` 之外 `except` 略宽于 missing-audio（benign）；`executor._threads` 无界增长（dev 无害）。

### 仓库工程
- `packages/patchify/tests/fixtures/.gitattributes` 把该目录所有 `*.wav` 豁免 LFS——若将来提交大 golden 音频需重新审视。

### Separation（Phase 1A/1B 技术债 & 已知限制）
- `registry env_lock` 字段级覆盖 MSST constraints 文件（现靠 `test_msst_constraints_file_pinned` 漂移守护）
- `setup-sep-*` 后加 import-only smoke（mock 单测抓不到运行时依赖缺失，1B 验收实证）
- mel-roformer MPS driver 峰值 ~24.9GB，16GB 机器可能 OOM——batch 调优协议为既定 fallback；roformer 模型加载 ~40s 对 worker 延迟预算的影响待 1C 评估

## 关键文档索引

- 契约决策：`docs/prd/decision-log.md`（2026-07-07 一批）
- 设计 spec：`docs/superpowers/specs/`（workstation / cloud-infra / patch-view / audio-worker / app-api / web-api-integration）
- 实施计划：`docs/superpowers/plans/`（patchify path-b / web-patch-view / audio-worker / app-api / web-api-integration）
- SDD 执行账本：`.superpowers/sdd/progress.md`（gitignored，本地）
- 协作约定：`CLAUDE.md` / `AGENTS.md`（双胞胎，保持同步）
