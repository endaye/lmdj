#!/usr/bin/env bash
# 把项目打包成可分享的 zip：排除虚拟环境、输出、素材、缓存。
# 用法: bash make_share_zip.sh  →  生成 ../lmdj-song-pipeline-share.zip
set -e
cd "$(dirname "$0")"
OUT="../lmdj-song-pipeline-share.zip"
rm -f "$OUT"
zip -r "$OUT" . \
  -x '.venv/*' \
  -x 'output/*' \
  -x 'input_*/*' \
  -x '_*/*' \
  -x '*/__pycache__/*' \
  -x '.pytest_cache/*' \
  -x '*.pyc' \
  -x '.git/*' \
  -x '*.egg-info/*' \
  -x '*.DS_Store' >/dev/null
echo "打包完成: $OUT"
unzip -Z1 "$OUT" | grep -vE '__pycache__|\.pyc' | sort
