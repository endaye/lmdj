#!/usr/bin/env bash
# LMDJ dev helper — 在仓库任意位置执行均可，操作以仓库根目录为准。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORE="$ROOT/packages/core-models"
PATCHIFY="$ROOT/packages/patchify"
DEMO="$ROOT/references/demos/lmdj-song-pipeline"
TESTSONG="$DEMO/output/testsong"
WORKER="$ROOT/workers/audio"
PFS_VENV="$WORKER/.venv-pfs"
SEP_DEMUCS_VENV="$WORKER/.venv-sep-demucs"
SEP_SCNET_VENV="$WORKER/.venv-sep-scnet"
SEP_BSROF_VENV="$WORKER/.venv-sep-bs-roformer"
SEP_MELROF_VENV="$WORKER/.venv-sep-mel-roformer"
MSST_DIR="$WORKER/.msst"
CONSTRAINTS="$WORKER/config/parity-constraints.txt"

usage() {
  cat <<'EOF'
LMDJ dev helper

用法: scripts/dev.sh <command>

  setup              创建/补齐 packages 的 venv（core-models + patchify），幂等
  setup-demo         创建参考 demo 的 venv（重依赖 demucs/torch，首次下载很大）
  setup-pfs          创建 pipeline-from-stems venv（librosa 等 DSP 栈，constraints 锁版本）
  setup-sep-demucs   创建 HT Demucs runner venv（torch 栈，constraints 锁版本）
  setup-sep-scnet    创建 SCNet runner venv + MSST pinned clone
  setup-sep-bs-roformer  创建 BS-RoFormer runner venv（复用 MSST clone/constraints）
  setup-sep-mel-roformer 创建 Mel-Band RoFormer runner venv（复用 MSST clone/constraints）
  separate <id> <audio> [device]   跑单个 separator smoke（默认 mps）
  bench --dataset M.json --separators a,b --device mps   benchmark 执行层（data root 默认 testdata/audio）
  bench-report --run DIR [--run DIR2] ...   聚合 benchmark run，产出 summary.json/csv + 对齐文本表（spec §9）
  bench-listen --run DIR [--no-stems]       把一个 run 的 completed 组合打包成匿名盲听样本（spec §8/§9.3）
  parity             frozen-stems parity 门槛：旧 demo pipeline vs PipelineFromStems（spec §3.2）
  test               跑两个 package 的全部测试（25 个）
  patchify <dir>...  对一个 pipeline package 目录生成 patch.json（参数透传 CLI）
  song <audio> <id>  用 demo pipeline 处理一首歌并 patchify（需先 setup-demo）
  smoke              端到端冒烟：testsong → patch.json → 摘要（testsong 缺失时自动生成）
  creator-smoke <audio>  API 全链路：上传、16-Pad 校验、两次确定性 Export
  all                setup + test + smoke
EOF
}

ensure_pkg_venvs() {
  if [ ! -x "$CORE/.venv/bin/python" ]; then
    echo "==> 创建 core-models venv"
    python3 -m venv "$CORE/.venv"
    "$CORE/.venv/bin/pip" -q install -e "$CORE[test]"
  fi
  if [ ! -x "$PATCHIFY/.venv/bin/python" ]; then
    echo "==> 创建 patchify venv"
    python3 -m venv "$PATCHIFY/.venv"
    "$PATCHIFY/.venv/bin/pip" -q install -e "$CORE"
    "$PATCHIFY/.venv/bin/pip" -q install -e "$PATCHIFY[test]"
  fi
}

ensure_demo_venv() {
  if [ ! -x "$DEMO/.venv/bin/song-pipeline" ]; then
    echo "demo venv 不存在，先运行: scripts/dev.sh setup-demo" >&2
    exit 1
  fi
}

cmd_setup() {
  ensure_pkg_venvs
  echo "==> packages venv 就绪"
}

cmd_setup_demo() {
  if [ ! -x "$DEMO/.venv/bin/python" ]; then
    echo "==> 创建 demo venv（demucs/torch，可能需要 10 分钟以上）"
    python3 -m venv "$DEMO/.venv"
  fi
  "$DEMO/.venv/bin/pip" -q install -e "$DEMO" -c "$CONSTRAINTS"
  echo "==> demo venv 就绪"
}

