#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "$script_dir/.." && pwd -P)"
deploy_root="$repo_root/build/deploy/web-runtime-host"
orchestrator_tool="$repo_root/apps/web-runtime-host/tools/deploy_orchestrator.py"
tag_pattern='^lmdj-v([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)$'
production_url='https://lmdj-runtime.netlify.app'
trusted_fingerprint='2B5EE362F058800036AD4FB5116ECE156F954D29'
initial_tag='lmdj-v1.0.15.2'
initial_tag_target='72ae40074620cc5681c462ba04a31a666449734f'
python_bin='python3'
owned_temp=''
owned_temp_parent=''
tag_checkout=''

usage() {
  cat >&2 <<'EOF'
usage:
  scripts/web-runtime-deploy.sh verify TAG
  scripts/web-runtime-deploy.sh deploy TAG
  scripts/web-runtime-deploy.sh smoke BASE_URL PRODUCT_BUILD HOST_VERSION
EOF
}

fail() {
  echo "Web Runtime deployment error: $1" >&2
  return 2
}

without_deploy_secrets() {
  env \
    -u GITHUB_TOKEN \
    -u GH_TOKEN \
    -u GITHUB_ENTERPRISE_TOKEN \
    -u GH_ENTERPRISE_TOKEN \
    -u NETLIFY_AUTH_TOKEN \
    -u NETLIFY_RUNTIME_SITE_ID \
    "$@"
}

with_pinned_github() {
  env \
    -u GH_TOKEN \
    -u GITHUB_ENTERPRISE_TOKEN \
    -u GH_ENTERPRISE_TOKEN \
    -u GH_HOST \
    -u GH_REPO \
    -u NETLIFY_AUTH_TOKEN \
    -u NETLIFY_RUNTIME_SITE_ID \
    GITHUB_TOKEN="$GITHUB_TOKEN" \
    "$@"
}

with_netlify_credential() {
  env \
    -u GH_TOKEN \
    -u GITHUB_ENTERPRISE_TOKEN \
    -u GH_ENTERPRISE_TOKEN \
    -u GH_HOST \
    -u GH_REPO \
    "$@"
}

cleanup_all() {
  local status=$?
  trap - EXIT INT TERM
  if [[ -n "$tag_checkout" ]]; then
    if ! without_deploy_secrets \
      git worktree remove --force "$tag_checkout" >/dev/null 2>&1
    then
      echo "Web Runtime deployment error: detached tag checkout cleanup failed" >&2
      status=2
    fi
    tag_checkout=''
  fi
  if [[ -n "$owned_temp" ]]; then
    local resolved_parent=''
    local basename=''
    resolved_parent="$(cd "$(dirname "$owned_temp")" 2>/dev/null && pwd -P)" || true
    basename="$(basename "$owned_temp")"
    if [[ \
      -z "$owned_temp_parent" || \
      "$resolved_parent" != "$owned_temp_parent" || \
      "$basename" != lmdj-web-runtime-deploy.* || \
      -L "$owned_temp" || \
      ! -d "$owned_temp" \
    ]]; then
      echo "Web Runtime deployment error: refusing unsafe temporary cleanup" >&2
      status=2
    elif ! rm -rf -- "$owned_temp"; then
      echo "Web Runtime deployment error: temporary cleanup failed" >&2
      status=2
    fi
    owned_temp=''
  fi
  exit "$status"
}

trap cleanup_all EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

create_owned_temp() {
  local requested_parent="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
  [[ -d "$requested_parent" && ! -L "$requested_parent" ]] || {
    fail "temporary parent is unavailable"
    return
  }
  owned_temp_parent="$(cd "$requested_parent" && pwd -P)"
  owned_temp="$(mktemp -d "$owned_temp_parent/lmdj-web-runtime-deploy.XXXXXX")"
  [[ -d "$owned_temp" && ! -L "$owned_temp" ]] || {
    fail "owned temporary root was not created safely"
    return
  }
  chmod 700 "$owned_temp"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing command: $1"
}

