set(
  lmdj_web_runtime_identity_path
  "${CMAKE_SOURCE_DIR}/products/lmdj/generated/web-runtime-identity.json"
)
set_property(
  DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
  "${lmdj_web_runtime_identity_path}"
)
file(READ "${lmdj_web_runtime_identity_path}" lmdj_web_runtime_identity)
string(JSON lmdj_web_product_build GET "${lmdj_web_runtime_identity}" product_build)
string(JSON lmdj_web_platform_version GET "${lmdj_web_runtime_identity}" platform version)
string(JSON lmdj_web_protocol_version GET "${lmdj_web_runtime_identity}" protocol_version)
string(JSON lmdj_web_heap_bytes GET "${lmdj_web_runtime_identity}" heap_bytes)
string(JSON lmdj_web_host_contract GET "${lmdj_web_runtime_identity}" hosts web-runtime-host distribution_contract)
string(JSON lmdj_web_host_id GET "${lmdj_web_runtime_identity}" hosts web-runtime-host id)
string(JSON lmdj_web_host_version GET "${lmdj_web_runtime_identity}" hosts web-runtime-host version)
string(JSON lmdj_web_emcc_version GET "${lmdj_web_runtime_identity}" emscripten emcc_version)
string(JSON lmdj_web_releases_revision GET "${lmdj_web_runtime_identity}" emscripten emscripten_releases_revision)
string(JSON lmdj_web_emsdk_revision GET "${lmdj_web_runtime_identity}" emscripten emsdk_revision)
string(JSON lmdj_web_emsdk_tag GET "${lmdj_web_runtime_identity}" emscripten emsdk_tag)
string(JSON lmdj_web_limit_bank GET "${lmdj_web_runtime_identity}" resource_limits decoded_float_pcm_bytes_per_bank)
string(JSON lmdj_web_limit_total GET "${lmdj_web_runtime_identity}" resource_limits decoded_float_pcm_bytes_total)
string(JSON lmdj_web_limit_frames GET "${lmdj_web_runtime_identity}" resource_limits decoded_frames_per_pad)
string(JSON lmdj_web_limit_import GET "${lmdj_web_runtime_identity}" resource_limits imported_wav_bytes)

add_library(
  lmdj_web_runtime_control
  STATIC
    src/control_runtime.cpp
)
add_library(lmdj::web_runtime_control ALIAS lmdj_web_runtime_control)
target_include_directories(
  lmdj_web_runtime_control
  PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/include"
  PRIVATE
    "${CMAKE_SOURCE_DIR}/packages/application-facade/internal"
)
target_link_libraries(
  lmdj_web_runtime_control
  PUBLIC
    lmdj::application
    lmdj::audio_runtime
  PRIVATE
    lmdj_picosha2
)
lmdj_target_warnings(lmdj_web_runtime_control)
lmdj_target_sanitizers(lmdj_web_runtime_control)

add_library(
  lmdj_web_runtime_manifest_gate
  STATIC
    src/manifest_gate.cpp
)
add_library(
  lmdj::web_runtime_manifest_gate ALIAS lmdj_web_runtime_manifest_gate
)
target_include_directories(
  lmdj_web_runtime_manifest_gate
  PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/include"
)
target_link_libraries(
  lmdj_web_runtime_manifest_gate
  PRIVATE
    lmdj::foundation
    lmdj_picosha2
)
lmdj_target_warnings(lmdj_web_runtime_manifest_gate)
lmdj_target_sanitizers(lmdj_web_runtime_manifest_gate)