cmd_test() {
  ensure_pkg_venvs
  echo "==> core-models"
  "$CORE/.venv/bin/python" -m pytest "$CORE/tests" -q
  echo "==> patchify"
  "$PATCHIFY/.venv/bin/python" -m pytest "$PATCHIFY/tests" -q
}

cmd_patchify() {
  [ $# -ge 1 ] || { echo "用法: scripts/dev.sh patchify <package_dir> [--out PATH]" >&2; exit 1; }
  ensure_pkg_venvs
  "$PATCHIFY/.venv/bin/lmdj-patchify" "$@"
}

cmd_song() {
  [ $# -eq 2 ] || { echo "用法: scripts/dev.sh song <audio_file> <song_id>" >&2; exit 1; }
  local audio="$1" song_id="$2"
  ensure_demo_venv
  ensure_pkg_venvs
  echo "==> demo pipeline 处理（分轨较慢）"
  (cd "$DEMO" && .venv/bin/song-pipeline run "$audio" --song-id "$song_id" --fast)
  echo "==> patchify"
  "$PATCHIFY/.venv/bin/lmdj-patchify" "$DEMO/output/$song_id"
  summarize "$DEMO/output/$song_id/patch.json"
}

cmd_smoke() {
  ensure_pkg_venvs
  ensure_testsong
  "$PATCHIFY/.venv/bin/lmdj-patchify" "$TESTSONG"
  summarize "$TESTSONG/patch.json"
}

cmd_creator_smoke() {
  [ $# -eq 1 ] || {
    echo "用法: scripts/dev.sh creator-smoke <audio>" >&2
    exit 1
  }
  [ -f "$1" ] || {
    echo "音频不存在: $1" >&2
    exit 1
  }
  ensure_pkg_venvs

  local audio="$1"
  local api_base="${LMDJ_API_BASE_URL:-http://127.0.0.1:8000}"
  local poll_interval="${LMDJ_CREATOR_SMOKE_POLL_INTERVAL_SECONDS:-1}"
  local connect_timeout="${LMDJ_CREATOR_SMOKE_CONNECT_TIMEOUT_SECONDS:-5}"
  local request_timeout="${LMDJ_CREATOR_SMOKE_REQUEST_TIMEOUT_SECONDS:-120}"
  local timeout_seconds="${LMDJ_CREATOR_SMOKE_TIMEOUT_SECONDS:-1800}"
  local timeout_value
  for timeout_value in "$connect_timeout" "$request_timeout" "$timeout_seconds"; do
    case "$timeout_value" in
      ""|0|*[!0-9]*)
        echo "Creator smoke timeouts must be positive integer seconds" >&2
        return 1
        ;;
    esac
  done
  api_base="${api_base%/}"
  CREATOR_SMOKE_TMP="$(mktemp -d)"
  trap 'rm -rf "${CREATOR_SMOKE_TMP:-}"' EXIT

  local upload_json="$CREATOR_SMOKE_TMP/upload.json"
  local status_json="$CREATOR_SMOKE_TMP/status.json"
  local patch_json="$CREATOR_SMOKE_TMP/patch.json"
  local export_a="$CREATOR_SMOKE_TMP/export-a.zip"
  local export_b="$CREATOR_SMOKE_TMP/export-b.zip"

  curl --silent --show-error --fail-with-body \
    --connect-timeout "$connect_timeout" \
    --max-time "$request_timeout" \
    --form "file=@${audio}" \
    --output "$upload_json" \
    "$api_base/uploads"

  local job_id
  job_id=$(
    "$CORE/.venv/bin/python" - "$upload_json" <<'EOF'
import json
import sys

with open(sys.argv[1]) as handle:
    body = json.load(handle)
job_id = body.get("job_id")
if not isinstance(job_id, str) or not job_id:
    raise SystemExit("upload response missing job_id")
print(job_id)
EOF
  )

  local state=""
  local poll_started_at poll_deadline now remaining status_max_time
  poll_started_at="$(date +%s)"
  poll_deadline="$((poll_started_at + timeout_seconds))"
  while :; do
    now="$(date +%s)"
    remaining="$((poll_deadline - now))"
    if [ "$remaining" -le 0 ]; then
      echo "Creator job timed out after ${timeout_seconds}s: $job_id" >&2
      return 1
    fi
    status_max_time="$request_timeout"
    if [ "$remaining" -lt "$status_max_time" ]; then
      status_max_time="$remaining"
    fi
    curl --silent --show-error --fail-with-body \
      --connect-timeout "$connect_timeout" \
      --max-time "$status_max_time" \
      --output "$status_json" \
      "$api_base/jobs/$job_id"
    state=$(
      "$CORE/.venv/bin/python" - "$status_json" <<'EOF'
import json
import sys

with open(sys.argv[1]) as handle:
    body = json.load(handle)
state = body.get("state")
if not isinstance(state, str):
    raise SystemExit("job status response missing state")
print(state)
EOF
    )
    case "$state" in
      completed) break ;;
      failed|cancelled)
        echo "Creator job $state: $job_id" >&2
        return 1
        ;;
      queued|generating|separating|extracting|patchifying|rendering)
        sleep "$poll_interval"
        ;;
      *)
        echo "Unknown Creator job state: $state" >&2
        return 1
        ;;
    esac
  done

  curl --silent --show-error --fail-with-body \
    --connect-timeout "$connect_timeout" \
    --max-time "$request_timeout" \
    --output "$patch_json" \
    "$api_base/jobs/$job_id/patch"

  local patch_summary
  patch_summary=$(
    "$CORE/.venv/bin/python" - "$patch_json" <<'EOF'
import json
import sys

import jsonschema

from lmdj_core_models.model import load_patch_schema

with open(sys.argv[1]) as handle:
    patch = json.load(handle)
jsonschema.validate(patch, load_patch_schema())
expected = list(range(16))
if [pad.get("index") for pad in patch["pads"]] != expected:
    raise SystemExit("patch pads must be ordered with indexes 0..15")
for scene in patch["scenes"]:
    if scene.get("pad_indexes") != expected:
        raise SystemExit(
            f"scene {scene.get('scene_id', '<unknown>')} must cover indexes 0..15"
        )
patch_id = patch.get("patch_id")
if not isinstance(patch_id, str) or not patch_id:
    raise SystemExit("patch response missing patch_id")
print(f"{patch_id}\t{len(patch['pads'])}")
EOF
  )
  local patch_id pad_count
  IFS=$'\t' read -r patch_id pad_count <<<"$patch_summary"

  curl --silent --show-error --fail-with-body \
    --connect-timeout "$connect_timeout" \
    --max-time "$request_timeout" \
    --output "$export_a" \
    "$api_base/jobs/$job_id/export"
  curl --silent --show-error --fail-with-body \
    --connect-timeout "$connect_timeout" \
    --max-time "$request_timeout" \
    --output "$export_b" \
    "$api_base/jobs/$job_id/export"

  local export_sha256_a export_sha256_b
  export_sha256_a=$(
    "$CORE/.venv/bin/python" - "$export_a" <<'EOF'
import hashlib
import sys

with open(sys.argv[1], "rb") as handle:
    print(hashlib.file_digest(handle, "sha256").hexdigest())
EOF
  )
  export_sha256_b=$(
    "$CORE/.venv/bin/python" - "$export_b" <<'EOF'
import hashlib
import sys

with open(sys.argv[1], "rb") as handle:
    print(hashlib.file_digest(handle, "sha256").hexdigest())
EOF
  )
  if [ "$export_sha256_a" != "$export_sha256_b" ]; then
    echo "Creator exports are not deterministic for job $job_id" >&2
    return 1
  fi

  printf 'job_id: %s\n' "$job_id"
  printf 'patch_id: %s\n' "$patch_id"
  printf 'pads: %s\n' "$pad_count"
  printf 'export_sha256_a: %s\n' "$export_sha256_a"
  printf 'export_sha256_b: %s\n' "$export_sha256_b"
  printf 'deterministic: yes\n'
}

