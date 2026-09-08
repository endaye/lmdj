# Separation Phase 1C-b（指标与评分层）Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 1C-a 的 run 目录树之上建立指标与评分层：客观分轨指标（SDR/SI-SDR/mixture consistency/泄漏）、Patch 指标、§9 评分（40/30/20/10 + §9.5 硬门槛）、`summary.json`/`summary.csv` 报告（含跨平台 merge）、匿名盲听打包。

**Architecture:** 新模块加入 `workers/audio/lmdj_audio_worker/benchmark/`（metrics / patch_metrics / scoring / report / listening + cli 扩展），全部运行在 workers/audio 主 venv（新 `metrics` extra：museval + pandas 栈；**无 torch**——SI-SDR 自实现 numpy）。输入是 1C-a 产出的 run 目录（combo.json/separation stems/pfs 包/patch.json + snapshots）；输出 `summary.json`/`summary.csv`/`listening-test/` 落回 run 目录（spec §8 结构补全）。

**Tech Stack:** museval==0.4.1（BSSEval v4 framewise，1s window/hop 取 median——MUSDB 文献惯例）+ 其传递依赖（pandas==3.0.3, scipy==1.17.1, simplejson==4.1.1）；numpy==1.26.4；SI-SDR/一致性/泄漏为自实现纯 numpy。

**Spec:** `docs/design/2026-07-15-multi-separator-benchmark-design.md` §8（输出结构/盲听目录）、§9（指标/权重/硬门槛）、§12.1（评分权重总和、硬门槛不可绕过测试）。

**Base branch:** `main`（1C-a 已合并，6dcb37df）。分支 `codex/feat-separation-phase1c-metrics`。

## 已核实的事实（2026-07-16 探测）

- `museval==0.4.1` 在 numpy==1.26.4 / py3.12 下可装可算：`museval.metrics.bss_eval(ref, est, window=44100, hop=44100)`，`ref/est` 形状 `(nsrc, samples, ch)`，返回 `(sdr, isr, sir, sar, perms)`，`sdr` 形状 `(nsrc, nframes)`——近似信号实测 SDR ≈ 40dB ✓。传递依赖 pandas==3.0.3、scipy==1.17.1、simplejson==4.1.1。
- **`fast_bss_eval==0.1.4` 的 `si_sdr` 在无 torch 环境下损坏**（dispatch 无条件引用 torch 后端属性，实测 AttributeError）。装 torch 进主 venv 违背隔离——**决策：SI-SDR 自实现**（Le Roux 2019 标准公式，纯 numpy），spec §9.2 的 pin 行需同步修订（Task 10）。
- 1C-a run 目录契约：`combo.json`（status/stages/performance/cache_key_components）、`separation/stems/{drums,bass,vocals,other}.wav`（float32 44.1k 双声道）、`normalized/<dataset>/<track.id>/<stem>.wav`、`pfs/<track.id>/report.json`（status/score/attempts/lanes）、`pfs/<track.id>/patch.json`、`run.json`（args/summary/failures）、`environment.json`。
- manifest GT 契约（1C-a）：`Track.ground_truth = {drums,bass,vocals,other: 相对路径}`，`manifest.data_root()` 解析。
- checkpoint 大小可从 `~/.cache/lmdj/separators/<id>/<sha>/` 实测（report 阶段 stat）；`model_load_seconds` 在 combo performance 里。

## 自定义指标的精确定义（本 plan 的规范文本，实现与测试都以此为准）

设 `s` 为 GT stem、`ŝ` 为估计（逐声道计算后取算术平均），全曲整段：

