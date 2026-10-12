#!/usr/bin/env python3
"""Real Journal fault journeys + real Git intervals; not platform acceptance.

Memory transport reproduces intent/append/anchor loss, not GitHub authorization,
visibility, concurrency ownership or workflow_run wakeups. Those remain O1.
"""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
import batch_controller as controller
import batch_github_journal as github
import incremental_batch as batch
from incremental_batch_journal import Journal, JournalBlocked
import self_test
import test_scope

A, B, C, D = (c * 40 for c in "abcd")
POLICY = test_scope.load_policy(ROOT)


class Memory:
    def __init__(self):
        self.checkpoint = {"head": None, "pending": None}
        self.comments = []
        self.fail = None
        self.lock = True

    def read(self):
        return deepcopy(self.checkpoint)

    def replace(self, previous, replacement):
        if self.checkpoint != previous:
            raise RuntimeError("why: anchor raced; remedy: reconcile")
        self.checkpoint = deepcopy(replacement)

    def page(self, issue, cursor, authenticated_prefix=0):
        return {"comments": deepcopy(self.comments), "next": None,
                "cursor": str(len(self.comments)) if self.comments else None}

    def page_after(self, issue, cursor):
        start = int(cursor)
        rows = deepcopy(self.comments[start:])
        return {"comments": rows, "next": None,
                "cursor": str(len(self.comments)) if rows else None,
                "total": len(self.comments)}

    def last(self, issue):
        return deepcopy(self.comments[-1]) if self.comments else None

    def append(self, issue, envelope):
        kind = envelope["event"]["type"]
        failure = self.fail
        if failure == (kind, "before"):
            self.fail = None
            raise RuntimeError("why: lost request; remedy: reconcile exact intent")
        self.comments.append({"id": len(self.comments) + 1, "edited": False,
                              "envelope": deepcopy(envelope), "provenance": {}})
        if failure == (kind, "after"):
            self.fail = None
            raise RuntimeError("why: lost response; remedy: reconcile exact append")

    def journal(self):
        return Journal(782, self, self, lambda *args: True, lambda: self.lock)


