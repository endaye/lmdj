#!/usr/bin/env python3

"""Two Hosts, one Catalog, one partition -- asserted as equality, not text.

Stage 11's plan asked for a Web/Native refusal-consistency table. What existed
instead was a source-string scan (`soundset_refusal_ownership_test.py`), which
can see that no Host *names* a locked reason of its own, and a per-Host suite
on each side that had its own idea of the answer:

  - `cli_test.py` carried the partition as a literal and asserted equality,
    but only for the CLI Host.
  - `creator_web_soundset.spec.mjs` asserted the browser *rendered* the strings
    `soundset_content_mismatch` and `soundset_license_ineligible` somewhere in
    a list of four. Which Set carried which token was never checked, so two
    refusals could swap their reasons and the surface would stay green.
  - The Native Host had no Sound Set coverage at all.

So the two Hosts could disagree about the same bytes and every suite would
pass. This test and its browser counterpart both measure against
`tests/fixtures/soundset/catalog-partition.json`, which is the single
expectation; nothing here restates it.

Equality, not containment, is the whole point. A Set silently promoted from
refused to published is an eligibility regression that no positive assertion
can see, and a partition file that forgot an entry would make the Host report
an extra refusal -- which equality catches and `assertIn` would not.

What this cannot express: it is the `soundset.catalog.list` partition only.
Publishable is not installable -- S11-D3 keeps the Unsupported Audio Kit on the
published side here and refuses it at install with
`soundset_audio_unsupported` -- and `soundset_manifest_invalid`,
`soundset_slot_invalid` and `soundset_occupied_conflict` are decided by other
operations. Two Hosts that agree here can still disagree at install.
"""

from __future__ import annotations

import json
from pathlib import Path
import select
import subprocess
import sys
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tests/host"))

PARTITION = json.loads(
    (REPO_ROOT / "tests/fixtures/soundset/catalog-partition.json").read_text(
        encoding="utf-8"
    )
)
RESPONSE_TIMEOUT_SECONDS = 30.0


