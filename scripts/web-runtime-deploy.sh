#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "$script_dir/.." && pwd -P)"
deploy_root="$repo_root/build/deploy/web-runtime-host"
orchestrator_tool="$repo_root/apps/web-runtime-host/tools/deploy_orchestrator.py"
tag_pattern='^lmdj-v([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)$'
production_url='https://lmdj-runtime.netlify.app'
trusted_tag_fingerprint='2B5EE362F058800036AD4FB5116ECE156F954D29'
trusted_checksum_fingerprint='CB928A6E89DE498851688EF1AAC3E7019FC1478B'
initial_tag='lmdj-v1.0.15.2'
initial_tag_target='72ae40074620cc5681c462ba04a31a666449734f'
canonical_repository='endaye/lmdj'
remote_tag_ref=''
remote_main_ref='refs/lmdj-deploy/origin-main'
python_bin='python3'
owned_temp=''
owned_temp_parent=''
owned_gnupg=''
owned_gnupg_parent=''
tag_checkout=''
publication_attempted=0
deployment_complete=0
recovery_running=0
recovery_api_timeout_seconds=30
recovery_http_timeout_seconds=180
recovery_browser_timeout_seconds=180
recovery_evidence_timeout_seconds=30
preflight_probe_timeout_seconds=15
prior_deploy_id=''
prior_deploy_url=''
prior_product_build=''
prior_host_version=''
prior_index_sha256=''
prior_manifest_sha256=''
staged_index_sha256=''
staged_manifest_sha256=''
current_site_json='{}'
prior_immutable_http_result='{}'
prior_immutable_browser_result='{}'
prior_production_http_result='{}'
prior_production_browser_result='{}'
reconcile_site_json='{}'
post_recovery_site_json='{}'
recovery_response_json='null'
recovery_action='not-started'
recovery_immutable_http_result='{}'
recovery_immutable_browser_result='{}'
recovery_production_http_result='{}'
recovery_production_browser_result='{}'
disabled_alias_probe_result='{}'

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

with_gh_environment_removed() {
  local -a unset_arguments=()
  local name=''
  while IFS= read -r name; do
    [[ "$name" == GH* ]] && unset_arguments+=(-u "$name")
  done < <(compgen -e)
  env "${unset_arguments[@]}" "$@"
}

without_deploy_secrets() {
  with_gh_environment_removed \
    -u GITHUB_TOKEN \
    -u GITHUB_ENTERPRISE_TOKEN \
    -u NETLIFY_AUTH_TOKEN \
    -u NETLIFY_RUNTIME_SITE_ID \
    "$@"
}

with_pinned_github() {
  with_gh_environment_removed \
    -u GITHUB_ENTERPRISE_TOKEN \
    -u NETLIFY_AUTH_TOKEN \
    -u NETLIFY_RUNTIME_SITE_ID \
    "$@"
}

with_pinned_github_git() {
  GIT_TERMINAL_PROMPT=0 with_pinned_github git \
    -c credential.username=x-access-token \
    -c 'credential.helper=!f() { if test "$1" = get && test -n "${GITHUB_TOKEN:-}"; then printf "%s\n" "username=x-access-token" "password=$GITHUB_TOKEN"; fi; }; f' \
    "$@"
}

with_netlify_credential() {
  with_gh_environment_removed \
    -u GITHUB_TOKEN \
    -u GITHUB_ENTERPRISE_TOKEN \
    "$@"
}

remove_tag_checkout_path() {
  local selected_path="$1"
  [[ \
    -n "$owned_temp" && \
    "$selected_path" == "$owned_temp/tag-target" && \
    -d "$selected_path" && \
    ! -L "$selected_path" \
  ]] || return 1
  rm -rf -- "$selected_path" || return 1
  [[ ! -e "$selected_path" && ! -L "$selected_path" ]]
}

