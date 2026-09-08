#!/usr/bin/env python3
"""Pack and verify deterministic lmdj.project-bundle.v1 transfer files."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import BinaryIO, Iterator


MAGIC = b"LMDJBND1"
MAX_INDEX_BYTES = 4_194_304
MAX_ENTRIES = 4_096
MAX_PATH_BYTES = 255
MAX_ENTRY_BYTES = 67_108_864
MAX_PAYLOAD_BYTES = 536_870_912
CHUNK_BYTES = 1_048_576

_ROOT_KEYS = {
    "bundle_digest",
    "compression",
    "contract",
    "contract_version",
    "entries",
    "project_contract",
    "project_id",
    "uncompressed_bytes",
}
_ENTRY_KEYS = {"bytes", "offset", "path", "sha256"}
# The container version this tool writes, and every container version it
# still reads. Widening the Project Contract enum is an additive Contract
# MINOR, so a 1.2.0 reader accepts every 1.0.0 and 1.1.0 index unchanged.
CONTRACT_VERSION = "1.2.0"
READABLE_CONTRACT_VERSIONS = frozenset({"1.0.0", "1.1.0", CONTRACT_VERSION})
# Every Project Contract level a Bundle may name. `lmdj.project.v4` is the
# only level this Build writes, so omitting it made every new Project
# unpackable (#784).
PROJECT_CONTRACTS = frozenset({
    "lmdj.project.v1",
    "lmdj.project.v2",
    "lmdj.project.v3",
    "lmdj.project.v4",
})
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z"
)
_PATH = re.compile(r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*\Z")
_CHECKPOINT = re.compile(r"history/checkpoints/(?:0|[1-9][0-9]*)\.json\Z")


class BundleError(ValueError):
    """The Project Bundle or source tree violates the transfer Contract."""


@dataclass(frozen=True)
class _SourceFile:
    relative: str
    path: Path
    size: int
    device: int
    inode: int


def canonical_json(value: object) -> bytes:
    """Return the single canonical JSON representation used by the Contract."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def bundle_digest(index: dict) -> str:
    """Hash the canonical index with only bundle_digest omitted."""
    if not isinstance(index, dict):
        raise BundleError("bundle index must be an object")
    digest_source = dict(index)
    digest_source.pop("bundle_digest", None)
    return hashlib.sha256(canonical_json(digest_source)).hexdigest()


