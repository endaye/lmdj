#!/usr/bin/env python3
"""Guard real proof output observations and preservation of failed verdicts.

Profiler fixtures exercise reporting only. They neither substitute a browser
output device nor establish physical Bluetooth timing/switch acceptance.
"""

from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts/local-audio-output.py"
spec = importlib.util.spec_from_file_location("local_audio_output", HELPER)
audio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audio)


# Shape captured from system_profiler SPAudioDataType -json on macOS. The
# input and system-effects defaults deliberately differ from the audio output.
PROFILE = {"SPAudioDataType": [{"_name": "coreaudio_device", "_items": [
    {"_name": "Microphone", "coreaudio_default_audio_input_device": "spaudio_yes",
     "coreaudio_device_transport": "coreaudio_device_type_builtin"},
    {"_name": "Effects", "coreaudio_default_audio_system_device": "spaudio_yes",
     "coreaudio_device_transport": "coreaudio_device_type_usb"},
    {"_name": "MacBook Pro Speakers", "coreaudio_default_audio_output_device": "spaudio_yes",
     "coreaudio_device_transport": "coreaudio_device_type_builtin",
     "coreaudio_output_source": "MacBook Pro Speakers"},
]}]}
BUILTIN = {"status": "observed", "observed_at": "2026-10-07T00:00:00.000+00:00",
           "device": audio.default_output(PROFILE)}
BLUETOOTH = {**BUILTIN, "device": {"name": "Headphones",
             "transport": "coreaudio_device_type_bluetooth"}}
UNAVAILABLE = {"status": "unavailable", "observed_at": BUILTIN["observed_at"],
               "reason": "system_profiler timed out after 5s"}


class OutputSelectionTest(unittest.TestCase):
    def test_audio_default_is_selected_instead_of_input_or_system_default(self):
        self.assertEqual(audio.default_output(PROFILE), {
            "name": "MacBook Pro Speakers", "transport": "coreaudio_device_type_builtin",
            "source": "MacBook Pro Speakers",
        })

    def test_ambiguous_default_is_not_reported_as_a_known_device(self):
        profile = copy.deepcopy(PROFILE)
        profile["SPAudioDataType"][0]["_items"].append(profile["SPAudioDataType"][0]["_items"][-1])
        with self.assertRaisesRegex(ValueError, "exactly one"):
            audio.default_output(profile)

    def test_missing_default_is_not_reported_as_stable_builtin(self):
        with self.assertRaisesRegex(ValueError, "exactly one"):
            audio.default_output({"SPAudioDataType": []})

    def test_missing_transport_is_not_reported_as_known(self):
        profile = copy.deepcopy(PROFILE)
        del profile["SPAudioDataType"][0]["_items"][-1]["coreaudio_device_transport"]
        with self.assertRaisesRegex(ValueError, "transport is unavailable"):
            audio.default_output(profile)

    def test_profiler_timeout_remains_visible_and_advisory(self):
        with mock.patch.object(audio.subprocess, "run", side_effect=subprocess.TimeoutExpired("profiler", 5)):
            observation = audio.observe_output()
        self.assertEqual(observation["status"], "unavailable")
        self.assertIn("timed out", observation["reason"])

    def test_invalid_profiler_output_remains_visible_and_advisory(self):
        with mock.patch.object(audio.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "invalid JSON")):
            self.assertEqual(audio.observe_output()["status"], "unavailable")

    def test_profiler_failure_remains_visible_and_advisory(self):
        with mock.patch.object(audio.subprocess, "run", return_value=subprocess.CompletedProcess([], 2, "")):
            self.assertEqual(audio.observe_output()["reason"], "system_profiler exited 2")


class WarningTest(unittest.TestCase):
    def test_stable_builtin_output_has_no_environment_warning(self):
        self.assertEqual(audio.warnings(BUILTIN, BUILTIN), [])

    def test_bluetooth_at_start_is_flagged_after_disconnect(self):
        self.assertIn("Bluetooth default output observed", audio.warnings(BLUETOOTH, BUILTIN))

    def test_bluetooth_at_end_is_flagged(self):
        self.assertIn("Bluetooth default output observed", audio.warnings(BUILTIN, BLUETOOTH))

    def test_changed_wired_device_is_flagged(self):
        usb = {**BUILTIN, "device": {"name": "USB Audio", "transport": "coreaudio_device_type_usb"}}
        self.assertIn("default output changed between start and end", audio.warnings(BUILTIN, usb))

    def test_unavailable_endpoint_does_not_claim_device_stability(self):
        self.assertEqual(audio.warnings(BUILTIN, UNAVAILABLE), [
            "default output diagnostics unavailable; device stability is unknown",
        ])


