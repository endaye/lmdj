# Separation Phase 1B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 BS-RoFormer 与 Mel-Band RoFormer 两个四轨 runner（均 `experimental`），registry 填入过门禁的真实条目，Mac MPS 验收；同时把 MSST 家族 runner 逻辑抽取为共享实现（scnet 重构为薄壳，行为不变）。

**Architecture:** 三个 MSST 家族 runner（scnet / bs_roformer / mel_band_roformer）共享 `runners/_msst.py` 的参数化实现（模型加载、demix、canonical 映射逐行来自已验收的 scnet.py），每个 runner 仍是独立模块 + **独立 venv**（spec §5 字面），但共享同一份 constraints（`runner-scnet-constraints.txt`）与同一个 MSST pinned clone（`.msst`，read-only，`msst.lock` 锁定）。

**Tech Stack:** 与 Phase 1A scnet 栈完全相同（torch==2.12.1 等，constraints 不变）。

**Spec:** `docs/superpowers/specs/2026-07-15-multi-separator-benchmark-design.md`（§5/§6/§10；§6 对 RoFormer 的门禁：只启用能追溯来源、固定 revision、明确四轨与许可的 checkpoint）。

**Base branch:** `main`（Phase 1A 已合并，e277e1d0）。分支 `codex/feat-separation-phase1b`。

## 已核实的事实（2026-07-16 调研 + 用户决策）

- **BS-RoFormer 四轨 checkpoint**（唯一合规候选）：MSST release **v1.0.12**，ZFTurbo 训练，MUSDB test SDR **9.65**：
  - ckpt: `https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/v1.0.12/model_bs_roformer_ep_17_sdr_9.6568.ckpt`
  - config: `https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/v1.0.12/config_bs_roformer_384_8_2_485100.yaml`
  - config 已核验 `instruments: ['drums', 'bass', 'other', 'vocals']`、`target_instrument: null`。
- **Mel-Band RoFormer 四轨 checkpoint**（用户选定 ep_1）：MSST release **v1.0.11**，SDR **8.22**，单文件 234MB：
  - ckpt: `https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/v1.0.11/model_mel_band_roformer_ep_1_sdr_8.2175.ckpt`
  - config: `https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/v1.0.11/model_mel_band_roformer_ep_1_sdr_8.2175.yaml`
  - config 已核验四轨。**弃选**：同 release 的 ep_5（SDR 8.94）是 3.5GB 双分卷 zip，与单 artifact 缓存契约冲突（升级路径记入 decision-log）；HF 社区 FT（SYH99999）可追溯性弱于 ZFTurbo release。
- 两个 checkpoint 与 config 均在 MSST（MIT）的不可变 GitHub release 上；license 门禁可过。
- MSST 推理仍走 pinned clone（`msst.lock` @ 83d495df）的 `demix`；`model_type` 字符串预期为 `"bs_roformer"` / `"mel_band_roformer"`——实施时对照 `.msst/utils/settings.py` 真实分支核对（1A 的核对惯例）。
- spec §8 的 separator id 示例即 `bs-roformer-4stem` / `mel-roformer-4stem`——采用。

## Global Constraints

- `workers/audio` 主包 `dependencies` 保持 `[]`；torch/MSST 只在 runner venv；runner 模块顶层不得 import torch/MSST。
- **scnet 重构必须行为不变**：常量、CLI、错误类别、输出一字不变；验收任务里 re-smoke scnet 证明无回归。
- 不允许静默设备 fallback；MPS OOM 时**预授权重放 1A 的 batch_size→1 调优**（用户已批准该模式：改 vendored yaml + 注释头 + registry inference dict/config_sha256 同步），调优后仍 OOM → BLOCKED 上报。
- 两个新条目 status = `experimental`（spec §6：双平台验证后才可升 verified）；env_lock_sha256 = `msst.lock` 的 SHA-256（与 scnet 相同——三者共享同一推理环境锁）。
- vendored config 落 `workers/audio/config/bs_roformer/` 与 `workers/audio/config/mel_band_roformer/`（`config/**` 已有 LFS 豁免 + text diff）。
- MSST clone 只读；`references/demos/` 冻结；commit 符合 Conventional Commits v1.0.0。

## 准备

