"""Fixed discovery inventory; not proof of remote initialization or recovery."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
import batch_runtime
import review_discovery


class DiscoveryStorageTests(unittest.TestCase):
    def setUp(self):
        self.config = batch_runtime.strict_json(
            (ROOT / "scripts/ci/review_discovery_storage.json").read_bytes())

    def test_closed_top_level(self):
        self.assertEqual(set(self.config), {"storage", "source_floor", "review_workflow_id"},
                         "why: discovery config roles differ; remedy: retain the reviewed closed inventory")

    def test_exact_reserved_storage(self):
        self.assertEqual(self.config["storage"], {
            "repository": "endaye/lmdj", "issue_number": 849,
            "issue_node_id": "I_kwDOTK_1fs8AAAABQKj2dQ",
            "bot_node_id": "MDM6Qm90NDE4OTgyODI=", "workflow_id": 352307416,
            "epoch": "review-discovery-20260908-issue849"},
            "why: discovery identity differs from reservation; remedy: audit and review any storage migration")

    def test_source_starts_with_first_serial_review_producer(self):
        self.assertEqual(self.config["source_floor"], {
            "control_sha": "0bcb14e9ada890f4c0e6b549f72dcdce05cf9c1c",
            "created_at": "2026-09-07T18:29:09Z"},
            "why: source floor omits producer history; remedy: preserve the verified introducing SHA/time")

    def test_review_workflow_is_not_controller(self):
        self.assertIs(type(self.config["review_workflow_id"]), int,
                      "why: review workflow ID is not integer; remedy: retain actual numeric identity")
        self.assertEqual(self.config["review_workflow_id"], 352327391,
                         "why: wrong review workflow; remedy: use the independently verified PR Review ID")

    def test_actual_protocol_accepts_initial_state_without_baseline(self):
        row = self.config["storage"]
        state = review_discovery.new_state(epoch=row["epoch"], repository=row["repository"],
            workflow_id=self.config["review_workflow_id"], source_floor=self.config["source_floor"])
        self.assertEqual(state["runs"], {},
                         "why: inventory invented reviews; remedy: discover authenticated original attempts")
        self.assertEqual(state["generation"], 0,
                         "why: config creates progress; remedy: leave initial discovery unprocessed")

    def test_actual_runtime_accepts_six_fields_without_network(self):
        class NoApi:
            def _request(self, *args, **kwargs):
                raise AssertionError("why: config inspection called API; remedy: keep initialization separate")
        environment = {"GITHUB_REPOSITORY": "endaye/lmdj", "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "17", "GITHUB_RUN_ATTEMPT": "1",
            "BATCH_WRITER_LOCK": "self-test-report"}
        runtime = batch_runtime.Runtime(self.config["storage"], root=ROOT,
                                       environment=environment, api=NoApi())
        self.assertEqual(runtime.config, self.config["storage"],
                         "why: Runtime changes storage identity; remedy: preserve existing six-field protocol")


if __name__ == "__main__":
    unittest.main()
