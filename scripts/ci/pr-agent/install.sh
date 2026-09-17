#!/usr/bin/env bash
# Install or update the PR-Agent engine on the Netcup review host.
#
# Run as root on the host:
#   sudo bash install.sh <staging-dir>
# where <staging-dir> holds the repository copies of pr_agent_review.py,
# runtime.toml and run-engine.sh. The pinned upstream source, vendored
# dependencies and tokenizer asset come from the already extracted bundle
# release under $INSTALL_ROOT/releases and are not changed here.
#
# What this does:
#   1. copies the installed bundle to a new release with the new adapter/config;
#   2. rewrites the IDENTITY manifest and DEPLOYMENT_IDENTITY.json so the engine's
#      own installation check binds the new adapter/config bytes;
#   3. makes the release root-owned and read-only, and gives every CI runner
#      account write access to the shared ledger and engine working directory
#      through POSIX ACLs. Runner services must separately allow these exact
#      paths in ReadWritePaths; changed mounts require an idle service restart;
#   4. verifies that candidate as a runner account, then atomically switches
#      current and retains the previous release for rollback. No model call.
set -euo pipefail

INSTALL_ROOT=${PR_AGENT_INSTALL_ROOT:-/var/lib/lmdj/pr-agent}
RUNNER_ACCOUNTS=${PR_AGENT_RUNNER_ACCOUNTS:-"lmdj-runner-01 lmdj-runner-02 lmdj-runner-03 lmdj-runner-04 lmdj-runner-05 lmdj-runner-06 lmdj-runner-07 lmdj-runner-08"}
PYTHON=/usr/bin/python3.12

fail() { echo "why: $*; remedy: correct the installation input and rerun install.sh" >&2; exit 2; }

[[ $(id -u) == 0 ]] || fail "run as root"
staging=$(readlink -f "${1:-}")
cd /
[[ -n "${1:-}" && -d "$staging" ]] || fail "usage: install.sh <staging-dir>"
for name in pr_agent_review.py runtime.toml run-engine.sh; do
  [[ -f "$staging/$name" ]] || fail "staging directory lacks $name"