- **SI-SDR**（higher better）：`α = ⟨ŝ, s⟩ / ⟨s, s⟩`；`e_t = α·s`；`e_r = ŝ − e_t`；`SI-SDR = 10·log10(‖e_t‖² / ‖e_r‖²)`。GT 能量为 0 → `null`（不参与聚合）；完美重建 clip 到 +120。
- **Mixture consistency**（lower better，dB）：`MC = 10·log10(‖Σᵢ ŝᵢ − mix‖² / ‖mix‖²)`，`mix` = 归一化输入。完美一致 clip 到 −120。
- **泄漏 leakage**（lower better，dB）：对估计 `ŝᵢ` 与每个 `j≠i` 的 GT：`βⱼ = ⟨ŝᵢ, sⱼ⟩ / ⟨sⱼ, sⱼ⟩`；`leakᵢ = 10·log10(maxⱼ ‖βⱼ·sⱼ‖² / ‖ŝᵢ‖²)`（正交投影能量占比，取最坏邻轨）。估计能量为 0 → `null`。
- **SDR**：museval BSSEval v4，window=hop=44100（1s 帧），对帧取 `nanmedian`，逐 stem 报告 + 四轨平均（spec §9.2：平均值不得隐藏单轨退化——per-stem 始终保留）。

## Global Constraints

- 权重与硬门槛照抄 spec §9：可靠性 10（批次成功 6 + contract 合规 2 + 三次重复结构稳定 2）、分轨质量 30（SDR 15 + SI-SDR 10 + 一致性/泄漏 5）、Patch 质量 40（completed/passed 15 + validation score 10 + retry/降级/结构 5 + 盲听 10）、性能 20（RTF/墙钟 12 + 峰值内存 5 + checkpoint 大小/加载 3）。**任何硬门槛失败不得用总分抵消**；权重总和恒等测试必须存在（spec §12.1）。
- 归一化只在同一 run snapshot 内做模型排序（spec §9.4）：每个子指标跨 separator min-max 到 [0,1]（lower-better 先取负）；单 separator 或全相等 → 该子指标记 1.0 并标注 `degenerate: true`。**所有原始指标、分项、失败记录必须保留**在 summary。
- 盲听分数与双平台 smoke 是外部输入：`--listening-scores F`（按匿名 id keyed）与 `--attestations F`（如 `{"linux_cpu_smoke": true, "macos_mps_smoke": true, "mac_physical_memory_bytes": 68719476736}`）；缺失 → 对应分项/门槛状态记 `"missing"`/`"unknown"`——**不得默默按 0 或按通过处理**。盲听否决（任一维度 ≥2 人打 1 分）→ 该 separator 门槛 `veto_failed`。
- 缓存命中组合的 performance 属于首次真实 run 的记录（1C-a 语义）——聚合直接使用 combo.json 的 performance。
- 无绝对主机路径进入 summary/listening 包；匿名 id 随机、key 文件不进入盲听分发内容。
- 主包 `dependencies` 保持 `[]`；新依赖只进 `metrics` extra + `config/metrics-constraints.txt`（precise pins；environment.json 快照扩展纳入其 sha256——1C-a snapshots 小改）。
- commit 符合 Conventional Commits；`references/demos/`、MSST clone 不动。

## 准备

```bash
cd workers/audio
python3 -m venv .venv 2>/dev/null || true
.venv/bin/pip install -e ../../packages/core-models -e ../../packages/patchify
.venv/bin/pip install -e ".[test,pfs]" -c config/parity-constraints.txt
.venv/bin/python -m pytest tests/ -q   # 基线 179 tests 全绿
```

---

### Task 1: `metrics` extra + constraints + environment 快照扩展

**Files:**
- Create: `workers/audio/config/metrics-constraints.txt`
- Modify: `workers/audio/pyproject.toml`（`metrics` extra）
- Modify: `workers/audio/lmdj_audio_worker/benchmark/snapshots.py`（environment.json 的 config 哈希文件列表从三个扩到四个）
- Modify: `workers/audio/tests/benchmark/test_snapshots.py`（断言扩展）

**Steps:**
- [ ] `workers/audio/config/metrics-constraints.txt`：

```text
# benchmark 指标层版本锁（spec §9.2：指标实现必须 pin 死并记入 environment.json）。
# SI-SDR/一致性/泄漏为自实现 numpy（fast_bss_eval 0.1.4 无 torch 时 si_sdr 损坏，弃用——见 decision-log 2026-07-16）。
museval==0.4.1
pandas==3.0.3
scipy==1.17.1
simplejson==4.1.1
numpy==1.26.4
soundfile==0.14.0
```

