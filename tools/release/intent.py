"""Intent carrier: snapshot freeze, ledger row and reviewed intent docs PR.

One carrier owns the driver's `intent` step. It commits, on top of the
verified candidate target, the frozen Portal snapshot (versions.json append
plus the official Portal freeze) and the release-intent ledger row bound to
the exact batch evidence verified by the `verification` step, then opens and
drives one reviewed docs PR through the existing witness transport. The merge
squash is documentation only: the release target stays the candidate target,
which already carries the squash witness.

Nothing here allocates a BUILD (the cut did), executes suites, tags,
publishes, deploys or promotes.
"""

from copy import deepcopy
import hashlib
from pathlib import Path
import json
import re

from .model import canonical_sha256
from .orchestration_driver import Observation


class IntentError(ValueError):
    pass


def _fail(reason):
    raise IntentError(
        f"why: intent carrier {reason}; remedy: restore the verified candidate "
        "evidence and the original request without re-freezing the snapshot, "
        "rewriting the ledger or reopening a merged pull request")


_TAG = re.compile(r"lmdj-v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\."
                  r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")
_BUILD = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.0\Z")
_SPEC_KEYS = {"operation_id", "request_sha256", "repository_id", "actor_id",
              "target_revision", "product_build", "tag", "snapshot_sha256",
              "batch_reference", "batch_run_id"}
_INTENT_OP_STEP = "intent"
_LEDGER_RELATIVE = Path("docs/release-evidence/release-intents.json")
_VERSIONS_RELATIVE = Path("apps/architecture-portal/versions.json")


def intent_operation_id(request_sha256):
    return canonical_sha256({"request": request_sha256, "step": _INTENT_OP_STEP})


def validate_spec(spec):
    if type(spec) is not dict or set(spec) != _SPEC_KEYS:
        _fail("scope fields are invalid")
    if not all(isinstance(spec[k], str) and re.fullmatch(r"[0-9a-f]{64}", spec[k])
               for k in ("operation_id", "request_sha256", "snapshot_sha256")):
        _fail("scope digests are invalid")
    if spec["operation_id"] != intent_operation_id(spec["request_sha256"]):
        _fail("operation differs from the original request")
    if not (isinstance(spec["target_revision"], str)
            and re.fullmatch(r"[0-9a-f]{40}", spec["target_revision"])):
        _fail("target revision is invalid")
    if type(spec["repository_id"]) is not int or spec["repository_id"] <= 0 \
            or type(spec["actor_id"]) is not int or spec["actor_id"] <= 0 \
            or type(spec["batch_run_id"]) is not int or spec["batch_run_id"] <= 0:
        _fail("numeric scope identities are invalid")
    if type(spec["product_build"]) is not str or _BUILD.fullmatch(spec["product_build"]) is None:
        _fail("product build is invalid")
    if spec["tag"] != "lmdj-v" + spec["product_build"] or _TAG.fullmatch(spec["tag"]) is None:
        _fail("tag does not match the product build")
    if type(spec["batch_reference"]) is not str or not 0 < len(spec["batch_reference"]) <= 65536:
        _fail("batch reference is invalid")


def intent_document_relative(spec):
    validate_spec(spec)
    return f"docs/release-evidence/{spec['tag']}-canary-release-intent.md"


def ledger_row(spec):
    """The exact releasable ledger row this PR appends; frozen input, not output."""
    validate_spec(spec)
    return {"tag": spec["tag"], "kind": "product", "identity": spec["product_build"],
            "target_revision": spec["target_revision"], "channel": "canary",
            "disposition": "releasable", "profile": "web-hosts",
            "snapshot": spec["product_build"], "merged_main_run_id": spec["batch_run_id"],
            "evidence_paths": [intent_document_relative(spec)],
            "batch_test_evidence": spec["batch_reference"]}


def intent_markdown(spec):
    validate_spec(spec)
    return (
        f"# LMDJ `{spec['product_build']}` Canary Release Intent\n\n"
        "This record binds one reserved Product Build to one exact protected-`main` "
        "revision (the candidate target, which carries its squash witness), one "
        "immutable Portal snapshot and one authenticated full batch result. It "
        "authorizes a reviewable `releasable` ledger row only. It does not create "
        "a tag, a Draft, a GitHub Release, a Runtime deployment or a promotion.\n\n"
        "| Field | Value |\n| --- | --- |\n"
        f"| Tag | `{spec['tag']}` |\n"
        f"| Kind / identity | `product` / `{spec['product_build']}` |\n"
        "| Channel | `canary` |\n| Profile | `web-hosts` |\n"
        f"| Target revision | `{spec['target_revision']}` |\n"
        f"| Snapshot | `{spec['product_build']}` |\n"
        f"| Full batch run | [{spec['batch_run_id']}](https://github.com/endaye/lmdj"
        f"/actions/runs/{spec['batch_run_id']}) |\n\n"
        f"Batch reference digest: `{hashlib.sha256(spec['batch_reference'].encode()).hexdigest()}`\n"
    )


def pr_document(spec):
    validate_spec(spec)
    document = {"title": f"docs(release): record {spec['product_build']} canary release intent",
                "body": ("## Canary release intent\n\n"
                         f"Product Build: `{spec['product_build']}`\n\n"
                         f"Tag: `{spec['tag']}`\n\n"
                         f"Candidate target (unchanged): `{spec['target_revision']}`\n\n"
                         f"Immutable snapshot: `{spec['snapshot_sha256']}`\n\n"
                         f"Full batch run: [{spec['batch_run_id']}](https://github.com/endaye/lmdj"
                         f"/actions/runs/{spec['batch_run_id']})\n\n"
                         "Adds only the frozen Portal snapshot, the release-intent ledger row "
                         "and its evidence document. The release target stays the candidate "
                         "target; the batch result binding was independently verified before "
                         "this pull request. No tag, Release, deployment or promotion is "
                         "claimed.\n\n"
                         "Version impact: none\n\n"
                         "Reason: release-operation documentation and ledger evidence only.\n\n"
                         "Documentation impact: required\n\n"
                         f"Affected portal pages: /versions/{spec['product_build']}/\n\n"
                         f"<!-- lmdj-release-intent-pr.v1 {canonical_sha256(spec)} -->\n"),
                "head": "docs/release-witness-" + spec["operation_id"], "base": "main",
                "draft": False, "maintainer_can_modify": False}
    if len(document["body"]) > 20000:
        _fail("generated document exceeds the transport bound")
    return document


def ledger_append(existing_rows, row):
    """One canonical new-ledger rows list; refuses duplicates, keeps history."""
    if not isinstance(existing_rows, list):
        _fail("existing ledger rows are invalid")
    if any(existing.get("tag") == row["tag"] for existing in existing_rows):
        _fail("ledger already records this tag")
    return existing_rows + [deepcopy(row)]


def _read_json(path, why):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _fail(why)


def _committed_json(git, relative):
    """Read one tracked file's committed bytes; the commit is the authority."""
    try:
        raw = git("show", "HEAD:" + relative)
    except Exception:
        _fail("committed " + relative + " is unreadable")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        _fail("committed " + relative + " is malformed")


class IntentCommit:
    """Create the intent docs commit on an owned worktree at the candidate target.

    `freeze(worktree_root)` runs the official Portal snapshot freeze for this
    BUILD (trusted composition invokes the documented docs-site version entry);
    tests supply a recording fake. Mutations are idempotent from committed
    state: an existing worktree at the exact target resumes, nothing refreezes
    or rewrites the ledger once committed.
    """

    def __init__(self, root, repository_root, *, spec, freeze, author_name, author_email):
        validate_spec(spec)
        self.root = Path(root).absolute()
        if self.root.resolve() != self.root:
            _fail("worktree root contains a symlink")
        self.repository_root = Path(repository_root).absolute()
        self.spec = deepcopy(spec)
        self.freeze = freeze
        self.author = dict(author_name=author_name, author_email=author_email)
        self._workspace = None
        self._committed_head = None

    def _git(self, *args):
        from .publication_workspace import PublicationWorkspace, PublicationWorkspaceError
        if self._workspace is None:
            self._workspace = PublicationWorkspace(self.root)
        try:
            return self._workspace.git(*args)
        except PublicationWorkspaceError as error:
            raise IntentError(f"worktree Git is unavailable: {error}") from None

    def _repository_git(self, *args):
        from .publication_workspace import PublicationWorkspace, PublicationWorkspaceError
        repository = PublicationWorkspace(self.repository_root)
        try:
            return repository.git(*args)
        except PublicationWorkspaceError as error:
            raise IntentError(f"repository Git is unavailable: {error}") from None

    def _completed(self):
        """The already-created intent commit for this operation, or None.

        Recovery is verification of the original commit's content, never
        regeneration: a clean worktree whose *committed* ledger row equals the
        frozen row and whose committed tree carries the intent document is the
        completed state. Bytes are read from the commit, so a worktree file
        that merely matches on disk cannot stand in for the commit.
        """
        head = self._git("rev-parse", "HEAD").decode().strip()
        if head == self.spec["target_revision"]:
            return None
        self._git("merge-base", "--is-ancestor", self.spec["target_revision"], head)
        if self._git("status", "--porcelain").strip():
            _fail("existing worktree has uncommitted changes")
        document = _committed_json(self._git, str(_LEDGER_RELATIVE))
        rows = document.get("entries") if isinstance(document, dict) else None
        if not isinstance(rows, list):
            _fail("committed release-intents.json is malformed")
        matches = [row for row in rows if row.get("tag") == self.spec["tag"]]
        if len(matches) != 1 or matches[0] != ledger_row(self.spec):
            _fail("existing intent commit does not carry this operation's ledger row")
        self._git("cat-file", "-e", "HEAD:" + intent_document_relative(self.spec))
        return head

    def completed_head(self):
        """Public recovery: the verified intent commit, or None before it exists.

        Returns None when no worktree exists yet; a worktree that is neither
        the candidate target nor exactly this operation's commit fails closed.
        """
        if not self.root.exists():
            return None
        return self._completed()

    def _ensure_worktree(self, *, before_write):
        if self.root.exists():
            return self._completed()
        before_write()
        if self.root.exists():
            # A concurrent creator between the guard and the Git call is a
            # resume of the same operation, never a second worktree attempt.
            return self._completed()
        self._repository_git("worktree", "add", "--detach", str(self.root),
                             self.spec["target_revision"])
        head = self._git("rev-parse", "HEAD").decode().strip()
        if head != self.spec["target_revision"]:
            _fail("worktree is not at the verified candidate target")
        return None

    def _append_versions(self):
        builds = _read_json(self.root / _VERSIONS_RELATIVE, "portal versions.json is unreadable")
        if not isinstance(builds, list) or any(not isinstance(b, str) for b in builds):
            _fail("portal versions.json is not a list of builds")
        if self.spec["product_build"] in builds:
            return
        builds.append(self.spec["product_build"])
        (self.root / _VERSIONS_RELATIVE).write_text(
            json.dumps(builds, indent=2) + "\n", encoding="utf-8")

    def _append_ledger(self):
        document = _read_json(self.root / _LEDGER_RELATIVE, "release-intents.json is unreadable")
        if not isinstance(document, dict) or not isinstance(document.get("entries"), list):
            _fail("release-intents.json is malformed")
        document["entries"] = ledger_append(document["entries"], ledger_row(self.spec))
        (self.root / _LEDGER_RELATIVE).write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def commit(self, *, before_write):
        """Create the single intent docs commit; returns (head_sha, tree_sha)."""
        if not callable(before_write) or not callable(self.freeze):
            _fail("requires the parent write guard and the trusted snapshot freeze")
        completed = self._ensure_worktree(before_write=before_write)
        if completed is not None:
            tree = self._git("rev-parse", "HEAD^{tree}").decode().strip()
            return completed, tree
        self._append_versions()
        self._git("add", str(_VERSIONS_RELATIVE))
        self._git("-c", "user.name=" + self.author["author_name"],
                  "-c", "user.email=" + self.author["author_email"],
                  "commit", "-m",
                  f"chore(portal): add {self.spec['product_build']} to version index")
        before_write()
        # The official freeze runs against the committed tree at the target.
        self.freeze(self.root)
        self._git("add", "-A")
        self._append_ledger()
        (self.root / intent_document_relative(self.spec)).write_text(
            intent_markdown(self.spec), encoding="utf-8")
        self._git("add", "-A")
        before_write()
        self._git("-c", "user.name=" + self.author["author_name"],
                  "-c", "user.email=" + self.author["author_email"],
                  "commit", "-m",
                  f"docs(release): record {self.spec['product_build']} canary release intent")
        head = self._git("rev-parse", "HEAD").decode().strip()
        tree = self._git("rev-parse", "HEAD^{tree}").decode().strip()
        self._committed_head = head
        return head, tree
