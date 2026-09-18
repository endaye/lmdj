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
import time
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

    def test_a_concurrent_drive_cannot_replace_a_frozen_projection(self):
        # The existence check and the write are not one operation, so two
        # drives for the same tag can both see nothing frozen. The loser must
        # fail closed rather than replace bytes the winner is already bound to.
        self.prepared()
        frozen = projection.projection(self.root, TAG, "runtime", reader=Reader())
        real = projection.read_frozen

        def blind_once(*arguments, calls=[]):
            # Only the existence check misses it, the way the losing drive's
            # would; the handler then reads what is actually on disk.
            calls.append(None)
            return None if len(calls) == 1 else real(*arguments)

        with mock.patch.object(projection, "read_frozen", blind_once):
            with self.assertRaises(JournalError) as raised:
                projection.freeze(self.root, TAG, "runtime",
                                  dict(frozen, site_id="another-worker"))
        self.assertIn("another drive", str(raised.exception))
        self.assertEqual(real(self.root, TAG, "runtime"), frozen)
        path = self.root / projection.output_relative(TAG, "runtime")
        self.assertEqual(sorted(entry.name for entry in path.parent.iterdir()),
                         [path.name], "the losing writer left a temporary behind")

    def test_a_concurrent_drive_that_agrees_gets_the_frozen_bytes(self):
        # Losing the race is not an error when both drives assembled the same
        # projection: the loser is bound to exactly what the winner wrote.
        self.prepared()
        frozen = projection.projection(self.root, TAG, "runtime", reader=Reader())
        real = projection.read_frozen

        def blind_once(*arguments, calls=[]):
            calls.append(None)
            return None if len(calls) == 1 else real(*arguments)

        with mock.patch.object(projection, "read_frozen", blind_once):
            self.assertEqual(
                projection.freeze(self.root, TAG, "runtime", dict(frozen)), frozen)

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

    def test_an_entry_that_is_not_a_regular_file_is_refused(self):
        # A link member under an entry file's name would digest its target path
        # rather than served bytes. Two other layers already close this — the
        # plan's archive digest refuses a tampered archive, and `create_dist_zip`
        # refuses a symlink at build time — so this is the third, stated where
        # the bytes are actually read.
        prepared = self.prepared()
        archive = self.root / "build/release" / TAG / "assets" / prepared.archive_name
        link = zipfile.ZipInfo("dist/index.html")
        link.create_system = 3
        link.external_attr = (0o120777 << 16)
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr(link, b"../elsewhere/index.html")
            bundle.writestr("dist/host-manifest.json", MANIFEST)
        document = json.loads((self.root / "build/release" / TAG
                               / "release-plan.json").read_bytes())
        document["assets"][0]["sha256"] = hashlib.sha256(
            archive.read_bytes()).hexdigest()
        payload = canonical_json(document)
        (self.root / "build/release" / TAG / "release-plan.json").write_bytes(payload)
        (self.root / "build/release" / TAG / "release-plan.sha256").write_text(
            hashlib.sha256(payload).hexdigest() + "\n", encoding="ascii")
        with self.assertRaises(JournalError) as raised:
            projection.projection(self.root, TAG, "runtime", reader=Reader())
        self.assertIn("not a regular file", str(raised.exception))

    def test_a_url_that_is_not_the_immutable_origin_is_refused(self):
        # A well-formed but wrong URL would freeze and only be caught by the
        # effect's field comparison, long after the dispatch. A substring test
        # passed several of these; the check is on the host's first label,
        # which is where the two origins actually differ.
        wrong = {
            "production": f"https://{WORKER}.lmdj.workers.dev",
            "worker in the path": f"https://{VERSION[:8]}.lmdj.workers.dev/{WORKER}",
            "prefix in the path": f"https://{WORKER}.lmdj.workers.dev/{VERSION[:8]}",
            "both in a query": f"https://{WORKER}.lmdj.workers.dev/?v={VERSION[:8]}-{WORKER}",
            "another version": f"https://0e1d2c3b-{WORKER}.lmdj.workers.dev",
            "another worker": f"https://{VERSION[:8]}-creator.lmdj.workers.dev",
        }
        for label, url in wrong.items():
            with self.subTest(url=label):
                directory = tempfile.TemporaryDirectory()
                self.addCleanup(directory.cleanup)
                self.root = Path(directory.name)
                self.prepared()
                reader = Reader()
                reader.version_url = lambda host, version, u=url: u
                with self.assertRaises(JournalError) as raised:
                    projection.projection(self.root, TAG, "runtime", reader=reader)
                self.assertIn("names another version or Worker",
                              str(raised.exception))

    def test_a_first_deployment_is_decided_by_type_not_identity(self):
        # A reader assembled from a second import of this module hands back a
        # different object; identity would send a first deployment down the
        # "invalid version" branch instead.
        self.prepared()
        reader = Reader(version=projection.NoDeployment())
        self.assertIsNot(reader.version, projection.NO_DEPLOYMENT)
        frozen = projection.projection(self.root, TAG, "runtime", reader=reader)
        self.assertIsNone(frozen["prior"])

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

    def test_each_tag_inspects_in_its_own_workspace(self):
        # Two concurrent drives must not share one adapter run store, and the
        # workspace belongs beside the projection that tag freezes.
        from tools.release.prepared_step import output_relative

        seen = {}
        environment = dict(os.environ, CLOUDFLARE_API_TOKEN="token")
        for tag in (TAG, "lmdj-v1.0.61.0"):
            with mock.patch.dict(os.environ, environment, clear=True), \
                    mock.patch.object(self.composition, "_CloudflareReader") as built, \
                    mock.patch("tools.release.deployment_projection.projection",
                               return_value=None):
                self.composition.deployment_projection(self.root, tag, "runtime")
            seen[tag] = Path(built.call_args[0][1])
        self.assertNotEqual(seen[TAG], seen["lmdj-v1.0.61.0"])
        for tag, workspace in seen.items():
            self.assertEqual(workspace.parent,
                             self.root / output_relative(tag),
                             "why: the inspection workspace is not beside the "
                             "projection its tag freezes; "
                             "remedy: derive it from the prepared output path")

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

    def test_a_link_planted_at_the_workspace_is_refused_not_chmodded(self):
        # The path sits under an ignored directory, so anything that can write
        # the worktree can plant a link here. `is_dir()` follows links, so
        # chmodding what it finds would set 0700 on someone else's directory.
        victim = self.root / "victim"
        victim.mkdir()
        victim.chmod(0o755)
        state = self.root / "build/release" / TAG / "cloudflare-inspection"
        state.parent.mkdir(parents=True)
        state.symlink_to(victim)
        reader = self.composition._CloudflareReader("token", state)
        with self.assertRaises(JournalError) as raised:
            reader.replaced_version("web-runtime-host")
        self.assertIn("not a directory", str(raised.exception))
        self.assertEqual(victim.stat().st_mode & 0o777, 0o755,
                         "why: a planted link had its target chmodded, so this "
                         "process changed permissions on a directory it does "
                         "not own; remedy: lstat and refuse")

    def test_a_workspace_left_readable_is_made_private(self):
        state = self.root / "build/release/cloudflare-inspection"
        state.mkdir(parents=True)
        state.chmod(0o755)
        self.inspected(state)
        self.assertEqual(state.stat().st_mode & 0o077, 0,
                         "why: an existing workspace kept group or other bits, "
                         "which the adapter refuses; "
                         "remedy: make it private before inspecting")

    def test_a_tool_that_floods_stdout_reads_as_no_document(self):
        # The timeout is not a size bound: without one, whatever the child
        # prints is captured before anything can refuse it.
        flood = self.root / "flood.py"
        flood.write_text(
            "import sys\n"
            "sys.stdout.write('{\"a\": \"' + 'x' * (2 * 1024 * 1024) + '\"}')\n",
            encoding="utf-8")
        self.assertIsNone(self.composition._read_only_tool(flood, ()))

    def test_a_tool_within_the_bound_still_reads(self):
        answer = self.root / "answer.py"
        answer.write_text("print('{\"worker\": \"lab\"}')\n", encoding="utf-8")
        self.assertEqual(self.composition._read_only_tool(answer, ()),
                         {"worker": "lab"})

    def test_a_tool_that_hangs_is_bounded_by_the_timeout(self):
        # The defect this replaced: reading a pipe blocks until EOF, so a tool
        # that prints a little and then hangs never reaches the size bound or
        # the timeout, and the drive stalls instead of reporting `pending`.
        hang = self.root / "hang.py"
        hang.write_text("import sys, time\n"
                        "sys.stdout.write('{\"worker\": \"lab\"}')\n"
                        "sys.stdout.flush()\n"
                        "time.sleep(600)\n", encoding="utf-8")
        started = time.monotonic()
        with mock.patch.object(self.composition, "_READ_TIMEOUT", 3):
            self.assertIsNone(self.composition._read_only_tool(hang, ()))
        self.assertLess(time.monotonic() - started, 60,
                        "why: the call was not bounded by the timeout, so a "
                        "hung tool stalls the drive; "
                        "remedy: bound the duration and kill the child")

    def test_a_failed_inspection_is_not_cached(self):
        # One transient timeout must not make every later read in the same
        # assembly return None and report `pending` after the tool would
        # have answered.
        answers = [None, {"worker": "lab", "exists": True,
                          "deployment": {"version_id": VERSION}}]
        reader = self.composition._CloudflareReader("token", self.root / "state")
        with mock.patch.object(self.composition, "_read_only_tool",
                               side_effect=answers):
            self.assertIsNone(reader.replaced_version("web-runtime-host"))
            self.assertEqual(reader.worker("web-runtime-host"), "lab")

    def test_a_successful_inspection_is_read_once(self):
        # The Worker identity and the version it holds must come from one
        # observation, not two reads that could straddle a change.
        reader = self.composition._CloudflareReader("token", self.root / "state")
        with mock.patch.object(
                self.composition, "_read_only_tool",
                return_value={"worker": "lab", "exists": True,
                              "deployment": {"version_id": VERSION}}) as tool:
            self.assertEqual(reader.worker("web-runtime-host"), "lab")
            self.assertEqual(reader.replaced_version("web-runtime-host"), VERSION)
        self.assertEqual(tool.call_count, 1)

    def test_one_assembly_reads_each_tool_once(self):
        # The module documents itself as one Worker read and one origin read.
        # Without memoizing the origins, `version_url` and `observe` each
        # launched their own subprocess and `observe` launched a second.
        reader = self.composition._CloudflareReader("token", self.root / "state")
        answers = {
            "cloudflare_host.py": {"worker": "lab", "exists": True,
                                   "deployment": {"version_id": VERSION}},
            "cloudflare_deployment_evidence.py": {
                "host": "web-runtime-host", "worker": WORKER,
                "production": f"https://{WORKER}.lmdj.workers.dev",
                "version": VERSION_URL},
            "cloudflare_site_observation.py": observation(),
        }
        seen = []

        def answer(tool, arguments, **kwargs):
            seen.append(Path(tool).name)
            return answers[Path(tool).name]

        with mock.patch.object(self.composition, "_read_only_tool", answer):
            reader.worker("web-runtime-host")
            reader.replaced_version("web-runtime-host")
            reader.version_url("web-runtime-host", VERSION)
            reader.observe("web-runtime-host")
        self.assertEqual(sorted(seen), [
            "cloudflare_deployment_evidence.py",
            "cloudflare_deployment_evidence.py",
            "cloudflare_host.py",
            "cloudflare_site_observation.py",
        ], "why: one assembly launched more subprocesses than the reads it "
           "documents; remedy: memoize each tool's answer per host and version")

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