- [ ] pyproject `[project.optional-dependencies]` 加 `metrics = ["museval"]`（版本靠 constraints）；测试 venv 重装：`.venv/bin/pip install -e ".[test,pfs,metrics]" -c config/parity-constraints.txt -c config/metrics-constraints.txt`
- [ ] snapshots：environment.json 哈希列表加 `metrics-constraints.txt`；更新既有测试（四个哈希重算断言）
- [ ] `cd workers/audio && .venv/bin/python -m pytest tests/ -q` 全绿；`.venv/bin/python -c "import museval; print(museval.__version__)"` → 0.4.1
- [ ] Commit: `feat(benchmark): add pinned metrics dependencies and extend environment snapshot`

---

### Task 2: `benchmark/metrics.py`（一）— SI-SDR / mixture consistency / 泄漏（自实现）

**Files:**
- Create: `workers/audio/lmdj_audio_worker/benchmark/metrics.py`
- Test: `workers/audio/tests/benchmark/test_metrics_custom.py`

**Interfaces:**
- Produces（Task 3/6 依赖）：
  - `STEMS = ("drums", "bass", "vocals", "other")`、`MC_FLOOR_DB = -120.0`
  - `si_sdr(reference: np.ndarray, estimate: np.ndarray) -> float | None`（输入 `(frames, ch)`）
  - `mixture_consistency(estimates: dict, mix: np.ndarray) -> float`
  - `leakage(estimates: dict, references: dict) -> dict[str, float | None]`

**实现代码（完整，照抄）：**

```python
# workers/audio/lmdj_audio_worker/benchmark/metrics.py
"""客观分轨指标（spec §9.2）。

SDR 用 museval（BSSEval v4，1s framewise median，MUSDB 惯例）；
SI-SDR / mixture consistency / 泄漏为自实现纯 numpy——精确定义见
docs/plans/2026-07-16-separation-phase1c-metrics.md
（fast_bss_eval 0.1.4 无 torch 时 si_sdr 损坏，弃用）。
"""
from __future__ import annotations

import numpy as np

STEMS = ("drums", "bass", "vocals", "other")
MC_FLOOR_DB = -120.0
SI_SDR_CEIL_DB = 120.0
_EPS = 1e-12


def _per_channel(func, reference: np.ndarray, estimate: np.ndarray):
    values = []
    for ch in range(reference.shape[1]):
        v = func(reference[:, ch].astype(np.float64),
                 estimate[:, ch].astype(np.float64))
        if v is not None:
            values.append(v)
    return float(np.mean(values)) if values else None


def _si_sdr_1d(s: np.ndarray, s_hat: np.ndarray) -> float | None:
    energy = float(np.dot(s, s))
    if energy < _EPS:
        return None
    alpha = float(np.dot(s_hat, s)) / energy
    e_t = alpha * s
    e_r = s_hat - e_t
    num = float(np.dot(e_t, e_t))
    den = float(np.dot(e_r, e_r))
    if den < _EPS:
        return SI_SDR_CEIL_DB              # 完美重建，clip 对称上限
    return 10.0 * np.log10(max(num, _EPS) / den)


def si_sdr(reference: np.ndarray, estimate: np.ndarray) -> float | None:
    return _per_channel(_si_sdr_1d, reference, estimate)


def mixture_consistency(estimates: dict, mix: np.ndarray) -> float:
    total = sum(estimates[k] for k in STEMS)
    residual = float(np.sum((total.astype(np.float64)
                             - mix.astype(np.float64)) ** 2))
    mix_energy = float(np.sum(mix.astype(np.float64) ** 2))
    if mix_energy < _EPS:
        return MC_FLOOR_DB
    value = 10.0 * np.log10(max(residual, _EPS) / mix_energy)
    return max(value, MC_FLOOR_DB)


def leakage(estimates: dict, references: dict) -> dict:
    out: dict = {}
    for i in STEMS:
        est = estimates[i].astype(np.float64)
        est_energy = float(np.sum(est ** 2))
        if est_energy < _EPS:
            out[i] = None
            continue
        worst = 0.0
        for j in STEMS:
            if j == i:
                continue
            ref = references[j].astype(np.float64)
            ref_energy = float(np.sum(ref ** 2))
            if ref_energy < _EPS:
                continue
            beta = float(np.sum(est * ref)) / ref_energy
            worst = max(worst, beta * beta * ref_energy)
        out[i] = 10.0 * np.log10(max(worst, _EPS) / est_energy)
    return out
```

