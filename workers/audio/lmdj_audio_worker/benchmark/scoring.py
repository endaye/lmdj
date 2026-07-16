"""评分核心：§9 权重、run 内归一化、§9.5 生产晋级硬门槛（spec Task 5）。

本模块纯函数、无 I/O——combo 级别的指标聚合（多 combo -> 每 separator 一个
数）在 Task 6 的 `report.py` 里完成；这里只消费"已经 reduce 到单一可比数值"
的结果。这样 `composite_scores`/`hard_gates` 可以脱离真实 benchmark 产物被
单独测试，`report.py` 接线时只需要把 reduce 后的字典喂进来。

## 输入形状

`composite_scores(per_separator_metrics, listening)`：

- `per_separator_metrics`: `{separator_id: {block: {submetric: value|None}}}`。
  `block`/`submetric` 的键名与 `WEIGHTS` 完全一致 ——
  `reliability.{batch_success,contract_compliance,structural_stability}`、
  `separation.{sdr,si_sdr,consistency_leakage}`、
  `patch.{completed_passed,validation_score,retry_degrade_structure}`
  （**不含** `blind_listening`——它单独从 `listening` 参数读取）、
  `performance.{rtf_wall,peak_memory,size_load}`。每个值已经是"该 separator
  在该子指标上的单一可比数字"（例如 sdr 已经是四轨+多 track 的某种聚合均值），
  或 `None`（该 separator 这个子指标缺测）。
- `listening`: `None`（整体未做盲听）或
  `{separator_id: {"score": float|None, "veto": bool}}`。`score` 是盲听协议
  （spec §9.3）线性折算到 0-10 的结果；`veto` 是否命中"任一维度 ≥2 名评测者
  打 1 分"的否决规则（供 `hard_gates` 读取，不参与 composite 分数计算本身，
  但 veto 命中的 checkpoint 通常 score 也很低——两者独立记录）。缺失某个
  separator 的 entry，或 entry 里没有 "score" 键，等价于该 separator 的
  blind_listening 为 `None`。

`hard_gates(per_separator, attestations, listening, baseline_id)`：

- `per_separator`: `{separator_id: {invalid_stems_failures: int|None,
  total_combos: int|None, completed_combos: int|None,
  patch_passed_rate: float|None（0-1 分数，不是百分比）,
  peak_rss_bytes_max: int|None, peak_device_memory_bytes_max: int|None}}`。
  这是 run 级别的原始统计，不是 `composite_scores` 的输入（两者字段不同、
  互不依赖）。
- `attestations`: `None`（尚未跑双平台 smoke / 未采集内存 attestation）或
  `{"macos_mps_smoke": {separator_id: bool}, "linux_cpu_smoke":
  {separator_id: bool}, "linux_peak_rss_bytes": {separator_id: int}
  （可选；缺省时退回 per_separator 里的 peak_rss_bytes_max）,
  "mac_physical_memory_bytes": int（目标 Mac 机器物理内存，run 级别常量，
  不分 separator）}`。
- `listening`: 与 `composite_scores` 同一份输入，这里只读 `veto` 字段。

## 输出形状

`composite_scores` 返回 `{separator_id: {"blocks": {block_name:
{"score": float, "max": float, "submetrics": {submetric_name: {"raw":
value|None, "normalized": float|None, "weight": int, "score":
float|"missing", "degenerate": bool}}}}, "total": float, "scored_out_of":
float}}`。`"missing"`（字符串字面量）标记该子指标因为 raw 值缺失被排除在
总分与可得满分之外——不是 0 分，是"这条不计分"（盲听整体缺失只是这条通用
规则命中 10 分权重的特例，其余任何子指标缺失走同一条路径）。

`hard_gates` 返回 `{separator_id: {gate_name: "pass"|"fail"|"unknown", ...,
"gate_blocked": bool}, "any_gate_failed": bool}`。`gate_blocked`（per
separator）与顶层 `any_gate_failed`（整个 run）都只由 `"fail"` 触发——
`"unknown"` 既不算通过也不算失败，不会阻断晋级（保守；调用方如需更严格的
"未知视为失败"策略，应在 report.py 里另行处理，本模块只如实转述）。
"""
from __future__ import annotations

