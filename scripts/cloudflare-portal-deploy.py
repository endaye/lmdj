#!/usr/bin/env python3
"""Publish a Git-built Portal through a verified Cloudflare version Preview."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from urllib.request import Request, urlopen

ACCOUNT = "0b62b8881c07f48f7935f5380a1f55db"
WORKER = "docs"
ROOT = Path(__file__).resolve().parents[1]


def smoke_receipt(output, revision, base_url):
    """Retain only a closed, identity-matched successful smoke receipt."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError()
            result[key] = value
        return result
    try:
        receipt = json.loads(output.strip().split("\n")[-1], object_pairs_hook=unique)
        if (type(receipt) is not dict or set(receipt) != {"schema", "revision", "pages"}
                or receipt["schema"] != "lmdj.release-changelog-smoke.v1"
                or receipt["revision"] != revision or type(receipt["pages"]) is not list
                or not receipt["pages"]):
            raise ValueError()
        routes = set()
        for page in receipt["pages"]:
            if type(page) is not dict or set(page) != {"route", "url", "source_sha256", "content_sha256", "response_sha256", "response_bytes"}:
                raise ValueError()
            route = page["route"]
            if (type(route) is not str or re.fullmatch(r"/releases/(?:(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){3}/)?", route) is None
                    or route in routes or page["url"] != base_url.rstrip("/") + route):
                raise ValueError()
            routes.add(route)
            for key in ("source_sha256", "content_sha256", "response_sha256"):
                if type(page[key]) is not str or re.fullmatch(r"[0-9a-f]{64}", page[key]) is None:
                    raise ValueError()
            if type(page["response_bytes"]) is not int or not 0 < page["response_bytes"] <= 8 * 1024 * 1024:
                raise ValueError()
        if "/releases/" not in routes:
            raise ValueError()
        return receipt
    except (ValueError, TypeError, KeyError, AttributeError, IndexError):
        raise RuntimeError("why: Portal smoke receipt is absent or mismatched; remedy: reconcile the exact Git revision and deployment URL before proceeding") from None


def publish():
    if os.environ.get("GITHUB_EVENT_NAME") != "push" or os.environ.get("GITHUB_REF") != "refs/heads/main":
        raise RuntimeError("Portal production requires a main push; run the Git-triggered workflow")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if revision != os.environ.get("GITHUB_SHA"):
        raise RuntimeError("checkout differs from the triggering SHA; check out github.sha")
    token = os.environ["CLOUDFLARE_API_TOKEN"]
    evidence = {"git_revision": revision, "worker": WORKER, "status": "started"}
    evidence_path = Path(os.environ["RUNNER_TEMP"]) / f"cloudflare-portal-{os.environ['GITHUB_RUN_ID']}.json"
    base = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/workers/"

    def api(path, body=None):
        request = Request(base + path, headers={"Authorization": "Bearer " + token,
                          "Content-Type": "application/json"},
                          data=None if body is None else json.dumps(body).encode())
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
        if not result.get("success"):
            raise RuntimeError("Cloudflare request failed; inspect the sanitized workflow evidence")
        return result["result"]

    def state():
        return api(f"scripts/{WORKER}/deployments")["deployments"]

    def smoke(url):
        env = {k: v for k, v in os.environ.items() if k not in {"CLOUDFLARE_API_TOKEN", "GITHUB_TOKEN"}}
        env["PORTAL_REVISION"] = revision
        result = subprocess.run(["node", "scripts/smoke.mjs", url], cwd=ROOT / "apps/docs-site",
                                env=env, check=True, timeout=240, stdout=subprocess.PIPE, text=True)
        return smoke_receipt(result.stdout, revision, url)

    exists = WORKER in {s["id"] for s in api("scripts")}
    prior = state() if exists else []
    prior_route = api(f"scripts/{WORKER}/subdomain") if exists else {"enabled": False, "previews_enabled": True}
    evidence["prior"] = [{"id": x["id"], "versions": x["versions"]} for x in prior[:1]]
    evidence["prior_route"] = prior_route
    version = None
    promoted = False
    try:
        with tempfile.TemporaryDirectory(prefix="portal-upload-") as directory:
            config = json.loads((ROOT / "apps/docs-site/deploy/wrangler.json").read_text())
            config["workers_dev"] = False
            config["assets"]["directory"] = str(ROOT / "apps/docs-site/build")
            config_path = Path(directory) / "wrangler.json"
            config_path.write_text(json.dumps(config))
            command = ["node", os.environ["WRANGLER_JS"]]
            command += ["versions", "upload"] if exists else ["deploy"]
            result = subprocess.run(command + ["--config", str(config_path)], cwd=directory,
                                    capture_output=True, text=True, timeout=300)
            output = (result.stdout + result.stderr).replace(token, "[REDACTED]")
            print(output)
            result.check_returncode()
            match = re.search(r"(?:Worker|Current) Version ID: ([0-9a-f-]{36})", output)
            if not match:
                raise RuntimeError("upload returned no version identity; reconcile Worker versions before retry")
            version = match[1]
        evidence["version_id"] = version
        route = api(f"scripts/{WORKER}/subdomain")
        api(f"scripts/{WORKER}/subdomain", {"enabled": route["enabled"], "previews_enabled": True})
        preview = f"https://{version[:8]}-{WORKER}.lmdj.workers.dev"
        receipt = smoke(preview)
        evidence["preview"] = {"url": preview, "status": "passed", "changelogs": receipt}
        current = state()
        if exists and current != prior:
            raise RuntimeError("active deployment changed during preview; reconcile the other deployment")
        if not exists and current[0]["versions"] != [{"version_id": version, "percentage": 100}]:
            raise RuntimeError("new Worker changed during preview; reconcile before publication")
        promoted = True
        api(f"scripts/{WORKER}/deployments", {"strategy": "percentage", "versions": [{"version_id": version, "percentage": 100}]})
        api(f"scripts/{WORKER}/subdomain", {"enabled": True, "previews_enabled": True})
        for attempt in range(4):
            try:
                receipt = smoke("https://docs.lmdj.workers.dev")
                break
            except subprocess.CalledProcessError:
                if attempt == 3:
                    raise
                time.sleep(5)
        if state()[0]["versions"] != [{"version_id": version, "percentage": 100}]:
            raise RuntimeError("active version changed after verification; inspect the concurrent deployment")
        evidence["production"] = {"url": "https://docs.lmdj.workers.dev", "status": "passed", "changelogs": receipt}
        evidence["status"] = "passed"
    except BaseException:
        evidence["status"] = "failed"
        if promoted and state()[0]["versions"] == [{"version_id": version, "percentage": 100}]:
            if prior:
                api(f"scripts/{WORKER}/deployments", {"strategy": "percentage", "versions": prior[0]["versions"]})
            api(f"scripts/{WORKER}/subdomain", prior_route)
            evidence["recovery"] = {"deployment": state()[0]["versions"], "route": api(f"scripts/{WORKER}/subdomain")}
        raise
    finally:
        evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")


if __name__ == "__main__":
    publish()