cleanup_all() {
  local status=$?
  trap - EXIT INT TERM
  if (( status != 0 && publication_attempted == 1 && deployment_complete == 0 && recovery_running == 0 )); then
    recovery_running=1
    local original_status="$status"
    local recovery_status='passed'
    if ! reconcile_publication_failure "$original_status"; then
      echo "Web Runtime deployment error: publication recovery failed" >&2
      recovery_status='failed'
      status=2
    fi
    if ! write_recovery_evidence "$original_status" "$recovery_status"; then
      echo "Web Runtime deployment error: recovery evidence write failed" >&2
      status=2
    fi
  fi
  if [[ -n "$remote_tag_ref" ]]; then
    without_deploy_secrets git update-ref -d "$remote_tag_ref" >/dev/null 2>&1 || status=2
    remote_tag_ref=''
  fi
  without_deploy_secrets git update-ref -d "$remote_main_ref" >/dev/null 2>&1 || status=2
  if [[ -n "$tag_checkout" ]]; then
    if ! remove_tag_checkout_path "$tag_checkout"; then
      echo "Web Runtime deployment error: detached tag checkout cleanup failed" >&2
      status=2
    fi
    tag_checkout=''
  fi
  if [[ -n "$owned_gnupg" ]]; then
    local resolved_gnupg_parent=''
    local gnupg_basename=''
    resolved_gnupg_parent="$(cd "$(dirname "$owned_gnupg")" 2>/dev/null && pwd -P)" || true
    gnupg_basename="$(basename "$owned_gnupg")"
    if [[ \
      -z "$owned_gnupg_parent" || \
      "$resolved_gnupg_parent" != "$owned_gnupg_parent" || \
      "$gnupg_basename" != lmdj-web-runtime-gpg.* || \
      -L "$owned_gnupg" || \
      ! -d "$owned_gnupg" \
    ]]; then
      echo "Web Runtime deployment error: refusing unsafe GnuPG cleanup" >&2
      status=2
    elif ! rm -rf -- "$owned_gnupg"; then
      echo "Web Runtime deployment error: GnuPG cleanup failed" >&2
      status=2
    fi
    owned_gnupg=''
    unset GNUPGHOME
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

create_owned_gnupg_home() {
  owned_gnupg_parent="$(cd /tmp && pwd -P)" || {
    fail "short GnuPG temporary parent is unavailable"
    return
  }
  [[ -d "$owned_gnupg_parent" && ! -L "$owned_gnupg_parent" ]] || {
    fail "short GnuPG temporary parent is unsafe"
    return
  }
  owned_gnupg="$(mktemp -d "$owned_gnupg_parent/lmdj-web-runtime-gpg.XXXXXX")" || {
    fail "short GnuPG home creation failed"
    return
  }
  [[ -d "$owned_gnupg" && ! -L "$owned_gnupg" ]] || {
    fail "short GnuPG home was not created safely"
    return
  }
  chmod 700 "$owned_gnupg"
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

fetch_remote_authority() {
  local tag="$1"
  local origin_url=''
  local protected=''
  origin_url="$(without_deploy_secrets git remote get-url origin 2>/dev/null)" || {
    fail "canonical origin remote is unavailable"
    return
  }
  case "$origin_url" in
    https://github.com/endaye/lmdj|https://github.com/endaye/lmdj.git|https://endaye@github.com/endaye/lmdj.git|git@github.com:endaye/lmdj.git|ssh://git@github.com/endaye/lmdj.git) ;;
    *) fail "origin remote is not the canonical repository"; return ;;
  esac
  remote_tag_ref="refs/lmdj-deploy/tags/$tag"
  without_deploy_secrets git update-ref -d "$remote_tag_ref" >/dev/null 2>&1 || true
  without_deploy_secrets git update-ref -d "$remote_main_ref" >/dev/null 2>&1 || true
  with_pinned_github_git fetch --no-tags origin \
    "refs/tags/$tag:$remote_tag_ref" >/dev/null 2>&1 || {
    fail "canonical remote Product tag fetch failed"
    return
  }
  with_pinned_github_git fetch --no-tags origin \
    "refs/heads/main:$remote_main_ref" >/dev/null 2>&1 || {
    fail "canonical origin/main fetch failed"
    return
  }
  protected="$(
    with_pinned_github gh api "repos/$canonical_repository/branches/main" \
      --jq .protected 2>/dev/null
  )" || {
    fail "canonical main protection metadata is unavailable"
    return
  }
  [[ "$protected" == 'true' ]] || {
    fail "canonical origin/main is not protected"
    return
  }
}

