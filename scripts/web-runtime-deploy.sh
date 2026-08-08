#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "$script_dir/.." && pwd -P)"
deploy_root="$repo_root/build/deploy/web-runtime-host"
tag_pattern='^lmdj-v([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)$'
production_url='https://lmdj-runtime.netlify.app'
trusted_fingerprint='2B5EE362F058800036AD4FB5116ECE156F954D29'
initial_tag='lmdj-v1.0.15.2'
initial_tag_target='72ae40074620cc5681c462ba04a31a666449734f'
initial_host_digest='d56a7c99a3c489db068b93fcef70a254b498adf4bc65919253beccb199f3ad5a'
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

cleanup_all() {
  local status=$?
  trap - EXIT INT TERM
  if [[ -n "$tag_checkout" ]]; then
    if ! git worktree remove --force "$tag_checkout" >/dev/null 2>&1; then
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

  tag_type="$(git cat-file -t "refs/tags/$tag" 2>/dev/null)" || {
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
  gpg --batch --import "$key_path" >/dev/null 2>&1 || {
    fail "trusted Product signing key import failed"
    return
  }
  if ! verify_status="$(git verify-tag --raw "$tag" 2>&1)"; then
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

  tag_target="$(git rev-parse --verify "${tag}^{commit}" 2>/dev/null)" || {
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
    "$python_bin" - tag-identity "$tag_checkout" "$product_build" <<'PY'
import json
from pathlib import Path
import re
import sys

root = Path(sys.argv[2])
expected_product = sys.argv[3]
try:
    product = json.loads((root / "products/lmdj/version.json").read_text(encoding="utf-8"))
    host = json.loads((root / "apps/web-runtime-host/module.json").read_text(encoding="utf-8"))
except (OSError, UnicodeDecodeError, json.JSONDecodeError):
    raise SystemExit("tag-target identity manifests are invalid")
if set(product) != {"contract", "product", "milestone", "minor", "build", "patch"}:
    raise SystemExit("tag-target Product identity is invalid")
if product["contract"] != "lmdj.product-version.v1" or product["product"] != "lmdj":
    raise SystemExit("tag-target Product identity is invalid")
parts = [product[name] for name in ("milestone", "minor", "build", "patch")]
if any(type(part) is not int or part < 0 for part in parts):
    raise SystemExit("tag-target Product identity is invalid")
observed_product = ".".join(str(part) for part in parts)
if observed_product != expected_product:
    raise SystemExit("tag-target Product Build does not match the tag")
if (
    not isinstance(host, dict)
    or host.get("contract") != "lmdj.module.v1"
    or host.get("module") != "web-runtime-host"
    or not isinstance(host.get("version"), str)
    or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", host["version"]) is None
):
    raise SystemExit("tag-target Host identity is invalid")
print(observed_product + "\t" + host["version"])
PY
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
    "$python_bin" - release-metadata \
      "$tag" "$tag_target" "$product_build" "$host_version" "$release_json" <<'PY'
import json
import re
import sys
from urllib.parse import urlsplit

tag, tag_target, product_build, host_version = sys.argv[2:6]
try:
    release = json.loads(sys.argv[6])
except (UnicodeDecodeError, json.JSONDecodeError):
    raise SystemExit("GitHub Release metadata is invalid")
required = {"tagName", "isDraft", "isPrerelease", "targetCommitish", "assets", "url"}
if not isinstance(release, dict) or set(release) != required:
    raise SystemExit("GitHub Release metadata is invalid")
if release["tagName"] != tag or release["isDraft"] is not False:
    raise SystemExit("GitHub Release is not the exact published Product tag")
if release["isPrerelease"] is not True:
    raise SystemExit("GitHub Release is not a canary prerelease")
if release["targetCommitish"] not in {tag, tag_target}:
    raise SystemExit("GitHub Release target does not match the Product tag")
assets = release["assets"]
if not isinstance(assets, list) or any(not isinstance(asset, dict) for asset in assets):
    raise SystemExit("GitHub Release asset inventory is invalid")
names = [asset.get("name") for asset in assets]
if any(not isinstance(name, str) or not name for name in names):
    raise SystemExit("GitHub Release asset inventory is invalid")
archive = f"lmdj-web-runtime-host-{host_version}-product-{product_build}.zip"
checksum = archive + ".sha256"
host_archives = [
    name for name in names
    if name.startswith("lmdj-web-runtime-host-") and name.endswith(".zip")
]
host_checksums = [
    name for name in names
    if name.startswith("lmdj-web-runtime-host-") and name.endswith(".zip.sha256")
]
if host_archives != [archive] or host_checksums != [checksum]:
    raise SystemExit("GitHub Release Host asset identity is invalid")
release_url = release["url"]
parsed = urlsplit(release_url) if isinstance(release_url, str) else None
if (
    parsed is None
    or parsed.scheme != "https"
    or parsed.hostname != "github.com"
    or parsed.username is not None
    or parsed.password is not None
    or parsed.port is not None
    or parsed.query
    or parsed.fragment
    or not parsed.path.endswith("/releases/tag/" + tag)
):
    raise SystemExit("GitHub Release URL is invalid")
for value in (archive, checksum, release_url):
    if "\t" in value or "\n" in value or "\r" in value:
        raise SystemExit("GitHub Release metadata contains unsafe text")
print("\t".join((archive, checksum, release_url)))
PY
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
  gh release download "$tag" \
    --pattern "$archive_name" \
    --pattern "$checksum_name" \
    --dir "$download_root" \
    --clobber >/dev/null || {
    fail "GitHub Release asset download failed"
    return
  }
  "$python_bin" - downloaded-assets \
    "$download_root" "$archive_name" "$checksum_name" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[2])
expected = sorted(sys.argv[3:5])
actual = sorted(
    path.name for path in root.iterdir()
    if path.is_file() and not path.is_symlink()
)
if actual != expected or any(path.is_dir() or path.is_symlink() for path in root.iterdir()):
    raise SystemExit("downloaded GitHub Release asset inventory is invalid")
PY
  archive_path="$download_root/$archive_name"
  checksum_path="$download_root/$checksum_name"
}

stage_release_assets() {
  local stage_root="$owned_temp/staged"
  local bundle_json=''
  local fields=''
  bundle_json="$(
    "$python_bin" "$repo_root/apps/web-runtime-host/tools/release_bundle.py" stage \
      --repo-root "$tag_checkout" \
      --archive "$archive_path" \
      --checksum "$checksum_path" \
      --output-root "$stage_root" \
      --expected-product-build "$product_build" \
      --expected-host-version "$host_version"
  )" || {
    fail "released Host bundle verification failed"
    return
  }
  fields="$(
    "$python_bin" - staged-bundle \
      "$stage_root" "$product_build" "$host_version" "$bundle_json" <<'PY'