WEIGHTS: dict[str, dict[str, int]] = {
    "reliability": {"batch_success": 6, "contract_compliance": 2, "structural_stability": 2},
    "separation": {"sdr": 15, "si_sdr": 10, "consistency_leakage": 5},
    "patch": {"completed_passed": 15, "validation_score": 10, "retry_degrade_structure": 5,
              "blind_listening": 10},
    "performance": {"rtf_wall": 12, "peak_memory": 5, "size_load": 3},
}

# 数值越低越好的子指标（其余默认越高越好）：rtf/内存/体积/一致性-泄漏 dB
# 都是"误差/成本"类指标。见 metrics.py 的 mixture_consistency/leakage：值是
# 残差能量比的 dB，越接近 0（或越负）表示误差越小。
LOWER_BETTER: frozenset[str] = frozenset({
    "rtf_wall", "peak_memory", "size_load", "consistency_leakage",
})

GATES: tuple[str, ...] = (
    "contract_compliance",
    "success_rate",
    "passed_rate_vs_baseline",
    "macos_mps_smoke",
    "linux_cpu_smoke",
    "linux_rss_limit",
    "mac_memory_limit",
    "blind_veto",
)

_SUCCESS_RATE_THRESHOLD = 0.95
_PASSED_RATE_TOLERANCE_PP = 0.05
_LINUX_RSS_LIMIT_BYTES = 12 * 1024 ** 3
_MAC_MEMORY_LIMIT_FRACTION = 0.75


def normalize_metric(
    values: dict[str, float | None], lower_better: bool = False,
) -> tuple[dict[str, float | None], bool]:
    """跨 separator min-max 归一化到 [0, 1]。

    `None` 原样保留（缺测，不参与 min/max 计算，也不被赋值）。
    非 `None` 值里只有 0 或 1 个不同取值（单一 separator，或全部相等）时，
    没有可比的跨度——退化为全部记 1.0（满分，不惩罚），并返回
    `degenerate=True` 供调用方标注。`lower_better=True` 时把归一化方向
    反过来（原始值越低，归一化分越高）；退化情形下方向翻转没有意义，
    同样统一给 1.0。
    """
    present = {k: v for k, v in values.items() if v is not None}
    if not present:
        return {k: None for k in values}, False

    distinct = set(present.values())
    if len(distinct) <= 1:
        return {k: (1.0 if v is not None else None) for k, v in values.items()}, True

    lo = min(present.values())
    hi = max(present.values())
    span = hi - lo

    out: dict[str, float | None] = {}
    for k, v in values.items():
        if v is None:
            out[k] = None
            continue
        fraction = (v - lo) / span
        out[k] = (1.0 - fraction) if lower_better else fraction
    return out, False


def composite_scores(per_separator_metrics: dict, listening: dict | None) -> dict:
    """§9 分项得分 + 总分；见模块 docstring 的输入/输出形状说明。"""
    separator_ids = list(per_separator_metrics.keys())
    listening = listening or {}

    result: dict = {
        sep: {"blocks": {}, "total": 0.0, "scored_out_of": 0.0}
        for sep in separator_ids
    }

    for block_name, submetrics in WEIGHTS.items():
        for sep in separator_ids:
            result[sep]["blocks"][block_name] = {
                "score": 0.0, "max": 0.0, "submetrics": {},
            }

        for submetric_name, weight in submetrics.items():
            if submetric_name == "blind_listening":
                raw = {
                    sep: (listening.get(sep) or {}).get("score")
                    for sep in separator_ids
                }
            else:
                raw = {
                    sep: (per_separator_metrics.get(sep) or {}).get(block_name, {}).get(submetric_name)
                    for sep in separator_ids
                }

            normalized, degenerate = normalize_metric(
                raw, lower_better=submetric_name in LOWER_BETTER)

            for sep in separator_ids:
                block = result[sep]["blocks"][block_name]
                norm = normalized[sep]
                if norm is None:
                    block["submetrics"][submetric_name] = {
                        "raw": raw[sep], "normalized": None, "weight": weight,
                        "score": "missing", "degenerate": degenerate,
                    }
                    continue
                score = norm * weight
                block["submetrics"][submetric_name] = {
                    "raw": raw[sep], "normalized": norm, "weight": weight,
                    "score": score, "degenerate": degenerate,
                }
                block["score"] += score
                block["max"] += weight

    for sep in separator_ids:
        blocks = result[sep]["blocks"]
        result[sep]["total"] = sum(b["score"] for b in blocks.values())
        result[sep]["scored_out_of"] = sum(b["max"] for b in blocks.values())

    return result


