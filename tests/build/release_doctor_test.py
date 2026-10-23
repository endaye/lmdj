#!/usr/bin/env python3
"""`scripts/release.sh doctor` names each host defect and its remedy (#2422 item 5).

Each case fixes one fact about one check through injected probes: the pinned
emsdk, both signing-key roles in their own keyrings, GitHub auth, the journal
writer lock, a second release driver, disk, load, fseventsd, Spotlight and the
M1 runner. A failed check always carries a remedy; a check that does not apply
to the platform is `skip`, never `ok`.
"""

import fcntl
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.release import doctor  # noqa: E402
from tools.release.doctor import (  # noqa: E402
    Check,
    HostProbes,
    check_disk,
    check_emsdk,
    check_fseventsd,
    check_github_auth,
    check_journal_lock,
    check_load,
    check_release_processes,
    check_runner,
    check_signing_keys,
    check_spotlight,
    doctor_passed,
    format_doctor,
    run_doctor,
)

TAG, REVISION, RELEASES = "6.0.5", "d" * 40, "e" * 40
PRODUCT, CHECKSUM = "A" * 40, "B" * 40
LOCK = {"emsdk_tag": TAG, "emsdk_revision": REVISION,
        "emscripten_releases_revision": RELEASES}


class Probes:
    """Answers only what a check asks; unanswered reads are refusals."""

    platform = "darwin"

    def __init__(self, root):
        self.root = Path(root)
        self.environ = {}
        self.pid = 4242
        self.home = self.root / "home"
        self.files = {str(self.root / doctor.EMSCRIPTEN_LOCK): json.dumps(LOCK)}
        self.dirs = set()
        self.commands = {}
        self.free = 100 * 1024 ** 3
        self.load, self.cpus = 2.0, 8
        self.rows = []
        self.ancestor_pids = set()
        self.lock = "free"
        self.asked = []

    def is_dir(self, path):
        return str(path) in self.dirs

    def read_text(self, path):
        try:
            return self.files[str(path)]
        except KeyError:
            raise FileNotFoundError(str(path)) from None

    def run(self, argv, *, env=None):
        key = tuple(str(part) for part in argv)
        self.asked.append(key)
        return self.commands.get(key, (1, "", "unanswered"))

    def disk_free(self, path):
        return self.free

    def loadavg(self):
        return self.load

    def cpu_count(self):
        return self.cpus

    def processes(self):
        return list(self.rows)

    def lock_state(self, path):
        return self.lock

    def ancestors(self):
        return set(self.ancestor_pids)

    # fixture helpers
    def install_emsdk(self, sdk, *, head=REVISION, mapped=RELEASES, installed=TAG):
        self.dirs.add(str(sdk))
        self.commands[("git", "-C", str(sdk), "rev-parse", "HEAD")] = (0, head + "\n", "")
        self.files[str(sdk / "emscripten-releases-tags.json")] = json.dumps(
            {"releases": {TAG: mapped}})
        self.files[str(sdk / "upstream/emscripten/emscripten-version.txt")] = f'"{installed}"\n'

    def answer_key(self, fingerprint, *, homedir=None, present=True):
        argv = ["gpg", "--batch", "--with-colons", "--list-secret-keys", fingerprint]
        if homedir is not None:
            argv[1:1] = ["--homedir", homedir]
        self.commands[tuple(argv)] = (0, "sec:u:255:22:...\n" if present else "", "")


class DoctorChecksTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.probes = Probes(self.root)
        self.sdk = self.root / doctor.DEFAULT_EMSDK

    def assertFails(self, check, *, detail, remedy):
        self.assertEqual(check.status, "fail", check)
        self.assertIn(detail, check.detail)
        self.assertIn(remedy, check.remedy)

    # emsdk
    def test_emsdk_at_the_pinned_tag_and_revision_passes(self):
        self.probes.install_emsdk(self.sdk)
        check = check_emsdk(self.probes, self.root)
        self.assertEqual(check.status, "ok", check)
        self.assertIn(TAG, check.detail)

    def test_emsdk_honours_the_EMSDK_environment(self):
        other = self.root / "elsewhere/emsdk"
        self.probes.environ["EMSDK"] = str(other)
        self.probes.install_emsdk(other)
        self.assertEqual(check_emsdk(self.probes, self.root).status, "ok")

    def test_missing_emsdk_names_the_install_and_the_protection(self):
        check = check_emsdk(self.probes, self.root)
        self.assertFails(check, detail="no emsdk at", remedy="emsdk install 6.0.5")
        self.assertIn("Never delete build/toolchains", check.remedy)

    def test_emsdk_drift_from_the_lock_is_named(self):
        cases = {"head": dict(head="f" * 40), "mapped": dict(mapped="f" * 40),
                 "installed": dict(installed="6.0.4")}
        for name, drift in cases.items():
            with self.subTest(drift=name):
                self.probes = Probes(self.root)
                self.probes.install_emsdk(self.sdk, **drift)
                check = check_emsdk(self.probes, self.root)
                self.assertFails(check, detail="", remedy="emsdk")
                self.assertIn(REVISION if name == "head" else RELEASES if name == "mapped" else TAG,
                              check.detail)

    def test_unreadable_lock_fails_closed(self):
        del self.probes.files[str(self.root / doctor.EMSCRIPTEN_LOCK)]
        self.assertFails(check_emsdk(self.probes, self.root), detail="unreadable",
                         remedy="emscripten.lock.json")

    # signing keys
    def test_each_key_role_is_looked_up_in_its_own_keyring(self):
        self.probes.answer_key(PRODUCT)
        self.probes.answer_key(CHECKSUM, homedir=str(self.probes.home / doctor.CHECKSUM_KEYRING))
        checks = check_signing_keys(self.probes, product_fingerprint=PRODUCT,
                                    checksum_fingerprint=CHECKSUM)
        self.assertEqual([c.status for c in checks], ["ok", "ok"])
        self.assertIn(".gnupg-lmdj-release", checks[1].detail)
        self.assertNotIn("--homedir", " ".join(self.probes.asked[0]))

    def test_a_missing_role_key_names_its_keyring_and_the_pitfall(self):
        self.probes.answer_key(PRODUCT)
        self.probes.answer_key(CHECKSUM, homedir=str(self.probes.home / doctor.CHECKSUM_KEYRING),
                               present=False)
        checks = check_signing_keys(self.probes, product_fingerprint=PRODUCT,
                                    checksum_fingerprint=CHECKSUM)
        self.assertEqual(checks[0].status, "ok")
        self.assertFails(checks[1], detail=f"secret key {CHECKSUM} is not in",
                         remedy="release-signing-role-keyrings")
        self.assertIn("do not move the other role's key", checks[1].remedy)

    def test_the_product_role_follows_GNUPGHOME(self):
        self.probes.environ["GNUPGHOME"] = "/custom/home"
        checks = check_signing_keys(self.probes, product_fingerprint=PRODUCT,
                                    checksum_fingerprint=CHECKSUM)
        self.assertIn("/custom/home", checks[0].detail)

    # gh auth
    def test_github_auth_accepts_a_token_or_a_login(self):
        self.probes.environ["GITHUB_TOKEN"] = "x"
        self.assertEqual(check_github_auth(self.probes).status, "ok")
        del self.probes.environ["GITHUB_TOKEN"]
        self.probes.commands[("gh", "auth", "token")] = (0, "gho_x\n", "")
        self.assertEqual(check_github_auth(self.probes).status, "ok")
        self.probes.commands[("gh", "auth", "token")] = (1, "", "not logged in")
        self.assertFails(check_github_auth(self.probes), detail="no GITHUB_TOKEN",
                         remedy="gh auth login")

    # journal lock and processes
    def test_a_held_writer_lock_is_named_and_never_deleted(self):
        self.assertEqual(check_journal_lock(self.probes, self.root / "journal").status, "ok")
        self.probes.lock = "held"
        check = check_journal_lock(self.probes, self.root / "journal")
        self.assertFails(check, detail="held by another writer", remedy="never delete writer.lock")
        # A lock that cannot be opened is a permissions defect, not a holder.
        self.probes.lock = "unreadable: Permission denied"
        check = check_journal_lock(self.probes, self.root / "journal")
        self.assertFails(check, detail="cannot be opened (unreadable: Permission denied)",
                         remedy="fix its ownership and mode")
        self.assertNotIn("held", check.detail)

    def test_only_an_interpreter_running_the_cli_counts_as_a_release_process(self):
        self.probes.rows = [
            (4242, 1.0, "python3 /repo/tools/release/cli.py --repo-root /repo doctor"),
            (7, 0.0, "/bin/zsh -c eval 'python3 tools/release/cli.py --repo-root x status'"),
            (8, 0.0, "vim tools/release/cli.py"),
        ]
        self.assertEqual(check_release_processes(self.probes).status, "ok")
        # Interpreter options, `env`, and the module form are all the CLI.
        for command in ("env python3 -I -B tools/release/cli.py --repo-root /repo run --authority x",
                        "/usr/bin/python3.11 -m tools.release.cli --repo-root /repo resume release-1"):
            with self.subTest(command=command):
                self.probes.rows.append((9, 3.0, command))
                self.assertEqual(check_release_processes(self.probes).status, "fail")
                self.probes.rows.pop()
        # Read-only commands beside a driver are not a second driver.
        for arguments in ("--repo-root /repo status", "--repo-root=/repo audit --remote",
                          "--repo-root /repo doctor", "--repo-root /repo hydrate",
                          "--repo-root /repo publication-record t 1 a"):
            with self.subTest(arguments=arguments):
                self.probes.rows.append((9, 3.0, f"/usr/bin/python3 /repo/tools/release/cli.py {arguments}"))
                self.assertEqual(check_release_processes(self.probes).status, "ok")
                self.probes.rows.pop()
        for arguments in ("--repo-root /repo resume release-1", "--repo-root=/repo run --authority x",
                          "--repo-root /repo prepare lmdj-v1.0.1.0", "--repo-root /repo retire r --superseded-by t"):
            with self.subTest(arguments=arguments):
                self.probes.rows.append((9, 3.0, f"/usr/bin/python3 /repo/tools/release/cli.py {arguments}"))
                check = check_release_processes(self.probes)
                self.assertFails(check, detail=f"9 ({arguments})", remedy="kill <pid>")
                self.probes.rows.pop()
        # A wrapper shell above this process repeats the command being started.
        self.probes.rows.append((3, 0.0, "sh -c python3 /repo/tools/release/cli.py --repo-root /repo run --authority x"))
        self.assertEqual(check_release_processes(self.probes).status, "fail")
        self.probes.ancestor_pids = {3}
        self.assertEqual(check_release_processes(self.probes).status, "ok")

    # disk and load
    def test_disk_and_load_thresholds_name_what_to_free_and_stop(self):
        self.assertEqual(check_disk(self.probes, self.root).status, "ok")
        self.probes.free = 5 * 1024 ** 3
        check = check_disk(self.probes, self.root)
        self.assertFails(check, detail="5.0 GiB free, 20.0 GiB needed", remedy="never remove build/toolchains")
        self.assertEqual(check_load(self.probes).status, "ok")
        self.probes.load = 9.5
        check = check_load(self.probes)
        self.assertFails(check, detail="load 9.5 exceeds 8 cpus", remedy="pause the M1 runner")

    # fseventsd and spotlight
    def test_fseventsd_and_spotlight_are_macos_checks_with_cpu_limits(self):
        self.probes.rows = [(1, 90.0, "/System/.../fseventsd"), (2, 40.0, "/System/.../mds_stores"),
                            (3, 5.0, "/System/.../mds"), (4, 1.0, "   ")]
        self.probes.commands[("mdutil", "-s", "/")] = (0, "/:\n\tIndexing enabled. \n", "")
        check = check_fseventsd(self.probes)
        self.assertFails(check, detail="fseventsd is at 90% cpu", remedy="sudo killall fseventsd")
        check = check_spotlight(self.probes, self.root)
        self.assertFails(check, detail="indexing at 45% cpu", remedy="Spotlight Privacy")
        self.assertIn("volume indexing enabled", check.detail)
        self.probes.rows = [(1, 1.0, "/System/.../fseventsd"), (2, 2.0, "/System/.../mds_stores")]
        self.assertEqual(check_fseventsd(self.probes).status, "ok")
        self.assertEqual(check_spotlight(self.probes, self.root).status, "ok")
        self.probes.platform = "linux"
        self.assertEqual(check_fseventsd(self.probes).status, "skip")
        self.assertEqual(check_spotlight(self.probes, self.root).status, "skip")
        self.assertEqual(check_runner(self.probes).status, "skip")

    # runner
    def test_runner_states_pause_and_resume_commands(self):
        import plistlib
        label = "actions.runner.endaye-lmdj.endaye-mbp-m1"
        self.probes.commands[("launchctl", "list")] = (0, "123\t0\tcom.apple.x\n", "")
        self.assertEqual(check_runner(self.probes).status, "ok")
        self.probes.commands[("launchctl", "list")] = (0, f"123\t0\tcom.apple.x\n77\t0\t{label}\n", "")
        idle = check_runner(self.probes)
        self.assertEqual(idle.status, "ok")
        self.assertIn(f"launchctl bootout gui/$(id -u)/{label}", idle.detail)
        self.assertIn(f"launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/{label}.plist", idle.detail)
        self.probes.files[str(self.probes.home / "Library/LaunchAgents" / f"{label}.plist")] = plistlib.dumps(
            {"Label": label, "WorkingDirectory": "/Users/x/actions-runner/lmdj"}).decode()
        # A worker of another runner on this host is not this service's job.
        self.probes.rows = [(90, 50.0, "/Users/x/actions-runner/other/bin/Runner.Worker spawnclient 1 2")]
        self.assertEqual(check_runner(self.probes).status, "ok")
        self.probes.rows = [(90, 50.0, "/Users/x/actions-runner/lmdj/bin/Runner.Worker spawnclient 1 2")]
        busy = check_runner(self.probes)
        self.assertFails(busy, detail="executing a CI job", remedy=f"launchctl bootout gui/$(id -u)/{label}")
        # When prepare runs next, a loaded runner must be paused even if idle.
        self.probes.rows = []
        paused = check_runner(self.probes, require_paused=True)
        self.assertFails(paused, detail="is loaded; prepare refuses", remedy=f"launchctl bootout gui/$(id -u)/{label}")
        self.probes.commands[("launchctl", "list")] = (0, "123\t0\tcom.apple.x\n", "")
        self.assertEqual(check_runner(self.probes, require_paused=True).status, "ok")
        self.probes.commands[("launchctl", "list")] = (0, f"123\t0\tcom.apple.x\n77\t0\t{label}\n", "")
        # An agent without WorkingDirectory is located by its program's directory.
        self.probes.files[str(self.probes.home / "Library/LaunchAgents" / f"{label}.plist")] = plistlib.dumps(
            {"Label": label, "ProgramArguments": ["/Users/x/actions-runner/lmdj/runsvc.sh"]}).decode()
        self.probes.rows = [(90, 50.0, "/Users/x/actions-runner/other/bin/Runner.Worker spawnclient 1 2")]
        self.assertEqual(check_runner(self.probes).status, "ok")
        self.probes.rows = [(90, 50.0, "/Users/x/actions-runner/lmdj/bin/Runner.Worker spawnclient 1 2")]
        self.assertEqual(check_runner(self.probes).status, "fail")
        # Without a readable agent definition a running worker cannot be
        # attributed: the failure says so and names every service to pause.
        del self.probes.files[str(self.probes.home / "Library/LaunchAgents" / f"{label}.plist")]
        self.probes.rows = [(90, 50.0, "/Users/x/actions-runner/other/bin/Runner.Worker spawnclient 1 2")]
        unattributed = check_runner(self.probes)
        self.assertFails(unattributed, detail="launch agent is unreadable",
                         remedy=f"launchctl bootout gui/$(id -u)/{label}")
        self.probes.rows = []
        self.assertEqual(check_runner(self.probes).status, "ok")

    def test_every_loaded_runner_service_is_inspected(self):
        import plistlib
        first, second = "actions.runner.endaye-lmdj.endaye-mbp-m1", "actions.runner.other.second"
        self.probes.commands[("launchctl", "list")] = (0, f"77\t0\t{first}\n78\t0\t{second}\n", "")
        for label, workdir in ((first, "/Users/x/actions-runner/lmdj"), (second, "/Users/x/actions-runner/second")):
            self.probes.files[str(self.probes.home / "Library/LaunchAgents" / f"{label}.plist")] = plistlib.dumps(
                {"Label": label, "WorkingDirectory": workdir}).decode()
        idle = check_runner(self.probes)
        self.assertEqual(idle.status, "ok")
        self.assertIn(f"launchctl bootout gui/$(id -u)/{first}", idle.detail)
        self.assertIn(f"launchctl bootout gui/$(id -u)/{second}", idle.detail)
        # A job under the second service is reported against that service.
        self.probes.rows = [(90, 50.0, "/Users/x/actions-runner/second/bin/Runner.Worker spawnclient 1 2")]
        busy = check_runner(self.probes)
        self.assertFails(busy, detail=f"{second} is executing", remedy=f"launchctl bootout gui/$(id -u)/{second}")

    # aggregate
    def test_run_doctor_reports_every_check_in_a_fixed_order_and_fails_closed(self):
        self.probes.install_emsdk(self.sdk)
        self.probes.answer_key(PRODUCT)
        self.probes.answer_key(CHECKSUM, homedir=str(self.probes.home / doctor.CHECKSUM_KEYRING))
        self.probes.environ["GITHUB_TOKEN"] = "x"
        self.probes.commands[("launchctl", "list")] = (0, "", "")
        self.probes.commands[("mdutil", "-s", "/")] = (0, "/:\n\tIndexing enabled. \n", "")
        checks = run_doctor(self.root, product_fingerprint=PRODUCT, checksum_fingerprint=CHECKSUM,
                            journal_root=self.root / "journal", probes=self.probes)
        self.assertEqual([c.name for c in checks],
                         ["emsdk", "signing key (product)", "signing key (checksum)", "gh auth",
                          "journal lock", "release freeze", "release processes", "disk space",
                          "host load", "fseventsd", "spotlight", "m1 runner"])
        self.assertTrue(doctor_passed(checks))
        self.assertIn("release doctor: all checks passed", format_doctor(checks))
        self.probes.commands[("launchctl", "list")] = (0, "77\t0\tactions.runner.x.y\n", "")
        self.assertTrue(doctor_passed(run_doctor(
            self.root, product_fingerprint=PRODUCT, checksum_fingerprint=CHECKSUM,
            journal_root=self.root / "journal", probes=self.probes)))
        self.assertFalse(doctor_passed(run_doctor(
            self.root, product_fingerprint=PRODUCT, checksum_fingerprint=CHECKSUM,
            journal_root=self.root / "journal", probes=self.probes, require_paused_runner=True)))
        self.probes.commands[("launchctl", "list")] = (0, "", "")
        self.probes.lock = "held"
        checks = run_doctor(self.root, product_fingerprint=PRODUCT, checksum_fingerprint=CHECKSUM,
                            journal_root=self.root / "journal", probes=self.probes)
        self.assertFalse(doctor_passed(checks))
        report = format_doctor(checks)
        self.assertIn("[fail] journal lock:", report)
        self.assertIn("  remedy: wait for the running", report)
        self.assertIn("release doctor: 1 check(s) failed", report)

    def test_a_failed_check_must_carry_a_remedy(self):
        with self.assertRaises(ValueError):
            Check("x", "fail", "broken")
        with self.assertRaises(ValueError):
            Check("x", "broken", "")


