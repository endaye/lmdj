"""Tests for `benchmark/scoring.py` — weights, normalization, composite
scores, and §9.5 hard gates (spec Task 5).

Pure functions, no I/O: every fixture below is a hand-built in-memory dict
matching the shapes documented in `scoring.py`'s module docstring.
"""
from __future__ import annotations

from lmdj_audio_worker.benchmark.scoring import (
    GATES,
    LOWER_BETTER,
    WEIGHTS,
    composite_scores,
    hard_gates,
    normalize_metric,
)


class TestWeights:
    def test_weights_sum_to_100(self):
        """spec §12.1: 评分权重总和必须是 100（防止权重表被悄悄改坏）。"""
        total = sum(
            weight
            for block in WEIGHTS.values()
            for weight in block.values()
        )
        assert total == 100

    def test_blocks_match_spec_totals(self):
        assert sum(WEIGHTS["reliability"].values()) == 10
        assert sum(WEIGHTS["separation"].values()) == 30
        assert sum(WEIGHTS["patch"].values()) == 40
        assert sum(WEIGHTS["performance"].values()) == 20


class TestNormalizeMetric:
    def test_higher_better_min_max(self):
        values = {"a": 0.0, "b": 5.0, "c": 10.0}
        normalized, degenerate = normalize_metric(values)
        assert degenerate is False
        assert normalized == {"a": 0.0, "b": 0.5, "c": 1.0}

    def test_lower_better_inverts_ranking(self):
        """两个 separator，rtf 更低者应拿到更高的归一化分（不是更低）。"""
        values = {"fast": 0.2, "slow": 0.8}
        normalized, degenerate = normalize_metric(values, lower_better=True)
        assert degenerate is False
        assert normalized["fast"] > normalized["slow"]
        assert normalized == {"fast": 1.0, "slow": 0.0}

    def test_none_values_preserved(self):
        values = {"a": 1.0, "b": None, "c": 3.0}
        normalized, degenerate = normalize_metric(values)
        assert normalized["b"] is None
        assert degenerate is False
        assert normalized["a"] == 0.0
        assert normalized["c"] == 1.0

    def test_single_separator_is_degenerate(self):
        values = {"only": 42.0}
        normalized, degenerate = normalize_metric(values)
        assert degenerate is True
        assert normalized == {"only": 1.0}

    def test_all_equal_values_is_degenerate(self):
        values = {"a": 7.0, "b": 7.0, "c": 7.0}
        normalized, degenerate = normalize_metric(values)
        assert degenerate is True
        assert normalized == {"a": 1.0, "b": 1.0, "c": 1.0}

    def test_all_none_is_not_degenerate_and_stays_none(self):
        values = {"a": None, "b": None}
        normalized, degenerate = normalize_metric(values)
        assert normalized == {"a": None, "b": None}
        assert degenerate is False

    def test_degenerate_with_lower_better_still_all_one(self):
        values = {"a": 5.0, "b": 5.0}
        normalized, degenerate = normalize_metric(values, lower_better=True)
        assert degenerate is True
        assert normalized == {"a": 1.0, "b": 1.0}


def _full_metrics(sdr=10.0, rtf=0.5):
    """一份填满全部叶子指标的 per-separator 指标块（不含 blind_listening）。"""
    return {
        "reliability": {"batch_success": 1.0, "contract_compliance": 1.0,
                        "structural_stability": 1.0},
        "separation": {"sdr": sdr, "si_sdr": 8.0, "consistency_leakage": -20.0},
        "patch": {"completed_passed": 1.0, "validation_score": 0.6,
                  "retry_degrade_structure": 1.0},
        "performance": {"rtf_wall": rtf, "peak_memory": 1e9, "size_load": 100.0},
    }