def _json_object(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise BundleError(f"bundle index has duplicate JSON key: {key}")
        result[key] = value
    return result


def _decode_canonical_index(encoded: bytes) -> dict:
    if encoded.startswith(b"\xef\xbb\xbf"):
        raise BundleError("bundle index must not contain a UTF-8 BOM")
    try:
        text = encoded.decode("utf-8", errors="strict")
        value = json.loads(text, object_pairs_hook=_json_object)
    except BundleError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BundleError(f"bundle index is not valid UTF-8 JSON: {error}") from error
    if not isinstance(value, dict):
        raise BundleError("bundle index must be an object")
    try:
        canonical = canonical_json(value)
    except (TypeError, ValueError) as error:
        raise BundleError(f"bundle index cannot be canonicalized: {error}") from error
    if canonical != encoded:
        raise BundleError("bundle index is not canonical JSON")
    return value


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise BundleError(f"{label} must be a nonnegative integer")
    return value


def _validate_path(value: object) -> tuple[str, bytes]:
    if not isinstance(value, str):
        raise BundleError("bundle entry path must be a string")
    try:
        encoded = value.encode("ascii", errors="strict")
    except UnicodeEncodeError as error:
        raise BundleError("bundle entry path must use portable ASCII") from error
    if not encoded or len(encoded) > MAX_PATH_BYTES:
        raise BundleError("bundle entry path exceeds the 255-byte limit")
    if _PATH.fullmatch(value) is None:
        raise BundleError("bundle entry path has an invalid segment or separator")
    if any(segment in {".", ".."} for segment in value.split("/")):
        raise BundleError("bundle entry path contains a dot traversal segment")
    return value, encoded


def _validate_index(index: dict) -> list[dict]:
    if set(index) != _ROOT_KEYS:
        missing = sorted(_ROOT_KEYS - set(index))
        extra = sorted(set(index) - _ROOT_KEYS)
        raise BundleError(
            f"bundle index keys are invalid (missing={missing}, extra={extra})"
        )
    if index["contract"] != "lmdj.project-bundle.v1":
        raise BundleError("bundle contract is not lmdj.project-bundle.v1")
    if index["contract_version"] not in READABLE_CONTRACT_VERSIONS:
        raise BundleError("bundle contract version is unsupported")
    if index["compression"] != "none":
        raise BundleError("bundle compression must be none")
    if index["project_contract"] not in PROJECT_CONTRACTS:
        raise BundleError("bundle project contract is unsupported")
    if not isinstance(index["project_id"], str) or _UUID.fullmatch(
        index["project_id"]
    ) is None:
        raise BundleError("bundle project_id must be a lowercase UUID")
    if not isinstance(index["bundle_digest"], str) or _SHA256.fullmatch(
        index["bundle_digest"]
    ) is None:
        raise BundleError("bundle_digest must be a lowercase SHA-256")

    entries = index["entries"]
    if not isinstance(entries, list) or not entries:
        raise BundleError("bundle entries must be a non-empty array")
    if len(entries) > MAX_ENTRIES:
        raise BundleError("bundle entry count exceeds 4096")

    expected_offset = 0
    previous_path: bytes | None = None
    exact_paths: set[str] = set()
    folded_paths: set[str] = set()
    for position, item in enumerate(entries):
        if not isinstance(item, dict) or set(item) != _ENTRY_KEYS:
            raise BundleError(f"bundle entry {position} has invalid keys")
        relative, encoded_path = _validate_path(item["path"])
        if relative in exact_paths:
            raise BundleError(f"bundle has duplicate path: {relative}")
        folded = relative.lower()
        if folded in folded_paths:
            raise BundleError(f"bundle has an ASCII case-fold path collision: {relative}")
        if previous_path is not None and encoded_path <= previous_path:
            raise BundleError("bundle entry paths are not in unsigned UTF-8 order")
        exact_paths.add(relative)
        folded_paths.add(folded)
        previous_path = encoded_path

        byte_length = _integer(item["bytes"], f"entry {position} bytes")
        offset = _integer(item["offset"], f"entry {position} offset")
        if byte_length > MAX_ENTRY_BYTES:
            raise BundleError(f"bundle entry exceeds 64 MiB: {relative}")
        if offset != expected_offset:
            raise BundleError("bundle entry offsets must be contiguous")
        expected_offset += byte_length
        if expected_offset > MAX_PAYLOAD_BYTES:
            raise BundleError("bundle payload exceeds 512 MiB")
        if not isinstance(item["sha256"], str) or _SHA256.fullmatch(
            item["sha256"]
        ) is None:
            raise BundleError(f"bundle entry SHA-256 is invalid: {relative}")

    declared_total = _integer(
        index["uncompressed_bytes"], "bundle uncompressed_bytes"
    )
    if declared_total > MAX_PAYLOAD_BYTES:
        raise BundleError("bundle payload exceeds 512 MiB")
    if declared_total != expected_offset:
        raise BundleError("bundle uncompressed_bytes does not match its entries")
    if bundle_digest(index) != index["bundle_digest"]:
        raise BundleError("bundle_digest does not match the canonical index")
    return entries


def _hash_payload(stream: BinaryIO, byte_length: int) -> str:
    digest = hashlib.sha256()
    remaining = byte_length
    while remaining:
        chunk = stream.read(min(CHUNK_BYTES, remaining))
        if not chunk:
            raise BundleError("bundle payload is truncated")
        digest.update(chunk)
        remaining -= len(chunk)
    return digest.hexdigest()


def read_bundle(path: os.PathLike[str] | str) -> tuple[dict, int]:
    """Validate a complete Bundle without extracting it."""
    bundle_path = Path(path)
    try:
        info = bundle_path.lstat()
    except OSError as error:
        raise BundleError(f"bundle cannot be inspected: {error}") from error
    if not stat.S_ISREG(info.st_mode):
        raise BundleError("bundle path is not a regular file")
    try:
        with bundle_path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_dev != info.st_dev
                or opened.st_ino != info.st_ino
                or opened.st_size != info.st_size
            ):
                raise BundleError("bundle file changed while it was opened")
            header = stream.read(12)
            if len(header) != 12:
                raise BundleError("bundle header is truncated")
            if header[:8] != MAGIC:
                raise BundleError("bundle magic is invalid")
            index_bytes = int.from_bytes(header[8:12], "big")
            if index_bytes == 0:
                raise BundleError("bundle index is empty")
            if index_bytes > MAX_INDEX_BYTES:
                raise BundleError("bundle index exceeds 4 MiB")
            encoded_index = stream.read(index_bytes)
            if len(encoded_index) != index_bytes:
                raise BundleError("bundle index is truncated")
            index = _decode_canonical_index(encoded_index)
            entries = _validate_index(index)
            payload_offset = 12 + index_bytes
            expected_size = payload_offset + index["uncompressed_bytes"]
            if info.st_size < expected_size:
                raise BundleError("bundle payload is truncated")
            if info.st_size > expected_size:
                raise BundleError("bundle has trailing undeclared payload bytes")
            for item in entries:
                actual = _hash_payload(stream, item["bytes"])
                if actual != item["sha256"]:
                    raise BundleError(
                        f"bundle payload hash does not match: {item['path']}"
                    )
            if stream.read(1):
                raise BundleError("bundle has trailing undeclared payload bytes")
            return index, payload_offset
    except BundleError:
        raise
    except OSError as error:
        raise BundleError(f"bundle could not be read: {error}") from error


