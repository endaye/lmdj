"""Exact publication Task/squash source proof, never review or release authority.

Only passive Git blobs are projected. Private temporary indexes may add expected
objects to the local object store, but no checkout, ref, real index or remote
write occurs. Missing history is not fetched or guessed by this verifier.
"""

from pathlib import Path
from dataclasses import replace
import tempfile

from .batch_reference import sha
from .evidence_pr import validate_spec
from .model import canonical_sha256
from .publication import collect_publication_state
from .publication_evidence import LEDGER, PUBLICATIONS, PIN, PAGES, plan_publication_patch
from .publication_workspace import PublicationWorkspace


class EvidenceSourceError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise EvidenceSourceError(f"why: publication PR source {reason}; remedy: reconcile the exact Task, frozen publication and actual squash source; never substitute a PR status or rewrite history")


class PublicationSourceVerifier:
    def __init__(self, root):
        self.git = PublicationWorkspace(root).git

    def _commit(self, revision):
        require(sha(revision), "revision is invalid")
        require(self.git("cat-file", "-t", revision).strip() == b"commit", "revision is not a commit")
        require(int(self.git("cat-file", "-s", revision)) <= 65536, "commit exceeds its bound")
        # Read raw committed headers, ignoring replace refs, grafts and config.
        headers = self.git("cat-file", "commit", revision).split(b"\n\n", 1)[0].split(b"\n")
        trees = [row[5:].decode() for row in headers if row.startswith(b"tree ")]
        parents = [row[7:].decode() for row in headers if row.startswith(b"parent ")]
        require(len(trees) == 1 and sha(trees[0]) and all(sha(parent) for parent in parents), "commit headers are invalid")
        return trees[0], parents

    def _ancestor(self, before, after):
        self.git("merge-base", "--is-ancestor", before, after)

    def _expected_tree(self, revision, policy, intent, record, *, present=False):
        with tempfile.TemporaryDirectory(prefix="lmdj-publication-source-") as directory:
            root = Path(directory)
            for item in self.git("ls-tree", "-r", "-z", revision).split(b"\0"):
                if not item:
                    continue
                metadata, filename = item.split(b"\t", 1)
                if filename not in tuple(name.encode() for name in (LEDGER, PUBLICATIONS, PIN)) and not filename.startswith((PAGES + "/").encode()):
                    continue
                name = filename.decode()
                mode, kind, oid = metadata.split(b" ")
                require(mode == b"100644" and kind == b"blob" and ".." not in Path(name).parts,
                        "projection input mode is unsafe")
                size = int(self.git("cat-file", "-s", oid.decode()))
                require(0 <= size <= 8 * 1024 * 1024, "projection input exceeds its bound")
                blob = self.git("cat-file", "blob", oid.decode())
                require(len(blob) == size, "projection input length changed")
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(blob)
            patch = plan_publication_patch(root, policy, intent, record).encode()
            if present:
                require(not patch, "current main no longer contains the complete publication evidence")
                return None
            require(patch, "parent already contains this publication; this is not its introducing Task")
            index = root / "private-index"
            self.git("read-tree", revision, index=index)
            self.git("apply", "--cached", "--whitespace=error", "-", data=patch, index=index)
            tree = self.git("write-tree", index=index).decode().strip()
            require(sha(tree), "expected tree identity is invalid")
            return tree

    def verify(self, spec, *, policy, intent, record, main_revision, merge_revision=None):
        validate_spec(spec)
        require(policy.repository == "endaye/lmdj" and policy.branch == "main", "policy is not canonical")
        require(intent.tag == spec["tag"] and intent.target_revision == spec["target_revision"]
                and record.get("tag") == intent.tag and record.get("target_revision") == intent.target_revision,
                "fresh publication differs from the request")
        require(self.git("rev-parse", "--is-shallow-repository").strip() == b"false", "history is shallow")
        self._commit(main_revision)
        self._commit(spec["base_revision"])
        self._ancestor(intent.target_revision, spec["base_revision"])
        self._ancestor(spec["base_revision"], main_revision)
        head_tree, head_parents = self._commit(spec["head_sha"])
        # Promotion appends to the current intent; it does not rewrite the
        # original publication. This gate neither proves nor grants promotion.
        publication_intent = replace(intent, promotions=())
        require(head_parents == [spec["base_revision"]], "Task is not exactly one commit on its declared base")
        require(head_tree == spec["tree_sha"] == self._expected_tree(spec["base_revision"], policy, publication_intent, record),
                "Task tree is not the complete exact publication patch")
        result = {"schema": "lmdj.publication-pr-source.v1", "operation_id": spec["operation_id"],
            "request_sha256": spec["request_sha256"], "head_sha": spec["head_sha"], "tree_sha": head_tree,
            "base_revision": spec["base_revision"], "tag": intent.tag, "target_revision": intent.target_revision,
            "publication_sha256": canonical_sha256(record), "merge_sha": None, "merge_parent": None,
            "merge_tree": None}
        if merge_revision is not None:
            merge_tree, merge_parents = self._commit(merge_revision)
            require(len(merge_parents) == 1 and merge_revision != spec["head_sha"], "result is not a distinct squash commit")
            parent = merge_parents[0]
            self._ancestor(spec["base_revision"], parent)
            self._ancestor(merge_revision, main_revision)
            require(merge_tree == self._expected_tree(parent, policy, publication_intent, record),
                    "squash tree differs from the exact publication projected on its actual parent")
            result.update(merge_sha=merge_revision, merge_parent=parent, merge_tree=merge_tree)
            self._expected_tree(main_revision, policy, intent, record, present=True)
        return result


class PublishedPrSourceGate:
    """Compose the existing live signed-publication verifier with real Git proof.

    context_factory must be trusted controller code, normally cli.build_context
    for the service's repository. This source gate is one component of authorize
    and verify_merged, not an implementation of original user authority, Task
    test evidence, PR review/history or effective protection policy.
    """
    def __init__(self, root, *, context_factory, release_id, plan_sha256):
        self.source = PublicationSourceVerifier(root)
        self.context_factory = context_factory
        self.release_id, self.plan_sha256 = release_id, plan_sha256

    def verify(self, spec, *, merge_revision=None):
        context = self.context_factory()
        record, intent = collect_publication_state(spec["tag"], self.release_id, self.plan_sha256, context)
        policy = context.policy
        before = context.github.get_branch(policy.repository, policy.branch)
        require(before.name == "main" and before.protected is True, "main is not protected")
        proof = self.source.verify(spec, policy=policy, intent=intent, record=record,
                                   main_revision=before.commit_sha, merge_revision=merge_revision)
        # A moving main is allowed if it still contains the same immutable proof.
        # Never change the candidate or recreate the Task against that new head.
        after = context.github.get_branch(policy.repository, policy.branch)
        require(after.name == "main" and after.protected is True, "main protection changed")
        self.source._ancestor(merge_revision or spec["base_revision"], after.commit_sha)
        if merge_revision is not None:
            self.source._expected_tree(after.commit_sha, policy, intent, record, present=True)
        return proof
