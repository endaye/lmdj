#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "$script_dir/.." && pwd -P)"
orchestrator_tool="$repo_root/apps/creator-web/tools/deploy_orchestrator.py"
tag_pattern='^lmdj-v([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)$'
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
tag_checkout=''
release_asset_inventory=''

usage() {
  cat >&2 <<'EOF'
usage:
  scripts/creator-web-deploy.sh verify TAG
  scripts/creator-web-deploy.sh stage TAG ABSOLUTE_OUTPUT_DIRECTORY
EOF
}

fail() {
  echo "Creator Web deployment error: $1" >&2
  return 2
}

with_gh_environment_removed() {
  local -a unset_arguments=()
  local name=''
  while IFS= read -r name; do
    # An `&&` list whose test fails returns non-zero, which set -e treats as a
    # fatal statement, so the append must be a plain conditional.
    if [[ "$name" == GH* ]]; then
      unset_arguments+=(-u "$name")
    fi
  done < <(compgen -e)
  # bash 3.2 treats "${array[@]}" on an empty array as an unbound variable
  # under set -u, so an environment with no GH* variable must expand to
  # nothing rather than to an error. GITHUB_* does not match GH*: callers
  # that must not pass GITHUB_TOKEN remove it with an explicit -u.
  env ${unset_arguments[@]+"${unset_arguments[@]}"} "$@"
}

without_deploy_secrets() {
  with_gh_environment_removed \
    -u GITHUB_TOKEN \
    -u GITHUB_ENTERPRISE_TOKEN \
    -u CLOUDFLARE_API_TOKEN \
    "$@"
}

with_pinned_github() {
  with_gh_environment_removed \
    -u GITHUB_ENTERPRISE_TOKEN \
    -u CLOUDFLARE_API_TOKEN \
    "$@"
}

with_pinned_github_git() {
  GIT_TERMINAL_PROMPT=0 with_pinned_github git \
    -c credential.username=x-access-token \
    -c 'credential.helper=!f() { if test "$1" = get && test -n "${GITHUB_TOKEN:-}"; then printf "%s\n" "username=x-access-token" "password=$GITHUB_TOKEN"; fi; }; f' \
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
  if [[ -n "$remote_tag_ref" ]]; then
    without_deploy_secrets git update-ref -d "$remote_tag_ref" >/dev/null 2>&1 || status=2
    remote_tag_ref=''
  fi
  without_deploy_secrets git update-ref -d "$remote_main_ref" >/dev/null 2>&1 || status=2
  if [[ -n "$tag_checkout" ]]; then
    if ! remove_tag_checkout_path "$tag_checkout"; then
      echo "Creator Web deployment error: detached tag checkout cleanup failed" >&2
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
      "$basename" != lmdj-creator-web-deploy.* || \
      -L "$owned_temp" || \
      ! -d "$owned_temp" \
    ]]; then
      echo "Creator Web deployment error: refusing unsafe temporary cleanup" >&2
      status=2
    elif ! rm -rf -- "$owned_temp"; then
      echo "Creator Web deployment error: temporary cleanup failed" >&2
      status=2
    fi
    owned_temp=''
  fi
  exit "$status"
}

trap cleanup_all EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# A GnuPG home holds the agent socket, whose absolute path must fit the
# platform sun_path limit. macOS per-user TMPDIR values are long enough that
# "<parent>/lmdj-creator-web-deploy.XXXXXX/gnupg/S.gpg-agent" overflows it by a
# single character, and gpg then exits non-zero on an otherwise successful
# public-key import. Linux runners use a short TMPDIR and never reach it.
_GNUPG_SOCKET_BUDGET=104