def _safe_relative(relative: str) -> bytes:
    try:
        return _validate_path(relative)[1]
    except BundleError as error:
        raise BundleError(f"source path {relative!r} is invalid: {error}") from error


def _walk_source(root: Path) -> list[_SourceFile]:
    files: list[_SourceFile] = []
    total = 0

    def visit(directory: Path, prefix: str) -> None:
        nonlocal total
        try:
            children = list(os.scandir(directory))
        except OSError as error:
            raise BundleError(f"source directory cannot be read: {error}") from error
        for child in children:
            relative = f"{prefix}/{child.name}" if prefix else child.name
            _safe_relative(relative)
            try:
                info = child.stat(follow_symlinks=False)
            except OSError as error:
                raise BundleError(f"source entry cannot be inspected: {relative}") from error
            if stat.S_ISLNK(info.st_mode):
                raise BundleError(f"source tree contains a symlink: {relative}")
            if stat.S_ISDIR(info.st_mode):
                visit(Path(child.path), relative)
                continue
            if not stat.S_ISREG(info.st_mode):
                raise BundleError(f"source entry is not a regular file: {relative}")
            if info.st_nlink != 1:
                raise BundleError(f"source tree contains a hardlink: {relative}")
            if info.st_size > MAX_ENTRY_BYTES:
                raise BundleError(f"source entry exceeds 64 MiB: {relative}")
            total += info.st_size
            if total > MAX_PAYLOAD_BYTES:
                raise BundleError("source payload exceeds 512 MiB")
            files.append(
                _SourceFile(
                    relative=relative,
                    path=Path(child.path),
                    size=info.st_size,
                    device=info.st_dev,
                    inode=info.st_ino,
                )
            )

    visit(root, "")
    if not files:
        raise BundleError("source Project contains no regular files")
    if len(files) > MAX_ENTRIES:
        raise BundleError("source entry count exceeds 4096")
    files.sort(key=lambda item: item.relative.encode("ascii"))
    return files


def _open_source(item: _SourceFile) -> Iterator[BinaryIO]:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(item.path, flags)
    except OSError as error:
        raise BundleError(f"source file cannot be opened: {item.relative}") from error
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_dev != item.device
            or info.st_ino != item.inode
            or info.st_size != item.size
        ):
            raise BundleError(f"source file changed while packing: {item.relative}")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            yield stream
    finally:
        os.close(descriptor)