class TestCompositeScores:
    def test_two_separators_full_metrics_scored_out_of_90_without_listening(self):
        per_separator_metrics = {
            "sep-a": _full_metrics(sdr=10.0, rtf=0.5),
            "sep-b": _full_metrics(sdr=5.0, rtf=1.0),
        }

        result = composite_scores(per_separator_metrics, listening=None)

        # blind_listening (weight 10) is missing for both -> 100 - 10 = 90.
        assert result["sep-a"]["scored_out_of"] == 90
        assert result["sep-b"]["scored_out_of"] == 90
        assert (result["sep-a"]["blocks"]["patch"]["submetrics"]["blind_listening"]["score"]
                == "missing")
        assert (result["sep-b"]["blocks"]["patch"]["submetrics"]["blind_listening"]["score"]
                == "missing")
        # blind_listening's weight must not silently count toward achievable max.
        assert result["sep-a"]["blocks"]["patch"]["max"] == 30  # 15+10+5, no +10
        # missing is not zero-filled: it is excluded, not scored as 0.
        assert result["sep-a"]["blocks"]["patch"]["submetrics"]["blind_listening"]["normalized"] is None

    def test_blind_listening_present_included_in_total(self):
        per_separator_metrics = {
            "sep-a": _full_metrics(),
            "sep-b": _full_metrics(),
        }
        listening = {"sep-a": {"score": 9.0, "veto": False},
                     "sep-b": {"score": 3.0, "veto": False}}

        result = composite_scores(per_separator_metrics, listening=listening)

        assert result["sep-a"]["scored_out_of"] == 100
        assert result["sep-b"]["scored_out_of"] == 100
        bl_a = result["sep-a"]["blocks"]["patch"]["submetrics"]["blind_listening"]
        bl_b = result["sep-b"]["blocks"]["patch"]["submetrics"]["blind_listening"]
        assert bl_a["score"] != "missing"
        assert bl_a["normalized"] == 1.0   # sep-a has the higher raw listening score
        assert bl_b["normalized"] == 0.0

    def test_partial_listening_missing_only_for_one_separator(self):
        """一个 separator 缺盲听、另一个有 —— 缺的那个 scored_out_of 降到 90，
        另一个仍是 100，不是全体一起降级。"""
        per_separator_metrics = {
            "sep-a": _full_metrics(),
            "sep-b": _full_metrics(),
        }
        listening = {"sep-a": {"score": 8.0, "veto": False}}

        result = composite_scores(per_separator_metrics, listening=listening)

        assert result["sep-a"]["scored_out_of"] == 100
        assert result["sep-b"]["scored_out_of"] == 90
        assert (result["sep-b"]["blocks"]["patch"]["submetrics"]["blind_listening"]["score"]
                == "missing")

    def test_missing_submetric_excludes_weight_generally(self):
        """None 不仅限于盲听：任意子指标缺失都要从可得总分里排除该权重。"""
        metrics_a = _full_metrics()
        metrics_a["performance"]["size_load"] = None
        per_separator_metrics = {
            "sep-a": metrics_a,
            "sep-b": _full_metrics(),
        }
        listening = {"sep-a": {"score": 5.0, "veto": False},
                     "sep-b": {"score": 5.0, "veto": False}}

        result = composite_scores(per_separator_metrics, listening=listening)

        assert result["sep-a"]["scored_out_of"] == 97  # 100 - size_load(3)
        assert result["sep-b"]["scored_out_of"] == 100
        assert (result["sep-a"]["blocks"]["performance"]["submetrics"]["size_load"]["score"]
                == "missing")

    def test_lower_better_metric_rewards_lower_raw_value(self):
        """rtf_wall 更低的 separator 应该拿到更高的 performance 分数。"""
        per_separator_metrics = {
            "fast": _full_metrics(rtf=0.2),
            "slow": _full_metrics(rtf=0.8),
        }

        result = composite_scores(per_separator_metrics, listening=None)

        fast_rtf = result["fast"]["blocks"]["performance"]["submetrics"]["rtf_wall"]
        slow_rtf = result["slow"]["blocks"]["performance"]["submetrics"]["rtf_wall"]
        assert fast_rtf["score"] > slow_rtf["score"]
        assert fast_rtf["normalized"] == 1.0
        assert slow_rtf["normalized"] == 0.0

    def test_degenerate_single_separator_gets_full_marks_and_flag(self):
        per_separator_metrics = {"only": _full_metrics()}
        listening = {"only": {"score": 5.0, "veto": False}}

        result = composite_scores(per_separator_metrics, listening=listening)

        assert result["only"]["total"] == 100
        assert result["only"]["scored_out_of"] == 100
        sdr = result["only"]["blocks"]["separation"]["submetrics"]["sdr"]
        assert sdr["normalized"] == 1.0
        assert sdr["degenerate"] is True


def _gate_inputs(invalid_stems_failures=0, total_combos=10, completed_combos=10,
                  patch_passed_rate=0.9, peak_rss_bytes_max=1_000_000,
                  peak_device_memory_bytes_max=None):
    return {
        "invalid_stems_failures": invalid_stems_failures,
        "total_combos": total_combos,
        "completed_combos": completed_combos,
        "patch_passed_rate": patch_passed_rate,
        "peak_rss_bytes_max": peak_rss_bytes_max,
        "peak_device_memory_bytes_max": peak_device_memory_bytes_max,
    }


