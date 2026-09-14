#!/usr/bin/env python3
"""Read-only evidence probe for one explicitly selected CI host.

The probe never changes host state.  A missing capability or unreadable source
is reported as blocked/unavailable; only a readable mismatch with a repository
pin is a failed parity result.
"""

from __future__ import annotations

import argparse
import datetime as datetime_module
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time


HOSTS = {"netcup", "contabo"}
ROLES = {"ci-general", "ci-core", "ci-web-heavy"}
TOOLS = ("clang-22", "clang++-22", "llvm-cov-22", "ccache", "cmake", "ninja", "python3", "git-lfs")
KERNEL_KEYS = ("CONFIG_PARAVIRT_TIME_ACCOUNTING", "CONFIG_IRQ_TIME_ACCOUNTING")


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def run(*args: str) -> str | None:
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def load_json(path: Path) -> tuple[object | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, "missing"
    except (OSError, json.JSONDecodeError):
        return None, "malformed"


def read_service_unit(path: Path) -> str | None:
    """Derive the current process unit from its cgroup, never from a list scan."""
    text = read_text(path)
    if text is None:
        return None
    units = re.findall(r"(?:^|/)([^/\n]+\.service)(?:$|\n)", text)
    return units[-1] if units else None


def sanitizer_pin(path: Path) -> str | None:
    text = read_text(path)
    if text is None:
        return None
    match = re.search(r"^vm\.mmap_rnd_bits\s*=\s*([0-9]+)\s*$", text, re.MULTILINE)
    return match.group(1) if match else None


def mmap_observation(explicit_path: Path | None, proc_path: Path) -> tuple[str, str]:
    """Read the pinned ASLR setting from an explicit fixture or procfs."""
    source = explicit_path or proc_path
    text = read_text(source)
    value = text.strip() if text and text.strip() else "unavailable"
    return value, str(source)


def kernel_line(key: str) -> tuple[str, str]:
    for source in (Path(f"/boot/config-{platform.release()}"), Path("/proc/config.gz")):
        if not source.is_file() or not os.access(source, os.R_OK):
            continue
        if source.name == "config.gz":
            text = run("zcat", str(source))
        else:
            text = read_text(source)
        if text is None:
            continue
        for line in text.splitlines():
            if line.startswith(key + "=") or line == f"# {key} is not set":
                return line, str(source)
        return "absent from this config", str(source)
    return "unavailable", "unavailable"


def parse_cpu_fields(text: str | None) -> tuple[int, int, int] | None:
    """Parse exactly one complete aggregate cpu row through steal."""
    if not text:
        return None
    rows = [line.split() for line in text.splitlines() if line.startswith("cpu ")]
    if len(rows) != 1 or len(rows[0]) < 9:
        return None
    try:
        return tuple(int(value) for value in rows[0][6:9])  # irq, softirq, steal
    except ValueError:
        return None


def cpu_delta(before: tuple[int, int, int] | None, after: tuple[int, int, int] | None) -> dict[str, str]:
    if before is None or after is None:
        return {"status": "unavailable"}
    return {key: str(after[index] - before[index]) for index, key in enumerate(("irq", "softirq", "steal"))}


def markdown(data: dict) -> str:
    p = data["provenance"]
    lines = [
        f"## Host inventory: `{p['host']}` / `{p['role']}`",
        "",
        "| Provenance | Value |",
        "| --- | --- |",
    ]
    if data.get("status") == "blocked":
        lines.append(f"**blocked:** {data['reason']}")
        return "\n".join(lines) + "\n"
    for key in ("host", "role", "runner", "hostname", "observed_at_utc", "run_url", "run_attempt", "revision", "git_head", "workflow_sha", "service_unit"):
        lines.append(f"| {key} | `{p[key]}` |")
    lines += ["", "### Elastic controller parity"]
    config = data["controller_config"]
    if config["status"] == "match":
        lines.append(f"PASS: normalized config digest `{config['actual_digest']}` matches the repository pin.")
    elif config["status"] == "mismatch":
        lines.append(f"**mismatch:** host config digest `{config['actual_digest']}` differs from repository pin `{config['expected_digest']}`.")
    else:
        lines.append(f"blocked/unavailable: controller config is {config['status']}; parity is not claimed.")
    lines += ["", "### Sanitizer host parity"]
    sanitizer = data["sanitizer"]
    lines.append(f"| Setting | Observed | Repository pin | Source |")
    lines.append("| --- | --- | --- | --- |")
    lines.append(f"| `vm.mmap_rnd_bits` | `{sanitizer['observed']}` | `{sanitizer['expected']}` | `{sanitizer['source']}` |")
    if sanitizer["status"] == "mismatch":
        lines.append("**mismatch:** sanitizer ASLR setting differs from the repository pin.")
    elif sanitizer["status"] == "unavailable":
        lines.append("blocked/unavailable: sanitizer setting could not be read; readiness is not claimed.")
    lines += ["", "### Native Core toolchain", "", "| Tool | Present | Version | Path |", "| --- | --- | --- | --- |"]
    lines.extend(f"| `{row['tool']}` | {row['present']} | {row['version']} | `{row['path']}` |" for row in data["tools"])
    lines += ["", "### Host capacity", "", "| Property | Value |", "| --- | --- |"]
    lines.extend(f"| {key} | `{value}` |" for key, value in data["capacity"].items())
    lines += ["", "### Kernel accounting", "", "| Option | Reading | Source |", "| --- | --- | --- |"]
    lines.extend(f"| `{key}` | `{value}` | `{source}` |" for key, (value, source) in data["kernel"].items())
    lines += ["", "### Idle-host accounting", "", "| Counter | Delta (USER_HZ) |", "| --- | --- |"]
    lines.extend(f"| {key} | `{value}` |" for key, value in data["accounting"].items())
    lines.append("")
    lines.append("Missing capabilities and inaccessible sources are findings, not readiness claims; this probe is read-only.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True, choices=sorted(HOSTS))
    parser.add_argument("--role", required=True, choices=sorted(ROLES))
    parser.add_argument("--expected-config", type=Path, required=True)
    parser.add_argument("--actual-config", type=Path, default=Path("/etc/lmdj/elastic-runner.json"))
    parser.add_argument("--sanitizer-script", type=Path, required=True)
    parser.add_argument("--cgroup-file", type=Path, default=Path("/proc/self/cgroup"))
    parser.add_argument("--mmap-file", type=Path)
    parser.add_argument("--mmap-proc-file", type=Path, default=Path("/proc/sys/vm/mmap_rnd_bits"))
    parser.add_argument("--accounting-seconds", type=int, default=0)
    parser.add_argument("--proc-stat-file", type=Path, default=Path("/proc/stat"))
    parser.add_argument("--tool-root", type=Path)
    parser.add_argument("--free-file", type=Path)
    parser.add_argument("--df-file", type=Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args()

    if args.host == "contabo" and args.role != "ci-general":
        blocked = {"status": "blocked", "reason": f"role {args.role} is not provided by explicitly selected host {args.host}"}
        output = json.dumps(blocked, sort_keys=True) + "\n" if args.format == "json" else markdown({"status": "blocked", "reason": blocked["reason"], "provenance": {"host": args.host, "role": args.role}})
        sys.stdout.write(output)
        return 78

    expected, expected_error = load_json(args.expected_config)
    actual, actual_error = load_json(args.actual_config)
    expected_digest = digest(expected) if expected_error is None else None
    actual_digest = digest(actual) if actual_error is None else None
    if expected_error or actual_error:
        config_status = actual_error or expected_error or "unavailable"
    elif expected == actual:
        config_status = "match"
    else:
        config_status = "mismatch"

    expected_pin = sanitizer_pin(args.sanitizer_script)
    observed, observation_source = mmap_observation(args.mmap_file, args.mmap_proc_file)
    sanitizer_status = "unavailable" if expected_pin is None or observed == "unavailable" else ("match" if observed == expected_pin else "mismatch")
    service_unit = read_service_unit(args.cgroup_file) or "unavailable"
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
    repository = os.environ.get("GITHUB_REPOSITORY", "unavailable")
    run_id = os.environ.get("GITHUB_RUN_ID", "unavailable")
    run_url = f"{server}/{repository}/actions/runs/{run_id}" if run_id != "unavailable" else "unavailable"
    free_output = (read_text(args.free_file) if args.free_file else run("free", "-h")) or ""
    free_lines = free_output.splitlines()
    memory = free_lines[1].split()[1] if len(free_lines) > 1 and len(free_lines[1].split()) > 1 else "unavailable"
    df_output = (read_text(args.df_file) if args.df_file else run("df", "-h", ".")) or ""
    df_lines = df_output.splitlines()
    workspace_free = df_lines[1].split()[3] if len(df_lines) > 1 and len(df_lines[1].split()) > 3 else "unavailable"
    data = {
        "provenance": {
            "host": args.host,
            "role": args.role,
            "runner": os.environ.get("RUNNER_NAME", "unavailable"),
            "hostname": run("hostname") or "unavailable",
            "observed_at_utc": datetime_module.datetime.now(datetime_module.timezone.utc).isoformat(),
            "run_url": run_url,
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", "unavailable"),
            "revision": os.environ.get("GITHUB_SHA", "unavailable"),
            "git_head": run("git", "rev-parse", "HEAD") or "unavailable",
            "workflow_sha": os.environ.get("GITHUB_WORKFLOW_SHA", "unavailable"),
            "service_unit": service_unit,
        },
        "controller_config": {"status": config_status, "expected_digest": expected_digest, "actual_digest": actual_digest},
        "sanitizer": {"status": sanitizer_status, "expected": expected_pin or "unavailable", "observed": observed, "source": observation_source},
        "tools": [],
        "capacity": {
            "cores": run("nproc") or "unavailable",
            "memory": memory,
            "kernel": platform.release(),
            "distribution": next((line.split("=", 1)[1].strip('"') for line in (read_text(Path("/etc/os-release")) or "").splitlines() if line.startswith("PRETTY_NAME=")), "unavailable"),
            "workspace_free": workspace_free,
        },
        "kernel": {},
    }
    for tool in TOOLS:
        path = str(args.tool_root / tool) if args.tool_root and (args.tool_root / tool).is_file() else (None if args.tool_root else shutil.which(tool))
        version = run(path, "--version") if path else None
        data["tools"].append({"tool": tool, "present": "yes" if path else "**no**", "version": version.splitlines()[0][:60] if version else "—", "path": path or "—"})
    for key in KERNEL_KEYS:
        data["kernel"][key] = kernel_line(key)
    before = parse_cpu_fields(read_text(args.proc_stat_file))
    if args.accounting_seconds > 0:
        time.sleep(args.accounting_seconds)
    after = parse_cpu_fields(read_text(args.proc_stat_file))
    data["accounting"] = cpu_delta(before, after)
    output = json.dumps(data, sort_keys=True) + "\n" if args.format == "json" else markdown(data)
    sys.stdout.write(output)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and args.format == "markdown":
        try:
            with open(summary, "a", encoding="utf-8") as stream:
                stream.write(output)
        except OSError:
            pass
    return 1 if config_status == "mismatch" or sanitizer_status == "mismatch" else 0


if __name__ == "__main__":
    sys.exit(main())
