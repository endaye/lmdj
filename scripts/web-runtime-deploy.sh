#!/usr/bin/env bash
# Stable entry point; the implementation is shared with the other Web Host.
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/web-host-deploy.sh" web-runtime-host "$@"
