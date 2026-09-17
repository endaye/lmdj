"""Enrolled step carriers behind the single sequential release driver.

One carrier owns one step's far-side observe/execute pair. A step with no
enrolled carrier is refused by name before any request is created: an unowned
step is never reported absent, pending or verified, and no adapter invents a
result for it.
"""

from .orchestration import JournalError


class ReleaseBackend:
    """Driver adapter contract over the carriers enrolled for one release scope."""

    def __init__(self, git, github, carriers=()):
        self.git, self.github = git, github
        enrolled = tuple(carriers)
        self.carriers = {carrier.step: carrier for carrier in enrolled}
        if len(self.carriers) != len(enrolled):
            raise JournalError("why: duplicate release step carrier; remedy: enroll one carrier per step")

    def missing(self, steps) -> tuple[str, ...]:
        """Steps this backend cannot drive; the caller refuses instead of half-driving."""
        return tuple(step for step in steps if step not in self.carriers)

    def authenticate(self, request, policy) -> None:
        """Revalidate the authenticated actor and the pinned, reachable control.

        The driver already refuses a request whose pinned policy digest is not the
        enrolled one, so `policy` is accepted and not re-read here.

        # ponytail: actor identity and control reachability only; the reviewed
        # authorization record is bound by the carrier that owns the step needing
        # it. Widen this only when a carrier proves it must read more.
        """
        if self.github.get_authenticated_actor() != request["actor_id"]:
            raise JournalError("why: request actor is not the authenticated actor")
        if not self.git.is_main_ancestor(request["control_revision"]):
            raise JournalError("why: pinned control revision is not reachable canonical history")

    def observe(self, state, operation):
        return self._carrier(operation).observe(state, operation)

    def advance(self, state, operation, before_write) -> None:
        """Drive an unattempted effect under the driver's durable write guard."""
        self._carrier(operation).advance(state, operation, before_write=before_write)

    def execute(self, state, operation) -> None:
        self._carrier(operation).execute(state, operation)

    def _carrier(self, operation):
        try:
            return self.carriers[operation["step"]]
        except KeyError:
            raise JournalError(
                f"why: step {operation['step']} has no enrolled carrier; "
                "remedy: enroll that step's exact far-side verifier"
            ) from None
