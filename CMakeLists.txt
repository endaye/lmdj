cmake_minimum_required(VERSION 3.24)
project(lmdj_core LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib")
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib")

include(CTest)
include(cmake/LmdjDependencies.cmake)
include(cmake/LmdjWarnings.cmake)
include(cmake/LmdjCoverage.cmake)
include(cmake/LmdjTesting.cmake)

add_subdirectory(packages/foundation)
add_subdirectory(packages/authoring-domain)
add_subdirectory(packages/project-io)
add_subdirectory(packages/project-cooker)
add_subdirectory(packages/audio-runtime)
add_subdirectory(packages/provider-sdk)
add_subdirectory(providers/local-proof-success)
add_subdirectory(providers/local-proof-failure)
add_subdirectory(tests/core/provider)
add_subdirectory(packages/application-facade)

find_program(BASH_EXECUTABLE bash REQUIRED)
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)

if(APPLE AND TARGET lmdj_native_audio_probe)
  lmdj_add_test(
    NAME audio.native_probe_no_device
    TIER component
    COMMAND
      "${Python3_EXECUTABLE}"
      tests/platform/audio/native_audio_probe_smoke.py
      "$<TARGET_FILE:lmdj_native_audio_probe>"
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS audio
  )
endif()

add_subdirectory(apps/core-cli)
add_subdirectory(products/lmdj)

lmdj_add_test(
  NAME build.project_io_test_hook_symbols
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}"
    "${CMAKE_SOURCE_DIR}/tests/build/project_io_test_hook_symbols_test.py"
    "${CMAKE_NM}"
    "$<TARGET_FILE:lmdj_project_io>"
  LABELS persistence
)

lmdj_add_test(
  NAME build.project_io_test_hook_symbols_unit
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}"
    "${CMAKE_SOURCE_DIR}/tests/build/project_io_test_hook_symbols_unit_test.py"
  LABELS persistence
)

if(LMDJ_ENABLE_COVERAGE)
  set(
    lmdj_coverage_targets
    lmdj_foundation_tests
    lmdj_domain_project_tests
    lmdj_domain_command_handler_tests
    lmdj_domain_model_sequence_tests
    lmdj_project_store_tests
    lmdj_take_journal_tests
    lmdj_project_cooker_tests
    lmdj_project_cooker_determinism_matrix_tests
    lmdj_audio_runtime_tests
    lmdj_realtime_engine_tests
    lmdj_audio_realtime_queue_tests
    lmdj_provider_conformance_tests
    lmdj_provider_attempt_isolation_tests
    lmdj_provider_spec_regression_tests
    lmdj_application_facade_tests
    lmdj_assembly_loader_tests
    lmdj_application_c_api_tests
    lmdj_application_dynamic_load_tests
    lmdj_core_cli
    lmdj_core_c
    lmdj_project_io_fault_matrix_tests
    lmdj_application_c_api_stress_tests
  )
  if(APPLE)
    list(
      APPEND
      lmdj_coverage_targets
      lmdj_audio_coreaudio_tests
      lmdj_native_audio_probe
    )
  endif()
  set(lmdj_coverage_objects)
  foreach(lmdj_coverage_target IN LISTS lmdj_coverage_targets)
    if(NOT TARGET "${lmdj_coverage_target}")
      message(
        FATAL_ERROR
        "Coverage target is missing: ${lmdj_coverage_target}"
      )
    endif()
    string(
      APPEND
      lmdj_coverage_objects
      "$<TARGET_FILE:${lmdj_coverage_target}>\n"
    )
  endforeach()
  file(
    GENERATE
    OUTPUT "${CMAKE_BINARY_DIR}/coverage-objects.txt"
    CONTENT "${lmdj_coverage_objects}"
  )
endif()

