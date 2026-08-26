#!/usr/bin/env python3
"""Resource-guarded elastic capacity controller for trusted Linux runners.

Host-local, systemd-timer driven, no GitHub PAT. The decision core is pure:
``decide()`` consumes a Config, a HostObservation, and a ControllerState and
returns exactly one Decision plus the successor state, so every rule required
by issue #327 is deterministically testable without a host.

Capacity rules
--------------
- Scale out one stopped elastic service at a time, only when every active
  service has been busy for consecutive observations, the cooldown has
  elapsed, the operational ceiling permits, no ci-core service is running a
  job, and the CPU, slice-memory, system-memory, and I/O guards all admit one
  more worst-case job. Memory guards admit the *next* job, not the current
  state, and never assume swap relief.
- Scale in the highest-numbered idle elastic service after a sustained idle
  window; the adapter re-checks a grace window before stopping. A service
  with a live Runner.Worker is never stopped.
- Stopped elastic services heartbeat well inside GitHub's 14-day offline
  auto-removal window. A heartbeat that cannot reach the listener-ready state
  is a registration loss: it is reported and never silently retried.
- Invalid observations fail closed: capacity is preserved and the reason is
  logged.
- A reboot restores baseline capacity because only baseline services are
  enabled; this controller decides any later expansion.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

WORKER_PROCESS = "Runner.Worker"
LISTENER_READY_MARKER = "Listening for Jobs"
JOB_START_MARKER = "Running job:"
REGISTRATION_LOSS_TAG = "LMDJ-ELASTIC-REGISTRATION-LOSS"


class ConfigError(ValueError):
    """The controller configuration violates the issue #327 contract."""


@dataclasses.dataclass(frozen=True)
class ServiceSpec:
    name: str
    user: str
    kind: str  # "baseline" | "elastic"
    index: int
    roles: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class Config:
    host: str
    slice_name: str
    services: tuple[ServiceSpec, ...]
    operational_ceiling: int
    busy_observations_required: int
    idle_observations_required: int
    cooldown_seconds: int
    grace_seconds: int
    heartbeat_interval_seconds: int
    heartbeat_timeout_seconds: int
    next_job_memory_bytes: int
    system_memory_reserve_bytes: int
    cpu_load_max_ratio: float
    io_pressure_max_pct: float
    core_job_names: tuple[str, ...]

    @property
    def baseline(self) -> tuple[ServiceSpec, ...]:
        return tuple(s for s in self.services if s.kind == "baseline")

    @property
    def elastic(self) -> tuple[ServiceSpec, ...]:
        return tuple(s for s in self.services if s.kind == "elastic")


@dataclasses.dataclass(frozen=True)
class ServiceObservation:
    active: bool
    has_worker: bool
    # For services carrying ci-core: whether the current job is a ci-core job.
    # None means unknown, and unknown is treated as core (fail closed), because
    # contabo baselines carry both ci-general and ci-core: suppressing on a
    # bare Runner.Worker would deadlock scale-out behind the all-busy trigger.
    core_job: Optional[bool] = None


@dataclasses.dataclass(frozen=True)
class HostObservation:
    now: float
    services: dict[str, ServiceObservation]
    cpu_count: int
    load1: float
    mem_available_bytes: int
    slice_memory_current_bytes: int
    slice_memory_max_bytes: int
    io_pressure_some_avg60: float
    swap_total_bytes: int
    error: Optional[str] = None