cmd_setup_pfs() {
  if [ ! -x "$PFS_VENV/bin/python" ]; then
    echo "==> 创建 pipeline-from-stems venv"
    python3 -m venv "$PFS_VENV"
  fi
  # lmdj_audio_worker/__init__.py 会 import job -> lmdj_patchify，
  # 所以 pfs venv 也要装两个轻量 path dep（顺序：core-models 先）
  "$PFS_VENV/bin/pip" -q install -e "$CORE" -c "$CONSTRAINTS"
  "$PFS_VENV/bin/pip" -q install -e "$PATCHIFY" -c "$CONSTRAINTS"
  "$PFS_VENV/bin/pip" -q install -e "$WORKER[pfs]" -c "$CONSTRAINTS"
  echo "==> pfs venv 就绪"
}

cmd_setup_sep_demucs() {
  if [ ! -x "$SEP_DEMUCS_VENV/bin/python" ]; then
    echo "==> 创建 demucs runner venv"
    python3 -m venv "$SEP_DEMUCS_VENV"
  fi
  "$SEP_DEMUCS_VENV/bin/pip" -q install -e "$CORE" -c "$WORKER/config/runner-demucs-constraints.txt"
  "$SEP_DEMUCS_VENV/bin/pip" -q install -e "$PATCHIFY" -c "$WORKER/config/runner-demucs-constraints.txt"
  "$SEP_DEMUCS_VENV/bin/pip" -q install -e "$WORKER" demucs soundfile -c "$WORKER/config/runner-demucs-constraints.txt"
  echo "==> demucs runner venv 就绪"
}

