"""One durable dispatch intent, with read-only reconciliation after any attempt.

The trusted parent owns one canonical operation directory and original request
authority. Never start the same operation in another directory or reconstruct
lost state. This controller does not implement the parent release authority,
effect-readiness gates, global Site locks or publication/deployment acceptance.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import uuid

from .batch_reference import digest, positive, sha
from .dispatch_evidence import DispatchEvidenceConsumer, DispatchEvidenceError
from .dispatch_receipt import WORKFLOWS, receipt, unique
from .github_api import GitHubClient
from .model import canonical_json
from .orchestration import RequestJournal

MAX_STATE_BYTES = 1024 * 1024


class DurableDispatchError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise DurableDispatchError(f"why: durable dispatch {reason}; remedy: restore and reconcile the original operation journal; never create a replacement dispatch")


def validate_spec(spec):
    require(type(spec) is dict and set(spec) == {"request_sha256","operation_id","repository_id","actor_id",
        "workflow","workflow_id","control_revision","producer_revision","inputs"}, "scope fields are invalid")
    require(digest(spec["request_sha256"]) and digest(spec["operation_id"])
        and positive(spec["repository_id"]) and positive(spec["actor_id"]) and positive(spec["workflow_id"])
        and sha(spec["control_revision"]) and sha(spec["producer_revision"])
        and type(spec["workflow"]) is str and spec["workflow"] in WORKFLOWS
        and type(spec["inputs"]) is dict and spec["inputs"].get("request_id") == spec["operation_id"], "scope identities are invalid")
    # Reuse the closed producer input validator, not a second input policy.
    env = {"GITHUB_REPOSITORY_ID":str(spec["repository_id"]),"GITHUB_ACTOR_ID":str(spec["actor_id"]),
        "GITHUB_RUN_ID":"1","GITHUB_RUN_ATTEMPT":"1","GITHUB_EVENT_NAME":"workflow_dispatch",
        "GITHUB_REF":"refs/heads/main","GITHUB_REPOSITORY":"endaye/lmdj",
        "GITHUB_SHA":spec["control_revision"],"GITHUB_WORKFLOW_SHA":spec["control_revision"],
        "GITHUB_WORKFLOW_REF":f"endaye/lmdj/.github/workflows/{spec['workflow']}@refs/heads/main"}
    try:
        receipt({"inputs":spec["inputs"],"ref":"main","repository":{"id":spec["repository_id"],
                 "full_name":"endaye/lmdj"},"sender":{"id":spec["actor_id"]}},env,spec["workflow"],spec["control_revision"])
    except ValueError:
        require(False,"dispatch inputs are invalid")


class DurableDispatch:
    def __init__(self, root, *, client, consumer, authorize, ready):
        require(type(client) is GitHubClient and type(consumer) is DispatchEvidenceConsumer and callable(authorize) and callable(ready),
                "trusted dependencies are invalid")
        self.root, self.client, self.consumer, self.authorize = Path(root).absolute(),client,consumer,authorize
        self.ready = ready

    def _authorize(self,spec):
        validate_spec(spec)
        for key, value in {"repository_id":self.consumer.repository_id,"workflow":self.consumer.workflow,
                           "workflow_id":self.consumer.workflow_id,"producer_revision":self.consumer.producer}.items():
            require(spec[key] == value,"reader configuration changed")
        try:
            # Original request and live authority/protection must be verified
            # by trusted production code, not a JSON flag.
            self.authorize(deepcopy(spec))
        except Exception:
            require(False,"original authority is unavailable")

    def _ready(self,spec):
        try:
            self.ready(deepcopy(spec))
        except Exception:
            require(False,"effect prerequisites are unavailable")

    @staticmethod
    def _read(journal,spec):
        journal._active()
        try:
            fd=os.open("dispatch.json",os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=journal.directory)
        except FileNotFoundError:
            return None
        try:
            journal._private(fd)
            with os.fdopen(fd,"rb",closefd=False) as stream:raw=stream.read(MAX_STATE_BYTES+1)
            require(len(raw)<=MAX_STATE_BYTES,"state exceeds its size bound")
            state=json.loads(raw,object_pairs_hook=unique)
            require(type(state) is dict and set(state)=={"schema","spec","baseline","post_intent"}
                    and state["schema"]=="lmdj.durable-dispatch.v1" and canonical_json(state)==raw
                    and canonical_json(state["spec"])==canonical_json(spec)
                    and type(state["post_intent"]) is bool,"state is malformed or rebound")
            baseline=state["baseline"]
            require((baseline is None and not state["post_intent"]) or
                    (type(baseline) is list and len(baseline)<=10000 and all(positive(i) for i in baseline)
                     and baseline==sorted(set(baseline)) and state["post_intent"]),"baseline/intent is invalid")
            return state
        except (ValueError,UnicodeError):
            require(False,"state is corrupt or bound to another operation")
        finally:
            os.close(fd)

    @staticmethod
    def _save(journal,state):
        journal._active()
        raw = canonical_json(state)
        require(len(raw) <= MAX_STATE_BYTES, "state exceeds its size bound")
        name=".dispatch-pending-"+uuid.uuid4().hex
        fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=journal.directory)
        try:
            with os.fdopen(fd,"wb",closefd=False) as stream:
                stream.write(raw);stream.flush();os.fsync(stream.fileno())
            journal._active()
            os.replace(name,"dispatch.json",src_dir_fd=journal.directory,dst_dir_fd=journal.directory)
            os.fsync(journal.directory)
        finally:
            os.close(fd)

    def start(self,spec):
        """Enroll only a newly created directory; existing storage is resume-only."""
        return self._visit(spec,initialize=True,advance=True)

    def observe(self,spec,*,initialize=False):
        """No remote writes. Optional local enrollment is only for a new parent leg."""
        return self._visit(spec,initialize=initialize,advance=False)

    def resume(self,spec,*,before_post=None):
        return self._visit(spec,initialize=False,advance=True,before_post=before_post)

    def _visit(self,spec,*,initialize,advance,before_post=None):
        require(before_post is None or callable(before_post),"parent write guard is invalid")
        self._authorize(spec)
        require(self.root.resolve()==self.root,"directory is not canonical")
        created=False
        if initialize:
            try:
                self.root.mkdir(mode=0o700)
                created=True
            except FileExistsError:
                pass
            if created:
                parent=os.open(self.root.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                try:os.fsync(parent)
                finally:os.close(parent)
        if not self.root.exists():return {"status":"unknown","binding":None}
        with RequestJournal(self.root) as journal:
            if created:
                state={"schema":"lmdj.durable-dispatch.v1","spec":deepcopy(spec),"baseline":None,"post_intent":False}
                self._save(journal,state)
            else:
                state=self._read(journal,spec)
            if state is None:return {"status":"unknown","binding":None}
            return self._advance(journal,state,before_post=before_post) if advance else self._observe(journal,state)

    def _advance(self,journal,state,*,before_post=None):
        spec=state["spec"]
        self._authorize(spec)
        if not state["post_intent"]:
            self._ready(spec)
            suffix="/actions/workflows/"+spec["workflow"]+"/runs"
            try:
                first=self.consumer.pages(suffix,"workflow_runs")
                second=self.consumer.pages(suffix,"workflow_runs")
                baseline=sorted(row["id"] for row in first)
                require(baseline==sorted(row["id"] for row in second),"pre-POST inventory changed")
            except DispatchEvidenceError:
                return {"status":"unknown","binding":None}
            self._authorize(spec)
            self._ready(spec)
            state.update(baseline=baseline,post_intent=True)
            self._save(journal,state)
            journal._active()
            def write_guard():
                journal._active()
                self._authorize(spec)
                self._ready(spec)
                if before_post is not None:before_post()
                journal._active()
            try:
                self.client.dispatch_release(deepcopy(spec),before_post=write_guard)
            except Exception:
                # Includes timeouts and explicit API refusal. The durable
                # intent cannot be erased or used to justify another POST.
                pass
        return self._observe(journal,state)

    def _observe(self,journal,state):
        spec=state["spec"]
        journal._active()
        self._authorize(spec)
        if not state["post_intent"]:return {"status":"absent","binding":None}
        return self.consumer.discover(actor_id=spec["actor_id"],control_revision=spec["control_revision"],
                                      inputs=spec["inputs"],prior_run_ids=state["baseline"])
