"""Bind one supported durable dispatch to its parent and separate effect proof.

Trusted composition must supply original candidate/Draft/prior scope binding
and a read-only effect verifier. Correlation is never effect acceptance. This
module does not implement those production verifiers or select a live backend.
"""
from copy import deepcopy

from .durable_dispatch import DurableDispatch, validate_spec
from .model import canonical_sha256
from .orchestration import JournalError, _validate_state
from .orchestration_driver import Observation


WORKFLOW_STEPS = {"publish-release.yml":"publication",
                  "deploy-web-runtime-host.yml":"runtime",
                  "deploy-creator-web.yml":"creator"}


def require(value, reason):
    if not value:
        raise JournalError(f"why: managed dispatch {reason}; remedy: restore the original parent and child scope and independently verify the exact effect")


class DispatchTransition:
    def __init__(self, controller, spec, *, bind, verify_effect):
        require(type(controller) is DurableDispatch and callable(bind) and callable(verify_effect),
                "trusted dependencies are missing")
        validate_spec(spec)
        self.controller, self.spec = controller, deepcopy(spec)
        self.bind, self.verify_effect = bind, verify_effect
        self.step = WORKFLOW_STEPS[spec["workflow"]]

    def _bound(self, state, operation):
        _validate_state(state)
        validate_spec(self.spec)
        request = state["request"]
        expected = canonical_sha256({"request":state["request_digest"],"step":self.step})
        require(WORKFLOW_STEPS[self.spec["workflow"]] == self.step
                and operation.get("step") == self.step and operation.get("operation_id") == expected
                and self.spec["operation_id"] == expected and self.spec["request_sha256"] == state["request_digest"]
                and request["repository"] == "endaye/lmdj" and self.spec["actor_id"] == request["actor_id"]
                and (request["mode"] != "tag" or self.spec["inputs"]["tag"] == request["requested_tag"]),
                "does not match its original request")
        # Mandatory trusted code resolves the candidate, release plan/ID and
        # deployment prior from verified parent evidence, not user JSON flags.
        self.bind(deepcopy(state),deepcopy(operation),deepcopy(self.spec))
        return any(row["operation_id"] == expected for row in state["transitions"])

    def observe(self, state, operation):
        started = self._bound(state,operation)
        result = self.controller.observe(self.spec,initialize=not started)
        if result["status"] != "correlated":
            observed = Observation(result["status"])
            observed.validate()
            return observed
        binding = result["binding"]
        observed = self.verify_effect(deepcopy(state),deepcopy(operation),deepcopy(binding))
        require(type(observed) is Observation,"effect verifier returned an unsupported result")
        observed.validate()
        # The workflow exists. Missing effects cannot authorize another POST.
        if observed.status == "absent":return Observation("unknown")
        if observed.status != "verified":return observed
        evidence = {"sha256":canonical_sha256({"schema":"lmdj.dispatch-effect.v1",
                    "binding":binding,"effect":observed.evidence}),
                    "reference":observed.evidence["reference"]}
        return Observation("verified",evidence)

    def advance(self, state, operation, *, before_post):
        require(callable(before_post),"parent write guard is missing")
        require(self._bound(state,operation) and state["transitions"]
                and state["transitions"][-1] == operation and operation["status"] == "intent",
                "has no durable frontier intent")
        # Must already be enrolled before parent intent. Missing state never
        # calls start, and the return value is never accepted as effect proof.
        def write_guard():
            self._bound(state,operation)
            before_post()
        self.controller.resume(self.spec,before_post=write_guard)
