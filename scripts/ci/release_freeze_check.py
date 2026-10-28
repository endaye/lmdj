#!/usr/bin/env python3
"""Refuse CI and release-tool control-plane changes while a release request is active.

`scripts/release.sh run` holds the repository variable `LMDJ_RELEASE_FREEZE`
as the id of the request it drives and releases it when the request
completes or is retired. While it is set, a Pull Request that changes a
frozen path (the CI workflows and actions, `scripts/ci/`, `scripts/release.sh`
and `tools/release/`) fails this check: the cut PR must merge with zero
drift and the candidate batch must not see CI changes, and the 2.0.122.0
release lost a candidate to exactly such a merge (#2422 item 10, #2404
item 1). Everything else merges as usual; the changed files come from the
frozen change-scope manifest, never from a dispatcher-supplied list. An
unreadable input fails closed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

FROZEN_PREFIXES = (".github/workflows/", ".github/actions/", "scripts/ci/", "tools/release/")
FROZEN_EXACT = ("scripts/release.sh",)
_REQUEST_ID = re.compile(r"release-[0-9a-f]{16}\Z")


class FreezeCheckError(ValueError):
    pass


def require(condition, why, remedy):
    if not condition:
        raise FreezeCheckError(f"why: {why}; remedy: {remedy}")


def frozen_paths(paths):
    """The paths, sorted, that the release freeze covers."""
    return sorted(path for path in set(paths)
                  if path in FROZEN_EXACT or any(path.startswith(prefix) for prefix in FROZEN_PREFIXES))


def changed_paths(manifest_json):
    """Every changed path the frozen change-scope manifest records."""
    try:
        manifest = json.loads(manifest_json)
    except (TypeError, ValueError):
        require(False, "the change-scope manifest is not JSON",
                "pass the change-scope job's manifest output unchanged")
    files = manifest.get("changed_files") if isinstance(manifest, dict) else None
    require(isinstance(files, list), "the change-scope manifest records no changed_files list",
            "pass the change-scope job's manifest output unchanged")
    paths = []
    for record in files:
        record_paths = record.get("paths") if isinstance(record, dict) else None
        require(isinstance(record_paths, list) and all(isinstance(path, str) and path for path in record_paths),
                "a changed_files record names no path list", "pass the change-scope job's manifest output unchanged")
        paths.extend(record_paths)
    return paths


def read_manifest(path):
    """The manifest text, read even when no request holds the freeze."""
    try:
        with open(path, encoding="utf-8") as manifest:
            return manifest.read()
    except (OSError, UnicodeDecodeError):
        require(False, f"the change-scope manifest file {path} is unreadable",
                "download the change-scope job's manifest artifact unchanged")


def evaluate(freeze, manifest_json):
    """(ok, message). The message says who holds the freeze and what is frozen."""
    holder = (freeze or "").strip()
    if not holder:
        return True, "release freeze: no release request holds the freeze; nothing is frozen"
    require(_REQUEST_ID.fullmatch(holder) is not None,
            f"LMDJ_RELEASE_FREEZE is {holder!r}, not a release request id",
            "clear or correct the variable as `scripts/release.sh doctor` directs")
    frozen = frozen_paths(changed_paths(manifest_json))
    if frozen:
        return False, (f"why: release request {holder} holds the freeze and this Pull Request changes "
                       f"frozen control-plane paths: {', '.join(frozen)}; remedy: wait until the request "
                       "completes or is retired (`scripts/release.sh status` on the operator host), then "
                       "rerun this check; do not merge around it")
    return True, f"release freeze: request {holder} holds the freeze; this Pull Request touches no frozen path"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", required=True, help="the LMDJ_RELEASE_FREEZE repository variable (may be empty)")
    parser.add_argument("--manifest-file", required=True,
                        help="the change-scope manifest file; a large PR's manifest exceeds the argv/env limit")
    arguments = parser.parse_args(argv)
    try:
        ok, message = evaluate(arguments.freeze, read_manifest(arguments.manifest_file))
    except FreezeCheckError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(message, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