import json
from pathlib import Path
import re
import sys

stage_root = Path(sys.argv[2]).resolve()
expected_product, expected_host = sys.argv[3:5]
try:
    staged = json.loads(sys.argv[5])
except (UnicodeDecodeError, json.JSONDecodeError):
    raise SystemExit("staged Host bundle result is invalid")
if not isinstance(staged, dict) or set(staged) != {
    "archive_sha256", "dist_root", "host_version", "product_build"
}:
    raise SystemExit("staged Host bundle result is invalid")
try:
    dist_root = Path(staged["dist_root"]).resolve(strict=True)
except (OSError, TypeError):
    raise SystemExit("staged Host bundle root is invalid")
if dist_root != stage_root / "dist" or not dist_root.is_dir() or dist_root.is_symlink():
    raise SystemExit("staged Host bundle root is invalid")
digest = staged["archive_sha256"]
if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
    raise SystemExit("staged Host archive digest is invalid")
if staged["product_build"] != expected_product or staged["host_version"] != expected_host:
    raise SystemExit("staged Host identity is invalid")
print("\t".join((str(dist_root), digest)))
PY
  )" || {
    fail "staged Host bundle result verification failed"
    return
  }
  IFS=$'\t' read -r dist_root archive_sha256 <<<"$fields"
  if [[ "$tag" == "$initial_tag" && "$archive_sha256" != "$initial_host_digest" ]]; then
    fail "initial Host archive SHA-256 mismatch"
    return
  fi
}

