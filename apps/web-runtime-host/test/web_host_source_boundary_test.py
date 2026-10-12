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
    # Only the local response/notification fork, not global failClosed semantics,
    # JavaScript binding provenance or retained-owner release, is checked here.
    lexical = re.compile(
        '"(?:\\\\.|[^"\\\\])*"|\\\'(?:\\\\.|[^\\\'\\\\])*\\\'|`(?:\\\\.|[^`\\\\])*`|/\\*[\\s\\S]*?\\*/|//[^\\n]*|[A-Za-z_$][\\w$]*|\\d[\\w]*|===|!==|&&|\\|\\||[^\\s]'
    )

    def tokens(text: str) -> tuple[str, ...]:
        return tuple(t for t in lexical.findall(text) if not t.startswith(("//", "/*")))

    def check(value: bool) -> None:
        require(value, f"{label} Browser Main response correlation branch is missing")

    def group(ts: tuple[str, ...], start: int) -> tuple[tuple[str, ...], int]:
        pairs = {"(": ")", "[": "]", "{": "}"}
        check(start < len(ts) and ts[start] in pairs)
        stack = [pairs[ts[start]]]
        for n in range(start + 1, len(ts)):
            if ts[n] in pairs:
                stack.append(pairs[ts[n]])
            elif ts[n] in pairs.values():
                check(bool(stack) and ts[n] == stack.pop())
                if not stack:
                    return ts[start + 1:n], n + 1
        check(False)
        raise AssertionError("unreachable")

    def if_arm(ts: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        check(ts[:2] == ("if", "("))
        condition, end = group(ts, 1)
        check(end < len(ts) and ts[end] == "{")
        arm, end = group(ts, end)
        return condition, arm, ts[end:]

    source = tokens(runtime_pre_source)
    declaration = ("function", "pollTransport", "(", ")", "{")
    matches = [n for n in range(len(source)) if source[n:n + len(declaration)] == declaration]
    check(len(matches) == 1)
    poll, _ = group(source, matches[0] + len(declaration) - 1)
    # The current owned block has no templates; they are not parsed as effects.
    check(not any(t.startswith("`") for t in poll))
    fork = tokens('if (typeof message.request_id === "string")')
    matches = [n for n in range(len(poll)) if poll[n:n + len(fork)] == fork]
    check(len(matches) == 1)
    _, response, tail = if_arm(poll[matches[0]:])
    check(tail[:2] == ("else", "{"))
    notification, notification_end = group(tail, 1)

    # Both lookup and removal identify this response, not its operation name.
    check(len(response) >= 2 and response[0] in {"const", "let"})
    pending = response[1]
    check(pending not in {"message", "pendingRequests"})
    lookup = tokens(f"{response[0]} {pending} = pendingRequests.get(message.request_id);")
    check(response[:len(lookup)] == lookup)
    condition, tracked, rest = if_arm(response[len(lookup):])
    check(condition == (pending,))
    removal = tokens("pendingRequests.delete(message.request_id);")
    check(tracked[:len(removal)] == removal and "notificationSubscribers" not in tracked)
    check(rest[:2] == ("else", "if"))
    condition, abandoned, rest = if_arm(rest[1:])
    check(condition == tokens("abandonedRequestIds.delete(message.request_id)") and not abandoned)
    check(rest[:2] == ("else", "{"))
    unknown, end = group(rest, 1)
    check(end == len(rest))

    # One existing failClosed call, followed by no return or the current
    # redundant guard. No reachable arbitrary early exit is optional.
    call = tokens('failClosed(transportFailure("HOST_PROTOCOL_MISMATCH",')
    check(unknown[:len(call)] == call)
    check(len(unknown) > len(call) and unknown[len(call)].startswith(('"', "'")))
    suffix = unknown[len(call) + 1:]
    if suffix[:1] == (",",):
        suffix = suffix[1:]
    check(suffix[:3] == (")", ")", ";"))
    suffix = suffix[3:]
    check(not suffix or suffix == tokens("if (!transportTerminated) return;"))

    check(notification[:2] == ("for", "("))
    header, end = group(notification, 1)
    check(len(header) == 4 and header[0] in {"const", "let"} and
          header[1] != "message" and header[2:] == ("of", "notificationSubscribers"))
    check(end < len(notification) and notification[end] == "{")
    notify, end = group(notification, end)
    check(end == len(notification) and notify == tokens(f"{header[1]}(message);"))
    # Reject a new local early exit between this fork and the existing poll
    # continuation. This is not a global worker/receipt provenance proof.
    continuation = tail[notification_end:]
    # A final void return after rescheduling cannot skip the continuation.
    if continuation[-6:] == tokens("scheduleTransportPoll(); return;"):
        continuation = continuation[:-2]
    check(not any(t in {"return", "throw", "break", "continue"}
                  for t in continuation))


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
    runtime_session = platform_root / "web" / "runtime_session.mjs"
    web_host_main = host_root / "src" / "main.mjs"
    diagnostic_project = host_root / "src" / "diagnostic_project.mjs"

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
        runtime_session,
        web_host_main,
        diagnostic_project,
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
    runtime_session_source = runtime_session.read_text(encoding="utf-8")
    host_javascript = combined_text(
        [runtime_session, web_host_main, diagnostic_project]
    )
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
        r"(?<![\w.])record\.(?:begin|stop|commit)\b": (
            "retired Capture operation spelling"
        ),
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

    for pattern, description in {
        r"\b(?:ProjectStore|SequenceJournal|TakeJournal)\b": (
            "Project or journal implementation in browser JavaScript"
        ),
        r"sequence_pattern_fingerprint|fingerprintSequencePattern": (
            "Sequence fingerprint implementation in browser JavaScript"
        ),
        r"quantize_onset_tick|normalize_duration_tick|kTickDenominator": (
            "musical timing math in browser JavaScript"
        ),
        r'\b(?:onset_tick|duration_tick)\s*[:=].*[+*/%-]': (
            "fallback tick sequencer in browser JavaScript"
        ),
        r"recovery/(?:active|sealed)|sequence\.jsonl": (
            "Sequence journal layout knowledge in browser JavaScript"
        ),
    }.items():
        require(
            re.search(pattern, host_javascript) is None,
            f"{description} found",
        )

    sequence_adapter = re.search(
        r"function beginSequence\(.*?\n  async function reloadSnapshot\(",
        runtime_session_source,
        re.DOTALL,
    )
    require(sequence_adapter is not None, "Runtime Session Sequence adapter is missing")
    require(
        re.search(
            r"performance\.(?:now|timeOrigin)|Date\.(?:now|UTC)|"
            r"setInterval|requestAnimationFrame|Math\.(?:floor|round|ceil)",
            sequence_adapter.group(0),
        )
        is None,
        "Runtime Session Sequence adapter must not derive a musical clock or "
        "run a JavaScript fallback sequencer",
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
    responsive_cancellation = re.search(
        r'test\("Chromium packaged responsive cancellation wins before '
        r'mutation publication".*?\n\}\);',
        browser_spec_text,
        re.DOTALL,
    )
    require(
        responsive_cancellation is not None,
        "responsive terminal-ack proof is missing",
    )
    responsive_body = responsive_cancellation.group(0)
    replay = responsive_body.find(
        "expect(await replayConsumedTerminalAck(owner)).toBe(-1)"
    )
    accepted_consumes = [
        match.start()
        for match in re.finditer(r"acceptedConsumes:\s*1", responsive_body)
    ]
    claim_attempt_evidence = re.search(
        r"expect\(\s*await deadlineProofState\(owner,\s*requestId\)\s*,\s*"
        r"selected\.name\s*\)\s*\.toMatchObject\(\{\s*claim_attempted:\s*"
        r"selected\.claimAttempted\s*\}\)",
        responsive_body,
        re.DOTALL,
    )
    direct_inventory_evidence = re.search(
        r"expect\(\s*await opfsInventory\(owner\)\s*,\s*"
        r"`\$\{selected\.name\} direct cleanup`\s*\)\s*"
        r"\.toEqual\(inventoryBefore\)",
        responsive_body,
        re.DOTALL,
    )
    reopened_inventory_evidence = re.search(
        r"expect\(\s*await opfsInventory\(reopened\)\s*,\s*"
        r"selected\.name\s*\)\.toEqual\(inventoryBefore\)",
        responsive_body,
        re.DOTALL,
    )
    late_message_evidence = re.search(
        r"`\$\{selected\.name\} late messages`\s*\)"
        r"\.toEqual\(observationsBefore\)",
        responsive_body,
        re.DOTALL,
    )
    owner_close_evidence = re.search(
        r"expect\(\s*await owner\.evaluate\(\(\)\s*=>\s*"
        r"window\.lmdjWebRuntimeController\.close\(\)\s*\),\s*"
        r"selected\.name\s*\)\.toBe\(false\)",
        responsive_body,
        re.DOTALL,
    )
    reopened_close_evidence = re.search(
        r"expect\(\s*await reopened\.evaluate\(\(\)\s*=>\s*"
        r"window\.lmdjWebRuntimeController\.close\(\)\s*\),\s*"
        r"selected\.name\s*\)\.toBe\(true\)",
        responsive_body,
        re.DOTALL,
    )
    require(
        "forgedAcksSent: 2" in responsive_body
        and "duplicateReleaseRequestsSent: 2" in responsive_body
        and "observedWorkerAcks: 1" in responsive_body
        and replay >= 0
        and any(position < replay for position in accepted_consumes)
        and any(position > replay for position in accepted_consumes),
        "responsive terminal-ack proof must preserve the exact attack, real "
        "Worker ACK, one accepted consume, and deterministic replay rejection",
    )
    require(
        responsive_body.count("claimAttempted: false") == 2
        and claim_attempt_evidence is not None
        and 'publication: "cancelled"' in responsive_body
        and 'error: { code: "HOST_TIMEOUT" }' in responsive_body
        and '"restart-required"' in responsive_body
        and 'newSubmitCode: "HOST_TIMEOUT"' in responsive_body
        and "terminated: true" in responsive_body
        and "terminalOwnerReleased: true" in responsive_body,
        "responsive terminal-ack proof must preserve cancellation-before-claim "
        "and terminal owner cleanup",
    )
    require(
        direct_inventory_evidence is not None
        and late_message_evidence is not None
        and "project_revision, selected.name).toBe(0)" in responsive_body
        and "expect(after, selected.name).toEqual(before)" in responsive_body
        and reopened_inventory_evidence is not None,
        "responsive terminal-ack proof must preserve OPFS, late-message, "
        "and reopen Truth recovery evidence",
    )
    require(
        owner_close_evidence is not None and reopened_close_evidence is not None,
        "responsive terminal-ack proof must formally close both terminal owner "
        "and reopened controller",
    )
    require(
        "rejectedConsumes" not in responsive_body,
        "responsive terminal-ack proof must not assert scheduler-dependent "
        "rejection cardinality",
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
    sequence_journey = re.search(
        r'test\("Stage 9 Chromium records across an acknowledged switch, '
        r'reloads, and exposes observer status".*?\n\}\);',
        browser_spec_text,
        re.DOTALL,
    )
    require(
        sequence_journey is not None,
        "why: the packaged Stage 9 Sequence journey is missing; remedy: keep "
        "the named Chromium record/switch/reload journey in the Formal Host spec",
    )
    observed_pending = re.search(
        r"const observed = .*?expect\(observed\)\.toMatchObject\(\{.*?"
        r"pendingEventCount: 1,.*?\}\);",
        sequence_journey.group(0),
        re.DOTALL,
    )
    persisted_drain = re.search(
        r"const persistedStatus = .*?expect\(persistedStatus\)\.toMatchObject\(\{"
        r'.*?state: "inactive",.*?pendingEventCount: 0,.*?\}\);',
        sequence_journey.group(0),
        re.DOTALL,
    )
    require(
        observed_pending is not None
        and persisted_drain is not None
        and '"sequence.recovery.list"' in sequence_journey.group(0)
        and "persistedEvent" in sequence_journey.group(0)
        and "replayed: true" in sequence_journey.group(0)
        and "requestPatternSwitch" in sequence_journey.group(0)
        and "__sequenceBoundaries" in sequence_journey.group(0)
        and "continued.press" in sequence_journey.group(0)
        and "switchedPattern.events" in sequence_journey.group(0)
        and "snapshot.reload" in sequence_journey.group(0),
        "why: the packaged Sequence proof does not cross the acknowledged "
        "switch boundary into committed new-Pattern truth; remedy: assert the "
        "durable pending event, replayed Stop, reloaded exact event and drained "
        "journal, boundary acknowledgement, first later event, both Patterns, "
        "and reload in the named journey",
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
        "-sASYNCIFY_STACK_SIZE=131072",
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
    # Local correlation witnesses; existing real Native/browser/OPFS tests
    # retain owner-release acceptance. No owner-provenance claim is made here.
    for mutation_name, original, replacement in (
        ('tracked-response-wrong-id-lookup', 'pendingRequests.get(message.request_id)', 'pendingRequests.get(message.operation)'),
        ('tracked-response-wrong-id-removal', 'pendingRequests.delete(message.request_id)', 'pendingRequests.delete(message.operation)'),
        ('abandoned-response-wrong-id-removal', 'abandonedRequestIds.delete(message.request_id)', 'abandonedRequestIds.delete(message.operation)'),
        ('unknown-response-does-not-call-failClosed', '            failClosed(transportFailure(\n              "HOST_PROTOCOL_MISMATCH",', '            void(transportFailure(\n              "HOST_PROTOCOL_MISMATCH",'),
        ('response-dispatched-as-notification', 'pendingRequests.get(message.request_id)', '(notificationSubscribers.forEach((subscriber) => subscriber(message)), pendingRequests.get(message.request_id))'),
        ('unknown-response-unconditional-return', '            failClosed(transportFailure(\n              "HOST_PROTOCOL_MISMATCH",', '            return failClosed(transportFailure(\n              "HOST_PROTOCOL_MISMATCH",'),
        ('sealed-continuation-unconditional-return', '    if (transportTerminated) reapAbandonedControlRequests();', '    if (transportTerminated) return;'),
    ):
        require(runtime_pre_source.count(original) == 1,
                f"source-boundary {mutation_name} mutation anchor is missing or ambiguous")
        mutated_source = runtime_pre_source.replace(original, replacement, 1)
        require(mutated_source != runtime_pre_source,
                f"source-boundary {mutation_name} mutation was not applied")
        mutation_label = f"{mutation_name} mutation"
        try:
            require_uncorrelatable_response_fail_closed(mutated_source, mutation_label)
        except AssertionError as error:
            require(
                str(error) == f"{mutation_label} Browser Main response correlation branch is missing",
                f"source-boundary {mutation_name} failed for a different defect: {error}",
            )
        else:
            raise AssertionError(f"Web Host source boundary accepted {mutation_name} mutation")
    # Actual current failClosed synchronously seals before returning. Its
    # redundant guard may be absent; no negative anchor depends on that guard.
    dead_guard = "            if (!transportTerminated) return;\n"
    guard_count = runtime_pre_source.count(dead_guard)
    require(guard_count in {0, 1}, "source-boundary dead-guard positive anchor is ambiguous")
    if guard_count == 1:
        without_dead_guard = runtime_pre_source.replace(dead_guard, "", 1)
        require(without_dead_guard != runtime_pre_source,
                "source-boundary dead-guard positive control was not applied")
        require_uncorrelatable_response_fail_closed(without_dead_guard, "removed-dead-guard positive control")
    final_poll_tail = "    scheduleTransportPoll();\n  }\n\n  function retainedOwnerRequest"
    final_return_tail = "    scheduleTransportPoll();\n    return;\n  }\n\n  function retainedOwnerRequest"
    plain_count = runtime_pre_source.count(final_poll_tail)
    return_count = runtime_pre_source.count(final_return_tail)
    require(plain_count + return_count == 1,
            "source-boundary final-return positive anchor is missing or ambiguous")
    original_tail, replacement_tail = (
        (final_poll_tail, final_return_tail) if plain_count == 1
        else (final_return_tail, final_poll_tail)
    )
    final_return_control = runtime_pre_source.replace(original_tail, replacement_tail, 1)
    require(final_return_control != runtime_pre_source,
            "source-boundary final-return positive control was not applied")
    require_uncorrelatable_response_fail_closed(final_return_control, "final-void-return positive control")
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
