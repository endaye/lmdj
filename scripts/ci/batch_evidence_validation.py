"""Pure shared batch evidence checks; no API, filesystem or state writes."""
import batch_execution
import batch_verdict
import incremental_batch as batch

PREFIX = "Execute incremental batch / "
PRODUCER_JOB = PREFIX + "Scoped batch verdict"
ALIASES = {"core-tsan": "nightly-tsan", "core-stress": "nightly-stress"}
JOB_NAMES = {
    "docs-static": "Docs / static", "portal": "Architecture Portal / portal",
    "ci-contract": "CI contract", "deploy-contract": "Deploy contract",
    "chameleon-lab": "Chameleon Lab", "package": "Core package",
    "web-toolchain-conformance": "web-toolchain-conformance",
    "web-runtime-host": "web-runtime-host", "creator-web": "creator-web",
    "web-runtime-lab": "web-runtime-lab", "core-ubuntu": "core (ubuntu-latest)",
    "select-macos-runner": "Select macOS runner", "macos-primary": "macOS gates (primary)",
    "macos-fallback": "macOS gates (GitHub-hosted fallback)",
    "core-macos": "core (macos-latest)", "core-asan-macos": "core-asan-macos",
    "core-asan": "core-asan", "core-coverage": "core-coverage",
    "core-tsan": "Self-test TSan stress / core-tsan",
    "core-stress": "Self-test Release stress / core-stress",
}
EXECUTION_SOURCES = (
    ".github/workflows/self-test-report.yml", ".github/workflows/ci.yml",
    ".github/workflows/core-nightly.yml", ".github/workflows/architecture-portal.yml",
)


def require(condition, why):
    batch.require(condition, why, "reconcile exact trusted run, request and artifact identities; never repair evidence by hand")


def dependencies(policy):
    result = {job: ["change-scope"] for job in policy.inventory.job_owner}
    for job in ("macos-primary", "core-macos", "core-asan-macos"):
        result[job] = ["change-scope", "select-macos-runner"]
    result["macos-fallback"] = ["change-scope", "select-macos-runner", "macos-primary"]
    return result


def producer_uploaded(producer):
    steps = producer.get("steps")
    if not isinstance(steps, list):
        return False
    for name in ("Judge selected suites from actual needs", "Retain scoped verdict and raw needs"):
        matches = [step for step in steps if isinstance(step, dict) and step.get("name") == name]
        if len(matches) != 1 or matches[0].get("status") != "completed" or matches[0].get("conclusion") != "success":
            return False
    return True


def validate_bundle(bundle, request, run, policy):
    identity = {"request_id": request["id"], "request_kind": request["kind"], "base_sha": request["base"],
                "target_sha": request["target"], "control_sha": request["control"], "policy_digest": request["policy"],
                "run_id": run["id"], "run_attempt": 1}
    selected = set(request["selection"]["suites"])
    expected_execution = {"schema": batch_execution.SCHEMA, "identity": identity, "selection": request["selection"],
        "lanes": {s.scope_lane: s.id in selected for s in policy.inventory.suites if s.scope_lane is not None},
        "suites": {s.id: s.id in selected for s in policy.inventory.suites}}
    require(bundle["execution.json"] == expected_execution, "execution artifact differs from frozen request")
    rebuilt = batch_execution.from_needs(policy, identity, request["selection"], bundle["needs.json"],
                                          aliases=ALIASES, dependencies=dependencies(policy))
    checked = batch_verdict.validate(bundle["verdict.json"], policy, identity, request["selection"])
    require(checked == rebuilt, "verdict differs from actual retained needs context")
    return checked, identity


def validate_job_observations(checked, producer, jobs):
    visibility = [s for s in producer["steps"] if s.get("name") == "Keep failed selected work visible"]
    expected_conclusion = "failure" if checked["status"] == "failed" else "skipped"
    require(len(visibility) == 1 and visibility[0].get("conclusion") == expected_conclusion
            and producer["conclusion"] == ("failure" if checked["status"] == "failed" else "success"),
            "producer business outcome contradicts recomputed verdict")
    for observation in checked["observations"]:
        name = JOB_NAMES.get(observation["job"])
        require(name is not None, "product job has no reviewed API name mapping")
        matches = [j for j in jobs if j.get("name") == PREFIX + name]
        if observation["conclusion"] == "skipped" and not matches:
            continue  # GitHub may omit unexpanded reusable skipped jobs.
        require(len(matches) == 1, "product job API evidence missing or ambiguous")
        actual, claimed = matches[0].get("conclusion"), observation["conclusion"]
        compatible = actual == claimed or claimed == "failure" and actual in {"timed_out", "action_required", "startup_failure"}
        # Only this reviewed job deliberately uses job-level continuation.
        compatible |= observation["job"] == "macos-primary" and claimed == "success" and actual == "failure"
        require(compatible, "product job API conclusion contradicts retained needs")
