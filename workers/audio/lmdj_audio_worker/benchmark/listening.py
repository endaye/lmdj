"""匿名盲听打包 + 评分回读（spec §8/§9.3，Task 7）。

`build_listening_package` 遍历一个 run 目录的 `results/<dataset>/<track>/
<separator>/<device>/<repeat>/combo.json`，只挑 `status == "completed"` 的
组合，逐个复制到 `run_dir/listening-test/<uuid4().hex[:12]>/` 下的固定文件
名（`render.wav`/`loop.wav`/`stem-1..4.wav`），并把 track/separator/device/
repeat/stem 顺序只记录在 `listening-test/private-key.json` 里——匿名目录本
身（目录名、拷贝后的文件名、README 模板）绝不出现这些标识符字符串，这是
spec §8 "评测者看不到模型名，映射只保存在私有 key 文件中" 的字面实现。

`load_listening_scores` 是汇总阶段的另一半：把评分文件 + private-key 合并，
按 separator 聚合出 spec §9.3 定义的 0–10 线性折算分与否决判定，输出形状与
Task 5 `scoring.composite_scores`/`hard_gates` 的 `listening` 参数一致
（`{separator_id: {"score": float|None, "veto": bool}}`，这里额外附
`n_raters`/`n_combos` 供报告展示，`scoring.py` 只读 `score`/`veto` 两个键，
额外键不影响它）。
"""
from __future__ import annotations

import json
import random
import shutil
import uuid
from pathlib import Path

from ..separation.contract import CANONICAL_STEMS

DIMENSIONS: tuple[str, ...] = ("crosstalk", "transients", "low_end", "playability")

_PRIVATE_KEY_NAME = "private-key.json"
_README_NAME = "README.md"

