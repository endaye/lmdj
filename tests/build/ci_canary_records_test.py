"""Operational data consistency only; no storage/signing authority."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.canary import records as r


class RecordsTests(unittest.TestCase):
    def test_explicit_bootstrap_is_distinct_from_unavailable_storage(self):
        progress = r.initial_progress("endaye/lmdj")
        self.assertIsNone(progress["version_accounted"])
        self.assertEqual(progress["deployments"], dict.fromkeys(r.SITES))

        class Unavailable:
            def read(self):
                raise OSError("private diagnostic")

        with self.assertRaisesRegex(r.CanaryError, "why:.*unavailable; remedy:"):
            r.load_progress(Unavailable(), repository="endaye/lmdj")

    def test_round_trip_and_defensive_copy(self):
        original = r.initial_progress("endaye/lmdj")
        decoded = r.parse_progress(json.dumps(original), repository="endaye/lmdj")
        decoded["deployments"]["creator"] = "changed"
        self.assertIsNone(original["deployments"]["creator"])

    def test_duplicate_keys_corrupt_digest_and_unknown_fields_reject(self):
        valid = r.initial_progress("endaye/lmdj")
        cases = [json.dumps(valid).replace('"channel": "canary"',
                                          '"channel": "canary", "channel": "canary"')]
        for field, value in (("digest", "0" * 64), ("unknown", 1),
                             ("repository", "other/repo"), ("channel", "stable")):
            changed = deepcopy(valid)
            changed[field] = value
            cases.append(json.dumps(changed))
        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(r.CanaryError, "why:.*remedy:"):
                    r.parse_progress(payload, repository="endaye/lmdj")

    def test_malformed_pointers_and_partial_site_inventory_reject_even_if_resealed(self):
        valid = r.initial_progress("endaye/lmdj")
        for pointer in ({"revision": "main", "receipt_digest": "b" * 64},
                        {"revision": "a" * 40, "receipt_digest": "bad"},
                        {"revision": "a" * 40}, True):
            changed = deepcopy(valid)
            changed["version_accounted"] = pointer
            with self.assertRaises(r.CanaryError):
                r.validate_progress(r.seal(changed), repository="endaye/lmdj")
        changed = deepcopy(valid)
        del changed["deployments"]["runtime"]
        with self.assertRaises(r.CanaryError):
            r.validate_progress(r.seal(changed), repository="endaye/lmdj")

    def test_oversized_non_json_and_nonfinite_payloads_reject(self):
        for raw in (" " * (r.MAX_BYTES + 1), "not json", '{"x": NaN}', b"\xff", None):
            with self.subTest(raw_type=type(raw)):
                with self.assertRaises(r.CanaryError):
                    r.parse_progress(raw, repository="endaye/lmdj")

    def test_read_only_storage_port_loads_valid_record(self):
        document = r.initial_progress("endaye/lmdj")

        class Stored:
            def read(self):
                return json.dumps(document).encode()

        self.assertEqual(r.load_progress(Stored(), repository="endaye/lmdj"), document)

    def test_request_replay_is_stable_and_changed_input_rejects(self):
        operation = r.new_operation("daily:one", "a" * 64, "b" * 64)
        self.assertEqual(r.reconcile_operation(operation, "daily:one", "a" * 64), operation)
        for identifier, digest in (("manual:two", "a" * 64), ("daily:one", "c" * 64)):
            with self.assertRaisesRegex(r.CanaryError, "reused|mismatch"):
                r.reconcile_operation(operation, identifier, digest)

    def test_unknown_effect_never_returns_to_execution(self):
        planned = r.new_operation("manual:one", "a" * 64, "b" * 64)
        running = r.transition_operation(planned, expected_fence=1, state="running")
        unknown = r.transition_operation(running, expected_fence=2, state="unknown")
        self.assertEqual(planned["state"], "planned")
        self.assertEqual(unknown["fence"], 3)
        with self.assertRaisesRegex(r.CanaryError, "transition"):
            r.transition_operation(unknown, expected_fence=3, state="running")
        done = r.transition_operation(unknown, expected_fence=3, state="succeeded")
        self.assertEqual(done["state"], "succeeded")
        self.assertEqual(r.transition_operation(done, expected_fence=4, state="succeeded"), done)

    def test_stale_boolean_fence_and_terminal_reexecution_reject(self):
        planned = r.new_operation("one", "a" * 64, "b" * 64)
        for fence in (0, True, 2):
            with self.assertRaises(r.CanaryError):
                r.transition_operation(planned, expected_fence=fence, state="running")
        failed = r.transition_operation(planned, expected_fence=1, state="failed")
        with self.assertRaises(r.CanaryError):
            r.transition_operation(failed, expected_fence=2, state="running")

    def test_unknown_operation_keys_and_resealed_invalid_fence_reject(self):
        operation = r.new_operation("one", "a" * 64, "b" * 64)
        for field, value in (("fence", True), ("state", "mystery"), ("extra", "x")):
            changed = deepcopy(operation)
            changed[field] = value
            with self.assertRaises(r.CanaryError):
                r.reconcile_operation(r.seal(changed), "one", "a" * 64)


if __name__ == "__main__":
    unittest.main()
