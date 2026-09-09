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
import shutil
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
BASE_TIMEOUT_SECONDS = 30.0
INSTALL_REFUSAL = PARTITION["install_refusal"]
UNSUPPORTED_SET_ID = INSTALL_REFUSAL["set_id"]


def scaled_timeout(executable: Path) -> float:
    """`BASE_TIMEOUT_SECONDS`, multiplied for a sanitizer build.

    Same shape and same multipliers as `cli_test.configured_timeout`. A fixed
    deadline here would make the sanitizer lanes -- the ones where the timing
    is actually stressed -- fail as timeouts rather than as whatever they
    caught, which is the least readable failure this test could produce.
    """
    cache = (executable.parent.parent / "CMakeCache.txt").read_text(
        encoding="utf-8"
    )
    sanitizer = next(
        (
            line.removeprefix("LMDJ_SANITIZER:STRING=")
            for line in cache.splitlines()
            if line.startswith("LMDJ_SANITIZER:STRING=")
        ),
        "none",
    )
    return BASE_TIMEOUT_SECONDS * {"address": 3.0, "thread": 4.0}.get(
        sanitizer, 1.0
    )


def uuid_for(suffix: int) -> str:
    return f"00000000-0000-4000-8000-{suffix:012d}"


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


def cli_request(
    cli: Path,
    workspace: Path,
    assembly: Path,
    surface: str,
    request: dict,
    expected_exit: int = 0,
) -> dict:
    completed = subprocess.run(
        [
            str(cli),
            "--workspace", str(workspace),
            "--assembly", str(assembly),
            surface,
            "--request",
            canonical_json(request),
        ],
        cwd=REPO_ROOT, check=False, capture_output=True,
        timeout=scaled_timeout(cli),
    )
    assert completed.returncode == expected_exit, (
        completed.returncode, completed.stdout, completed.stderr
    )
    return json.loads(completed.stdout.decode("utf-8"))


def cli_list(cli: Path, workspace: Path, assembly: Path) -> dict:
    return cli_request(
        cli, workspace, assembly, "query",
        {"operation": "soundset.catalog.list"},
    )


def install_request(project: Path, revision: int, command_id: str) -> dict:
    """Install the Set that lists as publishable and refuses at install.

    S11-D3 keeps the Unsupported Audio Kit on the published side of the list
    partition, so this is the leg that proves publishable is not installable --
    and that both Hosts say so with the same locked token and the same
    `slot_index`, which is the field that names *why*.
    """
    return {
        "operation": "soundset.install",
        "project_path": str(project),
        "command_id": command_id,
        "expected_revision": revision,
        "bank_id": 2,
        "set_id": UNSUPPORTED_SET_ID,
        "version": INSTALL_REFUSAL["version"],
        "manifest_sha256": INSTALL_REFUSAL["manifest_sha256"],
    }


def assert_install_refusal(host_name: str, refused: dict) -> None:
    assert refused["ok"] is False, (host_name, refused)
    assert refused["error"]["code"] == INSTALL_REFUSAL["code"], (
        f"{host_name} install code: expected {INSTALL_REFUSAL['code']}, "
        f"observed {refused['error']['code']}"
    )
    assert refused["error"]["details"] == {
        "reason": INSTALL_REFUSAL["reason"],
        "slot_index": INSTALL_REFUSAL["slot_index"],
    }, (
        f"{host_name} install details: expected "
        f"{{'reason': {INSTALL_REFUSAL['reason']!r}, "
        f"'slot_index': {INSTALL_REFUSAL['slot_index']}}}, "
        f"observed {refused['error']['details']}"
    )


def assert_offline_degradation(host_name: str, listed: dict) -> None:
    """A Catalog that has gone away degrades; it does not refuse Set by Set.

    The distinction matters because `catalog_unavailable` is a per-Set refusal
    token, and answering with four of them here instead of an empty `refused`
    would be a Host inventing a refusal the Facade did not make.
    """
    assert listed["ok"] is True, (host_name, listed)
    assert listed["result"]["catalog_available"] is False, (host_name, listed)
    assert listed["result"]["refused"] == [], (host_name, listed["result"])


