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


def require_uncorrelatable_response_fail_closed(
    runtime_pre_source: str,
    label: str,
) -> None:
    correlation = re.search(
        r"const pending = pendingRequests\.get\(message\.request_id\);\s*"
        r"if\s*\(pending\)\s*\{.*?\n\s*\}\s*else\s*\{"
        r"(?P<missing_pending>.*?)\n\s*\}\s*\n\s*\}\s*else\s*\{\s*"
        r"for\s*\(const subscriber of notificationSubscribers\)",
        runtime_pre_source,
        re.DOTALL,
    )
    require(
        correlation is not None,
        f"{label} Browser Main response correlation branch is missing",
    )
    missing_pending = correlation.group("missing_pending")
    require(
        re.fullmatch(
            r'\s*failClosed\(transportFailure\(\s*"HOST_PROTOCOL_MISMATCH"'
            r",.*?\)\);\s*return;\s*",
            missing_pending,
            re.DOTALL,
        )
        is not None,
        f"{label} missing-pending response branch must fail closed with "
        "HOST_PROTOCOL_MISMATCH and return",
    )


def main() -> int:
    require(
        len(sys.argv) in {2, 3},
        "usage: web_host_source_boundary_test.py HOST_ROOT [LINK_EVIDENCE]",
    )
    host_root = Path(sys.argv[1]).resolve()
    host_cmake = host_root / "CMakeLists.txt"
    repo_root = host_root.parents[1]
    platform_root = repo_root / "packages" / "web-runtime-platform"
    source_root = platform_root / "src"
    include_root = platform_root / "include" / "lmdj" / "web_runtime"
    platform_cmake = platform_root / "CMakeLists.txt"
    product_cmake = repo_root / "products" / "lmdj" / "CMakeLists.txt"
    product_assembly = repo_root / "products" / "lmdj" / "assembly.json"
    root_cmake = repo_root / "CMakeLists.txt"
    realtime_failure_spec = (
        repo_root / "tests" / "platform" / "web" / "audio" / "realtime_failure.spec.mjs"
    )
    web_runtime_browser_spec = (
        repo_root
        / "tests"
        / "platform"
        / "web"
        / "host"
        / "web_runtime_host_browser.spec.mjs"
    )
    web_runtime_host_script = repo_root / "scripts" / "web-runtime-host.sh"
    web_toolchain_script = repo_root / "scripts" / "web-toolchain-conformance.sh"
    playwright_config = repo_root / "tests" / "platform" / "web" / "playwright.config.mjs"
    realtime_audio_worklet = (
        repo_root
        / "packages"
        / "audio-runtime"
        / "src"
        / "web"
        / "realtime_audio_worklet.cpp"
    )
    runtime_pre = source_root / "web-runtime-pre.js"

    required_files = [
        host_cmake,
        platform_cmake,
        include_root / "control_runtime.hpp",
        source_root / "control_runtime.cpp",
        source_root / "bridge.cpp",
        product_cmake,
        product_assembly,
        root_cmake,
        realtime_failure_spec,
        web_runtime_browser_spec,
        web_runtime_host_script,
        web_toolchain_script,
        playwright_config,
        realtime_audio_worklet,
        runtime_pre,
    ]
    for path in required_files:
        require(path.is_file(), f"required Task 6 source is missing: {path}")

    source_files = sorted(source_root.glob("*.cpp")) + sorted(include_root.glob("*.hpp"))
    source = combined_text(source_files)
    control_runtime_source = (source_root / "control_runtime.cpp").read_text(
        encoding="utf-8"
    )
    bridge_source = (source_root / "bridge.cpp").read_text(encoding="utf-8")
    runtime_pre_source = runtime_pre.read_text(encoding="utf-8")
    cmake = combined_text([host_cmake, platform_cmake, root_cmake, product_cmake])

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
    platform_cmake_text = platform_cmake.read_text(encoding="utf-8")
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
        "add_subdirectory(packages/web-runtime-platform)" in root_cmake_text,
        "root CMake does not include the shared Web Runtime Platform",
    )
    require(
        "src/control_runtime.cpp" in platform_cmake_text
        and "src/bridge.cpp" in platform_cmake_text,
        "Platform CMake does not compile the actual Runtime sources",
    )
    require(
        "src/control_runtime.cpp" not in host_cmake_text
        and "src/bridge.cpp" not in host_cmake_text,
        "Host CMake still owns shared Runtime sources",
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
        "emscripten_futex_wait" in quiescence_wait.group(1),
        "AudioWorklet quiescence must block the Control Worker on the "
        "render-thread acknowledgement",
    )
    require(
        "kQuiescenceRecheckInterval" in quiescence_wait.group(1)
        and "std::min" in quiescence_wait.group(1),
        "AudioWorklet quiescence must bound each futex wait so a missed "
        "notification cannot consume the whole request deadline",
    )
    require(
        "std::this_thread::sleep_for" not in quiescence_wait.group(1),
        "AudioWorklet quiescence must not poll or process the Control proxy "
        "queue while awaiting the render-thread acknowledgement",
    )
    require(
        "emscripten_futex_wake" in realtime_audio_worklet_source,
        "AudioWorklet final-quantum acknowledgement must wake the Control "
        "futex waiter",
    )
    playwright_config_text = playwright_config.read_text(encoding="utf-8")
    web_runtime_host_script_text = web_runtime_host_script.read_text(
        encoding="utf-8"
    )
    require(
        'process.env.LMDJ_WEB_HOST_FULL_CHROMIUM === "1"'
        in playwright_config_text,
        "full Chromium selection must be scoped behind the formal Web Host "
        "Proof environment",
    )
    require(
        re.search(
            r"\.\.\.\(fullChromium\s*\?\s*\{\s*"
            r"channel:\s*[\"']chromium[\"']\s*\}\s*:\s*\{\s*\}\)",
            playwright_config_text,
            re.DOTALL,
        )
        is not None,
        "default Chromium conformance must remain on its default runner while "
        "the formal Web Host Proof opts into full Chromium",
    )
    require(
        re.search(
            r"LMDJ_WEB_HOST_FULL_CHROMIUM=1\s*\\\s*.*?"
            r"--project=chromium\s*\\\s*"
            r'"\$\{formal_host_specs\[@\]\}"',
            web_runtime_host_script_text,
            re.DOTALL,
        )
        is not None,
        "formal browser Proof must run every discovered Formal Host spec in "
        "full Chromium new-headless mode",
    )
    require(
        "git -C \"$repo_root\" ls-files "
        "'tests/platform/web/host/web_runtime_host_*.spec.mjs'"
        in web_runtime_host_script_text,
        "formal browser Proof must discover its tracked Formal Host specs",
    )
    require(
        'if [[ ${#formal_host_specs[@]} -eq 0 ]]' in web_runtime_host_script_text,
        "formal browser Proof must fail closed when no tracked specs are found",
    )
    production_boundary = re.search(
        r"verify_production_source_boundary\(\)\s*\{(.*?)\n\}",
        web_runtime_host_script_text,
        re.DOTALL,
    )
    require(
        production_boundary is not None,
        "stable Web Host build must define a generated production source "
        "boundary gate",
    )
    production_boundary_body = production_boundary.group(1)
    require(
        '"$repo_root/apps/web-runtime-host/test/web_host_source_boundary_test.py"'
        in production_boundary_body
        and '"$repo_root/apps/web-runtime-host"' in production_boundary_body
        and '"$link_evidence_path"' in production_boundary_body,
        "generated production source boundary must pass Host root and exact "
        "link evidence to the shared validator",
    )
    build_host_function = re.search(
        r"build_host\(\)\s*\{(.*?)\n\}",
        web_runtime_host_script_text,
        re.DOTALL,
    )
    require(build_host_function is not None, "Web Host build function is missing")
    build_host_body = build_host_function.group(1)
    built_target = build_host_body.find(
        'run_cmake_build "$cmake_root" --target lmdj_web_runtime_host'
    )
    generated_boundary = build_host_body.find("verify_production_source_boundary")
    packaged_host = build_host_body.find("package_host")
    require(
        built_target >= 0
        and generated_boundary > built_target
        and packaged_host > generated_boundary,
        "stable Web Host build must validate generated production source "
        "after linking and before packaging",
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
    bridge_published = bridge_source.find(
        "web_bridge.store(web_bridge_owner.get(), std::memory_order_release);"
    )
    audio_published = bridge_source.find(
        "web_audio.store(web_audio_owner.get(), std::memory_order_release);"
    )
    require(
        bridge_published >= 0
        and audio_published >= 0
        and bridge_published < audio_published,
        "Browser Main must publish the ControlBridge before exposing audio "
        "readiness",
    )
    failure_spec_text = realtime_failure_spec.read_text(encoding="utf-8")
    pending_rejection_case = re.search(
        r'test\("unknown response rejects and clears another real pending '
        r'Browser Main request".*?\n\}\);',
        failure_spec_text,
        re.DOTALL,
    )
    require(
        pending_rejection_case is not None,
        "real Browser Main pending rejection case is missing",
    )
    require(
        "pendingRejectionEvidence(page)" in pending_rejection_case.group(0)
        and "pendingIdsBefore" in pending_rejection_case.group(0)
        and "pendingIdsAfter" in pending_rejection_case.group(0)
        and "HOST_PROTOCOL_MISMATCH" in pending_rejection_case.group(0)
        and "terminalOwnerReleased" in pending_rejection_case.group(0),
        "real Browser Main pending rejection case omits required evidence",
    )
    pending_rejection_helper = re.search(
        r"async function pendingRejectionEvidence\(page\)\s*\{(.*?)\n\}",
        failure_spec_text,
        re.DOTALL,
    )
    require(
        pending_rejection_helper is not None,
        "real Browser Main pending rejection helper is missing",
    )
    pending_rejection_body = pending_rejection_helper.group(1)
    untracked_submit = pending_rejection_body.find(
        "submitUntrackedHostStatus(untrackedRequestId)"
    )
    normal_send = pending_rejection_body.find("const pending = transport.send")
    require(
        untracked_submit >= 0 and normal_send > untracked_submit,
        "pending rejection proof must submit the untracked native response "
        "before registering the normal transport request",
    )
    require(
        "conformance.pendingRequestIds()" in pending_rejection_body
        and "PENDING_REJECTION_TIMEOUT" in pending_rejection_body,
        "pending rejection proof must observe clearing and bound rejection",
    )
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
    require(
        'let submitted = -1;' in helper_body
        and 'if (submitted === 0) break;' in helper_body
        and 'if (submitted !== -1)' in helper_body
        and 'await delay(5);' in helper_body
        and 'if (submitted !== 0)' in helper_body
        and 'Host submit timed out' in helper_body,
        "realtime failure submit helper must retry only the transient native "
        "bridge-not-ready result within its monotonic deadline",
    )
    fatal_wait = re.search(
        r"async\s+waitForFatal\(\)\s*\{(.*?)\n\s{6}\},",
        runtime_pre_source,
        re.DOTALL,
    )
    require(fatal_wait is not None, "processor fatal wait helper is missing")
    fatal_wait_body = fatal_wait.group(1)
    require(
        'Module["_lmdj_web_audio_control_failure_committed"]()'
        in fatal_wait_body,
        "processor fatal proof must observe committed Control failure",
    )
    require(
        re.search(r"submit\(\s*[\"']host\.status[\"']", fatal_wait_body) is None,
        "processor fatal proof must not submit through the Bridge after terminalization",
    )
    browser_spec_text = web_runtime_browser_spec.read_text(encoding="utf-8")
    diagnostic_overall_timeout = re.search(
        r"const DIAGNOSTIC_PROJECT_OVERALL_TIMEOUT_MS = ([0-9_]+);",
        browser_spec_text,
    )
    require(
        diagnostic_overall_timeout is not None
        and int(diagnostic_overall_timeout.group(1).replace("_", ""))
        >= 300_000,
        "diagnostic project proof must budget for 64 serial Pad assignments "
        "on the slow Linux runner",
    )
    diagnostic_overall_timeout_ms = int(
        diagnostic_overall_timeout.group(1).replace("_", "")
    )
    project_reopen_timeout = re.search(
        r"const PROJECT_REOPEN_OVERALL_TIMEOUT_MS = ([0-9_]+);",
        browser_spec_text,
    )
    require(
        project_reopen_timeout is not None
        and int(project_reopen_timeout.group(1).replace("_", "")) >= 60_000,
        "browser writer-handoff proof must retain the Product diagnostic "
        "project's 60 second reopen budget",
    )
    project_reopen_timeout_ms = int(
        project_reopen_timeout.group(1).replace("_", "")
    )
    require(
        "{ overallDeadlineMs = PROJECT_REOPEN_OVERALL_TIMEOUT_MS, "
        "retryDelayMs = 25 }" in browser_spec_text,
        "the shared browser reopen helper must default to the named "
        "writer-handoff budget",
    )
    diagnostic_stall_timeout = re.search(
        r"const DIAGNOSTIC_PROJECT_STALL_TIMEOUT_MS = ([0-9_]+);",
        browser_spec_text,
    )
    require(
        diagnostic_stall_timeout is not None
        and int(diagnostic_stall_timeout.group(1).replace("_", ""))
        >= 90_000,
        "diagnostic progress observation must outlive a slow reload handoff",
    )
    require(
        "diagnostic_project_error_code" in browser_spec_text
        and "HOST_TIMEOUT" in browser_spec_text
        and "recoverDiagnosticProjectAfterTimeout" in browser_spec_text,
        "the slow-runner browser journey must expose and recover exactly one "
        "reload handoff timeout",
    )
    require(
        browser_spec_text.count(
            "await recoverDiagnosticProjectAfterTimeout(page, error);"
        )
        == 1,
        "the browser proof must allow exactly one reload handoff recovery",
    )
    recovery_outcome_timeout = re.search(
        r'test\("Chromium recovery outcome timeout is terminal and releases '
        r'the lease".*?\n\}\);',
        browser_spec_text,
        re.DOTALL,
    )
    require(
        recovery_outcome_timeout is not None,
        "recovery outcome timeout browser proof is missing",
    )
    recovery_outcome_timeout_body = recovery_outcome_timeout.group(0)
    recovery_outcome_test_timeout = re.search(
        r"test\.setTimeout\(([0-9_]+)\);", recovery_outcome_timeout_body
    )
    require(
        recovery_outcome_test_timeout is not None
        and int(recovery_outcome_test_timeout.group(1).replace("_", ""))
        >= diagnostic_overall_timeout_ms + project_reopen_timeout_ms,
        "recovery outcome proof must outlive diagnostic preparation plus the "
        "writer-handoff reopen budget",
    )
    terminal_release_evidence = recovery_outcome_timeout_body.find(
        "terminalTransportEvidence(page)"
    )
    reopened_page = recovery_outcome_timeout_body.find(
        "const reopenedPage = await context.newPage()"
    )
    require(
        terminal_release_evidence >= 0
        and reopened_page > terminal_release_evidence
        and 'newSubmitCode: "HOST_STATE_INVALID"' in recovery_outcome_timeout_body
        and "terminalOwnerReleased: true" in recovery_outcome_timeout_body
        and "timeout: TERMINAL_RELEASE_OBSERVATION_TIMEOUT_MS"
        in recovery_outcome_timeout_body,
        "recovery outcome timeout must expose the terminated transport state "
        "and prove terminal owner release before a new page competes for the "
        "OPFS writer lease",
    )
    for diagnostic_test_name in (
        "Chromium binds the verified packaged runtime to the real AudioWorklet",
        "Chromium visible diagnostic project completes the packaged runtime journey",
    ):
        diagnostic_test = re.search(
            rf'test\("{re.escape(diagnostic_test_name)}".*?\n\}}\);',
            browser_spec_text,
            re.DOTALL,
        )
        diagnostic_test_timeout = (
            re.search(r"test\.setTimeout\(([0-9_]+)\);", diagnostic_test.group(0))
            if diagnostic_test is not None
            else None
        )
        require(
            diagnostic_test_timeout is not None
            and int(diagnostic_test_timeout.group(1).replace("_", ""))
            > diagnostic_overall_timeout_ms,
            f"{diagnostic_test_name} must outlive its diagnostic readiness budget",
        )
        if diagnostic_test_name.startswith("Chromium visible diagnostic"):
            require(
                int(diagnostic_test_timeout.group(1).replace("_", ""))
                >= 660_000,
                "the visible diagnostic journey must include one bounded "
                "reload-timeout recovery budget",
            )
    unresponsive_cancellation = re.search(
        r'test\("Chromium packaged unresponsive cancellation '
        r'force-terminates and recovers".*?\n\}\);',
        browser_spec_text,
        re.DOTALL,
    )
    require(
        unresponsive_cancellation is not None,
        "unresponsive cancellation browser proof is missing",
    )
    require(
        "claim_attempted: true" in unresponsive_cancellation.group(0),
        "unresponsive cancellation must prove that publication was attempted",
    )
    require(
        "deadlineMs: CLAIMED_PUBLICATION_PROOF_DEADLINE_MS"
        in unresponsive_cancellation.group(0),
        "unresponsive cancellation must leave enough time for slow runners to "
        "reach the publication claim before forcing termination",
    )
    require(
        "claim_started_open: true" not in unresponsive_cancellation.group(0),
        "unresponsive cancellation must allow deadline cancellation to race "
        "the publication-attempt observation",
    )
    require(
        "timeout: CLAIMED_PUBLICATION_PROOF_DEADLINE_MS + 5_000"
        in unresponsive_cancellation.group(0),
        "unresponsive cancellation observation must remain open after the "
        "request deadline fires",
    )
    unresponsive_release = unresponsive_cancellation.group(0).find(
        "releaseDeadlineProof(page)"
    )
    unresponsive_terminal_evidence = unresponsive_cancellation.group(0).find(
        "terminalTransportEvidence(page)"
    )
    require(
        unresponsive_terminal_evidence >= 0
        and unresponsive_release > unresponsive_terminal_evidence,
        "unresponsive cancellation must prove forced terminal cleanup before "
        "releasing the artificial claim gate",
    )
    require(
        "rejectedConsumes: 3" not in unresponsive_cancellation.group(0)
        and "expect([1, 2, 3]).toContain" in unresponsive_cancellation.group(0)
        and "replayConsumedTerminalAck(page)"
        in unresponsive_cancellation.group(0),
        "unresponsive terminal-ack proof must accept asynchronous rejection "
        "ordering and deterministically reject an explicit replay",
    )
    claimed_settlement = re.search(
        r'test\("Chromium packaged asset\.import claim wins before deadline '
        r'and settles after it".*?\n\}\);',
        browser_spec_text,
        re.DOTALL,
    )
    require(
        claimed_settlement is not None,
        "claimed publication settlement browser proof is missing",
    )
    require(
        "waitForTimeout(CLAIMED_PUBLICATION_PROOF_DEADLINE_MS + 100)"
        not in claimed_settlement.group(0),
        "claimed publication settlement must observe the first deadline "
        "cancellation instead of sleeping past the settlement watchdog",
    )
    require(
        '"HOST_RESTART_REQUIRED"' in claimed_settlement.group(0)
        and "reopenProject(" in claimed_settlement.group(0),
        "claimed publication settlement must recover authoritative Project "
        "Truth when a slow runner exceeds the settlement watchdog",
    )
    claimed_publication_hang = re.search(
        r'test\("Chromium claimed asset\.import publication hang becomes '
        r'restart-required and recovers".*?\n\}\);',
        browser_spec_text,
        re.DOTALL,
    )
    require(
        claimed_publication_hang is not None,
        "claimed publication hang browser proof is missing",
    )
    require(
        "deadlineMs: CLAIMED_PUBLICATION_PROOF_DEADLINE_MS"
        in claimed_publication_hang.group(0),
        "claimed publication hang must leave enough time for a slow runner "
        "to reach the publication claim before the deadline fires",
    )
    require(
        "timeout: CLAIMED_PUBLICATION_PROOF_DEADLINE_MS + 5_000"
        in claimed_publication_hang.group(0),
        "claimed publication hang observation must outlive its request "
        "deadline on a slow runner",
    )
    visible_journey = re.search(
        r'test\("Chromium visible diagnostic project completes the packaged '
        r'runtime journey".*?\n\}\);',
        browser_spec_text,
        re.DOTALL,
    )
    require(visible_journey is not None, "visible packaged journey is missing")
    take_outcome_proof = visible_journey.group(0).find(
        "await proveExactOutcomes(page, takeAdmissions"
    )
    take_stop = visible_journey.group(0).find(
        "stopTakeWithQuiescenceDiagnostics(page)"
    )
    require(
        take_outcome_proof >= 0 and take_outcome_proof < take_stop,
        "packaged Take proof must settle exact realtime outcomes before the "
        "stop barrier so slow OPFS persistence is not conflated with final "
        "AudioWorklet quiescence",
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
    require(
        '"$web_test_root/toolchain/server.py"' in runtime_gate.group(1)
        and "--port 0" in runtime_gate.group(1)
        and "--write-port" in runtime_gate.group(1),
        "AudioWorklet gate must start its own dynamic-port conformance server",
    )
    require(
        "proof_server_pid=$!" in runtime_gate.group(1)
        and "cleanup_proof_server" in runtime_gate.group(1),
        "AudioWorklet gate must own and clean up its conformance server",
    )
    require(
        "LMDJ_WEB_HOST_EXTERNAL_SERVER=1" in runtime_gate.group(1)
        and "LMDJ_WEB_HOST_BASE_URL=" in runtime_gate.group(1),
        "AudioWorklet gate must bind Playwright to the owned server URL",
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
            required_flag in platform_cmake_text,
            f"required fixed-heap Web Host flag is missing: {required_flag}",
        )
    require(
        "ASYNCIFY_IMPORTS" not in platform_cmake_text,
        "Host CMake must not override the Project I/O Asyncify import set",
    )
    require(
        re.search(
            r"const\s+TRANSPORT_POLL_INTERVAL_MS\s*=\s*16\s*;",
            runtime_pre_source,
        )
        is not None,
        "Web Host transport polling must use the bounded 16 ms cadence",
    )
    require(
        "window.setTimeout(pollTransport, TRANSPORT_POLL_INTERVAL_MS)"
        in runtime_pre_source,
        "Web Host transport polling must use the named bounded cadence",
    )
    require_uncorrelatable_response_fail_closed(
        runtime_pre_source,
        "source",
    )
    missing_return_source = runtime_pre_source.replace(
        "            return;\n          }\n        } else {",
        "          }\n        } else {",
        1,
    )
    require(
        missing_return_source != runtime_pre_source,
        "source-boundary terminal-return mutation was not applied",
    )
    try:
        require_uncorrelatable_response_fail_closed(
            missing_return_source,
            "missing-return mutation",
        )
    except AssertionError:
        pass
    else:
        raise AssertionError(
            "Web Host source boundary accepted a missing-pending branch "
            "without its terminal return"
        )
    require(
        re.search(
            r"const\s+TERMINAL_OWNER_RELEASE_GRACE_MS\s*=\s*5_000\s*;",
            runtime_pre_source,
        )
        is not None,
        "Web Host must give responsive Control cleanup a bounded 5 second "
        "terminal owner release grace",
    )
    require(
        "}, TERMINAL_OWNER_RELEASE_GRACE_MS);" in runtime_pre_source,
        "Web Host terminal owner fallback must use the named release grace",
    )

    if len(sys.argv) == 3:
        link_evidence = Path(sys.argv[2])
        require(link_evidence.is_file(), "generated direct-link evidence is missing")
        generated_cmake_cache = link_evidence.parents[2] / "CMakeCache.txt"
        require(
            generated_cmake_cache.is_file(),
            "generated production CMake cache evidence is missing",
        )
        require(
            "LMDJ_WEB_AUDIO_CONFORMANCE:BOOL=OFF"
            in generated_cmake_cache.read_text(encoding="utf-8"),
            "generated Web Host boundary must come from a production "
            "conformance-OFF build",
        )
        links = link_evidence.read_text(encoding="utf-8")
        require(
            re.search(r"(?:lmdj::project_io|lmdj_project_io)", links) is None,
            "generated Host direct links contain Project I/O",
        )
        require(
            re.search(r"lmdj_provider_local_", links) is None,
            "generated Host direct links contain Product Providers",
        )
        generated_runtime_pre = link_evidence.parent / "web-runtime-pre.js"
        require(
            generated_runtime_pre.is_file(),
            "generated production pre-JS evidence is missing",
        )
        generated_runtime_pre_source = generated_runtime_pre.read_text(
            encoding="utf-8"
        )
        require_uncorrelatable_response_fail_closed(
            generated_runtime_pre_source,
            "generated production pre-JS",
        )
        for conformance_surface in (
            "createConformanceApi",
            "submitUntrackedHostStatus",
            "pendingRequestIds",
            "lmdjWebRuntimeHostTest",
            "LMDJ_WEB_AUDIO_CONFORMANCE_API",
            "LMDJ_WEB_AUDIO_CONFORMANCE_INSTALL",
        ):
            require(
                conformance_surface not in generated_runtime_pre_source,
                "generated production pre-JS exposes conformance surface: "
                f"{conformance_surface}",
            )

    print("web Host source boundary: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"web Host source boundary: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