```bash
cd workers/audio
python3 -m venv .venv 2>/dev/null || true
.venv/bin/pip install -e ../../packages/core-models -e ../../packages/patchify
.venv/bin/pip install -e ".[test,pfs]" -c config/parity-constraints.txt
.venv/bin/python -m pytest tests/ -q   # 基线 121 tests 全绿
```

---

### Task 1: `runners/_msst.py` 共享实现 + scnet 薄壳重构

**Files:**
- Create: `workers/audio/lmdj_audio_worker/separation/runners/_msst.py`
- Modify: `workers/audio/lmdj_audio_worker/separation/runners/scnet.py`（重构为薄壳，常量与行为不变）
- Test: `workers/audio/tests/separation/test_msst_family.py`

**Interfaces:**
- Consumes: `runners/common.py` 全套（Phase 1A Task 1/2）
- Produces（Task 2/3 依赖）：
  - `msst_dir() -> Path`（`LMDJ_MSST_DIR` 覆盖，默认 `workers/audio/.msst`）
  - `msst_work(args, *, model_type: str, config_path: Path, artifact_name: str, setup_hint: str) -> RunnerOutput` —— scnet.py `_work` 的逐行参数化搬移（模型加载/权重解包/demix/canonical 映射/性能合并全部不变；错误消息里的 setup 提示改为 `setup_hint` 参数）
  - `CANONICAL_FROM_MSST = {"drums": "drums", "bass": "bass", "vocals": "vocals", "other": "other"}`

- [ ] **Step 1: Write the failing tests**

```python
# workers/audio/tests/separation/test_msst_family.py
from __future__ import annotations

from pathlib import Path

import pytest

from lmdj_audio_worker.separation.runners import _msst, scnet
from lmdj_audio_worker.separation.runners.common import RunnerError


def test_msst_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("LMDJ_MSST_DIR", str(tmp_path / "custom"))
    assert _msst.msst_dir() == tmp_path / "custom"


def test_msst_dir_default_under_worker_root(monkeypatch):
    monkeypatch.delenv("LMDJ_MSST_DIR", raising=False)
    assert _msst.msst_dir().name == ".msst"
    assert _msst.msst_dir().parent.name == "audio"


def test_missing_clone_raises_with_hint(monkeypatch, tmp_path):
    monkeypatch.setenv("LMDJ_MSST_DIR", str(tmp_path / "nowhere"))

    class Args:
        input = tmp_path / "in.wav"
        output = tmp_path / "out"
        device = "cpu"
        checkpoint_dir = tmp_path / "ckpt"
        seed = 0

    with pytest.raises(RunnerError) as exc:
        _msst.msst_work(Args(), model_type="scnet",
                        config_path=tmp_path / "cfg.yaml",
                        artifact_name="a.ckpt",
                        setup_hint="scripts/dev.sh setup-sep-scnet")
    assert exc.value.category == "inference"
    assert "setup-sep-scnet" in str(exc.value)


def test_scnet_constants_unchanged():
    # 重构后薄壳的公开常量必须与 1A 验收版本一字不差
    assert scnet.RUNNER_ID == "scnet-large"
    assert scnet.FAMILY == "scnet"
    assert scnet.RUNNER_VERSION == "0.1.0"
    assert scnet.ARTIFACT == "SCNet-large_starrytong_fixed.ckpt"
    assert scnet.MODEL_TYPE == "scnet"
    assert scnet.CONFIG_PATH.name == "config_musdb18_scnet_large_starrytong.yaml"


def test_scnet_work_delegates_to_msst(monkeypatch):
    captured = {}

    def fake_msst_work(args, **kwargs):
        captured.update(kwargs)
        return "SENTINEL"

    monkeypatch.setattr(scnet, "msst_work", fake_msst_work)
    assert scnet._work(object()) == "SENTINEL"
    assert captured["model_type"] == "scnet"
    assert captured["artifact_name"] == scnet.ARTIFACT
    assert captured["config_path"] == scnet.CONFIG_PATH
    assert "setup-sep-scnet" in captured["setup_hint"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/separation/test_msst_family.py -q
```

Expected: FAIL（`_msst` 不存在）。

- [ ] **Step 3: Write the implementation**

