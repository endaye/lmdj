cmake_minimum_required(VERSION 3.24)
project(lmdj_core LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib")
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib")

if(EMSCRIPTEN)
  add_compile_options(-pthread)
endif()

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
add_subdirectory(providers/local-sample-slice)
add_subdirectory(tests/core/provider)
add_subdirectory(packages/application-facade)

find_program(BASH_EXECUTABLE bash REQUIRED)
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)

lmdj_add_test(
  NAME provider.stage12_fixture_corpus
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/core/provider/stage12_fixture_corpus_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  LABELS provider fixtures
)

lmdj_add_test(
  NAME provider.benchmark_report
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}"
    tools/provider-benchmark/tests/report_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  LABELS provider benchmark
)

lmdj_add_test(
  NAME provider.benchmark_slice_score
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}"
    tools/provider-benchmark/tests/score_slice_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  LABELS provider benchmark
  )

add_subdirectory(apps/web-runtime-host)
add_subdirectory(packages/web-runtime-platform)

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
    if(UNIX AND NOT APPLE AND CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
      # CPython loads the C ABI with dlopen. Make the C++ exception runtime
      # available when libasan initializes its __cxa_throw interceptor.
      execute_process(
        COMMAND "${CMAKE_CXX_COMPILER}" "--print-file-name=libstdc++.so"
        RESULT_VARIABLE lmdj_asan_cxx_runtime_status
        OUTPUT_VARIABLE lmdj_asan_cxx_runtime
        OUTPUT_STRIP_TRAILING_WHITESPACE
      )
      if(NOT lmdj_asan_cxx_runtime_status EQUAL 0
         OR NOT IS_ABSOLUTE "${lmdj_asan_cxx_runtime}"
         OR NOT EXISTS "${lmdj_asan_cxx_runtime}")
        message(FATAL_ERROR "Unable to locate the C++ runtime for MCP ASAN tests")
      endif()
      string(APPEND lmdj_asan_runtime ":${lmdj_asan_cxx_runtime}")
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


add_subdirectory(apps/core-cli)
add_subdirectory(apps/native-host)
add_subdirectory(products/lmdj)

lmdj_add_test(
  NAME build.project_io_test_hook_symbols
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}"
    "${CMAKE_SOURCE_DIR}/tests/build/project_io_test_hook_symbols_test.py"
    "${CMAKE_NM}"
    "$<TARGET_FILE:lmdj_project_io>"
    "$<TARGET_FILE:lmdj_audio_runtime>"
    "$<TARGET_FILE:lmdj_web_runtime_control>"
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
    lmdj_foundation_json_tests
    lmdj_foundation_soundset_manifest_tests
    lmdj_domain_project_tests
    lmdj_domain_command_handler_tests
    lmdj_domain_performance_tests
    lmdj_domain_migration_v4_tests
    lmdj_domain_soundset_map_tests
    lmdj_domain_soundset_install_tests
    lmdj_domain_model_sequence_tests
    lmdj_project_store_tests
    lmdj_project_storage_platform_tests
    lmdj_project_bundle_transfer_tests
    lmdj_runtime_content_tests
    lmdj_project_cooker_sample_analysis_tests
    lmdj_project_cooker_performance_replay_tests
    lmdj_project_cooker_wav_selection_tests
    lmdj_project_cooker_tests
    lmdj_project_cooker_determinism_matrix_tests
    lmdj_audio_runtime_tests
    lmdj_prepared_sample_bank_tests
    lmdj_realtime_engine_tests
    lmdj_audio_realtime_queue_tests
    lmdj_audio_value_channel_tests
    lmdj_snapshot_publication_invariant_tests
    lmdj_master_fx_tests
    lmdj_master_fx_determinism_tests
    lmdj_master_fx_allocation_guard_tests
    lmdj_provider_durable_file_tests
    lmdj_provider_conformance_tests
    lmdj_provider_attempt_isolation_tests
    lmdj_provider_attempt_ledger_invariant_tests
    lmdj_provider_host_settings_invariant_tests
    lmdj_provider_spec_regression_tests
    lmdj_provider_sample_slice_tests
    lmdj_provider_artifact_source_tests
    lmdj_provider_output_validation_tests
    lmdj_provider_attempt_output_read_tests
    lmdj_provider_execution_crash_tests
    lmdj_facade_performance_runtime_consumer_tests
    lmdj_runtime_facade_tests
    lmdj_runtime_facade_concurrency_tests
    lmdj_application_facade_tests
    lmdj_facade_candidate_store_tests
    lmdj_facade_candidate_job_tests
    lmdj_facade_candidate_audition_tests
    lmdj_facade_runtime_content_export_tests
    lmdj_application_facade_failure_tests
    lmdj_facade_sequence_surface_tests
    lmdj_facade_performance_operation_contract_tests
    lmdj_facade_performance_replay_tests
    lmdj_facade_performance_runtime_bridge_tests
    lmdj_facade_performance_engine_adapter_tests
    lmdj_facade_resample_performance_tests
    lmdj_facade_performance_session_tests
    lmdj_facade_performance_gesture_admission_tests
    lmdj_facade_performance_rebase_matrix_tests
    lmdj_facade_sample_surface_tests
    lmdj_facade_web_runtime_limit_tests
    lmdj_facade_soundset_tests
    lmdj_facade_soundset_install_quota_tests
    lmdj_web_control_runtime_tests
    lmdj_web_manifest_gate_tests
    lmdj_web_realtime_session_tests
    lmdj_web_performance_bridge_tests
    lmdj_assembly_loader_tests
    lmdj_application_c_api_tests
    lmdj_application_dynamic_load_tests
    lmdj_core_cli
    lmdj_native_host
    lmdj_native_capture_allocation_failure
    lmdj_core_c
    lmdj_sequence_journal_tests
    lmdj_performance_journal_tests
    lmdj_performance_lifecycle_tests
    lmdj_performance_rebase_tests
    lmdj_session_mutual_exclusion_tests
    lmdj_project_io_fault_matrix_tests
    lmdj_soundset_store_tests
    lmdj_soundset_local_adapter_tests
    lmdj_project_io_soundset_install_commit_tests
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


lmdj_add_test(
  NAME build.active_tree
  TIER contract
  COMMAND "${BASH_EXECUTABLE}" tests/build/test_active_tree.sh
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
)

lmdj_add_test(
  NAME build.release_orchestration
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_orchestration_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_orchestration_driver
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_orchestration_driver_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_orchestration_entry
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_cli_orchestration_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_changelog
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_changelog_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_changelog_binding
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_changelog_binding_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_changelog_site
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_changelog_site_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_task_verification
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_task_verification_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 60
)

lmdj_add_test(
  NAME build.release_publication_effect
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_publication_effect_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_managed_dispatch
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_managed_dispatch_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_durable_dispatch
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_durable_dispatch_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_dispatch_evidence
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_dispatch_evidence_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_dispatch_receipt
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_dispatch_receipt_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_review_inventory
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_review_inventory_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_managed_pr_transition
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_managed_pr_transition_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_evidence_source
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_evidence_source_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 60
)

lmdj_add_test(
  NAME build.release_evidence_branch
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_evidence_branch_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 60
)

lmdj_add_test(
  NAME build.release_changelog_install
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_changelog_install_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_publication_workspace
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_publication_workspace_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 60
)

lmdj_add_test(
  NAME build.release_changelog_site_evidence
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_changelog_site_evidence_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_evidence_pr
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_evidence_pr_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_publication_evidence
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_publication_evidence_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_publication
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_publication_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_model
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/build/release_model_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_openpgp
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/build/release_openpgp_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_prepare
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/build/release_prepare_test.py
    ReleasePrepareTest
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_prepare.exact_targets
  TIER e2e
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/build/release_prepare_test.py
    ReleaseTargetValidationIntegrationTest
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 180
)

lmdj_add_test(
  NAME build.release_transitions
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/build/release_transitions_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_rehearsal
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/build/release_rehearsal_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_audit
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/build/release_audit_test.py
    ReleaseAuditTest
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

# Host tier, not contract: this case validates the real assembled-product
# snapshot by launching the portal's Node release-docs checker (~5s idle), so
# its cost scales with host contention, not with contract parsing. The 30s
# contract budget left <6x headroom and timed out at 30.2x s repeatedly on the
# loaded ci-core host (issue #291); 120s is 4x the observed loaded worst case.
lmdj_add_test(
  NAME build.release_audit.remote_canonical
  TIER host
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/build/release_audit_test.py
    ReleaseAuditIntegrationTest.test_remote_canonical_product_build_without_intent_audits_registered_entries
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 120
)

lmdj_add_test(
  NAME build.release_audit.repository_local
  TIER e2e
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/build/release_audit_test.py
    ReleaseAuditIntegrationTest.test_repository_local_audit_does_not_assume_current_intent_count
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 180
)

lmdj_add_test(
  NAME build.release_audit.snapshot_provenance
  TIER e2e
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/build/release_audit_test.py
    ReleaseAuditIntegrationTest.test_zero_intent_local_and_remote_audits_reject_corrupt_snapshot_provenance
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 180
)

lmdj_add_test(
  NAME build.release_audit_workflow
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/build/release_audit_workflow_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 10
)

lmdj_add_test(
  NAME build.release_publish_workflow
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/build/release_publish_workflow_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 10
)

lmdj_add_test(
  NAME build.release_skill
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/build/release_skill_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 10
)

lmdj_add_test(
  NAME build.web_runtime_deploy_workflow
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/build/web_runtime_deploy_workflow_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 10
)

lmdj_add_test(
  NAME build.web_runtime_public_deployment_docs
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/build/web_runtime_public_deployment_docs_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 10
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
  NAME host.performance_cli
  TIER host
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/host/performance_cli_test.py
    "$<TARGET_FILE:lmdj_core_cli>"
    "$<TARGET_FILE:lmdj_native_host>"
    "${CMAKE_SOURCE_DIR}/products/lmdj/assembly.json"
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 120
)

lmdj_add_test(
  NAME host.performance_mcp
  TIER host
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/host/performance_mcp_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)
set_tests_properties(
  host.performance_mcp
  PROPERTIES
    ENVIRONMENT "${lmdj_mcp_test_environment}"
)

lmdj_add_test(
  NAME host.performance_cross_host
  TIER host
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/host/cross_host_performance_idempotency_test.py
    "$<TARGET_FILE:lmdj_core_cli>"
    "$<TARGET_FILE:lmdj_core_c>"
    "$<TARGET_FILE:lmdj_native_host>"
    "${CMAKE_SOURCE_DIR}/products/lmdj/assembly.json"
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  LABELS persistence
  TIMEOUT 120
)
set_tests_properties(
  host.performance_cross_host
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
  NAME contract.schema_validator
  TIER unit
  COMMAND
    "${Python3_EXECUTABLE}" tests/conformance/json_schema_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
)

lmdj_add_test(
  NAME contract.schemas
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}" tests/conformance/schema_contract_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
)

# The Project Bundle Contract suite existed but was never registered, so it
# never ran and #784 shipped: the Bundle enum stayed at v3 while the writer
# moved to v4.
lmdj_add_test(
  NAME conformance.project_bundle
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}" tests/conformance/project_bundle_contract_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
)

