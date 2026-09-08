#!/usr/bin/env python3

from __future__ import annotations

import re
import sys
import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PLATFORM_ROOT = REPO_ROOT / "packages/web-runtime-platform"
FORBIDDEN_APP_FILES = {
    "control_runtime.cpp",
    "control_runtime.hpp",
    "bridge.cpp",
    "manifest_gate.cpp",
    "manifest_gate.hpp",
    "web-runtime-pre.js",
}
TEXT_SUFFIXES = {".c", ".cc", ".cpp", ".h", ".hpp", ".js", ".mjs", ".py", ".tsx"}


def fail(message: str) -> None:
    raise AssertionError(message)


def index_or_fail(source: str, needle: str, start: int, what: str) -> int:
    """`str.index` raises a bare `ValueError: substring not found`, which names
    no file, no rule and no remedy, and lands on whoever just edited a table
    they did not know this file parses -- the failure mode
    `.agents/pitfalls/gate-failure-readability.md` exists for.

    Returning `.find()`'s -1 unguarded is worse than the traceback: the slice
    silently becomes a different region, so the check keeps running against
    text that is not the structure it believes it is reading, and reports a
    confident answer about nothing.

    What this guard cannot express, measured rather than assumed: it only fires
    when the terminator is missing from the rest of the file. Delete a
    terminator mid-file and the search finds the *next* one instead, so the
    slice over-reads into unrelated source and no -1 ever appears. That case is
    caught downstream -- the declared `std::array` length stops matching the
    entries found, and the over-read pulls in strings that fail the parity
    assertion -- but it is caught by arithmetic that happens to disagree, not by
    this guard. A structure whose over-read happened to stay consistent would
    pass. Bounding each parse to its own braces would close it; that needs a
    brace matcher, which is more parser than this file should own.
    """
    found = source.find(needle, start)
    if found < 0:
        fail(
            f"{what}: expected to find {needle!r} terminating the structure "
            "this check parses, and it is missing, so the source is malformed "
            "or its shape changed. remedy: restore the terminator, or update "
            "this parser to the new shape -- do not leave it unparsed, because "
            "an unparsed inventory is not a checked one"
        )
    return found


def text_files(root: Path):
    excluded = {"node_modules", "build", "dist", ".next"}
    for directory, names, files in os.walk(root):
        names[:] = [name for name in names if name not in excluded]
        for name in files:
            path = Path(directory) / name
            if path.suffix in TEXT_SUFFIXES:
                yield path


def bridge_supported_operations() -> list[str]:
    """The operations `bridge.cpp` will dispatch. Anything absent is rejected
    with `bridge_protocol_error()` before it can reach `control_runtime`."""
    source = (PLATFORM_ROOT / "src/bridge.cpp").read_text(encoding="utf-8")
    match = re.search(
        r"bool supported_operation\([^)]*\)\s*\{\s*"
        r"static constexpr std::array<std::string_view,\s*(\d+)>\s*operations\{",
        source,
    )
    if match is None:
        fail(
            "cannot locate bridge.cpp supported_operation allowlist; "
            "remedy: keep the `static constexpr std::array<std::string_view, N> "
            "operations{` form this check parses, or update the parser with it"
        )
    body = source[
        match.end() : index_or_fail(
            source, "};", match.end(), "bridge.cpp supported_operation allowlist"
        )
    ]
    operations = re.findall(r'"([^"]+)"', body)
    declared = int(match.group(1))
    if declared != len(operations):
        fail(
            f"bridge.cpp allowlist declares {declared} operations but lists "
            f"{len(operations)}; remedy: correct the std::array length so the "
            "compiler keeps counting for you"
        )
    return operations


def protocol_host_operations() -> list[str]:
    """The operations `protocol.mjs` will send. The browser half of the same
    inventory `bridge.cpp` gates."""
    source = (PLATFORM_ROOT / "web/protocol.mjs").read_text(encoding="utf-8")
    match = re.search(r"HOST_OPERATIONS\s*=\s*Object\.freeze\(\[", source)
    if match is None:
        fail(
            "cannot locate HOST_OPERATIONS in protocol.mjs; remedy: keep the "
            "`Object.freeze([` form this check parses, or update the parser"
        )
    body = source[
        match.end() : index_or_fail(
            source, "])", match.end(), "protocol.mjs HOST_OPERATIONS"
        )
    ]
    return re.findall(r'"([^"]+)"', body)


