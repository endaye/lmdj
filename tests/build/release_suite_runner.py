#!/usr/bin/env python3
"""Run every `release_*_test.py` module across worker processes, failing closed on drift.

`python3 -m unittest discover -s tests/build -p 'release_*_test.py'` spends
its wall clock in real Git children, forks, GPG signatures and Host validator
interpreters: 74 modules, 1682 tests, 64 minutes serially on 2026-09-17. Each
module owns its temporary repositories, journals and loopback ports, so modules
can run concurrently; classes inside one module may share a seeded filesystem,
so a module never splits across workers. The parent discovers every test id
first, hands whole modules to workers, and compares the union of the workers'
executed ids with the discovered set: a silently skipped module is a failure,
not a faster pass.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
START = ROOT / "tests" / "build"
PATTERN = "release_*_test.py"
SLOWEST = 15
# A worker that outlives this is a hang the parent reports itself, with every
# other shard's result, instead of leaving the job limit to kill all of them.
WORKER_TIMEOUT = 1500.0
POLL = 0.5


def discover(start: Path = START, pattern: str = PATTERN) -> dict[str, list[str]]:
    """Return {module: sorted test ids} for every module the pattern names."""
    loader = unittest.TestLoader()
    suite = loader.discover(str(start), pattern=pattern, top_level_dir=str(start))
    if loader.errors:
        raise SystemExit("test discovery failed:\n" + "\n".join(loader.errors))
    modules: dict[str, list[str]] = {}

    def walk(item: object) -> None:
        if isinstance(item, unittest.TestSuite):
            for child in item:
                walk(child)
            return
        case = item
        test_id = case.id()
        modules.setdefault(test_id.split(".", 1)[0], []).append(test_id)

    walk(suite)
    if not modules:
        raise SystemExit("test discovery found no tests")
    for module, ids in modules.items():
        if len(set(ids)) != len(ids):
            raise SystemExit(f"test discovery produced duplicate test ids in {module}")
        ids.sort()
    return dict(sorted(modules.items()))


def partition(modules: dict[str, list[str]], shards: int) -> list[list[str]]:
    """Whole modules into `shards` buckets; largest first onto the lightest bucket.

    Test count is the only weight available before a run and a poor proxy
    for a module's real duration, but the assignment is deterministic for a
    given tree, which matters more than balance for reproducing a failure.
    """
    buckets: list[list[str]] = [[] for _ in range(shards)]
    weights = [0] * shards
    for module in sorted(modules, key=lambda name: (-len(modules[name]), name)):
        index = min(range(shards), key=lambda i: (weights[i], i))
        buckets[index].append(module)
        weights[index] += len(modules[module])
    return [bucket for bucket in buckets if bucket]


def resolve_shard_count(requested: int | None) -> int:
    if requested is None:
        return max(1, min(4, os.cpu_count() or 1))
    if requested < 1:
        raise SystemExit("--shards must be a positive integer")
    return requested


class _RecordingResult(unittest.TextTestResult):
    """Text output for the log plus the exact executed ids and their durations.

    The durations are the only per-test timing the lane produces: the ctest
    registrations of these modules carry tier budgets but no Core lane runs
    them, so a budget question (#1530) is answered from this report.
    """

    def __init__(self, *arguments, **keywords):
        super().__init__(*arguments, **keywords)
        self.executed: list[str] = []
        self.durations: dict[str, float] = {}
        self._started = 0.0

    def startTest(self, test):  # noqa: N802 - unittest API
        super().startTest(test)
        self.executed.append(test.id())
        self._started = time.monotonic()

    def stopTest(self, test):  # noqa: N802 - unittest API
        self.durations[test.id()] = time.monotonic() - self._started
        super().stopTest(test)


def run_worker(report: Path, modules: list[str], start: Path) -> int:
    """Run the named modules in this process and write the executed ids."""
    sys.path.insert(0, str(start))
    loader = unittest.TestLoader()
    suite = unittest.TestSuite(loader.loadTestsFromName(module) for module in modules)
    if loader.errors:
        report.write_text(json.dumps({"executed": [], "errors": loader.errors}))
        sys.stderr.write("\n".join(loader.errors) + "\n")
        return 1
    runner = unittest.TextTestRunner(stream=sys.stderr, verbosity=1, resultclass=_RecordingResult)
    result = runner.run(suite)
    report.write_text(json.dumps({"executed": result.executed, "errors": [],
                                  "durations": result.durations,
                                  "successful": result.wasSuccessful()}))
    return 0 if result.wasSuccessful() else 1


def _kill(child: subprocess.Popen) -> None:
    """Kill the worker's whole session; a group already gone is not an error."""
    for target in (lambda: os.killpg(child.pid, signal.SIGKILL), child.kill):
        try:
            target()
        except (ProcessLookupError, PermissionError):
            continue
        return


def _read_report(report: Path) -> dict:
    """A missing or truncated report is a failed shard, never a parent crash."""
    try:
        payload = json.loads(report.read_text())
    except (OSError, ValueError) as error:
        return {"executed": [], "errors": [f"worker report unreadable: {error}"], "successful": False}
    if type(payload) is not dict or type(payload.get("executed")) is not list:
        return {"executed": [], "errors": ["worker report malformed"], "successful": False}
    return payload


def run_sharded(shards: int, start: Path = START, pattern: str = PATTERN,
                worker_timeout: float = WORKER_TIMEOUT) -> int:
    modules = discover(start, pattern)
    discovered = sorted(test_id for ids in modules.values() for test_id in ids)
    groups = partition(modules, shards)
    started = time.monotonic()
    executed: list[str] = []
    durations: dict[str, float] = {}
    failed: list[str] = []
    self_path = str(Path(__file__).resolve())
    with tempfile.TemporaryDirectory(prefix="lmdj-release-suite-shards-") as directory:
        workers = []
        try:
            for index, group in enumerate(groups):
                report = Path(directory) / f"shard-{index}.json"
                log = open(Path(directory) / f"shard-{index}.log", "w+b")
                child = subprocess.Popen(
                    [sys.executable, self_path, "--worker", str(report), "--start", str(start), *group],
                    cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                workers.append((f"shard {index} of {len(groups)}", group, report, log, child))
            # Poll every child so one slow shard never delays another's report,
            # and a shard past the worker deadline is killed and reported here.
            deadline = time.monotonic() + worker_timeout
            hung: set[str] = set()
            while any(child.poll() is None for *_, child in workers):
                if time.monotonic() >= deadline:
                    for label, *_, child in workers:
                        if child.poll() is None:
                            hung.add(label)
                            _kill(child)
                    break
                time.sleep(POLL)
        finally:
            for *_, child in workers:
                if child.poll() is None:
                    _kill(child)
        for label, group, report, log, child in workers:
            status = child.wait()
            log.seek(0)
            output = log.read().decode("utf-8", "replace")
            log.close()
            payload = _read_report(report)
            executed.extend(payload.get("executed", []))
            durations.update(payload.get("durations", {}))
            if label in hung or status != 0 or payload.get("errors") or not payload.get("successful", False):
                failed.append(label)
                reason = f"hung past {worker_timeout:.0f}s and was killed" if label in hung else f"exit {status}"
                errors = "".join(f"{line}\n" for line in payload.get("errors", []))
                sys.stderr.write(f"\n===== {label} FAILED ({reason}): {' '.join(group)} =====\n{errors}{output}\n")
            else:
                summary = [line for line in output.splitlines() if line.startswith("Ran ")]
                sys.stderr.write(f"{label}: {' '.join(summary)} — {len(group)} modules\n")
    duration = time.monotonic() - started
    missing = sorted(set(discovered) - set(executed))
    unexpected = sorted(set(executed) - set(discovered))
    status = 1 if failed else 0
    if len(executed) != len(discovered) or missing or unexpected:
        status = 1
        sys.stderr.write(f"\nshard accounting failed: discovered {len(discovered)} tests, executed {len(executed)}\n")
        if missing:
            sys.stderr.write("never executed: " + ", ".join(missing[:20]) + ("..." if len(missing) > 20 else "") + "\n")
        if unexpected:
            sys.stderr.write("unexpected: " + ", ".join(unexpected[:20]) + "\n")
    slowest = sorted(durations.items(), key=lambda item: -item[1])[:SLOWEST]
    if slowest:
        sys.stderr.write(f"\nslowest {len(slowest)} tests:\n" + "".join(
            f"  {seconds:8.1f}s  {test_id}\n" for test_id, seconds in slowest))
    sys.stderr.write(
        f"\nRan {len(executed)} of {len(discovered)} discovered tests from {len(modules)} modules "
        f"across {len(groups)} shards in {duration:.3f}s: {'FAILED' if status else 'OK'}\n")
    if failed:
        sys.stderr.write("failed workers: " + ", ".join(failed) + "\n")
    sys.stderr.flush()
    return status


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--shards", type=int, default=None,
                        help="worker processes (default: min(4, cpu count))")
    parser.add_argument("--worker-timeout", type=float, default=WORKER_TIMEOUT,
                        help="seconds a worker may run before it is killed and reported")
    parser.add_argument("--start", default=str(START), help=argparse.SUPPRESS)
    parser.add_argument("--pattern", default=PATTERN, help=argparse.SUPPRESS)
    parser.add_argument("--worker", default=None, metavar="REPORT", help=argparse.SUPPRESS)
    parser.add_argument("modules", nargs="*", help=argparse.SUPPRESS)
    options = parser.parse_args(argv[1:])
    if options.worker is not None:
        return run_worker(Path(options.worker), options.modules, Path(options.start))
    if options.modules:
        parser.error("modules are only accepted in --worker mode")
    if options.worker_timeout <= 0:
        parser.error("--worker-timeout must be positive")
    return run_sharded(resolve_shard_count(options.shards), Path(options.start), options.pattern,
                       options.worker_timeout)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