require_secret() {
  local name="$1"
  [[ -n "${!name:-}" ]] || fail "required environment is missing: $name"
  [[ "${!name}" != *$'\n'* && "${!name}" != *$'\r'* ]] || {
    fail "required environment is invalid: $name"
  }
}

validate_tag() {
  local tag="$1"
  if [[ ! "$tag" =~ $tag_pattern ]]; then
    usage
    return 64
  fi
  product_build="${BASH_REMATCH[1]}"
}

verify_signed_tag() {
  local tag="$1"
  local key_path="$repo_root/.github/release-signing-keys/lmdj-product.asc"
  local tag_type=''
  local key_fingerprint=''
  local verify_status=''

  tag_type="$(
    without_deploy_secrets git cat-file -t "refs/tags/$tag" 2>/dev/null
  )" || {
    fail "Product tag is unavailable"
    return
  }
  [[ "$tag_type" == 'tag' ]] || {
    fail "Product tag must be annotated"
    return
  }

  mkdir -m 700 "$owned_temp/gnupg"
  export GNUPGHOME="$owned_temp/gnupg"
  key_fingerprint="$(
    without_deploy_secrets \
      gpg --batch --show-keys --with-colons "$key_path" 2>/dev/null |
      awk -F: '$1 == "fpr" {print $10; exit}'
  )" || {
    fail "trusted Product signing key is unavailable"
    return
  }
  [[ "$key_fingerprint" == "$trusted_fingerprint" ]] || {
    fail "trusted Product signing key fingerprint mismatch"
    return
  }
  without_deploy_secrets \
    gpg --batch --import "$key_path" >/dev/null 2>&1 || {
    fail "trusted Product signing key import failed"
    return
  }
  if ! verify_status="$(
    without_deploy_secrets git verify-tag --raw "$tag" 2>&1
  )"; then
    fail "Product tag signature verification failed"
    return
  fi
  if ! printf '%s\n' "$verify_status" |
    awk -v fingerprint="$trusted_fingerprint" '
      /^\[GNUPG:\] VALIDSIG / {
        for (field = 3; field <= NF; field += 1) {
          if ($field == fingerprint) found = 1
        }
      }
      END {exit(found ? 0 : 1)}
    '
  then
    fail "Product tag signature is not from the trusted key"
    return
  fi

  tag_target="$(
    without_deploy_secrets \
      git rev-parse --verify "${tag}^{commit}" 2>/dev/null
  )" || {
    fail "Product tag target cannot be resolved"
    return
  }
  [[ "$tag_target" =~ ^[0-9a-f]{40}$ ]] || {
    fail "Product tag target identity is invalid"
    return
  }
  if [[ "$tag" == "$initial_tag" && "$tag_target" != "$initial_tag_target" ]]; then
    fail "initial Product tag target mismatch"
    return
  fi
}

create_tag_checkout() {
  tag_checkout="$owned_temp/tag-target"
  without_deploy_secrets \
    git worktree add --detach "$tag_checkout" "$tag_target" >/dev/null 2>&1 || {
    fail "detached tag checkout creation failed"
    return
  }
  [[ -d "$tag_checkout" && ! -L "$tag_checkout" ]] || {
    fail "detached tag checkout is unsafe"
    return
  }
}

read_tag_identity() {
  local fields=''
  fields="$(
    "$python_bin" "$orchestrator_tool" \
      tag-identity "$tag_checkout" "$product_build"
  )" || {
    fail "signed tag-target identity verification failed"
    return
  }
  IFS=$'\t' read -r staged_product_build host_version <<<"$fields"
  [[ \
    "$staged_product_build" == "$product_build" && \
    "$host_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ \
  ]] || {
    fail "signed tag-target identity output is invalid"
    return
  }
}

