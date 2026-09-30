#!/usr/bin/env python3
"""The reviewed changelog editorial channel stores one approved pair per request."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.release.changelog_editorial import (  # noqa: E402
    EDITORIAL_FILE,
    EditorialError,
    load_pair,
    read,
    record,
)
from tools.release.model import canonical_json  # noqa: E402

REQUEST = "release-" + "1" * 16
TAG = "lmdj-v1.0.66.0"
BINDING = {"schema": "lmdj.release-changelog.v1", "sha256": "1" * 64, "notes_sha256": "2" * 64}
CHANGES = [{"category": "fix", "area": "creator", "text": "A fix.", "commits": ["a" * 40]}]
EXCLUSIONS = [{"commit": "b" * 40, "reason": "documentation only"}]


class EditorialChannelTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.operations = Path(temporary.name).resolve() / "operations" / REQUEST

    def record(self, **changes):
        arguments = dict(request_id=REQUEST, tag=TAG, changes=CHANGES,
                         exclusions=EXCLUSIONS, binding=BINDING)
        arguments.update(changes)
        return record(self.operations, **arguments)

    def test_nothing_is_recorded_before_the_owner_approves(self):
        self.assertIsNone(read(self.operations, request_id=REQUEST))

    def test_a_recorded_editorial_reads_back_exactly(self):
        path = self.record()
        self.assertEqual(path, self.operations / EDITORIAL_FILE)
        document = read(self.operations, request_id=REQUEST)
        self.assertEqual((document["tag"], document["changes"], document["exclusions"],
                          document["binding"]), (TAG, CHANGES, EXCLUSIONS, BINDING))

    def test_the_record_is_write_once(self):
        self.record()
        self.record()  # identical: a no-op
        with self.assertRaisesRegex(EditorialError, "differs from the editorial already recorded"):
            self.record(exclusions=[])
        self.assertEqual(read(self.operations, request_id=REQUEST)["exclusions"], EXCLUSIONS)

    def test_another_requests_record_is_refused(self):
        self.record()
        with self.assertRaisesRegex(EditorialError, "belongs to another request"):
            read(self.operations, request_id="release-" + "2" * 16)

    def test_an_edited_or_malformed_record_is_refused(self):
        self.record()
        path = self.operations / EDITORIAL_FILE
        document = json.loads(path.read_bytes())
        path.write_text(json.dumps(document, indent=2))
        with self.assertRaisesRegex(EditorialError, "canonical form"):
            read(self.operations, request_id=REQUEST)
        document["binding"] = {"sha256": "short"}
        path.write_bytes(canonical_json(document))
        with self.assertRaisesRegex(EditorialError, "frozen binding"):
            read(self.operations, request_id=REQUEST)

    def test_an_unbound_editorial_cannot_be_recorded(self):
        with self.assertRaises(EditorialError):
            self.record(binding={"sha256": "1" * 64})
        self.assertIsNone(read(self.operations, request_id=REQUEST))

    def test_the_approved_file_is_exactly_the_pair(self):
        source = self.operations.parent / "editorial.json"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(json.dumps({"changes": CHANGES, "exclusions": EXCLUSIONS}))
        self.assertEqual(load_pair(source), (CHANGES, EXCLUSIONS))
        for bad in ({"changes": CHANGES}, {"changes": {}, "exclusions": []},
                    {"changes": [], "exclusions": [], "notes": "extra"}):
            source.write_text(json.dumps(bad))
            with self.assertRaises(EditorialError):
                load_pair(source)


if __name__ == "__main__":
    unittest.main()
