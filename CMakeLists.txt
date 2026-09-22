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

lmdj_add_test(
  NAME provider.slice_evaluation_corpus
  TIER component
  COMMAND
    "${Python3_EXECUTABLE}"
    tools/provider-benchmark/tests/sample_slice_evaluation_test.py
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
    lmdj_domain_candidate_adoption_tests
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
    lmdj_pattern_admission_tests
    lmdj_pattern_transport_tests
    lmdj_pattern_transport_controller_tests
    lmdj_pattern_transport_executor_tests
    lmdj_facade_candidate_store_tests
    lmdj_facade_candidate_job_tests
    lmdj_facade_candidate_audition_tests
    lmdj_facade_candidate_adoption_tests
    lmdj_facade_provider_owner_tests
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
    lmdj_project_io_candidate_adoption_tests
    lmdj_application_c_api_stress_tests
    lmdj_cardputer_resource_observation_tests
    lmdj_cardputer_audio_diagnostics_tests
    lmdj_cardputer_dma_deadline_tests
    lmdj_cardputer_lcd_tests
    lmdj_cardputer_screen_tests
    lmdj_cardputer_feedback_interleaving_tests
    lmdj_cardputer_scanner_tests
    lmdj_cardputer_dac_startup_tests
    lmdj_cardputer_codec_gain_tests
    lmdj_cardputer_shared_i2c_tests
    lmdj_cardputer_status_payload_tests
    lmdj_cardputer_observation_wire_tests
    lmdj_cardputer_audio_lifecycle_tests
    lmdj_cardputer_input_tests
    lmdj_cardputer_transfer_tests
    lmdj_cardputer_transfer_transaction_tests
    lmdj_cardputer_transfer_hash_memory_tests
    lmdj_cardputer_transfer_session_tests
  )
  if(APPLE)
    list(
      APPEND
      lmdj_coverage_targets
      lmdj_audio_coreaudio_tests
      lmdj_native_audio_probe
    )
  endif()
  # The object list is built and checked at the end of this file, because a
  # test subdirectory registered later in the tree still has to resolve here.
endif()


lmdj_add_test(
  NAME build.active_tree
  TIER contract
  COMMAND "${BASH_EXECUTABLE}" tests/build/test_active_tree.sh
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
)