class TestHardGatesAllPass:
    def test_all_gates_pass_when_everything_clean(self):
        per_separator = {
            "htdemucs": _gate_inputs(patch_passed_rate=0.9),
            "sep-b": _gate_inputs(patch_passed_rate=0.88),
        }
        attestations = {
            "macos_mps_smoke": {"htdemucs": True, "sep-b": True},
            "linux_cpu_smoke": {"htdemucs": True, "sep-b": True},
            "linux_peak_rss_bytes": {"htdemucs": 1_000_000, "sep-b": 1_000_000},
            "mac_physical_memory_bytes": 32 * 1024 ** 3,
        }
        listening = {"htdemucs": {"score": 8.0, "veto": False},
                     "sep-b": {"score": 8.0, "veto": False}}

        result = hard_gates(per_separator, attestations, listening, baseline_id="htdemucs")

        for gate in GATES:
            assert result["htdemucs"][gate] == "pass"
            assert result["sep-b"][gate] == "pass"
        assert result["htdemucs"]["gate_blocked"] is False
        assert result["sep-b"]["gate_blocked"] is False
        assert result["any_gate_failed"] is False


class TestHardGatesContractAndSuccess:
    def test_invalid_stems_failures_fails_contract_compliance(self):
        per_separator = {"sep-a": _gate_inputs(invalid_stems_failures=2)}
        result = hard_gates(per_separator, attestations=None, listening=None)
        assert result["sep-a"]["contract_compliance"] == "fail"
        assert result["sep-a"]["gate_blocked"] is True
        assert result["any_gate_failed"] is True

    def test_missing_invalid_stems_failures_is_unknown(self):
        inputs = _gate_inputs()
        del inputs["invalid_stems_failures"]
        per_separator = {"sep-a": inputs}
        result = hard_gates(per_separator, attestations=None, listening=None)
        assert result["sep-a"]["contract_compliance"] == "unknown"

    def test_success_rate_below_95_fails(self):
        per_separator = {"sep-a": _gate_inputs(total_combos=10, completed_combos=9)}
        result = hard_gates(per_separator, attestations=None, listening=None)
        assert result["sep-a"]["success_rate"] == "fail"

    def test_success_rate_at_95_passes(self):
        per_separator = {"sep-a": _gate_inputs(total_combos=20, completed_combos=19)}
        result = hard_gates(per_separator, attestations=None, listening=None)
        assert result["sep-a"]["success_rate"] == "pass"

    def test_success_rate_unknown_when_total_combos_zero(self):
        per_separator = {"sep-a": _gate_inputs(total_combos=0, completed_combos=0)}
        result = hard_gates(per_separator, attestations=None, listening=None)
        assert result["sep-a"]["success_rate"] == "unknown"


class TestHardGatesPassedRateVsBaseline:
    def test_below_baseline_by_more_than_5pp_fails(self):
        per_separator = {
            "htdemucs": _gate_inputs(patch_passed_rate=0.90),
            "sep-b": _gate_inputs(patch_passed_rate=0.80),
        }
        result = hard_gates(per_separator, attestations=None, listening=None,
                             baseline_id="htdemucs")
        assert result["sep-b"]["passed_rate_vs_baseline"] == "fail"

    def test_within_5pp_of_baseline_passes(self):
        per_separator = {
            "htdemucs": _gate_inputs(patch_passed_rate=0.90),
            "sep-b": _gate_inputs(patch_passed_rate=0.86),
        }
        result = hard_gates(per_separator, attestations=None, listening=None,
                             baseline_id="htdemucs")
        assert result["sep-b"]["passed_rate_vs_baseline"] == "pass"

    def test_missing_baseline_is_unknown(self):
        per_separator = {"sep-b": _gate_inputs(patch_passed_rate=0.86)}
        result = hard_gates(per_separator, attestations=None, listening=None,
                             baseline_id="htdemucs")
        assert result["sep-b"]["passed_rate_vs_baseline"] == "unknown"


class TestHardGatesSmokeAttestations:
    def test_missing_attestations_is_unknown(self):
        per_separator = {"sep-a": _gate_inputs()}
        result = hard_gates(per_separator, attestations=None, listening=None)
        assert result["sep-a"]["macos_mps_smoke"] == "unknown"
        assert result["sep-a"]["linux_cpu_smoke"] == "unknown"

    def test_false_smoke_fails(self):
        per_separator = {"sep-a": _gate_inputs()}
        attestations = {"macos_mps_smoke": {"sep-a": False},
                         "linux_cpu_smoke": {"sep-a": True}}
        result = hard_gates(per_separator, attestations, listening=None)
        assert result["sep-a"]["macos_mps_smoke"] == "fail"
        assert result["sep-a"]["linux_cpu_smoke"] == "pass"
        assert result["sep-a"]["gate_blocked"] is True


