#!/usr/bin/env python3
"""Overflow runners are admitted only while their egress is fast (#2278, #2279).

`scripts/ci/host/runner-network-admission.sh` toggles an overflow runner's
admission label from a measured download. The defects these tests catch:
admitting on one fast sample, keeping a runner admitted through a slow or
failed sample, and changing labels when the Runner API cannot be read. The
script runs for real against stubbed `curl` and `gh`. The PowerShell twin
cannot run here, so its thresholds and probe are pinned to the bash ones.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/ci/host/runner-network-admission.sh"
TWIN = REPO_ROOT / "scripts/ci/host/runner-network-admission.ps1"
FAST = "3000000.000 10485760 206"
SLOW = "26661.000 801871 206"


class RunnerNetworkAdmissionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.state = self.root / "state"
        self.calls = self.root / "gh-calls"
        self.labels = self.root / "labels"
        (self.bin / "curl").write_text(
            '#!/usr/bin/env bash\nprintf %s "$PROBE_OUTPUT"\nexit "${PROBE_EXIT:-0}"\n', encoding="utf-8")
        (self.bin / "gh").write_text(
            "#!/usr/bin/env bash\n"
            'echo "$*" >>"$GH_CALLS"\n'
            'if [ "${GH_FAIL:-0}" = 1 ]; then echo "HTTP 502" >&2; exit 1; fi\n'
            'case "$*" in *"--jq"*) cat "$LABELS_FILE";; esac\n', encoding="utf-8")
        for tool in ("curl", "gh"):
            (self.bin / tool).chmod(0o755)

    def tick(self, probe: str, labels: str, *, probe_exit: int = 0, gh_fail: bool = False) -> list[str]:
        self.labels.write_text(labels, encoding="utf-8")
        self.calls.write_text("", encoding="utf-8")
        system_path = os.environ["PATH"]
        environment = {
            "HOME": str(self.root), "PATH": system_path,
            "LMDJ_ADMISSION_PATH": f"{self.bin}{os.pathsep}{system_path}",
            "LMDJ_ADMISSION_STATE_DIR": str(self.state),
            "PROBE_OUTPUT": probe, "PROBE_EXIT": str(probe_exit),
            "GH_CALLS": str(self.calls), "LABELS_FILE": str(self.labels),
            "GH_FAIL": "1" if gh_fail else "0",
        }
        result = subprocess.run(["bash", str(SCRIPT)], env=environment, check=False,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return [c for c in self.calls.read_text(encoding="utf-8").splitlines() if "-X" in c]

    def test_two_consecutive_fast_samples_admit_the_runner(self) -> None:
        unadmitted = "self-hosted,macOS,ARM64,lmdj-mac-m4"
        self.assertEqual(self.tick(FAST, unadmitted), [], "one fast sample must not admit")
        writes = self.tick(FAST, unadmitted)
        self.assertEqual(len(writes), 1)
        self.assertIn("-X POST repos/endaye/lmdj/actions/runners/37/labels -f labels[]=ci-macos-gates", writes[0])

    def test_a_slow_sample_resets_the_streak(self) -> None:
        unadmitted = "self-hosted,macOS,ARM64,lmdj-mac-m4"
        self.tick(FAST, unadmitted)
        self.tick(SLOW, unadmitted)
        self.assertEqual(self.tick(FAST, unadmitted), [], "the streak must restart after a slow sample")

    def test_one_slow_or_failed_sample_withdraws_an_admitted_runner(self) -> None:
        admitted = "self-hosted,macOS,ARM64,lmdj-mac-m4,ci-macos-gates"
        for case, kwargs in {"slow": {"probe": SLOW}, "timeout": {"probe": SLOW, "probe_exit": 28}}.items():
            with self.subTest(case=case):
                writes = self.tick(labels=admitted, **kwargs)
                self.assertEqual(len(writes), 1)
                self.assertIn("-X DELETE repos/endaye/lmdj/actions/runners/37/labels/ci-macos-gates", writes[0])

    def test_a_fast_admitted_runner_is_left_alone(self) -> None:
        self.assertEqual(self.tick(FAST, "self-hosted,lmdj-mac-m4,ci-macos-gates"), [])

    def test_an_unreadable_runner_api_changes_nothing(self) -> None:
        # One fast sample already counted: a second one would admit if the
        # script carried on with an empty label list after the read failed.
        self.tick(FAST, "self-hosted,macOS,ARM64,lmdj-mac-m4")
        self.assertEqual(self.tick(FAST, "", gh_fail=True), [])
        self.assertIn("gh-error", (self.state / "admission.log").read_text(encoding="utf-8"))

    def test_the_powershell_twin_uses_the_same_probe_and_thresholds(self) -> None:
        bash = SCRIPT.read_text(encoding="utf-8")
        twin = TWIN.read_text(encoding="utf-8")
        for bash_name, twin_name in (("ADMIT_BYTES_PER_SECOND", "AdmitBytesPerSecond"),
                                     ("REVOKE_BYTES_PER_SECOND", "RevokeBytesPerSecond"),
                                     ("ADMIT_STREAK", "AdmitStreak"),
                                     ("PROBE_URL", "ProbeUrl")):
            with self.subTest(setting=bash_name):
                bash_value = re.search(rf"(?m)^{bash_name}=(\S+)$", bash).group(1)
                twin_value = re.search(rf'(?m)^\${twin_name} = "?([^"\s]+)"?$', twin).group(1)
                self.assertEqual(bash_value, twin_value)


if __name__ == "__main__":
    unittest.main()
