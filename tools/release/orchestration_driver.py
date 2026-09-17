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

    A resumed opaque unresolved intent is observe-only. Even positive absence cannot
    prove an earlier timed-out write will not arrive later. It is never replayed
    automatically. The backend may observe a positively identified completed run,
    but may not dispatch from observe. The concrete enrolled publication PR
    child may advance its next unattempted effect after pending/absent observation;
    its own durable POST/PUT intents still forbid unknown-write replay.
    """

    def __init__(self, root, policy: OrchestrationPolicy, backend: TransitionBackend, *, publication_pr=None, dispatches=(), candidate=None):
        # Deferred import avoids the PR controller's Observation import cycle.
        from .evidence_pr_transition import EvidencePrTransition
        from .dispatch_transition import DispatchTransition
        from .candidate_transition import CandidateTransition
        if candidate is not None and type(candidate) is not CandidateTransition:
            raise JournalError("why: unsupported managed candidate; remedy: use the concrete checked-cut and witness transition, not an arbitrary retry callback")
        self.candidate = candidate
        if publication_pr is not None and type(publication_pr) is not EvidencePrTransition:
            raise JournalError("why: unsupported managed release adapter; remedy: use the concrete publication PR transition, not an arbitrary retry callback")
        self.root, self.policy, self.backend = root, policy, backend
        self.publication_pr = publication_pr
        if (type(dispatches) not in (tuple,list) or any(type(item) is not DispatchTransition for item in dispatches)
                or len({item.step for item in dispatches}) != len(dispatches)):
            raise JournalError("why: unsupported or duplicate managed dispatch; remedy: compose one concrete dispatch transition per release step")
        self.dispatches = {item.step:item for item in dispatches}

    def _managed(self, operation):
        if operation["step"] == "candidate":
            return self.candidate
        return self.publication_pr if operation["step"] == "published_record" else self.dispatches.get(operation["step"])

    def run(self, request: dict) -> DriveResult:
        with RequestJournal(self.root) as journal:
            self._authenticate(request)
            state = journal.resolve_active(request)
            if state is None:
                state = journal.create(request)
            else:
                # Incoming authority does not renew or replace the original
                # grant. All adapters and operations stay bound to this state.
                self._authenticate(state["request"])
                journal.bind_alias(request, state)
            return self._advance(journal, state)

    def resume(self, request_id: str) -> DriveResult:
        with RequestJournal(self.root) as journal:
            alias = journal.read_alias(request_id)
            if alias is not None:
                self._authenticate(alias["request"])
                state = journal.resolve_active(alias["request"])
            else:
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
            observer = self._managed(operation) or self.backend
            result = observer.observe(deepcopy(state), deepcopy(operation))
        except Exception:
            # Read failures carry no negative proof and may contain secrets.
            return Observation("unknown")
        if type(result) is not Observation:
            raise JournalError("why: invalid adapter result; remedy: repair the trusted adapter")
        result.validate()
        return result

    def _advance_managed(self, journal, state, operation):
        self._authenticate(state["request"])
        journal._active()
        try:
            managed = self._managed(operation)
            def before_write():
                self._authenticate(state["request"])
                journal._active()
            if operation["step"] in self.dispatches:
                managed.advance(deepcopy(state),deepcopy(operation),before_post=before_write)
            else:
                managed.advance(deepcopy(state), deepcopy(operation), before_write=before_write)
        except Exception:
            return Observation("unknown")
        return self._observe(journal.read(state["request"]["id"]), operation)

    def _backend_carrier(self, operation):
        """The enrolled backend carrier for this step, when it owns one."""
        carriers = getattr(self.backend, "carriers", None)
        if not isinstance(carriers, dict):
            return None
        return carriers.get(operation["step"])

    def _backend_advance(self, operation):
        """A backend carrier that drives its own effect under the write guard."""
        carrier = self._backend_carrier(operation)
        return carrier if callable(getattr(carrier, "advance", None)) else None

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
                if self._managed(operation) and observed.status in ("absent", "pending"):
                    observed = self._advance_managed(journal, journal.read(request_id), operation)
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
            managed = self._managed(operation)
            advanced = self._backend_advance(operation)
            if observed.status not in (("absent", "verified", "pending")
                                       if managed or advanced else ("absent", "verified")):
                return result(observed.status, step)
            journal.begin(request_id, step)
            if managed and observed.status != "verified":
                observed = self._advance_managed(journal, journal.read(request_id), operation)
                if observed.status != "verified":
                    return result("unknown" if observed.status == "absent" else observed.status, step)
            elif advanced is not None and observed.status != "verified":
                self._authenticate(state["request"])
                state = journal.read(request_id)

                def guard():
                    self._authenticate(state["request"])
                    journal._active()

                try:
                    advanced.advance(deepcopy(state), deepcopy(operation), before_write=guard)
                except Exception:
                    # External errors may embed credentials; never persist or
                    # expose their strings as the request's public status.
                    return result("unknown", step)
                observed = self._observe(journal.read(request_id), operation)
                if observed.status != "verified":
                    return result("unknown" if observed.status == "absent" else observed.status, step)
            elif observed.status == "absent":
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
