add_library(
  lmdj_authoring_domain
  STATIC
    src/project.cpp
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
  lmdj_add_test(
    NAME domain.model_sequence
    TIER unit
    COMMAND lmdj_domain_model_sequence_tests
    TIMEOUT 10
    LABELS domain generated
  )
endif()