verify_signed_tag() {
  local tag="$1"
  local key_path="$repo_root/.github/release-signing-keys/lmdj-product.asc"
  local tag_type=''
  local key_fingerprint=''
  local verify_status=''
  local import_error=''

  tag_type="$(
    without_deploy_secrets git cat-file -t "$remote_tag_ref" 2>/dev/null
  )" || {
    fail "Product tag is unavailable"
    return
  }
  [[ "$tag_type" == 'tag' ]] || {
    fail "Product tag must be annotated"
    return
  }

  create_owned_gnupg_home || return
  export GNUPGHOME="$owned_gnupg"
  key_fingerprint="$(
    without_deploy_secrets \
      gpg --batch --show-keys --with-colons "$key_path" 2>/dev/null |
      awk -F: '$1 == "fpr" {print $10; exit}'
  )" || {
    fail "trusted Product signing key is unavailable"
    return
  }
  [[ "$key_fingerprint" == "$trusted_tag_fingerprint" ]] || {
    fail "trusted Product signing key fingerprint mismatch"
    return
  }
  if ! import_error="$(
    without_deploy_secrets \
      gpg --batch --no-autostart --import "$key_path" 2>&1
  )"; then
    printf '%s\n' "$import_error" >&2
    fail "trusted Product signing key import failed"
    return
  fi
  if ! verify_status="$(
    without_deploy_secrets git verify-tag --raw "$remote_tag_ref" 2>&1
  )"; then
    fail "Product tag signature verification failed"
    return
  fi
  if ! printf '%s\n' "$verify_status" |
    awk -v fingerprint="$trusted_tag_fingerprint" '
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
      git rev-parse --verify "${remote_tag_ref}^{commit}" 2>/dev/null
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
  without_deploy_secrets git merge-base --is-ancestor \
    "$tag_target" "$remote_main_ref" >/dev/null 2>&1 || {
    fail "Product tag target is not an ancestor of protected origin/main"
    return
  }
}

create_tag_checkout() {
  local candidate="$owned_temp/tag-target"
  local empty_template="$owned_temp/git-template"
  local candidate_tag_ref='refs/lmdj-deploy/tag-target'
  local checkout_head=''
  mkdir -m 700 "$empty_template" || {
    fail "detached tag checkout template creation failed"
    return
  }
  without_deploy_secrets \
    git init --quiet --template="$empty_template" "$candidate" >/dev/null 2>&1 || {
    fail "detached tag checkout creation failed"
    return
  }
  without_deploy_secrets \
    git -C "$candidate" fetch --no-tags --no-write-fetch-head \
      "$repo_root" "$remote_tag_ref:$candidate_tag_ref" >/dev/null 2>&1 || {
    fail "detached tag checkout ref materialization failed"
    return
  }
  without_deploy_secrets \
    env GIT_LFS_SKIP_SMUDGE=1 \
      git -C "$candidate" checkout --detach "$tag_target" >/dev/null 2>&1 || {
    fail "detached tag checkout population failed"
    return
  }
  checkout_head="$(
    without_deploy_secrets git -C "$candidate" rev-parse --verify HEAD 2>/dev/null
  )" || {
    fail "detached tag checkout identity is unavailable"
    return
  }
  [[ "$checkout_head" == "$tag_target" ]] || {
    fail "detached tag checkout identity mismatch"
    return
  }
  [[ -d "$candidate" && ! -L "$candidate" ]] || {
    fail "detached tag checkout is unsafe"
    return
  }
  tag_checkout="$candidate"
}