class Inputs:
    """Deterministic main/API stand-in; actual Git cases below use GitInputs."""
    def __init__(self):
        self.control_sha = A
        self.main = B
        self.policies = {A: POLICY, B: POLICY, C: POLICY, D: POLICY}
        self.selection = test_scope._selection(POLICY, ["creator"], ["host changes"])
        self.intervals = []
        self.advance_on_refresh = None

    def refresh(self):
        if self.advance_on_refresh:
            self.main = self.advance_on_refresh.pop(0)
        return self.main

    def ancestor(self, base, target):
        return base <= target

    def verify_target(self, target):
        batch.require(target in self.policies, "missing complete target history")

    def policy_at(self, sha, historical=False):
        batch.require(sha in self.policies, "missing historical policy")
        return self.policies[sha]

    def interval_selection(self, base, target, policy):
        self.intervals.append((base, target))
        return deepcopy(self.selection)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.memory, self.inputs = Memory(), Inputs()
        self.statuses = {1: "running", 2: "running", 3: "running", 4: "running", 5: "running"}
        self.receipts = {}
        self.old_terminal = True

    def make(self, run=1, epoch="epoch"):
        return controller.Controller(self.memory.journal(), self.inputs, {"run_id": run, "attempt": 1},
            run_state=lambda r: self.statuses.get(r["run_id"], "unknown"),
            result_for=lambda request, r: self.receipts.get(request["id"], {"status": "pending"}),
            old_runs_terminal=lambda: self.old_terminal, lock_held=lambda: self.memory.lock, epoch=epoch)

    def settle(self, action, run, outcome="passed"):
        self.statuses[run] = "terminal"
        request = action["request"]
        self.receipts[request["id"]] = {"status": "ready", "outcomes": {
            suite: outcome for suite in request["selection"]["suites"]}, "reference": "durable:" + request["id"]}

    def baseline(self):
        start = self.make().reconcile()
        self.settle(start, 1)
        done = self.make(2).reconcile()
        self.assertEqual(done["state"]["processed"], B,
                         "why: bootstrap did not persist progress; remedy: settle result then advance")
        return done

    def test_auto_freezes_daily_work_and_bootstrap_stays_complete(self):
        self.inputs.interval_verification = lambda base, target, policy, selected: {s: "quick" for s in selected}
        first = self.make().reconcile()
        self.assertNotIn("verification", first["request"])
        self.settle(first, 1)
        self.make(2).reconcile()
        self.inputs.main = C
        action = self.make(2).reconcile()
        self.assertEqual(action["request"]["verification"], {"creator": "quick"})

    def test_unpaused_debt_overrides_daily_quick_with_complete_work(self):
        self.baseline()
        self.inputs.main = C
        first = self.make(2).reconcile()
        self.settle(first, 2, "infrastructure")
        self.make(3).reconcile()
        self.inputs.main = D
        self.inputs.interval_verification = lambda base, target, policy, selected: {s: "quick" for s in selected}
        action = self.make(3).reconcile()
        self.assertEqual(action["request"]["verification"], {"creator": "full"})

    def test_bootstrap_claim_then_completion_then_idle(self):
        start = self.make().reconcile()
        self.assertEqual(start["action"], "execute", "why: bootstrap did not claim; remedy: admit full after old-run audit")
        self.assertEqual(start["request"]["selection"]["suites"], sorted(POLICY.suite_ids))
        self.assertIsNone(start["state"]["processed"], "why: admission pretended tested; remedy: wait for result")
        self.settle(start, 1)
        done = self.make(2).reconcile()
        self.assertEqual(done["action"], "idle")
        self.assertEqual(done["state"]["processed"], B)
        self.assertTrue(done["state"]["history_unknown"], "why: bootstrap erased historical uncertainty; remedy: retain it")
        events = self.memory.journal().load()
        self.assertLess([e["type"] for e in events].index("result"), [e["type"] for e in events].index("advance"))

    def test_idle_day_creates_no_log_or_test(self):
        self.baseline()
        count = len(self.memory.comments)
        for _ in range(3):
            self.assertEqual(self.make(3).reconcile()["action"], "idle")
        self.assertEqual(len(self.memory.comments), count, "why: idle tick added work; remedy: write only changed observations")

    def test_missing_epoch_does_not_guess_empty_progress(self):
        with self.assertRaisesRegex(batch.BatchError, "epoch"):
            self.make(epoch=None).reconcile()
        self.assertEqual(self.memory.comments, [])

    def test_existing_first_event_supplies_epoch(self):
        first = self.make().reconcile()
        self.assertEqual(self.make(2, epoch=None).reconcile()["state"]["epoch"], first["state"]["epoch"])

    def test_old_runs_unknown_blocks_bootstrap(self):
        self.old_terminal = None
        result = self.make().reconcile()
        self.assertEqual(result["action"], "waiting")
        self.assertIsNone(result["state"]["active"])
        self.assertIsNone(result["state"]["processed"])

    def test_unknown_executor_keeps_claim_and_cursor(self):
        start = self.make().reconcile()
        self.statuses[1] = "unknown"
        self.inputs.main = D
        next_action = self.make(2).reconcile()
        self.assertEqual(next_action["action"], "waiting")
        self.assertEqual(next_action["state"]["active"], start["state"]["active"])
        self.assertEqual(next_action["state"]["pending"], D)

    def test_duplicate_current_run_never_reissues_execute(self):
        self.make().reconcile()
        self.assertEqual(self.make().reconcile()["action"], "waiting")

    def test_settlement_only_does_not_admit_initial_bootstrap(self):
        answer = self.make().reconcile(allow_execution=False)
        self.assertEqual(answer["action"], "idle")
        self.assertIsNone(answer["state"]["active"])
        self.assertIsNone(answer["state"]["processed"])

    def test_settlement_only_does_not_claim_same_run_lost_admit(self):
        self.memory.fail = ("admit", "after")
        with self.assertRaises(JournalBlocked):
            self.make().reconcile()
        answer = self.make().reconcile(allow_execution=False)
        self.assertEqual(answer["action"], "waiting")
        self.assertIsNone(answer["state"]["active"]["claim"])

    def test_settlement_only_persists_terminal_result_without_starting_next(self):
        start = self.make().reconcile()
        self.settle(start, 1)
        self.inputs.main = C
        answer = self.make(2).reconcile(allow_execution=False)
        self.assertEqual(answer["action"], "idle")
        self.assertEqual(answer["state"]["processed"], B)
        self.assertEqual(answer["state"]["pending"], C)
        self.assertIsNone(answer["state"]["active"])

    def test_execution_switch_requires_boolean(self):
        with self.assertRaisesRegex(batch.BatchError, "boolean"):
            self.make().reconcile(allow_execution="false")

    def test_partial_run_attempt_rejected(self):
        with self.assertRaisesRegex(batch.BatchError, "reruns"):
            controller.Controller(None, None, {"run_id": 1, "attempt": 2}, run_state=None,
                                  result_for=None, old_runs_terminal=None, lock_held=None)

    def test_pending_result_does_not_become_missing(self):
        start = self.make().reconcile()
        self.statuses[1] = "terminal"
        result = self.make(2).reconcile()
        self.assertEqual(result["action"], "waiting")
        self.assertNotIn(start["request"]["id"], result["state"]["results"])

    def test_confirmed_missing_advances_with_debt(self):
        start = self.make().reconcile()
        self.statuses[1] = "terminal"
        self.receipts[start["request"]["id"]] = {"status": "missing"}
        done = self.make(2).reconcile()
        self.assertEqual(done["state"]["processed"], B)
        self.assertEqual(set(done["state"]["debts"]), set(POLICY.suite_ids))

    def test_invalid_ready_outcomes_never_advance(self):
        start = self.make().reconcile()
        self.statuses[1] = "terminal"
        self.receipts[start["request"]["id"]] = {"status": "ready", "outcomes": {}, "reference": "x"}
        with self.assertRaisesRegex(batch.BatchError, "every selected"):
            self.make(2).reconcile()
        self.assertNotIn("advance", [e["type"] for e in self.memory.journal().load()])

    def test_coalesces_b_running_c_d_to_one_latest_interval(self):
        self.baseline()
        self.inputs.main = C
        running = self.make(2).reconcile()
        self.inputs.main = D
        waiting = self.make(3).reconcile()
        self.assertEqual(waiting["state"]["active"]["request_id"], running["request"]["id"])
        self.settle(running, 2)
        next_action = self.make(3).reconcile()
        self.assertEqual(next_action["action"], "execute")
        self.assertEqual((next_action["request"]["base"], next_action["request"]["target"]), (C, D))
        self.assertEqual(self.inputs.intervals, [(B, C), (C, D)])

    def test_completion_boundary_rereads_latest_main(self):
        first = self.make().reconcile()
        self.settle(first, 1)
        self.inputs.advance_on_refresh = [B, D]
        next_action = self.make(2).reconcile()
        self.assertEqual(next_action["request"]["target"], D, "why: completion lost main tail; remedy: reread before admission")

    def test_none_waits_for_real_terminal_without_heavy_action(self):
        self.baseline()
        self.inputs.main = C
        self.inputs.selection = test_scope._selection(POLICY, [], ["only explanatory docs"])
        none = self.make(2).reconcile()
        self.assertEqual(none["action"], "idle")
        self.assertEqual(none["state"]["processed"], B)
        self.assertEqual(self.make(3).reconcile()["action"], "waiting")
        self.statuses[2] = "terminal"
        done = self.make(3).reconcile()
        self.assertEqual(done["state"]["processed"], C)
        self.assertEqual(done["state"]["results"][none["request"]["id"]]["outcomes"], {})

    def test_lost_admit_response_reconciles_claim_in_same_live_run(self):
        self.memory.fail = ("admit", "after")
        with self.assertRaises(JournalBlocked):
            self.make().reconcile()
        recovered = self.make().reconcile()
        self.assertEqual(recovered["action"], "execute")
        self.assertEqual(sum(e["type"] == "admit" for e in self.memory.journal().load()), 1)

    def test_lost_claim_response_never_reexecutes(self):
        self.memory.fail = ("claim", "after")
        with self.assertRaises(JournalBlocked):
            self.make().reconcile()
        self.assertEqual(self.make().reconcile()["action"], "waiting")

    def test_terminated_before_claim_records_missing_and_releases(self):
        self.memory.fail = ("admit", "after")
        with self.assertRaises(JournalBlocked):
            self.make().reconcile()
        self.statuses[1] = "terminal"
        done = self.make(2).reconcile()
        self.assertEqual(done["action"], "idle")
        self.assertEqual(done["state"]["processed"], B)
        self.assertTrue(done["state"]["debts"])

    def test_lost_result_response_recovers_then_advances_without_rerun(self):
        first = self.make().reconcile()
        self.settle(first, 1)
        self.memory.fail = ("result", "after")
        with self.assertRaises(JournalBlocked):
            self.make(2).reconcile()
        done = self.make(2).reconcile()
        self.assertEqual(done["action"], "idle")
        self.assertEqual(done["state"]["processed"], B)
        self.assertEqual(sum(e["type"] == "result" for e in self.memory.journal().load()), 1)

    def test_uncertain_absent_append_blocks_without_second_post(self):
        self.memory.fail = ("admit", "before")
        with self.assertRaises(JournalBlocked):
            self.make().reconcile()
        count = len(self.memory.comments)
        with self.assertRaises(JournalBlocked):
            self.make(2).reconcile()
        self.assertEqual(len(self.memory.comments), count)

    def test_historical_policy_replay_uses_recorded_control(self):
        first = self.make().reconcile()
        changed = deepcopy(POLICY.config)
        changed["none_prefixes"].append("docs/more-notes/")
        self.inputs.policies[C] = test_scope.parse_policy(POLICY.routing,
            json.loads((ROOT / "scripts/ci/self_test_policy.json").read_text()), changed)
        self.inputs.control_sha, self.inputs.main = C, C
        self.assertNotEqual(self.inputs.policies[C].digest, first["request"]["policy"])
        result = self.make(2).reconcile()
        self.assertEqual(result["state"]["requests"][first["request"]["id"]]["policy"], POLICY.digest)

    def test_missing_historical_policy_blocks_replay(self):
        self.make().reconcile()
        self.inputs.control_sha = C
        del self.inputs.policies[A]
        with self.assertRaisesRegex(batch.BatchError, "historical policy"):
            self.make(2).reconcile()

    def test_explicit_candidate_is_fair_and_keeps_auto_cursor(self):
        self.baseline()
        candidate = batch.make_request(POLICY, request_id="candidate-1", kind="candidate", base_sha=None,
            target_sha=A, control_sha=A, selection=test_scope._selection(POLICY, POLICY.suite_ids, []),
            origin_run={"run_id": 2, "attempt": 1})
        self.inputs.main = D
        action = self.make(2).reconcile(explicit=candidate)
        self.assertEqual(action["request"]["target"], A)
        self.settle(action, 2)
        automatic = self.make(3).reconcile()
        self.assertEqual(automatic["state"]["processed"], B)
        self.assertEqual((automatic["request"]["base"], automatic["request"]["target"]), (B, D))

    def test_explicit_redelivery_does_not_rerun_completed_candidate(self):
        self.baseline()
        request = batch.make_request(POLICY, request_id="candidate-1", kind="candidate", base_sha=None,
            target_sha=A, control_sha=A, selection=test_scope._selection(POLICY, POLICY.suite_ids, []),
            origin_run={"run_id": 2, "attempt": 1})
        action = self.make(2).reconcile(explicit=request)
        self.settle(action, 2)
        self.make(3).reconcile()
        self.assertEqual(self.make(3).reconcile(explicit=request)["action"], "idle")

    def test_no_lock_cannot_read_or_admit(self):
        self.memory.lock = False
        with self.assertRaisesRegex(batch.BatchError, "lock"):
            self.make().reconcile()
        self.assertEqual(self.memory.comments, [])

    def test_resume_debt_is_bounded_and_redelivery_does_not_reset_budget(self):
        first = self.make().reconcile()
        self.settle(first, 1, "infrastructure")
        self.make(2).reconcile()
        self.inputs.main = C
        second = self.make(2).reconcile()
        self.settle(second, 2, "infrastructure")
        paused = self.make(3).reconcile()
        self.assertTrue(all(d["paused"] for d in paused["state"]["debts"].values()),
                        "why: repeat unavailable work did not pause; remedy: retain bounded debt")
        self.assertEqual(self.make(3).reconcile()["action"], "idle")
        command = {"id": "operator-resume-1", "suites": ["creator"], "reason": "runner restored"}
        retry = self.make(3).reconcile(resume=command)
        self.assertEqual(retry["request"]["selection"]["suites"], ["creator"],
                         "why: explicit debt resume tested unrelated suites; remedy: select resumed closure only")
        self.settle(retry, 3, "infrastructure")
        after = self.make(4).reconcile()
        self.assertEqual(after["state"]["debts"]["creator"]["attempts"], 1)
        replay = self.make(4).reconcile(resume=command)
        self.assertEqual(replay["action"], "idle", "why: redelivered resume restarted tests; remedy: retain command identity")
        self.assertEqual(replay["state"]["debts"]["creator"]["attempts"], 1)

    def test_docs_none_cannot_clear_previous_product_failure(self):
        first = self.make().reconcile()
        self.settle(first, 1, "failed")
        failed = self.make(2).reconcile()
        self.inputs.main = C
        self.inputs.selection = test_scope._selection(POLICY, [], ["explanatory docs"])
        none = self.make(2).reconcile()
        self.assertEqual(none["action"], "idle")
        self.statuses[2] = "terminal"
        done = self.make(3).reconcile()
        self.assertEqual(done["state"]["failures"], failed["state"]["failures"],
                         "why: none erased product failure history; remedy: preserve unresolved observations")

    def test_report_retry_reads_durable_result_and_does_not_reexecute(self):
        first = self.make().reconcile()
        self.settle(first, 1, "failed")
        done = self.make(2).reconcile()
        reference = done["state"]["results"][first["request"]["id"]]["reference"]
        # Reporter failure is outside scheduler storage. Subsequent reads retain
        # its exact result reference and never require a fresh product run.
        again = self.make(3).reconcile()
        self.assertEqual(again["action"], "idle")
        self.assertEqual(again["state"]["results"][first["request"]["id"]]["reference"], reference)

    def test_result_storage_failure_does_not_advance_cursor(self):
        first = self.make().reconcile()
        self.settle(first, 1)
        self.memory.fail = ("result", "before")
        with self.assertRaises(JournalBlocked):
            self.make(2).reconcile()
        self.assertNotIn("advance", [c["envelope"]["event"]["type"] for c in self.memory.comments])
        with self.assertRaises(JournalBlocked):
            self.make(3).reconcile()

    def test_lost_advance_response_replays_without_second_result(self):
        first = self.make().reconcile()
        self.settle(first, 1)
        self.memory.fail = ("advance", "after")
        with self.assertRaises(JournalBlocked):
            self.make(2).reconcile()
        done = self.make(2).reconcile()
        self.assertEqual(done["state"]["processed"], B)
        self.assertEqual(sum(e["type"] == "advance" for e in self.memory.journal().load()), 1)

    def test_older_main_observation_cannot_reverse_pending(self):
        self.make().reconcile()
        self.inputs.main = A
        with self.assertRaisesRegex(batch.BatchError, "ancestry"):
            self.make(2).reconcile()
        self.assertEqual(self.memory.journal().load()[0]["data"]["target"], B)

    def test_finished_invoker_cannot_own_new_admission(self):
        self.statuses[1] = "terminal"
        result = self.make().reconcile()
        self.assertEqual(result["action"], "waiting")
        self.assertIsNone(result["state"]["active"])

    def test_ready_receipt_unknown_fields_rejected(self):
        first = self.make().reconcile()
        self.settle(first, 1)
        self.receipts[first["request"]["id"]]["unexpected"] = True
        with self.assertRaisesRegex(batch.BatchError, "schema"):
            self.make(2).reconcile()

    def test_deleted_tail_cannot_bootstrap_or_reexecute(self):
        self.make().reconcile()
        self.memory.comments.pop()
        with self.assertRaisesRegex(JournalBlocked, "suffix"):
            self.make(2).reconcile()


class RealGitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        for name in ("scope_policy.json", "self_test_policy.json", "test_scope_policy.json"):
            target = self.root / "scripts/ci" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / "scripts/ci" / name).read_bytes())
        self.base = self.commit()
        self.tip = self.base
        self.inputs = controller.GitInputs(self.root, self.base, lambda: self.tip,
                                          lambda interval: {"complete": True, "labels": []})

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True).stdout.decode().strip()

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        return self.git("rev-parse", "HEAD")

    def daily_change(self, labels=()):
        target = self.root / "apps/creator-web/src/components/overview_display.tsx"
        target.parent.mkdir(parents=True)
        target.write_text("// presentation fixture")
        self.tip = self.commit()
        self.inputs.advice = lambda interval: {"complete": True, "labels": list(labels)}
        self.inputs.refresh()
        selected = self.inputs.interval_selection(self.base, self.tip, POLICY)
        return self.inputs.interval_verification(self.base, self.tip, POLICY, selected["suites"])

    def test_real_interval_selects_durable_smoke(self):
        self.assertEqual(self.daily_change()["creator"], "quick")

    def test_authenticated_review_can_restore_complete_work(self):
        self.assertEqual(self.daily_change(["test:creator"])["creator"], "full")

    def test_missing_historical_policy_never_enables_quick(self):
        self.inputs.policy_at = lambda sha, **kwargs: None
        result = self.daily_change()
        self.assertEqual(result, {suite: "full" for suite in POLICY.suite_ids})

    def test_revert_retains_actual_interval_paths(self):
        contract = self.root / "contracts/new.json"
        contract.parent.mkdir()
        contract.write_text("{}")
        self.commit()
        contract.unlink()
        self.tip = self.commit()
        self.inputs.refresh()
        selected = self.inputs.interval_selection(self.base, self.tip, POLICY)
        self.assertEqual(selected["kind"], "full", "why: endpoint net diff hid contract revert; remedy: use each first parent delta")

    def test_complete_explanatory_docs_select_none(self):
        note = self.root / "docs/notes/n.md"
        note.parent.mkdir(parents=True)
        note.write_text("note")
        self.tip = self.commit()
        self.inputs.refresh()
        self.assertEqual(self.inputs.interval_selection(self.base, self.tip, POLICY)["kind"], "none")

    def test_missing_mapper_preserves_complete_git_floor(self):
        note = self.root / "docs/notes/n.md"
        note.parent.mkdir(parents=True)
        note.write_text("explanatory note")
        self.tip = self.commit()
        self.inputs.advice = None
        self.inputs.refresh()
        selection = self.inputs.interval_selection(self.base, self.tip, POLICY)
        self.assertEqual(selection["kind"], "none",
            "why: missing advice was confused with missing Git inventory; remedy: preserve complete deterministic scope per spec section 3.3")
        self.assertTrue(any("review" in reason and "remedy:" in reason for reason in selection["reasons"]))

    def test_incomplete_advice_preserves_host_floor_and_valid_additions(self):
        path = "apps/creator-web/src/fixture.ts"
        target = self.root / path
        target.parent.mkdir(parents=True)
        target.write_text("// fixture")
        self.tip = self.commit()
        self.inputs.advice = lambda interval: {"complete": False, "labels": ["test:web_runtime_host"]}
        self.inputs.refresh()
        selected = self.inputs.interval_selection(self.base, self.tip, POLICY)
        expected = test_scope.select(POLICY, [path], ["test:web_runtime_host"])
        self.assertEqual(selected["suites"], expected["suites"])
        self.assertEqual(selected["kind"], "focused")

    def test_missing_advice_never_reduces_contract_or_unknown_floor(self):
        self.inputs.advice = None
        for path in ("contracts/new.json", "unknown-future-area/file.txt"):
            with self.subTest(path=path):
                target = self.root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("fixture")
                self.tip = self.commit()
                self.inputs.refresh()
                self.assertEqual(self.inputs.interval_selection(self.base, self.tip, POLICY)["suites"], sorted(POLICY.suite_ids))

    def test_incomplete_advice_full_still_dominates_docs(self):
        self.inputs.advice = lambda interval: {"complete": False, "labels": ["test:full"]}
        self.inputs.refresh()
        self.assertEqual(self.inputs.interval_selection(self.base, self.base, POLICY)["kind"], "full")

    def test_missing_policy_with_incomplete_advice_still_requires_full(self):
        self.inputs.advice = None
        self.inputs.refresh()
        self.inputs.policy_at = lambda sha, historical=False: (_ for _ in ()).throw(batch.BatchError("fixture missing policy"))
        self.assertEqual(self.inputs.interval_selection(self.base, self.base, POLICY)["kind"], "full")

    def test_long_backlog_explanation_is_bounded_and_the_admit_record_fits_the_journal(self):
        """Defect: one reason per changed path over a 261-commit backlog produced a 260 KB admit
        record, above the 60,000-byte journal object limit, so every tick refused its own admit
        locally and the scheduler never admitted a batch."""
        sources = self.root / "packages/application-facade/src"
        sources.mkdir(parents=True)
        for index in range(600):
            (sources / f"fixture_{index:04d}.cpp").write_text("// fixture")
        self.tip = self.commit()
        self.inputs.advice = None
        self.inputs.refresh()
        selection = self.inputs.interval_selection(self.base, self.tip, POLICY)
        self.assertGreater(len(selection["reasons"]), 500, "why: the fixture stopped producing a long explanation; remedy: restore the many-path interval")
        run = {"run_id": 17, "attempt": 1}
        request = batch.make_request(POLICY, request_id="batch:epoch:1", kind="auto", base_sha=self.base,
                                     target_sha=self.tip, control_sha=self.tip, selection=selection, origin_run=run)
        batch._request(POLICY, request)
        bounded = request["selection"]
        self.assertEqual(bounded["suites"], sorted(POLICY.suite_ids),
                         "why: bounding the explanation changed the decision; remedy: bound reasons only, never suites")
        self.assertLessEqual(len(json.dumps(bounded["reasons"], separators=(",", ":")).encode()), test_scope.REASON_BUDGET)
        self.assertEqual(len([r for r in bounded["reasons"] if r.startswith(test_scope.OMISSION_MARKER)]), 1)
        selection = bounded
        event = {"id": "epoch:1", "epoch": "epoch", "generation": 1, "type": "admit",
                 "data": {"request": request, "executor_run": run, "history_complete": True,
                          "ancestor": True, "old_runs_terminal": True}}
        envelope = {"previous": "f" * 64, "event": event}
        envelope["digest"] = batch.digest(envelope)
        writer = {"repository": "endaye/lmdj", "issue_number": 807, "run_id": 17, "run_attempt": 1,
                  "control_sha": self.tip, "workflow_path": ".github/workflows/self-test-report.yml",
                  "workflow_id": 352307416, "job_name": "Incremental batch controller"}
        checkpoint = json.dumps({"schema": github.SCHEMA, "kind": "checkpoint", "writer": writer,
                                 "payload": {"head": "f" * 64, "pending": envelope}},
                                sort_keys=True, separators=(",", ":"), allow_nan=False)
        self.assertLessEqual(len(checkpoint.encode()), github.LIMIT,
                             "why: the pending admit checkpoint exceeds the journal object limit; remedy: bound the explanation")
        github.decode(checkpoint)

    def test_tag_object_is_not_main_commit(self):
        self.git("tag", "-am", "tag", "candidate")
        self.tip = self.git("rev-parse", "candidate")
        with self.assertRaisesRegex(batch.BatchError, "not a commit"):
            self.inputs.refresh()

    def test_tag_object_cannot_be_explicit_target(self):
        self.git("tag", "-am", "tag", "candidate")
        tag = self.git("rev-parse", "candidate")
        self.inputs.refresh()
        with self.assertRaisesRegex(batch.BatchError, "not a commit"):
            self.inputs.verify_target(tag)

    def test_missing_policy_does_not_execute_historical_code(self):
        (self.root / "scripts/ci/test_scope_policy.json").unlink()
        self.tip = self.commit()
        self.inputs.refresh()
        with self.assertRaisesRegex(batch.BatchError, "Git input"):
            self.inputs.policy_at(self.tip)

    @staticmethod
    def retired_lane_documents():
        """Current policy documents plus one retired lane, as recorded pre-retirement."""
        files = ("scope_policy.json", "self_test_policy.json", "test_scope_policy.json")
        docs = [json.loads((ROOT / "scripts/ci" / name).read_text()) for name in files]
        routing, inventory = docs[0], docs[1]
        routing["lanes"].append("chameleon_lab")
        routing["lane_jobs"]["chameleon_lab"] = ["chameleon-lab"]
        routing["self_hosted_jobs"].append("chameleon-lab")
        routing["rules"].append({"match": {"kind": "prefix", "value": "demos/chameleon-lab/"},
                                 "lanes": ["chameleon_lab"]})
        inventory["suites"].append({"id": "chameleon_lab",
                                    "origin": {"kind": "scope_lane", "lane": "chameleon_lab"},
                                    "jobs": ["chameleon-lab"], "required": True})
        return docs

    def write_policies(self, docs):
        names = ("scope_policy.json", "self_test_policy.json", "test_scope_policy.json")
        for name, document in zip(names, docs):
            (self.root / "scripts/ci" / name).write_text(json.dumps(document, indent=2) + "\n",
                                                         encoding="utf-8")

    def test_replay_tolerates_a_lane_retired_after_the_journal_recording(self):
        """Defect #2022: after the chameleon_lab lane retirement, every tick failed
        closed in _replay (ScopeError: lanes do not match the closed v1 allowlist)
        because pre-retirement controls carry the old inventory; main batch
        execution and report delivery stopped. Replay accepts the historical
        superset; the frozen request's bound digest is reproduced exactly."""
        historical_docs = self.retired_lane_documents()
        current_docs = [json.loads((ROOT / "scripts/ci" / name).read_text())
                        for name in ("scope_policy.json", "self_test_policy.json", "test_scope_policy.json")]
        self.write_policies(historical_docs)
        old = self.commit()
        self.write_policies(current_docs)
        self.tip = self.commit()
        # The policy object the pre-retirement era parsed and froze into its
        # requests: identical content, identical digest, no replay-era flag.
        historical = test_scope.ScopePolicy(
            historical_docs[0], self_test.parse_policy(historical_docs[1]), historical_docs[2],
            self_test.digest_of({"routing": historical_docs[0], "inventory": historical_docs[1],
                                 "scope": historical_docs[2]}))
        run = {"run_id": 7, "attempt": 1}
        selection = test_scope._selection(historical, historical.suite_ids, ["bootstrap requires full"])
        request = batch.make_request(historical, request_id="batch:epoch:1", kind="bootstrap",
                                     base_sha=None, target_sha=old, control_sha=old,
                                     selection=selection, origin_run=run)
        memory = Memory()
        previous = None
        for event in ({"id": "epoch:0", "epoch": "epoch", "generation": 0, "type": "observe",
                       "data": {"target": old, "descends_pending": True}},
                      {"id": "epoch:1", "epoch": "epoch", "generation": 1, "type": "admit",
                       "data": {"request": request, "executor_run": run, "history_complete": True,
                                "ancestor": True, "old_runs_terminal": True}}):
            envelope = {"previous": previous, "event": event}
            envelope["digest"] = batch.digest(envelope)
            memory.comments.append({"id": len(memory.comments) + 1, "edited": False,
                                    "envelope": envelope, "provenance": {}})
            previous = envelope["digest"]
        memory.checkpoint = {"head": previous, "pending": None}
        inputs = controller.GitInputs(self.root, self.tip, lambda: self.tip)
        replay = controller.Controller(memory.journal(), inputs, {"run_id": 9, "attempt": 1},
            run_state=lambda run: "running",
            result_for=lambda request, run: {"status": "pending"},
            old_runs_terminal=lambda: True, lock_held=lambda: memory.lock, epoch="epoch")
        answer = replay.reconcile(allow_execution=False)
        self.assertEqual(answer["action"], "waiting")
        frozen = answer["state"]["requests"]["batch:epoch:1"]
        self.assertEqual(frozen["control"], old)
        self.assertEqual(frozen["policy"], historical.digest)
        self.assertEqual(answer["state"]["pending"], self.tip)


if __name__ == "__main__":
    unittest.main()
