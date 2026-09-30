"""The reviewed changelog editorial channel for one release request.

The changelog step freezes a reviewed (changes, exclusions) pair against the
exact Git range of the release. The pair is authored outside the driver and
approved by the Owner; this module is the channel that hands the approved pair
to the driver. `record` stores it in the request's own operations directory
only after `changelog.freeze` proved complete source coverage, together with
the frozen document's binding digests. `read` returns it to the composition,
which binds the digests into the changelog step's spec; the step re-freezes
the same pair at its write boundary and refuses any divergence.

The record is write-once: re-recording the identical editorial is a no-op and
a different one is refused, so an approved editorial cannot be silently
replaced after the step has bound it.
"""

from copy import deepcopy
import json
import os
from pathlib import Path
import re

from .model import canonical_json

EDITORIAL_FILE = "changelog-editorial.json"
SCHEMA = "lmdj.release-changelog-editorial.v1"
_KEYS = {"schema", "request_id", "tag", "changes", "exclusions", "binding"}
_DIGEST = re.compile(r"[0-9a-f]{64}")
_TAG = re.compile(r"lmdj-v[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+")
_MAX_BYTES = 4 * 1024 * 1024


class EditorialError(RuntimeError):
    pass


def _fail(reason):
    raise EditorialError(
        f"why: changelog editorial {reason}; remedy: record the Owner-approved "
        "editorial with `scripts/release.sh editorial REQUEST_ID FILE`")


def _validate(document):
    if type(document) is not dict or set(document) != _KEYS or document["schema"] != SCHEMA:
        _fail("record is malformed")
    if type(document["request_id"]) is not str or not document["request_id"]:
        _fail("record names no request")
    if type(document["tag"]) is not str or _TAG.fullmatch(document["tag"]) is None:
        _fail("record names no Product tag")
    if type(document["changes"]) is not list or type(document["exclusions"]) is not list:
        _fail("record carries no editorial pair")
    binding = document["binding"]
    if (type(binding) is not dict or set(binding) != {"schema", "sha256", "notes_sha256"}
            or any(type(binding[key]) is not str or _DIGEST.fullmatch(binding[key]) is None
                   for key in ("sha256", "notes_sha256"))):
        _fail("record carries no frozen binding")
    return document


def load_pair(path):
    """The (changes, exclusions) pair an editorial file supplies."""
    try:
        raw = Path(path).read_bytes()
    except OSError:
        _fail("file is unreadable")
    if len(raw) > _MAX_BYTES:
        _fail("file exceeds its reviewable size")
    try:
        document = json.loads(raw)
    except ValueError:
        _fail("file is not JSON")
    if (type(document) is not dict or set(document) != {"changes", "exclusions"}
            or type(document["changes"]) is not list or type(document["exclusions"]) is not list):
        _fail('file must be exactly {"changes": [...], "exclusions": [...]}')
    return document["changes"], document["exclusions"]


def record(operations, *, request_id, tag, changes, exclusions, binding):
    """Store the frozen-and-approved editorial once for this request."""
    document = _validate({"schema": SCHEMA, "request_id": request_id, "tag": tag,
                          "changes": deepcopy(changes), "exclusions": deepcopy(exclusions),
                          "binding": deepcopy(binding)})
    operations = Path(operations)
    operations.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = operations / EDITORIAL_FILE
    payload = canonical_json(document)
    existing = read(operations, request_id=request_id)
    if existing is not None:
        if existing != document:
            _fail("differs from the editorial already recorded for this request")
        return path
    temporary = operations / (EDITORIAL_FILE + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    # Linking refuses an existing name, so a concurrent record cannot be replaced.
    try:
        os.link(temporary, path)
    except FileExistsError:
        _fail("was recorded concurrently; re-run to compare")
    finally:
        os.unlink(temporary)
    return path


def read(operations, *, request_id):
    """The recorded editorial for this request, or None before one exists."""
    path = Path(operations) / EDITORIAL_FILE
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError:
        _fail("record is unreadable")
    if len(raw) > _MAX_BYTES:
        _fail("record exceeds its reviewable size")
    try:
        document = _validate(json.loads(raw))
    except ValueError:
        _fail("record is not JSON")
    if canonical_json(document) != raw:
        _fail("record is not in canonical form")
    if document["request_id"] != request_id:
        _fail("record belongs to another request")
    return document