set(
  lmdj_mcp_test_environment
  "PYTHONPATH=${CMAKE_SOURCE_DIR}/apps/core-mcp"
)
if(LMDJ_SANITIZER STREQUAL "address")
  if(APPLE)
    set(lmdj_asan_runtime_name libclang_rt.asan_osx_dynamic.dylib)
  elseif(UNIX)
    set(lmdj_asan_runtime_name libasan.so)
  endif()
  if(DEFINED lmdj_asan_runtime_name)
    execute_process(
      COMMAND
        "${CMAKE_CXX_COMPILER}"
        "--print-file-name=${lmdj_asan_runtime_name}"
      RESULT_VARIABLE lmdj_asan_runtime_status
      OUTPUT_VARIABLE lmdj_asan_runtime
      OUTPUT_STRIP_TRAILING_WHITESPACE
    )
    if(
      NOT lmdj_asan_runtime_status EQUAL 0
      OR NOT IS_ABSOLUTE "${lmdj_asan_runtime}"
      OR NOT EXISTS "${lmdj_asan_runtime}"
    )
      message(
        FATAL_ERROR
        "Unable to locate the AddressSanitizer runtime for MCP Host tests"
      )
    endif()
    list(
      APPEND lmdj_mcp_test_environment
      "LMDJ_ASAN_RUNTIME=${lmdj_asan_runtime}"
    )
    if(APPLE)
      list(
        APPEND lmdj_mcp_test_environment
        "ASAN_OPTIONS=verify_interceptors=0"
      )
    elseif(UNIX)
      # libasan is preloaded into an otherwise uninstrumented CPython process
      # for ctypes coverage. Ignore CPython's process-lifetime allocations in
      # these Host tests only; native C++ sanitizer tests retain leak checks.
      list(
        APPEND lmdj_mcp_test_environment
        "ASAN_OPTIONS=detect_leaks=0"
      )
    endif()
  endif()
endif()

lmdj_add_test(
  NAME build.active_tree
  TIER contract
  COMMAND "${BASH_EXECUTABLE}" tests/build/test_active_tree.sh
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
)

lmdj_add_test(
  NAME host.mcp_stdio
  TIER host
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/host/mcp_stdio_test.py
    "$<TARGET_FILE:lmdj_core_c>"
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 60
)
set_tests_properties(
  host.mcp_stdio
  PROPERTIES
    ENVIRONMENT "${lmdj_mcp_test_environment}"
)

lmdj_add_test(
  NAME host.mcp_facade_parity
  TIER host
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/host/mcp_facade_parity_test.py
    "$<TARGET_FILE:lmdj_core_cli>"
    "$<TARGET_FILE:lmdj_core_c>"
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 120
)
set_tests_properties(
  host.mcp_facade_parity
  PROPERTIES
    ENVIRONMENT "${lmdj_mcp_test_environment}"
)

lmdj_add_test(
  NAME build.version
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/version_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
)

lmdj_add_test(
  NAME contract.schemas
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}" tests/conformance/schema_contract_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
)

lmdj_add_test(
  NAME conformance.module_graph
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}" tests/conformance/module_graph_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
)

lmdj_add_test(
  NAME conformance.version_lock
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}" tests/conformance/version_lock_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
)

lmdj_add_test(
  NAME build.proof_failure_artifacts
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}" tests/build/proof_failure_artifacts_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  LABELS persistence
)

lmdj_add_test(
  NAME e2e.proof_path_safety
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}" tests/e2e/proof_path_safety_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  LABELS persistence
)

lmdj_add_test(
  NAME e2e.headless_core_proof
  TIER e2e
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/e2e/headless_core_proof.py
    "$<TARGET_FILE:lmdj_core_cli>"
    "$<TARGET_FILE:lmdj_core_c>"
    "${CMAKE_SOURCE_DIR}/products/lmdj/assembly.json"
    "${CMAKE_BINARY_DIR}/proof-ctest/run"
    "${CMAKE_BINARY_DIR}/proof-ctest/beat.wav"
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  LABELS assembly
  TIMEOUT 180
)
set_tests_properties(
  e2e.headless_core_proof
  PROPERTIES
    ENVIRONMENT "${lmdj_mcp_test_environment}"
)

lmdj_add_test(
  NAME package.acceptance
  TIER e2e
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/distribution/package_acceptance_test.py
    --build-root "${CMAKE_BINARY_DIR}"
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  LABELS abi assembly generated
  TIMEOUT 180
)
set_tests_properties(
  package.acceptance
  PROPERTIES
    ENVIRONMENT "${lmdj_mcp_test_environment}"
)

lmdj_add_test(
  NAME build.test_taxonomy
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/build/test_test_taxonomy.py
    "${CMAKE_BINARY_DIR}"
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
)

lmdj_add_test(
  NAME build.core_script
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/build/core_script_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 10
)
