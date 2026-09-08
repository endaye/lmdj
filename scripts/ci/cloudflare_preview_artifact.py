"""Validate an untrusted static ZIP before a trusted publisher receives it.

This module executes no uploaded code and performs no network or deployment
operations. Callers must obtain run/PR/artifact metadata from authenticated
GitHub APIs, not from files inside the archive.
"""
from hashlib import sha256
from pathlib import Path, PurePosixPath
import json
import shutil
import tempfile
import re
import stat
from zipfile import ZipFile

REPOSITORY = "endaye/lmdj"
WORKFLOW = ".github/workflows/cloudflare-preview-build.yml"
MAX_FILES = 20_000
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_ZIP_BYTES = 256 * 1024 * 1024


def require(condition, why):
    if not condition:
        raise ValueError(f"why: {why}; remedy: rebuild the exact PR head with the trusted Preview workflow")


def validate_identity(run, pr, artifact):
    """Bind API objects to an open same-repository PR at its current exact head."""
    head = pr["head"]["sha"]
    require(bool(re.fullmatch(r"[0-9a-f]{40}", head)), "invalid head SHA")
    require(pr["state"] == "open", "PR is no longer open")
    require(pr["base"]["repo"]["full_name"] == REPOSITORY, "foreign base repository")
    require(pr["head"]["repo"]["full_name"] == REPOSITORY, "external PR publication is not enabled")
    require(pr["base"]["ref"] == "main", "unexpected PR base")
    require(run["repository"]["full_name"] == REPOSITORY, "foreign build repository")
    require(run["head_repository"]["full_name"] == REPOSITORY, "foreign build source")
    require(run["path"] == WORKFLOW, "unexpected build workflow")
    require(run["event"] == "pull_request", "unexpected build event")
    require(run["status"] == "completed" and run["conclusion"] == "success", "build did not succeed")
    require(run["head_sha"] == head, "build is stale")
    require(any(item["number"] == pr["number"] and item["head"]["sha"] == head
                for item in run["pull_requests"]), "build does not identify this PR head")
    require(artifact["workflow_run"]["id"] == run["id"], "artifact belongs to another run")
    require(artifact["workflow_run"]["head_sha"] == head, "artifact belongs to another head")
    require(artifact["name"] == f"portal-preview-{head}-{run['run_attempt']}", "artifact attempt/name mismatch")
    require(not artifact["expired"], "artifact has expired")
    require(0 < artifact["size_in_bytes"] <= MAX_ZIP_BYTES, "artifact archive exceeds limit")
    return {"pr_number": pr["number"], "head_sha": head,
            "run_id": run["id"], "run_attempt": run["run_attempt"], "artifact_id": artifact["id"]}


