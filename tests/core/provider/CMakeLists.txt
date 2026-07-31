if(BUILD_TESTING)
  find_package(Threads REQUIRED)

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