class ReleaseFreezeCheckTest(unittest.TestCase):
    """The doctor reports who holds the release freeze and refuses a stale one."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.journal = self.root / "journal"
        self.journal.mkdir()
        self.probes = Probes(self.root)
        self.command = ("gh", "variable", "get", "LMDJ_RELEASE_FREEZE", "--repo", "endaye/lmdj")

    def check(self):
        return doctor.check_release_freeze(self.probes, repository="endaye/lmdj", journal_root=self.journal)

    def test_no_freeze_is_ok(self):
        self.probes.commands[self.command] = (1, "", "variable not found: LMDJ_RELEASE_FREEZE")
        self.assertEqual(self.check().status, "ok")

    def test_a_freeze_held_by_an_active_request_is_ok(self):
        request = "release-" + "1" * 16
        (self.journal / f"{request}.json").write_text("{}")
        self.probes.commands[self.command] = (0, request + "\n", "")
        check = self.check()
        self.assertEqual(check.status, "ok")
        self.assertIn(request, check.detail)

    def test_a_stale_or_unknown_freeze_fails_with_the_clearing_remedy(self):
        request = "release-" + "1" * 16
        (self.journal / f"{request}.json").write_text("{}")
        (self.journal / f"{request}.retired").write_text("{}")
        for value in (request, "release-" + "2" * 16, "garbage"):
            with self.subTest(value=value):
                self.probes.commands[self.command] = (0, value + "\n", "")
                check = self.check()
                self.assertEqual(check.status, "fail")
                self.assertIn("gh variable delete LMDJ_RELEASE_FREEZE", check.remedy)
                self.assertIn("retire", check.remedy)

    def test_an_unreadable_variable_api_fails_closed(self):
        self.probes.commands[self.command] = (1, "", "HTTP 502")
        check = self.check()
        self.assertEqual(check.status, "fail")
        self.assertIn("cannot read", check.detail)

    def test_run_doctor_includes_the_freeze_check(self):
        self.probes.commands[self.command] = (1, "", "variable not found")
        checks = run_doctor(self.root, product_fingerprint=PRODUCT, checksum_fingerprint=CHECKSUM,
                            journal_root=self.journal, probes=self.probes, repository="endaye/lmdj")
        self.assertIn("release freeze", [check.name for check in checks])


class HostProbesTest(unittest.TestCase):
    def test_lock_state_reflects_a_held_flock_a_missing_and_an_unopenable_file(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "writer.lock"
            probes = HostProbes()
            self.assertEqual(probes.lock_state(lock), "free")
            lock.write_bytes(b"")
            self.assertEqual(probes.lock_state(lock), "free")
            # A lock file this account may only read is probed, not reported held.
            lock.chmod(0o400)
            self.assertEqual(probes.lock_state(lock), "free")
            lock.chmod(0o600)
            fd = os.open(lock, os.O_RDWR)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertEqual(probes.lock_state(lock), "held")
            finally:
                os.close(fd)
            self.assertEqual(probes.lock_state(lock), "free")
            # A symlink where the lock should be cannot be opened: unreadable, not held.
            lock.unlink()
            lock.symlink_to(Path(directory) / "elsewhere")
            self.assertTrue(probes.lock_state(lock).startswith("unreadable:"))

    def test_ancestors_walks_the_parent_chain_and_excludes_init(self):
        class Fake(HostProbes):
            parents = {100: 50, 50: 7, 7: 1}

            def run(self, argv, *, env=None):
                return 0, f"{self.parents.get(int(argv[-1]), 0)}\n", ""
        probes = Fake()
        probes.pid = 100
        self.assertEqual(probes.ancestors(), {50, 7})

    def test_processes_parses_ps_rows_and_tolerates_a_failed_ps(self):
        class Fake(HostProbes):
            def run(self, argv, *, env=None):
                return 0, "  12  0.5 /bin/a b c\n 13 bad x\n 14 100.0 python3\n", ""
        self.assertEqual(Fake().processes(), [(12, 0.5, "/bin/a b c"), (14, 100.0, "python3")])

        class Failing(HostProbes):
            def run(self, argv, *, env=None):
                return 1, "", "ps failed"
        self.assertEqual(Failing().processes(), [])


if __name__ == "__main__":
    unittest.main()
