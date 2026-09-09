if(BUILD_TESTING)
  find_package(Threads REQUIRED)
  add_executable(lmdj_provider_sample_slice_tests sample_slice_test.cpp)
  target_include_directories(lmdj_provider_sample_slice_tests PRIVATE "${CMAKE_SOURCE_DIR}")
  target_link_libraries(lmdj_provider_sample_slice_tests PRIVATE lmdj_provider_local_sample_slice)
  target_compile_definitions(lmdj_provider_sample_slice_tests PRIVATE
    LMDJ_SLICE_SOURCE_PACKAGE_MANIFEST="${CMAKE_BINARY_DIR}/providers/local-sample-slice/local.sample.slice.source-package.json")
  lmdj_target_warnings(lmdj_provider_sample_slice_tests)
  lmdj_target_sanitizers(lmdj_provider_sample_slice_tests)
  lmdj_add_test(NAME provider.sample_slice TIER component COMMAND lmdj_provider_sample_slice_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}" LABELS provider)
  add_executable(lmdj_provider_callback_stress_tests callback_stress_test.cpp)
  target_include_directories(lmdj_provider_callback_stress_tests PRIVATE "${CMAKE_SOURCE_DIR}")
  target_link_libraries(lmdj_provider_callback_stress_tests PRIVATE lmdj_provider_local_proof_success Threads::Threads)
  lmdj_target_warnings(lmdj_provider_callback_stress_tests)
  lmdj_target_sanitizers(lmdj_provider_callback_stress_tests)
  lmdj_add_test(NAME provider.callback_stress TIER stress COMMAND lmdj_provider_callback_stress_tests WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}" LABELS provider)
  if(UNIX AND NOT EMSCRIPTEN)
    add_executable(lmdj_provider_execution_crash_tests execution_crash_test.cpp "${CMAKE_SOURCE_DIR}/packages/provider-sdk/src/attempt_store.cpp")
    target_compile_definitions(lmdj_provider_execution_crash_tests PRIVATE LMDJ_PROVIDER_TEST_CHECKPOINTS)
    target_include_directories(lmdj_provider_execution_crash_tests PRIVATE "${CMAKE_SOURCE_DIR}")
    target_link_libraries(lmdj_provider_execution_crash_tests PRIVATE lmdj_provider_local_proof_success lmdj_picosha2 Threads::Threads)
    lmdj_target_warnings(lmdj_provider_execution_crash_tests)
    lmdj_target_sanitizers(lmdj_provider_execution_crash_tests)
    lmdj_add_test(NAME provider.execution_crash TIER component COMMAND lmdj_provider_execution_crash_tests WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}" LABELS provider persistence)
  endif()
  add_executable(lmdj_provider_output_validation_tests output_validation_test.cpp)
  target_include_directories(lmdj_provider_output_validation_tests PRIVATE "${CMAKE_SOURCE_DIR}")
  target_link_libraries(lmdj_provider_output_validation_tests PRIVATE lmdj_provider_local_proof_success Threads::Threads)
  lmdj_target_warnings(lmdj_provider_output_validation_tests)
  lmdj_target_sanitizers(lmdj_provider_output_validation_tests)
  lmdj_add_test(NAME provider.output_validation TIER component COMMAND lmdj_provider_output_validation_tests WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}" LABELS provider)
  add_executable(lmdj_provider_artifact_source_tests artifact_source_test.cpp)
  target_include_directories(lmdj_provider_artifact_source_tests PRIVATE "${CMAKE_SOURCE_DIR}")
  target_link_libraries(lmdj_provider_artifact_source_tests PRIVATE lmdj_provider_local_proof_success Threads::Threads)
  lmdj_target_warnings(lmdj_provider_artifact_source_tests)
  lmdj_target_sanitizers(lmdj_provider_artifact_source_tests)
  lmdj_add_test(NAME provider.artifact_source TIER component COMMAND lmdj_provider_artifact_source_tests WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}" LABELS provider)

  add_executable(
    lmdj_provider_durable_file_tests
    durable_file_test.cpp
  )
  target_include_directories(
    lmdj_provider_durable_file_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_provider_durable_file_tests
    PRIVATE
      lmdj::provider_sdk
  )
  lmdj_target_warnings(lmdj_provider_durable_file_tests)
  lmdj_target_sanitizers(lmdj_provider_durable_file_tests)
  lmdj_add_test(
    NAME provider.durable_file
    TIER unit
    COMMAND lmdj_provider_durable_file_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS provider persistence
  )

  add_executable(
    lmdj_provider_conformance_tests
    conformance_test.cpp
  )
  target_include_directories(
    lmdj_provider_conformance_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_provider_conformance_tests
    PRIVATE
      lmdj_provider_local_proof_success
      lmdj_provider_local_proof_failure
  )
  lmdj_target_warnings(lmdj_provider_conformance_tests)
  lmdj_target_sanitizers(lmdj_provider_conformance_tests)
  lmdj_add_test(
    NAME provider.conformance
    TIER component
    COMMAND lmdj_provider_conformance_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS provider
  )

  add_executable(
    lmdj_provider_attempt_isolation_tests
    attempt_isolation_test.cpp
  )
  target_include_directories(
    lmdj_provider_attempt_isolation_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_provider_attempt_isolation_tests
    PRIVATE
      lmdj_provider_local_proof_failure
  )
  lmdj_target_warnings(lmdj_provider_attempt_isolation_tests)
  lmdj_target_sanitizers(lmdj_provider_attempt_isolation_tests)
  lmdj_add_test(
    NAME provider.attempt_isolation
    TIER component
    COMMAND lmdj_provider_attempt_isolation_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS provider
  )

  add_executable(
    lmdj_provider_attempt_ledger_invariant_tests
    attempt_ledger_invariant_test.cpp
  )
  target_include_directories(
    lmdj_provider_attempt_ledger_invariant_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_provider_attempt_ledger_invariant_tests
    PRIVATE
      lmdj_provider_local_proof_success
      lmdj_provider_local_proof_failure
  )
  lmdj_target_warnings(lmdj_provider_attempt_ledger_invariant_tests)
  lmdj_target_sanitizers(lmdj_provider_attempt_ledger_invariant_tests)
  lmdj_add_test(
    NAME provider.attempt_ledger_invariant
    TIER component
    COMMAND lmdj_provider_attempt_ledger_invariant_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS provider persistence
  )

  add_executable(
    lmdj_provider_host_settings_invariant_tests
    host_settings_invariant_test.cpp
  )
  target_include_directories(
    lmdj_provider_host_settings_invariant_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_provider_host_settings_invariant_tests
    PRIVATE
      lmdj_provider_local_proof_success
      lmdj_provider_local_proof_failure
  )
  lmdj_target_warnings(lmdj_provider_host_settings_invariant_tests)
  lmdj_target_sanitizers(lmdj_provider_host_settings_invariant_tests)
  lmdj_add_test(
    NAME provider.host_settings_invariant
    TIER component
    COMMAND lmdj_provider_host_settings_invariant_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS provider persistence
  )

  add_executable(
    lmdj_provider_spec_regression_tests
    spec_regression_test.cpp
  )
  target_include_directories(
    lmdj_provider_spec_regression_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_compile_definitions(
    lmdj_provider_spec_regression_tests
    PRIVATE
      LMDJ_SUCCESS_SOURCE_PACKAGE_MANIFEST="${CMAKE_BINARY_DIR}/providers/local-proof-success/local.proof.success.source-package.json"
      LMDJ_FAILURE_SOURCE_PACKAGE_MANIFEST="${CMAKE_BINARY_DIR}/providers/local-proof-failure/local.proof.failure.source-package.json"
  )
  target_link_libraries(
    lmdj_provider_spec_regression_tests
    PRIVATE
      lmdj_provider_local_proof_success
      lmdj_provider_local_proof_failure
      Threads::Threads
  )
  lmdj_target_warnings(lmdj_provider_spec_regression_tests)
  lmdj_target_sanitizers(lmdj_provider_spec_regression_tests)
  lmdj_add_test(
    NAME provider.spec_regression
    TIER component
    COMMAND lmdj_provider_spec_regression_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS provider
  )
endif()