if(EMSCRIPTEN)
  option(
    LMDJ_WEB_AUDIO_CONFORMANCE
    "Expose browser-only Web Audio conformance diagnostics"
    OFF
  )
  set(
    LMDJ_WEB_AUDIO_OUTPUT_DIR
    ""
    CACHE PATH
    "Optional output directory for the formal Web Audio host"
  )
  add_executable(
    lmdj_web_runtime_host
    src/bridge.cpp
  )
  target_link_libraries(
    lmdj_web_runtime_host
    PRIVATE
      lmdj::web_runtime_control
      lmdj::web_runtime_manifest_gate
  )
  target_include_directories(
    lmdj_web_runtime_host
    PRIVATE
      "${CMAKE_SOURCE_DIR}/packages/application-facade/internal"
  )
  if(LMDJ_WEB_AUDIO_CONFORMANCE)
    target_compile_definitions(
      lmdj_web_runtime_host
      PRIVATE LMDJ_WEB_AUDIO_CONFORMANCE=1
    )
    set(
      LMDJ_WEB_CONFORMANCE_MANIFEST
      "{\"assets\":[{\"bytes\":48,\"path\":\"assets/diagnostic-project.0000000000000000000000000000000000000000000000000000000000000000.mjs\",\"role\":\"host_module\",\"sha256\":\"0000000000000000000000000000000000000000000000000000000000000000\"},{\"bytes\":49,\"path\":\"assets/input-adapters.1111111111111111111111111111111111111111111111111111111111111111.mjs\",\"role\":\"host_module\",\"sha256\":\"1111111111111111111111111111111111111111111111111111111111111111\"},{\"bytes\":50,\"path\":\"assets/main.2222222222222222222222222222222222222222222222222222222222222222.mjs\",\"role\":\"host_main\",\"sha256\":\"2222222222222222222222222222222222222222222222222222222222222222\"},{\"bytes\":51,\"path\":\"assets/preflight.3333333333333333333333333333333333333333333333333333333333333333.mjs\",\"role\":\"host_module\",\"sha256\":\"3333333333333333333333333333333333333333333333333333333333333333\"},{\"bytes\":52,\"path\":\"assets/protocol.4444444444444444444444444444444444444444444444444444444444444444.mjs\",\"role\":\"host_module\",\"sha256\":\"4444444444444444444444444444444444444444444444444444444444444444\"},{\"bytes\":53,\"path\":\"assets/runtime.5555555555555555555555555555555555555555555555555555555555555555.js\",\"role\":\"runtime_script\",\"sha256\":\"5555555555555555555555555555555555555555555555555555555555555555\"},{\"bytes\":54,\"path\":\"assets/runtime.6666666666666666666666666666666666666666666666666666666666666666.wasm\",\"role\":\"runtime_wasm\",\"sha256\":\"6666666666666666666666666666666666666666666666666666666666666666\"},{\"bytes\":55,\"path\":\"assets/state-machine.7777777777777777777777777777777777777777777777777777777777777777.mjs\",\"role\":\"host_module\",\"sha256\":\"7777777777777777777777777777777777777777777777777777777777777777\"},{\"bytes\":56,\"path\":\"assets/styles.8888888888888888888888888888888888888888888888888888888888888888.css\",\"role\":\"host_style\",\"sha256\":\"8888888888888888888888888888888888888888888888888888888888888888\"}],\"distribution_contract\":\"${lmdj_web_host_contract}\",\"emscripten\":{\"emcc_version\":\"${lmdj_web_emcc_version}\",\"emscripten_releases_revision\":\"${lmdj_web_releases_revision}\",\"emsdk_revision\":\"${lmdj_web_emsdk_revision}\",\"emsdk_tag\":\"${lmdj_web_emsdk_tag}\"},\"heap_bytes\":${lmdj_web_heap_bytes},\"host_id\":\"${lmdj_web_host_id}\",\"host_version\":\"${lmdj_web_host_version}\",\"manifest_version\":1,\"platform_version\":\"${lmdj_web_platform_version}\",\"product_build\":\"${lmdj_web_product_build}\",\"protocol_version\":${lmdj_web_protocol_version},\"resource_limits\":{\"decoded_float_pcm_bytes_per_bank\":${lmdj_web_limit_bank},\"decoded_float_pcm_bytes_total\":${lmdj_web_limit_total},\"decoded_frames_per_pad\":${lmdj_web_limit_frames},\"imported_wav_bytes\":${lmdj_web_limit_import}}}"
    )
    string(
      REPLACE
      "{\"bytes\":49,\"path\":\"assets/input-adapters.1111111111111111111111111111111111111111111111111111111111111111.mjs\",\"role\":\"host_module\",\"sha256\":\"1111111111111111111111111111111111111111111111111111111111111111\"}"
      "{\"bytes\":49,\"path\":\"assets/input-adapters.1111111111111111111111111111111111111111111111111111111111111111.mjs\",\"role\":\"host_module\",\"sha256\":\"1111111111111111111111111111111111111111111111111111111111111111\"},{\"bytes\":57,\"path\":\"assets/integrity.9999999999999999999999999999999999999999999999999999999999999999.mjs\",\"role\":\"platform_module\",\"sha256\":\"9999999999999999999999999999999999999999999999999999999999999999\"}"
      LMDJ_WEB_CONFORMANCE_MANIFEST
      "${LMDJ_WEB_CONFORMANCE_MANIFEST}"
    )
    string(
      SHA256 LMDJ_WEB_CONFORMANCE_MANIFEST_SHA256
      "${LMDJ_WEB_CONFORMANCE_MANIFEST}"
    )
  endif()
  set(
    lmdj_web_runtime_exports
    _main
    _lmdj_web_host_submit
    _lmdj_web_host_poll
    _lmdj_web_host_cancel_request
    _lmdj_web_host_deadline_proof_configure
    _lmdj_web_host_deadline_proof_release
    _lmdj_web_host_deadline_proof_state
    _lmdj_web_host_set_terminal_token
    _lmdj_web_host_authorize_terminal_release
    _lmdj_web_host_complete_terminal_release
    _lmdj_web_host_consume_terminal_release
    _lmdj_web_host_failed
    _lmdj_web_host_initialize_manifest
    _lmdj_web_audio_start
    _lmdj_web_audio_state
    _lmdj_web_audio_fatal
    _lmdj_web_audio_observed_sample_rate
    _lmdj_web_audio_observed_render_quantum
    _lmdj_web_audio_control_failure_committed
    _lmdj_web_audio_commit_failure
    _lmdj_web_audio_bootstrap_timeout
  )
  if(LMDJ_WEB_AUDIO_CONFORMANCE)
    list(
      APPEND lmdj_web_runtime_exports
      _lmdj_web_audio_test_poll
      _lmdj_web_audio_test_render_calls
      _lmdj_web_audio_test_output_energy
      _lmdj_web_audio_test_ack_generation
      _lmdj_web_audio_test_observed_frames
      _lmdj_web_audio_test_gate_closed
      _lmdj_web_audio_test_in_flight
      _lmdj_web_audio_test_gate_state
      _lmdj_web_audio_test_start_calls
      _lmdj_web_audio_test_validate_configuration
      _lmdj_web_audio_test_bootstrap_failure
      _lmdj_web_audio_test_invalid_shape
      _lmdj_web_audio_test_generation_matches
      _lmdj_web_audio_test_processor_error
      _lmdj_web_audio_test_request_outcomes
      _lmdj_web_audio_test_queue_outcome_mirror_write
      _lmdj_web_audio_test_release_outcome_mirror_write
      _lmdj_web_audio_test_outcome_mirror_state
      _lmdj_web_audio_test_outcome_mirror_writer_timed_out
      _lmdj_web_audio_test_outcome_state
      _lmdj_web_audio_test_outcome_count
      _lmdj_web_audio_test_outcome_sequence
      _lmdj_web_audio_test_outcome_code
      _lmdj_web_audio_test_outcome_frame
      _lmdj_web_audio_test_clear_outcomes
    )
  endif()
  list(JOIN lmdj_web_runtime_exports "," lmdj_web_runtime_exports_csv)
  set_property(
    DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/src/web-runtime-pre.js"
  )
  file(
    READ "${CMAKE_CURRENT_SOURCE_DIR}/src/web-runtime-pre.js"
    lmdj_web_runtime_pre_js
  )
  if(LMDJ_WEB_AUDIO_CONFORMANCE)
    string(
      REPLACE
      "  /* LMDJ_WEB_AUDIO_CONFORMANCE_MANIFEST */"
      "  Module[\"lmdjHostManifestBytes\"] = new TextEncoder().encode('${LMDJ_WEB_CONFORMANCE_MANIFEST}');\n  Module[\"lmdjHostManifestSha256\"] = \"${LMDJ_WEB_CONFORMANCE_MANIFEST_SHA256}\";"
      lmdj_web_runtime_pre_js
      "${lmdj_web_runtime_pre_js}"
    )
  else()
    foreach(lmdj_web_audio_block IN ITEMS API INSTALL)
      set(
        lmdj_web_audio_begin
        "/* LMDJ_WEB_AUDIO_CONFORMANCE_${lmdj_web_audio_block}_BEGIN */"
      )
      set(
        lmdj_web_audio_end
        "/* LMDJ_WEB_AUDIO_CONFORMANCE_${lmdj_web_audio_block}_END */"
      )
      string(
        FIND "${lmdj_web_runtime_pre_js}" "${lmdj_web_audio_begin}"
        lmdj_web_audio_begin_index
      )
      string(
        FIND "${lmdj_web_runtime_pre_js}" "${lmdj_web_audio_end}"
        lmdj_web_audio_end_index
      )
      if(lmdj_web_audio_begin_index LESS 0 OR lmdj_web_audio_end_index LESS 0)
        message(FATAL_ERROR "formal Web Audio pre-js markers are incomplete")
      endif()
      string(
        SUBSTRING "${lmdj_web_runtime_pre_js}" 0
        ${lmdj_web_audio_begin_index} lmdj_web_audio_prefix
      )
      string(LENGTH "${lmdj_web_audio_end}" lmdj_web_audio_end_length)
      math(
        EXPR lmdj_web_audio_suffix_index
        "${lmdj_web_audio_end_index} + ${lmdj_web_audio_end_length}"
      )
      string(
        SUBSTRING "${lmdj_web_runtime_pre_js}"
        ${lmdj_web_audio_suffix_index} -1 lmdj_web_audio_suffix
      )
      set(
        lmdj_web_runtime_pre_js
        "${lmdj_web_audio_prefix}${lmdj_web_audio_suffix}"
      )
    endforeach()
  endif()
  set(
    lmdj_web_runtime_pre_js_path
    "${CMAKE_CURRENT_BINARY_DIR}/web-runtime-pre.js"
  )
  set(
    lmdj_web_runtime_post_js_path
    "${CMAKE_CURRENT_BINARY_DIR}/web-runtime-post.js"
  )
  file(
    WRITE "${lmdj_web_runtime_pre_js_path}"
    ";(() => {\n${lmdj_web_runtime_pre_js}"
  )
  file(WRITE "${lmdj_web_runtime_post_js_path}" "\n})();\n")
  set_property(
    TARGET lmdj_web_runtime_host APPEND PROPERTY LINK_DEPENDS
    "${lmdj_web_runtime_pre_js_path}"
    "${lmdj_web_runtime_post_js_path}"
  )
  target_link_options(
    lmdj_web_runtime_host
    PRIVATE
      -pthread
      -sWASMFS
      -sAUDIO_WORKLET
      -sWASM_WORKERS
      -sPROXY_TO_PTHREAD
      -sINITIAL_MEMORY=536870912
      -sALLOW_MEMORY_GROWTH=0
      -sEXIT_RUNTIME=0
      -sENVIRONMENT=web,worker
      "--pre-js=${lmdj_web_runtime_pre_js_path}"
      "--post-js=${lmdj_web_runtime_post_js_path}"
      "-sDEFAULT_LIBRARY_FUNCS_TO_INCLUDE=['$emscriptenRegisterAudioObject']"
      "-sEXPORTED_FUNCTIONS=${lmdj_web_runtime_exports_csv}"
      -sEXPORTED_RUNTIME_METHODS=ccall
  )
  set_target_properties(
    lmdj_web_runtime_host
    PROPERTIES OUTPUT_NAME lmdj-web-runtime
  )
  if(LMDJ_WEB_AUDIO_OUTPUT_DIR)
    set_target_properties(
      lmdj_web_runtime_host
      PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${LMDJ_WEB_AUDIO_OUTPUT_DIR}"
    )
    if(LMDJ_WEB_AUDIO_CONFORMANCE)
      file(MAKE_DIRECTORY "${LMDJ_WEB_AUDIO_OUTPUT_DIR}")
      configure_file(
        "${CMAKE_SOURCE_DIR}/tests/platform/web/audio/realtime_audio_worklet.html"
        "${LMDJ_WEB_AUDIO_OUTPUT_DIR}/lmdj-web-runtime.html"
        @ONLY
      )
    endif()
  endif()
  file(
    GENERATE
    OUTPUT
      "${CMAKE_CURRENT_BINARY_DIR}/lmdj_web_runtime_host.link-libraries.txt"
    CONTENT
      "$<TARGET_PROPERTY:lmdj_web_runtime_host,LINK_LIBRARIES>\n"
  )
  lmdj_target_warnings(lmdj_web_runtime_host)