**测试要点（每条一个测试；性质锚定，不与实现互抄）：**
1. `si_sdr(x, x)` == 120.0；
2. 尺度不变：`si_sdr(x, 2.5*x) == si_sdr(x, x)`；
3. 单调性：噪声 σ=0.1 的 SI-SDR < σ=0.01 的；
4. 静音 GT → None；
5. 手算锚点：`s` 与正交扰动构造，手推期望值 ±1e-6；
6. `mixture_consistency`：精确加和 → −120.0；残差能量 = mix 能量 1% → ≈ −20.0（±0.1）；
7. `leakage`：估计=纯别轨 GT → ≈ 0.0 dB；估计=自轨且与他轨正交 → < −60；估计静音 → None。

- [ ] TDD 全流程 + `pytest tests/benchmark/ -q` 全绿
- [ ] Commit: `feat(benchmark): add self-implemented si-sdr, mixture consistency and leakage metrics`

---

### Task 3: `metrics.py`（二）— museval SDR wrapper + GT 装载 + 逐组合客观指标

**Files:**
- Modify: `workers/audio/lmdj_audio_worker/benchmark/metrics.py`（追加）
- Test: `workers/audio/tests/benchmark/test_metrics_objective.py`

**Interfaces:**
- Produces:
  - `sdr_framewise_median(references: dict, estimates: dict) -> dict[str, float | None]`：museval `bss_eval`，堆叠 `(4, samples, ch)`，window=hop=44100，逐 stem 帧 `nanmedian`；全 NaN → None
  - `load_stems_dir(dir: Path) -> dict[str, np.ndarray]`（4 canonical wav → (frames,2) float32；缺轨 ValueError）
  - `load_gt(track) -> dict[str, np.ndarray]`（`manifest.data_root()` 解析；采样率非 44100 ValueError；与估计长度差 ≤1 sample 截齐，超差 ValueError——对齐入口在 `objective_for_combo` 内做）
  - `objective_for_combo(combo_dir: Path, track, mix: np.ndarray) -> dict`：无 GT → `{"has_gt": False, "mixture_consistency": <float>}`；有 GT → 再补 `{"sdr": {stem…, "mean"}, "si_sdr": {…, "mean"}, "leakage": {…}}`（mean 对 None 跳过）
- 测试：合成信号四轨（不同频率正弦/脉冲）；GT=自身 → SDR/SI-SDR 极高；GT=加噪 → 有限值；缺轨/坏采样率错误路径。museval 真实调用（Task 1 已装）。

- [ ] TDD + `pytest tests/benchmark/ -q` 全绿
- [ ] Commit: `feat(benchmark): compute per-combo objective metrics with museval sdr`

---

### Task 4: `benchmark/patch_metrics.py` — Patch 指标提取

**Files:**
- Create: `workers/audio/lmdj_audio_worker/benchmark/patch_metrics.py`
- Test: `workers/audio/tests/benchmark/test_patch_metrics.py`

**Interfaces:**
- Produces: `patch_metrics_for_combo(combo_dir: Path, track_id: str) -> dict`：从 `combo.json` + `pfs/<track_id>/report.json` + 同目录 `patch.json` 提取：`{"combo_completed": bool, "pipeline_status": "passed"|"rejected"|"failed"|None, "validation_score": float|None, "attempts": int|None, "drum_degraded": bool|None, "n_samples": int|None, "n_lanes": int|None, "lane_names": list|None, "patch_loads": bool}`。`drum_degraded` = lane 名含 `drum_low`/`drum_high`（demo 降级键位约定）；`patch_loads` = patch.json 存在、可解析、含 `patch_id`。文件缺失逐项 None，不抛异常。
- 测试：手工 combo 目录 fixture 四种（完整 passed / 缺 pfs / 降级 lanes / 坏 patch.json）。

- [ ] TDD + 全绿；Commit: `feat(benchmark): extract patch quality metrics from combo outputs`

---

### Task 5: `benchmark/scoring.py` — 归一化、权重、硬门槛

