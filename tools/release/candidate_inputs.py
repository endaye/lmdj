"""Passive candidate input proof, not allocation, CI proof or main authority."""
from pathlib import Path, PurePosixPath
import tempfile

from scripts.version import load_version
from .batch_reference import sha
from .dispatch_receipt import unique
from .model import canonical_json, canonical_sha256
from .publication_workspace import PublicationWorkspace
import json

VERSION = "products/lmdj/version.json"


class CandidateInputError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise CandidateInputError(f"why: candidate inputs {reason}; remedy: retain the original request baseline and reconcile candidate changes; do not silently allocate or advance to a new source")


def documentation_only(filename):
    if filename.startswith("docs/"):
        return not filename.startswith(("docs/release-evidence/", "docs/governance/", "docs/quality/"))
    return filename.startswith(("apps/docs-site/docs/", "apps/docs-site/diagrams/",
                                "apps/docs-site/static/diagrams/"))


class CandidateInputs:
    def __init__(self, root):
        self.git = PublicationWorkspace(root).git

    def freeze(self, revision):
        try:
            require(sha(revision), "revision is not an exact commit")
            require(self.git("rev-parse", "--is-shallow-repository").strip() == b"false",
                    "history is shallow")
            require(self.git("cat-file", "-t", revision).strip() == b"commit",
                    "revision is not a commit")
            tree = self.git("rev-parse", revision + "^{tree}").decode().strip()
            require(sha(tree), "tree identity is invalid")
            inventory = {}
            version_oid = None
            for row in self.git("ls-tree", "-r", "-z", "--full-tree", revision).split(b"\0"):
                if not row:
                    continue
                metadata, raw_name = row.split(b"\t", 1)
                mode, kind, oid = metadata.decode("ascii").split(" ")
                filename = raw_name.decode("utf-8")
                require(filename and not PurePosixPath(filename).is_absolute()
                        and str(PurePosixPath(filename)) == filename
                        and ".." not in PurePosixPath(filename).parts
                        and all(ord(c) >= 32 and ord(c) != 127 for c in filename),
                        "tracked path is noncanonical")
                require((mode, kind) in (("100644", "blob"), ("100755", "blob"),
                                        ("120000", "blob"), ("160000", "commit"))
                        and sha(oid), "tracked object identity is invalid")
                if filename == VERSION:
                    require(mode == "100644" and kind == "blob", "Product version is not a regular manifest")
                    version_oid = oid
                require(filename not in inventory, "tracked inventory is duplicated")
                inventory[filename] = {"path":filename, "mode":mode, "object":oid}
            selected = {name for name in inventory if not documentation_only(name)}
            directories = {str(parent) for name in inventory
                           for parent in PurePosixPath(name).parents}
            # Resolve only committed, direct in-tree targets. No filesystem reads,
            # chained links, link traversal, or external dependency assumptions.
            for name in sorted(selected):
                entry = inventory[name]
                if entry["mode"] != "120000":
                    continue
                require(0 < int(self.git("cat-file", "-s", entry["object"])) <= 4096,
                        "symlink target exceeds its bound")
                target = self.git("cat-file", "blob", entry["object"]).decode("utf-8")
                require(target and not target.startswith("/")
                        and all(ord(c) >= 32 and ord(c) != 127 for c in target),
                        "symlink target is not a safe relative path")
                parts = list(PurePosixPath(name).parent.parts)
                for component in target.split("/"):
                    current = "/".join(parts) or "."
                    require(current in directories, "symlink traverses a non-directory or link")
                    if component == "..":
                        require(parts, "symlink escapes the repository")
                        parts.pop()
                    elif component not in ("", "."):
                        parts.append(component)
                resolved = "/".join(parts)
                dependencies = {path for path in inventory
                                if path == resolved or not resolved or path.startswith(resolved + "/")}
                require(dependencies, "symlink target is missing")
                require(all(inventory[path]["mode"] in ("100644", "100755")
                            for path in dependencies),
                        "symlink target contains a link or external Gitlink")
                selected.update(dependencies)
            entries = [inventory[name] for name in selected]
            require(version_oid is not None, "Product version is missing")
            entries.sort(key=lambda entry:entry["path"])
            require(len({e["path"] for e in entries}) == len(entries), "tracked inventory is duplicated")
            blobs = sorted({e["object"] for e in entries if e["mode"] != "160000"})
            checked = self.git("cat-file", "--batch-check=%(objecttype) %(objectname)",
                               data=("\n".join(blobs) + "\n").encode()).decode().splitlines()
            require(checked == ["blob " + oid for oid in blobs],
                    "tracked input blobs are missing or have the wrong type")
            require(0 < int(self.git("cat-file", "-s", version_oid)) <= 65536,
                    "Product version exceeds its bound")
            version_raw = self.git("cat-file", "blob", version_oid)
            document = json.loads(version_raw, object_pairs_hook=unique)
            # Use the installed canonical parser, never a script from revision.
            with tempfile.TemporaryDirectory(prefix="lmdj-candidate-version-") as directory:
                version_file = Path(directory) / "version.json"
                version_file.write_bytes(canonical_json(document))
                version = str(load_version(version_file))
            return {"schema":"lmdj.candidate-inputs.v1", "base_revision":revision,
                    "base_tree":tree, "product_build":version, "entries":entries,
                    "projection_sha256":canonical_sha256(entries)}
        except CandidateInputError:
            raise
        except Exception:
            raise CandidateInputError("why: candidate input objects are missing or invalid; remedy: restore exact trusted history and manifests without changing the request baseline") from None

    def verify(self, frozen, main_revision):
        try:
            require(type(frozen) is dict and type(frozen.get("base_revision")) is str,
                    "frozen baseline is missing")
            require(self.freeze(frozen["base_revision"]) == frozen, "frozen baseline was changed")
            observed = self.freeze(main_revision)
            self.git("merge-base", "--is-ancestor", frozen["base_revision"], main_revision)
            require(observed["entries"] == frozen["entries"]
                    and observed["product_build"] == frozen["product_build"],
                    "changed since the original baseline")
            return {"schema":"lmdj.candidate-input-check.v1", "base_revision":frozen["base_revision"],
                    "observed_main":main_revision, "product_build":frozen["product_build"],
                    "projection_sha256":frozen["projection_sha256"]}
        except CandidateInputError:
            raise
        except Exception:
            raise CandidateInputError("why: candidate ancestry is unavailable or divergent; remedy: restore the original main history without substituting another candidate") from None
