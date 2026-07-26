from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class BuildIdentity:
    version: str
    revision: str


def build_identity_from_env() -> BuildIdentity:
    return BuildIdentity(
        version=os.environ.get("LMDJ_PRODUCT_VERSION", "").strip() or "dev",
        revision=os.environ.get("LMDJ_BUILD_REVISION", "").strip() or "unknown",
    )