done
[[ -x "$PYTHON" ]] || fail "$PYTHON is required"
[[ "$INSTALL_ROOT" == /* && "$INSTALL_ROOT" != / && ! -L "$INSTALL_ROOT" ]] || fail "installation root must be an absolute directory"
INSTALL_ROOT=$(readlink -f "$INSTALL_ROOT")
[[ -L "$INSTALL_ROOT/current" ]] || fail "no release is linked at $INSTALL_ROOT/current; extract the bundle first"
source_release=$(readlink -f "$INSTALL_ROOT/current")
[[ $(dirname "$source_release") == "$INSTALL_ROOT/releases" ]] || fail "current is outside the releases directory"
[[ -d "$source_release/pr_agent" && -d "$source_release/vendor" && -f "$source_release/IDENTITY" && -f "$source_release/DEPLOYMENT_IDENTITY.json" ]] \
  || fail "current is not a complete PR-Agent bundle"
for directory in "$INSTALL_ROOT" "$INSTALL_ROOT/releases" "$source_release"; do
  [[ ! -L "$directory" && $(stat -c %u "$directory") == 0 ]] || fail "installation directories must be root-owned"
  (( (8#$(stat -c %a "$directory") & 0022) == 0 )) || fail "installation directories must not be group/world writable"
done
command -v setfacl >/dev/null || fail "install the acl package on the host first"
[[ -f "$INSTALL_ROOT/slot.lock" && ! -L "$INSTALL_ROOT/slot.lock" ]] || fail "a regular slot.lock is required"
exec 9< "$INSTALL_ROOT/slot.lock"
flock -n 9 || fail "a review or installation owns the slot; wait for it to finish"

# Never rewrite a release already named by a retained result. Failed candidates
# remain for inspection, and current is unchanged until the witness succeeds.
release=$(mktemp -d "$INSTALL_ROOT/releases/cutover.XXXXXXXX")
cp -a "$source_release/." "$release/"

echo "release: $release"
install -o root -g root -m 0444 "$staging/pr_agent_review.py" "$release/pr_agent_review.py"
install -o root -g root -m 0444 "$staging/runtime.toml" "$release/runtime.toml"

# Rebind the candidate member identities. archive remains the seed bundle's
# provenance; adapter/config hashes identify the separately installed overlay.
"$PYTHON" - "$release" <<'PY'
import hashlib, json, pathlib, sys
release = pathlib.Path(sys.argv[1])

def identity(path):
    data = path.read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "byte_length": len(data)}

manifest_path = release / "IDENTITY"
manifest = {}
order = []
for line in manifest_path.read_text(encoding="utf-8").splitlines():
    if line and "=" in line:
        key, value = line.split("=", 1)
        manifest[key] = value
        order.append(key)
manifest["adapter_sha256"] = identity(release / "pr_agent_review.py")["sha256"]
manifest["default_config_sha256"] = identity(release / "config.toml")["sha256"]
manifest_path.chmod(0o644)
manifest_path.write_text("".join(f"{key}={manifest[key]}\n" for key in order), encoding="utf-8")
manifest_path.chmod(0o444)

deployment_path = release / "DEPLOYMENT_IDENTITY.json"
deployment = json.loads(deployment_path.read_text(encoding="utf-8"))
for name, relative in {
    "manifest": "IDENTITY", "adapter": "pr_agent_review.py", "default_config": "config.toml",
    "requirements_lock": "requirements.lock",
    "stock_tokenizer_asset": "tokenizer-cache/fb374d419588a4632f3f557e76b4b70aebbca790",
}.items():
    deployment["files"][name] = {"path": relative, **identity(release / relative)}
deployment_path.chmod(0o644)
deployment_path.write_text(json.dumps(deployment, sort_keys=True, separators=(",", ":")), encoding="utf-8")
deployment_path.chmod(0o444)
print("manifest adapter_sha256:", manifest["adapter_sha256"])
PY

# The engine trusts root-owned, non-writable bytes for every runner account.
chown -R root:root "$release"
find "$release" -type d -exec chmod 0755 {} +
find "$release" -type f -exec chmod 0444 {} +

# Shared writable state: budget ledger and engine working directory.
for directory in "$INSTALL_ROOT/engine-state" "$INSTALL_ROOT/engine"; do
  [[ ! -L "$directory" ]] || fail "shared state cannot be a symlink"
  mkdir -p "$directory"
  chown root:root "$directory"
  chmod 0755 "$directory"
  for account in $RUNNER_ACCOUNTS; do
    if id "$account" >/dev/null 2>&1; then
      setfacl -m "u:$account:rwx" -d -m "u:$account:rwx" "$directory"
    fi
  done
  # Existing ledger files must stay appendable by every runner account.
  for existing in "$directory"/*; do
    [[ ! -L "$existing" ]] || fail "shared state entries cannot be symlinks"
    [[ -f "$existing" ]] || continue
    for account in $RUNNER_ACCOUNTS; do
      id "$account" >/dev/null 2>&1 && setfacl -m "u:$account:rw" "$existing"
    done
  done
done

# Prove installation identity from a runner account. This is outside its service
# mount namespace: it does NOT prove live ReadWritePaths or ledger write access.
smoke_account=""
for account in $RUNNER_ACCOUNTS; do
  if id "$account" >/dev/null 2>&1; then smoke_account=$account; break; fi
done
[[ -n "$smoke_account" ]] || fail "no runner account exists for the witness check"
witness=$(sudo -u "$smoke_account" -H env PYTHONPATH="$release/vendor:$release" \
  PYTHONDONTWRITEBYTECODE=1 LITELLM_LOCAL_MODEL_COST_MAP=true \
  "$PYTHON" -s "$release/pr_agent_review.py" --config "$release/runtime.toml" \
  --engine-cwd "$INSTALL_ROOT/engine" --witness)
"$PYTHON" - "$witness" <<'PY'
import json, sys
witness = json.loads(sys.argv[1])
assert witness.get("schema") == "lmdj.pr-agent-config-witness.v1", witness
enabled = [name for name in witness["provider_order"] if witness["providers"][name]["enabled"]]
print("witness ok; enabled providers:", enabled)
print("engine:", witness["engine"]["name"], witness["engine"]["version"], witness["engine"]["source_commit"][:12])
PY
ln -s "$source_release" "$INSTALL_ROOT/previous.next.$$"
mv -Tf "$INSTALL_ROOT/previous.next.$$" "$INSTALL_ROOT/previous"
ln -s "$release" "$INSTALL_ROOT/current.next.$$"
mv -Tf "$INSTALL_ROOT/current.next.$$" "$INSTALL_ROOT/current"
echo "previous: $source_release"
echo "installed: $release"