ensure_msst_clone() {
  local lock="$WORKER/config/msst.lock"
  local url commit
  url=$(grep '^url=' "$lock" | cut -d= -f2-)
  commit=$(grep '^commit=' "$lock" | cut -d= -f2-)
  if [ ! -d "$MSST_DIR/.git" ]; then
    echo "==> clone MSST @ ${commit}"
    git clone --no-checkout "$url" "$MSST_DIR"
  fi
  (cd "$MSST_DIR" && git fetch -q origin "$commit" && git checkout -q "$commit")
}

setup_msst_family_venv() {
  local venv="$1"
  if [ ! -x "$venv/bin/python" ]; then
    echo "==> 创建 $(basename "$venv")"
    python3 -m venv "$venv"
  fi
  "$venv/bin/pip" -q install -e "$CORE" -c "$WORKER/config/runner-scnet-constraints.txt"
  "$venv/bin/pip" -q install -e "$PATCHIFY" -c "$WORKER/config/runner-scnet-constraints.txt"
  grep -v '^#' "$WORKER/config/runner-scnet-constraints.txt" | sed '/^$/d' > /tmp/msst-reqs.txt
  "$venv/bin/pip" -q install -e "$WORKER" -r /tmp/msst-reqs.txt
}

cmd_setup_sep_scnet() {
  local lock="$WORKER/config/msst.lock"
  local commit
  commit=$(grep '^commit=' "$lock" | cut -d= -f2-)
  ensure_msst_clone
  setup_msst_family_venv "$SEP_SCNET_VENV"
  echo "==> scnet runner venv 就绪（MSST @ ${commit}）"
}

cmd_setup_sep_bs_roformer() {
  ensure_msst_clone
  setup_msst_family_venv "$SEP_BSROF_VENV"
  echo "==> bs-roformer runner venv 就绪"
}

cmd_setup_sep_mel_roformer() {
  ensure_msst_clone
  setup_msst_family_venv "$SEP_MELROF_VENV"
  echo "==> mel-roformer runner venv 就绪"
}

ensure_testsong() {
  if [ ! -f "$TESTSONG/lanes.json" ]; then
    ensure_demo_venv
    echo "==> 生成 testsong（合成曲，stems 预置，跳过 demucs）"
    (cd "$DEMO" && .venv/bin/python scripts/make_test_song.py output/testsong \
      && .venv/bin/song-pipeline run output/testsong/input.wav --song-id testsong --fast)
  fi
}

cmd_parity() {
  ensure_demo_venv
  ensure_pkg_venvs
  [ -x "$PFS_VENV/bin/python" ] || { echo "先运行: scripts/dev.sh setup-pfs" >&2; exit 1; }
  ensure_testsong

  echo "==> 环境指纹校验（不符即中止，spec §3.2）"
  "$PFS_VENV/bin/python" -m lmdj_audio_worker.envcheck \
    "$DEMO/.venv" "$PFS_VENV" --constraints "$CONSTRAINTS"

  local tmp; tmp="$(mktemp -d)"
  echo "==> 旧 pipeline（demo venv，cached stems 跳过 demucs）"
  mkdir -p "$tmp/old/parity/stems"
  cp "$TESTSONG/stems/"*.wav "$tmp/old/parity/stems/"
  (cd "$DEMO" && .venv/bin/song-pipeline run "$TESTSONG/input.wav" \
    --out "$tmp/old" --song-id parity --fast)

  echo "==> 新 PipelineFromStems（pfs venv，同一组 stems）"
  "$PFS_VENV/bin/python" -m lmdj_audio_worker.pipeline_from_stems \
    --stems "$tmp/old/parity/stems" --out "$tmp/new" --song-id parity

  echo "==> parity 比较"
  "$PFS_VENV/bin/python" -m lmdj_audio_worker.pipeline_from_stems.parity \
    "$tmp/old/parity" "$tmp/new/parity"

  echo "==> Patchify 两侧 + patch_id 一致性"
  "$PATCHIFY/.venv/bin/lmdj-patchify" "$tmp/old/parity"
  "$PATCHIFY/.venv/bin/lmdj-patchify" "$tmp/new/parity"
  "$PATCHIFY/.venv/bin/python" - "$tmp/old/parity/patch.json" "$tmp/new/parity/patch.json" <<'EOF'
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
assert a["patch_id"] == b["patch_id"], f"patch_id 不一致: {a['patch_id']} vs {b['patch_id']}"
print(f"patch_id 一致: {a['patch_id']}")
EOF
  echo "==> parity PASS（临时输出保留在 ${tmp}）"
}

