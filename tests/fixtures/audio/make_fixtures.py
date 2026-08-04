import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import wave


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIRECTORY = Path(
    os.environ.get(
        "LMDJ_AUDIO_FIXTURE_OUTPUT_DIRECTORY",
        REPOSITORY_ROOT / "tests/fixtures/audio",
    )
).resolve()
REALTIME_CAPACITY_HEADER = Path(
    os.environ.get(
        "LMDJ_REALTIME_CAPACITY_HEADER",
        REPOSITORY_ROOT
        / "packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp",
    )
).resolve()
SAMPLE_RATE = 48_000
WEB_RUNTIME_HOST_FRAME_COUNT = 240
WEB_RUNTIME_HOST_TRIGGER_COUNT = 500
WEB_RUNTIME_HOST_TRIGGER_PACING_MS = 2


def pcm16(value: float) -> int:
    return max(-32_768, min(32_767, round(value)))


def kick_samples() -> list[int]:
    return [
        pcm16(
            30_000
            * (1.0 - frame / 4_800)
            * math.sin(2.0 * math.pi * 60.0 * frame / SAMPLE_RATE)
        )
        for frame in range(4_800)
    ]


def snare_samples() -> list[int]:
    state = 0x6D2B79F5
    samples = []
    for frame in range(2_400):
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= state >> 17
        state ^= (state << 5) & 0xFFFFFFFF
        state &= 0xFFFFFFFF
        noise = (state & 0xFFFF) - 32_768
        samples.append(pcm16(noise * (1.0 - frame / 2_400)))
    return samples


def web_runtime_host_samples() -> list[int]:
    return [
        pcm16(
            12_000
            * (1.0 - frame / WEB_RUNTIME_HOST_FRAME_COUNT)
            * math.sin(2.0 * math.pi * 440.0 * frame / SAMPLE_RATE)
        )
        for frame in range(WEB_RUNTIME_HOST_FRAME_COUNT)
    ]


def wav_bytes(channels: int, samples: list[int]) -> bytes:
    frame_bytes = struct.pack("<" + "h" * len(samples), *samples)
    data_size = len(frame_bytes)
    return (
        b"RIFF"
        + struct.pack("<I", 36 + data_size)
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, channels, SAMPLE_RATE,
                      SAMPLE_RATE * channels * 2, channels * 2, 16)
        + b"data"
        + struct.pack("<I", data_size)
        + frame_bytes
    )


def write_fixture(name: str, contents: bytes) -> str:
    path = FIXTURE_DIRECTORY / name
    expected_hash = hashlib.sha256(contents).hexdigest()
    try:
        with open(path, "rb") as existing:
            existing_hash = hashlib.sha256(existing.read()).hexdigest()
    except FileNotFoundError:
        existing_hash = None
    if existing_hash is not None and existing_hash != expected_hash:
        raise SystemExit(
            f"fixture hash changed unexpectedly: {path.relative_to(REPOSITORY_ROOT)}"
        )
    with open(path, "wb") as output:
        output.write(contents)
    with wave.open(str(path), "rb") as fixture:
        if (fixture.getsampwidth(), fixture.getframerate()) != (2, SAMPLE_RATE):
            raise SystemExit(
                f"fixture encoding is invalid: {path.relative_to(REPOSITORY_ROOT)}"
            )
    return expected_hash


