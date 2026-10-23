"""Read-only host preflight for the release entry (`scripts/release.sh doctor`).

Every failure of 2.0.122.0's `prepare` and `resume` rounds that was not a
product defect was a host condition the tool could have named before starting:
the pinned emsdk deleted by a cleanup, a signing key in the wrong keyring, a
stale `gh` login, a resume started while another driver held the journal,
a workstation at load 35 with `fseventsd` pegged, the M1 runner executing a
candidate batch on the same cores (#2422 items 5 and 7). `run_doctor` reads
those facts — it executes no build, writes nothing, and holds no lock beyond
a non-blocking probe — and reports each as `ok`, `fail` with why and remedy,
or `skip` where the check does not apply to this platform. `run`, `resume`
and `prepare` refuse to start while any check fails.

Probes are injected (`HostProbes`) so every check is testable without the
host; the production probes are plain `os`/`subprocess` reads.
"""

from __future__ import annotations

from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_FINGERPRINT = re.compile(r"[0-9A-F]{40}\Z")
EMSCRIPTEN_LOCK = Path("tools/web-runtime/emscripten.lock.json")
DEFAULT_EMSDK = Path("build/toolchains/emsdk")
CHECKSUM_KEYRING = ".gnupg-lmdj-release"
RUNNER_LABEL_PREFIX = "actions.runner."
MINIMUM_FREE_BYTES = 20 * 1024 ** 3
FSEVENTSD_CPU_LIMIT = 50.0
SPOTLIGHT_CPU_LIMIT = 30.0
_PROBE_TIMEOUT = 20


@dataclass(frozen=True)
class Check:
    name: str
    status: str  # ok | fail | skip
    detail: str
    remedy: str = ""

    def __post_init__(self):
        if self.status not in ("ok", "fail", "skip"):
            raise ValueError("doctor check status is invalid")
        if self.status == "fail" and not self.remedy:
            raise ValueError("a failed doctor check must name its remedy")


class HostProbes:
    """The production reads. Every method is side-effect free."""

    platform = sys.platform

    def __init__(self):
        self.environ = dict(os.environ)
        self.pid = os.getpid()
        self.home = Path.home()

    def is_dir(self, path):
        return Path(path).is_dir()

    def read_text(self, path):
        return Path(path).read_text(encoding="utf-8")

    def run(self, argv, *, env=None):
        try:
            completed = subprocess.run(
                [str(part) for part in argv], capture_output=True, text=True,
                timeout=_PROBE_TIMEOUT, check=False,
                env=None if env is None else {**os.environ, **env})
        except (OSError, subprocess.SubprocessError) as error:
            return 127, "", str(error)
        return completed.returncode, completed.stdout, completed.stderr

    def disk_free(self, path):
        return shutil.disk_usage(path).free

    def loadavg(self):
        return os.getloadavg()[0]

    def cpu_count(self):
        return os.cpu_count() or 1

    def processes(self):
        """[(pid, cpu_percent, command)] for every process the account can see."""
        code, stdout, _ = self.run(["ps", "-Ao", "pid=,%cpu=,command="])
        rows = []
        if code != 0:
            return rows
        for line in stdout.splitlines():
            parts = line.strip().split(None, 2)
            if len(parts) < 3:
                continue
            try:
                rows.append((int(parts[0]), float(parts[1]), parts[2]))
            except ValueError:
                continue
        return rows

    def ancestors(self):
        """The pids of this process's ancestors (a wrapper shell is not a second driver)."""
        found, pid = set(), self.pid
        for _ in range(64):
            code, stdout, _ = self.run(["ps", "-o", "ppid=", "-p", str(pid)])
            try:
                parent = int(stdout.strip()) if code == 0 else 0
            except ValueError:
                break
            if parent <= 1 or parent in found:
                break
            found.add(parent)
            pid = parent
        return found

    def lock_state(self, path):
        """"free", "held", or "unreadable: <reason>" for the journal writer lock.

        Opened read-only: flock needs no write access, so a lock file another
        account owns is probed for a holder. A file that cannot be opened at
        all (permissions, a symlink in place of the lock) is reported as
        unreadable, which is a different defect from a held lock.
        """
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return "free"
        except OSError as error:
            return f"unreadable: {error.strerror or type(error).__name__}"
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return "held"
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
            return "free"
        finally:
            os.close(fd)


def _gib(value):
    return f"{value / 1024 ** 3:.1f} GiB"


