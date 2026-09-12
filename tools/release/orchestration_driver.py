"""Sequential release driver with authenticated, far-side transition adapters.

Adapters own existing release verifiers and supported command interfaces. They
must use exact identities and conditional writes; dispatch acceptance is never
a verified result. No production adapter is selected by this module.
"""

from copy import deepcopy
from dataclasses import dataclass
from typing import Protocol

from .model import canonical_sha256
from .orchestration import JournalError, RequestJournal, STEPS, _validate_evidence, validate_request
from .orchestration_policy import OrchestrationPolicy


@dataclass(frozen=True)
class Observation:
    # absent means positively absent, not unreadable/not yet indexed.
    status: str
    evidence: dict | None = None

    def validate(self):
        if self.status not in ("verified", "absent", "pending", "conflict", "unknown"):
            raise JournalError("why: invalid adapter observation; remedy: repair the trusted adapter")
        if self.status == "verified":
            _validate_evidence(self.evidence)
        elif self.evidence is not None:
            raise JournalError("why: unverified adapter evidence; remedy: verify the far-side result")


class TransitionBackend(Protocol):
    def authenticate(self, request: dict, policy: OrchestrationPolicy) -> None:
        """Raise if the original authority or current trusted control is invalid.

        Revalidate authenticated actor/authority_ref, canonical repository,
        immutable request scope, pinned policy/control, and current protections.
        Merely matching a user-provided actor ID or digest is not authorization.
        """

    def observe(self, state: dict, operation: dict) -> Observation:
        """Read only. Validate exact request-bound canonical far-side evidence.

        This also revalidates every saved receipt on resume. For historical
        transitions use their existing verifier's immutable proof, not mutable
        state that a legitimate later transition supersedes (Draft → published).
        unknown/ambiguous/expired evidence must never become absent or verified.
        """

    def execute(self, state: dict, operation: dict) -> None:
        """One supported transition, no blind mutation retries.

        Revalidate preconditions at the write boundary, use conditional identity
        guards, and bind all external IDs to operation_id. Return values cannot
        prove completion; observe must independently verify the far side.
        """


@dataclass(frozen=True)
class DriveResult:
    request_id: str
    status: str
    step: str | None
    verified_steps: tuple[str, ...]


class ReleaseDriver:
    """Advance under one journal lock; pending work yields to the service loop.

    A resumed unresolved intent is observe-only. Even positive absence cannot
    prove an earlier timed-out write will not arrive later. It is never replayed
    automatically. The backend may observe a positively identified completed run,
    but may not dispatch from observe. Recovery therefore preserves unknowns.
    """

    def __init__(self, root, policy: OrchestrationPolicy, backend: TransitionBackend):
        self.root, self.policy, self.backend = root, policy, backend

    def run(self, request: dict) -> DriveResult:
        with RequestJournal(self.root) as journal:
            self._authenticate(request)
            state = journal.create(request)
            return self._advance(journal, state)

    def resume(self, request_id: str) -> DriveResult:
        with RequestJournal(self.root) as journal:
            state = journal.read(request_id)
            if state is None:
                raise JournalError("why: request is missing; remedy: use the original request ID")
            self._authenticate(state["request"])
            return self._advance(journal, state)

    def _authenticate(self, request):
        validate_request(request)
        if request["policy_digest"] != self.policy.digest:
            raise JournalError("why: request policy changed; remedy: restore the pinned reviewed policy")
        try:
            self.backend.authenticate(deepcopy(request), self.policy)
        except Exception:
            raise JournalError(
                "why: request authority is unavailable or invalid; remedy: restore the original authenticated authority"
            ) from None

    def _observe(self, state, operation):
        try:
            result = self.backend.observe(deepcopy(state), deepcopy(operation))
        except Exception:
            # Read failures carry no negative proof and may contain secrets.
            return Observation("unknown")
        if type(result) is not Observation:
            raise JournalError("why: invalid adapter result; remedy: repair the trusted adapter")
        result.validate()
        return result

    def _advance(self, journal, state):
        verified = []
        request_id = state["request"]["id"]

        def result(status, step):
            return DriveResult(request_id, status, step, tuple(verified))

        # Persisted verified bits are not accepted without fresh far-side proof.
        for operation in state["transitions"]:
            self._authenticate(state["request"])
            observed = self._observe(state, operation)
            if operation["status"] == "verified":
                if observed.status != "verified":
                    return result("evidence-" + observed.status, operation["step"])
                if observed.evidence != operation["evidence"]:
                    return result("evidence-conflict", operation["step"])
            else:
                if observed.status != "verified":
                    return result("unknown" if observed.status == "absent" else observed.status,
                                  operation["step"])
                journal.confirm(request_id, operation["operation_id"], observed.evidence)
            verified.append(operation["step"])

        for step in STEPS[len(verified):]:
            state = journal.read(request_id)
            self._authenticate(state["request"])
            operation = {"step": step, "operation_id": canonical_sha256(
                {"request": state["request_digest"], "step": step}),
                "status": "intent", "evidence": None}
            observed = self._observe(state, operation)
            if observed.status not in ("absent", "verified"):
                return result(observed.status, step)
            journal.begin(request_id, step)
            if observed.status == "absent":
                # Intent is durable before anything that can perform a write.
                # An auth failure here leaves an unresolved intent, not a retry.
                self._authenticate(state["request"])
                state = journal.read(request_id)
                try:
                    self.backend.execute(deepcopy(state), deepcopy(operation))
                except Exception:
                    # External errors may embed credentials; never persist or
                    # expose their strings as the request's public status.
                    return result("unknown", step)
                observed = self._observe(state, operation)
                if observed.status != "verified":
                    return result("unknown" if observed.status == "absent" else observed.status, step)
            journal.confirm(request_id, operation["operation_id"], observed.evidence)
            verified.append(step)
        return result("complete", None)
