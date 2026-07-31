add_library(
  lmdj_audio_runtime
  STATIC
    src/offline_renderer.cpp
    src/wav_writer.cpp
)
add_library(lmdj::audio_runtime ALIAS lmdj_audio_runtime)

target_include_directories(
  lmdj_audio_runtime
  PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/include"
)
target_link_libraries(
  lmdj_audio_runtime
  PUBLIC
    lmdj::foundation
    lmdj::project_cooker
)
lmdj_target_warnings(lmdj_audio_runtime)
lmdj_target_sanitizers(lmdj_audio_runtime)

if(BUILD_TESTING)
  add_executable(
    lmdj_audio_runtime_tests
    "${CMAKE_SOURCE_DIR}/tests/core/audio/offline_renderer_test.cpp"
  )
  target_include_directories(
    lmdj_audio_runtime_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
      "${CMAKE_CURRENT_SOURCE_DIR}/include"
  )
  target_link_libraries(
    lmdj_audio_runtime_tests
    PRIVATE
      lmdj::audio_runtime
  )
  lmdj_target_warnings(lmdj_audio_runtime_tests)
  lmdj_target_sanitizers(lmdj_audio_runtime_tests)
  lmdj_add_test(
    NAME audio.offline_renderer
    TIER component
    COMMAND lmdj_audio_runtime_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS audio
  )
endif()