# -- checks -----------------------------------------------------------------


def check_emsdk(probes, root):
    root = Path(root)
    try:
        lock = json.loads(probes.read_text(root / EMSCRIPTEN_LOCK))
        tag, revision = lock["emsdk_tag"], lock["emsdk_revision"]
        releases_revision = lock["emscripten_releases_revision"]
    except (OSError, ValueError, KeyError, TypeError):
        return Check("emsdk", "fail", f"the pinned lock {EMSCRIPTEN_LOCK} is unreadable",
                     "restore tools/web-runtime/emscripten.lock.json from main")
    configured = probes.environ.get("EMSDK", "").strip()
    sdk = Path(configured).expanduser() if configured else root / DEFAULT_EMSDK
    install = (f"git clone https://github.com/emscripten-core/emsdk {sdk} && "
               f"git -C {sdk} checkout {revision} && {sdk}/emsdk install {tag} && "
               f"{sdk}/emsdk activate {tag}; then export EMSDK={sdk}. Never delete "
               "build/toolchains: it is release-owned (#2422 item 6)")
    if not probes.is_dir(sdk):
        return Check("emsdk", "fail", f"no emsdk at {sdk} (EMSDK "
                     f"{'set' if configured else 'unset, default path'})", install)
    code, head, _ = probes.run(["git", "-C", sdk, "rev-parse", "HEAD"])
    head = head.strip()
    if code != 0 or _SHA.fullmatch(head) is None:
        return Check("emsdk", "fail", f"{sdk} is not a Git checkout of emsdk", install)
    if head != revision:
        return Check("emsdk", "fail", f"emsdk at {sdk} is at {head}, the lock pins {revision}",
                     f"git -C {sdk} checkout {revision} && {sdk}/emsdk install {tag} && "
                     f"{sdk}/emsdk activate {tag}")
    try:
        releases = json.loads(probes.read_text(sdk / "emscripten-releases-tags.json"))
        mapped = releases["releases"][tag]
    except (OSError, ValueError, KeyError, TypeError):
        return Check("emsdk", "fail", f"{sdk} has no release mapping for {tag}", install)
    if mapped != releases_revision:
        return Check("emsdk", "fail", f"emsdk maps {tag} to {mapped}, the lock pins "
                     f"{releases_revision}", install)
    try:
        installed = probes.read_text(sdk / "upstream/emscripten/emscripten-version.txt").strip().strip('"')
    except OSError:
        return Check("emsdk", "fail", f"emsdk {tag} is not installed under {sdk}/upstream",
                     f"{sdk}/emsdk install {tag} && {sdk}/emsdk activate {tag}")
    if installed != tag:
        return Check("emsdk", "fail", f"installed emscripten is {installed}, the lock pins {tag}",
                     f"{sdk}/emsdk install {tag} && {sdk}/emsdk activate {tag}")
    return Check("emsdk", "ok", f"{sdk}: emsdk {tag} at {revision[:12]}")


def check_signing_keys(probes, *, product_fingerprint, checksum_fingerprint):
    """Both key roles must be usable from their own keyrings (pitfall
    release-signing-role-keyrings): product in the ambient keyring, checksum
    in the dedicated one. Never relocate a key to satisfy one lookup."""
    checks = []
    ambient = probes.environ.get("GNUPGHOME", "").strip() or str(probes.home / ".gnupg")
    dedicated = str(probes.home / CHECKSUM_KEYRING)
    for role, fingerprint, home, homedir in (
            ("product", product_fingerprint, ambient, None),
            ("checksum", checksum_fingerprint, dedicated, dedicated)):
        name = f"signing key ({role})"
        if type(fingerprint) is not str or _FINGERPRINT.fullmatch(fingerprint) is None:
            checks.append(Check(name, "fail", "the policy pins no valid fingerprint",
                                "restore tools/release/policy.json from main"))
            continue
        argv = ["gpg", "--batch", "--with-colons", "--list-secret-keys", fingerprint]
        if homedir is not None:
            argv[1:1] = ["--homedir", homedir]
        code, stdout, _ = probes.run(argv)
        present = code == 0 and any(line.startswith("sec") for line in stdout.splitlines())
        if present:
            checks.append(Check(name, "ok", f"{fingerprint[-8:]} in {home}"))
        else:
            checks.append(Check(name, "fail",
                                f"secret key {fingerprint} is not in {home}",
                                f"import the {role} private key into {home} (the {role} role "
                                "resolves only that keyring); do not move the other role's key; "
                                "see .agents/pitfalls/release-signing-role-keyrings.md"))
    return checks


