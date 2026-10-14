#!/usr/bin/env bash
# Separate conformance candidate. This never changes ordinary Creator proof selection.
set -euo pipefail
umask 077

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "$script_dir/.." && pwd -P)"
io_root="$repo_root/build/web/creator-count-in-io"
web_root="$repo_root/tests/platform/web"
run_root=""
server_pid=""
ready_root=""

cleanup() {
  local status=$?
  trap - EXIT
  if [[ -n "$server_pid" ]]; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
  if [[ -n "$ready_root" ]]; then
    case "$ready_root" in
      "${TMPDIR:-/tmp}"/lmdj-creator-count-in-io.*)
        python3 - "$ready_root" <<'PY'
import pathlib, shutil, sys
path = pathlib.Path(sys.argv[1])
if path.is_symlink() or not path.name.startswith("lmdj-creator-count-in-io."):
    raise SystemExit("unsafe owned readiness cleanup")
shutil.rmtree(path)
PY
        ;;
      *) echo "unsafe owned readiness cleanup: $ready_root" >&2; status=2 ;;
    esac
  fi
  if [[ -n "$run_root" ]]; then
    python3 - "$run_root" "$status" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
code = int(sys.argv[2])
(root / "result.json").write_text(json.dumps({
    "scope": "separate Creator production-controller OPFS conformance candidate",
    "ordinary_creator_acceptance": "not established by this entrypoint",
    "exit_code": code, "status": "passed" if code == 0 else "failed",
}, sort_keys=True) + "\n", encoding="utf-8")
PY
    echo "Creator count-in I/O proof artifacts: $run_root (exit $status)"
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

