#!/bin/bash
# Admit or withdraw the M4 Pro overflow runner by its host conditions (#2278).
#
# The M4 Pro is the owner's everyday laptop. It may take the macOS gates only
# while all of these hold (owner policy, 2026-10-18):
#   - on AC power, continuously for at least 10 minutes (never on battery);
#   - the owner has been idle for at least 15 minutes;
#   - no thermal or performance warning is recorded;
#   - at least 30 GB free on the data volume;
#   - the CI egress is fast: a fixed 10 MiB GitHub range downloaded every
#     10 minutes, admitted after two consecutive samples of at least 2 MiB/s
#     and withdrawn after one under 500 KiB/s or a failed download. The M4
#     and en-home share a Tailscale exit node whose throughput swings from
#     MiB/s to tens of KiB/s.
# launchd runs this every minute, so unplugging or returning to the keyboard
# withdraws the label within a minute. A job already running continues. Any
# network is allowed. An unreadable Runner API changes nothing, and a failed
# label write is logged as such and retried on the next run.
#
# Install: copy this file and com.lmdj.runner-network-admission.plist (see
# docs/quality/core-test-policy.md). Requires an authenticated `gh` with admin
# access to the repository.
set -uo pipefail
export PATH="${LMDJ_ADMISSION_PATH:-/opt/homebrew/bin:/usr/local/bin:/usr/bin:/usr/sbin:/bin:/sbin}"
REPOSITORY="${LMDJ_ADMISSION_REPOSITORY:-endaye/lmdj}"
RUNNER_ID="${LMDJ_ADMISSION_RUNNER_ID:-37}"
LABEL="${LMDJ_ADMISSION_LABEL:-ci-macos-gates}"
DIR="${LMDJ_ADMISSION_STATE_DIR:-$HOME/Library/Application Support/lmdj-ci}"
NOW="${LMDJ_ADMISSION_NOW:-$(date +%s)}"
ADMIT_BYTES_PER_SECOND=2097152
REVOKE_BYTES_PER_SECOND=512000
ADMIT_STREAK=2
PROBE_INTERVAL_SECONDS=600
AC_MIN_SECONDS=600
IDLE_MIN_SECONDS=900
DISK_MIN_GB=30
PROBE_URL=https://github.com/actions/runner/releases/download/v2.338.0/actions-runner-linux-x64-2.338.0.tar.gz
mkdir -p "$DIR"
STATE="$DIR/admission-state"; LOG="$DIR/admission.log"

# State: streak, network verdict (fast|slow|unknown), last probe time, AC-since time.
# Read as data, never sourced: an unknown key or malformed value is ignored.
streak=0; network=unknown; probed_at=0; ac_since=0
while IFS='=' read -r key value; do
  case "$key=$value" in
    streak=[0-9]*|probed_at=[0-9]*|ac_since=[0-9]*)
      [[ "$value" =~ ^[0-9]+$ ]] && printf -v "$key" '%s' "$value";;
    network=fast|network=slow|network=unknown) network=$value;;
  esac
done < <(cat "$STATE" 2>/dev/null)

if [ $((NOW - probed_at)) -ge "$PROBE_INTERVAL_SECONDS" ]; then
  out=$(curl -sS -L -o /dev/null -r 0-10485759 --max-time 30 \
    -w '%{speed_download} %{size_download} %{http_code}' "$PROBE_URL" 2>&1); rc=$?
  out=${out//$'\n'/ }
  speed=0
  if [ $rc -eq 0 ] && [[ "$out" =~ ^([0-9.]+)\ ([0-9]+)\ ([0-9]+)$ ]] \
    && [ "${BASH_REMATCH[3]}" -lt 400 ] && [ "${BASH_REMATCH[2]}" -gt 1048576 ]; then
    speed=${BASH_REMATCH[1]%.*}
  fi
  if [ "$speed" -ge "$ADMIT_BYTES_PER_SECOND" ]; then streak=$((streak+1)); else streak=0; fi
  if [ "$speed" -lt "$REVOKE_BYTES_PER_SECOND" ]; then network=slow
  elif [ "$streak" -ge "$ADMIT_STREAK" ]; then network=fast
  fi
  probed_at=$NOW
  echo "$(date -u +%FT%TZ) probe speed=${speed}B/s curl='$out' streak=$streak network=$network" >>"$LOG"
fi

blockers=()
if pmset -g batt | head -1 | grep -q "AC Power"; then
  [ "$ac_since" -gt 0 ] || ac_since=$NOW
  [ $((NOW - ac_since)) -ge "$AC_MIN_SECONDS" ] || blockers+=("ac<${AC_MIN_SECONDS}s")
else
  ac_since=0; blockers+=("battery")
fi
idle_ns=$(ioreg -c IOHIDSystem | awk '/HIDIdleTime/ {print $NF; exit}')
[ $(( ${idle_ns:-0} / 1000000000 )) -ge "$IDLE_MIN_SECONDS" ] || blockers+=("user-active")
# Nominal prints only "No ... warning level has been recorded" notes; a
# recorded warning level above 0 or a CPU speed limit under 100 blocks.
pmset -g therm | awk -F'= *' '/CPU_Speed_Limit/ && $2+0 < 100 {hot=1}
  /[Ww]arning [Ll]evel *=/ && $2+0 > 0 {hot=1} END {exit !hot}' && blockers+=("thermal")
free_gb=$(df -g /System/Volumes/Data 2>/dev/null | awk 'NR==2 {print $4}')
[ "${free_gb:-0}" -ge "$DISK_MIN_GB" ] || blockers+=("disk<${DISK_MIN_GB}GB")
[ "$network" = fast ] || blockers+=("network-$network")

printf 'streak=%s\nnetwork=%s\nprobed_at=%s\nac_since=%s\n' "$streak" "$network" "$probed_at" "$ac_since" >"$STATE"

if ! labels=$(gh api "repos/$REPOSITORY/actions/runners/$RUNNER_ID" --jq '[.labels[].name]|join(",")' 2>&1); then
  echo "$(date -u +%FT%TZ) gh-error $labels" >>"$LOG"
  exit 0
fi
admitted=false; [[ ",$labels," == *",$LABEL,"* ]] && admitted=true
action=keep
if $admitted && [ ${#blockers[@]} -gt 0 ]; then
  if gh api -X DELETE "repos/$REPOSITORY/actions/runners/$RUNNER_ID/labels/$LABEL" --silent; then
    action=revoke
  else
    action=revoke-failed
  fi
elif ! $admitted && [ ${#blockers[@]} -eq 0 ]; then
  if gh api -X POST "repos/$REPOSITORY/actions/runners/$RUNNER_ID/labels" -f "labels[]=$LABEL" --silent; then
    action=admit
  else
    action=admit-failed
  fi
fi
# Log every change, and otherwise only when the blockers change.
summary="admitted=$admitted blockers=${blockers[*]:-none} action=$action"
last=$(tail -1 "$LOG" 2>/dev/null | sed -E 's/^[^ ]+ //')
if [ "$action" != keep ] || [ "$summary" != "$last" ]; then
  echo "$(date -u +%FT%TZ) $summary" >>"$LOG"
fi