parse_release_metadata() {
  local tag="$1"
  local release_json="$2"
  local fields=''
  fields="$(
    "$python_bin" "$orchestrator_tool" release-metadata \
      "$tag" "$tag_target" "$product_build" "$host_version" "$release_json"
  )" || {
    fail "GitHub Release identity verification failed"
    return
  }
  IFS=$'\t' read -r archive_name checksum_name release_url <<<"$fields"
  [[ \
    -n "$archive_name" && \
    "$checksum_name" == "$archive_name.sha256" && \
    -n "$release_url" \
  ]] || {
    fail "GitHub Release identity output is invalid"
    return
  }
}

download_release_assets() {
  local tag="$1"
  local download_root="$owned_temp/download"
  mkdir "$download_root"
  with_pinned_github gh release download "$tag" \
    --repo endaye/lmdj \
    --pattern "$archive_name" \
    --pattern "$checksum_name" \
    --dir "$download_root" \
    --clobber >/dev/null 2>&1 || {
    fail "GitHub Release asset download failed"
    return
  }
  "$python_bin" "$orchestrator_tool" downloaded-assets \
    "$download_root" "$archive_name" "$checksum_name" || {
    fail "downloaded GitHub Release asset verification failed"
    return
  }
  archive_path="$download_root/$archive_name"
  checksum_path="$download_root/$checksum_name"
}

stage_release_assets() {
  local stage_root="$owned_temp/staged"
  local bundle_json=''
  local fields=''
  bundle_json="$(
    without_deploy_secrets \
      "$python_bin" "$repo_root/apps/web-runtime-host/tools/release_bundle.py" stage \
        --repo-root "$tag_checkout" \
        --archive "$archive_path" \
        --checksum "$checksum_path" \
        --output-root "$stage_root" \
        --expected-product-build "$product_build" \
        --expected-host-version "$host_version" 2>/dev/null
  )" || {
    fail "released Host bundle verification failed"
    return
  }
  fields="$(
    "$python_bin" "$orchestrator_tool" staged-bundle \
      "$stage_root" "$product_build" "$host_version" "$tag" "$bundle_json"
  )" || {
    fail "staged Host bundle result verification failed"
    return
  }
  IFS=$'\t' read -r dist_root archive_sha256 <<<"$fields"
}

remove_tag_checkout() {
  without_deploy_secrets \
    git worktree remove --force "$tag_checkout" >/dev/null 2>&1 || {
    fail "detached tag checkout cleanup failed"
    return
  }
  [[ ! -e "$tag_checkout" && ! -L "$tag_checkout" ]] || {
    fail "detached tag checkout was not removed"
    return
  }
  tag_checkout=''
}

verify_release() {
  local tag="$1"
  local release_json=''
  create_owned_temp
  verify_signed_tag "$tag"
  create_tag_checkout
  read_tag_identity
  release_json="$(
    with_pinned_github gh release view "$tag" \
      --repo endaye/lmdj \
      --json tagName,isDraft,isPrerelease,targetCommitish,assets,url \
      2>/dev/null
  )" || {
    fail "GitHub Release metadata is unavailable"
    return
  }
  parse_release_metadata "$tag" "$release_json"
  download_release_assets "$tag"
  stage_release_assets
  remove_tag_checkout
}

create_draft_deploy() {
  local headers_path="$repo_root/apps/web-runtime-host/deploy/_headers"
  local fields=''
  fields="$(
    with_netlify_credential \
      "$python_bin" "$orchestrator_tool" create-draft \
        "$dist_root" "$headers_path" "$product_build" "$host_version" "$tag"
  )" || {
    fail "Netlify draft deploy creation failed"
    return
  }
  IFS=$'\t' read -r deploy_id deploy_url <<<"$fields"
  [[ -n "$deploy_id" && -n "$deploy_url" ]] || {
    fail "Netlify draft deploy identity output is invalid"
    return
  }
}

run_http_smoke() {
  local base_url="$1"
  local expected_deploy_id="${2:-}"
  local arguments=(
    "$repo_root/apps/web-runtime-host/tools/deployment_smoke.py"
    "$base_url"
    "$product_build"
    "$host_version"
  )
  if [[ -n "$expected_deploy_id" ]]; then
    arguments+=(--expected-deploy-id "$expected_deploy_id")
  fi
  without_deploy_secrets "$python_bin" "${arguments[@]}" >/dev/null
}

