#!/usr/bin/env python3
"""Deterministic tests for the elastic runner controller decision core (#327).

Every scenario the issue's acceptance names is covered here without a host:
scale-out, resource refusal, cooldown, hard ceiling, idle scale-in,
busy-worker protection, malformed input, reboot baseline, ci-core-busy
suppression, projected next-job memory refusal (including the no-swap netcup
profile), scale-in grace-window recheck, and registration-heartbeat
scheduling.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts/ci/elastic_runner.py"

spec = importlib.util.spec_from_file_location("elastic_runner", MODULE_PATH)
er = importlib.util.module_from_spec(spec)
sys.modules["elastic_runner"] = er
spec.loader.exec_module(er)


def netcup_config(**overrides):
    raw = {
        "host": "netcup",
        "slice": "lmdj-ci.slice",
        "baseline": [
            {"service": f"runner-{i:02d}", "user": f"u{i:02d}", "index": i,
             "roles": ["ci-general", "ci-web-heavy"]}
            for i in (1, 2, 3, 4)
        ],
        "elastic": [
            {"service": f"runner-{i:02d}", "user": f"u{i:02d}", "index": i,
             "roles": ["ci-general", "ci-web-heavy"]}
            for i in (5, 6, 7, 8)
        ],
        "operational_ceiling": 8,
        "busy_observations_required": 3,
        "idle_observations_required": 5,
        "cooldown_seconds": 300,
        "grace_seconds": 5,
        "heartbeat_interval_seconds": 7 * 86400,
        "heartbeat_timeout_seconds": 120,
        "next_job_memory_bytes": 6 * 2**30,
        "system_memory_reserve_bytes": 2 * 2**30,
        "cpu_load_max_ratio": 0.85,
        "io_pressure_max_pct": 40.0,
    }
    raw.update(overrides)
    return er.load_config(raw)


def contabo_config():
    return er.load_config({
        "host": "contabo",
        "slice": "lmdj-ci.slice",
        "baseline": [
            {"service": f"runner-{i:02d}", "user": f"u{i:02d}", "index": i,
             "roles": ["ci-general", "ci-core"]}
            for i in (1, 2)
        ] + [
            {"service": "runner-03", "user": "u03", "index": 3,
             "roles": ["ci-general"]}
        ],
        "elastic": [
            {"service": f"runner-{i:02d}", "user": f"u{i:02d}", "index": i,
             "roles": ["ci-general"]}
            for i in (4, 5, 6)
        ],
        "operational_ceiling": 4,
        "busy_observations_required": 3,
        "idle_observations_required": 5,
        "cooldown_seconds": 300,
        "grace_seconds": 5,
        "heartbeat_interval_seconds": 7 * 86400,
        "heartbeat_timeout_seconds": 120,
        "next_job_memory_bytes": 4 * 2**30,
        "system_memory_reserve_bytes": 2 * 2**30,
        "cpu_load_max_ratio": 0.85,
        "io_pressure_max_pct": 40.0,
        "core_job_names": ["core (ubuntu-latest)", "core-asan", "core-coverage",
                           "Core package"],
    })


def observation(config, active, busy=(), now=1_000_000.0, swap_total=0,
                core_jobs=None, **host):
    core_jobs = core_jobs or {}
    services = {
        spec.name: er.ServiceObservation(
            active=spec.name in active,
            has_worker=spec.name in busy,
            core_job=core_jobs.get(spec.name),
        )
        for spec in config.services
    }
    defaults = dict(
        cpu_count=16,
        load1=2.0,
        mem_available_bytes=40 * 2**30,
        slice_memory_current_bytes=8 * 2**30,
        slice_memory_max_bytes=48 * 2**30,
        io_pressure_some_avg60=1.0,
    )
    defaults.update(host)
    return er.HostObservation(now=now, services=services, swap_total_bytes=swap_total, **defaults)


def fresh_state(config, heartbeat_ok_at=1_000_000.0):
    """State whose heartbeats are all satisfied, isolating capacity rules."""
    state = er.ControllerState()
    for spec in config.elastic:
        state.last_online_ts[spec.name] = heartbeat_ok_at
    return state


BASELINE = ("runner-01", "runner-02", "runner-03", "runner-04")


class CheckedInTopologyTest(unittest.TestCase):
    def test_checked_in_configs_use_four_and_three_baseline_runners(self):
        expected = {
            "netcup": ([1, 2, 3, 4], [5, 6, 7, 8], 8),
            "contabo": ([1, 2, 3], [4, 5, 6], 4),
        }
        for host, (baseline, elastic, ceiling) in expected.items():
            path = ROOT / "scripts/ci/elastic-runner" / f"{host}.json"
            raw = json.loads(path.read_text())
            self.assertEqual([entry["index"] for entry in raw["baseline"]], baseline)
            self.assertEqual([entry["index"] for entry in raw["elastic"]], elastic)
            self.assertEqual(raw["operational_ceiling"], ceiling)


class DeploymentContractTest(unittest.TestCase):
    def test_deploy_finds_the_controller_from_a_repository_checkout(self):
        """A clone must be a valid staging directory.

        `elastic_runner.py` lives in `scripts/ci/` because the contract tests
        import it there; the deploy script, the unit files and the host
        configs live one directory down. The script used to install
        `$here/elastic_runner.py`, which exists in neither layout a clone
        produces, so the documented redeploy failed with `install: cannot
        stat` on the first host that needed it.
        """
        script = (ROOT / "scripts/ci/elastic-runner/deploy-controller.sh").read_text()
        self.assertIn('controller="$here/../elastic_runner.py"', script)
        self.assertIn('install -o root -g root -m 0755 "$controller"', script)
        self.assertNotIn(
            'install -o root -g root -m 0755 "$here/elastic_runner.py"',
            script,
            msg=("why: the controller is not beside this script in the repository, "
                 "so installing from $here fails on a clone; remedy: resolve it "
                 "from $here/../ with a fallback"),
        )
        self.assertTrue(
            (ROOT / "scripts/ci/elastic_runner.py").is_file(),
            "the path the script resolves must be where the controller actually is",
        )

    def test_deploy_enables_declared_baselines_after_daemon_reload(self):
        script = (
            ROOT / "scripts/ci/elastic-runner/deploy-controller.sh"
        ).read_text()
        reconciliation = (
            'for unit in $baseline_units; do\n'
            '  systemctl enable --now "$unit"\n'
            'done'
        )
        self.assertIn(reconciliation, script)
        self.assertLess(
            script.index("systemctl daemon-reload"),
            script.index(reconciliation),
        )


def run_busy_ticks(config, state, active, ticks, now=1_000_000.0, core_jobs=None, **host):
    """Ticks where every active service is busy. Unless a test overrides it,
    core-capable services are classified as running general jobs so that the
    ci-core suppression rule is isolated to its own tests."""
    if core_jobs is None:
        core_jobs = {
            spec.name: False for spec in config.services if "ci-core" in spec.roles
        }
    decision = None
    for i in range(ticks):
        obs = observation(
            config, active=active, busy=active, now=now + i,
            core_jobs=core_jobs, **host,
        )
        decision, state = er.decide(config, obs, state)
    return decision, state


class ScaleOutTest(unittest.TestCase):
    def test_all_busy_streak_starts_lowest_stopped_elastic(self):
        config = netcup_config()
        decision, state = run_busy_ticks(config, fresh_state(config), BASELINE, 3)
        self.assertEqual(decision.action, "scale_out")
        self.assertEqual(decision.service, "runner-05")
        self.assertEqual(state.all_busy_streak, 0)
        self.assertEqual(state.last_scale_out_ts, 1_000_002.0)

    def test_streak_below_threshold_takes_no_action(self):
        config = netcup_config()
        decision, _ = run_busy_ticks(config, fresh_state(config), BASELINE, 2)
        self.assertEqual(decision.action, "none")

    def test_one_idle_service_resets_the_streak(self):
        config = netcup_config()
        state = fresh_state(config)
        _, state = run_busy_ticks(config, state, BASELINE, 2)
        obs = observation(config, active=BASELINE, busy=BASELINE[:2], now=1_000_002.0)
        decision, state = er.decide(config, obs, state)
        self.assertEqual(decision.action, "none")
        self.assertEqual(state.all_busy_streak, 0)

    def test_scale_out_is_one_service_at_a_time(self):
        config = netcup_config()
        decision, _ = run_busy_ticks(config, fresh_state(config), BASELINE, 3)
        self.assertEqual(decision.action, "scale_out")
        # A single decision names a single service; there is no batch shape.
        self.assertIsInstance(decision.service, str)


class ResourceRefusalTest(unittest.TestCase):
    def test_cpu_guard_refuses(self):
        config = netcup_config()
        decision, _ = run_busy_ticks(
            config, fresh_state(config), BASELINE, 3, load1=15.0
        )
        self.assertEqual(decision.action, "none")
        self.assertTrue(any("cpu guard" in r for r in decision.reasons))

    def test_io_guard_refuses(self):
        config = netcup_config()
        decision, _ = run_busy_ticks(
            config, fresh_state(config), BASELINE, 3, io_pressure_some_avg60=55.0
        )
        self.assertEqual(decision.action, "none")
        self.assertTrue(any("io guard" in r for r in decision.reasons))

    def test_refusal_preserves_capacity_and_keeps_counting(self):
        config = netcup_config()
        decision, state = run_busy_ticks(
            config, fresh_state(config), BASELINE, 4, load1=15.0
        )
        self.assertEqual(decision.action, "none")
        self.assertEqual(state.all_busy_streak, 4)
        self.assertEqual(state.last_scale_out_ts, 0.0)


class ProjectedMemoryRefusalTest(unittest.TestCase):
    def test_slice_guard_admits_the_next_job_not_the_current_state(self):
        config = netcup_config()
        # 43 GiB used of 48 GiB: fine today, but 43 + 6 > 48 for the next job.
        decision, _ = run_busy_ticks(
            config, fresh_state(config), BASELINE, 3,
            slice_memory_current_bytes=43 * 2**30,
        )
        self.assertEqual(decision.action, "none")
        self.assertTrue(any("slice memory guard" in r for r in decision.reasons))

    def test_no_swap_profile_refuses_without_system_headroom(self):
        config = netcup_config()
        decision, _ = run_busy_ticks(
            config, fresh_state(config), BASELINE, 3,
            mem_available_bytes=7 * 2**30, swap_total=0,
        )
        self.assertEqual(decision.action, "none")
        self.assertTrue(any("system memory guard" in r for r in decision.reasons))

    def test_swap_is_never_counted_as_relief(self):
        config = netcup_config()
        decision_with_swap, _ = run_busy_ticks(
            config, fresh_state(config), BASELINE, 3,
            mem_available_bytes=7 * 2**30, swap_total=8 * 2**30,
        )
        self.assertEqual(decision_with_swap.action, "none")
        self.assertTrue(
            any("system memory guard" in r for r in decision_with_swap.reasons)
        )


class CooldownTest(unittest.TestCase):
    def test_cooldown_blocks_consecutive_scale_outs(self):
        config = netcup_config()
        state = fresh_state(config)
        decision, state = run_busy_ticks(config, state, BASELINE, 3)
        self.assertEqual(decision.action, "scale_out")
        active = BASELINE + ("runner-05",)
        decision, state = run_busy_ticks(
            config, state, active, 3, now=1_000_010.0
        )
        self.assertEqual(decision.action, "none")
        self.assertTrue(any("cooldown" in r for r in decision.reasons))

    def test_elapsed_cooldown_admits_the_next_service(self):
        config = netcup_config()
        state = fresh_state(config)
        _, state = run_busy_ticks(config, state, BASELINE, 3)
        active = BASELINE + ("runner-05",)
        decision, _ = run_busy_ticks(
            config, state, active, 3, now=1_000_002.0 + 301
        )
        self.assertEqual(decision.action, "scale_out")
        self.assertEqual(decision.service, "runner-06")


class CeilingTest(unittest.TestCase):
    def test_operational_ceiling_refuses_above_active_count(self):
        config = contabo_config()
        active = ("runner-01", "runner-02", "runner-03", "runner-04")
        decision, _ = run_busy_ticks(config, fresh_state(config), active, 3)
        self.assertEqual(decision.action, "none")
        self.assertTrue(any("ceiling" in r for r in decision.reasons))

    def test_contabo_runners_05_06_stay_outside_consideration(self):
        """Ceiling 4 on contabo: 05 and 06 can never be capacity targets."""
        config = contabo_config()
        state = fresh_state(config)
        active = ("runner-01", "runner-02", "runner-03")
        decision, state = run_busy_ticks(config, state, active, 3)
        self.assertEqual(decision.action, "scale_out")
        self.assertEqual(decision.service, "runner-04")
        active = ("runner-01", "runner-02", "runner-03", "runner-04")
        decision, _ = run_busy_ticks(config, state, active, 3, now=1_002_000.0)
        self.assertEqual(decision.action, "none")

    def test_ceiling_below_baseline_is_a_config_error(self):
        with self.assertRaises(er.ConfigError):
            netcup_config(operational_ceiling=2)


class ScaleInTest(unittest.TestCase):
    def test_sustained_idle_stops_highest_numbered_elastic(self):
        config = netcup_config()
        state = fresh_state(config)
        active = BASELINE + ("runner-05", "runner-06")
        decision = None
        for i in range(5):
            obs = observation(config, active=active, busy=BASELINE, now=1_000_000.0 + i)
            decision, state = er.decide(config, obs, state)
        self.assertEqual(decision.action, "scale_in")
        self.assertEqual(decision.service, "runner-06")

    def test_baseline_is_never_a_scale_in_target(self):
        config = netcup_config()
        state = fresh_state(config)
        decision = None
        for i in range(10):
            obs = observation(config, active=BASELINE, busy=(), now=1_000_000.0 + i)
            decision, state = er.decide(config, obs, state)
        self.assertEqual(decision.action, "none")


class BusyWorkerProtectionTest(unittest.TestCase):
    def test_a_service_with_a_worker_is_never_stopped(self):
        config = netcup_config()
        state = fresh_state(config)
        active = BASELINE + ("runner-05",)
        for i in range(20):
            obs = observation(
                config, active=active, busy=("runner-05",), now=1_000_000.0 + i
            )
            decision, state = er.decide(config, obs, state)
            self.assertNotEqual(decision.action, "scale_in")

    def test_grace_recheck_aborts_when_worker_appears(self):
        idle = er.ServiceObservation(active=True, has_worker=False)
        working = er.ServiceObservation(active=True, has_worker=True)
        ok, reason = er.confirm_scale_in(idle, working, recent_job_start=False)
        self.assertFalse(ok)
        self.assertIn("never stopped", reason)


class GraceWindowRecheckTest(unittest.TestCase):
    def test_recent_job_acceptance_aborts_the_stop(self):
        idle = er.ServiceObservation(active=True, has_worker=False)
        ok, reason = er.confirm_scale_in(idle, idle, recent_job_start=True)
        self.assertFalse(ok)
        self.assertIn("accepted a job", reason)

    def test_clean_grace_window_admits_the_stop(self):
        idle = er.ServiceObservation(active=True, has_worker=False)
        ok, _ = er.confirm_scale_in(idle, idle, recent_job_start=False)
        self.assertTrue(ok)


class MalformedInputTest(unittest.TestCase):
    def test_observation_error_fails_closed(self):
        config = netcup_config()
        state = fresh_state(config)
        state.all_busy_streak = 7
        obs = er.HostObservation(
            now=1_000_000.0, services={}, cpu_count=0, load1=0.0,
            mem_available_bytes=0, slice_memory_current_bytes=0,
            slice_memory_max_bytes=0, io_pressure_some_avg60=0.0,
            swap_total_bytes=0, error="boom",
        )
        decision, new_state = er.decide(config, obs, state)
        self.assertEqual(decision.action, "none")
        self.assertTrue(any("fail closed" in r for r in decision.reasons))
        self.assertTrue(any("remedy" in r for r in decision.reasons))
        self.assertEqual(new_state.all_busy_streak, 7)

    def test_missing_service_fails_closed(self):
        config = netcup_config()
        obs = observation(config, active=BASELINE, busy=BASELINE)
        obs.services.pop("runner-08")
        decision, _ = er.decide(config, obs, fresh_state(config))
        self.assertEqual(decision.action, "none")
        self.assertTrue(any("missing services" in r for r in decision.reasons))

    def test_nonsense_metrics_fail_closed(self):
        config = netcup_config()
        for field, value in (
            ("cpu_count", 0),
            ("load1", -1.0),
            ("io_pressure_some_avg60", 250.0),
            ("slice_memory_max_bytes", 0),
        ):
            obs = observation(config, active=BASELINE, busy=BASELINE, **{field: value})
            decision, _ = er.decide(config, obs, fresh_state(config))
            self.assertEqual(decision.action, "none", field)


class RebootBaselineTest(unittest.TestCase):
    def test_post_reboot_baseline_with_fresh_state_takes_no_capacity_action(self):
        """Only baseline services are enabled, so a reboot restores baseline;
        with satisfied heartbeats the controller then has nothing to do."""
        config = netcup_config()
        obs = observation(config, active=BASELINE, busy=(), now=1_000_100.0)
        decision, state = er.decide(config, obs, fresh_state(config))
        self.assertEqual(decision.action, "none")
        self.assertEqual(state.all_busy_streak, 0)


class CiCoreSuppressionTest(unittest.TestCase):
    def test_running_core_job_suppresses_scale_out(self):
        config = contabo_config()
        active = ("runner-01", "runner-02", "runner-03")
        decision, _ = run_busy_ticks(
            config, fresh_state(config), active, 3,
            core_jobs={"runner-01": True, "runner-02": False},
        )
        self.assertEqual(decision.action, "none")
        self.assertTrue(any("ci-core suppression" in r for r in decision.reasons))

    def test_unclassifiable_job_on_a_core_service_suppresses(self):
        """Unknown is treated as core: the observer fails closed."""
        config = contabo_config()
        active = ("runner-01", "runner-02", "runner-03")
        decision, _ = run_busy_ticks(
            config, fresh_state(config), active, 3,
            core_jobs={"runner-01": None, "runner-02": False},
        )
        self.assertEqual(decision.action, "none")
        self.assertTrue(any("ci-core suppression" in r for r in decision.reasons))

    def test_general_jobs_on_core_services_do_not_deadlock_scale_out(self):
        """Contabo baselines carry both roles; busy with general jobs they
        must still admit elastic capacity, or elastic would be dead code."""
        config = contabo_config()
        active = ("runner-01", "runner-02", "runner-03")
        decision, _ = run_busy_ticks(config, fresh_state(config), active, 3)
        self.assertEqual(decision.action, "scale_out")
        self.assertEqual(decision.service, "runner-04")

    def test_core_host_without_job_classifier_is_a_config_error(self):
        with self.assertRaises(er.ConfigError):
            er.load_config({
                "host": "contabo", "slice": "lmdj-ci.slice",
                "baseline": [{"service": "runner-01", "user": "u01", "index": 1,
                              "roles": ["ci-general", "ci-core"]}],
                "elastic": [{"service": "runner-03", "user": "u03", "index": 3,
                             "roles": ["ci-general"]}],
                "operational_ceiling": 2,
                "busy_observations_required": 1, "idle_observations_required": 1,
                "cooldown_seconds": 1, "grace_seconds": 1,
                "heartbeat_interval_seconds": 86400, "heartbeat_timeout_seconds": 60,
                "next_job_memory_bytes": 1, "system_memory_reserve_bytes": 1,
                "cpu_load_max_ratio": 0.85, "io_pressure_max_pct": 40.0,
            })

    def test_elastic_ci_core_role_is_rejected_at_load(self):
        with self.assertRaises(er.ConfigError):
            er.load_config({
                "host": "contabo", "slice": "lmdj-ci.slice",
                "baseline": [{"service": "runner-01", "user": "u01", "index": 1,
                              "roles": ["ci-core"]}],
                "elastic": [{"service": "runner-03", "user": "u03", "index": 3,
                             "roles": ["ci-core"]}],
                "operational_ceiling": 2,
                "busy_observations_required": 1, "idle_observations_required": 1,
                "cooldown_seconds": 1, "grace_seconds": 1,
                "heartbeat_interval_seconds": 86400, "heartbeat_timeout_seconds": 60,
                "next_job_memory_bytes": 1, "system_memory_reserve_bytes": 1,
                "cpu_load_max_ratio": 0.85, "io_pressure_max_pct": 40.0,
            })


class HeartbeatTest(unittest.TestCase):
    def test_unknown_last_online_is_due_immediately(self):
        config = netcup_config()
        obs = observation(config, active=BASELINE, busy=())
        decision, _ = er.decide(config, obs, er.ControllerState())
        self.assertEqual(decision.action, "heartbeat")
        self.assertEqual(decision.service, "runner-05")

    def test_heartbeat_fires_inside_the_14_day_window(self):
        config = netcup_config()
        state = fresh_state(config, heartbeat_ok_at=0.0)
        obs = observation(config, active=BASELINE, busy=(), now=7 * 86400 + 1.0)
        decision, _ = er.decide(config, obs, state)
        self.assertEqual(decision.action, "heartbeat")

    def test_one_heartbeat_per_tick(self):
        config = netcup_config()
        obs = observation(config, active=BASELINE, busy=())
        decision, _ = er.decide(config, obs, er.ControllerState())
        self.assertEqual(decision.action, "heartbeat")
        self.assertIsInstance(decision.service, str)

    def test_capacity_actions_win_over_heartbeats(self):
        config = netcup_config()
        decision, _ = run_busy_ticks(config, er.ControllerState(), BASELINE, 3)
        self.assertEqual(decision.action, "scale_out")

    def test_registration_loss_is_reported_and_never_retried(self):
        config = netcup_config()
        ok, message = er.heartbeat_outcome(False, "runner-05")
        self.assertFalse(ok)
        self.assertIn(er.REGISTRATION_LOSS_TAG, message)
        self.assertIn("why=", message)
        self.assertIn("remedy=", message)
        state = fresh_state(config, heartbeat_ok_at=0.0)
        state.registration_loss["runner-05"] = message
        obs = observation(config, active=BASELINE, busy=(), now=30 * 86400.0)
        decision, _ = er.decide(config, obs, state)
        self.assertEqual(decision.action, "heartbeat")
        self.assertNotEqual(decision.service, "runner-05")

    def test_activation_clears_a_registration_loss(self):
        config = netcup_config()
        state = fresh_state(config)
        state.registration_loss["runner-05"] = "lost"
        obs = observation(config, active=BASELINE + ("runner-05",), busy=())
        _, new_state = er.decide(config, obs, state)
        self.assertNotIn("runner-05", new_state.registration_loss)

    def test_interval_at_or_beyond_14_days_is_a_config_error(self):
        with self.assertRaises(er.ConfigError):
            netcup_config(heartbeat_interval_seconds=14 * 86400)

    def test_heartbeat_success_message_names_the_service(self):
        ok, message = er.heartbeat_outcome(True, "runner-07")
        self.assertTrue(ok)
        self.assertIn("runner-07", message)


class StatePersistenceTest(unittest.TestCase):
    def test_state_round_trips_through_json(self):
        state = er.ControllerState(
            all_busy_streak=2,
            idle_streaks={"runner-04": 3},
            last_scale_out_ts=123.0,
            last_online_ts={"runner-05": 456.0},
            registration_loss={"runner-06": "lost"},
        )
        restored = er.ControllerState.from_json(state.to_json())
        self.assertEqual(restored.to_json(), state.to_json())


if __name__ == "__main__":
    unittest.main()
