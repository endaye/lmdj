#!/bin/bash
# Admit or withdraw an overflow runner by its measured egress (#2278, #2279).
#
# The M4 Pro and en-home overflow runners reach GitHub through a shared
# Tailscale exit node whose throughput swings from MiB/s to tens of KiB/s.
# A runner admitted while the link is slow fails checkout or downloads and
# turns a batch red. Each overflow host runs this every 10 minutes (launchd on
# the M4 Pro; the PowerShell twin on en-home). It downloads a fixed 10 MiB
# range over the same egress CI uses and toggles the runner's admission label
# through the Runner API, so a slow link returns its work to netcup or the M1
# instead of failing it. Admission needs two consecutive fast samples; one
# slow or failed sample withdraws it at once.
#
# Install on the M4 Pro: copy this file and com.lmdj.runner-network-admission.plist
# (see docs/quality/core-test-policy.md). Requires an authenticated `gh` with
# admin access to the repository.
set -uo pipefail
export PATH="${LMDJ_ADMISSION_PATH:-/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin}"
REPOSITORY="${LMDJ_ADMISSION_REPOSITORY:-endaye/lmdj}"
RUNNER_ID="${LMDJ_ADMISSION_RUNNER_ID:-37}"
LABEL="${LMDJ_ADMISSION_LABEL:-ci-macos-gates}"
DIR="${LMDJ_ADMISSION_STATE_DIR:-$HOME/Library/Application Support/lmdj-ci}"
ADMIT_BYTES_PER_SECOND=2097152
REVOKE_BYTES_PER_SECOND=512000
ADMIT_STREAK=2
PROBE_URL=https://github.com/actions/runner/releases/download/v2.338.0/actions-runner-linux-x64-2.338.0.tar.gz
mkdir -p "$DIR"
STATE="$DIR/admission-state"; LOG="$DIR/admission.log"
streak=$(cat "$STATE" 2>/dev/null || echo 0)
out=$(curl -sS -L -o /dev/null -r 0-10485759 --max-time 30 \
  -w '%{speed_download} %{size_download} %{http_code}' "$PROBE_URL" 2>&1); rc=$?
speed=0
if [ $rc -eq 0 ] && [[ "$out" =~ ^([0-9.]+)\ ([0-9]+)\ ([0-9]+)$ ]] \
  && [ "${BASH_REMATCH[3]}" -lt 400 ] && [ "${BASH_REMATCH[2]}" -gt 1048576 ]; then
  speed=${BASH_REMATCH[1]%.*}
fi
if ! labels=$(gh api "repos/$REPOSITORY/actions/runners/$RUNNER_ID" --jq '[.labels[].name]|join(",")' 2>&1); then
  echo "$(date -u +%FT%TZ) gh-error $labels" >>"$LOG"
  exit 0
fi
admitted=false; [[ ",$labels," == *",$LABEL,"* ]] && admitted=true
if [ "$speed" -ge "$ADMIT_BYTES_PER_SECOND" ]; then streak=$((streak+1)); else streak=0; fi
action=keep
if $admitted && [ "$speed" -lt "$REVOKE_BYTES_PER_SECOND" ]; then
  gh api -X DELETE "repos/$REPOSITORY/actions/runners/$RUNNER_ID/labels/$LABEL" --silent && action=revoke
elif ! $admitted && [ "$streak" -ge "$ADMIT_STREAK" ]; then
  gh api -X POST "repos/$REPOSITORY/actions/runners/$RUNNER_ID/labels" -f "labels[]=$LABEL" --silent && action=admit
fi
echo "$streak" >"$STATE"
echo "$(date -u +%FT%TZ) speed=${speed}B/s curl='$out' admitted=$admitted streak=$streak action=$action" >>"$LOG"