`workers/audio/lmdj_audio_worker/separation/runners/_msst.py`（`msst_work` 主体逐行来自 1A 已验收的 `scnet.py::_work`，只做参数化——不要"顺手改进"）：

```python
# workers/audio/lmdj_audio_worker/separation/runners/_msst.py
"""MSST 家族 runner 共享实现（scnet / bs_roformer / mel_band_roformer）。

模型加载、demix、canonical 映射逐行来自 Phase 1A 已验收的 scnet runner；
三个家族只在常量（model_type / config / artifact / venv）上不同。
MSST 不是 pip 包：sys.path 注入 workers/audio/.msst（LMDJ_MSST_DIR 可覆盖）。
只读使用，不修改其源码；API 以 config/msst.lock 的 commit 为准。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from .common import (DeviceMemorySampler, PerfTracker, RunnerError,
                     RunnerOutput, load_stereo_44k, resolve_device)

_WORKER_ROOT = Path(__file__).resolve().parents[3]
CANONICAL_FROM_MSST = {"drums": "drums", "bass": "bass",
                       "vocals": "vocals", "other": "other"}


def msst_dir() -> Path:
    return Path(os.environ.get("LMDJ_MSST_DIR", _WORKER_ROOT / ".msst"))


def msst_work(args, *, model_type: str, config_path: Path,
              artifact_name: str, setup_hint: str) -> RunnerOutput:
    msst = msst_dir()
    if not (msst / "utils").exists():
        raise RunnerError(
            f"MSST clone 缺失: {msst} — 先运行 {setup_hint}",
            category="inference")
    sys.path.insert(0, str(msst))
    import torch
    from utils.model_utils import demix
    from utils.settings import get_model_from_config  # pinned commit 核对

    device = resolve_device(args.device)
    torch.manual_seed(args.seed)
    tracker = PerfTracker()

    artifact = Path(args.checkpoint_dir) / artifact_name
    if not artifact.exists():
        raise RunnerError(f"checkpoint 缺失: {artifact}", category="checksum")
    with tracker.phase("model_load"):
        model, config = get_model_from_config(model_type, str(config_path))
        state = torch.load(artifact, map_location="cpu", weights_only=False)
        if isinstance(state, dict) and "state_dict" in state:
            state = state["state_dict"]
        model.load_state_dict(state)
        model.to(device)
        model.eval()

    wav = load_stereo_44k(args.input)          # (frames, 2) float32, 44.1k
    mix = wav.T                                # MSST demix 期望 (2, frames)

    sampler = DeviceMemorySampler(device)
    sampler.start()
    with tracker.phase("inference"), torch.no_grad():
        separated = demix(config, model, mix, torch.device(device),
                          model_type=model_type, pbar=False)
    memory = sampler.stop()

    stems = {}
    for canonical, msst_name in CANONICAL_FROM_MSST.items():
        if msst_name not in separated:
            raise RunnerError(
                f"MSST 输出缺少 {msst_name}（收到 {sorted(separated)}）",
                category="invalid_stems")
        arr = separated[msst_name]
        if arr.ndim == 2 and arr.shape[0] == 2:   # (2, frames) -> (frames, 2)
            arr = arr.T
        stems[canonical] = arr.astype("float32")
    performance = tracker.snapshot() | memory
    return RunnerOutput(stems=stems, actual_device=device,
                        performance=performance)
```

`workers/audio/lmdj_audio_worker/separation/runners/scnet.py` 整体替换为薄壳（常量一字不变）：

```python
"""SCNet-large runner：MSST(pinned clone) demix -> canonical four stems（spec §5）。

实现在 runners/_msst.py（MSST 家族共享）；本模块只保留家族常量与 CLI 入口。
"""
from __future__ import annotations

import sys
from pathlib import Path

from ._msst import msst_work
from .common import run_runner_main

RUNNER_ID = "scnet-large"
FAMILY = "scnet"
RUNNER_VERSION = "0.1.0"
ARTIFACT = "SCNet-large_starrytong_fixed.ckpt"
MODEL_TYPE = "scnet"
_WORKER_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = _WORKER_ROOT / "config" / "scnet" / "config_musdb18_scnet_large_starrytong.yaml"


def _work(args):
    return msst_work(args, model_type=MODEL_TYPE, config_path=CONFIG_PATH,
                     artifact_name=ARTIFACT,
                     setup_hint="scripts/dev.sh setup-sep-scnet")


def main(argv: list[str] | None = None) -> int:
    return run_runner_main(argv, runner_id=RUNNER_ID, family=FAMILY,
                           runner_version=RUNNER_VERSION, work=_work)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/ -q
```

