#!/usr/bin/env bash
set -euo pipefail

# Reproducible, test-only proof of the real pinned PR-Agent handler seam.
# Production never downloads or installs anything here: the exported bundle
# owns its source, dependencies and identity.  This lane prepares an isolated
# equivalent from a fixed archive so a clean CI checkout cannot silently skip
# the actual PRReviewer/LiteLLMAIHandler import and call path.

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
RUNTIME=${PR_AGENT_TEST_PREP_PYTHON:-python3.12}
SOURCE_URL=https://github.com/the-pr-agent/pr-agent/archive/53072488e4c3b5a6c9ae730fe6fb52fc5f09d06c.tar.gz
SOURCE_ARCHIVE_SHA256=820c83581a16b32d8b60b8dff068a0c76eda1ee04be3621bb6f91a08dd666780
SOURCE_COMMIT=53072488e4c3b5a6c9ae730fe6fb52fc5f09d06c
SOURCE_VERSION=0.45.0

fail() {
  echo "pr-agent integration: $*" >&2
  exit 2
}

command -v curl >/dev/null 2>&1 || fail "curl is required; remedy: install curl or mark this lane not-runnable-here"
command -v "$RUNTIME" >/dev/null 2>&1 || fail "Python 3.12 is required; remedy: provide python3.12 or set PR_AGENT_TEST_PREP_PYTHON"

WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/lmdj-pr-agent-integration.XXXXXX")
trap 'rm -rf "$WORK_DIR"' EXIT
ARCHIVE="$WORK_DIR/pr-agent-source.tar.gz"
SOURCE_ROOT="$WORK_DIR/source"
VENV="$WORK_DIR/venv"

"$RUNTIME" -c 'import sys; assert sys.version_info[:2] == (3, 12), sys.version' \
  || fail "selected runtime is not Python 3.12"

curl --fail --silent --show-error --location --output "$ARCHIVE" "$SOURCE_URL"
"$RUNTIME" - "$ARCHIVE" "$SOURCE_ARCHIVE_SHA256" <<'PY'
import hashlib
import pathlib
import sys

archive = pathlib.Path(sys.argv[1])
expected = sys.argv[2]
actual = hashlib.sha256(archive.read_bytes()).hexdigest()
if actual != expected:
    raise SystemExit(f"source archive hash mismatch: {actual}")
PY
"$RUNTIME" - "$ARCHIVE" "$SOURCE_ROOT" "$SOURCE_COMMIT" "$SOURCE_VERSION" <<'PY'
import hashlib
import pathlib
import sys
import tarfile

archive_path = pathlib.Path(sys.argv[1])
destination = pathlib.Path(sys.argv[2])
destination.mkdir(parents=True)
destination.chmod(0o755)

def protected_mode(mode: int, default: int) -> int:
    return (mode & 0o777 & ~0o022) or default

def safe_relative(name: str) -> pathlib.PurePosixPath | None:
    parts = pathlib.PurePosixPath(name).parts
    if len(parts) == 1:
        return None
    if parts[0] in ("", ".", "..") or any(part in ("", ".", "..") for part in parts[1:]):
        raise SystemExit(f"unsafe source archive member: {name!r}")
    relative = pathlib.PurePosixPath(*parts[1:])
    if relative == pathlib.PurePosixPath("LICENSE"):
        return relative
    if relative == pathlib.PurePosixPath("pr_agent") or pathlib.PurePosixPath("pr_agent") in relative.parents:
        return relative
    return None

with tarfile.open(archive_path, "r:gz") as bundle:
    for member in bundle:
        relative = safe_relative(member.name)
        if relative is None:
            continue
        if member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
            raise SystemExit(f"unsupported source archive member: {member.name!r}")
        target = destination / relative
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
            target.chmod(protected_mode(member.mode, 0o755))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.parent.chmod(0o755)
        with bundle.extractfile(member) as source, target.open("wb") as output:
            output.write(source.read())
        target.chmod(protected_mode(member.mode, 0o644))

def tree_digest(root: pathlib.Path) -> str:
    entries = []
    for candidate in (root / "LICENSE", root / "pr_agent"):
        if not candidate.exists() or candidate.is_symlink():
            raise SystemExit(f"source identity path is missing or symlinked: {candidate}")
        paths = [candidate] if candidate.is_file() else sorted(candidate.rglob("*"))
        for path in paths:
            if path.is_symlink():
                raise SystemExit(f"source identity path is symlinked: {path}")
            if path.is_dir() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            if not path.is_file():
                raise SystemExit(f"unsupported source identity entry: {path}")
            data = path.read_bytes()
            relative = path.relative_to(root).as_posix()
            entries.append(f"{relative}\0{len(data)}\0".encode() + data)
    if not entries:
        raise SystemExit("source tree has no regular files")
    return hashlib.sha256(b"".join(entries)).hexdigest()

if not (destination / "LICENSE").is_file() or not (destination / "pr_agent").is_dir():
    raise SystemExit("pinned source archive did not contain LICENSE and pr_agent")
(destination / "IDENTITY").write_text(
    "schema=lmdj.pr-agent-bundle.v1\n"
    f"source_commit={sys.argv[3]}\n"
    f"source_version={sys.argv[4]}\n"
    f"source_tree_sha256={tree_digest(destination)}\n",
    encoding="utf-8",
)
PY

"$RUNTIME" -m venv "$VENV"
BOOTSTRAP_REQUIREMENTS="$WORK_DIR/bootstrap-requirements.txt"
printf '%s\n' \
  'setuptools==80.9.0 --hash=sha256:062d34222ad13e0cc312a4c02d73f059e86a4acbfbdea8f8f76b28c99f306922 --hash=sha256:f36b47402ecde768dbfafc46e8e4207b4360c654f1f3bb84475f0a28628fb19c' \
  'wheel==0.46.1 --hash=sha256:f796f65d72750ccde090663e466d0ca37cd72b62870f7520b96d34cdc07d86d8 --hash=sha256:fd477efb5da0f7df1d3c76c73c14394002c844451bd63229d8570f376f5e6a38' \
  'packaging==25.0 --hash=sha256:29572ef2b1f17581046b3a2227d5c611fb25ec70ca1ba8554b24b0e69331a484 --hash=sha256:d443872c98d677bf60f6a1f2f8c1cb748e8fe762d2bf9d3148b5599295b0fc4f' \
  > "$BOOTSTRAP_REQUIREMENTS"
PIP_DISABLE_PIP_VERSION_CHECK=1 "$VENV/bin/python" -m pip install \
  --no-compile --no-deps --require-hashes --requirement "$BOOTSTRAP_REQUIREMENTS"
PIP_DISABLE_PIP_VERSION_CHECK=1 "$VENV/bin/python" -m pip install \
  --no-compile --no-build-isolation --require-hashes --requirement \
  "$ROOT_DIR/scripts/ci/pr-agent/requirements.lock"

env \
  PR_AGENT_RUN_INTEGRATION=1 \
  PR_AGENT_TEST_PYTHON="$VENV/bin/python" \
  PR_AGENT_TEST_SOURCE_ROOT="$SOURCE_ROOT" \
  python3 "$ROOT_DIR/tests/build/ci_pr_agent_review_test.py"

echo "pr-agent integration: passed pinned Python 3.12 real-handler seam proof"
