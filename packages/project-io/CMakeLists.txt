add_library(
  lmdj_project_io
  STATIC
    src/project_store.cpp
    src/take_journal.cpp
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
  lmdj_target_warnings(lmdj_project_store_tests)
  lmdj_target_sanitizers(lmdj_project_store_tests)
  add_test(NAME project_io.project_store COMMAND lmdj_project_store_tests)

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
  lmdj_target_warnings(lmdj_take_journal_tests)
  lmdj_target_sanitizers(lmdj_take_journal_tests)
  add_test(NAME project_io.take_journal COMMAND lmdj_take_journal_tests)
endif()
