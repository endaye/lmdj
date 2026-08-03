add_library(
  lmdj_project_io
  STATIC
    src/project_store.cpp
    src/take_journal.cpp
    src/native/storage_platform.cpp
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
lmdj_target_warnings(lmdj_project_io)
lmdj_target_sanitizers(lmdj_project_io)

if(BUILD_TESTING)
  find_package(Threads REQUIRED)

  add_library(
    lmdj_project_io_testable
    STATIC
      src/project_store.cpp
      src/take_journal.cpp
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
    lmdj_take_journal_tests
    "${CMAKE_SOURCE_DIR}/tests/core/project_io/take_journal_test.cpp"
  )
  target_include_directories(
    lmdj_take_journal_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_take_journal_tests
    PRIVATE
      lmdj_project_io_testable
      nlohmann_json::nlohmann_json
  )
  target_compile_definitions(
    lmdj_take_journal_tests
    PRIVATE
      LMDJ_PROJECT_IO_TESTING=1
  )
  lmdj_target_warnings(lmdj_take_journal_tests)
  lmdj_target_sanitizers(lmdj_take_journal_tests)
  lmdj_add_test(
    NAME project_io.take_journal
    TIER component
    COMMAND lmdj_take_journal_tests
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
endif()
