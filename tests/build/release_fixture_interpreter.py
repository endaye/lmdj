#!/usr/bin/env python3
"""Select the Python that release tooling fixtures spawn under the sanitized environment.

The release executor hands its children only PATH, HOME, TMPDIR and the Git
guards, so a child interpreter must start without the parent's loader
variables. setup-python's relocated CPython on a self-hosted Linux runner does
not: its shared libpython resolves only through the LD_LIBRARY_PATH the action
exports, and every `python3` child exits 127 with a loader error the executor
records as a digest. See `.agents/pitfalls/sanitized-child-interpreter-dependency.md`.
"""
from __future__ import annotations

import atexit
from functools import lru_cache
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

PROBE_ENVIRONMENT = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
PROBE = ("import argparse,json,pathlib,subprocess,sys; "
         "assert sys.version_info >= (3, 11); print('lmdj-fixture-python-ready')")


@lru_cache(maxsize=16)
def standalone_python(candidates):
    """Return the first candidate that starts under the sanitized environment."""
    for index, candidate in enumerate(candidates):
        try:
            result = subprocess.run([candidate, "-I", "-c", PROBE], env=PROBE_ENVIRONMENT,
                                    capture_output=True, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and result.stdout == b"lmdj-fixture-python-ready\n":
            if index:
                print(f"Process fixture uses independently verified interpreter: {candidate}", file=sys.stderr)
            return candidate
    raise RuntimeError("why: no fixture Python starts with the sanitized environment; "
                       "remedy: provide a standalone system Python 3.11+; do not forward loader variables or skip process tests")


def candidates():
    """The parent first, then the system and the PATH's versioned interpreters."""
    found = [sys.executable, "/usr/bin/python3", "/usr/local/bin/python3"]
    found += [shutil.which(name) for name in ("python3", "python3.14", "python3.13", "python3.12", "python3.11")]
    return tuple(dict.fromkeys(path for path in found if path))


@lru_cache(maxsize=None)
def fixture_python():
    return standalone_python(candidates())


@lru_cache(maxsize=None)
def fixture_path():
    """PATH for sanitized children whose `python3` is the verified interpreter.

    The production vectors name `python3` and resolve it through the PATH the
    fixture passes, so a private bin with a thin absolute-path wrapper goes
    first. A wrapper, not a symlink: the interpreter keeps its own prefix.
    """
    interpreter = fixture_python()
    directory = tempfile.mkdtemp(prefix="lmdj-fixture-python-")
    atexit.register(shutil.rmtree, directory, ignore_errors=True)
    for name in ("python3", "python"):
        wrapper = Path(directory) / name
        wrapper.write_text(f"#!/bin/sh\nexec {shlex.quote(interpreter)} \"$@\"\n")
        wrapper.chmod(0o755)
    return directory + os.pathsep + os.environ["PATH"]


def reexec_when_parent_cannot_start_sanitized():
    """Re-run this test under a standalone interpreter when its own cannot start.

    Production tools spawn `sys.executable` with a sanitized environment; a
    test of those tools therefore needs a parent that satisfies the same
    prerequisite. This is a fixture concern only, never production selection.
    """
    interpreter = fixture_python()
    if os.path.realpath(interpreter) == os.path.realpath(sys.executable):
        return
    if os.environ.get("LMDJ_FIXTURE_REEXEC") == interpreter:
        raise RuntimeError("why: re-executed fixture interpreter still differs from the verified one; "
                           "remedy: inspect the interpreter candidates instead of looping")
    os.environ["LMDJ_FIXTURE_REEXEC"] = interpreter
    print(f"Re-executing {sys.argv[0]} under independently verified interpreter: {interpreter}", file=sys.stderr)
    sys.stderr.flush()
    os.execv(interpreter, [interpreter, *sys.argv])
