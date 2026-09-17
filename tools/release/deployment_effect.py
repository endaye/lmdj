"""Authenticate recorded Host deployment effects; never deploy or infer retries.

Trusted parent composition supplies the frozen signed-release/Site/prior
projection. This verifies the original run's retained evidence, not the current
production alias; final live verification and request authority remain separate.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

from .batch_reference import digest, sha
from .dispatch_evidence import DispatchEvidenceConsumer
from .dispatch_receipt import unique
from .durable_dispatch import validate_spec
from .model import canonical_json, canonical_sha256
from .orchestration import JournalError, _validate_state
from .orchestration_driver import Observation

HOSTS = {
    "deploy-web-runtime-host.yml": ("runtime", "web-runtime-host", "runtime-host-deployment-evidence", "lmdj.web-runtime-host.deployment-evidence.v3"),
    "deploy-creator-web.yml": ("creator", "creator-web", "creator-host-deployment-evidence", "lmdj.creator-web.deployment-evidence.v2"),
}
LIMIT = 1024 * 1024  # Existing promotion evidence archive bound, not a log dump.
ROOT = Path(__file__).resolve().parents[2]


def require(value, reason):
    if not value:
        raise JournalError(f"why: deployment effect {reason}; remedy: reconcile the original run, frozen release, Site and prior evidence without redispatching")


class DeploymentEffect:
    def __init__(self, *, consumer, spec, expected):
        validate_spec(spec)
        require(type(consumer) is DispatchEvidenceConsumer and spec["workflow"] in HOSTS,
                "trusted Host reader is missing")
        require(consumer.repository_id == spec["repository_id"] and consumer.workflow == spec["workflow"]
                and consumer.workflow_id == spec["workflow_id"] and consumer.producer == spec["producer_revision"],
                "reader configuration differs")
        require(type(expected) is dict and set(expected) == {
            "target_revision", "product_build", "host_version", "site_id", "archive", "release_files", "prior", "prior_site_sha256"},
            "frozen projection is missing")
        require(digest(expected["prior_site_sha256"])
                and expected["prior_site_sha256"] == spec["inputs"]["prior_site_sha256"],
                "original Site snapshot differs from dispatch")
        require(sha(expected["target_revision"]) and all(type(expected[k]) is str and expected[k]
                for k in ("product_build", "host_version", "site_id")), "frozen identity is invalid")
        require(type(expected["archive"]) is dict and set(expected["archive"]) == {"filename", "sha256"}
                and type(expected["archive"]["filename"]) is str and digest(expected["archive"]["sha256"]),
                "frozen archive is invalid")
        require(type(expected["release_files"]) is dict and set(expected["release_files"]) == {"index_sha256", "manifest_sha256"}
                and all(digest(v) for v in expected["release_files"].values()), "frozen bytes are invalid")
        prior = expected["prior"]
        require(prior is None or (type(prior) is dict and set(prior) == {
            "deploy_id", "deploy_url", "product_build", "host_version", "index_sha256", "manifest_sha256"}
            and all(type(v) is str and v for v in prior.values())
            and digest(prior["index_sha256"]) and digest(prior["manifest_sha256"])), "frozen prior is invalid")
        self.consumer = consumer
        self.spec, self.expected = deepcopy(spec), deepcopy(expected)
        self.step, self.host, self.artifact_name, self.contract = HOSTS[spec["workflow"]]

    def _binding(self, binding):
        actual = self.consumer.verify(run_id=binding["run_id"], actor_id=self.spec["actor_id"],
            control_revision=self.spec["control_revision"], inputs=self.spec["inputs"])
        require(actual == binding, "dispatch correlation changed")

    def _outcome(self, binding):
        run = self.consumer.run(binding["run_id"], self.spec["actor_id"], self.spec["control_revision"])
        if run.get("status") in ("queued", "in_progress", "waiting", "pending", "requested"):
            return "pending"
        if run.get("status") != "completed": return "unknown"
        if run.get("conclusion") != "success":
            return "conflict" if run.get("conclusion") in (
                "failure", "cancelled", "timed_out", "action_required", "neutral", "skipped", "stale", "startup_failure") else "unknown"
        jobs = self.consumer.pages(f"/actions/runs/{binding['run_id']}/attempts/1/jobs", "jobs")
        if (len(jobs) != 2 or {j.get("name") for j in jobs} != {"preflight", "deploy"}
                or any(type(j.get("run_id")) is not int or j["run_id"] != binding["run_id"]
                    or type(j.get("run_attempt")) is not int or j["run_attempt"] != 1
                    or j.get("head_sha") != self.spec["control_revision"]
                    or j.get("status") != "completed" or j.get("conclusion") != "success" for j in jobs)):
            return "conflict"
        deploy = next(j for j in jobs if j["name"] == "deploy")
        require(type(deploy.get("steps")) is list, "deploy steps are missing")
        uploads = [s for s in deploy["steps"] if type(s) is dict and s.get("name") == "Upload deployment evidence and failure logs"]
        require(len(uploads) == 1 and uploads[0].get("status") == "completed"
                and uploads[0].get("conclusion") == "success", "evidence upload did not pass")
        return "verified"

    def _document(self, binding):
        c = self.consumer
        inventory = c.pages(f"/actions/runs/{binding['run_id']}/artifacts", "artifacts")
        matches = [a for a in inventory if a.get("name") == self.artifact_name]
        require(len(matches) == 1, "artifact is missing or ambiguous")
        artifact = matches[0]
        require(artifact.get("expired") is False and type(artifact.get("size_in_bytes")) is int
                and 0 < artifact["size_in_bytes"] <= LIMIT, "artifact expired or exceeds the archive bound")
        expires = datetime.strptime(artifact["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        require(expires > c.now, "artifact retention elapsed")
        origin = artifact.get("workflow_run")
        require(type(origin) is dict and all(type(origin.get(k)) is int and origin[k] == v for k,v in {
            "id":binding["run_id"], "repository_id":c.repository_id, "head_repository_id":c.repository_id}.items())
            and origin.get("head_sha") == self.spec["control_revision"] and origin.get("head_branch") == "main",
            "artifact origin differs")
        raw = c.get(f"/actions/artifacts/{artifact['id']}/zip", raw=True)
        require(type(raw) is bytes and 0 < len(raw) <= LIMIT and len(raw) == artifact["size_in_bytes"]
                and artifact.get("digest") == "sha256:" + hashlib.sha256(raw).hexdigest(), "artifact transfer differs")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            require(len(members) == 2 and {m.filename for m in members} == {"evidence.json", "deployment.log"}
                    and sum(m.file_size for m in members) <= LIMIT
                    and all(not m.is_dir() and (m.external_attr >> 16) & 0o170000 != 0o120000 for m in members),
                    "archive members are unsafe or include recovery instead of success")
            member = archive.getinfo("evidence.json")
            require(member.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                    "compression does not support bounded decoding")
            with archive.open(member) as stream:
                payload = stream.read(LIMIT + 1)
            require(len(payload) <= LIMIT, "decoded evidence exceeds size limit")
        document = json.loads(payload, object_pairs_hook=unique)
        require(type(document) is dict, "document is invalid")
        # Execute only this installed trusted tool, never candidate/tag files.
        env = {k:v for k,v in os.environ.items() if k in ("PATH", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP")}
        result = subprocess.run([sys.executable, "-s", "-B", str(ROOT / "apps" / self.host / "tools/deploy_orchestrator.py"),
            "evidence-validate-document", self.contract], input=payload, capture_output=True, env=env, timeout=10)
        require(result.returncode == 0 and result.stdout == canonical_json(document),
                "canonical Host validation refused")
        return document, artifact, inventory, expires

    def __call__(self, state, operation, binding):
        try:
            _validate_state(state)
            request = state["request"]
            op = canonical_sha256({"request":state["request_digest"], "step":self.step})
            require(operation.get("step") == self.step and operation.get("operation_id") == op
                    and self.spec["operation_id"] == op and self.spec["request_sha256"] == state["request_digest"]
                    and request["repository"] == "endaye/lmdj" and request["actor_id"] == self.spec["actor_id"]
                    and (request["mode"] != "tag" or request["requested_tag"] == self.spec["inputs"]["tag"]),
                    "does not belong to the original request")
            self._binding(binding)
            outcome = self._outcome(binding)
            if outcome != "verified": return Observation(outcome)
            document, artifact, inventory, expires = self._document(binding)
            prior = document["prior_good"]
            if prior is not None:
                if canonical_sha256(prior["site_response"]) != self.spec["inputs"]["prior_site_sha256"]:
                    return Observation("conflict")
                prior = {**{k:prior[k] for k in ("deploy_id", "deploy_url", "product_build", "host_version")},
                         **{k:prior["immutable"]["http"]["result"][k] for k in ("index_sha256", "manifest_sha256")}}
            projection = {**{k:document[k] for k in ("product_build", "host_version", "site_id", "archive", "release_files")},
                          "target_revision":document["git_revision"], "prior":prior,
                          "prior_site_sha256":self.spec["inputs"]["prior_site_sha256"]}
            if (projection != self.expected or document["tag"] != self.spec["inputs"]["tag"]
                    or document["github_actions"]["run_id"] != str(binding["run_id"])):
                return Observation("conflict")
            self._binding(binding)
            outcome = self._outcome(binding)
            if outcome != "verified": return Observation(outcome)
            require(self.consumer.pages(f"/actions/runs/{binding['run_id']}/artifacts", "artifacts") == inventory,
                    "artifact inventory changed")
            receipts = [a for a in inventory if a.get("name") == "release-dispatch-correlation"]
            require(len(receipts) == 1, "correlation artifact is missing or ambiguous")
            require(receipts[0]["expires_at"] == binding["artifact_expires_at"], "correlation retention changed")
            receipt_expires = datetime.strptime(binding["artifact_expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            now = self.consumer.now
            require(expires > now and receipt_expires > now, "artifact retention elapsed")
            return Observation("verified", {"sha256":canonical_sha256({"document":document, "artifact":artifact}),
                "reference":document["github_actions"]["run_url"]})
        except Exception:
            # Missing or malformed evidence never means the deployment was absent.
            return Observation("unknown")