def control_runtime_soundset_operations() -> list[str]:
    """The Sound Set operations `control_runtime.cpp` serves. This is the
    inventory that is written when a Facade operation is wired up, and it is
    the one that gets ahead of the two transport inventories."""
    source = (PLATFORM_ROOT / "src/control_runtime.cpp").read_text(encoding="utf-8")
    marker = "soundset_operations{"
    if marker not in source:
        fail(
            "cannot locate control_runtime.cpp soundset_operations table; "
            "remedy: keep the `soundset_operations{` map form this check "
            "parses, or update the parser with it"
        )
    start = index_or_fail(
        source, marker, 0, "control_runtime.cpp soundset_operations table"
    ) + len(marker)
    body = source[
        start : index_or_fail(
            source, "};", start, "control_runtime.cpp soundset_operations table"
        )
    ]
    return re.findall(r'\{"([^"]+)",\s*(?:true|false)\}', body)


def check_served_operations_are_reachable() -> None:
    """Every operation `control_runtime` serves must be admitted by
    `bridge.cpp` and sendable by `protocol.mjs`, and the two transport
    inventories must agree with each other.

    The ordering matters and is the whole point. `soundset.audition` (#799) was
    served by `control_runtime.cpp` -- a payload validator and a deadline entry,
    both written -- and was in *neither* transport inventory. Because it was
    absent from both, the two transports agreed with each other perfectly, so
    comparing only those two is blind to exactly this defect. It is caught by
    binding them to what is actually served.

    The failure it produces is silent rather than loud: `supported_operation`
    rejects an unlisted operation with `bridge_protocol_error()`, so the served
    code looks present, is covered by its own `control_runtime` tests, which
    call `dispatch()` directly and never cross the bridge, and can never run in
    the product.

    What this check cannot express: it reads the Sound Set table only. An
    operation served by one of `control_runtime`'s many `if (operation == ...)`
    branches is outside it, because those branches are not an enumerable
    inventory. Extending this to them needs the branches to become a table
    first -- until then, a non-Sound-Set operation can repeat this defect.
    """
    bridge = bridge_supported_operations()
    protocol = protocol_host_operations()
    served = control_runtime_soundset_operations()
    if not served:
        fail(
            "parsed zero operations from control_runtime.cpp soundset_operations; "
            "remedy: a check that finds nothing proves nothing -- fix the parser"
        )
    for label, names in (("bridge.cpp", bridge), ("protocol.mjs", protocol)):
        if sorted(set(names)) != sorted(names):
            fail(f"{label} repeats an operation in its inventory: {sorted(names)}")

    unreachable = sorted(
        name
        for name in served
        if name not in set(bridge) or name not in set(protocol)
    )
    if unreachable:
        fail(
            "control_runtime serves operations the Web Host cannot deliver: "
            f"{unreachable}. Each has a handler and is rejected before reaching "
            "it, so its own tests pass and the product cannot use it. "
            "remedy: add each to bridge.cpp's supported_operation allowlist "
            "(and its std::array length) and to HOST_OPERATIONS in protocol.mjs"
        )

    bridge_only = sorted(set(bridge) - set(protocol))
    protocol_only = sorted(set(protocol) - set(bridge))
    if bridge_only or protocol_only:
        fail(
            "bridge.cpp and protocol.mjs disagree about the Host operation set. "
            f"Admitted by bridge.cpp but never sent: {bridge_only or 'none'}. "
            f"Sent by protocol.mjs but rejected by bridge.cpp: "
            f"{protocol_only or 'none'}. "
            "remedy: add the operation to both inventories, or remove it from "
            "both; a one-sided entry is unreachable in one direction"
        )


