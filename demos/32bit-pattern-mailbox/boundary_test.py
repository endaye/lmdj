"""Reduced timing/ordering regressions; not an Engine or weak-memory model."""

from itertools import combinations
import unittest


def interleavings(audio, control):
    """All merges preserving each actor's program order."""
    for positions in combinations(range(len(audio) + len(control)), len(audio)):
        selected = set(positions)
        a, c = iter(audio), iter(control)
        yield [next(a) if index in selected else next(c)
               for index in range(len(audio) + len(control))]


def claimed_boundary(pending_frame, pending_bar_frames, frontier):
    if pending_frame >= frontier:
        return pending_frame
    return pending_frame + ((frontier - pending_frame) // pending_bar_frames + 1) * pending_bar_frames


class BoundaryTest(unittest.TestCase):
    def test_callback_frontier_preserves_claimed_boundary(self):
        # Values from publication_claim_race_preserves_the_claimed_boundary_and_phase:
        # callback covers [95999,96001); pending 90-BPM Pattern has 128000-frame bars.
        self.assertEqual(claimed_boundary(96000, 128000, 95999 + 2), 224000)

    def test_tail_only_transport_is_a_detected_wrong_protocol(self):
        # Audio observation at callback tail cannot substitute for decision data.
        wrong = claimed_boundary(96000, 128000, 95999)
        self.assertEqual(wrong, 96000)
        self.assertNotEqual(wrong, 224000)

    def test_origin_published_before_descriptor_clear(self):
        # This SC ordering model isolates the source's origin-before-A-clear rule.
        # A reader observing A clear then reads the separately published Transport.
        outcomes = set()
        for trace in interleavings(["publish_origin", "clear_a"], ["read_a", "read_origin"]):
            a, origin, observed_a = 1, 0, None
            for action in trace:
                if action == "publish_origin":
                    origin = 96000
                elif action == "clear_a":
                    a = 0
                elif action == "read_a":
                    observed_a = a
                elif observed_a == 0:
                    outcomes.add(origin)
                    self.assertEqual(origin, 96000, trace)
        self.assertEqual(outcomes, {96000}, "model never observed completed activation")

    def test_late_origin_publication_has_a_counterexample(self):
        counterexamples = []
        for trace in interleavings(["clear_a", "publish_origin"], ["read_a", "read_origin"]):
            a, origin, observed_a = 1, 0, None
            for action in trace:
                if action == "publish_origin":
                    origin = 96000
                elif action == "clear_a":
                    a = 0
                elif action == "read_a":
                    observed_a = a
                elif observed_a == 0 and origin == 0:
                    counterexamples.append(trace)
        self.assertIn(["clear_a", "read_a", "read_origin", "publish_origin"], counterexamples)

    def test_claim_handoff_publishes_a_before_clearing_q(self):
        # Deliberately stops before activation/cancellation, where empty A can be valid.
        for reversed_order in (False, True):
            actions = ["publish_a", "clear_q"]
            if reversed_order:
                actions.reverse()
            missing = False
            completed_seen = False
            for trace in interleavings(actions, ["read_q", "read_a"]):
                q, a, observed_q = 1 | 8, 0, None
                for action in trace:
                    if action == "publish_a":
                        a = 1
                    elif action == "clear_q":
                        q = 0
                    elif action == "read_q":
                        observed_q = q
                    elif observed_q == 0:
                        completed_seen = True
                        missing |= a == 0
            self.assertTrue(completed_seen, "model omitted observing Q clear")
            self.assertEqual(missing, reversed_order,
                             "handoff order must distinguish missing-descriptor mutant")

    def test_empty_claim_marker_is_not_a_pattern_identity(self):
        slot_mask, claimed = 7, 8
        claimed_empty = 0 | claimed
        self.assertNotEqual(claimed_empty, 0)
        self.assertEqual(claimed_empty & slot_mask, 0)
        # Treating every nonzero Q as a generation/slot would consult invalid payload.
        self.assertFalse(1 <= (claimed_empty & slot_mask) <= 4)


if __name__ == "__main__":
    unittest.main()