lmdj_add_test(
  NAME conformance.runtime_content
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}" tests/conformance/runtime_content_contract_test.py
    --consumer $<TARGET_FILE:lmdj_runtime_content_tests>
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
  NAME e2e.project_bundle_writer_level
  TIER e2e
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/e2e/project_bundle_writer_level_test.py
    "$<TARGET_FILE:lmdj_core_cli>"
    "${CMAKE_SOURCE_DIR}/products/lmdj/assembly.json"
    "${CMAKE_BINARY_DIR}/bundle-writer-level"
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  LABELS assembly
  TIMEOUT 60
)

# Node, not a native target: the reader under test is the browser ES module in
# packages/web-runtime-platform/web/, and the only honest input for it is a
# Bundle the shipped CLI and packer produced, which needs the assembled
# product. Every CI job that runs scripts/core.sh provisions Node 22.
lmdj_add_test(
  NAME e2e.project_bundle_browser_reader
  TIER e2e
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/e2e/project_bundle_browser_reader_test.py
    "$<TARGET_FILE:lmdj_core_cli>"
    "${CMAKE_SOURCE_DIR}/products/lmdj/assembly.json"
    "${CMAKE_BINARY_DIR}/bundle-browser-reader"
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  LABELS assembly
  TIMEOUT 120
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
  NAME build.facade_surface_sharding
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/build/facade_surface_sharding_test.py
    "${CMAKE_BINARY_DIR}"
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
)

