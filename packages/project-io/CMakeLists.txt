set(lmdj_project_io_platform_source src/native/storage_platform.cpp)
if(EMSCRIPTEN)
  set(lmdj_project_io_platform_source src/web/storage_platform.cpp)
endif()

add_library(
  lmdj_project_io
  STATIC
    src/project_store.cpp
    src/workspace_cache.cpp
    src/project_bundle_transfer.cpp
    src/sequence_journal.cpp
    src/sequence_admission_codec.cpp
    src/soundset_store.cpp
    ${lmdj_project_io_platform_source}
)
add_library(lmdj::project_io ALIAS lmdj_project_io)

target_include_directories(
  lmdj_project_io
  PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/include"
)
target_link_libraries(
  lmdj_project_io
  PUBLIC
    lmdj::authoring_domain
  PRIVATE
    lmdj_picosha2
)
if(EMSCRIPTEN)
  set(
    lmdj_project_io_async_imports
    "['lmdj_opfs_acquire_writer','lmdj_opfs_ensure_directory','lmdj_opfs_exists','lmdj_opfs_directory_exists','lmdj_opfs_byte_length','lmdj_opfs_read_complete','lmdj_opfs_create_immutable','lmdj_opfs_replace_complete','lmdj_opfs_append_durable','lmdj_opfs_remove','lmdj_opfs_list_names','lmdj_opfs_list_directories','lmdj_opfs_remove_tree','lmdj_opfs_publish_directory_if_absent','lmdj_opfs_validate_tree']"
  )
  if(LMDJ_PROJECT_IO_WEB_TESTING)
    set(
      lmdj_project_io_async_imports
      "['lmdj_opfs_acquire_writer','lmdj_opfs_ensure_directory','lmdj_opfs_exists','lmdj_opfs_directory_exists','lmdj_opfs_byte_length','lmdj_opfs_read_complete','lmdj_opfs_create_immutable_test','lmdj_opfs_replace_complete_test','lmdj_opfs_append_durable_test','lmdj_opfs_remove','lmdj_opfs_list_names','lmdj_opfs_list_directories','lmdj_opfs_remove_tree','lmdj_opfs_publish_directory_if_absent_test','lmdj_opfs_validate_tree']"
    )
  endif()
  target_link_options(
    lmdj_project_io
    INTERFACE
      "--js-library=${CMAKE_CURRENT_SOURCE_DIR}/src/web/library_opfs_storage.js"
      -sASYNCIFY=1
      "-sASYNCIFY_IMPORTS=${lmdj_project_io_async_imports}"
      -sSTACK_SIZE=131072
      -sWASMFS
  )
  set_property(
    TARGET lmdj_project_io
    APPEND PROPERTY INTERFACE_LINK_DEPENDS
      "${CMAKE_CURRENT_SOURCE_DIR}/src/web/library_opfs_storage.js"
  )
endif()
lmdj_target_warnings(lmdj_project_io)
lmdj_target_sanitizers(lmdj_project_io)