Expected: 全部 PASS（121 + 5 新）。

- [ ] **Step 5: Commit**

```bash
git add workers/audio/lmdj_audio_worker/separation/runners/_msst.py \
        workers/audio/lmdj_audio_worker/separation/runners/scnet.py \
        workers/audio/tests/separation/test_msst_family.py
git commit -m "refactor(runners): extract shared msst family worker from scnet"
```

---

### Task 2: BS-RoFormer runner + venv + vendored config

**Files:**
- Create: `workers/audio/lmdj_audio_worker/separation/runners/bs_roformer.py`
- Create: `workers/audio/config/bs_roformer/config_bs_roformer_384_8_2_485100.yaml`（下载入库）
- Modify: `scripts/dev.sh`（`ensure_msst_clone` / `setup_msst_family_venv` 辅助抽取 + `setup-sep-bs-roformer` + usage + case）

**Interfaces:**
- Consumes: Task 1 的 `msst_work`；`runner-scnet-constraints.txt`（三家族共享）；`.msst` clone
- Produces: CLI 同族；常量 `RUNNER_ID = "bs-roformer-4stem"`、`FAMILY = "bs_roformer"`、`RUNNER_VERSION = "0.1.0"`、`ARTIFACT = "model_bs_roformer_ep_17_sdr_9.6568.ckpt"`、`MODEL_TYPE = "bs_roformer"`；dev.sh 辅助 `ensure_msst_clone` / `setup_msst_family_venv`（Task 3 复用）

- [ ] **Step 1: 下载 vendored config 并核验**

```bash
curl -fsSL --create-dirs -o workers/audio/config/bs_roformer/config_bs_roformer_384_8_2_485100.yaml \
  https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/v1.0.12/config_bs_roformer_384_8_2_485100.yaml
grep -E "instruments|sample_rate|batch_size|chunk_size" workers/audio/config/bs_roformer/*.yaml | head
shasum -a 256 workers/audio/config/bs_roformer/config_bs_roformer_384_8_2_485100.yaml   # 记录 → Task 4
```

Expected: `instruments: ['drums', 'bass', 'other', 'vocals']`、sample_rate 44100。记录 inference 段的 batch_size/chunk_size 原始值。

- [ ] **Step 2: Write the runner**

```python
# workers/audio/lmdj_audio_worker/separation/runners/bs_roformer.py
"""BS-RoFormer 4-stem runner：MSST(pinned clone) demix -> canonical four stems。

checkpoint：MSST release v1.0.12（ZFTurbo 训练，MUSDB SDR 9.65，MIT）。
实现在 runners/_msst.py；本模块只保留家族常量与 CLI 入口。
"""
from __future__ import annotations

import sys
from pathlib import Path

from ._msst import msst_work
from .common import run_runner_main

RUNNER_ID = "bs-roformer-4stem"
FAMILY = "bs_roformer"
RUNNER_VERSION = "0.1.0"
ARTIFACT = "model_bs_roformer_ep_17_sdr_9.6568.ckpt"
MODEL_TYPE = "bs_roformer"
_WORKER_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = _WORKER_ROOT / "config" / "bs_roformer" / "config_bs_roformer_384_8_2_485100.yaml"


def _work(args):
    return msst_work(args, model_type=MODEL_TYPE, config_path=CONFIG_PATH,
                     artifact_name=ARTIFACT,
                     setup_hint="scripts/dev.sh setup-sep-bs-roformer")


def main(argv: list[str] | None = None) -> int:
    return run_runner_main(argv, runner_id=RUNNER_ID, family=FAMILY,
                           runner_version=RUNNER_VERSION, work=_work)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: dev.sh — 抽共享辅助 + 新命令**

变量区追加 `SEP_BSROF_VENV="$WORKER/.venv-sep-bs-roformer"`。把 `cmd_setup_sep_scnet` 中的 clone 段与 venv 建立段抽成两个辅助函数（放在 `cmd_setup_sep_scnet` 之前；scnet 命令改为调用它们，输出行保持不变）：

```bash
ensure_msst_clone() {
  local lock="$WORKER/config/msst.lock"
  local url commit
  url=$(grep '^url=' "$lock" | cut -d= -f2-)
  commit=$(grep '^commit=' "$lock" | cut -d= -f2-)
  if [ ! -d "$MSST_DIR/.git" ]; then
    echo "==> clone MSST @ ${commit}"
    git clone --no-checkout "$url" "$MSST_DIR"
  fi
  (cd "$MSST_DIR" && git fetch -q origin "$commit" && git checkout -q "$commit")
}