read_tag_identity() {
  local fields=''
  fields="$(
    without_deploy_secrets "$python_bin" "$orchestrator_tool" \
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
  local fields=''
  fields="$(
    without_deploy_secrets "$python_bin" "$orchestrator_tool" release-metadata \
      "$tag" "$tag_target" "$product_build" "$host_version"
  )" || {
    fail "GitHub Release identity verification failed"
    return
  }
  IFS=$'\t' read -r archive_name checksum_name signature_name release_url <<<"$fields"
  [[ \
    -n "$archive_name" && \
    "$checksum_name" == "$archive_name.sha256" && \
    "$signature_name" == "$checksum_name.asc" && \
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
    --pattern "$signature_name" \
    --dir "$download_root" \
    --clobber >/dev/null 2>&1 || {
    fail "GitHub Release asset download failed"
    return
  }
  without_deploy_secrets "$python_bin" "$orchestrator_tool" downloaded-assets \
    "$download_root" "$archive_name" "$checksum_name" "$signature_name" || {
    fail "downloaded GitHub Release asset verification failed"
    return
  }
  archive_path="$download_root/$archive_name"
  checksum_path="$download_root/$checksum_name"
  signature_path="$download_root/$signature_name"
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
        --checksum-signature "$signature_path" \
        --checksum-public-key "$repo_root/.github/release-signing-keys/lmdj-release-checksum.asc" \
        --trusted-checksum-fingerprint "$trusted_checksum_fingerprint" \
        --output-root "$stage_root" \
        --expected-product-build "$product_build" \
        --expected-host-version "$host_version" 2>/dev/null
  )" || {
    fail "released Host bundle verification failed"
    return
  }
  fields="$(
    without_deploy_secrets "$python_bin" "$orchestrator_tool" staged-bundle \
      "$stage_root" "$product_build" "$host_version" "$tag" "$bundle_json"
  )" || {
    fail "staged Host bundle result verification failed"
    return
  }
  IFS=$'\t' read -r dist_root archive_sha256 staged_index_sha256 staged_manifest_sha256 <<<"$fields"
  [[ "$staged_index_sha256" =~ ^[0-9a-f]{64}$ && "$staged_manifest_sha256" =~ ^[0-9a-f]{64}$ ]] || {
    fail "staged Host release file identity output is invalid"
    return
  }
}

remove_tag_checkout() {
  remove_tag_checkout_path "$tag_checkout" || {
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
  fetch_remote_authority "$tag"
  verify_signed_tag "$tag"
  create_tag_checkout
  read_tag_identity
  release_json="$(
    with_pinned_github gh release view "$tag" \
      --repo endaye/lmdj \
      --json tagName,isDraft,isPrerelease,targetCommitish,assets,url \
      --jq '{tagName,isDraft,isPrerelease,targetCommitish,assets:[.assets[]|{name:.name}],url}' \
      2>/dev/null
  )" || {
    fail "GitHub Release metadata is unavailable"
    return
  }
  parse_release_metadata "$tag" <<<"$release_json"
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

parse_site_fields() {
  without_deploy_secrets "$python_bin" -c '
import json,sys
value=json.load(sys.stdin)
prior=value.get("published_deploy")
if prior is None:
    print(value["state"] + "\t\t")
else:
    print(value["state"] + "\t" + prior["id"] + "\t" + prior["deploy_ssl_url"])
'
}

get_current_site() {
  local timeout_seconds="${1:-}"
  local -a command=("$python_bin" "$orchestrator_tool" site-current "$NETLIFY_RUNTIME_SITE_ID")
  if [[ -n "$timeout_seconds" ]]; then
    command=(timeout --signal=TERM --kill-after=5s "${timeout_seconds}s" "${command[@]}")
  fi
  current_site_json="$(
    with_netlify_credential "${command[@]}"
  )" || {
    fail "Netlify current published deploy lookup failed"
    return
  }
  local fields=''
  fields="$(parse_site_fields <<<"$current_site_json")" || {
    fail "Netlify current published deploy output is invalid"
    return
  }
  IFS=$'\t' read -r current_site_state current_deploy_id current_deploy_url <<<"$fields"
}

preflight_prior_good() {
  local identity_json=''
  local fields=''
  get_current_site
  [[ "$current_site_state" != 'disabled' ]] || {
    fail "Netlify site is already disabled; refusing automatic enable or publication"
    return
  }
  prior_deploy_id="$current_deploy_id"
  prior_deploy_url="$current_deploy_url"
  if [[ -z "$prior_deploy_id" ]]; then
    return
  fi
  if run_disabled_alias_probe "$production_url" "$preflight_probe_timeout_seconds" 2>/dev/null; then
    prior_deploy_id=''
    prior_deploy_url=''
    return
  fi
  identity_json="$(
    without_deploy_secrets "$python_bin" \
      "$repo_root/apps/web-runtime-host/tools/deployment_smoke.py" \
      discover-identity "$prior_deploy_url"
  )" || {
    fail "prior published deploy identity discovery failed"
    return
  }
  fields="$(
    without_deploy_secrets "$python_bin" -c '