def native_requests(
    host: Path,
    cli: Path,
    workspace: Path,
    assembly: Path,
    project: Path,
    requests: tuple[dict, ...],
) -> list[dict]:
    """Drive requests through the long-lived Native Host and return the replies.

    One process for the whole sequence, because that is what the Native Host
    is: a session, not a command. A refusal that only reproduces on a fresh
    process would be a different defect from the one this looks for.
    """
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
            [process.stdout], [], [], scaled_timeout(host)
        )
        assert readable, f"Native Host never became ready; returncode={process.poll()}"
        ready = json.loads(process.stdout.readline().decode("utf-8"))
        assert ready["ok"] is True and ready["operation"] == "ready", ready
        replies: list[dict] = [ready]
        for request in (*requests, {"operation": "quit"}):
            process.stdin.write(canonical_json(request).encode("utf-8") + b"\n")
            process.stdin.flush()
            readable, _, _ = select.select(
                [process.stdout], [], [], scaled_timeout(host)
            )
            assert readable, (
                f"Native Host did not answer {request['operation']}; "
                f"returncode={process.poll()}"
            )
            line = process.stdout.readline()
            assert line, (process.poll(),)
            response = json.loads(line.decode("utf-8"))
            if request["operation"] != "quit":
                replies.append(response)
        process.stdin.close()
        assert process.wait(timeout=scaled_timeout(host)) == 0
        return replies
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=scaled_timeout(host))


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

        # Leg 2 -- the same Set that lists as publishable is refused at
        # install, with the same code, the same locked token and the same
        # slot_index on both Hosts.
        cli_project = temp_root / "cli.lmdj"
        import native_host_test

        native_host_test.author_project(cli, cli_workspace, assembly, cli_project)
        cli_revision = cli_request(
            cli, cli_workspace, assembly, "query",
            {"operation": "project.inspect", "project_path": str(cli_project)},
        )["project_revision"]
        cli_install = cli_request(
            cli, cli_workspace, assembly, "command",
            install_request(cli_project, cli_revision, uuid_for(928)),
            expected_exit=2,
        )
        assert_install_refusal("CLI Host", cli_install)

        # Leg 3 -- a Catalog that has gone away degrades rather than refusing
        # Set by Set.
        shutil.rmtree(cli_workspace / ".lmdj-host/soundset-catalog")
        assert_offline_degradation("CLI Host", cli_list(cli, cli_workspace, assembly))

        native_workspace = temp_root / "native-workspace"
        native_workspace.mkdir()
        publish_workspace_catalog(native_workspace)
        native_project = temp_root / "native.lmdj"
        # The Native Host holds the Project open and announces the revision it
        # opened at. Guessing one instead would make this leg fail on a
        # revision conflict rather than on the audio decision it compares.
        ready, native_listed = native_requests(
            host, cli, native_workspace, assembly, native_project,
            ({"operation": "soundset.catalog.list"},),
        )
        assert_partition("Native Host", native_listed)
        _, native_install = native_requests(
            host, cli, native_workspace, assembly,
            temp_root / "native-install.lmdj",
            (
                install_request(
                    temp_root / "native-install.lmdj",
                    ready["result"]["project_revision"],
                    uuid_for(929),
                ),
            ),
        )
        assert_install_refusal("Native Host", native_install)

        shutil.rmtree(native_workspace / ".lmdj-host/soundset-catalog")
        _, native_offline = native_requests(
            host, cli, native_workspace, assembly,
            temp_root / "native-offline.lmdj",
            ({"operation": "soundset.catalog.list"},),
        )
        assert_offline_degradation("Native Host", native_offline)

        # The pairwise assertion, not just two independent ones against the
        # file. Both Hosts drifting the same way would satisfy the two checks
        # above; this one says they answered each other identically for the
        # fields the Locked Error Reasons table freezes.
        assert observed_partition(cli_listed) == observed_partition(native_listed), (
            observed_partition(cli_listed), observed_partition(native_listed)
        )

    reasons = sorted(
        {v["reason"] for v in PARTITION["refused"].values()}
        | {INSTALL_REFUSAL["reason"]}
    )
    print(
        "sound set catalog partition: CLI and Native Host agree on "
        f"{len(PARTITION['published'])} published and "
        f"{len(PARTITION['refused'])} refused Sets, on the install refusal of "
        "the one publishable Set that is not installable, and on degrading "
        f"rather than refusing when the Catalog is gone; reasons {reasons}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