if(BUILD_TESTING)
  find_package(Threads REQUIRED)

  add_library(
    lmdj_project_io_testable
    STATIC
      src/project_store.cpp
      src/workspace_cache.cpp
      src/project_bundle_transfer.cpp
      src/sequence_journal.cpp
      src/sequence_admission_codec.cpp
      src/soundset_store.cpp
      src/native/storage_platform.cpp
  )
  target_include_directories(
    lmdj_project_io_testable
    PUBLIC
      "${CMAKE_CURRENT_SOURCE_DIR}/include"
  )
  target_link_libraries(
    lmdj_project_io_testable
    PUBLIC
      lmdj::authoring_domain
    PRIVATE
      lmdj_picosha2
  )
  target_compile_definitions(
    lmdj_project_io_testable
    PRIVATE
      LMDJ_PROJECT_IO_TESTING=1
  )
  lmdj_target_warnings(lmdj_project_io_testable)
  lmdj_target_sanitizers(lmdj_project_io_testable)

  add_executable(
    lmdj_project_store_tests
    "${CMAKE_SOURCE_DIR}/tests/core/project_io/project_store_test.cpp"
  )
  target_include_directories(
    lmdj_project_store_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_project_store_tests
    PRIVATE
      lmdj_project_io_testable
      nlohmann_json::nlohmann_json
      Threads::Threads
  )
  target_compile_definitions(
    lmdj_project_store_tests
    PRIVATE
      LMDJ_PROJECT_IO_TESTING=1
  )
  lmdj_target_warnings(lmdj_project_store_tests)
  lmdj_target_sanitizers(lmdj_project_store_tests)
  lmdj_add_test(
    NAME project_io.project_store
    TIER component
    COMMAND lmdj_project_store_tests
    LABELS persistence
  )

  add_executable(
    lmdj_project_storage_platform_tests
    "${CMAKE_SOURCE_DIR}/tests/core/project_io/storage_platform_contract_test.cpp"
  )
  target_include_directories(
    lmdj_project_storage_platform_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_project_storage_platform_tests
    PRIVATE
      lmdj_project_io_testable
      lmdj_picosha2
      Threads::Threads
  )
  target_compile_definitions(
    lmdj_project_storage_platform_tests
    PRIVATE
      LMDJ_PROJECT_IO_TESTING=1
  )
  lmdj_target_warnings(lmdj_project_storage_platform_tests)
  lmdj_target_sanitizers(lmdj_project_storage_platform_tests)
  lmdj_add_test(
    NAME project_io.storage_platform
    TIER component
    COMMAND lmdj_project_storage_platform_tests
    LABELS persistence concurrency
  )

  add_executable(
    lmdj_project_bundle_transfer_tests
    "${CMAKE_SOURCE_DIR}/tests/core/project_io/project_bundle_transfer_test.cpp"
  )
  target_include_directories(
    lmdj_project_bundle_transfer_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_project_bundle_transfer_tests
    PRIVATE
      lmdj_project_io_testable
      lmdj_picosha2
      nlohmann_json::nlohmann_json
      Threads::Threads
  )
  target_compile_definitions(
    lmdj_project_bundle_transfer_tests
    PRIVATE
      LMDJ_PROJECT_IO_TESTING=1
  )
  lmdj_target_warnings(lmdj_project_bundle_transfer_tests)
  lmdj_target_sanitizers(lmdj_project_bundle_transfer_tests)
  lmdj_add_test(
    NAME project_io.project_bundle_transfer
    TIER component
    COMMAND lmdj_project_bundle_transfer_tests
    LABELS persistence concurrency
  )

  add_executable(
    lmdj_sequence_journal_tests
    "${CMAKE_SOURCE_DIR}/tests/core/project_io/sequence_journal_test.cpp"
  )
  target_include_directories(
    lmdj_sequence_journal_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_sequence_journal_tests
    PRIVATE
      lmdj_project_io_testable
      lmdj_picosha2
      nlohmann_json::nlohmann_json
      Threads::Threads
  )
  target_compile_definitions(
    lmdj_sequence_journal_tests
    PRIVATE
      LMDJ_PROJECT_IO_TESTING=1
      LMDJ_SOURCE_DIR="${CMAKE_SOURCE_DIR}"
  )
  lmdj_target_warnings(lmdj_sequence_journal_tests)
  lmdj_target_sanitizers(lmdj_sequence_journal_tests)
  lmdj_add_test(
    NAME project_io.sequence_journal
    TIER component
    COMMAND lmdj_sequence_journal_tests
    LABELS persistence concurrency
  )
  lmdj_add_test(
    NAME project_io.sequence_journal_stress
    TIER stress
    COMMAND lmdj_sequence_journal_tests --stress
    LABELS persistence concurrency
    TIMEOUT 30
  )
  lmdj_add_test(
    NAME project_io.sequence_fingerprint_vectors
    TIER component
    COMMAND
      "${Python3_EXECUTABLE}"
      "${CMAKE_SOURCE_DIR}/tests/conformance/sequence_fingerprint_vector_test.py"
    LABELS persistence conformance
  )

  add_executable(
    lmdj_performance_journal_tests
    "${CMAKE_SOURCE_DIR}/tests/core/project_io/performance_journal_test.cpp"
  )
  target_include_directories(
    lmdj_performance_journal_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_performance_journal_tests
    PRIVATE
      lmdj_project_io_testable
      lmdj_picosha2
      nlohmann_json::nlohmann_json
      Threads::Threads
  )
  target_compile_definitions(
    lmdj_performance_journal_tests
    PRIVATE
      LMDJ_PROJECT_IO_TESTING=1
  )
  lmdj_target_warnings(lmdj_performance_journal_tests)
  lmdj_target_sanitizers(lmdj_performance_journal_tests)
  lmdj_add_test(
    NAME project_io.performance_journal
    TIER component
    COMMAND lmdj_performance_journal_tests
    LABELS persistence concurrency
  )

  foreach(lmdj_performance_contract_test IN ITEMS lifecycle rebase)
    add_executable(
      lmdj_performance_${lmdj_performance_contract_test}_tests
      "${CMAKE_SOURCE_DIR}/tests/core/project_io/performance_${lmdj_performance_contract_test}_test.cpp"
    )
    target_include_directories(
      lmdj_performance_${lmdj_performance_contract_test}_tests
      PRIVATE
        "${CMAKE_SOURCE_DIR}"
    )
    target_link_libraries(
      lmdj_performance_${lmdj_performance_contract_test}_tests
      PRIVATE
        lmdj_project_io_testable
        nlohmann_json::nlohmann_json
        Threads::Threads
    )
    target_compile_definitions(
      lmdj_performance_${lmdj_performance_contract_test}_tests
      PRIVATE
        LMDJ_PROJECT_IO_TESTING=1
    )
    lmdj_target_warnings(
      lmdj_performance_${lmdj_performance_contract_test}_tests
    )
    lmdj_target_sanitizers(
      lmdj_performance_${lmdj_performance_contract_test}_tests
    )
    lmdj_add_test(
      NAME project_io.performance_${lmdj_performance_contract_test}
      TIER component
      COMMAND lmdj_performance_${lmdj_performance_contract_test}_tests
      LABELS persistence concurrency
    )
  endforeach()

  add_executable(
    lmdj_session_mutual_exclusion_tests
    "${CMAKE_SOURCE_DIR}/tests/core/project_io/session_mutual_exclusion_test.cpp"
  )
  target_include_directories(
    lmdj_session_mutual_exclusion_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_session_mutual_exclusion_tests
    PRIVATE
      lmdj_project_io_testable
      lmdj_picosha2
      nlohmann_json::nlohmann_json
      Threads::Threads
  )
  target_compile_definitions(
    lmdj_session_mutual_exclusion_tests
    PRIVATE
      LMDJ_PROJECT_IO_TESTING=1
  )
  lmdj_target_warnings(lmdj_session_mutual_exclusion_tests)
  lmdj_target_sanitizers(lmdj_session_mutual_exclusion_tests)
  lmdj_add_test(
    NAME project_io.session_mutual_exclusion
    TIER component
    COMMAND lmdj_session_mutual_exclusion_tests
    LABELS persistence concurrency
  )
  lmdj_add_test(
    NAME project_io.performance_writer_lease_stress
    TIER stress
    COMMAND lmdj_session_mutual_exclusion_tests --stress
    LABELS persistence concurrency
    TIMEOUT 30
  )

  add_executable(
    lmdj_soundset_store_tests
    "${CMAKE_SOURCE_DIR}/tests/core/project_io/soundset_store_test.cpp"
  )
  target_include_directories(
    lmdj_soundset_store_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_soundset_store_tests
    PRIVATE
      lmdj_project_io_testable
      lmdj_picosha2
      nlohmann_json::nlohmann_json
  )
  target_compile_definitions(
    lmdj_soundset_store_tests
    PRIVATE
      LMDJ_PROJECT_IO_TESTING=1
  )
  lmdj_target_warnings(lmdj_soundset_store_tests)
  lmdj_target_sanitizers(lmdj_soundset_store_tests)
  lmdj_add_test(
    NAME project_io.soundset_store
    TIER component
    COMMAND lmdj_soundset_store_tests
    LABELS persistence
  )

  add_executable(
    lmdj_soundset_local_adapter_tests
    "${CMAKE_SOURCE_DIR}/tests/core/project_io/soundset_local_adapter_test.cpp"
  )
  target_include_directories(
    lmdj_soundset_local_adapter_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_soundset_local_adapter_tests
    PRIVATE
      lmdj_project_io_testable
      lmdj_picosha2
  )
  target_compile_definitions(
    lmdj_soundset_local_adapter_tests
    PRIVATE
      LMDJ_PROJECT_IO_TESTING=1
  )
  lmdj_target_warnings(lmdj_soundset_local_adapter_tests)
  lmdj_target_sanitizers(lmdj_soundset_local_adapter_tests)
  lmdj_add_test(
    NAME project_io.soundset_local_adapter
    TIER component
    COMMAND lmdj_soundset_local_adapter_tests
    LABELS persistence
  )

  add_executable(
    lmdj_project_io_fault_matrix_tests
    "${CMAKE_SOURCE_DIR}/tests/core/project_io/fault_matrix_test.cpp"
  )
  target_include_directories(
    lmdj_project_io_fault_matrix_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_project_io_fault_matrix_tests
    PRIVATE
      lmdj_project_io_testable
      nlohmann_json::nlohmann_json
  )
  target_compile_definitions(
    lmdj_project_io_fault_matrix_tests
    PRIVATE
      LMDJ_PROJECT_IO_TESTING=1
  )
  lmdj_target_warnings(lmdj_project_io_fault_matrix_tests)
  lmdj_target_sanitizers(lmdj_project_io_fault_matrix_tests)
  lmdj_add_test(
    NAME project_io.fault_matrix
    TIER component
    COMMAND lmdj_project_io_fault_matrix_tests
    LABELS persistence
    TIMEOUT 30
  )
  add_executable(
    lmdj_project_io_soundset_install_commit_tests
    "${CMAKE_SOURCE_DIR}/tests/core/project_io/soundset_install_commit_test.cpp"
  )
  target_include_directories(
    lmdj_project_io_soundset_install_commit_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_project_io_soundset_install_commit_tests
    PRIVATE
      lmdj_project_io_testable
      lmdj_picosha2
      nlohmann_json::nlohmann_json
  )
  target_compile_definitions(
    lmdj_project_io_soundset_install_commit_tests
    PRIVATE
      LMDJ_PROJECT_IO_TESTING=1
  )
  lmdj_target_warnings(lmdj_project_io_soundset_install_commit_tests)
  lmdj_target_sanitizers(lmdj_project_io_soundset_install_commit_tests)
  lmdj_add_test(
    NAME project_io.soundset_install_commit
    TIER component
    COMMAND lmdj_project_io_soundset_install_commit_tests
    LABELS persistence
    TIMEOUT 30
  )
  add_executable(
    lmdj_project_io_candidate_adoption_tests
    "${CMAKE_SOURCE_DIR}/tests/core/project_io/candidate_adoption_test.cpp"
  )
  target_include_directories(
    lmdj_project_io_candidate_adoption_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_project_io_candidate_adoption_tests
    PRIVATE
      lmdj_project_io_testable
      lmdj_picosha2
      nlohmann_json::nlohmann_json
  )
  target_compile_definitions(
    lmdj_project_io_candidate_adoption_tests
    PRIVATE
      LMDJ_PROJECT_IO_TESTING=1
  )
  lmdj_target_warnings(lmdj_project_io_candidate_adoption_tests)
  lmdj_target_sanitizers(lmdj_project_io_candidate_adoption_tests)
  lmdj_add_test(
    NAME project_io.candidate_adoption
    TIER component
    COMMAND lmdj_project_io_candidate_adoption_tests
    LABELS persistence
    TIMEOUT 30
  )
endif()