**Files:**
- Create: `workers/audio/lmdj_audio_worker/benchmark/scoring.py`
- Test: `workers/audio/tests/benchmark/test_scoring.py`

**Interfaces:**
- Produces:
  - `WEIGHTS = {"reliability": {"batch_success": 6, "contract_compliance": 2, "structural_stability": 2}, "separation": {"sdr": 15, "si_sdr": 10, "consistency_leakage": 5}, "patch": {"completed_passed": 15, "validation_score": 10, "retry_degrade_structure": 5, "blind_listening": 10}, "performance": {"rtf_wall": 12, "peak_memory": 5, "size_load": 3}}`
  - `normalize_metric(values: dict[str, float | None], lower_better: bool = False) -> tuple[dict, bool]`：跨 separator min-max；None 保 None；单值/全等 → 全 1.0 + `degenerate=True`
  - `composite_scores(per_separator_metrics: dict, listening: dict | None) -> dict`：分项得分 + 总分；盲听缺失 → 该分项 `"missing"`、总分按 90 分制并标 `"scored_out_of": 90`
  - `hard_gates(per_separator: dict, attestations: dict | None, listening: dict | None, baseline_id: str = "htdemucs") -> dict`：§9.5 逐门槛 `"pass"|"fail"|"unknown"`（contract 合规 100% = invalid_stems 失败数 0；成功率 ≥95%；passed rate ≥ baseline−5pp，baseline 缺席 → unknown；双平台 smoke 与内存门槛依赖 attestations，缺 → unknown；盲听否决依赖 listening veto 标记）+ `"any_gate_failed": bool`
- 关键测试（spec §12.1 点名）：`sum(所有叶子权重) == 100`；**gate fail 的 separator 无论总分多高都 `gate_blocked: true`**；盲听缺失不置 0（断言 "missing" + scored_out_of 90）；退化归一化标注；lower_better 反向正确。

- [ ] TDD + 全绿；Commit: `feat(benchmark): add scoring weights, normalization and hard gates`

---

### Task 6: `benchmark/report.py` — 聚合与 summary 产出（含跨平台 merge）

**Files:**
- Create: `workers/audio/lmdj_audio_worker/benchmark/report.py`
- Test: `workers/audio/tests/benchmark/test_report.py`

**Interfaces:**
- Produces:
  - `collect_run(run_dir: Path, manifests: dict | None = None) -> dict`：遍历 results 树读 combo.json + patch_metrics + （有 GT 且 stems 在时）objective metrics；聚合每 separator×device：组合数/完成率/失败分类计数、性能（wall/inference 均值、RTF=inference_seconds/duration、peak RSS/device 最大、checkpoint 大小实测 stat + model_load 均值）、结构稳定性（同 track 多 repeat 的 `(n_samples, lane_names)` 一致比例；无重复 → None）
  - `build_summary(runs: list[dict], listening: dict | None, attestations: dict | None) -> dict`：多 run 合并（同 separator 跨设备并列）、scoring/hard_gates 装配、逐组合原始记录全保留
  - `write_summary(out_dir: Path, summary: dict) -> None`：`summary.json` + `summary.csv`（每行 separator×device：完成率/SDR mean/SI-SDR mean/MC/leak worst/passed rate/RTF/peak mem/总分/gate 状态；pandas to_csv）
  - summary 无绝对路径（测试断言）
- 测试：手工构造两个小 run fixture（objective 部分直接注入 metrics dict——monkeypatch `objective_for_combo`），断言聚合数、跨 run merge、csv 列与读回。

- [ ] TDD + 全绿；Commit: `feat(benchmark): aggregate runs into summary json and csv with cross-platform merge`

---

### Task 7: `benchmark/listening.py` — 匿名盲听打包

**Files:**
- Create: `workers/audio/lmdj_audio_worker/benchmark/listening.py`
- Test: `workers/audio/tests/benchmark/test_listening.py`