def check_github_auth(probes):
    token = probes.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        return Check("gh auth", "ok", "GITHUB_TOKEN is set")
    code, stdout, _ = probes.run(["gh", "auth", "token"])
    if code == 0 and stdout.strip():
        return Check("gh auth", "ok", "gh is logged in (token available)")
    return Check("gh auth", "fail", "no GITHUB_TOKEN and `gh auth token` yields nothing",
                 "run `gh auth login`, or export GITHUB_TOKEN=\"$(gh auth token)\" in this shell")


def check_journal_lock(probes, journal_root):
    lock = Path(journal_root) / "writer.lock"
    state = probes.lock_state(lock)
    if state == "free":
        return Check("journal lock", "ok", "writer.lock is free")
    if state == "held":
        return Check("journal lock", "fail", f"{lock} is held by another writer",
                     "wait for the running run/resume/retire to finish (see the release "
                     "processes check); never delete writer.lock or the journal")
    return Check("journal lock", "fail", f"{lock} cannot be opened ({state})",
                 "the journal must be a private directory owned by this account with "
                 "writer.lock a regular 0600 file; fix its ownership and mode (chown/chmod), "
                 "never delete or replace it")


FREEZE_VARIABLE = "LMDJ_RELEASE_FREEZE"
_REQUEST_ID = re.compile(r"release-[0-9a-f]{16}\Z")


def check_release_freeze(probes, *, repository, journal_root):
    """Who holds the release freeze. An active request may; a retired or
    unknown one is a stale freeze that blocks every control-plane merge for
    nothing, so it fails with the clearing remedy (#2422 item 10)."""
    if not repository:
        return Check("release freeze", "skip", "repository unknown; the policy names it in production")
    code, stdout, stderr = probes.run(["gh", "variable", "get", FREEZE_VARIABLE, "--repo", repository])
    if code != 0:
        if "not found" in (stderr + stdout).lower():
            return Check("release freeze", "ok", f"{FREEZE_VARIABLE} is not set: no release request holds the freeze")
        return Check("release freeze", "fail", f"cannot read {FREEZE_VARIABLE}: {(stderr or stdout).strip()[:200]}",
                     "authenticate gh (`gh auth login`) with access to the repository's Actions variables and rerun")
    holder = stdout.strip()
    journal = Path(journal_root)
    if _REQUEST_ID.fullmatch(holder) and (journal / f"{holder}.json").is_file() \
            and not (journal / f"{holder}.retired").exists():
        return Check("release freeze", "ok", f"held by active request {holder}: CI and release-tool "
                     "control-plane merges are frozen until it completes or is retired")
    return Check("release freeze", "fail",
                 f"{FREEZE_VARIABLE} names {holder!r}, which is not an active request of this journal "
                 "(retired, unknown or malformed)",
                 f"if no release is running anywhere, clear it with `gh variable delete {FREEZE_VARIABLE} "
                 f"--repo {repository}`; a request that is still active elsewhere must finish or be "
                 "retired first (`scripts/release.sh status`, `scripts/release.sh retire`)")


# The release.sh commands that drive or mutate release state; a second one of
# these is a second driver. Read-only commands (status, audit, doctor,
# publication-record, publication-patch, verify-*) and the object-store
# hydrate may run beside a driver.
DRIVING_COMMANDS = frozenset({"run", "resume", "retire", "prepare", "push-tag",
                              "create-draft", "publish-draft", "promote",
                              "editorial", "rehearsal"})


def _release_cli_arguments(command):
    """The arguments after the release CLI program when `command` runs it, else None.

    Only an interpreter invocation counts — `python3 [-opts] …/tools/release/cli.py`
    or `python3 [-opts] -m tools.release.cli` — so a shell whose command string
    merely mentions the path (an editor, a heredoc, this doctor's own wrapper)
    is not a release driver.
    """
    tokens = command.split()
    for index, token in enumerate(tokens):
        if not Path(token).name.startswith("python"):
            continue
        rest = index + 1
        while rest < len(tokens) and tokens[rest].startswith("-") and tokens[rest] != "-m":
            rest += 1
        if rest < len(tokens) and tokens[rest].endswith("tools/release/cli.py"):
            return " ".join(tokens[rest + 1:])
        if rest + 1 < len(tokens) and tokens[rest] == "-m" and tokens[rest + 1] == "tools.release.cli":
            return " ".join(tokens[rest + 2:])
    return None