setup_msst_family_venv() {
  local venv="$1"
  if [ ! -x "$venv/bin/python" ]; then
    echo "==> 创建 $(basename "$venv")"
    python3 -m venv "$venv"
  fi
  "$venv/bin/pip" -q install -e "$CORE" -c "$WORKER/config/runner-scnet-constraints.txt"
  "$venv/bin/pip" -q install -e "$PATCHIFY" -c "$WORKER/config/runner-scnet-constraints.txt"
  grep -v '^#' "$WORKER/config/runner-scnet-constraints.txt" | sed '/^$/d' > /tmp/msst-reqs.txt
  "$venv/bin/pip" -q install -e "$WORKER" -r /tmp/msst-reqs.txt
}

cmd_setup_sep_bs_roformer() {
  ensure_msst_clone
  setup_msst_family_venv "$SEP_BSROF_VENV"
  echo "==> bs-roformer runner venv 就绪"
}
```

usage 追加 `setup-sep-bs-roformer  创建 BS-RoFormer runner venv（复用 MSST clone/constraints）`；case 表加 `setup-sep-bs-roformer) cmd_setup_sep_bs_roformer ;;`。

- [ ] **Step 4: 建 venv + import/CLI smoke + 全量单测**

```bash
bash -n scripts/dev.sh && scripts/dev.sh setup-sep-bs-roformer
workers/audio/.venv-sep-bs-roformer/bin/python -m lmdj_audio_worker.separation.runners.bs_roformer --help
grep -n "bs_roformer" workers/audio/.msst/utils/settings.py | head -3   # model_type 分支核对，记入 report
cd workers/audio && .venv/bin/python -m pytest tests/ -q
```

Expected: `--help` exit 0；grep 命中 `bs_roformer` 分支；主 venv 全绿。

- [ ] **Step 5: Commit**

```bash
git add workers/audio/lmdj_audio_worker/separation/runners/bs_roformer.py \
        workers/audio/config/bs_roformer scripts/dev.sh
git commit -m "feat(runners): add bs-roformer 4-stem runner"
```

---

### Task 3: Mel-Band RoFormer runner + venv + vendored config

**Files:**
- Create: `workers/audio/lmdj_audio_worker/separation/runners/mel_band_roformer.py`
- Create: `workers/audio/config/mel_band_roformer/model_mel_band_roformer_ep_1_sdr_8.2175.yaml`（下载入库）
- Modify: `scripts/dev.sh`（`setup-sep-mel-roformer` + usage + case）

**Interfaces:**
- Consumes: Task 1 `msst_work`、Task 2 的 `ensure_msst_clone`/`setup_msst_family_venv`
- Produces: 常量 `RUNNER_ID = "mel-roformer-4stem"`、`FAMILY = "mel_band_roformer"`、`RUNNER_VERSION = "0.1.0"`、`ARTIFACT = "model_mel_band_roformer_ep_1_sdr_8.2175.ckpt"`、`MODEL_TYPE = "mel_band_roformer"`

- [ ] **Step 1: 下载 vendored config 并核验**

```bash
curl -fsSL --create-dirs -o workers/audio/config/mel_band_roformer/model_mel_band_roformer_ep_1_sdr_8.2175.yaml \
  https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/v1.0.11/model_mel_band_roformer_ep_1_sdr_8.2175.yaml
