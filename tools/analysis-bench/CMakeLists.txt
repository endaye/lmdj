add_library(
  lmdj_analysis_bench_shared
  STATIC
    shared/src/wav_pcm16.cpp
)
target_include_directories(
  lmdj_analysis_bench_shared
  PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/shared/include"
)
target_link_libraries(
  lmdj_analysis_bench_shared
  PUBLIC
    lmdj_foundation
)
lmdj_target_warnings(lmdj_analysis_bench_shared)
lmdj_target_sanitizers(lmdj_analysis_bench_shared)

if(BUILD_TESTING)
  add_executable(
    lmdj_analysis_bench_wav_tests
    tests/wav_pcm16_test.cpp
  )
  target_include_directories(
    lmdj_analysis_bench_wav_tests
    PRIVATE
      "${CMAKE_CURRENT_SOURCE_DIR}/tests"
  )
  target_link_libraries(
    lmdj_analysis_bench_wav_tests
    PRIVATE
      lmdj_analysis_bench_shared
      lmdj_provider_sdk
  )
  lmdj_target_warnings(lmdj_analysis_bench_wav_tests)
  lmdj_target_sanitizers(lmdj_analysis_bench_wav_tests)
  lmdj_add_test(
    NAME analysis_bench.wav
    TIER unit
    COMMAND lmdj_analysis_bench_wav_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS analysis-bench
  )
endif()