_README_TEXT = """\
# Blind Listening Test Package

This directory contains anonymized audio samples for the LMDJ separator
benchmark's blind-listening round (spec §9.3). Do **not** open
`private-key.json` before or during scoring — it maps anonymized IDs back to
the real track/separator/device/repeat identity and must stay private until
the scoring round is over.

## Protocol

- At least **3** independent raters must score every anonymized sample
  (`<anon_id>/`) before a checkpoint's blind-listening score is considered
  valid.
- For each sample, rate all four dimensions on a **1–5** integer scale:
  - `crosstalk` — bleed between separated stems.
  - `transients` — sharpness/preservation of drum and pluck attacks.
  - `low_end` — bass/kick clarity and definition.
  - `playability` — how good the resulting LMDJ pad-rhythm patch feels to
    trigger and play.
- A rating of **1** on any dimension means "severe defect". If **2 or more**
  raters independently give a 1 on the same dimension for the same sample,
  that checkpoint is vetoed regardless of its other scores (see spec §9.3/
  §9.5 — vetoed checkpoints fail the production hard gate and are not offset
  by the composite score).
- Each sample directory contains:
  - `render.wav` — the re-rendered LMDJ loop (post pipeline stages 3-6).
  - `loop.wav` — the original extracted loop, for reference.
  - `stem-1.wav` .. `stem-4.wav` (when included) — the four separated stems
    in a **randomized order** per sample (drums/bass/vocals/other in no
    fixed position), so the file order itself cannot be used to guess the
    model.

## Scoring file format

Submit one JSON file per rater round (or one merged file), matching:

```json
{
  "<anon_id>": {
    "<rater_name>": {
      "crosstalk": 1,
      "transients": 1,
      "low_end": 1,
      "playability": 1
    }
  }
}
```

Every score is an integer 1-5. `<anon_id>` must match a directory name in
this package. `<rater_name>` should be a stable identifier for the same
person across all samples they score (needed to count distinct raters).
"""


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def build_listening_package(run_dir: Path, include_stems: bool = True) -> Path:
    """打包所有 completed 组合为匿名盲听样本；返回 `run_dir/listening-test`。

    每个 completed 组合 -> `listening-test/<uuid4().hex[:12]>/`：
    `pfs/<track>/render_preview.wav` -> `render.wav`，
    `pfs/<track>/loop_preview.wav` -> `loop.wav`，
    可选四条 `separation/stems/{drums,bass,vocals,other}.wav` -> 随机顺序的
    `stem-1..4.wav`（顺序由 `random.sample` 决定并记入 private key，防止
    文件顺序本身泄露模型身份）。预览文件缺失的组合直接跳过（不产出匿名
    目录，也不记入 private key）——不足以打包盲听样本的组合不该混进去。
    """
    run_dir = Path(run_dir)
    results_root = run_dir / "results"
    listening_dir = run_dir / "listening-test"
    listening_dir.mkdir(parents=True, exist_ok=True)

    private_key: dict[str, dict] = {}

    if results_root.is_dir():
        for combo_json_path in sorted(results_root.glob("*/*/*/*/*/combo.json")):
            try:
                combo = json.loads(combo_json_path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(combo, dict) or combo.get("status") != "completed":
                continue

            combo_dir = combo_json_path.parent
            repeat_dir_name = combo_dir.name
            device = combo.get("device") or combo_dir.parent.name
            separator = combo.get("separator") or combo_dir.parent.parent.name
            track = combo.get("track") or combo_dir.parent.parent.parent.name
            repeat = combo.get("repeat")
            if repeat is None:
                repeat = int(repeat_dir_name) if repeat_dir_name.isdigit() else repeat_dir_name

            render_src = combo_dir / "pfs" / track / "render_preview.wav"
            loop_src = combo_dir / "pfs" / track / "loop_preview.wav"
            if not render_src.is_file() or not loop_src.is_file():
                continue

            anon_id = uuid.uuid4().hex[:12]
            dest = listening_dir / anon_id
            dest.mkdir(parents=True, exist_ok=True)

            shutil.copyfile(render_src, dest / "render.wav")
            shutil.copyfile(loop_src, dest / "loop.wav")

            stem_order: list[str] = []
            if include_stems:
                stems_dir = combo_dir / "separation" / "stems"
                available = [s for s in CANONICAL_STEMS if (stems_dir / f"{s}.wav").is_file()]
                stem_order = random.sample(available, len(available))
                for i, stem_name in enumerate(stem_order, start=1):
                    shutil.copyfile(stems_dir / f"{stem_name}.wav", dest / f"stem-{i}.wav")

            private_key[anon_id] = {
                "track": track,
                "separator": separator,
                "device": device,
                "repeat": repeat,
                "stem_order": stem_order,
            }

    _write_json(listening_dir / _PRIVATE_KEY_NAME, private_key)
    (listening_dir / _README_NAME).write_text(_README_TEXT)

    return listening_dir


def load_listening_scores(scores_path: Path, key_path: Path) -> dict:
    """回读评分文件 + private key，按 separator 聚合成 §9.3 分数与否决判定。

    `scores_path`: `{anon_id: {rater_name: {dim: 1..5}}}`。
    `key_path`: `build_listening_package` 写出的 private-key.json。

    返回 `{separator_id: {"score": float, "veto": bool, "n_raters": int,
    "n_combos": int}}`——`score`/`veto` 的形状与 Task 5 `scoring.
    composite_scores`/`hard_gates` 的 `listening` 参数一致（那两个函数只读
    这两个键；`n_raters`/`n_combos` 是这里额外附带的诊断字段）。

    `score` = 该 separator 所有 rater×dim×combo 单项分的算术均值，线性折算
    到 0-10：`(mean - 1) / 4 * 10`（1 分 -> 0，5 分 -> 10）。
    `veto` = 该 separator 名下任一 (combo, dim) 组合被 >= 2 名不同 rater 打
    1 分——逐 combo、逐维度独立判定，一旦命中即整条 separator veto=True。

    private key 里没有对应条目的 anon_id（陈旧/损坏的评分文件）直接忽略，
    不抛异常。
    """
    scores = json.loads(Path(scores_path).read_text())
    key = json.loads(Path(key_path).read_text())

    values_by_sep: dict[str, list[float]] = {}
    combos_by_sep: dict[str, set[str]] = {}
    raters_by_sep: dict[str, set[str]] = {}
    veto_by_sep: dict[str, bool] = {}

    for anon_id, raters in scores.items():
        entry = key.get(anon_id)
        if not isinstance(entry, dict):
            continue
        separator = entry.get("separator")
        if not separator or not isinstance(raters, dict):
            continue

        combos_by_sep.setdefault(separator, set()).add(anon_id)

        for rater_name, dims in raters.items():
            if not isinstance(dims, dict):
                continue
            raters_by_sep.setdefault(separator, set()).add(rater_name)
            for dim in DIMENSIONS:
                if dim in dims:
                    values_by_sep.setdefault(separator, []).append(dims[dim])

        for dim in DIMENSIONS:
            n_ones = sum(
                1 for dims in raters.values()
                if isinstance(dims, dict) and dims.get(dim) == 1
            )
            if n_ones >= 2:
                veto_by_sep[separator] = True

    result: dict[str, dict] = {}
    for separator, values in values_by_sep.items():
        mean = sum(values) / len(values)
        score = (mean - 1) / 4 * 10
        result[separator] = {
            "score": score,
            "veto": veto_by_sep.get(separator, False),
            "n_raters": len(raters_by_sep.get(separator, set())),
            "n_combos": len(combos_by_sep.get(separator, set())),
        }

    return result