import json,sys
value=json.load(sys.stdin)
print(value["product_build"] + "\t" + value["host_version"])
' <<<"$identity_json"
  )" || {
    fail "prior published deploy identity output is invalid"
    return
  }
  IFS=$'\t' read -r prior_product_build prior_host_version <<<"$fields"
  run_http_smoke "$prior_deploy_url" "$prior_product_build" "$prior_host_version" "$prior_deploy_id"
  prior_immutable_http_result="$http_smoke_result"
  read -r prior_index_sha256 prior_manifest_sha256 < <(extract_http_digests "$http_smoke_result")
  run_browser_smoke "$prior_deploy_url" "$prior_product_build" "$prior_host_version" "$prior_deploy_id"
  prior_immutable_browser_result="$browser_smoke_result"
  run_http_smoke "$production_url" "$prior_product_build" "$prior_host_version" '' "$prior_index_sha256" "$prior_manifest_sha256"
  prior_production_http_result="$http_smoke_result"
  run_browser_smoke "$production_url" "$prior_product_build" "$prior_host_version" "$prior_deploy_id"
  prior_production_browser_result="$browser_smoke_result"
}

run_disabled_alias_probe() {
  local base_url="$1"
  local timeout_seconds="${2:-}"
  local started_at=''
  local ended_at=''
  local raw_result=''
  local -a command=(
    "$python_bin"
    "$repo_root/apps/web-runtime-host/tools/deployment_smoke.py"
    probe-disabled-alias
    "$base_url"
  )
  if [[ -n "$timeout_seconds" ]]; then
    command+=(--timeout "$timeout_seconds")
  fi
  started_at="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  raw_result="$({ without_deploy_secrets "${command[@]}"; })" || return 2
  ended_at="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  disabled_alias_probe_result="{\"ended_at\":\"$ended_at\",\"result\":$raw_result,\"started_at\":\"$started_at\",\"status\":\"passed\"}"
}

restore_exact_deploy() {
  local restore_id="$1"
  with_netlify_credential timeout --signal=TERM --kill-after=5s "${recovery_api_timeout_seconds}s" \
    "$python_bin" "$orchestrator_tool" publish \
    "$NETLIFY_RUNTIME_SITE_ID" "$restore_id"
}

reconcile_publication_failure() {
  local original_status="$1"
  get_current_site "$recovery_api_timeout_seconds" || return 2
  reconcile_site_json="$current_site_json"
  if [[ "$current_deploy_id" == "$prior_deploy_id" && -n "$prior_deploy_id" ]]; then
    recovery_action='prior-still-current'
    post_recovery_site_json="$reconcile_site_json"
    recovery_immutable_http_result="$prior_immutable_http_result"
    recovery_immutable_browser_result="$prior_immutable_browser_result"
    recovery_production_http_result="$prior_production_http_result"
    recovery_production_browser_result="$prior_production_browser_result"
    return 0
  fi
  if [[ -z "$current_deploy_id" && -z "$prior_deploy_id" ]]; then
    recovery_action='no-publication'
    post_recovery_site_json="$reconcile_site_json"
    return 0
  fi
  if [[ "$current_deploy_id" != "${deploy_id:-}" ]]; then
    recovery_action='unsafe-unknown-alias'
    return 2
  fi
  if [[ -n "$prior_deploy_id" ]]; then
    recovery_response_json="$(restore_exact_deploy "$prior_deploy_id")" || return 2
    recovery_action='restored-prior'
    get_current_site "$recovery_api_timeout_seconds" || return 2
    post_recovery_site_json="$current_site_json"
    [[ "$current_site_state" == 'current' && "$current_deploy_id" == "$prior_deploy_id" && "$current_deploy_url" == "$prior_deploy_url" ]] || return 2
    run_http_smoke "$prior_deploy_url" "$prior_product_build" "$prior_host_version" "$prior_deploy_id" "$prior_index_sha256" "$prior_manifest_sha256" "$recovery_http_timeout_seconds" || return 2
    recovery_immutable_http_result="$http_smoke_result"
    run_browser_smoke "$prior_deploy_url" "$prior_product_build" "$prior_host_version" "$prior_deploy_id" "$recovery_browser_timeout_seconds" || return 2
    recovery_immutable_browser_result="$browser_smoke_result"
    run_http_smoke "$production_url" "$prior_product_build" "$prior_host_version" '' "$prior_index_sha256" "$prior_manifest_sha256" "$recovery_http_timeout_seconds" || return 2
    recovery_production_http_result="$http_smoke_result"
    run_browser_smoke "$production_url" "$prior_product_build" "$prior_host_version" "$prior_deploy_id" "$recovery_browser_timeout_seconds" || return 2
    recovery_production_browser_result="$browser_smoke_result"
  else
    recovery_response_json="$(
      with_netlify_credential timeout --signal=TERM --kill-after=5s "${recovery_api_timeout_seconds}s" \
        "$python_bin" "$orchestrator_tool" disable-site \
        "$NETLIFY_RUNTIME_SITE_ID" "failed first publication; original status $original_status"
    )" || return 2
    recovery_action='disabled-first-publication'
    get_current_site "$recovery_api_timeout_seconds" || return 2
    post_recovery_site_json="$current_site_json"
    if [[ "$current_site_state" != 'disabled' ]]; then
      run_disabled_alias_probe "$production_url" "$recovery_http_timeout_seconds" || return 2
      recovery_production_http_result="$disabled_alias_probe_result"
    fi
  fi
  return 0
}

