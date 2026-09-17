#!/usr/bin/env python3
"""Real prepared outputs and archives; every live read is an injected reader.

The production change that makes these fail is a projection that guesses an
identity it cannot read, re-observes production after the deployment replaced
it, or assembles a document the deployment effect would refuse.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.release import deployment_projection as projection
from tools.release.model import canonical_json, canonical_sha256
from tools.release.orchestration import JournalError

TAG = "lmdj-v1.0.60.0"
BUILD = "1.0.60.0"
HOST_VERSION = "3.0.0"
REVISION = "b" * 40
WORKER = "lab"
VERSION = "1f2e3d4c-5b6a-4788-9900-aabbccddeeff"
VERSION_URL = f"https://1f2e3d4c-{WORKER}.lmdj.workers.dev"
INDEX = b"<!doctype html><title>lmdj</title>"
MANIFEST = json.dumps(
    {"product_build": BUILD, "host_version": HOST_VERSION}, sort_keys=True,
).encode()


def observation(product_build=BUILD, host_version="2.9.0",
                index=b"prior index", manifest=b"prior manifest"):
    """The shape `cloudflare_site_observation.observe` returns."""
    digests = {"index_sha256": hashlib.sha256(index).hexdigest(),
               "manifest_sha256": hashlib.sha256(manifest).hexdigest()}
    return {
        "response": {"url": f"https://{WORKER}.lmdj.workers.dev",
                     "product_build": product_build,
                     "host_version": host_version,
                     "file_digests": {"/index.html": digests["index_sha256"],
                                      "/host-manifest.json": digests["manifest_sha256"]}},
        "product_build": product_build, "host_version": host_version,
        "release_files": digests,
    }


class Reader:
    """The four live facts, each answerable and each independently withholdable."""

    def __init__(self, *, version=VERSION, observed=None):
        self.version = version
        self.observed = observation() if observed is None else observed
        self.observations = 0

    def worker(self, host):
        return WORKER

    def version_url(self, host, version):
        return f"https://{version[:8]}-{WORKER}.lmdj.workers.dev"

    def replaced_version(self, host):
        return self.version

    def observe(self, host):
        self.observations += 1
        return self.observed


class PreparedOutput:
    """A real prepared output: plan document, its digest, and the staged archive."""

    def __init__(self, root, *, product_build=BUILD, manifest=MANIFEST,
                 hosts=("web-runtime-host",)):
        output = Path(root) / "build/release" / TAG
        (output / "assets").mkdir(parents=True)
        assets = []
        self.archive_names = {}
        self.archive_digests = {}
        for host in hosts:
            prefix = projection.ARCHIVE_PREFIXES[host]
            name = f"{prefix}-{HOST_VERSION}-product-{product_build}.zip"
            archive = output / "assets" / name
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("dist/index.html", INDEX)
                bundle.writestr("dist/host-manifest.json", manifest)
            sha256 = hashlib.sha256(archive.read_bytes()).hexdigest()
            self.archive_names[host] = name
            self.archive_digests[host] = sha256
            assets.append({"name": name, "bytes": archive.stat().st_size,
                           "sha256": sha256})
        self.archive_name = self.archive_names[hosts[0]]
        self.archive_sha256 = self.archive_digests[hosts[0]]
        document = {
            "schema": "lmdj.release-plan.v1", "repository": "endaye/lmdj",
            "tag": TAG, "tag_object": "c" * 40, "target_revision": REVISION,
            "kind": "product", "identity": product_build, "profile": "product",
            "assets": assets,
        }
        payload = canonical_json(document)
        (output / "release-plan.json").write_bytes(payload)
        (output / "release-plan.sha256").write_text(
            hashlib.sha256(payload).hexdigest() + "\n", encoding="ascii")
        self.root = Path(root)
        self.index_sha256 = hashlib.sha256(INDEX).hexdigest()
        self.manifest_sha256 = hashlib.sha256(manifest).hexdigest()


class ProjectionTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def prepared(self, **kwargs):
        return PreparedOutput(self.root, **kwargs)

    def test_an_unprepared_release_has_no_projection(self):
        # Nothing is wrong: `prepare` has not run, so the step waits.
        self.assertIsNone(
            projection.projection(self.root, TAG, "runtime", reader=Reader()))

    def test_an_unreadable_worker_has_no_projection(self):
        # No token, no answer: waiting is the only honest outcome, and no
        # frozen document may be left behind to be believed later.
        self.prepared()
        reader = Reader(version=None)
        self.assertIsNone(
            projection.projection(self.root, TAG, "runtime", reader=reader))
        self.assertIsNone(projection.read_frozen(self.root, TAG, "runtime"))

    def test_a_deployed_worker_with_an_unreadable_origin_has_no_projection(self):
        # A Worker that holds a deployment but serves nothing is a gap, not a
        # first deployment; the prior it would replace is unknown.
        self.prepared()
        reader = Reader(observed=None)
        reader.observed = None
        self.assertIsNone(
            projection.projection(self.root, TAG, "runtime", reader=reader))

    def test_the_projection_binds_this_release_and_what_production_serves(self):
        prepared = self.prepared()
        reader = Reader()
        frozen = projection.projection(self.root, TAG, "runtime", reader=reader)
        self.assertEqual(frozen, {
            "target_revision": REVISION,
            "product_build": BUILD,
            "host_version": HOST_VERSION,
            "site_id": WORKER,
            "archive": {"filename": prepared.archive_name,
                        "sha256": prepared.archive_sha256},
            "release_files": {"index_sha256": prepared.index_sha256,
                              "manifest_sha256": prepared.manifest_sha256},
            "prior": {
                "deploy_id": VERSION, "deploy_url": VERSION_URL,
                "product_build": BUILD, "host_version": "2.9.0",
                "index_sha256": reader.observed["release_files"]["index_sha256"],
                "manifest_sha256": reader.observed["release_files"]["manifest_sha256"],
            },
            "prior_site_sha256": canonical_sha256(reader.observed["response"]),
        })

    def test_an_absent_deployment_projects_no_prior(self):
        # First deployment: the Worker holds nothing, so there is no prior and
        # nothing served to digest — and the projection still stands.
        self.prepared()
        reader = Reader(version=projection.NO_DEPLOYMENT)
        frozen = projection.projection(self.root, TAG, "runtime", reader=reader)
        self.assertIsNone(frozen["prior"])
        self.assertEqual(frozen["prior_site_sha256"],
                         canonical_sha256({"worker": WORKER, "served": False}))
        self.assertEqual(reader.observations, 0)

    def test_the_prior_is_read_before_dispatch_and_never_re_observed(self):
        # The deployment replaces exactly what the first read saw. Re-deriving
        # afterwards would digest this release and report drift against itself.
        self.prepared()
        first = Reader()
        frozen = projection.projection(self.root, TAG, "runtime", reader=first)
        deployed = Reader(observed=observation(product_build=BUILD,
                                               host_version=HOST_VERSION,
                                               index=INDEX, manifest=MANIFEST))
        again = projection.projection(self.root, TAG, "runtime", reader=deployed)
        self.assertEqual(again, frozen)
        self.assertEqual(deployed.observations, 0)

    def test_the_two_steps_freeze_separately(self):
        self.prepared(hosts=("web-runtime-host", "creator-web"))
        runtime = projection.projection(self.root, TAG, "runtime", reader=Reader())
        creator = projection.projection(self.root, TAG, "creator", reader=Reader())
        self.assertEqual(runtime["archive"]["filename"],
                         f"lmdj-web-runtime-host-{HOST_VERSION}-product-{BUILD}.zip")
        self.assertEqual(creator["archive"]["filename"],
                         f"lmdj-creator-web-{HOST_VERSION}-product-{BUILD}.zip")

    def test_a_second_freeze_with_different_contents_is_refused(self):
        # One drive, one agreement: the freeze is write-once, so a later
        # assembly that disagrees is reported rather than silently adopted.
        self.prepared()
        frozen = projection.projection(self.root, TAG, "runtime", reader=Reader())
        with self.assertRaises(JournalError) as raised:
            projection.freeze(self.root, TAG, "runtime",
                              dict(frozen, site_id="another-worker"))
        self.assertIn("already frozen", str(raised.exception))
        self.assertEqual(projection.read_frozen(self.root, TAG, "runtime"), frozen)

    def test_the_freeze_persists_its_bytes_and_the_entry_that_publishes_them(self):
        # The projection is the agreement for the rest of the drive, and the
        # drive outlives this process. Losing the rename would send the next
        # resume back to observe a production the deployment already replaced.
        self.prepared()
        seen = []
        real = os.fsync
        def record(descriptor):
            try:
                seen.append(os.fstat(descriptor).st_ino)
            except OSError:
                pass
            return real(descriptor)
        with mock.patch.object(os, "fsync", record):
            projection.projection(self.root, TAG, "runtime", reader=Reader())
        path = self.root / projection.output_relative(TAG, "runtime")
        self.assertIn(path.stat().st_ino, seen,
                      "why: the frozen bytes were not persisted before the "
                      "rename published them; remedy: fsync before os.replace")
        self.assertIn(path.parent.stat().st_ino, seen,
                      "why: the directory entry the publishing rename creates "
                      "was not persisted, so the freeze can be lost and a "
                      "resume would observe a replaced production; "
                      "remedy: fsync the parent after os.replace")
        self.assertEqual(sorted(entry.name for entry in path.parent.iterdir()),
                         [path.name], "the freeze left a temporary file behind")

    def test_a_failed_handover_closes_the_descriptor_it_was_given(self):
        self.prepared()
        closed = []
        real = os.close
        with mock.patch.object(os, "fdopen", side_effect=ValueError("fixture")), \
                mock.patch.object(os, "close",
                                  lambda fd: (closed.append(fd), real(fd))[1]):
            with self.assertRaises(ValueError):
                projection.projection(self.root, TAG, "runtime", reader=Reader())
        self.assertEqual(len(closed), 1,
                         "why: the descriptor mkstemp handed over was not closed "
                         "when wrapping it failed; "
                         "remedy: close it before re-raising")
        self.assertIsNone(projection.read_frozen(self.root, TAG, "runtime"))

    def test_a_freeze_of_the_wrong_shape_is_refused(self):
        # A document that reached the disk without the compared fields cannot
        # become an expectation; the effect would refuse it anyway, and this
        # refuses it before a dispatch is built from it.
        self.prepared()
        frozen = projection.projection(self.root, TAG, "runtime", reader=Reader())
        path = self.root / projection.output_relative(TAG, "runtime")
        frozen.pop("site_id")
        path.write_bytes(canonical_json(frozen))
        with self.assertRaises(JournalError) as raised:
            projection.read_frozen(self.root, TAG, "runtime")
        self.assertIn("compared fields", str(raised.exception))

    def test_a_reformatted_freeze_is_refused(self):
        # The bytes are the agreement, so an equal document written differently
        # is still drift rather than a second opinion.
        self.prepared()
        frozen = projection.projection(self.root, TAG, "runtime", reader=Reader())
        path = self.root / projection.output_relative(TAG, "runtime")
        path.write_text(json.dumps(frozen, indent=2), encoding="utf-8")
        with self.assertRaises(JournalError) as raised:
            projection.read_frozen(self.root, TAG, "runtime")
        self.assertIn("frozen as", str(raised.exception))

    def test_an_archive_for_another_build_is_refused(self):
        # The plan's identity and the manifest inside the archive must agree;
        # deploying a mismatched pair would pass a wrong Build to production.
        self.prepared(manifest=json.dumps(
            {"product_build": "1.0.59.0", "host_version": HOST_VERSION},
            sort_keys=True).encode())
        with self.assertRaises(JournalError) as raised:
            projection.projection(self.root, TAG, "runtime", reader=Reader())
        self.assertIn("another Product Build", str(raised.exception))

    def test_a_tampered_archive_is_refused(self):
        prepared = self.prepared()
        archive = self.root / "build/release" / TAG / "assets" / prepared.archive_name
        archive.write_bytes(archive.read_bytes() + b"\x00")
        with self.assertRaises(JournalError) as raised:
            projection.projection(self.root, TAG, "runtime", reader=Reader())
        self.assertIn("differ from the plan", str(raised.exception))

    def test_an_unknown_step_is_refused(self):
        with self.assertRaises(JournalError):
            projection.output_relative(TAG, "portal")


class ComparisonShapeTest(unittest.TestCase):
    """What the effect builds from a document must equal what this freezes."""

    def test_the_projection_key_set_is_the_compared_key_set(self):
        from tools.release.deployment_effect import DeploymentEffect  # noqa: F401
        source = Path(ROOT / "tools/release/deployment_effect.py").read_text(
            encoding="utf-8")
        # The effect states its own key set once, in the guard that refuses a
        # projection of any other shape; this reads that statement rather than
        # restating it.
        marker = '"target_revision", "product_build", "host_version", "site_id", "archive", "release_files", "prior", "prior_site_sha256"'
        self.assertIn(marker, source)
        self.assertEqual(
            set(projection._FIELDS),
            {name.strip().strip('"') for name in marker.split(",")})


class CompositionSeamTest(unittest.TestCase):
    """What the real entry answers before the operator's token is present."""

    def setUp(self):
        from tools.release import entry_composition

        self.composition = entry_composition
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def test_without_a_token_the_step_waits(self):
        # Not an error and not a guess: the Worker cannot be read, so the two
        # deployment steps report `pending` exactly as an unprepared release does.
        environment = {k: v for k, v in os.environ.items()
                       if k != "CLOUDFLARE_API_TOKEN"}
        with mock.patch.dict(os.environ, environment, clear=True):
            for step in ("runtime", "creator"):
                with self.subTest(step=step):
                    self.assertIsNone(self.composition.deployment_projection(
                        self.root, TAG, step))

    def inspected(self, state):
        """Run one inspection with the tool stubbed; return the argv it built."""
        reader = self.composition._CloudflareReader("token", state)
        with mock.patch.object(self.composition, "_read_only_tool",
                               return_value=None) as tool:
            self.assertIsNone(reader.replaced_version("web-runtime-host"))
        return tool.call_args[0][1]

    def test_the_inspection_workspace_is_one_the_adapter_accepts(self):
        # The adapter's run store creates its own journal root at 0700 and
        # refuses one whose group or other bits are set. Pre-creating it here
        # with the default mode would make every inspection fail on a check
        # that has nothing to do with the Worker.
        state = self.root / "build/release/cloudflare-inspection"
        argv = self.inspected(state)
        self.assertEqual(argv[-1], str(state))
        self.assertTrue(state.parent.is_dir(), "the workspace has no parent")
        self.assertFalse(state.exists(),
                         "why: the journal root was created here instead of by "
                         "the adapter, which creates it private; "
                         "remedy: create only its parent")

    def test_a_workspace_left_readable_is_made_private(self):
        state = self.root / "build/release/cloudflare-inspection"
        state.mkdir(parents=True)
        state.chmod(0o755)
        self.inspected(state)
        self.assertEqual(state.stat().st_mode & 0o077, 0,
                         "why: an existing workspace kept group or other bits, "
                         "which the adapter refuses; "
                         "remedy: make it private before inspecting")

    def test_an_unreadable_tool_reads_as_no_document(self):
        # Every live read fails closed into None, which each caller turns into
        # `pending` rather than into an assumption about production.
        self.assertIsNone(self.composition._read_only_tool(
            self.root / "absent-tool.py", ()))

    def test_the_reader_names_no_worker_url_or_version_of_its_own(self):
        # The Worker name, both origin shapes and the replaced version all come
        # from installed read-only tools; a literal here would drift silently.
        source = Path(ROOT / "tools/release/entry_composition.py").read_text(
            encoding="utf-8")
        seam = source[source.index("class _CloudflareReader"):
                      source.index("def deployment_projection")]
        for literal in ("workers.dev", "https://", "WORKERS", "TARGETS"):
            self.assertNotIn(literal, seam)


if __name__ == "__main__":
    unittest.main(verbosity=2)
