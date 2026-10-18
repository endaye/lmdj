#!/usr/bin/env python3
"""Overflow runners are admitted only while their host can take CI (#2278, #2279).

`scripts/ci/host/runner-network-admission.sh` toggles the M4 Pro's admission
label from its host conditions: AC power held for 10 minutes, the owner idle
for 15 minutes, no thermal warning, 30 GB free, and a fast CI egress measured
every 10 minutes. The defects these tests catch: admitting while any
condition fails (on battery, just plugged in, owner active, throttled, disk
low, slow or single-sample link), keeping an admitted runner after a
condition fails, probing the network every run, changing labels when the
Runner API cannot be read, and logging a failed label write as a success.
The script runs for real against stubbed host tools. The PowerShell twin
cannot run here, so its shared thresholds and probe are pinned to these.
"""

from __future__ import annotations

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
ADMITTED = "self-hosted,macOS,ARM64,lmdj-mac-m4,ci-macos-gates"
UNADMITTED = "self-hosted,macOS,ARM64,lmdj-mac-m4"
NOMINAL_THERM = "Note: No thermal warning level has been recorded\nNote: No performance warning level has been recorded\n"


class RunnerNetworkAdmissionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.state = self.root / "state"
        self.calls = self.root / "calls"
        self.now = 1_000_000
        stubs = {
            "curl": 'echo curl >>"$CALLS"\nprintf %s "$PROBE_OUTPUT"\nexit "${PROBE_EXIT:-0}"\n',
            "pmset": 'case "$*" in "-g batt") printf "Now drawing from \'%s\'\\n" "$POWER";;'
                     ' "-g therm") printf "%s" "$THERM";; esac\n',
            "ioreg": 'printf \'    | |   "HIDIdleTime" = %s\\n\' "$IDLE_NS"\n',
            "df": 'printf "Filesystem 1G-blocks Used Available\\n/dev/disk3s5 460 300 %s\\n" "$FREE_GB"\n',
            "gh": 'echo "gh $*" >>"$CALLS"\n'
                  'if [ "${GH_FAIL:-0}" = 1 ]; then echo "HTTP 502" >&2; exit 1; fi\n'
                  'case "$*" in *"-X "*) [ "${GH_WRITE_FAIL:-0}" = 1 ] && exit 1;; esac\n'
                  'case "$*" in *"--jq"*) printf %s "$LABELS";; esac\n',
        }
        for name, body in stubs.items():
            (self.bin / name).write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
            (self.bin / name).chmod(0o755)

    def tick(self, *, labels: str = UNADMITTED, probe: str = FAST, probe_exit: int = 0,
             power: str = "AC Power", idle_s: int = 3600, therm: str = NOMINAL_THERM,
             free_gb: int = 96, gh_fail: bool = False, write_fail: bool = False,
             advance: int = 600) -> tuple[list[str], bool]:
        """Run once, `advance` seconds after the previous run; return (label writes, probed)."""
        self.now += advance
        self.calls.write_text("", encoding="utf-8")
        system_path = os.environ["PATH"]
        environment = {
            "HOME": str(self.root), "PATH": system_path,
            "LMDJ_ADMISSION_PATH": f"{self.bin}{os.pathsep}{system_path}",
            "LMDJ_ADMISSION_STATE_DIR": str(self.state),
            "LMDJ_ADMISSION_NOW": str(self.now),
            "PROBE_OUTPUT": probe, "PROBE_EXIT": str(probe_exit), "POWER": power,
            "IDLE_NS": str(idle_s * 1_000_000_000), "THERM": therm, "FREE_GB": str(free_gb),
            "LABELS": labels, "CALLS": str(self.calls),
            "GH_FAIL": "1" if gh_fail else "0", "GH_WRITE_FAIL": "1" if write_fail else "0",
        }
        result = subprocess.run(["bash", str(SCRIPT)], env=environment, check=False,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls.read_text(encoding="utf-8").splitlines()
        return [c for c in calls if c.startswith("gh") and "-X" in c], "curl" in calls

    def ready(self) -> None:
        """Two fast probes ten minutes apart, on AC for the whole time, owner idle."""
        self.tick()
        self.tick()

    def last_action(self) -> str:
        return (self.state / "admission.log").read_text(encoding="utf-8").splitlines()[-1].rsplit("action=", 1)[1]

    def test_all_conditions_and_two_fast_probes_admit(self) -> None:
        writes, _ = self.tick()
        self.assertEqual(writes, [], "one fast probe must not admit")
        writes, _ = self.tick()
        self.assertEqual(len(writes), 1)
        self.assertIn("gh api -X POST repos/endaye/lmdj/actions/runners/37/labels -f labels[]=ci-macos-gates", writes[0])

    def test_each_failing_condition_blocks_admission(self) -> None:
        cases = {
            "battery": {"power": "Battery Power"},
            "owner active": {"idle_s": 60},
            "thermal": {"therm": "CPU_Speed_Limit \t= 70\n"},
            "disk": {"free_gb": 12},
            "slow link": {"probe": SLOW},
        }
        for case, kwargs in cases.items():
            with self.subTest(case=case):
                self.setUp()
                self.tick()
                writes, _ = self.tick(**kwargs)
                self.assertEqual(writes, [], f"{case} must block admission")

    def test_each_failing_condition_withdraws_an_admitted_runner(self) -> None:
        for case, kwargs in {"battery": {"power": "Battery Power"}, "owner active": {"idle_s": 0},
                             "thermal": {"therm": "Thermal Warning Level = 2\n"}, "disk": {"free_gb": 5},
                             "slow link": {"probe": SLOW}, "failed probe": {"probe": SLOW, "probe_exit": 28}}.items():
            with self.subTest(case=case):
                self.setUp()
                self.ready()
                writes, _ = self.tick(labels=ADMITTED, **kwargs)
                self.assertEqual(len(writes), 1, f"{case} must withdraw")
                self.assertIn("-X DELETE repos/endaye/lmdj/actions/runners/37/labels/ci-macos-gates", writes[0])

    def test_power_must_be_held_for_ten_minutes(self) -> None:
        # The link is already fast, so only the AC hold can block below.
        self.ready()
        self.tick(labels=ADMITTED, power="Battery Power", advance=60)
        writes, probed = self.tick(advance=60)
        self.assertFalse(probed)
        self.assertEqual(writes, [], "just plugged back in must not admit")
        writes, _ = self.tick(advance=300)
        self.assertEqual(writes, [], "five minutes on AC must not admit")
        writes, _ = self.tick(advance=300)
        self.assertEqual(len(writes), 1, "ten minutes on AC with a fast link admits")

    def test_the_network_is_probed_at_most_every_ten_minutes(self) -> None:
        _, probed = self.tick()
        self.assertTrue(probed)
        _, probed = self.tick(advance=60)
        self.assertFalse(probed, "a run one minute later must reuse the last probe")
        _, probed = self.tick(advance=600)
        self.assertTrue(probed)

    def test_an_unreadable_runner_api_changes_nothing(self) -> None:
        self.tick()
        writes, _ = self.tick(gh_fail=True)
        self.assertEqual(writes, [])
        self.assertIn("gh-error", (self.state / "admission.log").read_text(encoding="utf-8"))

    def test_a_failed_label_write_is_logged_and_retried(self) -> None:
        self.ready()
        writes, _ = self.tick(labels=ADMITTED, power="Battery Power", write_fail=True)
        self.assertEqual(len(writes), 1)
        self.assertEqual(self.last_action(), "revoke-failed")
        writes, _ = self.tick(labels=ADMITTED, power="Battery Power", advance=60)
        self.assertEqual(len(writes), 1, "the next run must retry the revoke")
        self.assertEqual(self.last_action(), "revoke")

    def test_the_powershell_twin_shares_the_probe_and_thresholds(self) -> None:
        bash = SCRIPT.read_text(encoding="utf-8")
        twin = TWIN.read_text(encoding="utf-8")
        for bash_name, twin_name in (("ADMIT_BYTES_PER_SECOND", "AdmitBytesPerSecond"),
                                     ("REVOKE_BYTES_PER_SECOND", "RevokeBytesPerSecond"),
                                     ("ADMIT_STREAK", "AdmitStreak"),
                                     ("PROBE_INTERVAL_SECONDS", "ProbeIntervalSeconds"),
                                     ("IDLE_MIN_SECONDS", "IdleMinSeconds"),
                                     ("DISK_MIN_GB", "DiskMinGB"),
                                     ("PROBE_URL", "ProbeUrl")):
            with self.subTest(setting=bash_name):
                bash_value = re.search(rf"(?m)^{bash_name}=(\S+)$", bash).group(1)
                twin_value = re.search(rf'(?m)^\${twin_name} = "?([^"\s]+)"?$', twin).group(1)
                self.assertEqual(bash_value, twin_value)


if __name__ == "__main__":
    unittest.main()
