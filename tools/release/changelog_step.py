"""One carrier for the driver's `changelog` step: freeze, commit and reviewed PR.

`freeze` binds the reviewed editorial changes/exclusions to the exact
baseline..target range selected from the canonical ledger, exactly as
`changelog.py` does for the legacy path. `ChangelogCommit` then lands that
frozen document in the release-intents ledger entry plus its rendered notes
evidence on top of canonical `main` (the intent merge already carries the
ledger row; this is the reviewable edit that binds the changelog to it), and
`ChangelogCarrier` drives one reviewed docs PR through the existing witness
transport with this step's own closed spec. Observation allocates and executes
nothing.
"""

from copy import deepcopy
import json
from pathlib import Path
import re

from .changelog import ChangelogError, binding, freeze as freeze_changelog
from .evidence_branch import PublicationBranch
from .github_api import GitHubClient
from .intent import _LEDGER_RELATIVE
from .model import canonical_sha256
from .orchestration_driver import Observation
from .witness_pr import WitnessPullRequest


class ChangelogStepError(ValueError):
    pass


def _fail(reason):
    raise ChangelogStepError(
        f"why: changelog step {reason}; remedy: restore the merged intent "
        "ledger and the reviewed editorial input without rewriting history "
        "or reopening a merged pull request")