summarize() {
  "$PATCHIFY/.venv/bin/python" - "$1" <<'EOF'
import json, sys
data = json.load(open(sys.argv[1]))
print(f"patch_id : {data['patch_id']}")
print(f"bpm      : {data['bpm']} | loop: {data['loop_seconds']}s")
print("pads     :")
for p in data["pads"]:
    print(f"  [{p['index']}] {p['slot']:<14} {p['action']:<16} -> {p['element_id'] or '-'}")
print(f"pattern  : {len(data['patterns'][0]['notes'])} notes / {data['patterns'][0]['length_steps']} steps")
print(f"elements : {[e['name'] for e in data['elements']]}")
print(f"unmapped : {data['metadata']['unmapped_element_ids']}")
EOF
}

cmd_separate() {
  [ $# -ge 2 ] || { echo "用法: scripts/dev.sh separate <id> <audio> [device]" >&2; exit 1; }
  (cd "$ROOT" && "$WORKER/.venv/bin/python" -m lmdj_audio_worker.separation.smoke \
    --id "$1" --input "$2" --device "${3:-mps}")
}

cmd_bench() {
  (cd "$ROOT" && LMDJ_BENCH_DATA_ROOT="${LMDJ_BENCH_DATA_ROOT:-$ROOT/testdata/audio}" \
    "$WORKER/.venv/bin/python" -m lmdj_audio_worker.cli benchmark "$@")
}

cmd_bench_report() {
  [ $# -ge 1 ] || { echo "用法: scripts/dev.sh bench-report --run DIR [--run DIR2] [--listening-scores F] [--attestations F] [--out DIR]" >&2; exit 1; }
  (cd "$ROOT" && "$WORKER/.venv/bin/python" -m lmdj_audio_worker.cli report "$@")
}

cmd_bench_listen() {
  [ $# -ge 1 ] || { echo "用法: scripts/dev.sh bench-listen --run DIR [--no-stems]" >&2; exit 1; }
  (cd "$ROOT" && "$WORKER/.venv/bin/python" -m lmdj_audio_worker.cli listening-package "$@")
}

cmd="${1:-}"
[ -n "$cmd" ] && shift || true
case "$cmd" in
  setup)           cmd_setup ;;
  setup-demo)      cmd_setup_demo ;;
  setup-pfs)       cmd_setup_pfs ;;
  setup-sep-demucs) cmd_setup_sep_demucs ;;
  setup-sep-scnet) cmd_setup_sep_scnet ;;
  setup-sep-bs-roformer) cmd_setup_sep_bs_roformer ;;
  setup-sep-mel-roformer) cmd_setup_sep_mel_roformer ;;
  separate)        cmd_separate "$@" ;;
  bench)           cmd_bench "$@" ;;
  bench-report)    cmd_bench_report "$@" ;;
  bench-listen)    cmd_bench_listen "$@" ;;
  parity)          cmd_parity ;;
  test)            cmd_test ;;
  patchify)        cmd_patchify "$@" ;;
  song)            cmd_song "$@" ;;
  smoke)           cmd_smoke ;;
  creator-smoke)   cmd_creator_smoke "$@" ;;
  all)             cmd_setup; cmd_test; cmd_smoke ;;
  ""|-h|--help|help) usage ;;
  *)               echo "未知命令: $cmd" >&2; usage; exit 1 ;;
esac
