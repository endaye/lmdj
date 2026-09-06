#!/usr/bin/env bash
# Install or update the elastic runner controller on a trusted Linux host (#327).
#
# Runs ON the host as root, from a repository checkout:
#
#   sudo bash scripts/ci/elastic-runner/deploy-controller.sh \
#     scripts/ci/elastic-runner/contabo.json
#
# The controller lives one directory up, in scripts/ci/, because it is a CI
# script that the contract tests import; the unit files and host configs live
# here beside this script. Resolving both from this script's own location is
# what lets a plain `git clone` be the staging directory -- assembling one by
# hand was the documented path and it failed on the first real redeploy, with
# `install: cannot stat .../elastic-runner/elastic_runner.py`.
set -euo pipefail

config="${1:?usage: deploy-controller.sh <config.json>}"
here="$(cd "$(dirname "$0")" && pwd)"

controller="$here/../elastic_runner.py"
[ -f "$controller" ] || controller="$here/elastic_runner.py"
if [ ! -f "$controller" ]; then
  echo "why: elastic_runner.py is neither at $here/../ nor beside this script," >&2
  echo "  so the controller this deploys cannot be found" >&2
  echo "remedy: run this from a repository checkout, or place the controller" >&2
  echo "  beside the script" >&2
  exit 2
fi

python3 - "$config" <<'EOF'
import json, sys
json.load(open(sys.argv[1]))
EOF

install -d -o root -g root -m 0755 /usr/local/lib/lmdj /etc/lmdj
install -o root -g root -m 0755 "$controller" /usr/local/lib/lmdj/elastic_runner.py
install -o root -g root -m 0644 "$config" /etc/lmdj/elastic-runner.json
install -o root -g root -m 0644 "$here/lmdj-elastic-runner.service" /etc/systemd/system/lmdj-elastic-runner.service
install -o root -g root -m 0644 "$here/lmdj-elastic-runner.timer" /etc/systemd/system/lmdj-elastic-runner.timer

# Baseline services outrank elastic ones under contention: the admission
# guards cannot shed load already admitted, so priority is set at the unit.
baseline_units="$(python3 -c '
import json, sys
for entry in json.load(open(sys.argv[1]))["baseline"]:
    print(entry["service"])
' /etc/lmdj/elastic-runner.json)"
for unit in $baseline_units; do
  install -d -o root -g root -m 0755 "/etc/systemd/system/${unit}.d"
  printf '[Service]\nCPUWeight=300\n' > "/etc/systemd/system/${unit}.d/20-lmdj-priority.conf"
  # set-property applies the weight to the live cgroup immediately, so a busy
  # baseline runner does not need a restart for the drop-in to matter.
  systemctl set-property --runtime "$unit" CPUWeight=300 2>/dev/null || true
  echo "priority drop-in written for ${unit}"
done

systemctl daemon-reload
for unit in $baseline_units; do
  systemctl enable --now "$unit"
done
systemctl enable --now lmdj-elastic-runner.timer

# One dry run proves the controller can observe and decide on this host.
python3 /usr/local/lib/lmdj/elastic_runner.py \
  --config /etc/lmdj/elastic-runner.json \
  --state /var/lib/lmdj-elastic/state.json --dry-run
echo "controller deployed; timer $(systemctl is-enabled lmdj-elastic-runner.timer)/$(systemctl is-active lmdj-elastic-runner.timer)"
