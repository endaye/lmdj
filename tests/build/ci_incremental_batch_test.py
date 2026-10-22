#!/usr/bin/env python3
"""Pure state transitions, not evidence of remote Actions event delivery."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
import incremental_batch as batch
import test_scope

A, B, C, E = (character * 40 for character in "abce")


class SchedulerTest(unittest.TestCase):
    def setUp(self):
        self.policy = test_scope.load_policy(ROOT)
        self.state = batch.new_state("epoch-1")
        self.serial = 0
        self.full = test_scope.select(self.policy, ["contracts/example.json"])
        self.none = test_scope.select(self.policy, ["docs/notes/explanation.md"])
        # Use canonical selection vocabulary; path selection itself is T1's job.
        self.none = test_scope._selection(self.policy, [], ["verified explanatory documentation"])
        self.suite = self.policy.suite_ids[0]
        self.focused = test_scope._selection(self.policy, [self.suite], ["changed owned behavior"])

    def event(self, kind, data):
        self.serial += 1
        return {"id": str(self.serial), "epoch": self.state["epoch"],
                "generation": self.state["generation"], "type": kind, "data": data}

    def apply(self, kind, data):
        event = self.event(kind, data)
        self.state = batch.reduce(self.state, event, self.policy)
        return event

    def observe(self, target):
        self.apply("observe", {"target": target, "descends_pending": True})

    def request(self, target, selection=None, kind="auto", name=None, run=10):
        return batch.make_request(self.policy, request_id=name or f"request-{self.serial}", kind=kind,
                                  base_sha=self.state["processed"], target_sha=target, control_sha=A,
                                  selection=selection or self.full, origin_run={"run_id": run, "attempt": 1})

    def admit(self, request, **observations):
        self.apply("admit", {"request": request, "history_complete": True,
                             "executor_run": request["origin_run"],
                             "ancestor": True, "old_runs_terminal": True, **observations})

    def finish(self, request, outcome="passed"):
        executor = self.state["active"]["executor_run"]
        self.apply("claim", {"request_id": request["id"], "run": executor})
        self.apply("result", {"request_id": request["id"], "run": executor,
                              "target": request["target"], "policy": request["policy"],
                              "outcomes": {suite: outcome for suite in request["selection"]["suites"]},
                              "reference": f"durable-result:{request['id']}", "terminal": True})
        self.apply("advance", {"request_id": request["id"]})

    def bootstrap(self):
        self.observe(A)
        request = self.request(A, kind="bootstrap")
        self.admit(request)
        self.finish(request)

    def test_bootstrap_requires_old_runs_proven_terminal(self):
        self.observe(A)
        with self.assertRaisesRegex(batch.BatchError, "why: old controlled runs.*remedy:"):
            self.admit(self.request(A, kind="bootstrap"), old_runs_terminal=False)
        self.assertIsNone(self.state["active"], "why: uncertain old execution admitted; remedy: require terminal audit")

    def test_bootstrap_does_not_claim_historical_health(self):
        self.bootstrap()
        self.assertTrue(self.state["history_unknown"], "why: bootstrap erased historical uncertainty; remedy: retain it")

    def test_complete_journey_coalesces_pending_tip_after_restart(self):
        self.bootstrap()
        self.observe(B)
        request = self.request(B, self.focused)
        self.admit(request)
        self.assertEqual(self.state["processed"], A, "why: admission advanced cursor; remedy: wait for durable result")
        self.observe(C)
        self.observe(E)
        self.state = deepcopy(self.state)  # serialized/reloaded state, no process-local lock or queue
        self.assertEqual(self.state["requests"][request["id"]]["target"], B,
                         "why: pending tip retargeted active batch; remedy: freeze request")
        self.finish(request)
        self.assertEqual(self.state["pending"], E, "why: completion lost pending tail; remedy: retain latest observation")
        next_request = self.request(E, self.focused)
        self.admit(next_request)
        self.assertEqual(next_request["base"], B, "why: next interval skipped commits; remedy: start at processed")
        self.finish(next_request)
        self.assertEqual(self.state["processed"], E, "why: follow-up did not catch up; remedy: advance after result")

    def test_completion_boundary_new_tip_remains_visible(self):
        self.bootstrap()
        self.observe(B)
        request = self.request(B)
        self.admit(request)
        self.finish(request)
        self.observe(E)
        self.assertEqual((self.state["processed"], self.state["pending"]), (B, E),
                         "why: completion boundary lost merge; remedy: reread main")

    def test_stale_push_cannot_reverse_pending(self):
        self.observe(E)
        with self.assertRaisesRegex(batch.BatchError, "stale or ancestry"):
            self.apply("observe", {"target": B, "descends_pending": False})

    def test_unknown_history_cannot_bootstrap(self):
        self.observe(A)
        with self.assertRaisesRegex(batch.BatchError, "history"):
            self.admit(self.request(A, kind="bootstrap"), history_complete=False)

    def test_nonancestor_is_not_empty_interval(self):
        self.bootstrap()
        self.observe(B)
        with self.assertRaisesRegex(batch.BatchError, "ancestor"):
            self.admit(self.request(B), ancestor=False)

    def test_new_state_cannot_admit_focused_without_bootstrap(self):
        self.observe(A)
        with self.assertRaisesRegex(batch.BatchError, "baseline"):
            self.admit(self.request(A, self.focused))

    def test_none_is_recorded_without_selected_tests(self):
        self.bootstrap()
        self.observe(B)
        request = self.request(B, self.none)
        self.admit(request)
        self.finish(request)
        self.assertEqual(self.state["results"][request["id"]]["outcomes"], {},
                         "why: none fabricated suite passes; remedy: retain empty selected set")
        self.assertEqual(self.state["processed"], B, "why: none failed to account interval; remedy: persist and advance")

    def test_no_change_tick_cannot_start_tests(self):
        self.bootstrap()
        with self.assertRaisesRegex(batch.BatchError, "no new main"):
            self.admit(self.request(A))

    def test_duplicate_event_is_idempotent_even_after_newer_events(self):
        event = self.apply("observe", {"target": A, "descends_pending": True})
        self.observe(B)
        self.assertEqual(batch.reduce(self.state, event, self.policy), self.state,
                         "why: repeated event changed state; remedy: deduplicate by event identity")

    def test_reused_event_identity_with_different_body_rejected(self):
        event = self.apply("observe", {"target": A, "descends_pending": True})
        event["data"]["target"] = B
        with self.assertRaisesRegex(batch.BatchError, "reused"):
            batch.reduce(self.state, event, self.policy)

    def test_stale_generation_rejected_without_mutation(self):
        event = self.event("observe", {"target": A, "descends_pending": True})
        self.observe(B)
        before = deepcopy(self.state)
        with self.assertRaisesRegex(batch.BatchError, "stale generation"):
            batch.reduce(self.state, event, self.policy)
        self.assertEqual(self.state, before, "why: rejected event mutated state; remedy: reduce on a copy")

    def test_old_epoch_cannot_write_recovered_state(self):
        event = self.event("observe", {"target": A, "descends_pending": True})
        event["epoch"] = "old"
        with self.assertRaisesRegex(batch.BatchError, "old recovery"):
            batch.reduce(self.state, event, self.policy)

    def test_second_admission_cannot_overlap_heavy_execution(self):
        self.observe(A)
        request = self.request(A, kind="bootstrap")
        self.admit(request)
        with self.assertRaisesRegex(batch.BatchError, "heavy budget"):
            self.admit(request)

    def test_duplicate_claim_same_run_is_safe(self):
        self.observe(A)
        request = self.request(A, kind="bootstrap")
        self.admit(request)
        for _ in range(2):
            self.apply("claim", {"request_id": request["id"], "run": request["origin_run"]})
        self.assertEqual(self.state["active"]["claim"], request["origin_run"],
                         "why: duplicate claim changed owner; remedy: bind originating run")

    def test_duplicate_dispatch_other_run_cannot_claim(self):
        self.observe(A)
        request = self.request(A, kind="bootstrap")
        self.admit(request)
        with self.assertRaisesRegex(batch.BatchError, "admitted executor"):
            self.apply("claim", {"request_id": request["id"], "run": {"run_id": 99, "attempt": 1}})

    def test_partial_rerun_cannot_claim(self):
        with self.assertRaisesRegex(batch.BatchError, "partial Actions"):
            batch.identity({"run_id": 10, "attempt": 2})

    def test_advance_before_result_cannot_move_cursor(self):
        self.observe(A)
        request = self.request(A, kind="bootstrap")
        self.admit(request)
        with self.assertRaisesRegex(batch.BatchError, "persisted"):
            self.apply("advance", {"request_id": request["id"]})

    def test_cancelled_batch_preserves_debt_before_docs(self):
        self.bootstrap()
        self.observe(B)
        request = self.request(B, self.focused)
        self.admit(request)
        self.finish(request, "cancelled")
        self.observe(C)
        with self.assertRaisesRegex(batch.BatchError, "omitted executable"):
            self.admit(self.request(C, self.none))
        self.assertIn(self.suite, self.state["debts"], "why: cancellation debt vanished; remedy: carry selected obligations")

    def test_terminal_executor_before_claim_is_settled_without_reexecution(self):
        self.bootstrap()
        self.observe(B)
        request = self.request(B, self.focused)
        self.admit(request)
        self.state = deepcopy(self.state)  # controller restarts after admission
        executor = self.state["active"]["executor_run"]
        result = {"request_id": request["id"], "run": executor,
                  "target": B, "policy": request["policy"],
                  "outcomes": {self.suite: "missing"},
                  "reference": "authenticated-terminal-run:10", "terminal": True}
        with self.assertRaisesRegex(batch.BatchError, "claimed run"):
            self.apply("result", result)
        # The adapter first verifies the old run is terminal. This bookkeeping
        # claim is never an instruction to launch work in the reconciler run.
        self.apply("claim", {"request_id": request["id"], "run": executor})
        self.apply("result", result)
        self.apply("advance", {"request_id": request["id"]})
        self.assertIsNone(self.state["active"],
                          "why: terminal unstarted executor retained ownership; remedy: settle its claim and result")
        self.assertEqual(self.state["processed"], B,
                         "why: persisted missing result lost progress; remedy: advance with debt")
        self.assertEqual(self.state["debts"][self.suite]["outcome"], "missing",
                         "why: unstarted tests counted as coverage; remedy: retain selected-suite debt")

    def test_repeated_infrastructure_failure_pauses_debt_without_infinite_retry(self):
        self.bootstrap()
        for target in (B, C):
            self.observe(target)
            request = self.request(target, self.focused)
            self.admit(request)
            self.finish(request, "infrastructure")
        self.assertTrue(self.state["debts"][self.suite]["paused"],
                        "why: repeated infrastructure debt not paused; remedy: bound automatic recovery")
        self.observe(E)
        request = self.request(E, self.none)
        self.admit(request)
        self.finish(request)
        self.assertIn(self.suite, self.state["debts"], "why: docs erased paused debt; remedy: preserve uncovered state")

    def test_explicit_resume_allows_one_no_change_recovery(self):
        self.bootstrap()
        self.observe(B)
        request = self.request(B, self.focused)
        self.admit(request)
        self.finish(request, "infrastructure")
        self.apply("resume", {"suites": [self.suite], "reason": "runner repaired by operator"})
        request = self.request(B, self.focused)
        self.admit(request)
        self.finish(request)
        self.assertNotIn(self.suite, self.state["debts"], "why: repair did not satisfy debt; remedy: record same-target result")
        with self.assertRaisesRegex(batch.BatchError, "no new main"):
            self.admit(self.request(B, self.focused))

    def test_later_pass_does_not_close_unresolved_failure(self):
        self.bootstrap()
        for target, outcome in ((B, "failed"), (C, "passed")):
            self.observe(target)
            request = self.request(target, self.focused)
            self.admit(request)
            self.finish(request, outcome)
        self.assertEqual(len(self.state["failures"]), 1, "why: green closed root cause; remedy: retain issue observation")

    def test_candidate_boundary_fairness_and_historical_cursor_isolation(self):
        self.bootstrap()
        self.observe(E)
        request = self.request(E, self.focused)
        self.admit(request)
        candidate = self.request(B, kind="candidate", name="candidate")
        self.apply("enqueue", candidate)
        self.finish(request, "infrastructure")
        self.observe("f" * 40)
        with self.assertRaisesRegex(batch.BatchError, "explicit request is waiting"):
            self.admit(self.request("f" * 40))
        before = deepcopy(self.state["debts"])
        self.admit(candidate, executor_run={"run_id": 999, "attempt": 1})
        self.assertEqual(self.state["active"]["executor_run"]["run_id"], 999,
                         "why: queued candidate bound to finished submitting run; remedy: bind admission executor")
        self.finish(candidate)
        self.assertEqual(self.state["processed"], E, "why: historical candidate moved cursor; remedy: isolate explicit observations")
        self.assertEqual(self.state["debts"], before, "why: historical candidate cleared newer debt; remedy: keep scopes separate")

    STRESS, ASAN = "core_release_stress", "core_asan"

    def settled_candidate(self, outcomes, name="candidate"):
        """A candidate for B whose durable result records ``outcomes`` (others passed)."""
        candidate = self.request(B, kind="candidate", name=name)
        self.apply("enqueue", candidate)
        self.admit(candidate, executor_run={"run_id": 999, "attempt": 1})
        executor = self.state["active"]["executor_run"]
        self.apply("claim", {"request_id": candidate["id"], "run": executor})
        self.apply("result", {"request_id": candidate["id"], "run": executor, "target": B,
                              "policy": candidate["policy"], "terminal": True,
                              "reference": "durable-result:" + name,
                              "outcomes": {suite: outcomes.get(suite, "passed")
                                           for suite in candidate["selection"]["suites"]}})
        self.apply("advance", {"request_id": candidate["id"]})
        return candidate

    def retry(self, original, environmental, *, name="retry-1", suites=None, target=B, control=A):
        selection = test_scope._selection(self.policy, sorted(environmental) if suites is None else suites,
                                          ["retry of " + original])
        return batch.make_request(self.policy, request_id=name, kind="retry", base_sha=None, target_sha=target,
                                  control_sha=control, selection=selection, origin_run={"run_id": 11, "attempt": 1},
                                  retry_of={"request": original, "environmental": environmental})

    def test_retry_request_pairs_kind_with_its_proof(self):
        self.bootstrap()
        environmental = {self.STRESS: {"outcome": "cancelled", "jobs": {}}}
        with self.assertRaisesRegex(batch.BatchError, "retry"):
            batch.make_request(self.policy, request_id="r", kind="retry", base_sha=None, target_sha=B, control_sha=A,
                               selection=test_scope._selection(self.policy, [self.STRESS], []),
                               origin_run={"run_id": 11, "attempt": 1})
        with self.assertRaisesRegex(batch.BatchError, "retry"):
            batch.make_request(self.policy, request_id="r", kind="candidate", base_sha=None, target_sha=B, control_sha=A,
                               selection=self.full, origin_run={"run_id": 11, "attempt": 1},
                               retry_of={"request": "candidate", "environmental": environmental})
        # A retry re-runs lanes; it is not a change, so no dependency closure.
        request = self.retry("candidate", {"core_ubuntu": {"outcome": "cancelled", "jobs": {}}})
        self.assertEqual(request["selection"]["suites"], ["core_ubuntu"])

    def test_retry_needs_a_durable_result_of_a_candidate_for_the_same_target(self):
        self.bootstrap()
        candidate = self.request(B, kind="candidate", name="candidate")
        self.apply("enqueue", candidate)
        proof = {self.STRESS: {"outcome": "cancelled", "jobs": {}}}
        with self.assertRaisesRegex(batch.BatchError, "no durable result"):
            self.apply("enqueue", self.retry("candidate", proof))
        with self.assertRaisesRegex(batch.BatchError, "names no candidate"):
            self.apply("enqueue", self.retry("unknown", proof))
        self.admit(candidate, executor_run={"run_id": 999, "attempt": 1})
        self.finish(candidate, "cancelled")
        with self.assertRaisesRegex(batch.BatchError, "same target"):
            self.apply("enqueue", self.retry("candidate", {s: {"outcome": "cancelled", "jobs": {}}
                                                         for s in candidate["selection"]["suites"]}, target=C))
        node = self.request(B, kind="node", name="node")
        self.apply("enqueue", node)
        with self.assertRaisesRegex(batch.BatchError, "names no candidate"):
            self.apply("enqueue", self.retry("node", proof, name="retry-node"))

    def test_retry_covers_exactly_the_suites_the_candidate_did_not_pass(self):
        self.bootstrap()
        self.settled_candidate({self.STRESS: "cancelled", self.ASAN: "failed"})
        stress = {self.STRESS: {"outcome": "cancelled", "jobs": {}}}
        asan = {self.ASAN: {"outcome": "failed", "jobs": {"core-asan": "timed_out"}}}
        with self.assertRaisesRegex(batch.BatchError, "exactly the suites"):
            self.apply("enqueue", self.retry("candidate", stress))
        passed = {"core_coverage": {"outcome": "cancelled", "jobs": {}}}
        with self.assertRaisesRegex(batch.BatchError, "exactly the suites|differs from the candidate result"):
            self.apply("enqueue", self.retry("candidate", {**stress, **asan, **passed}))
        self.apply("enqueue", self.retry("candidate", {**stress, **asan}))
        self.assertEqual(self.state["queue"], ["retry-1"])

    def test_retry_proof_must_match_the_result_and_name_environmental_jobs_only(self):
        self.bootstrap()
        self.settled_candidate({self.ASAN: "failed"})
        with self.assertRaisesRegex(batch.BatchError, "differs from the candidate result"):
            self.apply("enqueue", self.retry("candidate", {self.ASAN: {"outcome": "cancelled", "jobs": {}}}))
        with self.assertRaisesRegex(batch.BatchError, "environmental"):
            self.retry("candidate", {self.ASAN: {"outcome": "failed", "jobs": {}}})
        with self.assertRaisesRegex(batch.BatchError, "test failure never qualifies"):
            self.retry("candidate", {self.ASAN: {"outcome": "failed", "jobs": {"core-asan": "failure"}}})
        with self.assertRaisesRegex(batch.BatchError, "no job proof"):
            self.retry("candidate", {self.ASAN: {"outcome": "cancelled", "jobs": {"core-asan": "cancelled"}}})
        self.apply("enqueue", self.retry("candidate", {self.ASAN: {"outcome": "failed", "jobs": {"core-asan": "cancelled"}}}))
        self.assertEqual(self.state["queue"], ["retry-1"])

    def test_retry_is_once_per_candidate_moves_no_cursor_and_records_no_debt(self):
        self.bootstrap()
        self.observe(E)
        interval = self.request(E, self.focused)
        self.admit(interval)
        self.finish(interval, "infrastructure")   # a paused-or-not debt that a retry must not touch
        before = deepcopy(self.state["debts"])
        self.settled_candidate({self.STRESS: "cancelled"})
        retry = self.retry("candidate", {self.STRESS: {"outcome": "cancelled", "jobs": {}}})
        self.apply("enqueue", retry)
        self.admit(retry, executor_run={"run_id": 11, "attempt": 1})
        self.finish(retry)
        self.assertEqual(self.state["results"]["retry-1"]["outcomes"], {self.STRESS: "passed"})
        self.assertEqual(self.state["processed"], E, "why: retry moved the automatic cursor; remedy: isolate explicit work")
        self.assertEqual(self.state["debts"], before, "why: retry changed debt; remedy: isolate explicit work")
        with self.assertRaisesRegex(batch.BatchError, "at most once"):
            self.apply("enqueue", self.retry("candidate", {self.STRESS: {"outcome": "cancelled", "jobs": {}}}, name="retry-2"))

    def test_block_does_not_change_cursor(self):
        self.bootstrap()
        self.apply("block", {"why": "backend unavailable", "remedy": "restore checkpoint"})
        self.observe(B)
        with self.assertRaisesRegex(batch.BatchError, "explicitly blocked"):
            self.admit(self.request(B))
        self.assertEqual(self.state["processed"], A, "why: blocked storage advanced cursor; remedy: wait for persistence")


if __name__ == "__main__":
    unittest.main()
