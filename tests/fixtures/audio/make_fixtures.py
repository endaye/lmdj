import hashlib
import json
import math
import struct
import wave


FIXTURE_DIRECTORY = "tests/fixtures/audio"
SAMPLE_RATE = 48_000


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
    path = f"{FIXTURE_DIRECTORY}/{name}"
    expected_hash = hashlib.sha256(contents).hexdigest()
    try:
        with open(path, "rb") as existing:
            existing_hash = hashlib.sha256(existing.read()).hexdigest()
    except FileNotFoundError:
        existing_hash = None
    if existing_hash is not None and existing_hash != expected_hash:
        raise SystemExit(f"fixture hash changed unexpectedly: {path}")
    with open(path, "wb") as output:
        output.write(contents)
    with wave.open(path, "rb") as fixture:
        if (fixture.getsampwidth(), fixture.getframerate()) != (2, SAMPLE_RATE):
            raise SystemExit(f"fixture encoding is invalid: {path}")
    return expected_hash


def main() -> None:
    fixtures = {
        "kick.wav": wav_bytes(1, kick_samples()),
        "snare.wav": wav_bytes(1, snare_samples()),
        "stereo.wav": wav_bytes(
            2,
            [32_767, -32_768, -32_768, 32_767, 123, -789, -456, 1_011],
        ),
    }
    hashes = {
        name: write_fixture(name, contents)
        for name, contents in fixtures.items()
    }
    with open(f"{FIXTURE_DIRECTORY}/hashes.json", "w", encoding="utf-8") as output:
        json.dump(hashes, output, indent=2, sort_keys=True)
        output.write("\n")


if __name__ == "__main__":
    main()