def realtime_capacities() -> dict[str, int]:
    compiler_name = os.environ.get("LMDJ_NATIVE_CXX", "c++")
    compiler = shutil.which(compiler_name)
    if compiler is None:
        raise SystemExit(f"native C++ compiler is unavailable: {compiler_name}")
    if not REALTIME_CAPACITY_HEADER.is_file():
        raise SystemExit(
            f"realtime capacity header is unavailable: {REALTIME_CAPACITY_HEADER}"
        )

    source = f"""
#include <iostream>
#include {json.dumps(str(REALTIME_CAPACITY_HEADER))}

int main() {{
  std::cout << "queue=" << lmdj::audio::kRealtimeQueueCapacity << '\\n'
            << "trigger_outcome="
            << lmdj::audio::kRealtimeTriggerOutcomeCapacity << '\\n'
            << "voice=" << lmdj::audio::kRealtimeVoiceCapacity << '\\n';
}}
"""
    nlohmann_shim = """#pragma once
#include <string>
#include <utility>
namespace nlohmann {
class json {
 public:
  static json object() { return {}; }
  template <typename T> T get() const;
  template <typename T> json& operator=(T&&) { return *this; }
};
template <typename ValueType, typename SFINAE = void>
struct adl_serializer;
}
"""

    with tempfile.TemporaryDirectory(prefix="lmdj-realtime-capacities-") as root:
        temporary_root = Path(root)
        shim_path = temporary_root / "nlohmann/json.hpp"
        shim_path.parent.mkdir(parents=True)
        shim_path.write_text(nlohmann_shim, encoding="utf-8", newline="\n")
        executable = temporary_root / "realtime-capacities"
        command = [
            compiler,
            "-std=c++20",
            "-I",
            str(temporary_root),
            "-I",
            str(REPOSITORY_ROOT / "packages/audio-runtime/include"),
            "-I",
            str(REPOSITORY_ROOT / "packages/foundation/include"),
            "-I",
            str(REPOSITORY_ROOT / "packages/project-cooker/include"),
            "-I",
            str(REPOSITORY_ROOT / "packages/authoring-domain/include"),
            "-x",
            "c++",
            "-",
            "-o",
            str(executable),
        ]
        try:
            compiled = subprocess.run(
                command,
                check=False,
                capture_output=True,
                input=source,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise SystemExit(
                f"realtime capacity probe compilation failed: {error}"
            ) from error
        if compiled.returncode != 0:
            raise SystemExit(
                "realtime capacity probe compilation failed:\n"
                + compiled.stderr[-4_096:]
            )
        try:
            evaluated = subprocess.run(
                [str(executable)],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise SystemExit(
                f"realtime capacity probe execution failed: {error}"
            ) from error
        if evaluated.returncode != 0:
            raise SystemExit(
                "realtime capacity probe execution failed:\n"
                + evaluated.stderr[-4_096:]
            )

    capacities = {}
    for line in evaluated.stdout.splitlines():
        name, separator, value = line.partition("=")
        if separator != "=" or name in capacities:
            raise SystemExit(
                f"realtime capacity probe returned invalid output: {evaluated.stdout!r}"
            )
        try:
            capacities[name] = int(value)
        except ValueError:
            raise SystemExit(
                f"realtime capacity probe returned invalid output: {evaluated.stdout!r}"
            ) from None
    expected_names = {"queue", "trigger_outcome", "voice"}
    if set(capacities) != expected_names or any(
        value <= 0 for value in capacities.values()
    ):
        raise SystemExit(
            f"realtime capacity probe returned invalid output: {evaluated.stdout!r}"
        )
    return capacities


def write_web_runtime_host_metadata(wav_hash: str) -> None:
    capacities = realtime_capacities()
    duration_ms = WEB_RUNTIME_HOST_FRAME_COUNT * 1_000 / SAMPLE_RATE
    maximum_concurrent_voices = math.ceil(
        duration_ms / WEB_RUNTIME_HOST_TRIGGER_PACING_MS
    )
    if WEB_RUNTIME_HOST_TRIGGER_COUNT >= capacities["queue"]:
        raise SystemExit("browser trigger count must remain below realtime queue capacity")
    if WEB_RUNTIME_HOST_TRIGGER_COUNT >= capacities["trigger_outcome"]:
        raise SystemExit(
            "browser trigger count must remain below trigger outcome capacity"
        )
    if maximum_concurrent_voices >= capacities["voice"]:
        raise SystemExit(
            "browser fixture concurrency must remain below realtime voice capacity"
        )

    metadata = {
        "contract": "lmdj.web-runtime-host.browser-fixture.v1",
        "trigger_proof": {
            "admission_count": WEB_RUNTIME_HOST_TRIGGER_COUNT,
            "capacities": capacities,
            "capacity_source": (
                "compiler-evaluated packages/audio-runtime/include/lmdj/audio/"
                "realtime_engine.hpp constants"
            ),
            "maximum_concurrent_voices": maximum_concurrent_voices,
            "pacing_ms": WEB_RUNTIME_HOST_TRIGGER_PACING_MS,
        },
        "wav": {
            "channels": 1,
            "duration_ms": duration_ms,
            "frame_count": WEB_RUNTIME_HOST_FRAME_COUNT,
            "path": "web-runtime-host-short.wav",
            "sample_rate": SAMPLE_RATE,
            "sample_width_bytes": 2,
            "sha256": wav_hash,
        },
    }
    metadata_path = FIXTURE_DIRECTORY / "web-runtime-host-fixture.json"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    FIXTURE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    fixtures = {
        "kick.wav": wav_bytes(1, kick_samples()),
        "snare.wav": wav_bytes(1, snare_samples()),
        "stereo.wav": wav_bytes(
            2,
            [32_767, -32_768, -32_768, 32_767, 123, -789, -456, 1_011],
        ),
        "web-runtime-host-short.wav": wav_bytes(1, web_runtime_host_samples()),
    }
    hashes = {
        name: write_fixture(name, contents)
        for name, contents in fixtures.items()
    }
    with open(FIXTURE_DIRECTORY / "hashes.json", "w", encoding="utf-8") as output:
        json.dump(
            {
                name: fixture_hash
                for name, fixture_hash in hashes.items()
                if name != "web-runtime-host-short.wav"
            },
            output,
            indent=2,
            sort_keys=True,
        )
        output.write("\n")
    write_web_runtime_host_metadata(hashes["web-runtime-host-short.wav"])


if __name__ == "__main__":
    main()
