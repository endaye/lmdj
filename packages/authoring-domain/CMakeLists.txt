add_library(
  lmdj_authoring_domain
  STATIC
    src/project.cpp
    src/migration.cpp
    src/command_handler.cpp
)
add_library(lmdj::authoring_domain ALIAS lmdj_authoring_domain)

target_include_directories(
  lmdj_authoring_domain
  PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/include"
)
target_link_libraries(
  lmdj_authoring_domain
  PUBLIC
    lmdj::foundation
)
lmdj_target_warnings(lmdj_authoring_domain)
lmdj_target_sanitizers(lmdj_authoring_domain)

if(BUILD_TESTING)
  add_executable(
    lmdj_domain_project_tests
    "${CMAKE_SOURCE_DIR}/tests/core/domain/project_test.cpp"
  )
  target_include_directories(
    lmdj_domain_project_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_domain_project_tests
    PRIVATE
      lmdj::authoring_domain
  )
  lmdj_target_warnings(lmdj_domain_project_tests)
  lmdj_target_sanitizers(lmdj_domain_project_tests)
  lmdj_add_test(
    NAME domain.project
    TIER unit
    COMMAND lmdj_domain_project_tests
  )

  add_executable(
    lmdj_domain_command_handler_tests
    "${CMAKE_SOURCE_DIR}/tests/core/domain/command_handler_test.cpp"
  )
  target_include_directories(
    lmdj_domain_command_handler_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_domain_command_handler_tests
    PRIVATE
      lmdj::authoring_domain
  )
  lmdj_target_warnings(lmdj_domain_command_handler_tests)
  lmdj_target_sanitizers(lmdj_domain_command_handler_tests)
  lmdj_add_test(
    NAME domain.command_handler
    TIER unit
    COMMAND lmdj_domain_command_handler_tests
  )

  add_executable(
    lmdj_domain_performance_tests
    "${CMAKE_SOURCE_DIR}/tests/core/domain/performance_test.cpp"
  )
  target_include_directories(
    lmdj_domain_performance_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_domain_performance_tests
    PRIVATE
      lmdj::authoring_domain
  )
  lmdj_target_warnings(lmdj_domain_performance_tests)
  lmdj_target_sanitizers(lmdj_domain_performance_tests)
  lmdj_add_test(
    NAME domain.performance
    TIER unit
    COMMAND lmdj_domain_performance_tests
  )

  add_executable(
    lmdj_domain_migration_v4_tests
    "${CMAKE_SOURCE_DIR}/tests/core/domain/migration_v4_test.cpp"
  )
  target_include_directories(
    lmdj_domain_migration_v4_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_domain_migration_v4_tests
    PRIVATE
      lmdj::authoring_domain
  )
  target_compile_definitions(
    lmdj_domain_migration_v4_tests
    PRIVATE
      LMDJ_SOURCE_DIR="${CMAKE_SOURCE_DIR}"
  )
  lmdj_target_warnings(lmdj_domain_migration_v4_tests)
  lmdj_target_sanitizers(lmdj_domain_migration_v4_tests)
  lmdj_add_test(
    NAME domain.migration_v4
    TIER unit
    COMMAND lmdj_domain_migration_v4_tests
  )

  add_executable(
    lmdj_domain_model_sequence_tests
    "${CMAKE_SOURCE_DIR}/tests/core/domain/model_sequence_test.cpp"
  )
  target_include_directories(
    lmdj_domain_model_sequence_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_domain_model_sequence_tests
    PRIVATE
      lmdj::authoring_domain
  )
  lmdj_target_warnings(lmdj_domain_model_sequence_tests)
  lmdj_target_sanitizers(lmdj_domain_model_sequence_tests)
  # One generated matrix pass costs the same whichever property asserts on it,
  # so the seed range is the only axis that divides it. Four shards each carry
  # their own unit budget and together cover the same 256 seeds; a bare run of
  # the binary still covers all of them for local work.
  lmdj_add_test(
    NAME domain.model_sequence_seeds_0_63
    TIER unit
    COMMAND lmdj_domain_model_sequence_tests 0 63
    LABELS domain generated
  )

  lmdj_add_test(
    NAME domain.model_sequence_seeds_64_127
    TIER unit
    COMMAND lmdj_domain_model_sequence_tests 64 127
    LABELS domain generated
  )

  lmdj_add_test(
    NAME domain.model_sequence_seeds_128_191
    TIER unit
    COMMAND lmdj_domain_model_sequence_tests 128 191
    LABELS domain generated
  )

  lmdj_add_test(
    NAME domain.model_sequence_seeds_192_255
    TIER unit
    COMMAND lmdj_domain_model_sequence_tests 192 255
    LABELS domain generated
  )
endif()