run_browser_smoke() {
  local base_url="$1"
  env \
    -u GITHUB_TOKEN \
    -u GH_TOKEN \
    -u GITHUB_ENTERPRISE_TOKEN \
    -u GH_ENTERPRISE_TOKEN \
    -u NETLIFY_AUTH_TOKEN \
    -u NETLIFY_RUNTIME_SITE_ID \
    LMDJ_WEB_HOST_CLEAN_ROOM=1 \
    LMDJ_WEB_HOST_EXTERNAL_SERVER=1 \
    LMDJ_WEB_HOST_BASE_URL="$base_url" \
    LMDJ_WEB_HOST_EXPECTED_PRODUCT_BUILD="$product_build" \
    LMDJ_WEB_HOST_EXPECTED_VERSION="$host_version" \
    npm --prefix "$repo_root/tests/platform/web" test -- \
      --project=chromium \
      deployment/web_runtime_host_deployment.spec.mjs
}

publish_deploy() {
  with_netlify_credential \
    "$python_bin" "$orchestrator_tool" publish \
      "$NETLIFY_RUNTIME_SITE_ID" "$deploy_id" || {
    fail "Netlify same-ID publication failed"
    return
  }
}

initialize_evidence_target() {
  "$python_bin" "$orchestrator_tool" evidence-init \
    "$repo_root" "$deploy_root"
}

write_evidence() {
  "$python_bin" "$orchestrator_tool" evidence-write \
    "$deploy_root/evidence.json" \
    "$archive_sha256" "$deploy_id" "$deploy_url" "$tag_target" \
    "$host_version" "$product_build" "$release_url" \
    "$NETLIFY_RUNTIME_SITE_ID" "$tag"
}

deploy_release() {
  local selected_tag="$1"
  tag="$selected_tag"
  require_secret GITHUB_TOKEN
  require_secret NETLIFY_RUNTIME_SITE_ID
  require_secret NETLIFY_AUTH_TOKEN
  initialize_evidence_target
  verify_release "$tag"
  create_draft_deploy
  run_http_smoke "$deploy_url" "$deploy_id"
  run_browser_smoke "$deploy_url"
  publish_deploy
  run_http_smoke "$production_url"
  run_browser_smoke "$production_url"
  write_evidence
  echo "Web Runtime Host deployment: PASS ($deploy_id)"
}

smoke_target() {
  local base_url="$1"
  product_build="$2"
  host_version="$3"
  run_http_smoke "$base_url"
  run_browser_smoke "$base_url"
  echo "Web Runtime Host deployment smoke: PASS"
}

[[ $# -ge 1 ]] || {
  usage
  exit 64
}

command_name="$1"
shift
cd "$repo_root"

case "$command_name" in
  verify)
    [[ $# -eq 1 ]] || { usage; exit 64; }
    validate_tag "$1"
    tag="$1"
    for command in git gpg gh "$python_bin"; do
      require_command "$command"
    done
    [[ -f "$orchestrator_tool" ]] || fail "deployment orchestrator is unavailable"
    verify_release "$tag"
    echo "Web Runtime Host release verification: PASS ($tag)"
    ;;
  deploy)
    [[ $# -eq 1 ]] || { usage; exit 64; }
    validate_tag "$1"
    for command in git gpg gh "$python_bin" npm; do
      require_command "$command"
    done
    [[ -f "$orchestrator_tool" ]] || fail "deployment orchestrator is unavailable"
    deploy_release "$1"
    ;;
  smoke)
    [[ $# -eq 3 ]] || { usage; exit 64; }
    for command in "$python_bin" npm; do
      require_command "$command"
    done
    smoke_target "$1" "$2" "$3"
    ;;
  *)
    usage
    exit 64
    ;;
esac