def main() -> int:
    check_served_operations_are_reachable()

    app_owned = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in text_files(REPO_ROOT / "apps")
        if path.name in FORBIDDEN_APP_FILES
    )
    if app_owned:
        fail("shared Web Runtime sources remain app-owned: " + ", ".join(app_owned))

    for path in PLATFORM_ROOT.rglob("*"):
        if path.is_file() and path.suffix in {".css", ".scss", ".sass", ".less"}:
            fail(f"Platform package owns product presentation: {path}")

    forbidden_native_patterns = {
        r"(?:from|require\s*\()\s*['\"]react": "React dependency",
        r"\b(?:document|HTMLElement|CSSStyleSheet)\b": "DOM or CSS ownership",
        r"lmdj\.web-runtime-host\.distribution": "diagnostic distribution identity",
        r"\b(?:diagnostic-project|creator-web)\b": "product Host identity",
    }
    for production_root in (PLATFORM_ROOT / "include", PLATFORM_ROOT / "src"):
        for path in text_files(production_root):
            source = path.read_text(encoding="utf-8")
            for pattern, label in forbidden_native_patterns.items():
                if re.search(pattern, source, re.IGNORECASE):
                    fail(f"{label} entered Platform package: {path}")

    forbidden_web_patterns = {
        r"(?:from|require\s*\()\s*['\"]react": "React dependency",
        r"\b(?:getElementById|querySelectorAll|CSSStyleSheet)\b": (
            "product DOM presentation"
        ),
        r"\b(?:classList|innerHTML)\b": "product DOM mutation",
        r"lmdj\.web-runtime-host\.distribution": "diagnostic distribution identity",
        r"\b(?:diagnostic-project|creator-web)\b": "product Host identity",
    }
    for path in text_files(PLATFORM_ROOT / "web"):
        source = path.read_text(encoding="utf-8")
        for pattern, label in forbidden_web_patterns.items():
            if re.search(pattern, source, re.IGNORECASE):
                fail(f"{label} entered Platform web module: {path}")

    browser_owned_sources = [
        *text_files(PLATFORM_ROOT / "web"),
        PLATFORM_ROOT / "src" / "web-runtime-pre.js",
    ]
    for path in browser_owned_sources:
        if re.search(r"\bproject_path\b", path.read_text(encoding="utf-8")):
            fail(f"browser transport owns a Project bundle path: {path}")

    transport_source = (
        PLATFORM_ROOT / "src" / "web-runtime-pre.js"
    ).read_text(encoding="utf-8")
    for required in (
        "options.signal.addEventListener(\"abort\"",
        "options.cancelQuery === true",
        "abortPendingRequest(request.request_id, pending)",
        "lmdj_web_host_cancel_query",
        "pending.abortError",
        "pending.abortSignal.removeEventListener(\"abort\"",
        "const sidecarPointer = sidecar.byteLength === 0",
        "HEAPU8.set(sidecar, sidecarPointer)",
        '["number", "number", "number", "number", "number"]',
        "if (sidecarPointer !== 0) _free(sidecarPointer)",
    ):
        if required not in transport_source:
            fail("formal Host transport lacks settled request cancellation: " + required)

    creator_root = REPO_ROOT / "apps" / "creator-web"
    if creator_root.exists():
        for path in text_files(creator_root):
            source = path.read_text(encoding="utf-8")
            if re.search(r"diagnostic[_-]client\.mjs", source, re.IGNORECASE):
                fail(f"Creator imports diagnostic-only client: {path}")

    formal_host_main = (
        REPO_ROOT / "apps" / "web-runtime-host" / "src" / "main.mjs"
    )
    formal_host_source = formal_host_main.read_text(encoding="utf-8")
    for required in (
        "recordPerformanceEvent: session.recordPerformanceEvent",
        "requestPerformancePatternLaunch: session.requestPerformancePatternLaunch",
    ):
        if required not in formal_host_source:
            fail("formal Host lacks thin Performance bridge: " + required)
    forbidden_performance_authority = {
        r"\b(?:Date\.now|performance\.now)\s*\(": "wall-clock authority",
        r"\b(?:runtime_frame|target_tick|effective_tick|input_sequence)\b": (
            "Performance time or sequence authority"
        ),
        r"\b(?:coalesc|last[-_ ]write[-_ ]wins?|deduplicat)": (
            "semantic gesture coalescing"
        ),
        r"\b(?:fx_chain|effect_order|reorder_effect)\b": "FX order authority",
        r"\b(?:pattern_slots|project_truth|resolve_pattern)\b": (
            "Pattern-slot truth authority"
        ),
        r"\b(?:resolve_replay|replay_cursor|replay_tick)\b": (
            "replay progression authority"
        ),
        r"\b(?:artifact_digest|recovery_fingerprint)\b": (
            "Artifact or recovery identity authority"
        ),
    }
    for pattern, label in forbidden_performance_authority.items():
        if re.search(pattern, formal_host_source, re.IGNORECASE):
            fail(f"{label} entered formal Host JavaScript: {formal_host_main}")

    direct_project_io = re.compile(
        r"(?:lmdj/project_io/|\blmdj::project_io\b|\blmdj_project_io\b|"
        r"\b(?:ProjectStore|TakeJournal|ProjectStoragePlatform)\b)"
    )
    for host in ("web-runtime-host", "creator-web"):
        root = REPO_ROOT / "apps" / host
        if not root.exists():
            continue
        for production_root in (root / "include", root / "src"):
            if not production_root.exists():
                continue
            for path in text_files(production_root):
                if direct_project_io.search(path.read_text(encoding="utf-8")):
                    fail(f"Host bypasses Application Facade for Project I/O: {path}")
        cmake = root / "CMakeLists.txt"
        if cmake.is_file() and direct_project_io.search(cmake.read_text(encoding="utf-8")):
            fail(f"Host links Project I/O directly: {cmake}")

    print("web runtime platform source boundary: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"web runtime platform source boundary: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