remove_tag_checkout() {
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
    gh release view "$tag" \
      --json tagName,isDraft,isPrerelease,targetCommitish,assets,url
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
  local draft_json=''
  local fields=''
  [[ -f "$headers_path" && ! -L "$headers_path" ]] || {
    fail "Netlify response rules are unavailable"
    return
  }
  draft_json="$(
    "$python_bin" - netlify-create-draft \
      "$dist_root" "$headers_path" "$product_build" "$host_version" "$tag" <<'PY'
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

dist_root = Path(sys.argv[2]).resolve(strict=True)
headers_path = Path(sys.argv[3]).resolve(strict=True)
product_build, host_version, tag = sys.argv[4:7]
module_root = Path.cwd() / "apps/web-runtime-host/tools"
sys.path.insert(0, str(module_root))
from netlify_api import NetlifyClient

files = {}
for path in sorted(dist_root.rglob("*")):
    if path.is_symlink():
        raise SystemExit("staged distribution contains a symlink")
    if path.is_dir():
        continue
    if not path.is_file():
        raise SystemExit("staged distribution contains an unsafe entry")
    files["/" + path.relative_to(dist_root).as_posix()] = path.read_bytes()
if not files:
    raise SystemExit("staged distribution is empty")
files["/_headers"] = headers_path.read_bytes()
api_base = os.environ.get("LMDJ_NETLIFY_API_BASE", "https://api.netlify.com/api/v1")
if api_base != "https://api.netlify.com/api/v1":
    parsed = urlsplit(api_base)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}:
        raise SystemExit("Netlify API test endpoint must be loopback HTTP")
draft = NetlifyClient(
    token=os.environ["NETLIFY_AUTH_TOKEN"], api_base=api_base
).create_draft(
    site_id=os.environ["NETLIFY_RUNTIME_SITE_ID"],
    files=files,
    title=f"LMDJ Product {product_build} Host {host_version} ({tag})",
)
print(json.dumps({
    "deploy_ssl_url": draft.deploy_ssl_url,
    "id": draft.id,
    "site_id": draft.site_id,
    "state": draft.state,
}, sort_keys=True, separators=(",", ":")))
PY
  )" || {
    fail "Netlify draft deploy creation failed"
    return
  }
  fields="$(
    "$python_bin" - draft-identity "$NETLIFY_RUNTIME_SITE_ID" "$draft_json" <<'PY'
import json
import re
import sys
from urllib.parse import urlsplit

site_id = sys.argv[2]
try:
    draft = json.loads(sys.argv[3])
except (UnicodeDecodeError, json.JSONDecodeError):
    raise SystemExit("Netlify draft identity is invalid")
if not isinstance(draft, dict) or set(draft) != {"deploy_ssl_url", "id", "site_id", "state"}:
    raise SystemExit("Netlify draft identity is invalid")
deploy_id = draft["id"]
if not isinstance(deploy_id, str) or re.fullmatch(r"[A-Za-z0-9-]+", deploy_id) is None:
    raise SystemExit("Netlify Deploy ID is invalid")
if draft["site_id"] != site_id or draft["state"] != "ready":
    raise SystemExit("Netlify draft identity is invalid")
url = draft["deploy_ssl_url"]
parsed = urlsplit(url) if isinstance(url, str) else None
if (
    parsed is None
    or parsed.scheme != "https"
    or parsed.hostname is None
    or not parsed.hostname.endswith(".netlify.app")
    or not parsed.hostname.startswith(deploy_id.lower() + "--")
    or parsed.username is not None
    or parsed.password is not None
    or parsed.port is not None
    or parsed.path not in {"", "/"}
    or parsed.query
    or parsed.fragment
):
    raise SystemExit("Netlify immutable Deploy URL is invalid")
print("\t".join((deploy_id, url)))
PY
  )" || {
    fail "Netlify draft deploy identity verification failed"
    return
  }
  IFS=$'\t' read -r deploy_id deploy_url <<<"$fields"
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
  "$python_bin" "${arguments[@]}" >/dev/null
}

run_browser_smoke() {
  local base_url="$1"
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
  local published_json=''
  published_json="$(
    "$python_bin" - netlify-publish \
      "$NETLIFY_RUNTIME_SITE_ID" "$deploy_id" <<'PY'
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

site_id, deploy_id = sys.argv[2:4]
sys.path.insert(0, str(Path.cwd() / "apps/web-runtime-host/tools"))
from netlify_api import NetlifyClient

api_base = os.environ.get("LMDJ_NETLIFY_API_BASE", "https://api.netlify.com/api/v1")
if api_base != "https://api.netlify.com/api/v1":
    parsed = urlsplit(api_base)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}:
        raise SystemExit("Netlify API test endpoint must be loopback HTTP")