def _release_subcommand(arguments):
    """The release.sh subcommand in a cli.py argument string, or None."""
    tokens = arguments.split()
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--repo-root":
            index += 2
            continue
        if token.startswith("--repo-root="):
            index += 1
            continue
        return token if not token.startswith("-") else None
    return None


def check_release_processes(probes):
    # This process and the shells wrapping it (a `sh -c 'python3 cli.py run'`
    # parent repeats the driving command line) are the command being started,
    # not a second driver.
    own = {probes.pid} | set(probes.ancestors())
    others = []
    for pid, _, command in probes.processes():
        if pid in own:
            continue
        arguments = _release_cli_arguments(command)
        if arguments is not None and _release_subcommand(arguments) in DRIVING_COMMANDS:
            others.append((pid, arguments))
    if not others:
        return Check("release processes", "ok", "no other release.sh process")
    listed = ", ".join(f"{pid} ({arguments[:60]})" for pid, arguments in others[:5])
    return Check("release processes", "fail", f"another release.sh is running: {listed}",
                 "let it finish or stop it (kill <pid>) before starting a second driver; "
                 "two drivers on one journal are refused by the writer lock")


def check_disk(probes, root, minimum=MINIMUM_FREE_BYTES):
    try:
        free = probes.disk_free(root)
    except OSError:
        return Check("disk space", "fail", f"cannot read free space at {root}",
                     "check the volume that holds the repository")
    if free >= minimum:
        return Check("disk space", "ok", f"{_gib(free)} free")
    return Check("disk space", "fail", f"{_gib(free)} free, {_gib(minimum)} needed for two "
                 "clean Web Host builds and the Core package",
                 "free space: remove stale build/core and build/web trees of other worktrees, "
                 "old Playwright caches or Docker images; never remove build/toolchains or "
                 "build/release")


def check_load(probes):
    cpus = probes.cpu_count()
    load = probes.loadavg()
    if load <= cpus:
        return Check("host load", "ok", f"load {load:.1f} on {cpus} cpus")
    return Check("host load", "fail", f"load {load:.1f} exceeds {cpus} cpus; timing-sensitive "
                 "legs time out under this load (two prepare proofs did on 2.0.122.0)",
                 "stop heavy local work (proof lanes, builds, other agent sessions), pause the "
                 "M1 runner, and wait until the 1-minute load is below the cpu count")


def _program(command):
    """The program token of a ps command field; empty when the field is blank."""
    tokens = command.split()
    return tokens[0] if tokens else ""


def check_fseventsd(probes):
    if probes.platform != "darwin":
        return Check("fseventsd", "skip", "macOS only")
    cpu = max((cpu for _, cpu, command in probes.processes()
               if _program(command).endswith("/fseventsd")), default=0.0)
    if cpu <= FSEVENTSD_CPU_LIMIT:
        return Check("fseventsd", "ok", f"{cpu:.0f}% cpu")
    return Check("fseventsd", "fail", f"fseventsd is at {cpu:.0f}% cpu (it held a core for "
                 "17 days during 2.0.122.0)",
                 "restart it: sudo killall fseventsd (launchd respawns it); then rerun doctor")


def check_spotlight(probes, root):
    if probes.platform != "darwin":
        return Check("spotlight", "skip", "macOS only")
    cpu = sum(cpu for _, cpu, command in probes.processes()
              if _program(command).endswith(("/mds_stores", "/mds", "/mdworker_shared")))
    # mdutil answers for volumes, not folders: the repository's volume state
    # is reported; folder exclusions live in Spotlight Privacy and are not
    # readable here.
    code, stdout, _ = probes.run(["mdutil", "-s", "/"])
    state = ("volume " + " ".join(stdout.split()).replace("/: ", "").rstrip(".").lower()
             if code == 0 and stdout.strip() else "volume indexing state unknown")
    if cpu <= SPOTLIGHT_CPU_LIMIT:
        return Check("spotlight", "ok", f"{cpu:.0f}% cpu; {state}")
    return Check("spotlight", "fail", f"Spotlight is indexing at {cpu:.0f}% cpu; {state}",
                 "exclude the repository and the runner directory: System Settings → Siri & "
                 "Spotlight → Spotlight Privacy, add ~/Projects and ~/actions-runner "
                 "(or sudo mdutil -i off <volume> if the whole volume may stop indexing)")