@dataclasses.dataclass
class ControllerState:
    all_busy_streak: int = 0
    idle_streaks: dict[str, int] = dataclasses.field(default_factory=dict)
    last_scale_out_ts: float = 0.0
    last_online_ts: dict[str, float] = dataclasses.field(default_factory=dict)
    registration_loss: dict[str, str] = dataclasses.field(default_factory=dict)

    def to_json(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_json(cls, raw: dict) -> "ControllerState":
        state = cls()
        state.all_busy_streak = int(raw.get("all_busy_streak", 0))
        state.idle_streaks = {str(k): int(v) for k, v in raw.get("idle_streaks", {}).items()}
        state.last_scale_out_ts = float(raw.get("last_scale_out_ts", 0.0))
        state.last_online_ts = {str(k): float(v) for k, v in raw.get("last_online_ts", {}).items()}
        state.registration_loss = {str(k): str(v) for k, v in raw.get("registration_loss", {}).items()}
        return state


@dataclasses.dataclass(frozen=True)
class Decision:
    action: str  # "none" | "scale_out" | "scale_in" | "heartbeat"
    service: Optional[str]
    reasons: tuple[str, ...]

    def to_json(self) -> dict:
        return {"action": self.action, "service": self.service, "reasons": list(self.reasons)}


def load_config(raw: dict) -> Config:
    services = []
    seen_indices: dict[str, set[int]] = {"baseline": set(), "elastic": set()}
    for kind in ("baseline", "elastic"):
        for entry in raw.get(kind, []):
            spec = ServiceSpec(
                name=str(entry["service"]),
                user=str(entry["user"]),
                kind=kind,
                index=int(entry["index"]),
                roles=tuple(str(r) for r in entry["roles"]),
            )
            if spec.index in seen_indices[kind]:
                raise ConfigError(f"duplicate {kind} index {spec.index}")
            seen_indices[kind].add(spec.index)
            services.append(spec)
    if not any(s.kind == "baseline" for s in services):
        raise ConfigError("config declares no baseline services")
    for spec in services:
        if spec.kind == "elastic" and "ci-core" in spec.roles:
            raise ConfigError(
                f"elastic service {spec.name} declares ci-core: elastic capacity "
                "must never broaden the ci-core role (issue #327)"
            )
    config = Config(
        host=str(raw["host"]),
        slice_name=str(raw["slice"]),
        services=tuple(sorted(services, key=lambda s: (s.kind, s.index))),
        operational_ceiling=int(raw["operational_ceiling"]),
        busy_observations_required=int(raw["busy_observations_required"]),
        idle_observations_required=int(raw["idle_observations_required"]),
        cooldown_seconds=int(raw["cooldown_seconds"]),
        grace_seconds=int(raw["grace_seconds"]),
        heartbeat_interval_seconds=int(raw["heartbeat_interval_seconds"]),
        heartbeat_timeout_seconds=int(raw["heartbeat_timeout_seconds"]),
        next_job_memory_bytes=int(raw["next_job_memory_bytes"]),
        system_memory_reserve_bytes=int(raw["system_memory_reserve_bytes"]),
        cpu_load_max_ratio=float(raw["cpu_load_max_ratio"]),
        io_pressure_max_pct=float(raw["io_pressure_max_pct"]),
        core_job_names=tuple(str(n) for n in raw.get("core_job_names", [])),
    )
    if any("ci-core" in s.roles for s in config.services) and not config.core_job_names:
        raise ConfigError(
            "a host with ci-core services must declare core_job_names so the "
            "controller can tell a running core job from a general job; "
            "without it every busy baseline would suppress scale-out forever"
        )
    if config.operational_ceiling < len(config.baseline):
        raise ConfigError("operational ceiling is below the baseline service count")
    if config.busy_observations_required < 1 or config.idle_observations_required < 1:
        raise ConfigError("observation streak requirements must be at least 1")
    if config.heartbeat_interval_seconds >= 14 * 86400:
        raise ConfigError(
            "heartbeat interval must stay well inside GitHub's 14-day offline "
            "auto-removal window"
        )
    return config


def _validate_observation(config: Config, obs: HostObservation) -> Optional[str]:
    if obs.error:
        return f"observation error: {obs.error}"
    missing = [s.name for s in config.services if s.name not in obs.services]
    if missing:
        return f"observation missing services: {', '.join(missing)}"
    if obs.cpu_count <= 0:
        return f"invalid cpu_count {obs.cpu_count}"
    if obs.load1 < 0:
        return f"invalid load1 {obs.load1}"
    if obs.mem_available_bytes < 0:
        return f"invalid mem_available_bytes {obs.mem_available_bytes}"
    if obs.slice_memory_max_bytes <= 0:
        return f"invalid slice_memory_max_bytes {obs.slice_memory_max_bytes}"
    if obs.slice_memory_current_bytes < 0:
        return f"invalid slice_memory_current_bytes {obs.slice_memory_current_bytes}"
    if not 0 <= obs.io_pressure_some_avg60 <= 100:
        return f"invalid io_pressure_some_avg60 {obs.io_pressure_some_avg60}"
    return None


def _resource_refusals(config: Config, obs: HostObservation) -> list[str]:
    refusals = []
    load_ceiling = config.cpu_load_max_ratio * obs.cpu_count
    if obs.load1 > load_ceiling:
        refusals.append(
            f"cpu guard: load1 {obs.load1:.2f} exceeds {load_ceiling:.2f} "
            f"({config.cpu_load_max_ratio} x {obs.cpu_count} cpus)"
        )
    projected_slice = obs.slice_memory_current_bytes + config.next_job_memory_bytes
    if projected_slice > obs.slice_memory_max_bytes:
        refusals.append(
            "slice memory guard: current "
            f"{obs.slice_memory_current_bytes} + next-job {config.next_job_memory_bytes} "
            f"exceeds slice max {obs.slice_memory_max_bytes}"
        )
    # The system guard admits the *next* job and never counts swap as relief:
    # on the no-swap netcup profile overshoot goes straight to the OOM killer.
    required = config.next_job_memory_bytes + config.system_memory_reserve_bytes
    if obs.mem_available_bytes < required:
        refusals.append(
            f"system memory guard: available {obs.mem_available_bytes} is below "
            f"next-job {config.next_job_memory_bytes} + reserve "
            f"{config.system_memory_reserve_bytes} (swap_total={obs.swap_total_bytes}, "
            "never counted as relief)"
        )
    if obs.io_pressure_some_avg60 > config.io_pressure_max_pct:
        refusals.append(
            f"io guard: pressure some avg60 {obs.io_pressure_some_avg60:.1f}% exceeds "
            f"{config.io_pressure_max_pct:.1f}%"
        )
    return refusals


def decide(config: Config, obs: HostObservation, state: ControllerState) -> tuple[Decision, ControllerState]:
    """Pure decision core: exactly one action per tick, fail closed."""
    new_state = ControllerState.from_json(state.to_json())

    invalid = _validate_observation(config, obs)
    if invalid:
        return (
            Decision(
                "none",
                None,
                (
                    f"fail closed, capacity preserved: {invalid}",
                    "remedy: fix the observation source; the controller takes no "
                    "action on data it cannot trust",
                ),
            ),
            new_state,
        )

    active = {name for name, s in obs.services.items() if s.active}
    busy = {name for name, s in obs.services.items() if s.active and s.has_worker}

    # Track when each elastic service was last seen online, for the heartbeat.
    for spec in config.elastic:
        if spec.name in active:
            new_state.last_online_ts[spec.name] = obs.now
            new_state.registration_loss.pop(spec.name, None)

    # Busy/idle streak accounting.
    if active and active == busy:
        new_state.all_busy_streak += 1
    else:
        new_state.all_busy_streak = 0
    for spec in config.elastic:
        if spec.name in active and spec.name not in busy:
            new_state.idle_streaks[spec.name] = new_state.idle_streaks.get(spec.name, 0) + 1
        else:
            new_state.idle_streaks[spec.name] = 0

    # Scale in first: the highest-numbered elastic service idle for the full
    # window. Never a service with a live Runner.Worker.
    idle_candidates = [
        spec
        for spec in config.elastic
        if spec.name in active
        and not obs.services[spec.name].has_worker
        and new_state.idle_streaks.get(spec.name, 0) >= config.idle_observations_required
    ]
    if idle_candidates:
        target = max(idle_candidates, key=lambda s: s.index)
        new_state.idle_streaks[target.name] = 0
        return (
            Decision(
                "scale_in",
                target.name,
                (
                    f"idle for {config.idle_observations_required} consecutive "
                    "observations; adapter re-checks a "
                    f"{config.grace_seconds}s grace window before stopping",
                ),
            ),
            new_state,
        )

    # Scale out: every guard must admit one more worst-case job.
    stopped_elastic = sorted(
        (spec for spec in config.elastic if spec.name not in active),
        key=lambda s: s.index,
    )
    scale_out_refusals: list[str] = []
    if new_state.all_busy_streak >= config.busy_observations_required and stopped_elastic:
        if len(active) >= config.operational_ceiling:
            scale_out_refusals.append(
                f"operational ceiling {config.operational_ceiling} reached with "
                f"{len(active)} active services"
            )
        since_last = obs.now - new_state.last_scale_out_ts
        if since_last < config.cooldown_seconds:
            scale_out_refusals.append(
                f"cooldown: {since_last:.0f}s since last scale-out is below "
                f"{config.cooldown_seconds}s"
            )
        core_busy = [
            spec.name
            for spec in config.services
            if "ci-core" in spec.roles
            and obs.services[spec.name].has_worker
            and obs.services[spec.name].core_job is not False
        ]
        if core_busy:
            scale_out_refusals.append(
                "ci-core suppression: " + ", ".join(core_busy) + " is running a "
                "core job (or one the observer cannot classify, treated as core); "
                "admission guards cannot shed load already admitted, so timing-"
                "sensitive Core work wins by not admitting more"
            )
        scale_out_refusals.extend(_resource_refusals(config, obs))
        if not scale_out_refusals:
            target = stopped_elastic[0]
            new_state.last_scale_out_ts = obs.now
            new_state.all_busy_streak = 0
            return (
                Decision(
                    "scale_out",
                    target.name,
                    (
                        f"all {len(active)} active services busy for "
                        f"{config.busy_observations_required} consecutive observations; "
                        "all admission guards permit one more worst-case job",
                    ),
                ),
                new_state,
            )

    # Heartbeat: keep stopped, registered elastic identities inside GitHub's
    # 14-day offline auto-removal window. One service per tick, never one
    # already flagged as a registration loss.
    for spec in sorted(config.elastic, key=lambda s: s.index):
        if spec.name in active:
            continue
        if spec.name in new_state.registration_loss:
            continue
        last_online = new_state.last_online_ts.get(spec.name)
        if last_online is None or obs.now - last_online >= config.heartbeat_interval_seconds:
            return (
                Decision(
                    "heartbeat",
                    spec.name,
                    (
                        "stopped elastic service approaching the GitHub 14-day "
                        "offline auto-removal window"
                        if last_online is not None
                        else "stopped elastic service has no recorded online time",
                    ),
                ),
                new_state,
            )

    reasons = ["no action required"]
    if scale_out_refusals:
        reasons = ["scale-out refused: " + r for r in scale_out_refusals]
    return Decision("none", None, tuple(reasons)), new_state


def confirm_scale_in(pre: ServiceObservation, post: ServiceObservation, recent_job_start: bool) -> tuple[bool, str]:
    """Grace-window recheck for the assignment race, pure and testable.

    ``post`` is observed after the grace sleep; ``recent_job_start`` is true
    when the service journal shows a job-start marker inside the idle window.
    """
    if pre.has_worker or post.has_worker:
        return False, "abort: Runner.Worker appeared; a service running a job is never stopped"
    if recent_job_start:
        return False, "abort: listener accepted a job inside the idle window"
    return True, "grace window clean: no worker, no recent job acceptance"


def heartbeat_outcome(listener_ready: bool, service_name: str) -> tuple[bool, str]:
    """Classify a heartbeat attempt, pure and testable."""
    if listener_ready:
        return True, f"heartbeat ok: {service_name} authenticated and reached listener-ready"
    return (
        False,
        f"{REGISTRATION_LOSS_TAG} service={service_name} "
        "why=the runner failed to reach listener-ready during a heartbeat, so its "
        "GitHub registration is likely gone (14-day offline auto-removal) "
        "remedy=re-register this runner off-host with a fresh registration token, "
        "then clear its registration_loss entry in the controller state file; the "
        "controller never retries a lost registration silently",
    )


# ---------------------------------------------------------------------------
# Host adapter: thin, side-effectful, excluded from the deterministic tests.
# ---------------------------------------------------------------------------


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _read_first_line(path: Path) -> str:
    return path.read_text().splitlines()[0]


def _meminfo() -> dict[str, int]:
    values = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, _, rest = line.partition(":")
        values[key.strip()] = int(rest.split()[0]) * 1024
    return values


def _slice_memory(slice_name: str) -> tuple[int, int]:
    # A dash in a slice name nests it (lmdj-ci.slice lives under lmdj.slice),
    # so resolve the real cgroup path instead of assembling it from the name.
    result = _run(["systemctl", "show", slice_name, "-p", "ControlGroup", "--value"])
    control_group = result.stdout.strip().lstrip("/")
    if not control_group:
        raise RuntimeError(f"no ControlGroup for {slice_name}; is the slice active?")
    base = Path("/sys/fs/cgroup") / control_group
    current = int((base / "memory.current").read_text())
    raw_max = (base / "memory.max").read_text().strip()
    maximum = int(raw_max) if raw_max != "max" else 0
    return current, maximum


def _io_pressure_some_avg60() -> float:
    for line in Path("/proc/pressure/io").read_text().splitlines():
        if line.startswith("some"):
            match = re.search(r"avg60=([0-9.]+)", line)
            if match:
                return float(match.group(1))
    raise RuntimeError("no 'some avg60' value in /proc/pressure/io")


def _service_active(name: str) -> bool:
    return _run(["systemctl", "is-active", "--quiet", name]).returncode == 0


def _user_has_worker(user: str) -> bool:
    return _run(["pgrep", "-u", user, "-f", WORKER_PROCESS]).returncode == 0


def _current_job_is_core(service: str, core_job_names: tuple[str, ...]) -> Optional[bool]:
    """Classify the running job from the listener's journal, None if unknown."""
    result = _run(["journalctl", "-u", service, "-n", "400", "--no-pager", "-q"])
    lines = [l for l in result.stdout.splitlines() if JOB_START_MARKER in l]
    if not lines:
        return None
    job_name = lines[-1].split(JOB_START_MARKER, 1)[1].strip()
    if not job_name:
        return None
    return any(job_name.startswith(core) for core in core_job_names)


def _observe_service(spec: ServiceSpec, core_job_names: tuple[str, ...]) -> ServiceObservation:
    has_worker = _user_has_worker(spec.user)
    core_job = None
    if has_worker and "ci-core" in spec.roles:
        core_job = _current_job_is_core(spec.name, core_job_names)
    return ServiceObservation(
        active=_service_active(spec.name),
        has_worker=has_worker,
        core_job=core_job,
    )


def observe(config: Config, now: Optional[float] = None) -> HostObservation:
    try:
        services = {
            spec.name: _observe_service(spec, config.core_job_names)
            for spec in config.services
        }
        meminfo = _meminfo()
        slice_current, slice_max = _slice_memory(config.slice_name)
        return HostObservation(
            now=time.time() if now is None else now,
            services=services,
            cpu_count=len([l for l in Path("/proc/stat").read_text().splitlines() if re.match(r"cpu\d", l)]),
            load1=float(_read_first_line(Path("/proc/loadavg")).split()[0]),
            mem_available_bytes=meminfo["MemAvailable"],
            slice_memory_current_bytes=slice_current,
            slice_memory_max_bytes=slice_max,
            io_pressure_some_avg60=_io_pressure_some_avg60(),
            swap_total_bytes=meminfo.get("SwapTotal", 0),
        )
    except Exception as error:  # noqa: BLE001 - fail closed on any observation error
        return HostObservation(
            now=time.time() if now is None else now,
            services={},
            cpu_count=0,
            load1=0.0,
            mem_available_bytes=0,
            slice_memory_current_bytes=0,
            slice_memory_max_bytes=0,
            io_pressure_some_avg60=0.0,
            swap_total_bytes=0,
            error=f"{type(error).__name__}: {error}",
        )


def _recent_job_start(service: str, window_seconds: int) -> bool:
    result = _run(
        ["journalctl", "-u", service, "--since", f"-{window_seconds}s", "--no-pager", "-q"]
    )
    return JOB_START_MARKER in result.stdout


def _listener_ready_since(service: str, since_epoch: float, timeout: int) -> bool:
    deadline = time.time() + timeout
    since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(since_epoch))
    while time.time() < deadline:
        if not _service_active(service):
            time.sleep(2)
            continue
        result = _run(["journalctl", "-u", service, "--since", since, "--no-pager", "-q"])
        if LISTENER_READY_MARKER in result.stdout:
            return True
        time.sleep(3)
    return False