published = NetlifyClient(
    token=os.environ["NETLIFY_AUTH_TOKEN"], api_base=api_base
).publish_deploy(site_id=site_id, deploy_id=deploy_id)
print(json.dumps(published, sort_keys=True, separators=(",", ":")))
PY
  )" || {
    fail "Netlify same-ID publication failed"
    return
  }
  "$python_bin" - published-identity \
    "$NETLIFY_RUNTIME_SITE_ID" "$deploy_id" "$production_url" "$published_json" <<'PY'
import json
import sys

site_id, deploy_id, production_url = sys.argv[2:5]
try:
    published = json.loads(sys.argv[5])
except (UnicodeDecodeError, json.JSONDecodeError):
    raise SystemExit("Netlify published identity is invalid")
if (
    not isinstance(published, dict)
    or set(published) != {"id", "site_id", "ssl_url", "state"}
    or published["id"] != deploy_id
    or published["site_id"] != site_id
    or published["ssl_url"] != production_url
    or published["state"] != "ready"
):
    raise SystemExit("Netlify published identity is not the same ready Deploy")
PY
}

initialize_evidence_target() {
  "$python_bin" - evidence-init "$repo_root" "$deploy_root" <<'PY'
from pathlib import Path
import sys

repo_root = Path(sys.argv[2]).resolve(strict=True)
deploy_root = Path(sys.argv[3])
current = repo_root
for component in deploy_root.relative_to(repo_root).parts:
    current = current / component
    if current.exists() or current.is_symlink():
        if current.is_symlink() or not current.is_dir():
            raise SystemExit("deployment evidence path is unsafe")
    else:
        current.mkdir()
evidence = deploy_root / "evidence.json"
if evidence.is_symlink() or evidence.exists():
    evidence.unlink()
PY
}

write_evidence() {
  "$python_bin" - evidence-write \
    "$deploy_root/evidence.json" \
    "$archive_sha256" "$deploy_id" "$deploy_url" "$tag_target" \
    "$host_version" "$product_build" "$production_url" "$release_url" \
    "$NETLIFY_RUNTIME_SITE_ID" "$tag" <<'PY'
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlsplit

(
    output_name, archive_sha256, deploy_id, deploy_url, git_revision,
    host_version, product_build, production_url, release_url, site_id, tag,
) = sys.argv[2:13]
if re.fullmatch(r"[0-9a-f]{64}", archive_sha256) is None:
    raise SystemExit("deployment evidence archive digest is invalid")
if re.fullmatch(r"[0-9a-f]{40}", git_revision) is None:
    raise SystemExit("deployment evidence Git revision is invalid")
if re.fullmatch(r"[A-Za-z0-9-]+", deploy_id) is None or re.fullmatch(r"[A-Za-z0-9-]+", site_id) is None:
    raise SystemExit("deployment evidence live identity is invalid")
for url in (deploy_url, production_url, release_url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname is None or parsed.username or parsed.password:
        raise SystemExit("deployment evidence URL is invalid")
evidence = {
    "archive_sha256": archive_sha256,
    "channel": "canary",
    "contract": "lmdj.web-runtime-host.deployment-evidence.v1",
    "deploy_id": deploy_id,
    "deploy_url": deploy_url,
    "git_revision": git_revision,
    "host_version": host_version,
    "product_build": product_build,
    "production_url": production_url,
    "release_url": release_url,
    "site_id": site_id,
    "tag": tag,
}
serialized = json.dumps(evidence, sort_keys=True, separators=(",", ":")) + "\n"
output = Path(output_name)
if output.is_symlink() or not output.parent.is_dir() or output.parent.is_symlink():
    raise SystemExit("deployment evidence target is unsafe")
descriptor, temporary_name = tempfile.mkstemp(prefix=".evidence.", dir=output.parent)
try:
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as target:
        target.write(serialized)
        target.flush()
        os.fsync(target.fileno())
    os.replace(temporary_name, output)
finally:
    try:
        os.unlink(temporary_name)
    except FileNotFoundError:
        pass
PY
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
    verify_release "$tag"
    echo "Web Runtime Host release verification: PASS ($tag)"
    ;;
  deploy)
    [[ $# -eq 1 ]] || { usage; exit 64; }
    validate_tag "$1"
    for command in git gpg gh "$python_bin" npm; do
      require_command "$command"
    done
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
