add_library(
  lmdj_foundation
  STATIC
    src/artifact.cpp
    src/json.cpp
    src/soundset_manifest.cpp
)
add_library(lmdj::foundation ALIAS lmdj_foundation)

target_include_directories(
  lmdj_foundation
  PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/include"
)
target_link_libraries(
  lmdj_foundation
  PUBLIC
    nlohmann_json::nlohmann_json
  PRIVATE
    lmdj_picosha2
)
lmdj_target_warnings(lmdj_foundation)
lmdj_target_sanitizers(lmdj_foundation)

if(BUILD_TESTING)
  add_executable(
    lmdj_foundation_tests
    "${CMAKE_SOURCE_DIR}/tests/core/foundation/artifact_test.cpp"
  )
  target_include_directories(
    lmdj_foundation_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_foundation_tests
    PRIVATE
      lmdj::foundation
      nlohmann_json::nlohmann_json
  )
  lmdj_target_warnings(lmdj_foundation_tests)
  lmdj_target_sanitizers(lmdj_foundation_tests)
  lmdj_add_test(
    NAME foundation.artifact
    TIER unit
    COMMAND lmdj_foundation_tests
  )

  add_executable(
    lmdj_foundation_json_tests
    "${CMAKE_SOURCE_DIR}/tests/core/foundation/json_test.cpp"
  )
  target_include_directories(
    lmdj_foundation_json_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_foundation_json_tests
    PRIVATE
      lmdj::foundation
      nlohmann_json::nlohmann_json
  )
  lmdj_target_warnings(lmdj_foundation_json_tests)
  lmdj_target_sanitizers(lmdj_foundation_json_tests)
  lmdj_add_test(
    NAME foundation.json
    TIER unit
    COMMAND lmdj_foundation_json_tests
  )

  add_executable(
    lmdj_foundation_soundset_manifest_tests
    "${CMAKE_SOURCE_DIR}/tests/core/foundation/soundset_manifest_test.cpp"
  )
  target_include_directories(
    lmdj_foundation_soundset_manifest_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_foundation_soundset_manifest_tests
    PRIVATE
      lmdj::foundation
      nlohmann_json::nlohmann_json
  )
  target_compile_definitions(
    lmdj_foundation_soundset_manifest_tests
    PRIVATE
      LMDJ_SOURCE_DIR="${CMAKE_SOURCE_DIR}"
  )
  lmdj_target_warnings(lmdj_foundation_soundset_manifest_tests)
  lmdj_target_sanitizers(lmdj_foundation_soundset_manifest_tests)
  lmdj_add_test(
    NAME foundation.soundset_manifest
    TIER unit
    COMMAND lmdj_foundation_soundset_manifest_tests
  )
endif()
