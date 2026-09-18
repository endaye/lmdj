"""Durable BUILD reservations, not reviewed allocation or release authority.

One enrolled local catalogue must be shared by all allocators for a repository.
It is never recreated by reserve/resume. Retain failed reservations permanently.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile

from scripts.version import ProductVersion, load_version
from .candidate_inputs import CandidateInputs, VERSION
from .model import canonical_json, canonical_sha256
from .orchestration import RequestJournal, validate_request, _keys, _pairs, _fail

CATALOG = "build-reservations"
MAX_BYTES = 1024 * 1024


class CandidateReservations:
    def __init__(self, repository_root, state_root):
        self.inputs = CandidateInputs(repository_root)
        self.state_root = Path(state_root)

    def _version(self, revision, versions=None):
        if versions is not None and revision in versions:
            return versions[revision]
        try:
            metadata, name = self.inputs.git("ls-tree", revision, "--", VERSION).decode().rstrip("\n").split("\t")
            mode, kind, oid = metadata.split(" ")
            if mode != "100644" or kind != "blob" or name != VERSION:
                _fail("historical Product version is not a regular manifest")
            if not 0 < int(self.inputs.git("cat-file", "-s", oid)) <= 65536:
                _fail("historical Product version exceeds its bound")
            raw = self.inputs.git("cat-file", "blob", oid)
            document = json.loads(raw, object_pairs_hook=_pairs)
            with tempfile.TemporaryDirectory(prefix="lmdj-reservation-version-") as directory:
                filename = Path(directory) / "version.json"
                filename.write_bytes(canonical_json(document))
                version = load_version(filename)
            if versions is not None:
                versions[revision] = version
            return version
        except (ValueError, TypeError, UnicodeError):
            _fail("historical Product version is malformed or unavailable")

    def _history_floor(self, revision, versions=None):
        # Full history, not first-parent/path-simplified history: a higher BUILD
        # allocated then reverted or merged away still consumes its number.
        revisions = self.inputs.git("rev-list", "--full-history", revision,
                                    "--", VERSION).decode().splitlines()
        versions = {} if versions is None else versions
        builds = [self._version(revision, versions).build]
        for commit in revisions:
            row = self.inputs.git("ls-tree", commit, "--", VERSION)
            if row:  # A deletion commit has no manifest; its ancestors remain.
                builds.append(self._version(commit, versions).build)
        return max(builds)

    def _read(self, journal):
        journal._active()
        try:
            fd = os.open(CATALOG, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=journal.directory)
        except OSError:
            _fail("BUILD catalogue is missing or unsafe; restore enrolled storage, never reconstruct reservations")
        try:
            journal._private(fd)
            with os.fdopen(fd, "rb", closefd=False) as source:
                raw = source.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                _fail("BUILD catalogue exceeds its bound")
            envelope = json.loads(raw, object_pairs_hook=_pairs)
            _keys(envelope, ("catalogue", "sha256"))
            catalogue = envelope["catalogue"]
            _keys(catalogue, ("schema", "repository", "reservations"))
            if (catalogue["schema"] != "lmdj.build-reservations.v1"
                    or type(catalogue["reservations"]) is not list
                    or envelope["sha256"] != canonical_sha256(catalogue)
                    or raw != canonical_json(envelope)):
                _fail("BUILD catalogue schema or digest differs")
            seen, previous = set(), -1
            for record in catalogue["reservations"]:
                _keys(record, ("request", "request_sha256", "inputs_sha256", "history_floor", "version"))
                request = record["request"]
                validate_request(request)
                if (request["repository"] != catalogue["repository"] or request["mode"] != "new"
                        or request["id"] in seen
                        or record["request_sha256"] != canonical_sha256(request)
                        or type(record["inputs_sha256"]) is not str
                        or len(record["inputs_sha256"]) != 64
                        or any(c not in "0123456789abcdef" for c in record["inputs_sha256"])
                        or type(record["history_floor"]) is not int or record["history_floor"] < 0):
                    _fail("BUILD reservation binding differs")
                version = self._parse_version(record["version"])
                if version.patch != 0 or version.build != max(previous, record["history_floor"]) + 1:
                    _fail("BUILD reservation sequence differs")
                seen.add(request["id"])
                previous = version.build
            journal._active()
            return catalogue
        except (ValueError, TypeError, UnicodeError):
            _fail("BUILD catalogue content is malformed")
        finally:
            os.close(fd)

    @staticmethod
    def _parse_version(value):
        if type(value) is not str:
            _fail("BUILD identity is not text")
        version = ProductVersion(*(int(part) for part in value.split(".")))
        if str(version) != value:
            _fail("BUILD identity is noncanonical")
        return version

    @staticmethod
    def _save(journal, catalogue):
        raw = canonical_json({"catalogue": catalogue, "sha256": canonical_sha256(catalogue)})
        if len(raw) > MAX_BYTES:
            _fail("BUILD catalogue capacity exhausted; retain history and reconcile storage")
        journal._write(CATALOG, raw)

    def enroll(self, repository):
        """Explicit provisioning only; call from trusted setup, never recovery."""
        # Use the same repository grammar as authenticated request records.
        import re
        if type(repository) is not str or re.fullmatch(r"[a-z0-9_.-]+/[a-z0-9_.-]+", repository) is None:
            _fail("invalid reservation repository")
        catalogue_path = self.state_root / CATALOG
        if catalogue_path.exists():
            with RequestJournal(self.state_root) as journal:
                catalogue = self._read(journal)
                if catalogue["repository"] != repository:
                    _fail("BUILD catalogue belongs to another repository")
                return
        # No catalogue yet: the storage directory may already exist (a prior
        # run's journal opens create it and its writer lock), so enrollment
        # provisions the empty catalogue exactly when the directory holds
        # nothing but its writer lock.
        with RequestJournal(self.state_root) as journal:
            if sorted(os.listdir(journal.directory)) != ["writer.lock"]:
                _fail("new BUILD catalogue storage changed during enrollment")
            self._save(journal, {"schema":"lmdj.build-reservations.v1",
                                "repository":repository, "reservations":[]})

    def reserve(self, request, frozen, main_revision):
        """After caller authenticates authority/main/CI, reserve before cut edits.

        No recovery path silently chooses another number. This catalogue does
        not authenticate remote main, original user authority or baseline CI.
        """
        return self._resolve(request, frozen, main_revision, allocate=True)

    def observe(self, request, frozen, main_revision):
        """Read the original reservation, never allocate or enroll a catalogue.

        None is positive absence in the verified existing catalogue. A parent
        with an outstanding allocation intent cannot treat it as retry authority.
        """
        return self._resolve(request, frozen, main_revision, allocate=False)

    def _resolve(self, request, frozen, main_revision, *, allocate):
        validate_request(request)
        if request["mode"] != "new" or frozen.get("base_revision") != request["base_revision"]:
            _fail("BUILD reservation must bind the original new-release baseline")
        with RequestJournal(self.state_root) as journal:
            catalogue = self._read(journal)
            if catalogue["repository"] != request["repository"]:
                _fail("BUILD catalogue belongs to another repository")
            self.inputs.verify(frozen, main_revision)
            # Per-observation reuse only: immutable commits are parsed once in
            # this call, but every resume reads the real object store again.
            versions = {}
            floor = self._history_floor(request["base_revision"], versions)
            if main_revision != request["base_revision"] and self._history_floor(main_revision, versions) != floor:
                _fail("candidate-changed: BUILD allocation history advanced after the original baseline")
            current = self._version(request["base_revision"], versions)
            records = catalogue["reservations"]
            for record in records:
                if record["request"]["id"] == request["id"]:
                    if (record["request"] != request or record["inputs_sha256"] != canonical_sha256(frozen)
                            or record["history_floor"] != floor
                            or self._parse_version(record["version"]).milestone != current.milestone
                            or self._parse_version(record["version"]).minor != current.minor):
                        _fail("BUILD reservation cannot be rebound")
                    return deepcopy(record)
            if not allocate:
                return None
            previous = self._parse_version(records[-1]["version"]).build if records else -1
            version = ProductVersion(current.milestone, current.minor, max(floor, previous) + 1, 0)
            record = {"request":deepcopy(request), "request_sha256":canonical_sha256(request),
                      "inputs_sha256":canonical_sha256(frozen), "history_floor":floor, "version":str(version)}
            catalogue["reservations"].append(record)
            self._save(journal, catalogue)
            if self._read(journal) != catalogue:
                _fail("BUILD reservation far-side record differs")
            return deepcopy(record)