def apply(config: Config, decision: Decision, state: ControllerState, obs: HostObservation) -> ControllerState:
    if decision.action == "none" or decision.service is None:
        return state
    spec = next(s for s in config.services if s.name == decision.service)

    if decision.action == "scale_out":
        _run(["systemctl", "start", spec.name])
        print(f"scale-out: started {spec.name}")
        return state

    if decision.action == "scale_in":
        pre = ServiceObservation(_service_active(spec.name), _user_has_worker(spec.user))
        time.sleep(config.grace_seconds)
        post = ServiceObservation(_service_active(spec.name), _user_has_worker(spec.user))
        idle_window = config.idle_observations_required * config.grace_seconds + 600
        ok, reason = confirm_scale_in(pre, post, _recent_job_start(spec.name, idle_window))
        if ok:
            _run(["systemctl", "stop", spec.name])
            print(f"scale-in: stopped {spec.name} ({reason})")
        else:
            print(f"scale-in: kept {spec.name} ({reason})")
        return state

    if decision.action == "heartbeat":
        started = time.time()
        _run(["systemctl", "start", spec.name])
        ready = _listener_ready_since(spec.name, started, config.heartbeat_timeout_seconds)
        _run(["systemctl", "stop", spec.name])
        ok, message = heartbeat_outcome(ready, spec.name)
        print(message)
        if ok:
            state.last_online_ts[spec.name] = time.time()
        else:
            state.registration_loss[spec.name] = message
        return state

    raise ValueError(f"unknown action {decision.action}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true", help="observe and decide, apply nothing, mutate no state")
    args = parser.parse_args(argv)

    config = load_config(json.loads(args.config.read_text()))
    state = ControllerState()
    if args.state.exists():
        state = ControllerState.from_json(json.loads(args.state.read_text()))

    obs = observe(config)
    decision, new_state = decide(config, obs, state)
    print(json.dumps({"host": config.host, "decision": decision.to_json()}, ensure_ascii=False))

    if args.dry_run:
        return 0

    new_state = apply(config, decision, new_state, obs)
    args.state.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.state.with_suffix(".tmp")
    tmp.write_text(json.dumps(new_state.to_json(), indent=1))
    tmp.replace(args.state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