def _hash_source(item: _SourceFile) -> str:
    digest = hashlib.sha256()
    for stream in _open_source(item):
        while True:
            chunk = stream.read(CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _read_source_json(item: _SourceFile) -> object:
    encoded = bytearray()
    for stream in _open_source(item):
        while True:
            chunk = stream.read(CHUNK_BYTES)
            if not chunk:
                break
            encoded.extend(chunk)
    try:
        return json.loads(encoded.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BundleError(
            f"managed Project JSON cannot be parsed: {item.relative}"
        ) from error


def _load_project_identity(source: Path, files: list[_SourceFile]) -> tuple[str, str]:
    required_directories = (
        "assets",
        "history/checkpoints",
        "history/transactions",
        "recovery/active",
        "recovery/sealed",
    )
    for relative in required_directories:
        path = source / relative
        try:
            info = path.lstat()
        except OSError as error:
            raise BundleError(f"managed Project directory is missing: {relative}") from error
        if not stat.S_ISDIR(info.st_mode):
            raise BundleError(f"managed Project directory is invalid: {relative}")

    inventory = {item.relative: item for item in files}
    try:
        manifest_item = inventory["manifest.json"]
        checkpoint_item = inventory["history/checkpoints/0.json"]
    except KeyError as error:
        raise BundleError(f"managed Project identity file is missing: {error}") from error
    manifest = _read_source_json(manifest_item)
    checkpoint = _read_source_json(checkpoint_item)
    if not isinstance(manifest, dict) or manifest.get("contract") != (
        "lmdj.project.manifest.v1"
    ):
        raise BundleError("managed Project manifest contract is invalid")
    project_id = checkpoint.get("project_id") if isinstance(checkpoint, dict) else None
    if (
        not isinstance(checkpoint, dict)
        or checkpoint.get("contract") not in PROJECT_CONTRACTS
        or not isinstance(project_id, str)
        or _UUID.fullmatch(project_id) is None
    ):
        raise BundleError("managed Project initial checkpoint identity is invalid")
    # The head checkpoint, not the initial one, states the Contract level a
    # reader of this Bundle actually receives: Project I/O promotes a Project
    # on its first persist and leaves checkpoint 0 at the level it was created
    # with. Project I/O's own import derives the same value from the head, so
    # reading the initial checkpoint here would make the packed index and the
    # importer's recomputed digest disagree on a promoted Project.
    head_relative = manifest.get("head_checkpoint")
    if not isinstance(head_relative, str) or _CHECKPOINT.fullmatch(
        head_relative
    ) is None:
        raise BundleError("managed Project head checkpoint path is invalid")
    try:
        head_item = inventory[head_relative]
    except KeyError as error:
        raise BundleError(
            f"managed Project identity file is missing: {error}"
        ) from error
    head = _read_source_json(head_item)
    if (
        not isinstance(head, dict)
        or head.get("contract") not in PROJECT_CONTRACTS
        or head.get("project_id") != project_id
    ):
        raise BundleError("managed Project head checkpoint identity is invalid")
    return project_id, head["contract"]


def _copy_source(item: _SourceFile, output: BinaryIO, expected_hash: str) -> None:
    digest = hashlib.sha256()
    copied = 0
    for stream in _open_source(item):
        while True:
            chunk = stream.read(CHUNK_BYTES)
            if not chunk:
                break
            output.write(chunk)
            digest.update(chunk)
            copied += len(chunk)
    if copied != item.size or digest.hexdigest() != expected_hash:
        raise BundleError(f"source file changed while packing: {item.relative}")


def _inside(source: Path, candidate: Path) -> bool:
    try:
        return os.path.commonpath((source, candidate)) == os.fspath(source)
    except ValueError:
        return False


def pack_directory(
    source: os.PathLike[str] | str,
    output: os.PathLike[str] | str,
) -> str:
    """Atomically pack one managed Project directory into a portable Bundle."""
    source_path = Path(source)
    output_path = Path(output)
    try:
        source_info = source_path.lstat()
    except OSError as error:
        raise BundleError(f"source Project cannot be inspected: {error}") from error
    if not stat.S_ISDIR(source_info.st_mode):
        raise BundleError("source Project must be a real directory")
    source_absolute = source_path.resolve()
    output_absolute = output_path.parent.resolve(strict=False) / output_path.name
    if _inside(source_absolute, output_absolute):
        raise BundleError("bundle output must not be inside the source Project")
    if not output_path.parent.is_dir():
        raise BundleError("bundle output parent directory does not exist")

    files = _walk_source(source_path)
    # Inventory the complete tree before reading identity files so a symlinked
    # manifest/checkpoint is rejected without following it even transiently.
    project_id, project_contract = _load_project_identity(source_path, files)
    entries = []
    offset = 0
    for item in files:
        digest = _hash_source(item)
        entries.append(
            {
                "bytes": item.size,
                "offset": offset,
                "path": item.relative,
                "sha256": digest,
            }
        )
        offset += item.size
    index = {
        "bundle_digest": "0" * 64,
        "compression": "none",
        "contract": "lmdj.project-bundle.v1",
        "contract_version": CONTRACT_VERSION,
        "entries": entries,
        "project_contract": project_contract,
        "project_id": project_id,
        "uncompressed_bytes": offset,
    }
    index["bundle_digest"] = bundle_digest(index)
    _validate_index(index)
    encoded_index = canonical_json(index)
    if len(encoded_index) > MAX_INDEX_BYTES:
        raise BundleError("bundle index exceeds 4 MiB")

    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, raw_temporary = tempfile.mkstemp(
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
        )
        temporary = Path(raw_temporary)
        with os.fdopen(descriptor, "w+b") as stream:
            descriptor = -1
            stream.write(MAGIC)
            stream.write(len(encoded_index).to_bytes(4, "big"))
            stream.write(encoded_index)
            for item, encoded_entry in zip(files, entries, strict=True):
                _copy_source(item, stream, encoded_entry["sha256"])
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output_path)
        temporary = None
        if hasattr(os, "O_DIRECTORY"):
            directory_descriptor = os.open(
                output_path.parent, os.O_RDONLY | os.O_DIRECTORY
            )
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        return index["bundle_digest"]
    except BundleError:
        raise
    except OSError as error:
        raise BundleError(f"bundle could not be written atomically: {error}") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pack or verify lmdj.project-bundle.v1 transfer files"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    pack = commands.add_parser("pack")
    pack.add_argument("--source", required=True, type=Path)
    pack.add_argument("--output", required=True, type=Path)
    verify = commands.add_parser("verify")
    verify.add_argument("bundle", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "pack":
            digest = pack_directory(arguments.source, arguments.output)
        else:
            digest = read_bundle(arguments.bundle)[0]["bundle_digest"]
    except BundleError as error:
        print(f"Project Bundle error: {error}", file=sys.stderr)
        return 2
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
