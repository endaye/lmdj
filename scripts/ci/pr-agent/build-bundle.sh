#!/usr/bin/env bash
set -euo pipefail

# Build and export a pinned Linux amd64 Python bundle. The Dockerfile is only
# a reproducible build tool: production runs the exported files under a
# systemd-sandboxed Python 3.12 service, not a Docker daemon.

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
OUTPUT_DIR=${1:-${PR_AGENT_OUTPUT_DIR:-/tmp/lmdj-pr-agent-packaging/artifacts}}
SOURCE_ROOT=${PR_AGENT_SOURCE_ROOT:-/tmp/lmdj-pr-agent-upstream}
PYTHON_BIN=${PR_AGENT_PYTHON:-python3.12}
PYTHON_IMAGE=${PR_AGENT_PYTHON_IMAGE:-python:3.12.14-slim}
PYTHON_IMAGE_DIGEST=${PR_AGENT_PYTHON_IMAGE_DIGEST:-}
SOURCE_COMMIT=53072488e4c3b5a6c9ae730fe6fb52fc5f09d06c
SOURCE_VERSION=0.45.0
EXPECTED_SOURCE_TREE_SHA256=65af56f5627de2f42cd1de278321241dac2f54bdcfa596d3dc7a380ada534abf

fail() {
  echo "build-bundle: $*" >&2
  exit 2
}