owned_temp_parent_fits_gnupg_socket() {
  local parent="$1"
  local projected="$parent/lmdj-creator-web-deploy.XXXXXX/gnupg/S.gpg-agent"
  (( ${#projected} <= _GNUPG_SOCKET_BUDGET ))
}

create_owned_temp() {
  local requested_parent="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
  [[ -d "$requested_parent" && ! -L "$requested_parent" ]] || {
    fail "temporary parent is unavailable"
    return
  }
  owned_temp_parent="$(cd "$requested_parent" && pwd -P)"
  if ! owned_temp_parent_fits_gnupg_socket "$owned_temp_parent"; then
    [[ -d /tmp ]] || {
      fail "temporary parent exceeds the GnuPG socket budget"
      return
    }
    owned_temp_parent="$(cd /tmp && pwd -P)"
    owned_temp_parent_fits_gnupg_socket "$owned_temp_parent" || {
      fail "temporary parent exceeds the GnuPG socket budget"
      return
    }
  fi
  owned_temp="$(mktemp -d "$owned_temp_parent/lmdj-creator-web-deploy.XXXXXX")"
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
  local tag_file="$owned_temp/product-tag"

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

  mkdir -m 700 "$owned_temp/gnupg"
  export GNUPGHOME="$owned_temp/gnupg"
  key_fingerprint="$(
    without_deploy_secrets \
      gpg --batch --no-tty --no-autostart --homedir "$GNUPGHOME" \
        --show-keys --with-colons "$key_path" 2>/dev/null |
      awk -F: '$1 == "fpr" {print $10; exit}'
  )" || {
    fail "trusted Product signing key is unavailable"
    return
  }
  [[ "$key_fingerprint" == "$trusted_tag_fingerprint" ]] || {
    fail "trusted Product signing key fingerprint mismatch"
    return
  }
  without_deploy_secrets \
    gpg --batch --no-tty --no-autostart --homedir "$GNUPGHOME" \
      --import "$key_path" >/dev/null 2>&1 || {
    fail "trusted Product signing key import failed"
    return
  }
  without_deploy_secrets git cat-file tag "$remote_tag_ref" >"$tag_file" 2>/dev/null || {
    fail "Product tag signature input is unavailable"
    return
  }
  if ! without_deploy_secrets python3 "$repo_root/tools/release/tag_verifier.py" \
    --homedir "$GNUPGHOME" \
    --tag-file "$tag_file" \
    --fingerprint "$trusted_tag_fingerprint"; then
    fail "Product tag signature verification failed"
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
  IFS=$'\t' read -r archive_name checksum_name signature_name release_url release_asset_inventory <<<"$fields"
  [[ \
    -n "$archive_name" && \
    "$checksum_name" == "$archive_name.sha256" && \
    "$signature_name" == "$checksum_name.asc" && \
    -n "$release_url" && \
    "$release_asset_inventory" =~ ^[A-Za-z0-9._,-]+$ && \
    ",$release_asset_inventory," == *",$archive_name,"* && \
    ",$release_asset_inventory," == *",$checksum_name,"* && \
    ",$release_asset_inventory," == *",$signature_name,"* \
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
    --dir "$download_root" \
    --clobber >/dev/null 2>&1 || {
    fail "GitHub Release asset download failed"
    return
  }
  without_deploy_secrets "$python_bin" "$orchestrator_tool" downloaded-assets \
    "$download_root" "$archive_name" "$checksum_name" "$signature_name" \
    "$release_asset_inventory" || {
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
      "$python_bin" "$repo_root/apps/creator-web/tools/release_bundle.py" stage \
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

[[ $# -ge 1 ]] || {
  usage
  exit 64
}

command_name="$1"
shift
cd "$repo_root"

case "$command_name" in
  verify|stage)
    if [[ "$command_name" == stage ]]; then
      [[ $# -eq 2 ]] || { usage; exit 64; }
      stage_output="$2"
      [[ "$stage_output" == /* && ! -e "$stage_output" && ! -L "$stage_output" ]] || {
        fail "stage output must be an absent absolute directory"; exit 2;
      }
    else
      [[ $# -eq 1 ]] || { usage; exit 64; }
    fi
    require_secret GITHUB_TOKEN
    validate_tag "$1"
    tag="$1"
    for command in git gpg gh "$python_bin"; do
      require_command "$command"
    done
    [[ -f "$orchestrator_tool" ]] || fail "deployment orchestrator is unavailable"
    verify_release "$tag"
    if [[ "$command_name" == stage ]]; then
      without_deploy_secrets "$python_bin" "$repo_root/apps/web-runtime-host/tools/cloudflare_release_stage.py" \
        --repo-root "$repo_root" --source "$tag_target" --tag "$tag" \
        --dist "$dist_root" --archive "$archive_path" --checksum "$checksum_path" \
        --signature "$signature_path" --archive-sha256 "$archive_sha256" \
        --index-sha256 "$staged_index_sha256" --manifest-sha256 "$staged_manifest_sha256" \
        --output "$stage_output"
    fi
    echo "Creator Web Host release verification: PASS ($tag)"
    ;;
  *)
    usage
    exit 64
    ;;
esac
