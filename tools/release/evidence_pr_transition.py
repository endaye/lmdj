"""Closed parent/child binding for the durable publication evidence PR leg."""
from copy import deepcopy

from .evidence_pr import EvidencePullRequest, validate_spec
from .model import canonical_sha256
from .orchestration import JournalError, _validate_state
from .orchestration_driver import Observation


class EvidencePrTransition:
    def __init__(self, controller, spec):
        if type(controller) is not EvidencePullRequest:
            raise JournalError("why: managed publication controller is not the supported PR implementation; remedy: compose the trusted durable evidence PR controller")
        validate_spec(spec)
        self.controller, self.spec = controller, deepcopy(spec)

    def _bound(self, state, operation):
        _validate_state(state)
        request = state["request"]
        expected = canonical_sha256({"request": state["request_digest"], "step": "published_record"})
        if (operation.get("step") != "published_record" or operation.get("operation_id") != expected
                or self.spec["operation_id"] != expected or self.spec["request_sha256"] != state["request_digest"]
                or request["repository"] != "endaye/lmdj" or self.spec["actor_id"] != request["actor_id"]
                or (request["mode"] == "tag" and self.spec["tag"] != request["requested_tag"])):
            raise JournalError("why: managed PR is not bound to the original release operation; remedy: restore the exact request and child spec without rebinding either journal")
        return any(row["operation_id"] == expected for row in state["transitions"])

    def observe(self, state, operation):
        started = self._bound(state, operation)
        result = self.controller.observe(self.spec, initialize=not started)
        observed = Observation(result["status"], result["evidence"])
        observed.validate()
        return observed

    def advance(self, state, operation):
        if (not self._bound(state, operation) or not state["transitions"]
                or state["transitions"][-1] != operation or operation["status"] != "intent"):
            raise JournalError("why: managed PR has no durable frontier intent; remedy: initialize its parent transition before any child effect")
        # Its return value is not accepted as completion: parent re-observes.
        self.controller.advance(self.spec, require_initialized=True)
