#!/usr/bin/env python3
"""Regression tests for Native Host protocol response deadlines."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parent))

from native_host_test import response_timeout_seconds  # noqa: E402


class NativeHostTimeoutPolicyTest(unittest.TestCase):
    def test_only_durable_record_stop_receives_the_extended_deadline(self):
        self.assertEqual(
            response_timeout_seconds({"operation": "record.stop"}),
            30.0,
        )
        for request in (
            {"operation": "record.begin"},
            {"operation": "trigger"},
            {"operation": "status"},
            {},
        ):
            with self.subTest(request=request):
                self.assertEqual(response_timeout_seconds(request), 10.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
