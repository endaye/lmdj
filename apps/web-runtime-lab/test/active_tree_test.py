#!/usr/bin/env python3

from pathlib import Path
import re


LAB_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = LAB_ROOT.parents[1]


def read(relative: str) -> str:
    path = LAB_ROOT / relative
    assert path.is_file(), f"missing active Web Runtime Lab file: {relative}"
    assert not path.is_symlink(), f"active file must not be a symlink: {relative}"
    return path.read_text(encoding="utf-8")


def read_repository(relative: str) -> str:
    path = REPOSITORY_ROOT / relative
    assert path.is_file(), f"missing repository file: {relative}"
    return path.read_text(encoding="utf-8")


def require(source: str, patterns: tuple[str, ...], label: str) -> None:
    for pattern in patterns:
        assert pattern in source, f"{label} is missing {pattern!r}"


def main() -> int:
    index = read("index.html")
    styles = read("styles.css")
    main_source = read("src/main.js")
    worklet_source = read("src/worklet.js")
    probe_core = read("src/probe-core.mjs")
    lab_readme = read("README.md")
    apps_readme = read_repository("apps/README.md")
    ci_workflow = read_repository(".github/workflows/ci.yml")

    combined = "\n".join((index, styles, main_source, worklet_source, probe_core))
    for forbidden in (
        "lmdj.patch.v1",
        "lmdj.materials.v1",
        "/Users/",
        "products/lmdj",
        "application-facade",
        "localStorage",
        "sessionStorage",
        "indexedDB",
    ):
        assert forbidden not in combined, forbidden

    require(
        index,
        (
            'id="start-audio"',
            'id="trigger-pad"',
            'id="enable-midi"',
            'id="suspend-audio"',
            'id="resume-audio"',
            'id="export-report"',
            'id="decision-status"',
            '<link rel="icon" href="data:,">',
            'type="module"',
        ),
        "index",
    )
    require(
        main_source,
        (
            "new SharedArrayBuffer",
            "Atomics.add",
            "RING_CAPACITY = 1024",
            "WRITE_INDEX",
            "READ_INDEX",
            "DROPPED_COUNT",
            "ring-full",
            "audioWorklet.addModule",
            "new AudioWorkletNode",
            "requestMIDIAccess",
            'addEventListener("visibilitychange"',
            'addEventListener("pagehide"',
            'addEventListener("pageshow"',
            'addEventListener("freeze"',
            'addEventListener("resume"',
            "processorerror",
            "getOutputTimestamp",
            "createReport",
            'decisionStatus: "pending-threshold-approval"',
        ),
        "main",
    )
    for forbidden in (
        ".manufacturer",
        ".name",
        "sysex: true",
        "data[3]",
    ):
        assert forbidden not in main_source, forbidden
    pending_position = main_source.index("pendingTriggers.set(sequence")
    publish_position = main_source.index(
        "Atomics.add(controlView, WRITE_INDEX, 1)"
    )
    assert pending_position < publish_position, (
        "pending trigger metadata must exist before the record is published"
    )

    require(
        worklet_source,
        (
            "class RuntimeProbeProcessor extends AudioWorkletProcessor",
            "WebAssembly.Module",
            "WebAssembly.Instance",
            "Atomics.load",
            "WRITE_INDEX",
            "READ_INDEX",
            "while (readIndex < writeIndex)",
            "currentFrame",
            "outputs[0][0].length",
            'registerProcessor("lmdj-web-runtime-probe"',
            "Math.min(0.15",
            "Math.max(-0.15",
        ),
        "worklet",
    )
    assert re.search(r"\b128\b", worklet_source) is None, (
        "worklet must not hard-code a 128-frame render quantum"
    )

    require(
        probe_core,
        (
            'decisionStatus: "pending-threshold-approval"',
            "physicalMeasurement: null",
        ),
        "probe core",
    )
    assert re.search(r"\bpass\s*:", probe_core) is None

    require(
        lab_readme,
        (
            "scripts/web-runtime-lab.sh test",
            "scripts/web-runtime-lab.sh serve --port 4173",
            "scripts/web-runtime-lab.sh serve-lan",
            "trusted-cert.pem",
            "Pending threshold approval",
            "not physical Touch-to-Sound evidence",
            "MIDI input names",
            "raw MIDI messages",
            "persistent browser storage",
        ),
        "lab README",
    )
    require(
        apps_readme,
        ("web-runtime-lab", "product-neutral", "experimental Host"),
        "apps README",
    )
    require(
        ci_workflow,
        (
            "web-runtime-lab:",
            'python-version: "3.11"',
            'node-version: "22"',
            "run: scripts/web-runtime-lab.sh test",
        ),
        "CI workflow",
    )

    print("web runtime lab active tree: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
