"""Workflow-side dispatch correlation only; never release/deployment approval.

The eventual consumer must authenticate the retained artifact, actual API run,
and both workflow/tooling source revisions. Self-declared receipt JSON is not
authority. Legacy manual dispatch without request_id keeps its existing path.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from .model import canonical_json


WORKFLOWS = {
    "publish-release.yml": {"tag", "release_id", "plan_sha256", "request_id"},
    "deploy-web-runtime-host.yml": {"tag", "request_id"},
    "deploy-creator-web.yml": {"tag", "request_id"},
}


class ReceiptError(ValueError):
    pass


def require(value):
    if not value:
        raise ReceiptError("why: release dispatch context is invalid; remedy: use the original exact inputs on main with a new attempt-1 dispatch; do not treat this receipt as release approval")


def numeric(value):
    require(type(value) is str and re.fullmatch(r"[1-9][0-9]*", value))
    return int(value)


def receipt(event, env, workflow, tooling_revision):
    require(workflow in WORKFLOWS and type(event) is dict)
    inputs = event.get("inputs")
    require(type(inputs) is dict and set(inputs) == WORKFLOWS[workflow]
            and all(type(v) is str for v in inputs.values()))
    require(re.fullmatch(r"[0-9a-f]{64}", inputs["request_id"])
            and re.fullmatch(r"lmdj-v(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){3}", inputs["tag"]))
    if workflow == "publish-release.yml":
        numeric(inputs["release_id"])
        require(re.fullmatch(r"[0-9a-f]{64}", inputs["plan_sha256"]))
    repository_id = numeric(env.get("GITHUB_REPOSITORY_ID"))
    actor_id = numeric(env.get("GITHUB_ACTOR_ID"))
    run_id = numeric(env.get("GITHUB_RUN_ID"))
    require(env.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
            and env.get("GITHUB_REF") == "refs/heads/main"
            and env.get("GITHUB_REPOSITORY") == "endaye/lmdj"
            and env.get("GITHUB_RUN_ATTEMPT") == "1"
            and env.get("GITHUB_WORKFLOW_REF") == f"endaye/lmdj/.github/workflows/{workflow}@refs/heads/main")
    for revision in (tooling_revision, env.get("GITHUB_SHA"), env.get("GITHUB_WORKFLOW_SHA")):
        require(type(revision) is str and re.fullmatch(r"[0-9a-f]{40}", revision))
    repo, sender = event.get("repository"), event.get("sender")
    require(type(repo) is dict and type(repo.get("id")) is int and repo["id"] == repository_id
            and repo.get("full_name") == "endaye/lmdj"
            and type(sender) is dict and type(sender.get("id")) is int and sender["id"] == actor_id
            and event.get("ref") in ("main", "refs/heads/main"))
    return {"schema": "lmdj.release-dispatch-receipt.v1", "repository": "endaye/lmdj",
            "repository_id": repository_id, "actor_id": actor_id,
            "run_id": run_id, "run_attempt": 1, "event": "workflow_dispatch",
            "ref": "refs/heads/main", "workflow": workflow,
            "head_sha": env["GITHUB_SHA"], "workflow_sha": env["GITHUB_WORKFLOW_SHA"],
            "tooling_revision": tooling_revision, "inputs": dict(inputs)}


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", choices=WORKFLOWS, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        with open(os.environ["GITHUB_EVENT_PATH"], "rb") as stream:
            raw = stream.read(1024 * 1024 + 1)
        require(len(raw) <= 1024 * 1024)
        event = json.loads(raw, object_pairs_hook=unique)
        tooling = subprocess.run(["git", "rev-parse", "HEAD"], check=True,
                                 capture_output=True, text=True).stdout.strip()
        value = receipt(event, os.environ, args.workflow, tooling)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Never overwrite a prior receipt; partial output is not valid evidence.
        with args.output.open("xb") as stream:
            stream.write(canonical_json(value))
            stream.flush()
            os.fsync(stream.fileno())
    except (ValueError, OSError, KeyError, subprocess.SubprocessError):
        print("why: dispatch receipt unavailable; remedy: retain the failed run and reconcile the original request; never infer success or blindly retry", flush=True)
        return 1
    print("Dispatch correlation recorded; publication and deployment remain unverified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
