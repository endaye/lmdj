"""Reservation -> exact Git inputs -> canonical candidate build file bytes.

No candidate source execution, checkout, index/ref changes, snapshot or PR.
The parent must authenticate the request, main and baseline CI before calling.
"""
from hashlib import sha1, sha256
from pathlib import Path
import re
import tempfile

from scripts.version import ProductVersion, render_build_material
from .candidate import CandidateReservations
from .candidate_inputs import CandidateInputs
from .candidate_material_scope import material_files, scope_fields
from .model import canonical_sha256
from .orchestration import JournalError

MAX_BLOB_BYTES = 8 * 1024 * 1024
MAX_MATERIAL_BYTES = 64 * 1024 * 1024


def require(value, reason):
    if not value:
        raise JournalError(f"why: candidate material {reason}; remedy: retain the original reservation and restore its exact passive Git inputs")


RUNTIME_IDENTITY_GENERATOR = "tools/web-runtime/generate_runtime_identity.py"
# The generator itself is a frozen input: the export carries the exact bytes
# from the frozen baseline and _runtime_identity_files loads it from the
# export tree, so the committed identity is bound to the authenticated inputs.
RUNTIME_IDENTITY_INPUTS = ("tools/web-runtime/emscripten.lock.json",
                           "tools/web-runtime/runtime-identity.json",
                           RUNTIME_IDENTITY_GENERATOR)


def material_input(name):
    # The canonical generators scan all component manifests, Provider sources,
    # Contracts and Product assembly source. Core/Host implementation bytes are
    # still frozen by CandidateInputs even though this generator does not read them.
    return (name.startswith(("products/lmdj/", "providers/", "contracts/"))
            or name in RUNTIME_IDENTITY_INPUTS
            or re.fullmatch(r"(?:packages|apps)/[^/]+/module\.json", name) is not None)


