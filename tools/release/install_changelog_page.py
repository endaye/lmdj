"""Atomic create-only installation; no link/unlink window or copy fallback.

Called only with a fully written staging file by the local portal generator.
Linux renameat2(RENAME_NOREPLACE) and Darwin renameatx_np(RENAME_EXCL) reject
an intervening destination atomically. Unsupported filesystems fail closed.
"""

import ctypes
import errno
import hashlib
import os
from pathlib import Path
import stat
import sys


def _rename_exclusive(with_dir, source, to_dir, target):
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        rename = library.renameatx_np
        exclusive = 4  # sys/stdio.h: RENAME_EXCL
    elif sys.platform == "linux":
        rename = library.renameat2
        exclusive = 1  # Linux RENAME_NOREPLACE
    else:
        raise OSError(errno.ENOTSUP, "exclusive rename is unsupported")
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(with_dir, os.fsencode(source), to_dir, os.fsencode(target), exclusive):
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))


def install(source: Path, target: Path, digest: str):
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    with_dir = os.open(source.parent, flags)
    to_dir = descriptor = None
    try:
        to_dir = os.open(target.parent, flags)
        descriptor = os.open(source.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=with_dir)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError("unsafe staging file")
        value = hashlib.sha256()
        while block := os.read(descriptor, 65536):
            value.update(block)
        if value.hexdigest() != digest:
            raise ValueError("staging bytes changed")
        os.fsync(descriptor)
        os.fsync(with_dir)
        _rename_exclusive(with_dir, source.name, to_dir, target.name)
        os.fsync(to_dir)
        os.fsync(with_dir)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if to_dir is not None:
            os.close(to_dir)
        os.close(with_dir)


if __name__ == "__main__":
    try:
        if len(sys.argv) != 4:
            raise ValueError("source, destination and digest required")
        install(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
    except (OSError, ValueError, AttributeError):
        print("why: exclusive changelog page installation failed; remedy: inspect source/destination identity and filesystem support; never overwrite frozen history", file=sys.stderr)
        sys.exit(1)
