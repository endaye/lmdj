from __future__ import annotations

import json
import math
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

DEFAULT_MAX_BYTES = 200 * 1024 * 1024
DEFAULT_MAX_DURATION_SECONDS = 600.0
DEFAULT_FFPROBE_TIMEOUT_SECONDS = 15.0
_CHUNK_BYTES = 1024 * 1024
_SUPPORTED = ["wav", "mp3"]


@dataclass(frozen=True)
class UploadLimits:
    max_bytes: int
    max_duration_seconds: float
    ffprobe_timeout_seconds: float = DEFAULT_FFPROBE_TIMEOUT_SECONDS


@dataclass(frozen=True)
class AudioProbe:
    format_name: str
    codec_name: str
    duration_seconds: float


class PreflightError(Exception):
    def __init__(self, status_code: int, detail: dict[str, object]) -> None:
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


def limits_from_env() -> UploadLimits:
    return UploadLimits(
        max_bytes=int(os.environ.get("LMDJ_UPLOAD_MAX_BYTES", DEFAULT_MAX_BYTES)),
        max_duration_seconds=float(
            os.environ.get(
                "LMDJ_UPLOAD_MAX_DURATION_SECONDS",
                DEFAULT_MAX_DURATION_SECONDS,
            ),
        ),
        ffprobe_timeout_seconds=float(
            os.environ.get(
                "LMDJ_FFPROBE_TIMEOUT_SECONDS",
                DEFAULT_FFPROBE_TIMEOUT_SECONDS,
            ),
        ),
    )


def _unsupported(destination: Path) -> PreflightError:
    destination.unlink(missing_ok=True)
    return PreflightError(
        status_code=415,
        detail={"code": "unsupported_audio", "supported": _SUPPORTED.copy()},
    )


def persist_and_probe(
    file: UploadFile,
    destination: Path,
    limits: UploadLimits,
) -> AudioProbe:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".wav", ".mp3"}:
        raise _unsupported(destination)

    destination.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with destination.open("wb") as output:
        while chunk := file.file.read(_CHUNK_BYTES):
            total += len(chunk)
            if total > limits.max_bytes:
                output.close()
                destination.unlink(missing_ok=True)
                raise PreflightError(
                    status_code=413,
                    detail={
                        "code": "file_too_large",
                        "max_bytes": limits.max_bytes,
                    },
                )
            output.write(chunk)

    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name:format=format_name,duration",
        "-of",
        "json",
        str(destination),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=limits.ffprobe_timeout_seconds,
        )
        if result.returncode != 0:
            raise _unsupported(destination)
        payload = json.loads(result.stdout)
        streams = payload.get("streams")
        format_data = payload.get("format")
        if not isinstance(streams, list) or not streams or not isinstance(format_data, dict):
            raise _unsupported(destination)
        stream = streams[0]
        if not isinstance(stream, dict):
            raise _unsupported(destination)
        codec_name = stream.get("codec_name")
        format_name = format_data.get("format_name")
        duration = float(format_data.get("duration"))
        if (
            not isinstance(codec_name, str)
            or not codec_name
            or not isinstance(format_name, str)
            or not math.isfinite(duration)
            or duration < 0
        ):
            raise _unsupported(destination)
    except PreflightError:
        raise
    except subprocess.TimeoutExpired:
        destination.unlink(missing_ok=True)
        raise PreflightError(
            status_code=422,
            detail={
                "code": "audio_probe_timeout",
                "timeout_seconds": limits.ffprobe_timeout_seconds,
            },
        ) from None
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        raise _unsupported(destination) from None

    detected_formats = set(format_name.lower().split(","))
    expected_format = suffix.removeprefix(".")
    if expected_format not in detected_formats:
        raise _unsupported(destination)

    if duration > limits.max_duration_seconds:
        destination.unlink(missing_ok=True)
        raise PreflightError(
            status_code=422,
            detail={
                "code": "duration_too_long",
                "max_duration_seconds": limits.max_duration_seconds,
            },
        )

    return AudioProbe(
        format_name=format_name,
        codec_name=codec_name,
        duration_seconds=duration,
    )