write_recovery_evidence() {
  local original_status="$1"
  local recovery_status="$2"
  local recorded_at=''
  recorded_at="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  without_deploy_secrets "$python_bin" -c '
import json,sys
(
 original_status,recorded_at,action,recovery_status,attempted_id,attempted_url,
 prior_id,prior_url,prior_product,prior_host,prior_index,prior_manifest,
 reconcile,post_recovery,response,immutable_http,immutable_browser,
 production_http,production_browser,
)=sys.argv[1:]
prior=None if not prior_id else {
 "host_version":prior_host,"id":prior_id,"index_sha256":prior_index,
 "manifest_sha256":prior_manifest,"product_build":prior_product,"url":prior_url,
}
document={
 "action":action,
 "attempted_deploy":{"id":attempted_id,"url":attempted_url},
 "contract":"lmdj.web-runtime-host.deployment-recovery-evidence.v1",
 "original_status":int(original_status),
 "post_recovery_site":json.loads(post_recovery),
 "prior_deploy":prior,
 "reconcile":json.loads(reconcile),
 "recorded_at":recorded_at,
 "recovery_response":json.loads(response),
 "status":recovery_status,
 "validation":{
   "immutable_browser":json.loads(immutable_browser),
   "immutable_http":json.loads(immutable_http),
   "production_browser":json.loads(production_browser),
   "production_http":json.loads(production_http),
   "status":recovery_status,
 },
}
print(json.dumps(document,sort_keys=True,separators=(",",":")))
' "$original_status" "$recorded_at" "$recovery_action" "$recovery_status" \
    "${deploy_id:-}" "${deploy_url:-}" "$prior_deploy_id" "$prior_deploy_url" \
    "$prior_product_build" "$prior_host_version" "$prior_index_sha256" "$prior_manifest_sha256" \
    "$reconcile_site_json" "$post_recovery_site_json" "$recovery_response_json" \
    "$recovery_immutable_http_result" "$recovery_immutable_browser_result" \
    "$recovery_production_http_result" "$recovery_production_browser_result" |
    without_deploy_secrets timeout --signal=TERM --kill-after=5s "${recovery_evidence_timeout_seconds}s" \
      "$python_bin" "$orchestrator_tool" \
      evidence-write-document "$deploy_root/recovery-evidence.json" \
      lmdj.web-runtime-host.deployment-recovery-evidence.v1
}