def extract_static(archive, destination):
    """Extract only regular static files to a new private directory.

    Returns an independently computed manifest; uploaded manifests are not
    trusted. Failure removes only files created by this invocation. No callers
    may upload a partially extracted tree or load config from this directory.
    """
    archive, destination = Path(archive), Path(destination)
    require(0 < archive.stat().st_size <= MAX_ZIP_BYTES, "ZIP size exceeds limit")
    require(not destination.exists(), "extraction target already exists")
    entries = []
    with ZipFile(archive) as zipped:
        infos = zipped.infolist()
        require(0 < len(infos) <= MAX_FILES, "ZIP entry count exceeds limit")
        names = set()
        total = 0
        for info in infos:
            name = info.filename
            parts = PurePosixPath(name).parts
            require(name and not name.startswith('/') and '\\' not in name and
                    all(ord(c) >= 32 and ord(c) != 127 for c in name) and
                    all(p not in {'.', '..', ''} for p in name.split('/')),
                    "unsafe ZIP path")
            require(not info.is_dir(), "directory entries are not part of the static ZIP contract")
            require(name not in names, "duplicate ZIP path")
            names.add(name)
            mode = info.external_attr >> 16
            require(stat.S_IFMT(mode) in {0, stat.S_IFREG}, "ZIP contains a non-regular file")
            require(not info.flag_bits & 1, "encrypted ZIP member")
            require(0 <= info.file_size <= MAX_FILE_BYTES, "static file exceeds limit")
            require(not any(p.startswith('.') for p in parts), "hidden files are not publishable")
            require(parts[0] not in {'_worker.js', '_routes.json', 'wrangler.json', 'wrangler.toml',
                                     'wrangler.jsonc', '_redirects', '_headers'},
                    "uploaded deployment configuration is forbidden")
            total += info.file_size
            require(total <= MAX_TOTAL_BYTES, "expanded static archive exceeds limit")
        require({'index.html', '404.html'} <= names, "required static entry pages are missing")
        require(all('/'.join(PurePosixPath(name).parts[:n]) not in names
                    for name in names for n in range(1, len(PurePosixPath(name).parts))),
                "ZIP file/directory path collision")
        destination.mkdir(mode=0o700)
        created = []
        try:
            for info in infos:
                target = destination / info.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                with zipped.open(info) as source, target.open('xb') as output:
                    created.append(target)
                    digest = sha256()
                    size = 0
                    while chunk := source.read(1024 * 1024):
                        size += len(chunk)
                        require(size <= info.file_size, "expanded size differs from ZIP metadata")
                        digest.update(chunk)
                        output.write(chunk)
                require(size == info.file_size, "truncated ZIP member")
                entries.append({'path': info.filename, 'bytes': size, 'sha256': digest.hexdigest()})
        except BaseException:
            for target in reversed(created):
                target.unlink()
            for directory in sorted((p for p in destination.rglob('*') if p.is_dir()),
                                    key=lambda p: len(p.parts), reverse=True):
                directory.rmdir()
            destination.rmdir()
            raise
    return sorted(entries, key=lambda entry: entry['path'])


def package_static(source, archive):
    """Create the inner static ZIP consumed by extract_static.

    The CI artifact transport may wrap this ZIP. Publishers must validate and
    unwrap that transport separately; a producer manifest is never authority.
    Only the known build-only .nojekyll and provider _headers files are omitted.
    Trusted publication supplies its own headers. No configuration is executed.
    """
    source, archive = Path(source), Path(archive)
    require(source.is_dir() and not source.is_symlink(), "static source is not a real directory")
    source = source.resolve()
    require(not archive.resolve().is_relative_to(source), "archive target is inside static source")
    require(not archive.exists(), "archive target already exists")
    require(archive.parent.is_dir(), "archive parent directory is missing")
    with tempfile.TemporaryDirectory(prefix='portal-static-', dir=archive.parent) as temporary:
        temporary = Path(temporary)
        candidate = temporary / 'static.zip'
        paths = []
        total = 0
        for path in source.rglob('*'):
            require(not path.is_symlink(), "static source contains a symlink")
            if path.is_dir():
                continue
            require(path.is_file(), "static source contains a non-regular file")
            name = path.relative_to(source).as_posix()
            if name in {'_headers', '.nojekyll'}:
                continue
            size = path.stat().st_size
            require(size <= MAX_FILE_BYTES, "static file exceeds limit")
            total += size
            require(total <= MAX_TOTAL_BYTES, "static source exceeds total limit")
            paths.append((name, path))
            require(len(paths) <= MAX_FILES, "static source exceeds file count")
        with ZipFile(candidate, 'w') as zipped:
            for name, path in sorted(paths):
                zipped.write(path, name)
        manifest = extract_static(candidate, temporary / 'verified')
        with candidate.open('rb') as content:
            digest = sha256()
            while chunk := content.read(1024 * 1024):
                digest.update(chunk)
        created = False
        try:
            with archive.open('xb') as output, candidate.open('rb') as content:
                created = True
                shutil.copyfileobj(content, output)
        except BaseException:
            if created:
                archive.unlink()
            raise
    return {'archive_sha256': digest.hexdigest(), 'archive_bytes': archive.stat().st_size,
            'files': manifest}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--archive', required=True)
    args = parser.parse_args()
    print(json.dumps(package_static(args.source, args.archive), sort_keys=True))