require_clean_base_marker() {
  local log_file=$1
  local expected_bytes=$2
  local expected_sha256=$3
  local marker_count
  local marker_line
  local marker_bytes
  local marker_sha256

  marker_count=$(grep -Ec '^PR_AGENT_CLEAN_BASE_PROBE_PASS ' "$log_file" || true)
  if [[ "$marker_count" != 1 ]]; then
    fail "clean-base probe must emit exactly one success marker"
  fi
  marker_line=$(grep -E '^PR_AGENT_CLEAN_BASE_PROBE_PASS ' "$log_file")
  marker_bytes=${marker_line#* archive_bytes=}
  marker_bytes=${marker_bytes%% *}
  marker_sha256=${marker_line#* archive_sha256=}
  marker_sha256=${marker_sha256%% *}
  if [[ "$marker_bytes" != "$expected_bytes" ]]; then
    fail "clean-base marker archive byte length does not match bundle"
  fi
  if [[ "$marker_sha256" != "$expected_sha256" ]]; then
    fail "clean-base marker archive SHA256 does not match bundle"
  fi
}

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

command -v docker >/dev/null 2>&1 || fail "Docker CLI is required for the Linux amd64 build helper"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || fail "Python 3.12 is required for deterministic archive creation"
[[ -d "$SOURCE_ROOT/pr_agent" ]] || fail "source unavailable: set PR_AGENT_SOURCE_ROOT to the pinned checkout"
[[ -f "$SOURCE_ROOT/pyproject.toml" ]] || fail "source checkout has no pyproject.toml"
git -C "$SOURCE_ROOT" cat-file -e "$SOURCE_COMMIT:LICENSE" 2>/dev/null || fail "pinned source has no LICENSE"
[[ -f "$SCRIPT_DIR/requirements.lock" ]] || fail "dependency lock missing"
[[ -f "$SCRIPT_DIR/config.toml" ]] || fail "trusted config missing"
[[ -f "$ROOT_DIR/scripts/ci/pr_agent_review.py" ]] || fail "adapter input missing"

source_head=$(git -C "$SOURCE_ROOT" rev-parse HEAD 2>/dev/null || true)
[[ "$source_head" == "$SOURCE_COMMIT" ]] || fail "source checkout is not pinned to $SOURCE_COMMIT"
git -C "$SOURCE_ROOT" diff --quiet || fail "source checkout is modified"
grep -Fq "version = \"$SOURCE_VERSION\"" "$SOURCE_ROOT/pyproject.toml" || fail "source version is not $SOURCE_VERSION"

[[ "$PYTHON_IMAGE_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]] || fail "set PR_AGENT_PYTHON_IMAGE_DIGEST to an exact sha256 digest"

docker_context=$(docker context show 2>/dev/null || true)
docker_endpoint=$(docker context inspect "$docker_context" --format '{{(index .Endpoints "docker").Host}}' 2>/dev/null || true)
[[ "$docker_endpoint" == unix:///* ]] || fail "refusing non-local Docker endpoint: ${docker_endpoint:-unknown}"
docker_server=$(docker info --format '{{.OSType}} {{.Architecture}}' 2>/dev/null || true)
[[ "$docker_server" == linux\ * ]] || fail "Docker daemon is not Linux: ${docker_server:-unavailable}"

mkdir -p "$OUTPUT_DIR"
lock_sha256=$(sha256_file "$SCRIPT_DIR/requirements.lock")
bundle="$OUTPUT_DIR/lmdj-pr-agent-linux-amd64-${SOURCE_COMMIT}.tar"
[[ ! -e "$bundle" && ! -e "$bundle.sha256" ]] || fail "refusing to overwrite existing bundle identity: $bundle"
build_log="$OUTPUT_DIR/docker-build.log"
runtime_log="$OUTPUT_DIR/linux-amd64-import.log"
context=$(mktemp -d "${TMPDIR:-/tmp}/lmdj-pr-agent-context.XXXXXX")
extracted=$(mktemp -d "${TMPDIR:-/tmp}/lmdj-pr-agent-extracted.XXXXXX")
container_id=""
cleanup() {
  if [[ -n "$container_id" ]]; then docker rm -f "$container_id" >/dev/null 2>&1 || true; fi
  rm -rf "$context" "$extracted"
}
trap cleanup EXIT

mkdir -p "$context/pr_agent"
git -C "$SOURCE_ROOT" archive \
  --format=tar \
  "$SOURCE_COMMIT" \
  pr_agent LICENSE | tar -x -C "$context"
cp "$SCRIPT_DIR/requirements.lock" "$context/requirements.lock"
cp "$SCRIPT_DIR/config.toml" "$context/config.toml"
cp "$ROOT_DIR/scripts/ci/pr_agent_review.py" "$context/pr_agent_review.py"
license_sha256=$(sha256_file "$context/LICENSE")
source_tree_sha256=$("$PYTHON_BIN" - "$context" <<'PY'
import hashlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
entries = []
for candidate in (root / "LICENSE", root / "pr_agent"):
    if not candidate.exists() or candidate.is_symlink():
        raise SystemExit("source identity includes a missing or symlinked path")
    paths = [candidate] if candidate.is_file() else sorted(candidate.rglob("*"))
    for path in paths:
        if path.is_symlink():
            raise SystemExit("source identity cannot omit symlinked source bytes")
        if path.is_dir() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if not path.is_file():
            raise SystemExit("source identity contains an unsupported entry")
        data = path.read_bytes()
        relative = path.relative_to(root).as_posix()
        entries.append(f"{relative}\0{len(data)}\0".encode("utf-8") + data)
if not entries:
    raise SystemExit("source tree has no regular files")
print(hashlib.sha256(b"".join(entries)).hexdigest())
PY
)
[[ "$source_tree_sha256" == "$EXPECTED_SOURCE_TREE_SHA256" ]] || fail "source tree digest is not the independently pinned content identity"
cat > "$context/IDENTITY" <<EOF
schema=lmdj.pr-agent-bundle.v1
source_commit=$SOURCE_COMMIT
source_version=$SOURCE_VERSION
platform=linux/amd64
python=3.12
base_image=$PYTHON_IMAGE
base_image_digest=$PYTHON_IMAGE_DIGEST
requirements_lock_sha256=$lock_sha256
upstream_license_sha256=$license_sha256
source_tree_sha256=$source_tree_sha256
EOF

image="lmdj-pr-agent-build:${SOURCE_COMMIT}"
{
  echo "docker_context=$docker_context"
  echo "docker_endpoint=$docker_endpoint"
  echo "docker_server=$docker_server"
  echo "docker_image=$PYTHON_IMAGE@$PYTHON_IMAGE_DIGEST"
  echo "source_commit=$SOURCE_COMMIT"
  echo "requirements_lock_sha256=$lock_sha256"
  echo "upstream_license_sha256=$license_sha256"
  echo "source_tree_sha256=$source_tree_sha256"
  echo "command=docker build --platform linux/amd64 --build-arg PYTHON_IMAGE=$PYTHON_IMAGE --build-arg PYTHON_IMAGE_DIGEST=$PYTHON_IMAGE_DIGEST --build-arg PR_AGENT_SOURCE_COMMIT=$SOURCE_COMMIT --build-arg PR_AGENT_VERSION=$SOURCE_VERSION -f $SCRIPT_DIR/Dockerfile -t $image $context"
} > "$build_log"
docker build --platform linux/amd64 \
  --build-arg "PYTHON_IMAGE=$PYTHON_IMAGE" \
  --build-arg "PYTHON_IMAGE_DIGEST=$PYTHON_IMAGE_DIGEST" \
  --build-arg "PR_AGENT_SOURCE_COMMIT=$SOURCE_COMMIT" \
  --build-arg "PR_AGENT_VERSION=$SOURCE_VERSION" \
  -f "$SCRIPT_DIR/Dockerfile" -t "$image" "$context" >> "$build_log" 2>&1

image_platform=$(docker image inspect "$image" --format '{{.Os}}/{{.Architecture}}')
[[ "$image_platform" == linux/amd64 ]] || fail "built image platform is $image_platform, expected linux/amd64"
docker run --rm --platform linux/amd64 --entrypoint python "$image" -c \
  'import importlib.metadata, platform, sys; import litellm; from pr_agent.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler; from pr_agent.tools.pr_reviewer import PRReviewer; version = importlib.metadata.version("litellm"); assert sys.version_info[:2] == (3, 12); assert platform.system() == "Linux"; assert platform.machine() == "x86_64"; assert version == "1.100.0"; print(f"python={sys.version.split()[0]} platform={platform.platform()} machine={platform.machine()} litellm={version} PRReviewer={PRReviewer.__module__} LiteLLMAIHandler={LiteLLMAIHandler.__module__}")' \
  > "$runtime_log" 2>&1

container_id=$(docker create --platform linux/amd64 "$image" /bin/true)
docker cp "$container_id:/opt/lmdj/pr-agent/." "$extracted/"
docker rm "$container_id" >/dev/null
container_id=""

if find "$extracted" \( -type l -o -type d -name '__pycache__' -o -type f -name '*.pyc' \) -print -quit | grep -q .; then
  fail "export contains a symlink, __pycache__, or pyc"
fi

"$PYTHON_BIN" - "$extracted" "$bundle" <<'PY'
import sys
import tarfile
from pathlib import Path

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
with tarfile.open(destination, "w", format=tarfile.PAX_FORMAT) as archive:
    paths = sorted(source.rglob("*"), key=lambda path: path.relative_to(source).as_posix())
    paths.insert(0, source / ".")
    for path in paths:
        relative = path.relative_to(source) if path != source / "." else Path(".")
        info = archive.gettarinfo(str(path), arcname=Path("pr-agent") / relative)
        info.uid = 0
        info.gid = 0
        info.uname = ""
        info.gname = ""
        info.mtime = 0
        if info.isfile():
            with path.open("rb") as handle:
                archive.addfile(info, handle)
        else:
            archive.addfile(info)
PY

bundle_bytes=$(wc -c < "$bundle" | tr -d '[:space:]')
bundle_sha256=$(sha256_file "$bundle")
container_id=$(docker create --platform linux/amd64 \
  -i \
  -e LITELLM_LOCAL_MODEL_COST_MAP=true \
  -e "PR_AGENT_EXPECTED_LICENSE_SHA256=$license_sha256" \
  -e "PR_AGENT_EXPECTED_BASE_IMAGE=$PYTHON_IMAGE@$PYTHON_IMAGE_DIGEST" \
  -e "PR_AGENT_EXPECTED_SOURCE_TREE_SHA256=$EXPECTED_SOURCE_TREE_SHA256" \
  -e "PR_AGENT_EXPECTED_BUNDLE_BYTES=$bundle_bytes" \
  -e "PR_AGENT_EXPECTED_BUNDLE_SHA256=$bundle_sha256" \
  --entrypoint sh "$PYTHON_IMAGE@$PYTHON_IMAGE_DIGEST" \
  -c 'apt-get update -qq && apt-get install -y --no-install-recommends git >/dev/null && exec python -')
docker cp "$bundle" "$container_id:/tmp/pr-agent-bundle.tar"
docker start -ai "$container_id" >> "$runtime_log" 2>&1 <<'PY'
import hashlib
import importlib
import importlib.metadata
import os
import pathlib
import sys
import tarfile

bundle_path = pathlib.Path("/tmp/pr-agent-bundle.tar")
expected_bundle_bytes = int(os.environ["PR_AGENT_EXPECTED_BUNDLE_BYTES"])
expected_bundle_sha256 = os.environ["PR_AGENT_EXPECTED_BUNDLE_SHA256"]
assert bundle_path.is_file()
actual_bundle_bytes = bundle_path.stat().st_size
actual_bundle_digest = hashlib.sha256()
with bundle_path.open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        actual_bundle_digest.update(chunk)
actual_bundle_sha256 = actual_bundle_digest.hexdigest()
assert actual_bundle_bytes == expected_bundle_bytes
assert actual_bundle_sha256 == expected_bundle_sha256
root = pathlib.Path("/tmp/exported")
root.mkdir()
with tarfile.open(bundle_path) as archive:
    archive.extractall(root)
artifact = (root / "pr-agent").resolve()
identity = dict(
    line.split("=", 1)
    for line in (artifact / "IDENTITY").read_text(encoding="utf-8").splitlines()
    if line and "=" in line
)
expected_license = os.environ["PR_AGENT_EXPECTED_LICENSE_SHA256"]
expected_base_image = os.environ["PR_AGENT_EXPECTED_BASE_IMAGE"]
expected_source_tree = os.environ["PR_AGENT_EXPECTED_SOURCE_TREE_SHA256"]
assert os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] == "true"
sys.dont_write_bytecode = True
assert not any(path.is_symlink() for path in artifact.rglob("*"))
assert identity["schema"] == "lmdj.pr-agent-bundle.v1"
assert identity["source_commit"] == "53072488e4c3b5a6c9ae730fe6fb52fc5f09d06c"
assert identity["source_version"] == "0.45.0"
assert f"{identity['base_image']}@{identity['base_image_digest']}" == expected_base_image
assert identity["source_tree_sha256"] == expected_source_tree == "65af56f5627de2f42cd1de278321241dac2f54bdcfa596d3dc7a380ada534abf"
assert hashlib.sha256((artifact / "LICENSE").read_bytes()).hexdigest() == expected_license == identity["upstream_license_sha256"]
entries = [
    f"{path.relative_to(artifact).as_posix()}\0{len(path.read_bytes())}\0".encode("utf-8") + path.read_bytes()
    for candidate in (artifact / "LICENSE", artifact / "pr_agent")
    if candidate.exists()
    for path in ([candidate] if candidate.is_file() else sorted(candidate.rglob("*")))
    if not path.is_symlink() and path.is_file()
]
assert hashlib.sha256(b"".join(entries)).hexdigest() == identity["source_tree_sha256"]
sys.path.insert(0, str(artifact / "vendor"))
sys.path.insert(1, str(artifact))
import httpx

httpx_get_calls = []
def forbidden_get(url, *args, **kwargs):
    httpx_get_calls.append({"url": url, "timeout": kwargs.get("timeout")})
    raise AssertionError("LiteLLM attempted mutable model metadata HTTP")

httpx.get = forbidden_get
pr_agent = importlib.import_module("pr_agent")
litellm = importlib.import_module("litellm")
from litellm.litellm_core_utils.get_model_cost_map import get_model_cost_map_source_info

model_cost_info = get_model_cost_map_source_info()
handler_module = importlib.import_module("pr_agent.algo.ai_handlers.litellm_ai_handler")
reviewer_module = importlib.import_module("pr_agent.tools.pr_reviewer")
LiteLLMAIHandler = handler_module.LiteLLMAIHandler
PRReviewer = reviewer_module.PRReviewer
version = importlib.metadata.version("litellm")
assert version == "1.100.0"
assert PRReviewer.__module__ == "pr_agent.tools.pr_reviewer"
assert LiteLLMAIHandler.__module__ == "pr_agent.algo.ai_handlers.litellm_ai_handler"
assert httpx_get_calls == []
assert model_cost_info["source"] == "local"
assert model_cost_info["is_env_forced"] is True
assert model_cost_info["url"] is None
assert len(litellm.model_cost) > 0
modules = (pr_agent, litellm, handler_module, reviewer_module)
assert all(pathlib.Path(module.__file__).resolve().is_relative_to(artifact) for module in modules)
assert not any(path.is_symlink() or path.is_dir() and path.name == "__pycache__" or path.is_file() and path.suffix == ".pyc" for path in artifact.rglob("*"))
print(f"PR_AGENT_CLEAN_BASE_PROBE_PASS archive_bytes={actual_bundle_bytes} archive_sha256={actual_bundle_sha256} source_tree={identity['source_tree_sha256']} license={expected_license} clean_base={expected_base_image} litellm={version} model_cost_source={model_cost_info['source']} httpx_get_calls={len(httpx_get_calls)} PRReviewer={PRReviewer.__module__} LiteLLMAIHandler={LiteLLMAIHandler.__module__}")
PY

require_clean_base_marker "$runtime_log" "$bundle_bytes" "$bundle_sha256"
if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "$bundle" > "$bundle.sha256"
else
  shasum -a 256 "$bundle" > "$bundle.sha256"
fi
printf 'bundle=%s\n' "$bundle"
cat "$bundle.sha256"