grep -E "instruments|sample_rate|batch_size|chunk_size" workers/audio/config/mel_band_roformer/*.yaml | head
shasum -a 256 workers/audio/config/mel_band_roformer/model_mel_band_roformer_ep_1_sdr_8.2175.yaml   # 记录 → Task 4
```

- [ ] **Step 2: Write the runner**

```python
# workers/audio/lmdj_audio_worker/separation/runners/mel_band_roformer.py
"""Mel-Band RoFormer 4-stem runner：MSST(pinned clone) demix -> canonical four stems。

checkpoint：MSST release v1.0.11 ep_1（SDR 8.22，MIT）。同 release 的 ep_5（8.94）
是多分卷 zip，与单 artifact 缓存契约冲突——升级路径见 decision-log 2026-07-16。
实现在 runners/_msst.py；本模块只保留家族常量与 CLI 入口。
"""
from __future__ import annotations

import sys
from pathlib import Path

from ._msst import msst_work
from .common import run_runner_main

RUNNER_ID = "mel-roformer-4stem"
FAMILY = "mel_band_roformer"
RUNNER_VERSION = "0.1.0"
ARTIFACT = "model_mel_band_roformer_ep_1_sdr_8.2175.ckpt"
MODEL_TYPE = "mel_band_roformer"
_WORKER_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = (_WORKER_ROOT / "config" / "mel_band_roformer"
               / "model_mel_band_roformer_ep_1_sdr_8.2175.yaml")


def _work(args):
    return msst_work(args, model_type=MODEL_TYPE, config_path=CONFIG_PATH,
                     artifact_name=ARTIFACT,
                     setup_hint="scripts/dev.sh setup-sep-mel-roformer")


def main(argv: list[str] | None = None) -> int:
    return run_runner_main(argv, runner_id=RUNNER_ID, family=FAMILY,
                           runner_version=RUNNER_VERSION, work=_work)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: dev.sh** — 变量 `SEP_MELROF_VENV="$WORKER/.venv-sep-mel-roformer"`；命令：

```bash
cmd_setup_sep_mel_roformer() {
  ensure_msst_clone
  setup_msst_family_venv "$SEP_MELROF_VENV"
  echo "==> mel-roformer runner venv 就绪"
}
```

usage 追加 `setup-sep-mel-roformer  创建 Mel-Band RoFormer runner venv（复用 MSST clone/constraints）`；case 表加对应行。

- [ ] **Step 4: 建 venv + smoke + 全量单测**

```bash
bash -n scripts/dev.sh && scripts/dev.sh setup-sep-mel-roformer
workers/audio/.venv-sep-mel-roformer/bin/python -m lmdj_audio_worker.separation.runners.mel_band_roformer --help
grep -n "mel_band_roformer" workers/audio/.msst/utils/settings.py | head -3
cd workers/audio && .venv/bin/python -m pytest tests/ -q
```

- [ ] **Step 5: Commit**

```bash
git add workers/audio/lmdj_audio_worker/separation/runners/mel_band_roformer.py \
        workers/audio/config/mel_band_roformer scripts/dev.sh
git commit -m "feat(runners): add mel-band-roformer 4-stem runner"
```

---

### Task 4: registry 两个新条目

**Files:**
- Modify: `workers/audio/config/separators.json`（追加两个条目，现有两条不动）
- Modify: `workers/audio/tests/separation/test_registry.py`（shipped 测试扩到 4 条目）

**Interfaces:**
- Consumes: Task 2/3 常量；已有 `msst.lock`（env_lock）与两个 vendored config（config_sha256）
- Produces: `bs-roformer-4stem` 与 `mel-roformer-4stem` 条目，均 `experimental`

- [ ] **Step 1: 计算 SHA-256**

```bash
curl -fsSL -o /tmp/bsrof.ckpt "https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/v1.0.12/model_bs_roformer_ep_17_sdr_9.6568.ckpt"
curl -fsSL -o /tmp/melrof.ckpt "https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/v1.0.11/model_mel_band_roformer_ep_1_sdr_8.2175.ckpt"
shasum -a 256 /tmp/bsrof.ckpt /tmp/melrof.ckpt
shasum -a 256 workers/audio/config/msst.lock \
              workers/audio/config/bs_roformer/config_bs_roformer_384_8_2_485100.yaml \
              workers/audio/config/mel_band_roformer/model_mel_band_roformer_ep_1_sdr_8.2175.yaml
```

（下载失败/404 → BLOCKED 上报，不得替换 URL。）

- [ ] **Step 2: 追加条目** —— 模板照抄现有 scnet-large 条目结构，逐字段替换：
  - `id`/`family`/`runner`：`bs-roformer-4stem`/`bs_roformer`/`bs_roformer` 与 `mel-roformer-4stem`/`mel_band_roformer`/`mel_band_roformer`
  - `command`：venv 路径 `workers/audio/.venv-sep-bs-roformer/bin/python`（mel 同理）+ 模块 `lmdj_audio_worker.separation.runners.bs_roformer`（/`.mel_band_roformer`），参数模板与 scnet 一致
  - `source`：对应 release URL；revision `"MSST release v1.0.12 (trained by ZFTurbo, MUSDB SDR 9.65)"` / `"MSST release v1.0.11 ep_1 (MUSDB SDR 8.22)"`
  - `artifact_sha256`：Step 1 真实值
  - `license`：`{"code": "MIT (ZFTurbo/MSST)", "weights": "MIT (MSST release v1.0.12)"}`（mel 用 v1.0.11）
  - `stems`/`sample_rate`/`channels`/`devices`：同 scnet（`["cpu", "mps"]`）
  - `inference`：`{"model_type": "...", "config": "config/<family>/<yaml 名>", "config_sha256": "<真实值>", "batch_size": <yaml 原始值>, "chunk_size": <yaml 原始值>}`
  - `env_lock_sha256`：msst.lock 的 sha（与 scnet 条目同值）
  - `status`: `"experimental"`

- [ ] **Step 3: 更新 shipped 测试** — `test_shipped_registry_file_is_valid`：`set(by_id) == {"htdemucs", "scnet-large", "bs-roformer-4stem", "mel-roformer-4stem"}`，新条目 status `experimental`。`test_shipped_env_locks_match_files`：lock_files 映射加两个新 id → `msst.lock`；config sha 断言扩到三个 vendored yaml（scnet + 两个 roformer）。

- [ ] **Step 4: Run tests**

```bash
cd workers/audio && .venv/bin/python -m pytest tests/ -q
```

- [ ] **Step 5: Commit**

```bash
git add workers/audio/config/separators.json workers/audio/tests/separation/test_registry.py
git commit -m "feat(registry): register bs-roformer and mel-roformer 4-stem checkpoints (experimental)"
```

---

### Task 5: 真实验收 — Mac MPS smoke x2 + scnet 重构回归

**Files:** 无新文件（验收任务；调优/修正按性质回改并单独 commit）

前置：testsong 存在（没有则 `scripts/dev.sh setup-demo` + `smoke`）；`setup-sep-scnet` / `setup-sep-bs-roformer` / `setup-sep-mel-roformer` 已运行；`scripts/dev.sh setup` 已运行。

- [ ] **Step 1: scnet 重构回归 smoke（cpu 即可，快）**

```bash
scripts/dev.sh separate scnet-large references/demos/lmdj-song-pipeline/output/testsong/input.wav cpu
```

Expected: exit 0（actual_device: cpu、canonical OK）——证明 Task 1 薄壳重构无行为回归。

- [ ] **Step 2: bs-roformer MPS smoke**

```bash
scripts/dev.sh separate bs-roformer-4stem references/demos/lmdj-song-pipeline/output/testsong/input.wav mps
```

首次真实下载 ckpt 并 sha 校验（校验失败 = registry 数据错误 → BLOCKED）。若 MPS OOM（oom/SIGKILL）：**重放 1A 调优协议**——vendored yaml `inference.batch_size → 1`（注释头写明来源 sha 与改动），registry `inference` dict + `config_sha256` 同步，registry 测试重跑，然后重试 MPS；仍 OOM → 恢复原样、不 commit、BLOCKED 上报（含数据）。

- [ ] **Step 3: mel-roformer MPS smoke**（同 Step 2 协议）

- [ ] **Step 4: 记录验收数据** — 三个 runner 的 performance 行（调优前后如适用）写入 task report；清理 smoke 输出目录，`git status` 干净。

---

### Task 6: 文档同步

**Files:** `CLAUDE.md` / `AGENTS.md`、`docs/superpowers/2026-07-10-status-and-backlog.md`、`docs/prd/decision-log.md`

- [ ] **Step 1: CLAUDE.md / AGENTS.md** — 命令块 `setup-sep-scnet` 行后各追加：

```text
scripts/dev.sh setup-sep-bs-roformer   # create the BS-RoFormer runner venv (shares MSST clone/constraints)
scripts/dev.sh setup-sep-mel-roformer  # create the Mel-Band RoFormer runner venv (shares MSST clone/constraints)
```

两文件 workers/audio 条目中 `separation/runners/` 一句更新为：

```text
`separation/runners/` holds per-family separator runners (htdemucs verified; scnet-large / bs-roformer-4stem / mel-roformer-4stem experimental — the three MSST-family runners share runners/_msst.py, one pinned clone and one constraints file, each in its own `.venv-sep-*` venv driven by the registry command); `separation/smoke.py` is the registry→cache→runner→canonical-validation smoke entry.
```

- [ ] **Step 2: status-and-backlog** — 里程碑表追加：

```text
| #9 | Separation Phase 1B：BS-RoFormer（SDR 9.65）+ Mel-Band RoFormer（SDR 8.22）四轨 runner 与 experimental registry 条目；MSST 家族共享实现抽取（scnet 薄壳化）；Mac MPS 验收。plan: `docs/superpowers/plans/2026-07-16-separation-phase1b.md` | `workers/audio/separation/runners`、`config/` |
```

- [ ] **Step 3: decision-log** — 既有 `## 2026-07-16` 节末尾追加：

```markdown
### 已确认：RoFormer 四轨 checkpoint 选型与 MSST 家族共享实现

- 结论：BS-RoFormer 采用 MSST release v1.0.12 的 `model_bs_roformer_ep_17_sdr_9.6568.ckpt`（ZFTurbo 训练，MUSDB SDR 9.65，唯一过门禁的四轨候选）；Mel-Band RoFormer 采用 MSST release v1.0.11 的 ep_1（SDR 8.22，单文件）——同 release 的 ep_5（SDR 8.94）为 3.5GB 双分卷 zip，与单 artifact 缓存契约冲突，弃选并记录为升级路径（需先扩展 cache/registry 支持多分卷 artifact）；HF 社区 fine-tune 因训练过程可追溯性弱于 ZFTurbo release 一并弃选。三个 MSST 家族 runner（scnet/bs/mel）共享 `runners/_msst.py` 实现、同一 MSST pinned clone 与同一 constraints 文件，但按 spec §5 字面各自独立 venv 运行。
- 原因：spec §6 对 RoFormer 门禁最严（来源/revision/四轨/许可缺一不可）；社区单目标权重不得伪装四轨。benchmark 公平性让位于基建契约完整性，ep_5 升级路径显式保留。
- 影响：mel-band 家族在 Phase 1D benchmark 中以 ep_1（非家族最强形态）参赛，解读结果时需注明 ~0.7dB 的形态差；若家族展现潜力，升级 ep_5 是独立的基建扩展 + 重验收。
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md AGENTS.md docs/superpowers/2026-07-10-status-and-backlog.md docs/prd/decision-log.md
git commit -m "docs: record separation phase 1b roformer runners and checkpoint decisions"
```

---

## 收尾验证（全量）

```bash
cd workers/audio && .venv/bin/python -m pytest tests/ -q
scripts/dev.sh test
scripts/dev.sh separate scnet-large <testsong> cpu          # 重构回归
scripts/dev.sh separate bs-roformer-4stem <testsong> mps    # exit 0
scripts/dev.sh separate mel-roformer-4stem <testsong> mps   # exit 0
```

## Spec 覆盖对照（自查）

| Spec 要求 | Task |
|---|---|
| §6 RoFormer 门禁（来源/revision/四轨/许可）——两个 checkpoint 均过 | 调研 + 2/3/4 |
| §6 "单目标权重不得伪装四轨"（vocal-only 权重全部排除） | 调研 |
| §5 独立子进程 + 独立 venv | 2/3（per-family venv，共享 clone/constraints） |
| §5 canonical/性能/失败自写（复用 1A scaffold） | 1 |
| §10 OOM 处理协议（预授权 batch 调优重放，不静默降级） | 5 |
| §12.2.1 Mac MPS smoke | 5 |

不在本 plan 范围：dataset manifests / orchestrator / 指标（1C）、Linux CPU（1D）、ep_5 多分卷升级（独立后续）。