run_http_smoke() {
  local base_url="$1"
  local expected_product="${2:-$product_build}"
  local expected_host="${3:-$host_version}"
  local expected_deploy_id="${4:-}"
  local expected_index_sha256="${5:-}"
  local expected_manifest_sha256="${6:-}"
  local timeout_seconds="${7:-}"
  local arguments=(
    "$repo_root/apps/web-runtime-host/tools/deployment_smoke.py"
    "$base_url"
    "$expected_product"
    "$expected_host"
  )
  local started_at=''
  local ended_at=''
  local raw_result=''
  if [[ -n "$expected_deploy_id" ]]; then
    arguments+=(--expected-deploy-id "$expected_deploy_id")
  fi
  started_at="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  local -a command=("$python_bin" "${arguments[@]}")
  if [[ -n "$timeout_seconds" ]]; then
    command=(timeout --signal=TERM --kill-after=5s "${timeout_seconds}s" "${command[@]}")
  fi
  raw_result="$({ without_deploy_secrets "${command[@]}"; })"
  without_deploy_secrets "$python_bin" -c '
import json,re,sys
value=json.loads(sys.stdin.read())
expected_index,expected_manifest=sys.argv[1:]
for key,expected in (("index_sha256",expected_index),("manifest_sha256",expected_manifest)):
    actual=value.get(key)
    if not isinstance(actual,str) or re.fullmatch(r"[0-9a-f]{64}",actual) is None:
        raise SystemExit("HTTP smoke digest is invalid")
    if expected and actual != expected:
        raise SystemExit("HTTP smoke bytes do not match the trusted source")
' "$expected_index_sha256" "$expected_manifest_sha256" <<<"$raw_result"
  ended_at="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  http_smoke_result="{\"ended_at\":\"$ended_at\",\"result\":$raw_result,\"started_at\":\"$started_at\",\"status\":\"passed\"}"
}

extract_http_digests() {
  without_deploy_secrets "$python_bin" -c '
import json,sys
value=json.load(sys.stdin)["result"]
print(value["index_sha256"] + " " + value["manifest_sha256"])
' <<<"$1"
}

run_browser_smoke() {
  local base_url="$1"
  local expected_product="${2:-$product_build}"
  local expected_host="${3:-$host_version}"
  local expected_deploy_id="${4:-}"
  local timeout_seconds="${5:-}"
  local started_at=''
  local ended_at=''
  started_at="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  local -a command=(npm --prefix "$repo_root/tests/platform/web" test -- \
      --project=chromium deployment/web_runtime_host_deployment.spec.mjs)
  if [[ -n "$timeout_seconds" ]]; then
    command=(timeout --signal=TERM --kill-after=5s "${timeout_seconds}s" "${command[@]}")
  fi
  without_deploy_secrets \
    LMDJ_WEB_HOST_CLEAN_ROOM=1 \
    LMDJ_WEB_HOST_EXTERNAL_SERVER=1 \
    LMDJ_WEB_HOST_BASE_URL="$base_url" \
    LMDJ_WEB_HOST_EXPECTED_PRODUCT_BUILD="$expected_product" \
    LMDJ_WEB_HOST_EXPECTED_VERSION="$expected_host" \
    "${command[@]}"
  ended_at="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  browser_smoke_result="{\"base_url\":\"$base_url\",\"deploy_id\":\"$expected_deploy_id\",\"ended_at\":\"$ended_at\",\"host_version\":\"$expected_host\",\"product_build\":\"$expected_product\",\"started_at\":\"$started_at\",\"status\":\"passed\"}"
}

publish_deploy() {
  publication_attempted=1
  publish_response_json="$(
    with_netlify_credential \
      "$python_bin" "$orchestrator_tool" publish \
        "$NETLIFY_RUNTIME_SITE_ID" "$deploy_id"
  )" || {
    fail "Netlify same-ID publication failed"
    return
  }
}

initialize_evidence_target() {
  without_deploy_secrets "$python_bin" "$orchestrator_tool" evidence-init \
    "$repo_root" "$deploy_root"
}

