#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PUBLISHER="$(cd "$SCRIPT_DIR/.." && pwd)/publish-staging-release.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FAKE_BIN="$TMP/bin"
GH_STATE="$TMP/gh-state"
GH_LOG="$TMP/gh.log"
mkdir -p "$FAKE_BIN" "$GH_STATE"

cat > "$FAKE_BIN/gh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

printf 'gh %s\n' "$*" >> "$FAKE_GH_LOG"
test "${1:-}" = "release"
action="${2:-}"
tag="${3:-}"
shift 3
release_dir="$FAKE_GH_STATE/$tag"

option_value() {
  local wanted="$1"
  shift
  while [ "$#" -gt 0 ]; do
    if [ "$1" = "$wanted" ]; then
      printf '%s\n' "$2"
      return 0
    fi
    shift
  done
  return 1
}

case "$action" in
  view)
    test -f "$release_dir/body" || exit 1
    json="$(option_value --json "$@")"
    if [ "$json" = "body" ]; then
      cat "$release_dir/body"
    elif [ "$json" = "assets" ]; then
      if [ -d "$release_dir/assets" ]; then
        find "$release_dir/assets" -maxdepth 1 -type f -exec basename {} \; | sort
      fi
    else
      echo "unsupported view JSON: $json" >&2
      exit 2
    fi
    ;;
  create)
    asset_file=""
    if [[ "${1:-}" != --* ]]; then
      asset_file="$1"
      shift
    fi
    notes_file="$(option_value --notes-file "$@")"
    mkdir -p "$release_dir/assets"
    cp "$notes_file" "$release_dir/body"
    if [ -n "$asset_file" ]; then
      cp "$asset_file" "$release_dir/assets/$(basename "$asset_file")"
    fi
    ;;
  upload)
    source_file="$1"
    test -f "$release_dir/body"
    mkdir -p "$release_dir/assets"
    cp "$source_file" "$release_dir/assets/$(basename "$source_file")"
    ;;
  download)
    pattern="$(option_value --pattern "$@")"
    output_dir="$(option_value --dir "$@")"
    test -f "$release_dir/assets/$pattern"
    mkdir -p "$output_dir"
    cp "$release_dir/assets/$pattern" "$output_dir/$pattern"
    ;;
  *)
    echo "unsupported gh action: $action" >&2
    exit 2
    ;;
esac
EOF
chmod +x "$FAKE_BIN/gh"

new_repo() {
  local name="$1"
  local work="$TMP/$name"
  local remote="$TMP/$name.git"
  git init -q --bare "$remote"
  git init -q -b main "$work"
  git -C "$work" config user.name "Release Test"
  git -C "$work" config user.email "release-test@example.com"
  git -C "$work" commit -qm "feat: initial" --allow-empty
  git -C "$work" remote add origin "$remote"
  git -C "$work" push -q -u origin main
  printf '%s\n' "$work"
}

publish() {
  local repo="$1"
  local target="$2"
  local tag="$3"
  local notes="$4"
  (
    cd "$repo"
    PATH="$FAKE_BIN:$PATH" \
      FAKE_GH_STATE="$GH_STATE" \
      FAKE_GH_LOG="$GH_LOG" \
      GITHUB_REPOSITORY="endaye/lmdj" \
      GITHUB_SERVER_URL="https://github.com" \
      GITHUB_RUN_ID="42" \
      GH_TOKEN="test-token" \
      "$PUBLISHER" "$target" "$tag" "$notes"
  )
}

# New publication creates one immutable annotated Tag, Release, and matching asset.
REPO1="$(new_repo repo1)"
TARGET1="$(git -C "$REPO1" rev-parse HEAD)"
NOTES1="$REPO1/CHANGELOG-v0.2.0.md"
printf '# v0.2.0\n\nfirst release\n' > "$NOTES1"
publish "$REPO1" "$TARGET1" "v0.2.0" "$NOTES1"
test "$(git --git-dir="$TMP/repo1.git" rev-parse 'refs/tags/v0.2.0^{commit}')" = "$TARGET1"
test "$(git --git-dir="$TMP/repo1.git" cat-file -t refs/tags/v0.2.0)" = "tag"
git --git-dir="$TMP/repo1.git" cat-file -p refs/tags/v0.2.0 \
  | grep -Fq 'Workflow: https://github.com/endaye/lmdj/actions/runs/42'