def _gate_contract_compliance(inputs: dict) -> str:
    failures = inputs.get("invalid_stems_failures")
    if failures is None:
        return "unknown"
    return "pass" if failures == 0 else "fail"


def _gate_success_rate(inputs: dict) -> str:
    total = inputs.get("total_combos")
    completed = inputs.get("completed_combos")
    if not total:  # None 或 0：无法计算比率
        return "unknown"
    if completed is None:
        return "unknown"
    rate = completed / total
    return "pass" if rate >= _SUCCESS_RATE_THRESHOLD else "fail"


def _gate_passed_rate_vs_baseline(inputs: dict, per_separator: dict, baseline_id: str) -> str:
    rate = inputs.get("patch_passed_rate")
    baseline_inputs = per_separator.get(baseline_id)
    baseline_rate = baseline_inputs.get("patch_passed_rate") if baseline_inputs else None
    if rate is None or baseline_rate is None:
        return "unknown"
    return "pass" if rate >= baseline_rate - _PASSED_RATE_TOLERANCE_PP else "fail"


def _gate_bool_attestation(sep_id: str, attestations: dict | None, key: str) -> str:
    if not attestations:
        return "unknown"
    per_sep = attestations.get(key)
    if not isinstance(per_sep, dict):
        return "unknown"
    value = per_sep.get(sep_id)
    if value is None:
        return "unknown"
    return "pass" if value else "fail"


def _gate_linux_rss_limit(sep_id: str, inputs: dict, attestations: dict | None) -> str:
    value = None
    if attestations:
        per_sep = attestations.get("linux_peak_rss_bytes")
        if isinstance(per_sep, dict):
            value = per_sep.get(sep_id)
    if value is None:
        value = inputs.get("peak_rss_bytes_max")
    if value is None:
        return "unknown"
    return "pass" if value <= _LINUX_RSS_LIMIT_BYTES else "fail"


def _gate_mac_memory_limit(inputs: dict, attestations: dict | None) -> str:
    if not attestations:
        return "unknown"
    physical = attestations.get("mac_physical_memory_bytes")
    if physical is None:
        return "unknown"
    candidates = [
        v for v in (inputs.get("peak_rss_bytes_max"), inputs.get("peak_device_memory_bytes_max"))
        if v is not None
    ]
    if not candidates:
        return "unknown"
    peak = max(candidates)
    limit = physical * _MAC_MEMORY_LIMIT_FRACTION
    return "pass" if peak <= limit else "fail"


def _gate_blind_veto(sep_id: str, listening: dict | None) -> str:
    if not listening:
        return "unknown"
    entry = listening.get(sep_id)
    if not isinstance(entry, dict) or "veto" not in entry:
        return "unknown"
    return "fail" if entry["veto"] else "pass"


def hard_gates(
    per_separator: dict,
    attestations: dict | None,
    listening: dict | None,
    baseline_id: str = "htdemucs",
) -> dict:
    """§9.5 生产晋级硬门槛；见模块 docstring 的输入/输出形状说明。

    任何一个 gate 为 "fail" 都会把该 separator 标 `gate_blocked=True`，
    与 composite 总分完全无关——即使总分最高的 separator 也会被 block。
    """
    result: dict = {}
    any_gate_failed = False

    for sep_id, raw_inputs in per_separator.items():
        inputs = raw_inputs or {}
        gates = {
            "contract_compliance": _gate_contract_compliance(inputs),
            "success_rate": _gate_success_rate(inputs),
            "passed_rate_vs_baseline": _gate_passed_rate_vs_baseline(
                inputs, per_separator, baseline_id),
            "macos_mps_smoke": _gate_bool_attestation(sep_id, attestations, "macos_mps_smoke"),
            "linux_cpu_smoke": _gate_bool_attestation(sep_id, attestations, "linux_cpu_smoke"),
            "linux_rss_limit": _gate_linux_rss_limit(sep_id, inputs, attestations),
            "mac_memory_limit": _gate_mac_memory_limit(inputs, attestations),
            "blind_veto": _gate_blind_veto(sep_id, listening),
        }
        gate_blocked = any(status == "fail" for status in gates.values())
        if gate_blocked:
            any_gate_failed = True
        result[sep_id] = {**gates, "gate_blocked": gate_blocked}

    result["any_gate_failed"] = any_gate_failed
    return result
