"""Read-only publication effect for a correlated managed dispatch.

Reuse canonical Release verification, including assets, signatures and frozen
notes. Trusted composition supplies original authorization, readiness and the
frozen candidate projection; this verifier grants no mutation authority.
"""
from copy import deepcopy
from datetime import datetime, timezone

from .batch_reference import digest, sha
from .dispatch_evidence import DispatchEvidenceConsumer
from .durable_dispatch import validate_spec
from .model import canonical_sha256
from .orchestration import JournalError, _validate_state
from .orchestration_driver import Observation
from .prepare import PrepareContext
from .publication import collect_publication_state


def require(value, reason):
    if not value:
        raise JournalError(f"why: publication effect {reason}; remedy: reconcile the original candidate, exact workflow run and immutable Release without republishing")


class PublicationEffect:
    def __init__(self, *, context, consumer, spec, expected):
        require(type(context) is PrepareContext and type(consumer) is DispatchEvidenceConsumer,
                "trusted verification dependencies are missing")
        validate_spec(spec)
        require(spec["workflow"] == "publish-release.yml" and context.policy.repository == "endaye/lmdj",
                "is not a canonical publication")
        require(type(expected) is dict and set(expected) == {"target_revision","changelog_sha256","notes_sha256"}
                and sha(expected["target_revision"]) and digest(expected["changelog_sha256"])
                and digest(expected["notes_sha256"]),"frozen candidate projection is invalid")
        require(consumer.repository_id == spec["repository_id"] and consumer.workflow == spec["workflow"]
                and consumer.workflow_id == spec["workflow_id"] and consumer.producer == spec["producer_revision"],
                "reader configuration does not match the dispatch")
        self.context,self.consumer = context,consumer
        self.spec,self.expected = deepcopy(spec),deepcopy(expected)

    def _binding(self,binding):
        observed = self.consumer.verify(run_id=binding["run_id"],actor_id=self.spec["actor_id"],
            control_revision=self.spec["control_revision"],inputs=self.spec["inputs"])
        require(observed == binding,"correlation changed or was not independently authenticated")
        return datetime.strptime(observed["artifact_expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

    def _outcome(self,binding):
        run = self.consumer.run(binding["run_id"],self.spec["actor_id"],self.spec["control_revision"])
        if run.get("status") in ("queued","in_progress","waiting","pending","requested"):
            return "pending"
        if run.get("status") != "completed":return "unknown"
        if run.get("conclusion") == "success":
            jobs = self.consumer.pages(f"/actions/runs/{binding['run_id']}/attempts/1/jobs","jobs")
            if (len(jobs) != 2 or {job.get("name") for job in jobs} != {"preflight","publish"}
                    or any(type(job.get("run_id")) is not int or job["run_id"] != binding["run_id"]
                        or type(job.get("run_attempt")) is not int or job["run_attempt"] != 1
                        or job.get("head_sha") != self.spec["control_revision"]
                        or job.get("status") != "completed" or job.get("conclusion") != "success"
                        for job in jobs)):
                return "conflict"
            return "verified"
        if run.get("conclusion") in ("failure","cancelled","timed_out","action_required","neutral","skipped","stale","startup_failure"):
            return "conflict"
        return "unknown"

    def __call__(self,state,operation,binding):
        try:
            _validate_state(state)
            request = state["request"]
            expected_operation = canonical_sha256({"request":state["request_digest"],"step":"publication"})
            require(operation.get("step") == "publication" and operation.get("operation_id") == expected_operation
                    and self.spec["operation_id"] == expected_operation and self.spec["request_sha256"] == state["request_digest"]
                    and request["repository"] == "endaye/lmdj" and request["actor_id"] == self.spec["actor_id"]
                    and (request["mode"] != "tag" or request["requested_tag"] == self.spec["inputs"]["tag"]),
                    "does not belong to the original request")
            self._binding(binding)
            outcome = self._outcome(binding)
            if outcome != "verified":return Observation(outcome)
            inputs = self.spec["inputs"]
            record,intent = collect_publication_state(inputs["tag"],int(inputs["release_id"]),inputs["plan_sha256"],self.context)
            if (intent.profile != "web-hosts" or intent.channel != "canary"
                    or any(record[key] != value for key,value in self.expected.items())):
                return Observation("conflict")
            expires = self._binding(binding)
            outcome = self._outcome(binding)
            if outcome != "verified":return Observation(outcome)
            # The outcome reads can consume the remaining retention window.
            # Check the authenticated deadline locally after all remote reads.
            require(expires > self.consumer.now, "correlation expired during final outcome verification")
            return Observation("verified",{"sha256":canonical_sha256(record),
                "reference":"https://github.com/endaye/lmdj/releases/tag/"+inputs["tag"]})
        except Exception:
            # Existing verifiers can wrap remote errors; do not infer absence
            # or a retryable mutation from their human-readable messages.
            return Observation("unknown")