class ProofExecutionTest(unittest.TestCase):
    def run_proof(self, command, start=BUILTIN, end=BUILTIN):
        output = io.StringIO()
        with mock.patch.object(audio.sys, "platform", "darwin"), \
                mock.patch.object(audio, "observe_output", side_effect=[start, end]), \
                contextlib.redirect_stderr(output):
            code = audio.run_proof("creator", command)
        records = [json.loads(line.removeprefix("audio-output: "))
                   for line in output.getvalue().splitlines() if line.startswith("audio-output: ")]
        return code, records

    def test_observations_surround_the_real_command(self):
        output = io.StringIO()
        observations = []
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "executed"

            def observe():
                observations.append(marker.exists())
                return BUILTIN

            with mock.patch.object(audio.sys, "platform", "darwin"), \
                    mock.patch.object(audio, "observe_output", side_effect=observe), \
                    contextlib.redirect_stderr(output):
                audio.run_proof("creator", [sys.executable, "-c",
                    "from pathlib import Path; import sys; Path(sys.argv[1]).touch()", str(marker)])
        self.assertEqual(observations, [False, True],
            "why: probes must surround execution; remedy: observe before and after the proof")

    def test_failed_proof_retains_exit_status_with_device_rerun_advice(self):
        code, records = self.run_proof([sys.executable, "-c", "raise SystemExit(7)"], BLUETOOTH, BUILTIN)
        self.assertEqual(code, 7, "why: a device warning cannot erase failure; remedy: retain child exit status")
        self.assertEqual([record["phase"] for record in records], ["start", "end", "result"])
        self.assertEqual(records[-1]["command_exit_code"], 7)
        self.assertIn("re-run on a wired or built-in device", records[-1]["advice"])

    def test_passed_proof_retains_bluetooth_warning(self):
        code, records = self.run_proof([sys.executable, "-c", "pass"], BLUETOOTH, BLUETOOTH)
        self.assertEqual((code, records[-1]["warnings"]), (0, ["Bluetooth default output observed"]))

    def test_probe_unavailability_does_not_replace_failed_command_status(self):
        code, records = self.run_proof([sys.executable, "-c", "raise SystemExit(9)"], UNAVAILABLE, UNAVAILABLE)
        self.assertEqual((code, records[-1]["command_exit_code"]), (9, 9))

    def test_signal_exit_is_retained_as_a_shell_exit_status(self):
        code, records = self.run_proof([sys.executable, "-c", "import os,signal; os.kill(os.getpid(),signal.SIGTERM)"])
        self.assertEqual((code, records[-1]["command_exit_code"]), (128 + signal.SIGTERM,) * 2)

    def test_result_has_lane_pid_and_endpoint_timestamps(self):
        _, records = self.run_proof([sys.executable, "-c", "pass"])
        result = records[-1]
        self.assertEqual((result["lane"], result["pid"], result["start"]["observed_at"], result["end"]["observed_at"]),
                         ("creator", os.getpid(), BUILTIN["observed_at"], BUILTIN["observed_at"]))

    def test_other_platform_executes_original_command_without_probe(self):
        with mock.patch.object(audio.sys, "platform", "linux"), \
                mock.patch.object(audio, "observe_output", side_effect=AssertionError("must not probe")), \
                mock.patch.object(audio.os, "execvpe", side_effect=SystemExit(23)) as execute:
            with self.assertRaises(SystemExit):
                audio.run_proof("web_runtime_host", ["bash", "proof.sh"])
        self.assertEqual(execute.call_args.args[:2], ("bash", ["bash", "proof.sh"]))


class ProofEntryTest(unittest.TestCase):
    def check_entry(self, filename, lane):
        # Stop at the wrapper invocation so this test verifies the public shell
        # entry without substituting a browser device or running a Web build.
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "python3"
            executable.write_text(
                "#!" + sys.executable + "\nimport json,os,sys\n"
                "if sys.argv[1] == '-c':\n"
                "    os.execv(sys.executable, [sys.executable, *sys.argv[1:]])\n"
                "print(json.dumps(sys.argv[1:]))\nraise SystemExit(7)\n")
            executable.chmod(0o755)
            environment = {**os.environ, "PATH": directory + os.pathsep + os.environ["PATH"]}
            environment.pop("LMDJ_AUDIO_OUTPUT_WRAPPED", None)
            completed = subprocess.run(["bash", str(ROOT / "scripts" / filename), "proof"],
                env=environment, capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 7)
        self.assertEqual(json.loads(completed.stdout), [str(HELPER), "--lane", lane, "--",
                         "bash", str(ROOT / "scripts" / filename), "proof"],
            "why: public audio proofs must record device endpoints; remedy: invoke the diagnostic wrapper")

    def test_creator_proof_invokes_output_wrapper(self):
        self.check_entry("creator-web.sh", "creator")

    def test_runtime_host_proof_invokes_output_wrapper(self):
        self.check_entry("web-runtime-host.sh", "web_runtime_host")


if __name__ == "__main__":
    unittest.main()
