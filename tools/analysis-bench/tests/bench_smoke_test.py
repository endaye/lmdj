"""Smoke test: run the bench CLI on a fixture and validate the report."""

import json
import subprocess
import sys
import tempfile


def main() -> int:
    bench_binary = sys.argv[1]
    fixture = sys.argv[2]
    with tempfile.TemporaryDirectory() as workspace:
        completed = subprocess.run(
            [
                bench_binary,
                "--workspace", workspace,
                "--fixture", fixture,
                "--capability", "analysis.loudness.v1",
                "--iterations", "3",
            ],
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        report = json.loads(completed.stdout)
        assert report["capability"] == "analysis.loudness.v1"
        assert report["iterations"] == 3
        assert len(report["runs"]) == 1
        run = report["runs"][0]
        assert run["provider_id"] == "local.analysis-bench.loudness"
        assert run["deterministic"] is True
        assert len(run["output_sha256"]) == 64
        assert run["ms_min"] <= run["ms_median"] <= run["ms_max"]
        result = run["result"]
        assert result["contract"] == "lmdj.analysis-bench.loudness.v1"
        assert result["sample_rate"] == 48000
        assert result["peak_dbfs"] <= 0.0
        assert result["rms_dbfs"] <= result["peak_dbfs"]
    print("bench_smoke_test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
