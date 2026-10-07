#!/usr/bin/env python3
"""Advisory macOS output observations around a real audio proof command."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import signal
import subprocess
import sys
from collections.abc import Sequence


def default_output(payload: object) -> dict[str, str]:
    """Select the default audio output, never the input or system-effects route."""
    devices = []

    def visit(value: object) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            if value.get("coreaudio_default_audio_output_device") == "spaudio_yes":
                devices.append(value)
            visit(value.get("_items"))

    if isinstance(payload, dict):
        visit(payload.get("SPAudioDataType"))
    if len(devices) != 1:
        raise ValueError("expected exactly one default audio output")
    device = devices[0]
    name = device.get("_name")
    transport = device.get("coreaudio_device_transport")
    if not isinstance(name, str) or not name or not isinstance(transport, str) or not transport:
        raise ValueError("default audio output name or transport is unavailable")
    result = {"name": name, "transport": transport}
    source = device.get("coreaudio_output_source")
    if isinstance(source, str) and source:
        result["source"] = source
    return result


def observe_output() -> dict[str, object]:
    observation: dict[str, object] = {
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
    }
    try:
        completed = subprocess.run(
            ["/usr/sbin/system_profiler", "SPAudioDataType", "-json"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if completed.returncode != 0:
            raise ValueError(f"system_profiler exited {completed.returncode}")
        observation.update(status="observed", device=default_output(json.loads(completed.stdout)))
    except subprocess.TimeoutExpired:
        observation.update(status="unavailable", reason="system_profiler timed out after 5s")
    except (OSError, ValueError) as error:
        observation.update(status="unavailable", reason=str(error))
    return observation


def warnings(start: dict, end: dict) -> list[str]:
    messages = []
    devices = [item.get("device") for item in (start, end)]
    if any(device and "bluetooth" in device["transport"].lower() for device in devices):
        messages.append("Bluetooth default output observed")
    if all(devices) and devices[0] != devices[1]:
        messages.append("default output changed between start and end")
    if any(item.get("status") == "unavailable" for item in (start, end)):
        messages.append("default output diagnostics unavailable; device stability is unknown")
    return messages


def run_proof(lane: str, command: Sequence[str]) -> int:
    environment = {**os.environ, "LMDJ_AUDIO_OUTPUT_WRAPPED": lane}
    if sys.platform != "darwin":
        os.execvpe(command[0], command, environment)

    context = {"lane": lane, "pid": os.getpid()}

    def emit(phase: str, **fields: object) -> None:
        print("audio-output: " + json.dumps({**context, "phase": phase, **fields}),
              file=sys.stderr, flush=True)

    start = observe_output()
    emit("start", **start)
    handlers = {}
    try:
        # Own a process group so a cancelled wrapper forwards the signal to the
        # proof and its children, including the browser and fixture servers.
        with subprocess.Popen(command, env=environment, start_new_session=True) as child:
            def forward(signum: int, _frame: object) -> None:
                try:
                    os.killpg(child.pid, signum)
                except ProcessLookupError:
                    pass

            for signum in (signal.SIGINT, signal.SIGTERM):
                handlers[signum] = signal.signal(signum, forward)
            code = child.wait()
            code = code if code >= 0 else 128 - code
    except OSError as error:
        print(f"audio proof command could not start: {error}", file=sys.stderr)
        code = 127
    finally:
        for signum, handler in handlers.items():
            signal.signal(signum, handler)

    end = observe_output()
    emit("end", **end)
    messages = warnings(start, end)
    advice = ""
    if messages:
        advice = ("If an audio journey failed, re-run on a wired or built-in device; "
                  "retain the failure trace and inspect it before attributing a cause.")
    emit("result", command_exit_code=code, start=start, end=end,
         warnings=messages, advice=advice)
    return code


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", required=True, choices=("creator", "web_runtime_host"))
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("a proof command after -- is required")
    return run_proof(args.lane, command)


if __name__ == "__main__":
    sys.exit(main())