cmp "$NOTES1" "$GH_STATE/v0.2.0/body"
cmp "$NOTES1" "$GH_STATE/v0.2.0/assets/CHANGELOG-v0.2.0.md"

# A complete rerun is idempotent.
publish "$REPO1" "$TARGET1" "v0.2.0" "$NOTES1"
test "$(grep -c '^gh release create v0.2.0 ' "$GH_LOG")" = "1"
if grep -q '^gh release upload v0.2.0 ' "$GH_LOG"; then
  echo "new Release must attach its Changelog during creation" >&2
  exit 1
fi

# Existing Release body is authoritative when its asset is missing.
REPO2="$(new_repo repo2)"
TARGET2="$(git -C "$REPO2" rev-parse HEAD)"
git -C "$REPO2" tag -a v0.3.0 "$TARGET2" -m v0.3.0
git -C "$REPO2" push -q origin refs/tags/v0.3.0
mkdir -p "$GH_STATE/v0.3.0"
printf '# v0.3.0\n\ncanonical release body\n' > "$GH_STATE/v0.3.0/body"
NOTES2="$REPO2/CHANGELOG-v0.3.0.md"
printf 'stale generated body\n' > "$NOTES2"
publish "$REPO2" "$TARGET2" "v0.3.0" "$NOTES2"
cmp "$GH_STATE/v0.3.0/body" "$NOTES2"
cmp "$GH_STATE/v0.3.0/body" "$GH_STATE/v0.3.0/assets/CHANGELOG-v0.3.0.md"

# Existing mismatched asset fails without overwriting it.
printf 'tampered asset\n' > "$GH_STATE/v0.3.0/assets/CHANGELOG-v0.3.0.md"
if publish "$REPO2" "$TARGET2" "v0.3.0" "$NOTES2" 2>/dev/null; then
  echo "mismatched release asset unexpectedly succeeded" >&2
  exit 1
fi
test "$(cat "$GH_STATE/v0.3.0/assets/CHANGELOG-v0.3.0.md")" = "tampered asset"

# Existing Tag on another commit fails without moving the Tag.
REPO3="$(new_repo repo3)"
OLD3="$(git -C "$REPO3" rev-parse HEAD)"
git -C "$REPO3" tag -a v0.4.0 "$OLD3" -m v0.4.0
git -C "$REPO3" push -q origin refs/tags/v0.4.0
git -C "$REPO3" commit -qm "fix: newer" --allow-empty
TARGET3="$(git -C "$REPO3" rev-parse HEAD)"
git -C "$REPO3" tag -d v0.4.0 >/dev/null
git -C "$REPO3" tag -a v0.4.0 "$TARGET3" -m "misleading local Tag"
NOTES3="$REPO3/CHANGELOG-v0.4.0.md"
printf '# v0.4.0\n' > "$NOTES3"
if publish "$REPO3" "$TARGET3" "v0.4.0" "$NOTES3" 2>/dev/null; then
  echo "Tag mismatch unexpectedly succeeded" >&2
  exit 1
fi
test "$(git --git-dir="$TMP/repo3.git" rev-parse 'refs/tags/v0.4.0^{commit}')" = "$OLD3"

# A lightweight SemVer Tag is not accepted as a product release Tag.
REPO4="$(new_repo repo4)"
TARGET4="$(git -C "$REPO4" rev-parse HEAD)"
git -C "$REPO4" update-ref refs/tags/v0.5.0 "$TARGET4"
git -C "$REPO4" push -q origin refs/tags/v0.5.0
NOTES4="$REPO4/CHANGELOG-v0.5.0.md"
printf '# v0.5.0\n' > "$NOTES4"
if publish "$REPO4" "$TARGET4" "v0.5.0" "$NOTES4" 2>/dev/null; then
  echo "lightweight product Tag unexpectedly succeeded" >&2
  exit 1
fi
test "$(git --git-dir="$TMP/repo4.git" cat-file -t refs/tags/v0.5.0)" = "commit"

echo "publish-staging-release tests passed"
