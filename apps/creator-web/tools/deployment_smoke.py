#!/usr/bin/env python3

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys


RUNTIME_SMOKE_PATH = (
    Path(__file__).resolve().parents[2]
    / "web-runtime-host/tools/deployment_smoke.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_lmdj_web_runtime_deployment_smoke", RUNTIME_SMOKE_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("shared Web deployment smoke implementation is unavailable")
_RUNTIME_SMOKE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_RUNTIME_SMOKE)

ASSET_ROLES = _RUNTIME_SMOKE.ASSET_ROLES
CSP = _RUNTIME_SMOKE.CSP
REQUIRED_SECURITY_HEADERS = _RUNTIME_SMOKE.REQUIRED_SECURITY_HEADERS
SmokeError = _RUNTIME_SMOKE.SmokeError


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def discover_http_identity(
    *,
    base_url: str,
    require_https: bool = True,
    timeout_seconds: float = 10.0,
) -> dict[str, str]:
    identity = _RUNTIME_SMOKE.discover_http_identity(
        base_url=base_url,
        require_https=require_https,
        timeout_seconds=timeout_seconds,
        expected_host_id="creator-web",
    )
    return {"host_id": "creator-web", **identity}


def smoke(
    *,
    base_url: str,
    expected_product: str,
    expected_host: str,
    expected_host_id: str,
    expected_deploy_id: str | None = None,
    require_https: bool = True,
    timeout_seconds: float = 10.0,
) -> dict[str, object]:
    if expected_host_id != "creator-web":
        raise SmokeError("expected Host ID is invalid")
    started_at = _timestamp()
    result = _RUNTIME_SMOKE.smoke_http(
        base_url=base_url,
        expected_product_build=expected_product,
        expected_host_version=expected_host,
        expected_host_id=expected_host_id,
        expected_deploy_id=expected_deploy_id,
        require_https=require_https,
        timeout_seconds=timeout_seconds,
    )
    evidence: dict[str, object] = {
        "asset_count": result["asset_count"],
        "completed_at": _timestamp(),
        "host_id": expected_host_id,
        "host_version": expected_host,
        "index_sha256": result["index_sha256"],
        "manifest_sha256": result["manifest_sha256"],
        "product_build": expected_product,
        "started_at": started_at,
        "status": "passed",
        "url": base_url.rstrip("/") + "/",
    }
    if expected_deploy_id is not None:
        evidence["deploy_id"] = expected_deploy_id
    return evidence


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    if argv and argv[0] == "discover-identity":
        parser = argparse.ArgumentParser(
            description="Strictly discover published Creator Web Host identity"
        )
        parser.add_argument("base_url")
        parser.add_argument("--allow-http", action="store_true")
        parser.add_argument("--timeout", type=float, default=10.0)
        options = parser.parse_args(argv[1:])
        options.command = "discover-identity"
        return options
    parser = argparse.ArgumentParser(
        description="Validate an immutable published Creator Web Host"
    )
    parser.add_argument("base_url")
    parser.add_argument("expected_product")
    parser.add_argument("expected_host")
    parser.add_argument("--expected-deploy-id")
    parser.add_argument("--allow-http", action="store_true")
    parser.add_argument("--timeout", type=float, default=10.0)
    options = parser.parse_args(argv)
    options.command = "smoke"
    return options


def main(argv: list[str] | None = None) -> int:
    options = parse_arguments(sys.argv[1:] if argv is None else argv)
    try:
        if options.command == "discover-identity":
            result = discover_http_identity(
                base_url=options.base_url,
                require_https=not options.allow_http,
                timeout_seconds=options.timeout,
            )
        else:
            result = smoke(
                base_url=options.base_url,
                expected_product=options.expected_product,
                expected_host=options.expected_host,
                expected_host_id="creator-web",
                expected_deploy_id=options.expected_deploy_id,
                require_https=not options.allow_http,
                timeout_seconds=options.timeout,
            )
    except SmokeError as error:
        print(f"Creator deployment smoke error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
