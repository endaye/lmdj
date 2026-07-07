#!/usr/bin/env bash
# LMDJ dev helper — 在仓库任意位置执行均可，操作以仓库根目录为准。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORE="$ROOT/packages/core-models"
PATCHIFY="$ROOT/packages/patchify"
DEMO="$ROOT/references/demos/lmdj-song-pipeline"
TESTSONG="$DEMO/output/testsong"

usage() {
  cat <<'EOF'
LMDJ dev helper

用法: scripts/dev.sh <command>

  setup              创建/补齐 packages 的 venv（core-models + patchify），幂等
  setup-demo         创建参考 demo 的 venv（重依赖 demucs/torch，首次下载很大）
  test               跑两个 package 的全部测试（23 个）
  patchify <dir>...  对一个 pipeline package 目录生成 patch.json（参数透传 CLI）
  song <audio> <id>  用 demo pipeline 处理一首歌并 patchify（需先 setup-demo）
  smoke              端到端冒烟：testsong → patch.json → 摘要（testsong 缺失时自动生成）
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
  "$DEMO/.venv/bin/pip" -q install -e "$DEMO"
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
  if [ ! -f "$TESTSONG/lanes.json" ]; then
    ensure_demo_venv
    echo "==> 生成 testsong（合成曲，stems 预置，跳过 demucs）"
    (cd "$DEMO" && .venv/bin/python scripts/make_test_song.py output/testsong \
      && .venv/bin/song-pipeline run output/testsong/input.wav --song-id testsong --fast)
  fi
  "$PATCHIFY/.venv/bin/lmdj-patchify" "$TESTSONG"
  summarize "$TESTSONG/patch.json"
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

cmd="${1:-}"
[ -n "$cmd" ] && shift || true
case "$cmd" in
  setup)      cmd_setup ;;
  setup-demo) cmd_setup_demo ;;
  test)       cmd_test ;;
  patchify)   cmd_patchify "$@" ;;
  song)       cmd_song "$@" ;;
  smoke)      cmd_smoke ;;
  all)        cmd_setup; cmd_test; cmd_smoke ;;
  ""|-h|--help|help) usage ;;
  *)          echo "未知命令: $cmd" >&2; usage; exit 1 ;;
esac