def check_runner(probes, *, require_paused=False):
    """The runner shares the cores with `prepare`'s timing-sensitive legs.

    A running job always fails. An idle loaded service fails only when the
    command about to run is `prepare` (`require_paused`): a `run` or a
    `resume` waiting on the candidate batch needs the runner up, since that
    batch executes on it; the report then names the pause command for later.
    """
    if probes.platform != "darwin":
        return Check("m1 runner", "skip", "macOS only")
    code, stdout, _ = probes.run(["launchctl", "list"])
    labels = [line.split()[-1] for line in stdout.splitlines()
              if code == 0 and line.strip() and line.split()[-1].startswith(RUNNER_LABEL_PREFIX)]
    if not labels:
        return Check("m1 runner", "ok", "no actions runner service loaded (paused or not installed)")
    workers = [command for _, _, command in probes.processes() if "Runner.Worker" in command]
    idle = []
    for label in labels:
        pause = f"launchctl bootout gui/$(id -u)/{label}"
        resume = f"launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/{label}.plist"
        # A worker belongs to this service when it runs from the service's own
        # directory: the launch agent's WorkingDirectory, else the directory of
        # its program (runsvc.sh sits in the runner root). Without a readable
        # agent definition any worker counts, conservatively.
        workdir = None
        try:
            agent = plistlib.loads(probes.read_text(
                probes.home / "Library/LaunchAgents" / f"{label}.plist").encode("utf-8"))
            if isinstance(agent, dict):
                workdir = agent.get("WorkingDirectory")
                program = agent.get("ProgramArguments")
                if not isinstance(workdir, str) and isinstance(program, list) \
                        and program and isinstance(program[0], str):
                    workdir = str(Path(program[0]).parent)
                if not isinstance(workdir, str):
                    workdir = None
        except (OSError, ValueError, plistlib.InvalidFileException, UnicodeError):
            workdir = None
        if workdir is None and workers:
            return Check("m1 runner", "fail",
                         f"{label}'s launch agent is unreadable, so a running Runner.Worker "
                         "cannot be attributed to a service",
                         "wait for every runner job on this host to finish, or pause each "
                         "loaded runner service (" + "; ".join(
                             f"launchctl bootout gui/$(id -u)/{name}" for name in labels)
                         + "); then restore the agent definition under ~/Library/LaunchAgents")
        if workdir is not None and any(command.startswith(workdir.rstrip("/") + "/")
                                       for command in workers):
            return Check("m1 runner", "fail", f"{label} is executing a CI job on this host",
                         f"wait for the job, or pause the runner for the release: {pause}; "
                         f"resume it afterwards: {resume}")
        if require_paused:
            return Check("m1 runner", "fail", f"{label} is loaded; prepare refuses while a "
                         "runner can start a job on these cores",
                         f"pause it for the prepare: {pause}; resume it afterwards: {resume}")
        state = "loaded (agent definition unreadable), no worker running" if workdir is None \
            else "loaded, idle"
        idle.append(f"{label} {state}; prepare refuses while it is loaded, pause it then: "
                    f"{pause}; resume afterwards: {resume}")
    return Check("m1 runner", "ok", " | ".join(idle))


def run_doctor(root, *, product_fingerprint, checksum_fingerprint, journal_root, probes=None,
               require_paused_runner=False, repository=None):
    probes = HostProbes() if probes is None else probes
    root = Path(root)
    return [
        check_emsdk(probes, root),
        *check_signing_keys(probes, product_fingerprint=product_fingerprint,
                            checksum_fingerprint=checksum_fingerprint),
        check_github_auth(probes),
        check_journal_lock(probes, journal_root),
        check_release_freeze(probes, repository=repository, journal_root=journal_root),
        check_release_processes(probes),
        check_disk(probes, root),
        check_load(probes),
        check_fseventsd(probes),
        check_spotlight(probes, root),
        check_runner(probes, require_paused=require_paused_runner),
    ]


def doctor_passed(checks):
    return all(check.status != "fail" for check in checks)


def format_doctor(checks):
    lines = []
    for check in checks:
        lines.append(f"[{check.status}] {check.name}: {check.detail}")
        if check.status == "fail":
            lines.append(f"  remedy: {check.remedy}")
    failed = sum(1 for check in checks if check.status == "fail")
    lines.append("release doctor: " + ("all checks passed" if failed == 0
                                        else f"{failed} check(s) failed"))
    return "\n".join(lines) + "\n"