**Interfaces:**
- Produces:
  - `build_listening_package(run_dir: Path, include_stems: bool = True) -> Path`：每个 completed 组合 → `listening-test/<uuid4().hex[:12]>/`：拷 `pfs/<track>/render_preview.wav`→`render.wav`、`loop_preview.wav`→`loop.wav`、（可选）4 分轨 →`stem-1..4.wav`（**顺序随机化**，防顺序猜模型）；`listening-test/private-key.json`（anon_id → {track, separator, device, repeat, stem_order}）；`listening-test/README.md`（spec §9.3 协议：≥3 人、四维度 1–5 分模板）
  - 匿名目录内不得含 separator/track 字符串（文件名统一化）
  - `load_listening_scores(scores_path: Path, key_path: Path) -> dict`：`{anon_id: {rater: {dim: 1..5}}}` + key → 按 separator 聚合：全维度全评分者均值线性折算 0–10 + `veto` 检测（任一维度被 ≥2 人打 1）
- 测试：假 run fixture → 打包 → `grep -r "<separator id>" listening-test --exclude=private-key.json` 零命中、key 含 stem_order、评分还原数值 + veto 判定（构造 2 人打 1 的维度）。

- [ ] TDD + 全绿；Commit: `feat(benchmark): build anonymized listening package and score loader`

---

### Task 8: CLI（`report` / `listening-package`）+ dev.sh

**Files:**
- Modify: `workers/audio/lmdj_audio_worker/cli.py`、`scripts/dev.sh`
- Test: `workers/audio/tests/test_cli_report.py`

**Interfaces:**
- `lmdj-audio-worker report --run DIR [--run DIR2] [--listening-scores F] [--attestations F] [--out DIR]`（默认 out=第一个 run dir）：collect→build→write；打印每 separator 总分 + gate 状态对齐文本表；gate fail 不改变 exit code（报告工具非门禁执行者）但表格标注 `GATE FAILED`
- `lmdj-audio-worker listening-package --run DIR [--no-stems]`
- dev.sh：`bench-report` / `bench-listen` 包装（cwd=ROOT）+ usage/case
- 测试：monkeypatch collect/build/write，断言参数装配、多 --run 聚合、打印含表头；`bash -n`。

- [ ] TDD + 全绿；Commit: `feat(benchmark): add report and listening-package cli commands`

---

### Task 9: 真实验收 — 合成 GT 全链 + 真实报告

前置（本 worktree）：`scripts/dev.sh setup`、`setup-pfs`、`setup-sep-demucs`、`setup-sep-mel-roformer`（checkpoint 已在 ~/.cache，无需下载）。

- [ ] **Step 1: 合成 GT fixture**（一次性脚本放 /tmp）：生成 `/tmp/bench-gt-data/gt-song/`：四个 10s 44.1k 立体声 float32 合成 stem——`bass.wav`（80Hz 正弦）、`drums.wav`（2Hz 间隔宽带脉冲串）、`other.wav`（440+660Hz 和声）、`vocals.wav`（300Hz 带 5Hz 颤音正弦），`mix.wav` = 四轨逐样本精确加和；再把 `testdata/audio/suno/boom-bap/boom-bap-01.mp3` 拷入 `/tmp/bench-gt-data/`；manifest `/tmp/gt.manifest.json`：track `gt-song`（input=gt-song/mix.wav，has_ground_truth=true，四轨相对路径）+ track `boom-bap-01`（无 GT）。
- [ ] **Step 2: 跑 benchmark**：`LMDJ_BENCH_DATA_ROOT=/tmp/bench-gt-data scripts/dev.sh bench --dataset /tmp/gt.manifest.json --separators htdemucs,mel-roformer-4stem --device mps --run-id accept-1cb`（4 组合，全链数分钟）。
- [ ] **Step 3: 生成报告**：`scripts/dev.sh bench-report --run benchmarks/accept-1cb` → 检查 summary.json/summary.csv：GT track 的 SDR/SI-SDR 有限（合成频段可分，htdemucs SDR 应显著 >0）、两 separator 都有 MC、无 GT track 只有 MC、总分表两行、盲听列 "missing" + scored_out_of 90、双平台 gate "unknown"、csv pandas 可读回。数值记录进 task report。
- [ ] **Step 4: 盲听打包**：`scripts/dev.sh bench-listen --run benchmarks/accept-1cb`；`grep -r "htdemucs\|mel-roformer\|gt-song\|boom-bap" benchmarks/accept-1cb/listening-test --exclude=private-key.json` 零命中。
- [ ] **Step 5: mock 评分走 `--listening-scores`**：构造 3 人评分文件 → 总分含盲听分项（scored_out_of 100）；再构造含"某 separator 两人打 1"的评分 → 该 separator `veto_failed` + `gate_blocked`。
- [ ] **Step 6: 清理 /tmp**；`git status` 干净；验收数据（SDR/SI-SDR 表、总分表、veto 演示）写入 task report。

