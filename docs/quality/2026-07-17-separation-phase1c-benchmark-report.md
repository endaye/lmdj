# Task 6: Benchmark Report Generation (Phase 1C-b)

## Summary

Task 6 implements benchmark aggregation, summary assembly, and CSV reporting for the separation phase 1C (metrics) deliverable. The module aggregates per-combo raw results across runs and devices, computes scoring inputs, enforces hard gates, and emits `summary.json` + `summary.csv` for operational oversight.

## Test Coverage

**Total: 22 tests (11/6/5)**

- **TestCollectRunAggregation** (11 tests): fixture creation, performance/leakage/RTF/patch metrics aggregation, structural stability computation, leak_worst_db reduction
- **TestCollectRunObjective** (6 tests): objective computation flow, manifest/mix/error handling, downgrade-to-None on exception
- **TestBuildSummary** (5 tests): cross-run merging, CSV round-trip, path sanitization, linux_rss gate carry-forward

## Key Implementation Details

### Aggregation Strategy

- **SDR / SI-SDR**: mean of per-combo means from `has_gt=True` combos only
- **consistency_leakage**: mean of `mixture_consistency` (present with or without GT)
- **leak_worst_db** (new): per-combo max of stem leakage values, then mean over GT combos; reported for visibility, not fed to scoring (already simplified via consistency_leakage)
- **RTF**: mean of `inference_seconds / duration_seconds` where both are present and positive
- **peak_memory**: max of (max rss, max device mem) per combo, then max across combos
- **linux_rss_limit carry-forward**: only combos from Linux platform runs with device="cpu"

### Column Safety

CSV columns are now validated with exact set equality (not subset) in `test_csv_rows_columns_and_roundtrip` to prevent silent column drift.

## Fix Round 1

**Date:** 2026-07-16

**Issue:** leak_worst_db column omitted from summary.csv aggregation.

**Changes:**
1. Added `leak_worst_db_mean` to `_aggregate` objective reduction (line 359-369)
2. Added `leak_worst_db` column to `_build_csv_rows` (line 545)
3. Strengthened test assertion: replaced `issubset` with exact set equality (test_csv_rows_columns_and_roundtrip)
4. Added aggregation test: `test_leak_worst_db_two_gt_combos_aggregates_to_mean_of_max` verifying per-combo max → mean reduction logic
5. Updated test count from 21 to 22 (added one aggregation test)

**Test Result:** 275/275 pass in full suite (test/benchmark/test_report.py: 22/22 pass).
