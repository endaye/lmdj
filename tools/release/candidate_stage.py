"""One carrier for the driver's `candidate` step: preparation + transition.

Preparation (request -> installed source -> snapshot -> checked cut) runs
first inside the same far-side pair; the managed candidate transition (cut PR
-> witness -> witness PR) consumes its receipts. Observation allocates and
executes nothing; execution enrolls once, resumes each child exactly where its
durable history stands, and never reconstructs a lost child. This composes
existing controllers behind the existing driver protocol; it adds no second
driver and no extra journal layer.
"""

from .candidate_preparation import CandidatePreparation
from .candidate_transition import CandidateTransition
from .orchestration_driver import Observation


class CandidateStageError(ValueError):
    pass


def _fail(reason):
    raise CandidateStageError(
        f"why: candidate stage {reason}; remedy: restore the original request "
        "and child histories without reallocating, reinstalling or replaying "
        "unknown effects")


class CandidateStage:
    def __init__(self, *, preparation, transition_factory):
        """preparation: a constructed CandidatePreparation (owns its root).

        transition_factory(source, checked_cut, frozen) -> CandidateTransition.
        Trusted composition supplies the concrete roots, GitHub transport,
        review gates and fixed Task author; no production value is chosen here.
        """
        if type(preparation) is not CandidatePreparation:
            _fail("requires the concrete candidate preparation controller")
        self.preparation = preparation
        self._transition_factory = transition_factory
        self._transition = None

    def _managed(self):
        if self._transition is None:
            prepared = self.preparation.observe()
            if prepared.get("status") != "verified":
                _fail("preparation is not verified; the transition has no input")
            self._transition = self._transition_factory(
                prepared["source"], prepared["checked_cut"], prepared["frozen"])
        return self._transition

    def observe(self, state, operation):
        """Preparation status first; only a verified preparation observes the transition."""
        observed = self.preparation.observe()
        status = observed["status"]
        if status != "verified":
            if status in ("absent", "pending"):
                return Observation("pending")
            return Observation(status if status in ("conflict", "unknown") else "unknown")
        return self._managed().observe(state, operation)

    def advance(self, state, operation, *, before_write):
        """Enroll preparation once, drive it, then drive the transition."""
        if not callable(before_write):
            _fail("requires the driver's durable write guard")
        enrolled = self.preparation.observe(initialize=True)
        if enrolled["status"] not in ("absent", "pending", "verified"):
            return Observation("unknown")
        prepared = self.preparation.prepare(before_write=before_write)
        if prepared["status"] != "verified":
            return Observation(
                "pending" if prepared["status"] in ("absent", "pending") else "unknown")
        return self._managed().advance(state, operation, before_write=before_write)