---

### Task 10: 文档同步 + spec 修订

**Files:** `CLAUDE.md` / `AGENTS.md`、`docs/superpowers/2026-07-10-status-and-backlog.md`、`docs/prd/decision-log.md`、`docs/design/2026-07-15-multi-separator-benchmark-design.md`

- [ ] CLAUDE/AGENTS：命令块 `bench` 行后加：

```text
scripts/dev.sh bench-report --run DIR [...]   # aggregate run(s) -> summary.json/csv with §9 scoring and hard gates
scripts/dev.sh bench-listen --run DIR         # build anonymized blind-listening package
```

workers/audio 条目 benchmark 句子改为完整版（1C-a 执行层 + 1C-b 指标评分层，spec §7–§9 落地；SI-SDR self-implemented, museval pinned）。
- [ ] status-and-backlog：里程碑 `| #11 | Separation Phase 1C-b：指标/评分/报告/盲听打包（museval SDR + 自实现 SI-SDR/一致性/泄漏，§9 权重与硬门槛，summary.json/csv + 跨平台 merge，匿名盲听包）。plan: docs/plans/2026-07-16-separation-phase1c-metrics.md | workers/audio/benchmark |`；下一步候选更新：仅剩 1D 物料（MUSDB18HQ 下载、歌曲集扩充）与 1D 执行。
- [ ] **spec §9.2 修订**：`- SI-SDR 使用 \`fast_bss_eval\`，全曲整段计算；` 改为 `- SI-SDR 自实现（Le Roux 2019 标准公式，纯 numpy，全曲整段、逐声道均值；fast_bss_eval 0.1.4 在无 torch 环境下 si_sdr 损坏，弃用）；一致性与泄漏的精确定义以 plan 2026-07-16-separation-phase1c-metrics 的"自定义指标的精确定义"节为规范；`
- [ ] decision-log `2026-07-16` 追加：SI-SDR 自实现决策（含损坏证据）、泄漏/一致性定义、归一化方案（同 run min-max + 退化标注 + 盲听缺失 90 分制）、盲听匿名化含 stem 顺序随机化。
- [ ] Commit: `docs: record separation phase 1c-b metrics layer and spec amendments`

---

## 收尾验证（全量）

```bash
cd workers/audio && .venv/bin/python -m pytest tests/ -q   # 全绿（179 + 新增）
scripts/dev.sh test
# Task 9 验收命令可重放（benchmark cache 命中，报告重生成）
```

## Spec 覆盖对照（自查）

| Spec 要求 | Task |
|---|---|
| §9.1 可靠性分项（批次成功/contract 合规/结构稳定） | 5, 6 |
| §9.2 SDR（museval BSSv4 framewise median）/SI-SDR/一致性/泄漏 + 版本 pin + per-stem 保留 | 1–3 |
| §9.3 Patch 指标 + 盲听协议（四维度 1–5、均值折算 0–10、否决规则） | 4, 7 |
| §9.4 性能成本分项 + 综合分只在同 run 排序 + 原始指标全保留 | 5, 6 |
| §9.5 硬门槛逐条 + 外部 attestations 显式化 + 不可被总分抵消 | 5 |
| §8 summary.json/csv + listening-test/ + 跨平台 merge + 随机匿名 id + 私有 key | 6, 7 |
| §12.1 评分权重总和、门槛不可绕过 | 5 |
| spec §9.2 pin 修订（fast_bss_eval 弃用） | 10 |

不在本 plan 范围：MUSDB18HQ 下载与真实歌曲集扩充（1D 物料，需用户操作）、Linux CPU run 与三重复稳定性子集的实际执行（1D）、生产接入（Phase 2）。