def canonical_json(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def publish_workspace_catalog(workspace: Path) -> None:
    """Point a Workspace at the offline fixture Catalog, byte for byte.

    The same wiring `cli_test.py` uses. Nothing is injected and nothing is
    rewritten: the Host reads exactly the objects `tests/fixtures/soundset`
    publishes, so a disagreement between Hosts here is a Host disagreement and
    not a fixture difference.
    """
    catalog_root = workspace / ".lmdj-host/soundset-catalog"
    objects = catalog_root / "objects"
    objects.mkdir(parents=True)
    fixtures = REPO_ROOT / "tests/fixtures/soundset"
    for kind in ("manifest", "blob"):
        for source in sorted((fixtures / kind).iterdir()):
            if source.is_file():
                (objects / source.name).write_bytes(source.read_bytes())
    (catalog_root / "index.json").write_bytes(
        (fixtures / "catalog/index.json").read_bytes()
    )


def observed_partition(listed: dict) -> tuple[set[str], dict[str, tuple[str, str]]]:
    """`(published set_ids, {set_id: (code, reason)})` from a list result."""
    result = listed["result"]
    published = {entry["set_id"] for entry in result["sets"]}
    refused = {
        entry["set_id"]: (entry["code"], entry["reason"])
        for entry in result["refused"]
    }
    return published, refused


def expected_partition() -> tuple[set[str], dict[str, tuple[str, str]]]:
    return (
        set(PARTITION["published"]),
        {
            set_id: (value["code"], value["reason"])
            for set_id, value in PARTITION["refused"].items()
        },
    )


def assert_partition(host_name: str, listed: dict) -> None:
    assert listed["ok"] is True, (host_name, listed)
    assert listed["result"]["catalog_available"] is True, (host_name, listed)
    published, refused = observed_partition(listed)
    want_published, want_refused = expected_partition()
    assert published == want_published, (
        f"{host_name} published the wrong Sets: "
        f"missing={sorted(want_published - published)}, "
        f"unexpected={sorted(published - want_published)}"
    )
    assert refused == want_refused, (
        f"{host_name} refused differently: expected={want_refused}, "
        f"observed={refused}"
    )


def cli_list(cli: Path, workspace: Path, assembly: Path) -> dict:
    completed = subprocess.run(
        [
            str(cli),
            "--workspace", str(workspace),
            "--assembly", str(assembly),
            "query",
            "--request",
            canonical_json({"operation": "soundset.catalog.list"}),
        ],
        cwd=REPO_ROOT, check=False, capture_output=True,
    )
    assert completed.returncode == 0, (
        completed.returncode, completed.stdout, completed.stderr
    )
    return json.loads(completed.stdout.decode("utf-8"))


def native_list(
    host: Path, cli: Path, workspace: Path, assembly: Path, project: Path
) -> dict:
    """Drive the same operation through the long-lived Native Host process."""
    import native_host_test

    native_host_test.author_project(cli, workspace, assembly, project)
    process = subprocess.Popen(
        [
            str(host),
            "--workspace", str(workspace),
            "--assembly", str(assembly),
            "--project", str(project),
            "--pattern", native_host_test.STARTUP_PATTERN_ID,
            "--no-device",
        ],
        cwd=REPO_ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert process.stdin is not None and process.stdout is not None
        # The Native Host announces itself before it will answer anything.
        # Reading a request's reply without consuming this line first gets the
        # banner instead, whose `result` has none of the list fields -- which
        # looks exactly like a Host that answered a different shape.
        readable, _, _ = select.select(
            [process.stdout], [], [], RESPONSE_TIMEOUT_SECONDS
        )
        assert readable, f"Native Host never became ready; returncode={process.poll()}"
        ready = json.loads(process.stdout.readline().decode("utf-8"))
        assert ready["ok"] is True and ready["operation"] == "ready", ready
        for request in (
            {"operation": "soundset.catalog.list"},
            {"operation": "quit"},
        ):
            process.stdin.write(canonical_json(request).encode("utf-8") + b"\n")
            process.stdin.flush()
            readable, _, _ = select.select(
                [process.stdout], [], [], RESPONSE_TIMEOUT_SECONDS
            )
            assert readable, (
                f"Native Host did not answer {request['operation']}; "
                f"returncode={process.poll()}"
            )
            line = process.stdout.readline()
            assert line, (process.poll(),)
            response = json.loads(line.decode("utf-8"))
            if request["operation"] == "soundset.catalog.list":
                listed = response
        process.stdin.close()
        assert process.wait(timeout=10) == 0
        return listed
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: soundset_catalog_partition_test.py HOST CLI ASSEMBLY"
        )
    host = Path(sys.argv[1]).resolve(strict=True)
    cli = Path(sys.argv[2]).resolve(strict=True)
    assembly = Path(sys.argv[3]).resolve(strict=True)

    with tempfile.TemporaryDirectory(prefix="lmdj-soundset-partition-") as root:
        temp_root = Path(root).resolve()

        cli_workspace = temp_root / "cli-workspace"
        cli_workspace.mkdir()
        publish_workspace_catalog(cli_workspace)
        cli_listed = cli_list(cli, cli_workspace, assembly)
        assert_partition("CLI Host", cli_listed)

        native_workspace = temp_root / "native-workspace"
        native_workspace.mkdir()
        publish_workspace_catalog(native_workspace)
        native_listed = native_list(
            host, cli, native_workspace, assembly, temp_root / "native.lmdj"
        )
        assert_partition("Native Host", native_listed)

        # The pairwise assertion, not just two independent ones against the
        # file. Both Hosts drifting the same way would satisfy the two checks
        # above; this one says they answered each other identically for the
        # fields the Locked Error Reasons table freezes.
        assert observed_partition(cli_listed) == observed_partition(native_listed), (
            observed_partition(cli_listed), observed_partition(native_listed)
        )

    reasons = sorted({v["reason"] for v in PARTITION["refused"].values()})
    print(
        "sound set catalog partition: CLI and Native Host agree on "
        f"{len(PARTITION['published'])} published and "
        f"{len(PARTITION['refused'])} refused Sets carrying {reasons}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
