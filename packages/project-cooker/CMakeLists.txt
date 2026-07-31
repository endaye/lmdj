add_library(
  lmdj_project_cooker
  STATIC
    src/wav_reader.cpp
    src/project_cooker.cpp
)
add_library(lmdj::project_cooker ALIAS lmdj_project_cooker)

target_include_directories(
  lmdj_project_cooker
  PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/include"
)
target_link_libraries(
  lmdj_project_cooker
  PUBLIC
    lmdj::authoring_domain
)
lmdj_target_warnings(lmdj_project_cooker)
lmdj_target_sanitizers(lmdj_project_cooker)

if(BUILD_TESTING)
  add_executable(
    lmdj_project_cooker_tests
    "${CMAKE_SOURCE_DIR}/tests/core/cooker/project_cooker_test.cpp"
  )
  target_include_directories(
    lmdj_project_cooker_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_project_cooker_tests
    PRIVATE
      lmdj::project_cooker
  )
  lmdj_target_warnings(lmdj_project_cooker_tests)
  lmdj_target_sanitizers(lmdj_project_cooker_tests)
  lmdj_add_test(
    NAME cooker.project
    TIER component
    COMMAND lmdj_project_cooker_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS audio
  )

  add_executable(
    lmdj_project_cooker_determinism_matrix_tests
    "${CMAKE_SOURCE_DIR}/tests/core/cooker/determinism_matrix_test.cpp"
  )
  target_include_directories(
    lmdj_project_cooker_determinism_matrix_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_project_cooker_determinism_matrix_tests
    PRIVATE
      lmdj::project_cooker
  )
  lmdj_target_warnings(lmdj_project_cooker_determinism_matrix_tests)
  lmdj_target_sanitizers(lmdj_project_cooker_determinism_matrix_tests)
  lmdj_add_test(
    NAME cooker.determinism_matrix
    TIER unit
    COMMAND lmdj_project_cooker_determinism_matrix_tests
    TIMEOUT 10
    LABELS audio generated
  )
endif()
