#!/usr/bin/env python3

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def combined_text(paths: list[Path]) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def main() -> int:
    require(
        len(sys.argv) in {2, 3},
        "usage: web_host_source_boundary_test.py HOST_ROOT [LINK_EVIDENCE]",
    )
    host_root = Path(sys.argv[1]).resolve()
    source_root = host_root / "src"
    host_cmake = host_root / "CMakeLists.txt"
    repo_root = host_root.parents[1]
    product_cmake = repo_root / "products" / "lmdj" / "CMakeLists.txt"
    product_assembly = repo_root / "products" / "lmdj" / "assembly.json"
    root_cmake = repo_root / "CMakeLists.txt"
    realtime_failure_spec = (
        repo_root / "tests" / "platform" / "web" / "audio" / "realtime_failure.spec.mjs"
    )
    web_runtime_host_script = repo_root / "scripts" / "web-runtime-host.sh"
    web_toolchain_script = repo_root / "scripts" / "web-toolchain-conformance.sh"
    realtime_audio_worklet = (
        repo_root
        / "packages"
        / "audio-runtime"
        / "src"
        / "web"
        / "realtime_audio_worklet.cpp"
    )

    required_files = [
        host_cmake,
        source_root / "control_runtime.hpp",
        source_root / "control_runtime.cpp",
        source_root / "bridge.cpp",
        product_cmake,
        product_assembly,
        root_cmake,
        realtime_failure_spec,
        web_runtime_host_script,
        web_toolchain_script,
        realtime_audio_worklet,
    ]
    for path in required_files:
        require(path.is_file(), f"required Task 6 source is missing: {path}")

    source_files = sorted(source_root.glob("*.cpp")) + sorted(
        source_root.glob("*.hpp")
    )
    source = combined_text(source_files)
    control_runtime_source = (source_root / "control_runtime.cpp").read_text(
        encoding="utf-8"
    )
    bridge_source = (source_root / "bridge.cpp").read_text(encoding="utf-8")
    cmake = combined_text([host_cmake, root_cmake, product_cmake])

    forbidden_source = {
        r"lmdj/project_io/": "direct Project I/O include",
        r"\blmdj::project_io\b": "direct Project I/O namespace use",
        r"\b(?:ProjectStore|TakeJournal|ProjectStoragePlatform)\b": (
            "Project parser/storage surface"
        ),
        r"<(?:fcntl\.h|unistd\.h|sys/stat\.h)>": "direct POSIX surface",
        r"emscripten/wasmfs\.h|\bwasmfs_|\blmdj_opfs_": "direct OPFS surface",
        r"\bstd::(?:i|o)fstream\b|filesystem::directory_iterator": (
            "direct Project filesystem traversal"
        ),
        r"manifest\.json|events\.jsonl|transaction\.json|journal\.jsonl": (
            "Project bundle layout knowledge"
        ),
        r"lmdj\.patch\.v1|lmdj\.materials\.v1": "retired Contract",
        r"record\.(?:begin|stop|commit)": "retired Capture operation spelling",
        r"lmdj/providers/|providers/local-|\blocal_proof_": (
            "Product-specific Provider wiring"
        ),
        r"emscripten_proxy_sync|emscripten::ProxyingQueue|MAIN_THREAD_EM_ASM|"
        r"\bEM_ASM\b": "forbidden main-thread/proxy shortcut",
    }
    for pattern, description in forbidden_source.items():
        require(
            re.search(pattern, source) is None,
            f"{description} found in Web Host production source",
        )

    forbidden_cmake = {
        r"(?:lmdj::project_io|lmdj_project_io)": "direct Project I/O link",
        r"lmdj_provider_local_|providers/local-": "Product Provider link in Host CMake",
    }
    host_cmake_text = host_cmake.read_text(encoding="utf-8")
    for pattern, description in forbidden_cmake.items():
        require(
            re.search(pattern, host_cmake_text) is None,
            f"{description} found",
        )

    product_cmake_text = product_cmake.read_text(encoding="utf-8")
    product_assembly_data = json.loads(product_assembly.read_text(encoding="utf-8"))
    require(
        isinstance(product_assembly_data, dict),
        "Product Assembly must contain a JSON object",
    )
    assembly_hosts = product_assembly_data.get("hosts")
    require(
        isinstance(assembly_hosts, list),
        "Product Assembly hosts array is missing",
    )
    web_host_is_assembled = any(
        isinstance(host, dict) and host.get("id") == "web-runtime-host"
        for host in assembly_hosts
    )
    web_product_links = re.findall(
        r"target_link_libraries\s*\(\s*lmdj_web_runtime_host\b(.*?)\)",
        product_cmake_text,
        re.DOTALL,
    )
    require(
        len(web_product_links) <= 1,
        "Product Assembly has duplicate Web Host link blocks",
    )
    require(
        bool(web_product_links) == web_host_is_assembled,
        "Product Assembly Web Host link presence does not match Assembly membership",
    )
    for links in web_product_links:
        for pattern, description in forbidden_cmake.items():
            require(
                re.search(pattern, links) is None,
                f"{description} found in Product-owned Web Host links",
            )

    require(
        "<lmdj/facade/application.hpp>" in source,
        "Control Runtime must enter Project behavior through Application Facade",
    )
    require(
        "emscripten_proxy_async" in source,
        "guarded asynchronous Control pthread proxy is missing",
    )
    require(
        re.search(
            r"#if\s+defined\(__EMSCRIPTEN__\).*?emscripten_proxy_async",
            source,
            re.DOTALL,
        )
        is not None,
        "emscripten_proxy_async must be inside an Emscripten guard",
    )
    require("pthread_self" in source, "Control pthread identity capture is missing")
    require(
        "emscripten_exit_with_live_runtime" in source,
        "Control pthread must keep the Emscripten runtime alive for proxy work",
    )
    root_cmake_text = root_cmake.read_text(encoding="utf-8")
    require(
        "add_subdirectory(apps/web-runtime-host)" in root_cmake_text,
        "root CMake does not include the formal Web Host",
    )
    require(
        re.search(
            r"if\s*\(EMSCRIPTEN\).*?add_compile_options\s*\(\s*-pthread\s*\)",
            root_cmake_text,
            re.DOTALL,
        )
        is not None,
        "all Emscripten translation units must compile with -pthread",
    )
    require(
        "src/control_runtime.cpp" in host_cmake_text
        and "src/bridge.cpp" in host_cmake_text,
        "Host CMake does not compile the actual Task 6 sources",
    )
    outcome_drain = re.search(
        r"ControlRuntime::drain_outcomes\(\)\s*\{(.*?)\n\}",
        control_runtime_source,
        re.DOTALL,
    )
    require(outcome_drain is not None, "Control outcome drain is missing")
    require(
        "result.insert" not in outcome_drain.group(1),
        "Control outcome drain must not form a runtime-count iterator endpoint "
        "for a fixed array",
    )
    require(
        re.search(
            r"for\s*\([^)]*<\s*count[^)]*\).*?result\.push_back",
            outcome_drain.group(1),
            re.DOTALL,
        )
        is not None,
        "Control outcome drain must copy the bounded fixed array explicitly",
    )
    capture_finish = re.search(
        r"foundation::Result<void> finish_capture\(bool make_committable\)\s*"
        r"\{(.*?)\n  \}",
        control_runtime_source,
        re.DOTALL,
    )
    require(capture_finish is not None, "Control capture finish barrier is missing")
    capture_finish_body = capture_finish.group(1)
    require(
        "std::this_thread::yield()" not in capture_finish_body,
        "Emscripten capture barriers must not busy-wait with a non-yielding "
        "sched_yield implementation",
    )
    require(
        "coordinator->await_quiescent" in capture_finish_body,
        "capture barriers must request an acknowledged AudioWorklet quantum",
    )
    require(
        "coordinator->begin_rendering" in capture_finish_body,
        "successful take.stop must resume AudioWorklet rendering after the "
        "acknowledged final quantum",
    )
    realtime_audio_worklet_source = realtime_audio_worklet.read_text(
        encoding="utf-8"
    )
    quiescence_wait = re.search(
        r"RealtimeAudioWorklet::await_quiescent\([^)]*\)\s*noexcept\s*"
        r"\{(.*?)\n\}",
        realtime_audio_worklet_source,
        re.DOTALL,
    )
    require(
        quiescence_wait is not None,
        "AudioWorklet quiescence barrier is missing",
    )
    require(
        "std::this_thread::yield()" not in quiescence_wait.group(1),
        "AudioWorklet quiescence must not busy-wait with the pinned "
        "non-yielding sched_yield implementation",
    )
    require(
        "std::this_thread::sleep_for" in quiescence_wait.group(1),
        "AudioWorklet quiescence must release the Control Worker while "
        "awaiting the render-thread acknowledgement",
    )
    diagnostic_drain = re.search(
        r"void drain_outcomes_on_control\(void\*\)\s+noexcept\s*\{(.*?)\n\}",
        bridge_source,
        re.DOTALL,
    )
    require(diagnostic_drain is not None, "diagnostic outcome drain is missing")
    require(
        "&drain_outcomes_on_control" not in diagnostic_drain.group(1),
        "diagnostic outcome drain must not self-requeue while a mirror is writing",
    )
    failure_spec_text = realtime_failure_spec.read_text(encoding="utf-8")
    submission_helper = re.search(
        r"window\.__lmdjRealtimeFailureSubmit\s*=\s*async\s*"
        r"\([^)]*\)\s*=>\s*\{(.*?)\n\s{4}\};",
        failure_spec_text,
        re.DOTALL,
    )
    require(submission_helper is not None, "realtime failure submit helper is missing")
    helper_body = submission_helper.group(1)
    direct_submit = re.search(
        r"ccall\(\s*[\"']lmdj_web_host_submit[\"']\s*,\s*[\"']number[\"']"
        r"\s*,\s*\[[^\]]*\]\s*,\s*\[(.*?)\]\s*,?\s*\)",
        helper_body,
        re.DOTALL,
    )
    require(direct_submit is not None, "realtime failure direct native submit is missing")
    require(
        re.search(
            r",\s*performance\.timeOrigin\s*\+\s*deadline\s*,?\s*$",
            direct_submit.group(1).strip(),
        )
        is not None,
        "realtime failure direct submit must pass an absolute Emscripten cutoff",
    )
    require(
        re.search(
            r"while\s*\(\s*performance\.now\(\)\s*<\s*deadline\s*\)",
            helper_body,
        )
        is not None,
        "realtime failure response polling must retain the monotonic deadline",
    )
    runtime_gate = re.search(
        r"run_audio_worklet_conformance\(\)\s*\{(.*?)\n\}",
        web_runtime_host_script.read_text(encoding="utf-8"),
        re.DOTALL,
    )
    require(runtime_gate is not None, "Web Runtime Host AudioWorklet gate is missing")
    require(
        "audio/realtime_audio_worklet.spec.mjs" in runtime_gate.group(1)
        and "audio/realtime_failure.spec.mjs" in runtime_gate.group(1),
        "Web Runtime Host stable AudioWorklet gate must run both realtime specs",
    )
    toolchain_proof = re.search(
        r"\n\s{2}proof\)\n(.*?)\n\s{4}echo\s+"
        r"[\"']Web Toolchain Conformance Proof: PASS[\"']",
        web_toolchain_script.read_text(encoding="utf-8"),
        re.DOTALL,
    )
    require(toolchain_proof is not None, "Web Toolchain proof block is missing")
    require(
        "audio/realtime_audio_worklet.spec.mjs" in toolchain_proof.group(1)
        and "audio/realtime_failure.spec.mjs" in toolchain_proof.group(1),
        "Web Toolchain stable proof must run both realtime specs",
    )
    for required_flag in [
        "-pthread",
        "-sWASMFS",
        "-sAUDIO_WORKLET",
        "-sWASM_WORKERS",
        "-sPROXY_TO_PTHREAD",
        "-sINITIAL_MEMORY=536870912",
        "-sALLOW_MEMORY_GROWTH=0",
        "-sEXIT_RUNTIME=0",
        "-sENVIRONMENT=web,worker",
    ]:
        require(
            required_flag in host_cmake_text,
            f"required fixed-heap Web Host flag is missing: {required_flag}",
        )
    require(
        "ASYNCIFY_IMPORTS" not in host_cmake_text,
        "Host CMake must not override the Project I/O Asyncify import set",
    )

    if len(sys.argv) == 3:
        link_evidence = Path(sys.argv[2])
        require(link_evidence.is_file(), "generated direct-link evidence is missing")
        links = link_evidence.read_text(encoding="utf-8")
        require(
            re.search(r"(?:lmdj::project_io|lmdj_project_io)", links) is None,
            "generated Host direct links contain Project I/O",
        )
        require(
            re.search(r"lmdj_provider_local_", links) is None,
            "generated Host direct links contain Product Providers",
        )

    print("web Host source boundary: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"web Host source boundary: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
