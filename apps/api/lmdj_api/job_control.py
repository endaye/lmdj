from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
from pathlib import Path

CONTROL_FILENAME = "control.json"

_CONTROL_TOKEN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")


def new_control_token() -> str:
    return secrets.token_urlsafe(32)


def validate_control_token(value: str) -> str:
    if not _CONTROL_TOKEN.fullmatch(value):
        raise ValueError("invalid job control token")
    return value


def write_job_control(job_dir: Path, token: str) -> None:
    token = validate_control_token(token)
    payload = {
        "schema": "lmdj.job-control.v1",
        "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
    }
    temporary = job_dir / f"{CONTROL_FILENAME}.tmp"
    temporary.write_text(json.dumps(payload, indent=2))
    os.replace(temporary, job_dir / CONTROL_FILENAME)


def verify_job_control(job_dir: Path, token: str) -> bool:
    try:
        token = validate_control_token(token)
        payload = json.loads((job_dir / CONTROL_FILENAME).read_text())
        expected = payload["token_sha256"]
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return False
    return isinstance(expected, str) and hmac.compare_digest(
        expected,
        hashlib.sha256(token.encode()).hexdigest(),
    )