lmdj_add_test(
  NAME build.release_candidate_source_projection
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_source_test.py SourceProjectionTest -v
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_candidate_source_binding
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_source_test.py SourceBindingTest
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

foreach(witness_group IN ITEMS Lifecycle State Boundary Output)
  string(TOLOWER "${witness_group}" witness_group_lower)
  lmdj_add_test(
    NAME "build.release_candidate_witness_${witness_group_lower}"
    TIER contract
    COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_witness_test.py "Witness${witness_group}Test" -v
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    TIMEOUT 120
  )
endforeach()

lmdj_add_test(
  NAME build.release_candidate_merge_receipt
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_receipt_recovery_test.py MergeReceiptTest -v
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

foreach(witness_receipt_case IN ITEMS
    test_absence_is_passive_and_does_not_create_a_marker
    test_authority_exception_cannot_leak_through_full_traceback
    test_cold_success_needs_no_extra_verification_even_at_budget_limit
    test_unconfirmed_command_output_is_pending_without_reexecution
    test_changed_actual_artifact_cannot_recover_a_success_bit
    test_missing_enrolled_history_is_not_absence
    test_artifact_changed_by_final_authority_check_is_refused)
  lmdj_add_test(
    NAME "build.release_candidate_receipt_${witness_receipt_case}"
    TIER contract
    COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_receipt_recovery_test.py "WitnessReceiptTest.${witness_receipt_case}" -v
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    TIMEOUT 60
  )
endforeach()

foreach(candidate_workspace_case IN ITEMS
    WorkspaceTest.test_late_source_guard_cannot_recreate_workspace_history
    WorkspaceTest.test_late_source_guard_cannot_accept_missing_installed_history
    WorkspaceTest.test_observation_does_not_create_worktree_or_install
    WorkspaceTest.test_real_owned_checkout_install_and_cold_recovery
    WorkspaceTest.test_unowned_existing_path_is_not_adopted_or_overwritten
    WorkspaceTest.test_process_death_after_checkout_recovers_exact_creation_once
    WorkspaceTest.test_process_death_after_install_never_replays_unknown_command
    WorkspaceTest.test_missing_enrolled_state_is_not_recreated
    WorkspaceTest.test_authority_loss_at_install_intent_stops_child
    InstallFailureTest.test_nonzero_install_is_retained_and_never_replayed)
  lmdj_add_test(
    NAME "build.release_candidate_task_workspace_${candidate_workspace_case}"
    TIER contract
    COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_task_workspace_test.py "${candidate_workspace_case}" -v
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    TIMEOUT 90
  )
endforeach()

foreach(candidate_parent_case IN ITEMS
    test_unknown_cut_post_cannot_be_replayed_by_parent
    test_unknown_cut_put_cannot_be_replayed_by_parent
    test_confirmed_witness_recovers_after_parent_checkpoint_interruption
    test_started_workspace_without_child_enrollment_is_not_recreated
    test_main_observer_cannot_recreate_missing_parent_history
    test_original_authority_exception_has_no_secret_traceback
    test_cut_review_pending_cannot_generate_witness_or_install)
  lmdj_add_test(
    NAME "build.release_candidate_transition_${candidate_parent_case}"
    TIER contract
    COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_transition_test.py "TransitionTest.${candidate_parent_case}" -v
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    TIMEOUT 120
  )
endforeach()

# Entire real-Git parent journey, including two PRs and cold receipt recovery.
# Content checks are explicit fixtures; this does not replace the full Portal
# rehearsal or live GitHub/protection/review and release acceptance.
lmdj_add_test(
  NAME build.release_candidate_transition_journey
  TIER e2e
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_transition_test.py TransitionTest.test_cut_merge_is_pending_until_the_reviewed_witness_squash -v
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  # Tier default (180 s). Measured 96.4 s on the trusted pool (Deploy Contract,
  # run 35435898163, 2026-09-19); the former 900 s predated any measurement.
  # A local macOS run can exceed it through Git launch overhead alone (589 s
  # observed; see .agents/pitfalls/macos-git-launch-overhead.md), but no Core
  # lane selects build.release_* and the lane that runs it uses unittest.
)

lmdj_add_test(
  NAME build.release_candidate_witness_schema
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_witness_test.py WitnessSchemaTest -v
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

foreach(witness_task_group IN ITEMS Lifecycle Boundary Authority Crash)
  string(TOLOWER "${witness_task_group}" witness_task_group_lower)
  lmdj_add_test(
    NAME "build.release_candidate_witness_task_${witness_task_group_lower}"
    TIER contract
    COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_witness_task_test.py "Task${witness_task_group}Test" -v
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    TIMEOUT 120
  )
endforeach()

lmdj_add_test(
  NAME build.release_candidate_witness_task_artifact
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_witness_task_test.py ArtifactCaptureTest -v
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

foreach(candidate_check_case IN ITEMS
    ChecksLifecycleTest.test_six_actual_results_and_cold_resume_without_replay
    ChecksFailureTest.test_failed_command_retains_result_without_replay
    ChecksFailureTest.test_controller_death_after_command_is_unknown
    ChecksFailureTest.test_final_authority_loss_keeps_zero_exit_unconfirmed
    ChecksFailureTest.test_snapshot_history_loss_after_command_is_not_verified
    ChecksFailureTest.test_tracked_drift_after_command_is_not_verified
    ChecksReaderTest.test_missing_enrolled_history_cannot_reset_budget
    ChecksReaderTest.test_committed_cut_cannot_invent_staged_checks
    ChecksReaderTest.test_pr_digest_and_cut_identity_must_match
    ChecksReaderTest.test_rebound_command_or_control_is_refused
    ChecksReaderTest.test_reader_authority_cannot_remove_history
    ChecksResumeTest.test_death_after_cut_commit_continues_unstarted_committed_phase)
  lmdj_add_test(
    NAME "build.release_candidate_checks_${candidate_check_case}"
    TIER contract
    COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_checks_test.py "${candidate_check_case}" -v
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    TIMEOUT 60
  )
endforeach()

lmdj_add_test(
  NAME build.release_candidate_cut_recovery
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_cut_test.py CutRecoveryTest
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_candidate_cut_safety
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_cut_test.py CutSafetyTest
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_candidate_snapshot_recovery
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_snapshot_test.py SnapshotRecoveryTest
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 90
)

lmdj_add_test(
  NAME build.release_candidate_snapshot_safety
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_snapshot_test.py SnapshotSafetyTest SnapshotStateTest
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_candidate_workspace_recovery
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_workspace_test.py WorkspaceRecoveryTest
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 90
)

lmdj_add_test(
  NAME build.release_candidate_workspace_crash
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_workspace_test.py WorkspaceCrashTest
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_candidate_workspace_safety
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_workspace_test.py WorkspaceSafetyTest
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_candidate_material
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_material_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

foreach(preparation_case IN ITEMS
    PreparationJourneyTest.test_actual_all_legs_then_cold_observation_preserves_every_history
    PreparationCrashTest.test_source_child_success_survives_parent_checkpoint_death
    PreparationCrashTest.test_snapshot_child_success_survives_parent_checkpoint_death_without_resume
    PreparationCrashTest.test_cut_child_success_survives_parent_checkpoint_death_without_commands)
  lmdj_add_test(
    NAME "build.release_candidate_preparation_${preparation_case}"
    TIER e2e
    COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_preparation_test.py "${preparation_case}" -v
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    # Tier default (180 s): 26-30 s each on the trusted pool (run 35435898163).
  )
endforeach()

foreach(preparation_group IN ITEMS PreparationEnrollmentTest PreparationSourceGuardTest)
  lmdj_add_test(
    NAME "build.release_candidate_preparation_${preparation_group}"
    TIER contract
    COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_preparation_test.py "${preparation_group}" -v
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    TIMEOUT 120
  )
endforeach()

foreach(source_setup_group IN ITEMS ReservationReaderTest SetupLifecycleTest SetupBoundaryTest SetupInstallFailureTest SetupOrphanTest)
  string(TOLOWER "${source_setup_group}" source_setup_lower)
  set(source_setup_budget 60)
  if(source_setup_group STREQUAL "SetupLifecycleTest")
    set(source_setup_budget 120)
  endif()
  lmdj_add_test(
    NAME "build.release_candidate_source_setup_${source_setup_lower}"
    TIER contract
    COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_source_setup_test.py "${source_setup_group}" -v
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    TIMEOUT "${source_setup_budget}"
  )
endforeach()

lmdj_add_test(
  NAME build.release_candidate
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_candidate_inputs
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_inputs_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
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
  NAME build.release_command_output
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_command_output_test.py -v
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_deployment_effect
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_deployment_effect_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 120
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
  NAME build.release_branch_observation
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_branch_observation_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
)

lmdj_add_test(
  NAME build.release_candidate_pr_sequence
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_pr_sequence_test.py SequenceTest
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 90
)

foreach(witness_group IN ITEMS Pr Branch Sequence Journey)
  string(TOLOWER "${witness_group}" witness_group_lower)
  set(witness_budget 60)
  if(witness_group STREQUAL "Pr")
    set(witness_budget 30)
  elseif(witness_group STREQUAL "Journey")
    set(witness_budget 120)
  endif()
  lmdj_add_test(
    NAME "build.release_witness_pr_${witness_group_lower}"
    TIER contract
    COMMAND "${Python3_EXECUTABLE}" tests/build/release_witness_pr_test.py "Witness${witness_group}Test" -v
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    TIMEOUT "${witness_budget}"
  )
endforeach()

foreach(witness_source_group IN ITEMS Binding Merge History Authority)
  string(TOLOWER "${witness_source_group}" witness_source_lower)
  lmdj_add_test(
    NAME "build.release_witness_source_${witness_source_lower}"
    TIER contract
    COMMAND "${Python3_EXECUTABLE}" tests/build/release_witness_source_test.py "Source${witness_source_group}Test" -v
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    TIMEOUT 120
  )
endforeach()

# Each producer-backed case includes a real source/Task and process lifecycle.
# Keep bounded individual cases rather than sharing a live fixture concurrently.
foreach(witness_check_case IN ITEMS
    ChecksLifecycleTest.test_actual_six_commands_bind_output_and_cold_resume_does_not_replay
    ChecksFailureTest.test_failed_command_preserves_real_result_and_never_replays
    ChecksFailureTest.test_missing_enrolled_state_never_resets_command_budget
    ChecksFailureTest.test_controller_death_after_actual_command_is_unknown_not_replayed
    ChecksFailureTest.test_final_authority_loss_keeps_exit_zero_unconfirmed
    ChecksFailureTest.test_tracked_drift_after_command_is_not_verified
    ChecksReaderTest.test_forged_pr_digest_is_not_actual_command_evidence
    ChecksReaderTest.test_same_type_authority_exception_cannot_expose_secret
    ChecksReaderTest.test_reader_authority_cannot_delete_then_recreate_history
    ChecksReaderTest.test_committed_fixture_without_staged_commands_cannot_claim_them
    ChecksReaderTest.test_rebound_command_or_control_is_rejected
    ChecksResumeTest.test_death_after_task_commit_continues_only_unstarted_committed_phase)
  lmdj_add_test(
    NAME "build.release_witness_checks_${witness_check_case}"
    TIER contract
    COMMAND "${Python3_EXECUTABLE}" tests/build/release_witness_checks_test.py "${witness_check_case}" -v
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    TIMEOUT 120
  )
endforeach()

lmdj_add_test(
  NAME build.release_candidate_pr_sequence_boundaries
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_pr_sequence_test.py -v BoundaryTest
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 90
)

lmdj_add_test(
  NAME build.release_candidate_branch
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_branch_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 30
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
  NAME build.release_candidate_pr
  TIER contract
  COMMAND "${Python3_EXECUTABLE}" tests/build/release_candidate_pr_test.py
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

# Build the coverage object list from lmdj_coverage_targets now that every test
# subdirectory is registered, then check it against the native test targets.
#
# The coverage run attributes one module signature to each instrumented binary
# it executed, and scripts/core-coverage.sh refuses a run whose signature count
# differs from this list's object count. Every native test target the coverage
# test preset selects must therefore also be named by lmdj_coverage_targets.
# The gate reads the preset's own exclusion and names the missing targets at
# configure time, instead of leaving the coverage lane to report a count that
# names neither them nor the list.
if(LMDJ_ENABLE_COVERAGE)
  set(lmdj_coverage_objects)
  foreach(lmdj_coverage_target IN LISTS lmdj_coverage_targets)
    if(NOT TARGET "${lmdj_coverage_target}")
      message(
        FATAL_ERROR
        "why: lmdj_coverage_targets names ${lmdj_coverage_target}, but this "
        "configuration defines no such target, so the coverage object list "
        "cannot be built. remedy: remove that entry or fix its spelling in the "
        "root CMakeLists.txt, then rerun scripts/core.sh coverage check."
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
  # The coverage test preset's own exclusion is the only reason a registered
  # native test binary may be absent from lmdj_coverage_targets above.
  file(READ "${CMAKE_SOURCE_DIR}/CMakePresets.json" lmdj_preset_document)
  string(JSON lmdj_test_preset_count LENGTH "${lmdj_preset_document}" testPresets)
  math(EXPR lmdj_last_test_preset_index "${lmdj_test_preset_count} - 1")
  set(lmdj_coverage_test_preset_found FALSE)
  set(lmdj_coverage_test_exclusion "")
  foreach(lmdj_test_preset_index RANGE 0 ${lmdj_last_test_preset_index})
    string(
      JSON
      lmdj_test_preset_name
      GET "${lmdj_preset_document}" testPresets ${lmdj_test_preset_index} name
    )
    if(NOT lmdj_test_preset_name STREQUAL "coverage")
      continue()
    endif()
    set(lmdj_coverage_test_preset_found TRUE)
    # An indexed read fails when the exclusion is one regex and succeeds when it
    # is a list; matching a list's JSON text as if it were its regex would
    # instead demand coverage objects for tests the lane never runs.
    string(
      JSON
      lmdj_coverage_test_exclusion_first
      ERROR_VARIABLE lmdj_coverage_test_exclusion_index_error
      GET "${lmdj_preset_document}" testPresets ${lmdj_test_preset_index}
      filter exclude name 0
    )
    if(lmdj_coverage_test_exclusion_index_error STREQUAL "NOTFOUND")
      message(
        FATAL_ERROR
        "why: the coverage test preset declares filter.exclude.name as a JSON "
        "list, which this gate cannot read as the one regex the coverage lane "
        "applies; treating the list's text as that regex would demand coverage "
        "objects for tests the lane deliberately excludes. remedy: express the "
        "coverage exclusion as a single regex in CMakePresets.json, or extend "
        "this gate to iterate the list, then rerun scripts/core.sh coverage "
        "check."
      )
    endif()
    string(
      JSON
      lmdj_coverage_test_exclusion
      ERROR_VARIABLE lmdj_coverage_test_exclusion_error
      GET "${lmdj_preset_document}" testPresets
      ${lmdj_test_preset_index} filter exclude name
    )
    if(NOT lmdj_coverage_test_exclusion_error STREQUAL "NOTFOUND")
      message(
        FATAL_ERROR
        "why: the coverage test preset declares no readable "
        "filter.exclude.name (${lmdj_coverage_test_exclusion_error}), so this "
        "gate cannot tell which registered native test targets the coverage "
        "lane executes. remedy: restore the coverage test preset's "
        "filter.exclude.name in CMakePresets.json, then rerun "
        "scripts/core.sh coverage check."
      )
    endif()
  endforeach()
  if(NOT lmdj_coverage_test_preset_found)
    message(
      FATAL_ERROR
      "why: CMakePresets.json declares no `coverage` test preset, so this gate "
      "cannot tell which registered native test targets the coverage lane "
      "executes. remedy: restore the coverage test preset, or point this gate "
      "at the preset the coverage lane runs, then rerun "
      "scripts/core.sh coverage check."
    )
  endif()
  get_property(
    lmdj_native_test_registrations
    GLOBAL
    PROPERTY lmdj_native_test_registrations
  )
  set(lmdj_selected_native_test_targets)
  set(lmdj_excluded_native_test_targets)
  foreach(lmdj_native_test_registration IN LISTS lmdj_native_test_registrations)
    string(REPLACE "|" ";" lmdj_native_test_registration_parts
      "${lmdj_native_test_registration}"
    )
    list(GET lmdj_native_test_registration_parts 0 lmdj_native_test_name)
    list(GET lmdj_native_test_registration_parts 1 lmdj_native_test_target)
    if(lmdj_native_test_name MATCHES "${lmdj_coverage_test_exclusion}")
      list(APPEND lmdj_excluded_native_test_targets "${lmdj_native_test_target}")
    else()
      list(APPEND lmdj_selected_native_test_targets "${lmdj_native_test_target}")
    endif()
  endforeach()
  set(lmdj_unlisted_coverage_targets)
  foreach(lmdj_native_test_target IN LISTS lmdj_selected_native_test_targets)
    if(NOT lmdj_native_test_target IN_LIST lmdj_coverage_targets)
      list(APPEND lmdj_unlisted_coverage_targets "${lmdj_native_test_target}")
    endif()
  endforeach()
  if(lmdj_unlisted_coverage_targets)
    list(REMOVE_DUPLICATES lmdj_unlisted_coverage_targets)
    list(SORT lmdj_unlisted_coverage_targets)
    message(
      FATAL_ERROR
      "why: these native test targets run instrumented binaries that the "
      "coverage test preset selects, but the root lmdj_coverage_targets list "
      "does not name them, so the coverage run's module signature count cannot "
      "equal its coverage object count: ${lmdj_unlisted_coverage_targets}. "
      "remedy: append each target to lmdj_coverage_targets in the root "
      "CMakeLists.txt, in the same order as its own registration, then rerun "
      "scripts/core.sh coverage check."
    )
  endif()
  # The other direction, for the entries that are decidable here: a listed
  # target whose every registration the preset excludes never runs, so its
  # object can produce no module signature. Entries no test registration names
  # at all are outside this check -- the lane's own object probe decides them.
  set(lmdj_stale_coverage_targets)
  foreach(lmdj_coverage_target IN LISTS lmdj_coverage_targets)
    if(lmdj_coverage_target IN_LIST lmdj_excluded_native_test_targets
       AND NOT lmdj_coverage_target IN_LIST lmdj_selected_native_test_targets)
      list(APPEND lmdj_stale_coverage_targets "${lmdj_coverage_target}")
    endif()
  endforeach()
  if(lmdj_stale_coverage_targets)
    list(REMOVE_DUPLICATES lmdj_stale_coverage_targets)
    list(SORT lmdj_stale_coverage_targets)
    message(
      FATAL_ERROR
      "why: every test that runs these lmdj_coverage_targets entries is "
      "excluded by the coverage test preset, so their instrumented binaries "
      "never run and the coverage run's module signature count cannot equal "
      "its coverage object count: ${lmdj_stale_coverage_targets}. remedy: "
      "remove each target from lmdj_coverage_targets in the root CMakeLists.txt "
      "when the coverage lane no longer runs it, or drop the exclusion in "
      "CMakePresets.json, then rerun scripts/core.sh coverage check."
    )
  endif()
endif()
