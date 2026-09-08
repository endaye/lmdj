#!/usr/bin/env bash
# Compatibility entry point for historical instructions; use docs-site.sh.
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$script_dir/docs-site.sh" "$@"
