#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

cd "$ROOT"
python3 -m unittest scripts/release/tests/test_release_version.py -v
bash scripts/release/tests/test-publish-staging-release.sh

echo "release-versioning tests passed"
