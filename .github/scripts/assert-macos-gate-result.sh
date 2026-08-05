#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 core|asan" >&2
  exit 64
fi

case "$1" in
  core|asan) gate_name="$1" ;;
  *)
    echo "unknown macOS gate: $1" >&2
    exit 64
    ;;
esac

selected_lane=primary
completed="${PRIMARY_COMPLETED:-}"
prepare_result="${PRIMARY_PREPARE_RESULT:-}"
case "$gate_name" in
  core) gate_result="${PRIMARY_CORE_RESULT:-}" ;;
  asan) gate_result="${PRIMARY_ASAN_RESULT:-}" ;;
esac

if [[ "${FALLBACK_COMPLETED:-}" == "true" ]]; then
  selected_lane=fallback
  completed="$FALLBACK_COMPLETED"
  prepare_result="${FALLBACK_PREPARE_RESULT:-}"
  case "$gate_name" in
    core) gate_result="${FALLBACK_CORE_RESULT:-}" ;;
    asan) gate_result="${FALLBACK_ASAN_RESULT:-}" ;;
  esac
fi

if [[ "$completed" != "true" ]]; then
  echo "no macOS CI lane completed; primary infrastructure failed and no fallback result is available" >&2
  exit 1
fi

printf 'macOS gate lane=%s prepare=%s %s=%s\n' \
  "$selected_lane" "$prepare_result" "$gate_name" "$gate_result"

if [[ "$prepare_result" != "success" || "$gate_result" != "success" ]]; then
  echo "macOS $gate_name gate failed semantically; test failures are not retried" >&2
  exit 1
fi