[[ $# == 1 && "$1" == proof ]] || {
  echo "usage: scripts/creator-count-in-io-proof.sh proof" >&2
  exit 2
}

# Keep the ordinary packager's clean-source requirement, including untracked files.
[[ -z "$(git -C "$repo_root" status --porcelain=v1 --untracked-files=all)" ]] || {
  echo "Creator count-in I/O proof requires a clean committed candidate" >&2
  exit 2
}
candidate_head="$(git -C "$repo_root" rev-parse HEAD)"
python3 - "$repo_root" "$io_root" <<'PY'
import pathlib, sys
repo, target = map(pathlib.Path, sys.argv[1:])
if target.resolve() != repo / "build/web/creator-count-in-io":
    raise SystemExit("unsafe conformance build root")
for path in (target, target / "cmake", target / "runtime", target / "runs"):
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise SystemExit(f"unsafe conformance directory: {path}")
target.joinpath("runs").mkdir(parents=True, exist_ok=True)
PY
run_root="$(mktemp -d "$io_root/runs/candidate.XXXXXX")"
echo "Creator count-in I/O proof artifacts: $run_root"

if [[ -z "${EMSDK:-}" && -f "$repo_root/build/toolchains/emsdk/emsdk_env.sh" ]]; then
  export EMSDK="$repo_root/build/toolchains/emsdk"
fi
[[ -n "${EMSDK:-}" && -f "$EMSDK/emsdk_env.sh" ]] || {
  echo "EMSDK is not configured; use the existing pinned SDK" >&2; exit 2;
}
export EMSDK_QUIET=1
# shellcheck disable=SC1090
source "$EMSDK/emsdk_env.sh" >"$run_root/activate-toolchain.log" 2>&1
for command in node python3 emcmake cmake; do
  command -v "$command" >/dev/null || { echo "missing command: $command" >&2; exit 2; }
done
if [[ "$(node -p 'process.versions.node.split(".")[0]')" != "26" ]]; then
  echo "Node 26 is required" >&2
  exit 2
fi
python3 "$repo_root/tools/web-runtime/verify_emscripten.py" >"$run_root/toolchain.log" 2>&1
node --input-type=module - "$web_root" "$repo_root" >"$run_root/browser-identity.json" <<'JS'
import {readFileSync, existsSync} from "node:fs";
import {pathToFileURL} from "node:url";
import {join} from "node:path";
const [web, repo] = process.argv.slice(2);
const installed = JSON.parse(readFileSync(join(web, "node_modules/@playwright/test/package.json")));
const lock = JSON.parse(readFileSync(join(repo, "tools/web-runtime/emscripten.lock.json")));
if (installed.version !== lock.playwright) throw Error("locked Playwright is required");
const {chromium} = await import(pathToFileURL(join(web, "node_modules/@playwright/test/index.mjs")));
const executable = chromium.executablePath();
if (!existsSync(executable)) throw Error("locked full Chromium is missing; this proof never installs browsers");
console.log(JSON.stringify({node: process.version, playwright: installed.version, executable}));
JS

# A stale ON cache must never turn the official ordinary build into conformance.
python3 - "$repo_root/build/web/creator/cmake/CMakeCache.txt" <<'PY'
import pathlib, sys
cache = pathlib.Path(sys.argv[1])
if cache.exists() and "LMDJ_WEB_AUDIO_CONFORMANCE:BOOL=OFF" not in cache.read_text():
    raise SystemExit("ordinary Creator cache must have conformance OFF")
PY
"$repo_root/scripts/creator-web.sh" build >"$run_root/ordinary-creator-build.log" 2>&1
python3 - "$repo_root/build/web/creator/cmake/CMakeCache.txt" <<'PY'
import pathlib, sys
if "LMDJ_WEB_AUDIO_CONFORMANCE:BOOL=OFF" not in pathlib.Path(sys.argv[1]).read_text():
    raise SystemExit("ordinary Creator build did not retain conformance OFF")
PY
emcmake cmake \
  -C "$repo_root/tools/web-runtime/emscripten-threads-cache-init.cmake" \
  -S "$repo_root" -B "$io_root/cmake" -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=OFF -DLMDJ_WEB_AUDIO_CONFORMANCE=ON \
  -DLMDJ_WEB_AUDIO_OUTPUT_DIR="$io_root/runtime" >"$run_root/conformance-configure.log" 2>&1
parallel_args=(--parallel)
if [[ -n "${CMAKE_BUILD_PARALLEL_LEVEL:-}" ]]; then parallel_args+=("$CMAKE_BUILD_PARALLEL_LEVEL"); fi
cmake --build "$io_root/cmake" --target lmdj_web_runtime_host "${parallel_args[@]}" \
  >"$run_root/conformance-build.log" 2>&1
python3 "$repo_root/apps/creator-web/tools/package.py" --repo-root "$repo_root" \
  --ui-root "$repo_root/build/web/creator/ui" --runtime-root "$io_root/runtime" \
  --identity "$repo_root/build/web/toolchain/toolchain-identity.json" \
  --dist-root "$run_root/dist" >"$run_root/package.log" 2>&1
[[ "$(git -C "$repo_root" rev-parse HEAD)" == "$candidate_head" &&
   -z "$(git -C "$repo_root" status --porcelain=v1 --untracked-files=all)" ]] || {
  echo "source candidate changed during the separate build/package" >&2; exit 2;
}

# Bind this exact candidate, official manifest and every complete packaged asset.
python3 - "$repo_root" "$run_root" "$io_root" <<'PY'
import hashlib, json, pathlib, subprocess, sys
repo, run, io = map(pathlib.Path, sys.argv[1:])
manifest = json.loads(run.joinpath("dist/host-manifest.json").read_text())
paths = ["host-manifest.json", "index.html"] + [entry["path"] for entry in manifest["assets"]]
inventory = []
for name in sorted(paths):
    data = run.joinpath("dist", name).read_bytes()
    inventory.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
for name, source in [("toolchain-identity.json", repo / "build/web/toolchain/toolchain-identity.json"),
                     ("conformance-CMakeCache.txt", io / "cmake/CMakeCache.txt")]:
    run.joinpath(name).write_bytes(source.read_bytes())
head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
run.joinpath("artifact-bindings.json").write_text(json.dumps({
    "head": head, "source_status": subprocess.check_output([
        "git", "-C", str(repo), "status", "--porcelain=v1", "--untracked-files=all"], text=True),
    "manifest": manifest, "inventory": inventory,
    "scope": "conformance-only; no ordinary Creator acceptance or Product Build allocation",
}, sort_keys=True, indent=2) + "\n")
PY
ready_root="$(mktemp -d "${TMPDIR:-/tmp}/lmdj-creator-count-in-io.XXXXXX")"
nonce="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
python3 "$repo_root/tools/web-runtime/serve_distribution.py" --root "$run_root/dist" \
  --verifier "$repo_root/apps/creator-web/tools/package.py" --repo-root "$repo_root" \
  --port 0 --ready-file "$ready_root/ready.json" --ready-nonce "$nonce" \
  >"$run_root/server.log" 2>&1 &
server_pid=$!
python3 "$web_root/count_in/fixtures/verify_owned_server.py" \
  "$repo_root" "$run_root" "$ready_root/ready.json" "$server_pid" "$nonce" \
  >"$run_root/server-readiness.log" 2>&1
port="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["port"])' "$ready_root/ready.json")"
LMDJ_CREATOR_COUNT_IN_IO_BASE_URL="http://127.0.0.1:$port" \
LMDJ_CREATOR_COUNT_IN_IO_ARTIFACT_ROOT="$run_root" \
  node "$web_root/node_modules/@playwright/test/cli.js" test \
  --config "$web_root/count_in/fixtures/playwright.config.mjs" \
  --project=creator-count-in-io-chromium --workers=1 \
  "$web_root/count_in/creator_count_in_opfs.spec.mjs" \
  >"$run_root/playwright.log" 2>&1
