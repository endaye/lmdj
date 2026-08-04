add_library(
  lmdj_web_control_runtime
  STATIC
    src/control_runtime.cpp
)
add_library(lmdj::web_control_runtime ALIAS lmdj_web_control_runtime)
target_include_directories(
  lmdj_web_control_runtime
  PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/src"
)
target_link_libraries(
  lmdj_web_control_runtime
  PUBLIC
    lmdj::application
    lmdj::audio_runtime
  PRIVATE
    lmdj_picosha2
)
lmdj_target_warnings(lmdj_web_control_runtime)
lmdj_target_sanitizers(lmdj_web_control_runtime)

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
      lmdj::web_control_runtime
  )
  if(LMDJ_WEB_AUDIO_CONFORMANCE)
    target_compile_definitions(
      lmdj_web_runtime_host
      PRIVATE LMDJ_WEB_AUDIO_CONFORMANCE=1
    )
  endif()
  set(
    lmdj_web_runtime_exports
    _main
    _lmdj_web_host_submit
    _lmdj_web_host_poll
    _lmdj_web_host_failed
    _lmdj_web_audio_start
    _lmdj_web_audio_state
    _lmdj_web_audio_fatal
    _lmdj_web_audio_observed_sample_rate
    _lmdj_web_audio_observed_render_quantum
    _lmdj_web_audio_control_failure_committed
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
      _lmdj_web_audio_test_invalid_shape
      _lmdj_web_audio_test_generation_matches
      _lmdj_web_audio_test_processor_error
      _lmdj_web_audio_test_request_outcomes
      _lmdj_web_audio_test_outcome_state
      _lmdj_web_audio_test_outcome_count
      _lmdj_web_audio_test_outcome_sequence
      _lmdj_web_audio_test_outcome_code
      _lmdj_web_audio_test_outcome_frame
      _lmdj_web_audio_test_clear_outcomes
    )
  endif()
  list(JOIN lmdj_web_runtime_exports "," lmdj_web_runtime_exports_csv)
  file(
    READ "${CMAKE_CURRENT_SOURCE_DIR}/src/web-runtime-pre.js"
    lmdj_web_runtime_pre_js
  )
  if(NOT LMDJ_WEB_AUDIO_CONFORMANCE)
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
  file(WRITE "${lmdj_web_runtime_pre_js_path}" "${lmdj_web_runtime_pre_js}")
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
      "-sDEFAULT_LIBRARY_FUNCS_TO_INCLUDE=['$emscriptenRegisterAudioObject']"
      "-sEXPORTED_FUNCTIONS=${lmdj_web_runtime_exports_csv}"
      -sEXPORTED_RUNTIME_METHODS=ccall
  )
  set_target_properties(
    lmdj_web_runtime_host
    PROPERTIES OUTPUT_NAME lmdj-web-runtime-host
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
        "${LMDJ_WEB_AUDIO_OUTPUT_DIR}/lmdj-web-runtime-host.html"
        COPYONLY
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
  )
  target_link_libraries(
    lmdj_web_control_runtime_tests
    PRIVATE
      lmdj::web_control_runtime
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
  lmdj_add_test(
    NAME host.web_source_boundary
    TIER contract
    COMMAND
      "${Python3_EXECUTABLE}"
      "${CMAKE_CURRENT_SOURCE_DIR}/test/web_host_source_boundary_test.py"
      "${CMAKE_CURRENT_SOURCE_DIR}"
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  )
endif()
