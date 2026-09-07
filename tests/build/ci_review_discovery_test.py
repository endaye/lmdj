#!/usr/bin/env python3
"""Pure discovery journeys; API/source authentication belongs to the adapter."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/ci"))
import review_discovery as d


class DiscoveryTest(unittest.TestCase):
    def setUp(self):
        self.config = {"epoch": "review-discovery-test", "repository": "owner/repo", "workflow_id": 12,
                       "source_floor": {"control_sha": "a" * 40, "created_at": "2026-09-08T00:00:00Z"}}
        self.state = d.new_state(**self.config)
        self.events = []

    def record(self, run=7, attempt=1, created="2026-09-08T00:01:00Z"):
        return {"identity": {"run_id": run, "attempt": attempt}, "created_at": created}

    def event(self, kind, data, event_id=None):
        return {"id": event_id or f"event:{self.state['generation']}", "epoch": self.config["epoch"],
                "generation": self.state["generation"], "type": kind, "data": deepcopy(data)}

    def apply(self, kind, data):
        event = self.event(kind, data)
        self.state = d.reduce(self.state, event)
        self.events.append(event)
        return event

    def inventory(self, records=None, end="2026-09-08T01:00:00Z"):
        records = [self.record()] if records is None else records
        return {"start": self.state["inventory_frontier"], "end": end, "runs": records,
                "total_count": len(records), "inventory_digest": d.digest(records), "complete": True}

    def disposition(self, status="valid-review", run=7, attempt=1):
        ident = {"run_id": run, "attempt": attempt}
        proof = ({"identity": deepcopy(ident), "control_sha": "b" * 40, "receipt_digest": "c" * 64}
                 if status in d.TERMINAL else {"why": "artifact not available", "remedy": "reconcile exact receipt"})
        if status == "failure-queued":
            proof["outbox_key"] = "d" * 64
        return {"identity": ident, "status": status, "proof": proof}

    def reject(self, event):
        before = deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "why: .*; remedy: "):
            d.reduce(self.state, event)
        self.assertEqual(before, self.state)

    def test_complete_inventory_retains_every_supplied_page_member(self):
        # Concatenated data is a fixture, not proof that GitHub pages were read.
        records = [self.record(i) for i in range(1, 202)]
        self.apply("inventory", self.inventory(records))
        self.assertEqual(201, len(self.state["runs"]))
        self.assertEqual(201, len(d.summary(self.state)["unresolved"]))
        self.assertEqual("2026-09-08T01:00:00Z", self.state["inventory_frontier"])

    def test_partial_inventory_cannot_advance(self):
        data = self.inventory()
        data["complete"] = False
        self.reject(self.event("inventory", data))

    def test_missing_page_total_mismatch_cannot_advance(self):
        data = self.inventory()
        data["total_count"] = 101
        self.reject(self.event("inventory", data))

    def test_inventory_commitment_covers_complete_record(self):
        data = self.inventory()
        data["runs"][0]["created_at"] = "2026-09-08T00:02:00Z"
        self.reject(self.event("inventory", data))

    def test_window_gap_rejected(self):
        data = self.inventory()
        data["start"] = "2026-09-08T00:30:00Z"
        self.reject(self.event("inventory", data))

    def test_window_overlap_rejected(self):
        first = self.apply("inventory", self.inventory())
        self.reject(self.event("inventory", first["data"]))

    def test_empty_window_rejected(self):
        data = self.inventory()
        data["end"] = data["start"]
        self.reject(self.event("inventory", data))

    def test_empty_complete_interval_advances_without_invented_reviews(self):
        self.apply("inventory", self.inventory([]))
        self.assertEqual({}, self.state["runs"])
        self.assertEqual("2026-09-08T01:00:00Z", self.state["inventory_frontier"])

    def test_half_open_boundary_does_not_double_register(self):
        record = self.record(created="2026-09-08T01:00:00Z")
        self.reject(self.event("inventory", self.inventory([record])))
        self.apply("inventory", self.inventory([]))
        self.apply("inventory", self.inventory([record], "2026-09-08T02:00:00Z"))
        self.assertEqual({"7/1"}, set(self.state["runs"]))

    def test_duplicate_run_and_attempt_is_not_complete_inventory(self):
        self.reject(self.event("inventory", self.inventory([self.record(), self.record()])))

    def test_latest_attempt_cannot_replace_original_inventory(self):
        self.reject(self.event("inventory", self.inventory([self.record(attempt=2)])))

    def test_original_pending_survives_frontier_and_later_resolves(self):
        self.apply("inventory", self.inventory())
        self.apply("inventory", self.inventory([], "2026-09-09T00:00:00Z"))
        self.assertIn("7/1", d.summary(self.state)["unresolved"])
        self.apply("disposition", self.disposition())
        self.assertEqual({}, d.summary(self.state)["unresolved"])
        self.assertEqual("2026-09-09T00:00:00Z", self.state["inventory_frontier"])

    def test_later_attempt_is_independent_behind_frontier(self):
        self.apply("inventory", self.inventory())
        self.apply("disposition", self.disposition())
        self.apply("attempt", self.record(attempt=2))
        self.assertEqual("valid-review", self.state["runs"]["7/1"]["status"])
        self.assertEqual("pending", self.state["runs"]["7/2"]["status"])
        self.assertIn("source admissibility", self.state["runs"]["7/2"]["proof"]["why"])
        self.apply("disposition", self.disposition("unresolved", attempt=2))
        self.assertIn("7/2", d.summary(self.state)["unresolved"])

    def test_later_attempt_requires_original_run(self):
        self.reject(self.event("attempt", self.record(attempt=2)))

    def test_rerun_does_not_change_original_creation_time(self):
        self.apply("inventory", self.inventory())
        self.reject(self.event("attempt", self.record(attempt=2, created="2026-09-09T00:00:00Z")))

    def test_pending_then_missing_then_exact_receipt_resolution(self):
        self.apply("inventory", self.inventory())
        self.apply("disposition", self.disposition("unresolved"))
        self.assertIn("7/1", d.summary(self.state)["unresolved"])
        self.apply("disposition", self.disposition())
        self.assertEqual("valid-review", self.state["runs"]["7/1"]["status"])

    def test_failure_queue_is_not_business_delivery_success(self):
        self.apply("inventory", self.inventory())
        self.apply("disposition", self.disposition("failure-queued"))
        result = d.summary(self.state)
        self.assertEqual({"7/1": "d" * 64}, result["queued_failures"])
        self.assertTrue(result["inventoried_attempts_resolved"])
        self.assertIn("outbox delivery are separate", result["coverage"])
        self.assertNotIn("delivered", result)

    def test_failure_requires_exact_outbox_commitment(self):
        self.apply("inventory", self.inventory())
        data = self.disposition("failure-queued")
        data["proof"]["outbox_key"] = "looks delivered"
        self.reject(self.event("disposition", data))

    def test_retention_loss_survives_new_inventory_and_cannot_be_reset_pending(self):
        self.apply("inventory", self.inventory())
        self.apply("disposition", self.disposition("retention-lost"))
        self.apply("inventory", self.inventory([], "2026-11-01T00:00:00Z"))
        self.assertEqual(["7/1"], d.summary(self.state)["retention_lost"])
        self.reject(self.event("disposition", self.disposition("pending")))

    def test_retention_loss_can_only_resolve_exact_original_receipt(self):
        self.apply("inventory", self.inventory())
        self.apply("disposition", self.disposition("retention-lost"))
        bad = self.disposition()
        bad["proof"]["identity"]["attempt"] = 2
        self.reject(self.event("disposition", bad))
        self.apply("disposition", self.disposition())
        self.assertEqual([], d.summary(self.state)["retention_lost"])

    def test_uninventoried_receipt_rejected(self):
        self.reject(self.event("disposition", self.disposition()))

    def test_old_error_cannot_downgrade_terminal(self):
        self.apply("inventory", self.inventory())
        self.apply("disposition", self.disposition())
        self.reject(self.event("disposition", self.disposition("unresolved")))

    def test_conflicting_positive_receipt_rejected(self):
        self.apply("inventory", self.inventory())
        self.apply("disposition", self.disposition())
        changed = self.disposition()
        changed["proof"]["receipt_digest"] = "e" * 64
        self.reject(self.event("disposition", changed))

    def test_closed_mapper_resolves_without_creating_failure(self):
        self.apply("inventory", self.inventory())
        self.apply("disposition", self.disposition("closed-mapping"))
        self.assertEqual({}, d.summary(self.state)["queued_failures"])

    def test_lost_append_response_exact_event_redelivery_is_idempotent(self):
        first = self.apply("inventory", self.inventory())
        self.apply("disposition", self.disposition("failure-queued"))
        self.assertEqual(self.state, d.reduce(self.state, first))
        self.assertEqual(self.state, d.replay(self.config, [*self.events, first]))

    def test_reused_event_id_requires_complete_object_equality(self):
        original = self.apply("inventory", self.inventory())
        changed = deepcopy(original)
        changed["data"]["end"] = "2026-09-08T02:00:00Z"
        self.reject(changed)

    def test_duplicate_event_generation_boolean_is_not_original_integer(self):
        original = self.apply("inventory", self.inventory())
        changed = deepcopy(original)
        changed["generation"] = False
        self.reject(changed)

    def test_duplicate_event_count_float_is_not_original_integer(self):
        original = self.apply("inventory", self.inventory())
        changed = deepcopy(original)
        changed["data"]["total_count"] = 1.0
        self.reject(changed)

    def test_duplicate_event_nested_attempt_boolean_is_not_original_integer(self):
        original = self.apply("inventory", self.inventory())
        changed = deepcopy(original)
        changed["data"]["runs"][0]["identity"]["attempt"] = True
        self.reject(changed)

    def test_wrong_epoch_generation_and_unknown_event_rejected(self):
        for field, value in (("epoch", "other"), ("generation", True), ("generation", 9), ("type", "advance")):
            with self.subTest(field=field, value=value):
                event = self.event("inventory", self.inventory())
                event[field] = value
                self.reject(event)

    def test_unknown_fields_and_boolean_ids_rejected(self):
        for mutate in (lambda x: x.update(extra=1), lambda x: x["data"].update(extra=1),
                       lambda x: x["data"]["runs"][0]["identity"].update(run_id=True)):
            event = self.event("inventory", self.inventory())
            mutate(event)
            self.reject(event)

    def test_invalid_or_noncanonical_times_rejected(self):
        for value in ("2026-02-30T00:00:00Z", "2026-09-08T00:00:00+00:00", "yesterday"):
            data = self.inventory()
            data["end"] = value
            self.reject(self.event("inventory", data))

    def test_reducer_copies_and_replays_without_mutating_caller_objects(self):
        event = self.event("inventory", self.inventory())
        original = deepcopy(event)
        initial = deepcopy(self.state)
        result = d.reduce(self.state, event)
        self.assertEqual(initial, self.state)
        self.assertEqual(original, event)
        event["data"]["runs"].clear()
        self.assertEqual(1, len(result["runs"]))

    def gap(self, start="2026-09-08T00:00:00Z", end="2026-09-08T02:00:00Z", why="retention exceeded"):
        return {"start": start, "end": end, "why": why, "remedy": "recover independently retained complete inventory"}

    def test_unenumerable_retention_gap_is_durable_without_frontier_advance(self):
        self.apply("inventory-gap", self.gap())
        self.assertEqual(self.config["source_floor"]["created_at"], self.state["inventory_frontier"])
        self.assertEqual("retention exceeded", d.summary(self.state)["inventory_gaps"][0]["reasons"][0]["why"])

    def test_later_complete_inventory_does_not_cross_old_gap(self):
        self.apply("inventory-gap", self.gap())
        data = self.inventory([], "2026-09-08T03:00:00Z")
        data["start"] = "2026-09-08T02:00:00Z"
        self.apply("inventory", data)
        result = d.summary(self.state)
        self.assertEqual("2026-09-08T00:00:00Z", result["inventory_frontier"])
        self.assertEqual("2026-09-08T03:00:00Z", result["latest_inventory_end"])
        self.assertEqual(1, len(result["inventory_gaps"]))

    def test_partial_inventory_resolves_only_its_actual_gap_interval(self):
        self.apply("inventory-gap", self.gap())
        self.apply("inventory", self.inventory([], "2026-09-08T01:00:00Z"))
        gaps = self.state["gaps"]
        self.assertEqual(1, len(gaps))
        self.assertEqual("2026-09-08T01:00:00Z", gaps[0]["start"])
        self.assertEqual("2026-09-08T02:00:00Z", gaps[0]["end"])
        self.assertEqual("2026-09-08T00:00:00Z", gaps[0]["reasons"][0]["start"])
        self.apply("inventory", self.inventory([], "2026-09-08T02:00:00Z"))
        self.assertEqual([], self.state["gaps"])
        self.assertEqual("2026-09-08T02:00:00Z", self.state["inventory_frontier"])

    def test_middle_gap_resolution_retains_both_sides(self):
        self.apply("inventory-gap", self.gap(end="2026-09-08T03:00:00Z"))
        data = self.inventory([], "2026-09-08T02:00:00Z")
        data["start"] = "2026-09-08T01:00:00Z"
        self.apply("inventory", data)
        self.assertEqual([("2026-09-08T00:00:00Z", "2026-09-08T01:00:00Z"),
                          ("2026-09-08T02:00:00Z", "2026-09-08T03:00:00Z")],
                         [(g["start"], g["end"]) for g in self.state["gaps"]])

    def test_overlapping_gaps_normalize_and_preserve_both_reasons(self):
        event = self.apply("inventory-gap", self.gap())
        self.assertEqual(self.state, d.reduce(self.state, event))
        self.apply("inventory-gap", self.gap(start="2026-09-08T01:00:00Z", end="2026-09-08T03:00:00Z", why="API inventory lost"))
        self.assertEqual(3, len(self.state["gaps"]))
        self.assertEqual({"retention exceeded", "API inventory lost"},
                         {r["why"] for r in self.state["gaps"][1]["reasons"]})
        self.assertEqual(self.state, d.replay(self.config, self.events))

    def test_duplicate_gap_new_delivery_does_not_duplicate_reasons(self):
        self.apply("inventory-gap", self.gap())
        self.apply("inventory-gap", self.gap())
        self.assertEqual(1, len(self.state["gaps"]))
        self.assertEqual(1, len(self.state["gaps"][0]["reasons"]))

    def test_partial_untrusted_inventory_cannot_clear_any_gap(self):
        self.apply("inventory-gap", self.gap())
        data = self.inventory([])
        data["complete"] = False
        self.reject(self.event("inventory", data))
        self.assertEqual(1, len(self.state["gaps"]))

    def test_late_gap_cannot_downgrade_completed_inventory(self):
        self.apply("inventory", self.inventory([]))
        self.reject(self.event("inventory-gap", self.gap()))

    def test_repaired_gap_connects_already_complete_later_window(self):
        self.apply("inventory-gap", self.gap())
        later = self.inventory([], "2026-09-08T03:00:00Z")
        later["start"] = "2026-09-08T02:00:00Z"
        self.apply("inventory", later)
        self.apply("inventory", self.inventory([], "2026-09-08T02:00:00Z"))
        self.assertEqual("2026-09-08T03:00:00Z", self.state["inventory_frontier"])
        self.assertEqual([], self.state["gaps"])

    def test_inventory_gap_cannot_skip_an_unrecorded_prefix(self):
        self.reject(self.event("inventory-gap", self.gap(start="2026-09-08T01:00:00Z")))

    def test_nonfinite_commitment_rejected_with_remedy(self):
        with self.assertRaisesRegex(ValueError, "why: .*; remedy: "):
            d.digest({"value": float("nan")})


if __name__ == "__main__":
    unittest.main()
