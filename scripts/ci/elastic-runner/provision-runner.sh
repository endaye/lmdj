#!/usr/bin/env bash
# Provision one GitHub Actions runner service on a trusted Linux host (#327).
#
# Runs ON the host as root. The registration token is read from stdin and is
# never written to disk or shell history; no PAT is stored on the host. The
# runner tarball is checksum-pinned; a mismatch fails closed.
#
# Usage:
#   echo "$TOKEN" | provision-runner.sh \
#     --index 05 --name netcup-lmdj-linux-05 \
#     --labels lmdj-linux,lmdj-linux-pool,ci-general,netcup,ci-only-host,ci-web-heavy,elastic \
#     --template /root/unit.template --mode elastic
#
# --mode baseline: service enabled and started (survives reboot).
# --mode elastic:  service registered, disabled, and stopped (the controller
#                  decides any later expansion; reboot restores baseline only).
set -euo pipefail

RUNNER_VERSION="2.336.0"
RUNNER_SHA256="04cf0be1aff4c3ec3554466c39124ca250e3effd8873bb7e8d68535aa9505d5d"
REPO_URL="https://github.com/endaye/lmdj"
DIST_DIR="/opt/actions-runner-dist"

index="" name="" labels="" template="" mode=""
while [ $# -gt 0 ]; do
  case "$1" in
    --index) index="$2"; shift 2 ;;
    --name) name="$2"; shift 2 ;;
    --labels) labels="$2"; shift 2 ;;
    --template) template="$2"; shift 2 ;;
    --mode) mode="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
if [ -z "$index" ] || [ -z "$name" ] || [ -z "$labels" ] || [ -z "$template" ]; then
  echo "why: --index, --name, --labels, and --template are all required" >&2
  echo "remedy: pass every flag; see the usage header of this script" >&2
  exit 2
fi
if [ "$mode" != "baseline" ] && [ "$mode" != "elastic" ]; then
  echo "why: --mode must be baseline or elastic, got '$mode'" >&2
  echo "remedy: baseline services boot with the host, elastic services do not" >&2
  exit 2
fi

user="lmdj-runner-${index}"
workdir="/opt/actions-runner-${index}"
unit="actions.runner.endaye-lmdj.${name}.service"

token="$(cat)"
if [ -z "$token" ]; then
  echo "why: no registration token on stdin" >&2
  echo "remedy: generate one off-host with 'gh api -X POST repos/endaye/lmdj/actions/runners/registration-token' and pipe it in" >&2
  exit 2
fi

if id "$user" >/dev/null 2>&1; then
  echo "user $user already exists, reusing"
else
  useradd --system --create-home --home-dir "/var/lib/${user}" \
    --shell /usr/sbin/nologin "$user"
fi
# The shared build caches are root:lmdj-ci-cache mode 2770; a runner outside
# that group fails every cache write its unit's Environment= promises.
if getent group lmdj-ci-cache >/dev/null 2>&1; then
  usermod -aG lmdj-ci-cache "$user"
fi

mkdir -p "$DIST_DIR"
tarball="$DIST_DIR/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
if [ ! -f "$tarball" ]; then
  curl -fsSL -o "$tarball" \
    "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
fi
echo "${RUNNER_SHA256}  ${tarball}" | sha256sum -c - || {
  echo "why: runner tarball checksum mismatch; the pinned bytes are not what was downloaded" >&2
  echo "remedy: delete ${tarball} and retry; if it persists, verify the pin against the official v${RUNNER_VERSION} release digest" >&2
  rm -f "$tarball"
  exit 1
}

if [ -e "$workdir/.runner" ]; then
  echo "why: $workdir already holds a configured runner" >&2
  echo "remedy: this script never reconfigures in place; remove the service and directory deliberately first" >&2
  exit 1
fi
mkdir -p "$workdir"
tar -xzf "$tarball" -C "$workdir"
chown -R "${user}:${user}" "$workdir"

sudo -u "$user" HOME="/var/lib/${user}" bash -c "cd '$workdir' && ./config.sh \
  --unattended --url '$REPO_URL' --token '$token' \
  --name '$name' --labels '$labels' --work _work"

cat > "$workdir/runsvc.sh" <<'RUNSVC'
#!/bin/bash

# convert SIGTERM signal to SIGINT
# for more info on how to propagate SIGTERM to a child process see: http://veithen.github.io/2014/11/16/sigterm-propagation.html
trap 'kill -INT $PID' TERM INT

if [ -f ".path" ]; then
    # configure
    export PATH=`cat .path`
    echo ".path=${PATH}"
fi

nodever="node20"

# insert anything to setup env when running as a service
# run the host process which keep the listener alive
./externals/$nodever/bin/node ./bin/RunnerService.js &
PID=$!
wait $PID
trap - TERM INT
RUNSVC
chmod 0755 "$workdir/runsvc.sh"
chown "${user}:${user}" "$workdir/runsvc.sh"

if [ "$mode" = "baseline" ]; then cpu_weight=300; else cpu_weight=100; fi
sed -e "s|@INDEX@|${index}|g" -e "s|@NAME@|${name}|g" \
    -e "s|@WORKDIR@|${workdir}|g" -e "s|@CPUWEIGHT@|${cpu_weight}|g" \
    "$template" > "/etc/systemd/system/${unit}"
systemctl daemon-reload

if [ "$mode" = "baseline" ]; then
  systemctl enable --now "$unit"
else
  systemctl disable "$unit" >/dev/null 2>&1 || true
  systemctl stop "$unit" >/dev/null 2>&1 || true
fi

echo "provisioned ${name}: user=${user} workdir=${workdir} unit=${unit} mode=${mode}"