_SPEC_KEYS = {"operation_id", "request_sha256", "repository_id", "actor_id",
              "base_revision", "head_sha", "tree_sha", "target_revision",
              "product_build", "tag", "changelog_sha256", "notes_sha256"}
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_BUILD = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.0\Z")
_TAG = re.compile(r"lmdj-v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\."
                  r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")
_OP_STEP = "changelog"


def changelog_operation_id(request_sha256):
    return canonical_sha256({"request": request_sha256, "step": _OP_STEP})


def validate_spec(spec):
    if type(spec) is not dict or set(spec) != _SPEC_KEYS:
        _fail("scope fields are invalid")
    if not all(isinstance(spec[k], str) and _DIGEST.fullmatch(spec[k])
               for k in ("operation_id", "request_sha256", "changelog_sha256",
                         "notes_sha256")):
        _fail("scope digests are invalid")
    if spec["operation_id"] != changelog_operation_id(spec["request_sha256"]):
        _fail("operation differs from the original request")
    if not all(isinstance(spec[k], str) and _SHA.fullmatch(spec[k])
               for k in ("base_revision", "head_sha", "tree_sha", "target_revision")):
        _fail("scope revisions are invalid")
    if len({spec["base_revision"], spec["head_sha"], spec["target_revision"]}) != 3:
        _fail("base, head and target identities must be distinct")
    if type(spec["repository_id"]) is not int or spec["repository_id"] <= 0 \
            or type(spec["actor_id"]) is not int or spec["actor_id"] <= 0:
        _fail("numeric scope identities are invalid")
    if type(spec["product_build"]) is not str or _BUILD.fullmatch(spec["product_build"]) is None:
        _fail("product build is invalid")
    if spec["tag"] != "lmdj-v" + spec["product_build"] or _TAG.fullmatch(spec["tag"]) is None:
        _fail("tag does not match the product build")


def evidence_document_relative(spec):
    validate_spec(spec)
    return f"docs/release-evidence/{spec['tag']}-canary-changelog.md"


def pr_document(spec):
    validate_spec(spec)
    document = {"title": f"docs(release): bind {spec['product_build']} canary changelog",
                "body": ("## Canary release changelog\n\n"
                         f"Product Build: `{spec['product_build']}`\n\n"
                         f"Tag: `{spec['tag']}`\n\n"
                         f"Candidate target (unchanged): `{spec['target_revision']}`\n\n"
                         f"Changelog document SHA-256: `{spec['changelog_sha256']}`\n\n"
                         f"Rendered notes SHA-256: `{spec['notes_sha256']}`\n\n"
                         "Binds the reviewed frozen changelog into this release's "
                         "release-intents ledger entry and adds its rendered notes "
                         "evidence. The release target, snapshot and CI evidence stay "
                         "exactly as the merged intent recorded. No tag, Release, "
                         "deployment or promotion is claimed.\n\n"
                         "Version impact: none\n\n"
                         "Reason: release-operation documentation and ledger evidence only.\n\n"
                         "Documentation impact: required\n\n"
                         "Affected portal pages: /versions/"
                         + spec["product_build"] + "/\n\n"
                         f"<!-- lmdj-release-changelog-pr.v1 {canonical_sha256(spec)} -->\n"),
                "head": "docs/release-witness-" + spec["operation_id"], "base": "main",
                "draft": False, "maintainer_can_modify": False}
    if len(document["body"]) > 20000:
        _fail("generated document exceeds the transport bound")
    return document


def _updated_ledger_document(document, spec, changelog):
    """One canonical ledger document with this tag's row carrying the changelog."""
    if not isinstance(document, dict) or not isinstance(document.get("entries"), list):
        _fail("release-intents.json is malformed")
    entries = deepcopy(document["entries"])
    matches = [row for row in entries if row.get("tag") == spec["tag"]]
    if len(matches) != 1:
        _fail("the merged ledger does not carry exactly one row for this tag")
    row = matches[0]
    if row.get("changelog") is not None:
        _fail("the ledger row already binds a changelog")
    row["changelog"] = changelog
    return dict(document, entries=entries)


class ChangelogCommit:
    """Create the changelog docs commit on an owned worktree at canonical main.

    `editorial()` returns the reviewed (changes, exclusions) pair; trusted
    composition supplies it and the canonical ledger source. Mutations are
    idempotent from committed state: an existing worktree at the exact main
    tip resumes, nothing refreezes once committed.
    """

    def __init__(self, root, repository_root, *, spec, editorial, author_name,
                 author_email):
        validate_spec(spec)
        self.root = Path(root).absolute()
        if self.root.resolve() != self.root:
            _fail("worktree root contains a symlink")
        self.repository_root = Path(repository_root).absolute()
        self.spec = deepcopy(spec)
        self.editorial = editorial
        self.author = dict(author_name=author_name, author_email=author_email)
        self._workspace = None

    def _git(self, *args):
        from .publication_workspace import PublicationWorkspace, PublicationWorkspaceError
        if self._workspace is None:
            self._workspace = PublicationWorkspace(self.root)
        try:
            return self._workspace.git(*args)
        except PublicationWorkspaceError as error:
            raise ChangelogStepError(f"worktree Git is unavailable: {error}") from None

    def _repository_git(self, *args):
        from .publication_workspace import PublicationWorkspace, PublicationWorkspaceError
        repository = PublicationWorkspace(self.repository_root)
        try:
            return repository.git(*args)
        except PublicationWorkspaceError as error:
            raise ChangelogStepError(f"repository Git is unavailable: {error}") from None

    def _frozen(self, ledger_rows):
        """freeze() needs dataclass entries; rows here are the committed JSON."""
        from .model import Disposition, ReleaseIntent, ReleaseKind, ReleaseLedger

        def entry(row):
            return ReleaseIntent(
                row["tag"], ReleaseKind(row["kind"]), row["identity"],
                row["target_revision"], Disposition(row["disposition"]), row["profile"],
                tuple(row.get("evidence_paths", ())),
                channel=row.get("channel"), snapshot=row.get("snapshot"),
                merged_main_run_id=row.get("merged_main_run_id"),
                changelog=row.get("changelog"))
        entries = tuple(entry(row) for row in ledger_rows)
        intent = next((item for item in entries if item.tag == self.spec["tag"]), None)
        if intent is None:
            _fail("the ledger has no row for this tag")
        changes, exclusions = self.editorial()
        try:
            return freeze_changelog(self.root, intent, ReleaseLedger(entries, ()),
                                    changes, exclusions)
        except ChangelogError as error:
            raise ChangelogStepError(str(error)) from None

    def _declared_path(self, path):
        return path in (str(_LEDGER_RELATIVE), evidence_document_relative(self.spec))

    def _stage_declared(self):
        raw = self._git("ls-files", "-m", "-o", "--exclude-standard", "-z")
        changed = [name for name in raw.decode(errors="replace").split("\0") if name]
        unexpected = [name for name in changed if not self._declared_path(name)]
        if unexpected:
            _fail("worktree carries files outside the declared changelog paths: "
                  + unexpected[0])
        for name in changed:
            if not (self.root / name).exists():
                _fail("declared changelog path was deleted from the worktree: " + name)
            self._git("add", "--", name)

    def _committed_ledger(self):
        raw = self._git("show", "HEAD:" + str(_LEDGER_RELATIVE))
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            _fail("committed release-intents.json is malformed")

    def _completed(self):
        """The already-created changelog commit for this operation, or None."""
        head = self._git("rev-parse", "HEAD").decode().strip()
        if head == self.spec["base_revision"]:
            return None
        self._git("merge-base", "--is-ancestor", self.spec["base_revision"], head)
        if self._git("status", "--porcelain").strip():
            _fail("existing worktree has uncommitted changes")
        document = self._committed_ledger()
        rows = document.get("entries") if isinstance(document, dict) else None
        if not isinstance(rows, list):
            _fail("committed release-intents.json is malformed")
        matches = [row for row in rows if row.get("tag") == self.spec["tag"]]
        if len(matches) != 1 or matches[0].get("changelog") is None:
            _fail("the committed ledger row does not carry this changelog")
        from .changelog import validate as validate_changelog
        try:
            validate_changelog(matches[0]["changelog"])
        except ChangelogError as error:
            raise ChangelogStepError(str(error)) from None
        if canonical_sha256(matches[0]["changelog"]) != self.spec["changelog_sha256"]:
            _fail("the committed changelog differs from the reviewed document")
        self._git("cat-file", "-e", "HEAD:" + evidence_document_relative(self.spec))
        return head

    def completed_head(self):
        if not self.root.exists():
            return None
        return self._completed()

    def _ensure_worktree(self, *, before_write):
        if self.root.exists():
            return self._completed()
        before_write()
        if self.root.exists():
            return self._completed()
        self._repository_git("worktree", "add", "--detach", str(self.root),
                             self.spec["base_revision"])
        head = self._git("rev-parse", "HEAD").decode().strip()
        if head != self.spec["base_revision"]:
            _fail("worktree is not at the recorded canonical main tip")
        return None

    def commit(self, *, before_write):
        """Create the single changelog docs commit; returns (head_sha, tree_sha)."""
        if not callable(before_write) or not callable(self.editorial):
            _fail("requires the parent write guard and the reviewed editorial input")
        completed = self._ensure_worktree(before_write=before_write)
        if completed is not None:
            tree = self._git("rev-parse", "HEAD^{tree}").decode().strip()
            return completed, tree
        ledger = json.loads((self.root / _LEDGER_RELATIVE).read_text(encoding="utf-8"))
        changelog = self._frozen(ledger["entries"])
        if canonical_sha256(changelog) != self.spec["changelog_sha256"]:
            _fail("the frozen changelog differs from the reviewed document")
        updated = _updated_ledger_document(ledger, self.spec, changelog)
        (self.root / _LEDGER_RELATIVE).write_text(
            json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        from .changelog import render as render_changelog
        notes = render_changelog(changelog)
        (self.root / evidence_document_relative(self.spec)).write_text(
            notes, encoding="utf-8")
        self._stage_declared()
        before_write()
        self._git("-c", "user.name=" + self.author["author_name"],
                  "-c", "user.email=" + self.author["author_email"],
                  "commit", "-m",
                  f"docs(release): bind {self.spec['product_build']} canary changelog")
        head = self._git("rev-parse", "HEAD").decode().strip()
        tree = self._git("rev-parse", "HEAD^{tree}").decode().strip()
        return head, tree


class ChangelogBranch(PublicationBranch):
    _validate_spec = staticmethod(validate_spec)
    _document = staticmethod(pr_document)

    def __init__(self, root, repository, *, token, authorize):
        super().__init__(root, repository, token=token, authorize=authorize)
        self.api = GitHubClient(token=token).witness_pr_request


class ChangelogPullRequest(WitnessPullRequest):
    _validate_spec = staticmethod(validate_spec)
    _document = staticmethod(pr_document)


class ChangelogPrSequence:
    """Reuse the candidate sequence machinery with changelog-only children."""

    from .candidate_pr_sequence import CandidatePrSequence as _Base

    _impl = None

    def __new__(cls, root, *, branch, pr):
        if cls._impl is None:
            class ChangelogSequence(cls._Base):
                _validate_spec = staticmethod(validate_spec)
                _document = staticmethod(pr_document)
                _branch_type, _pr_type = ChangelogBranch, ChangelogPullRequest
                _state_file = "changelog-pr-sequence.json"
                _schema = "lmdj.changelog-pr-sequence.v1"
            cls._impl = ChangelogSequence
        return cls._impl(root, branch=branch, pr=pr)


class ChangelogCarrier:
    def __init__(self, *, commit, sequence):
        if type(commit) is not ChangelogCommit \
                or not isinstance(sequence, ChangelogPrSequence._Base) \
                or getattr(sequence, "_state_file", None) != "changelog-pr-sequence.json":
            _fail("requires the concrete changelog commit and changelog PR sequence")
        self.commit, self.sequence = commit, sequence
        self._spec = None

    def _recovered_spec(self):
        if not self.commit.root.exists():
            return None
        head = self.commit.completed_head()
        if head is None:
            return None
        tree = self.commit._git("rev-parse", "HEAD^{tree}").decode().strip()
        return dict(deepcopy(self.commit.spec), head_sha=head, tree_sha=tree)

    def observe(self, state, operation):
        recovered = self._recovered_spec()
        if recovered is not None:
            self._spec = recovered
        if self._spec is None:
            return Observation("pending")
        result = self.sequence.observe(self._spec, initialize=False)
        if result["status"] == "merged":
            merge = self.sequence.pr.observe_merge(self._spec)
            if merge.get("status") != "verified":
                return Observation("unknown")
            evidence = merge.get("evidence")
            digest = evidence.get("sha256") if isinstance(evidence, dict) else None
            if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
                _fail("verified merge exposes no evidence digest")
            return Observation("verified", {"sha256": digest,
                                            "reference": "changelog-pr:"
                                            + str(merge.get("merge", {}).get("number", "?"))})
        if result["status"] in ("absent", "pending"):
            return Observation("pending")
        return Observation("unknown" if result["status"] == "unknown" else "conflict")

    def advance(self, state, operation, *, before_write):
        if not callable(before_write):
            _fail("requires the driver's durable write guard")
        head, tree = self.commit.commit(before_write=before_write)
        self._spec = dict(deepcopy(self.commit.spec), head_sha=head, tree_sha=tree)
        result = self.sequence.advance(self._spec, before_write=before_write)
        if result["status"] == "merged":
            merge = self.sequence.pr.observe_merge(self._spec)
            if merge.get("status") != "verified":
                return Observation("unknown")
            evidence = merge.get("evidence")
            digest = evidence.get("sha256") if isinstance(evidence, dict) else None
            if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
                _fail("verified merge exposes no evidence digest")
            return Observation("verified", {"sha256": digest,
                                            "reference": "changelog-pr:"
                                            + str(merge.get("merge", {}).get("number", "?"))})
        if result["status"] in ("absent", "pending"):
            return Observation("pending")
        return Observation("unknown" if result["status"] == "unknown" else "conflict")