def _runtime_identity_files(root):
    """Regenerate the Runtime identity for the reserved build (#1531).

    Reads the NEW version/assembly/lock already materialized in the passive
    export tree and loads the generator from that same frozen export, so the
    committed identity can never lag the allocated build nor drift from the
    authenticated inputs.
    """
    import importlib.util

    source = root / RUNTIME_IDENTITY_GENERATOR
    require(source.is_file(), f"generator is absent from the frozen export: {RUNTIME_IDENTITY_GENERATOR}")
    spec = importlib.util.spec_from_file_location("lmdj_release_runtime_identity", source)
    require(spec is not None and spec.loader is not None, f"generator is not importable: {RUNTIME_IDENTITY_GENERATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    identity = module.generate(root)
    return {str(module.JSON_OUTPUT): module.canonical_json(identity),
            str(module.MJS_OUTPUT): module.mjs_bytes(identity)}


class CandidateBuildMaterial:
    def __init__(self, repository_root, reservation_root, *, material_scope=None):
        self.inputs = CandidateInputs(repository_root, material_scope=material_scope)
        self.material_scope = self.inputs.material_scope
        self.files = material_files(self.material_scope)
        self.reservations = CandidateReservations(repository_root, reservation_root,
                                                  material_scope=self.material_scope)

    def _export(self, frozen, destination):
        if self.material_scope is not None:
            require(self.inputs.freeze(frozen["base_revision"]) == frozen,
                    "frozen material scope or input projection changed")
        selected = [entry for entry in frozen["entries"] if material_input(entry["path"])
                    or (self.material_scope is not None and entry["path"] in self.files)]
        require(selected and all(entry["mode"] in ("100644", "100755") for entry in selected),
                "generator inputs contain a symlink or Gitlink")
        objects = sorted({entry["object"] for entry in selected})
        query = ("\n".join(objects) + "\n").encode()
        checked = self.inputs.git("cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)", data=query).decode().splitlines()
        require(len(checked) == len(objects), "blob inventory is incomplete")
        sizes = {}
        for oid, row in zip(objects, checked):
            fields = row.split(" ")
            require(len(fields) == 3 and fields[:2] == [oid, "blob"]
                    and fields[2].isdigit(), "blob identity or type differs")
            sizes[oid] = int(fields[2])
            require(sizes[oid] <= MAX_BLOB_BYTES, "input exceeds its byte bound")
        # Count materialized paths, not unique objects: many aliases of one
        # blob consume disk independently even though batch retrieval dedups it.
        require(sum(sizes[entry["object"]] for entry in selected) <= MAX_MATERIAL_BYTES,
                "input inventory exceeds its byte bound")
        raw = self.inputs.git("cat-file", "--batch", data=query)
        blobs, offset = {}, 0
        for oid in objects:
            header = f"{oid} blob {sizes[oid]}\n".encode()
            require(raw[offset:offset + len(header)] == header, "batch header differs")
            offset += len(header)
            blobs[oid] = raw[offset:offset + sizes[oid]]
            require(len(blobs[oid]) == sizes[oid] and raw[offset + sizes[oid]:offset + sizes[oid] + 1] == b"\n",
                    "batch content is incomplete")
            require(sha1(f"blob {sizes[oid]}\0".encode() + blobs[oid]).hexdigest() == oid,
                    "blob bytes do not match their Git identity")
            offset += sizes[oid] + 1
        require(offset == len(raw), "batch has extra bytes")
        for entry in selected:
            filename = destination / entry["path"]
            filename.parent.mkdir(parents=True, exist_ok=True)
            filename.write_bytes(blobs[entry["object"]])

    def prepare(self, request, frozen, main_revision):
        return self._prepare(request, frozen, main_revision, allocate=True)

    def observe(self, request, frozen, main_revision):
        """Reconstruct the original material without allocating a reservation."""
        return self._prepare(request, frozen, main_revision, allocate=False)

    def _prepare(self, request, frozen, main_revision, *, allocate):
        # Actual durable reservation precedes material generation. A generator
        # failure retains its number; retries use the same reservation.
        lookup = self.reservations.reserve if allocate else self.reservations.observe
        reservation = lookup(request, frozen, main_revision)
        require(reservation is not None, "original reservation is absent")
        with tempfile.TemporaryDirectory(prefix="lmdj-candidate-material-") as directory:
            root = Path(directory).resolve()
            self._export(frozen, root)
            expected = ProductVersion(*(int(part) for part in frozen["product_build"].split(".")))
            reserved = ProductVersion(*(int(part) for part in reservation["version"].split(".")))
            try:
                files = render_build_material(root, expected, reserved,
                    **({} if self.material_scope is None else {"material_profile":"creator-p1"}))
            except Exception:
                raise JournalError("why: canonical candidate material generation refused; remedy: retain the reservation and repair the original input or reconcile a new candidate, never bypass Assembly validation") from None
            # render_build_material returns bytes without writing them; the
            # identity generator reads the reserved build from the tree, so
            # materialize the four files in this throwaway export first.
            for name, raw in files.items():
                destination = root / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
            try:
                files.update(_runtime_identity_files(root))
            except Exception:
                raise JournalError("why: Runtime identity generation refused; remedy: retain the reservation and repair the identity generator inputs (tools/web-runtime policy and toolchain locks), never hand-edit the generated identity") from None
        self.inputs.verify(frozen, main_revision)
        require(set(files) == self.files, "generated inventory differs from the closed material scope")
        require(lookup(request, frozen, main_revision) == reservation,
                "reservation changed during generation")
        inventory = [{"path":name, "size":len(raw), "sha256":sha256(raw).hexdigest()}
                     for name, raw in sorted(files.items())]
        binding = {"schema":"lmdj.candidate-build-material.v1",
                   "base_revision":request["base_revision"],
                   "reservation_sha256":canonical_sha256(reservation),
                   "product_build":reservation["version"], "files":inventory,
                   **scope_fields(self.material_scope)}
        return {"binding":binding, "sha256":canonical_sha256(binding), "files":files}