endif()

if(BUILD_TESTING AND NOT EMSCRIPTEN)
  find_package(Threads REQUIRED)
  add_executable(
    lmdj_web_control_runtime_tests
    test/control_runtime_test.cpp
    src/bridge.cpp
  )
  target_include_directories(
    lmdj_web_control_runtime_tests
    PRIVATE
      "${CMAKE_CURRENT_SOURCE_DIR}/src"
      "${CMAKE_SOURCE_DIR}"
      "${CMAKE_SOURCE_DIR}/packages/application-facade/internal"
  )
  target_link_libraries(
    lmdj_web_control_runtime_tests
    PRIVATE
      lmdj::web_runtime_control
      lmdj_picosha2
      Threads::Threads
  )
  lmdj_target_warnings(lmdj_web_control_runtime_tests)
  lmdj_target_sanitizers(lmdj_web_control_runtime_tests)
  lmdj_add_test(
    NAME host.web_control_runtime
    TIER host
    COMMAND lmdj_web_control_runtime_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS audio concurrency
  )
  add_executable(
    lmdj_web_manifest_gate_tests
    test/manifest_gate_test.cpp
  )
  target_include_directories(
    lmdj_web_manifest_gate_tests
    PRIVATE
      "${CMAKE_CURRENT_SOURCE_DIR}/src"
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_web_manifest_gate_tests
    PRIVATE
      lmdj::web_runtime_manifest_gate
      lmdj::foundation
      lmdj_picosha2
  )
  lmdj_target_warnings(lmdj_web_manifest_gate_tests)
  lmdj_target_sanitizers(lmdj_web_manifest_gate_tests)
  lmdj_add_test(
    NAME host.web_manifest_gate
    TIER host
    COMMAND lmdj_web_manifest_gate_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  )
  add_executable(
    lmdj_web_realtime_session_tests
    test/realtime_session_test.cpp
    src/bridge.cpp
  )
  target_include_directories(
    lmdj_web_realtime_session_tests
    PRIVATE
      "${CMAKE_CURRENT_SOURCE_DIR}/src"
      "${CMAKE_SOURCE_DIR}"
      "${CMAKE_SOURCE_DIR}/packages/application-facade/internal"
  )
  target_link_libraries(
    lmdj_web_realtime_session_tests
    PRIVATE
      lmdj::web_runtime_control
      lmdj_picosha2
      Threads::Threads
  )
  lmdj_target_warnings(lmdj_web_realtime_session_tests)
  lmdj_target_sanitizers(lmdj_web_realtime_session_tests)
  lmdj_add_test(
    NAME host.web_realtime_session
    TIER host
    COMMAND lmdj_web_realtime_session_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS audio concurrency
  )
  lmdj_add_test(
    NAME host.web_source_boundary
    TIER contract
    COMMAND
      "${Python3_EXECUTABLE}"
      "${CMAKE_SOURCE_DIR}/apps/web-runtime-host/test/web_host_source_boundary_test.py"
      "${CMAKE_SOURCE_DIR}/apps/web-runtime-host"
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  )
  lmdj_add_test(
    NAME platform.web_runtime_source_boundary
    TIER contract
    COMMAND
      "${Python3_EXECUTABLE}"
      "${CMAKE_CURRENT_SOURCE_DIR}/test/source_boundary_test.py"
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  )
endif()