write_evidence() {
  local ended_at=''
  ended_at="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  without_deploy_secrets "$python_bin" -c '
import json,sys
(
 archive_name,archive_sha,revision,host,product,release_url,site_id,tag,
 run_id,started_at,ended_at,deploy_id,deploy_url,immutable_http,
 immutable_browser,publish_response,production_http,production_browser,
 prior_id,prior_url,prior_product,prior_host,prior_site,prior_immutable_http,
 prior_immutable_browser,prior_production_http,prior_production_browser,
 index_sha,manifest_sha,
)=sys.argv[1:]
prior_good=None
if prior_id:
    prior_good={
        "deploy_id":prior_id,
        "deploy_url":prior_url,
        "host_version":prior_host,
        "immutable":{"browser":json.loads(prior_immutable_browser),"http":json.loads(prior_immutable_http)},
        "product_build":prior_product,
        "production":{"browser":json.loads(prior_production_browser),"http":json.loads(prior_production_http)},
        "site_response":json.loads(prior_site),
    }
document={
 "archive":{"filename":archive_name,"sha256":archive_sha},
 "channel":"canary",
 "contract":"lmdj.web-runtime-host.deployment-evidence.v2",
 "ended_at":ended_at,
 "git_revision":revision,
 "github_actions":{"run_id":run_id,"run_url":f"https://github.com/endaye/lmdj/actions/runs/{run_id}"},
 "host_version":host,
 "immutable":{"browser":json.loads(immutable_browser),"deploy_id":deploy_id,"deploy_url":deploy_url,"http":json.loads(immutable_http)},
 "prior_good":prior_good,
 "product_build":product,
 "production":{"browser":json.loads(production_browser),"http":json.loads(production_http),"url":"https://lmdj-runtime.netlify.app"},
 "publication":{"response":json.loads(publish_response),"same_deploy_id":deploy_id},
 "release_files":{"index_sha256":index_sha,"manifest_sha256":manifest_sha},
 "release_url":release_url,
 "site_id":site_id,
 "started_at":started_at,
 "tag":tag,
}
print(json.dumps(document,sort_keys=True,separators=(",",":")))
' \
    "$archive_name" "$archive_sha256" "$tag_target" "$host_version" \
    "$product_build" "$release_url" "$NETLIFY_RUNTIME_SITE_ID" "$tag" \
    "$GITHUB_RUN_ID" "$deployment_started_at" "$ended_at" "$deploy_id" \
    "$deploy_url" "$immutable_http_result" "$immutable_browser_result" \
    "$publish_response_json" "$production_http_result" "$production_browser_result" \
    "$prior_deploy_id" "$prior_deploy_url" "$prior_product_build" \
    "$prior_host_version" "$current_site_json" \
    "$prior_immutable_http_result" "$prior_immutable_browser_result" \
    "$prior_production_http_result" "$prior_production_browser_result" \
    "$staged_index_sha256" "$staged_manifest_sha256" |
    without_deploy_secrets "$python_bin" "$orchestrator_tool" \
      evidence-write-document "$deploy_root/evidence.json" \
      lmdj.web-runtime-host.deployment-evidence.v2
}

deploy_release() {
  local selected_tag="$1"
  tag="$selected_tag"
  require_secret GITHUB_TOKEN
  require_secret NETLIFY_RUNTIME_SITE_ID
  require_secret NETLIFY_AUTH_TOKEN
  require_secret GITHUB_RUN_ID
  require_command timeout
  [[ "$GITHUB_RUN_ID" =~ ^[0-9]+$ ]] || fail "GitHub Actions run ID is invalid"
  [[ "${GITHUB_REPOSITORY:-}" == "$canonical_repository" ]] || fail "GitHub Actions repository is not canonical"
  [[ "${GITHUB_SERVER_URL:-}" == 'https://github.com' ]] || fail "GitHub Actions server URL is not canonical"
  deployment_started_at="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  initialize_evidence_target
  verify_release "$tag"
  preflight_prior_good
  create_draft_deploy
  run_http_smoke "$deploy_url" "$product_build" "$host_version" "$deploy_id" "$staged_index_sha256" "$staged_manifest_sha256"
  immutable_http_result="$http_smoke_result"
  run_browser_smoke "$deploy_url" "$product_build" "$host_version" "$deploy_id"
  immutable_browser_result="$browser_smoke_result"
  publish_deploy
  run_http_smoke "$production_url" "$product_build" "$host_version" '' "$staged_index_sha256" "$staged_manifest_sha256"
  production_http_result="$http_smoke_result"
  run_browser_smoke "$production_url" "$product_build" "$host_version" "$deploy_id"
  production_browser_result="$browser_smoke_result"
  write_evidence
  deployment_complete=1
  echo "Web Runtime Host deployment: PASS ($deploy_id)"
}

smoke_target() {
  local base_url="$1"
  product_build="$2"
  host_version="$3"
  run_http_smoke "$base_url" "$product_build" "$host_version"
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
    require_secret GITHUB_TOKEN
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