class TestHardGatesMemoryLimits:
    def test_linux_rss_over_12gib_fails(self):
        per_separator = {"sep-a": _gate_inputs(peak_rss_bytes_max=13 * 1024 ** 3)}
        result = hard_gates(per_separator, attestations=None, listening=None)
        assert result["sep-a"]["linux_rss_limit"] == "fail"

    def test_linux_rss_under_12gib_passes(self):
        per_separator = {"sep-a": _gate_inputs(peak_rss_bytes_max=11 * 1024 ** 3)}
        result = hard_gates(per_separator, attestations=None, listening=None)
        assert result["sep-a"]["linux_rss_limit"] == "pass"

    def test_linux_rss_from_attestations_overrides_per_separator(self):
        per_separator = {"sep-a": _gate_inputs(peak_rss_bytes_max=1_000)}
        attestations = {"linux_peak_rss_bytes": {"sep-a": 13 * 1024 ** 3}}
        result = hard_gates(per_separator, attestations, listening=None)
        assert result["sep-a"]["linux_rss_limit"] == "fail"

    def test_mac_memory_limit_missing_physical_bytes_is_unknown(self):
        per_separator = {"sep-a": _gate_inputs()}
        result = hard_gates(per_separator, attestations=None, listening=None)
        assert result["sep-a"]["mac_memory_limit"] == "unknown"

    def test_mac_memory_limit_over_75_percent_fails(self):
        physical = 16 * 1024 ** 3
        per_separator = {
            "sep-a": _gate_inputs(peak_rss_bytes_max=int(physical * 0.8),
                                   peak_device_memory_bytes_max=None),
        }
        attestations = {"mac_physical_memory_bytes": physical}
        result = hard_gates(per_separator, attestations, listening=None)
        assert result["sep-a"]["mac_memory_limit"] == "fail"

    def test_mac_memory_limit_uses_higher_of_rss_and_device_memory(self):
        physical = 16 * 1024 ** 3
        per_separator = {
            "sep-a": _gate_inputs(peak_rss_bytes_max=int(physical * 0.1),
                                   peak_device_memory_bytes_max=int(physical * 0.8)),
        }
        attestations = {"mac_physical_memory_bytes": physical}
        result = hard_gates(per_separator, attestations, listening=None)
        assert result["sep-a"]["mac_memory_limit"] == "fail"

    def test_mac_memory_limit_under_75_percent_passes(self):
        physical = 16 * 1024 ** 3
        per_separator = {
            "sep-a": _gate_inputs(peak_rss_bytes_max=int(physical * 0.5),
                                   peak_device_memory_bytes_max=None),
        }
        attestations = {"mac_physical_memory_bytes": physical}
        result = hard_gates(per_separator, attestations, listening=None)
        assert result["sep-a"]["mac_memory_limit"] == "pass"


class TestHardGatesBlindVeto:
    def test_veto_true_fails_regardless_of_score(self):
        per_separator = {"sep-a": _gate_inputs()}
        listening = {"sep-a": {"score": 9.5, "veto": True}}
        result = hard_gates(per_separator, attestations=None, listening=listening)
        assert result["sep-a"]["blind_veto"] == "fail"
        assert result["sep-a"]["gate_blocked"] is True

    def test_veto_false_passes(self):
        per_separator = {"sep-a": _gate_inputs()}
        listening = {"sep-a": {"score": 2.0, "veto": False}}
        result = hard_gates(per_separator, attestations=None, listening=listening)
        assert result["sep-a"]["blind_veto"] == "pass"

    def test_missing_listening_is_unknown(self):
        per_separator = {"sep-a": _gate_inputs()}
        result = hard_gates(per_separator, attestations=None, listening=None)
        assert result["sep-a"]["blind_veto"] == "unknown"


class TestGateBlockedIgnoresCompositeScore:
    def test_gate_fail_blocks_regardless_of_top_composite_score(self):
        """spec §12.1 点名用例：一个 separator 综合分远高于另一个，但触发了硬门槛，
        仍然必须 gate_blocked=True —— 硬门槛不可被总分绕过。"""
        per_separator_metrics = {
            "top-scorer": _full_metrics(sdr=20.0, rtf=0.1),   # dominates every submetric
            "baseline": _full_metrics(sdr=1.0, rtf=2.0),
        }
        listening = {"top-scorer": {"score": 10.0, "veto": False},
                     "baseline": {"score": 10.0, "veto": False}}

        scores = composite_scores(per_separator_metrics, listening=listening)
        assert scores["top-scorer"]["total"] > scores["baseline"]["total"]

        # top-scorer fails contract compliance despite the highest composite score.
        gate_inputs = {
            "top-scorer": _gate_inputs(invalid_stems_failures=3),
            "baseline": _gate_inputs(invalid_stems_failures=0),
        }
        gates = hard_gates(gate_inputs, attestations=None, listening=listening,
                            baseline_id="baseline")

        assert gates["top-scorer"]["gate_blocked"] is True
        assert gates["baseline"]["gate_blocked"] is False