lmdj_add_test(
  NAME build.facade_surface_sharding_unit
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/build/facade_surface_sharding_unit_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 10
)

lmdj_add_test(
  NAME fixtures.cardputer_music
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/build/cardputer_music_fixture_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
)

lmdj_add_test(
  NAME fixtures.soundset_corpus
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}"
    tools/soundset-fixtures/tests/fixture_corpus_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME fixtures.soundset_catalog_fixture_server
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}"
    tools/soundset-fixtures/tests/catalog_fixture_server_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
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

lmdj_add_test(
  NAME build.ci_runner_fallback
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/build/ci_runner_fallback_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 10
)

lmdj_add_test(
  NAME build.ci_build_acceleration
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/build/ci_build_acceleration_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 10
)

if(BUILD_TESTING)
  lmdj_add_test(
    NAME build.cardputer_host
    TIER component
    COMMAND "${Python3_EXECUTABLE}" tests/build/cardputer_host_build_test.py
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  )
  lmdj_add_test(
    NAME build.cardputer_transfer
    TIER component
    COMMAND "${Python3_EXECUTABLE}" tests/build/cardputer_transfer_test.py
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  )
  lmdj_add_test(
    NAME conformance.cardputer_transfer
    TIER contract
    COMMAND "${Python3_EXECUTABLE}" tests/conformance/cardputer_transfer_contract_test.py
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  )
  add_subdirectory(tests/platform/cardputer)
endif()
