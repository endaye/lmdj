#!/usr/bin/env python3
"""The single distribution manifest asset-role vocabulary.

Both Web Host packagers (`apps/web-runtime-host/tools/package.py` and
`apps/creator-web/tools/package.py`) and the shared deployment validator
(`apps/web-runtime-host/tools/deployment_smoke.py`) name manifest asset roles.
Before this module each of them, and each smoke fixture, carried its own copy,
so a role could exist in a producer that the validator had never heard of. That
drift is only observable at the deployment boundary, after packaging, signing
and release have all passed; it reached recurrence 2 on 2026-09-06 (see
`.agents/pitfalls/manifest-role-validator-sync.md`).

Every consumer imports the names below instead of restating them, and
`apps/web-runtime-host/test/manifest_asset_role_parity_test.py` fails when a
producer and this vocabulary disagree in either direction.
"""

from __future__ import annotations


CAPTURE_WORKLET = "capture_worklet"
HOST_MAIN = "host_main"
HOST_MODULE = "host_module"
HOST_STYLE = "host_style"
PERFORM_MASTER_TAP_WORKLET = "perform_master_tap_worklet"
PLATFORM_MODULE = "platform_module"
PRODUCT_IDENTITY = "product_identity"
RUNTIME_SCRIPT = "runtime_script"
RUNTIME_WASM = "runtime_wasm"

# Every role the shared deployment validator accepts in a manifest it is asked
# to validate. This is a historical union, not the current production
# inventory: the validator also baselines the previously published deployment
# as a rollback anchor, so a role that no current packager emits stays here as
# long as a retained published manifest still carries it.
ALLOWED_ASSET_ROLES = frozenset(
    (
        CAPTURE_WORKLET,
        HOST_MAIN,
        HOST_MODULE,
        HOST_STYLE,
        PERFORM_MASTER_TAP_WORKLET,
        PLATFORM_MODULE,
        PRODUCT_IDENTITY,
        RUNTIME_SCRIPT,
        RUNTIME_WASM,
    )
)

# Roles a Runtime Host manifest must carry exactly once.
SINGLETON_ASSET_ROLES = frozenset(
    (HOST_MAIN, HOST_STYLE, RUNTIME_SCRIPT, RUNTIME_WASM)
)

# What each packager is allowed to emit. These must equal the roles named by
# `hosts.<host_id>.expected_assets` in the Runtime identity, which is what both
# packagers order and verify their shipped manifests against; the parity gate
# asserts that equality so this declaration cannot drift from the producer.
WEB_RUNTIME_HOST_EMITTED_ASSET_ROLES = frozenset(
    (
        HOST_MAIN,
        HOST_MODULE,
        HOST_STYLE,
        PLATFORM_MODULE,
        PRODUCT_IDENTITY,
        RUNTIME_SCRIPT,
        RUNTIME_WASM,
    )
)
CREATOR_WEB_EMITTED_ASSET_ROLES = frozenset(
    (
        CAPTURE_WORKLET,
        HOST_MAIN,
        HOST_STYLE,
        PERFORM_MASTER_TAP_WORKLET,
        RUNTIME_SCRIPT,
        RUNTIME_WASM,
    )
)
EMITTED_ASSET_ROLES_BY_HOST_ID = {
    "creator-web": CREATOR_WEB_EMITTED_ASSET_ROLES,
    "web-runtime-host": WEB_RUNTIME_HOST_EMITTED_ASSET_ROLES,
}

# A Creator manifest carries exactly this inventory, one asset per role.
# Creator Host 3.0.0 added the Perform master tap; Creator Host 2.x priors,
# which the exact-tag deploy still discovers as its rollback identity, must
# keep the five-role inventory and must not claim the tap.
CREATOR_CURRENT_ASSET_ROLES = CREATOR_WEB_EMITTED_ASSET_ROLES
CREATOR_LEGACY_ASSET_ROLES = CREATOR_CURRENT_ASSET_ROLES - frozenset(
    (PERFORM_MASTER_TAP_WORKLET,)
)

RUNTIME_IDENTITY_RELATIVE_PATH = "tools/web-runtime/runtime-identity.json"
GENERATED_RUNTIME_IDENTITY_RELATIVE_PATH = (
    "products/lmdj/generated/web-runtime-identity.json"
)


def emitted_roles_from_identity(identity: object, host_id: str) -> frozenset[str]:
    """Roles the packager for `host_id` can ship, read from a Runtime identity.

    `expected_assets` is the inventory both packagers build their manifest
    asset list from and then re-verify position by position, so its `role`
    values are the producer's real vocabulary rather than a restatement of it.
    """
    if not isinstance(identity, dict):
        raise ValueError("Runtime identity is not an object")
    hosts = identity.get("hosts")
    if not isinstance(hosts, dict) or host_id not in hosts:
        raise ValueError(f"Runtime identity has no Host {host_id!r}")
    expected_assets = hosts[host_id].get("expected_assets")
    if not isinstance(expected_assets, list) or not expected_assets:
        raise ValueError(f"Host {host_id!r} declares no expected assets")
    roles = set()
    for entry in expected_assets:
        if not isinstance(entry, dict) or not isinstance(entry.get("role"), str):
            raise ValueError(f"Host {host_id!r} expected asset entry is invalid")
        roles.add(entry["role"])
    return frozenset(roles)
