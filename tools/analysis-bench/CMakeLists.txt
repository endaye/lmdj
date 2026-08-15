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

add_library(
  lmdj_analysis_bench_peaks
  STATIC
    providers/peaks/src/provider.cpp
)
target_include_directories(
  lmdj_analysis_bench_peaks
  PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/providers/peaks/include"
)
target_link_libraries(
  lmdj_analysis_bench_peaks
  PUBLIC
    lmdj_analysis_bench_shared
    lmdj_provider_sdk
)
lmdj_target_warnings(lmdj_analysis_bench_peaks)
lmdj_target_sanitizers(lmdj_analysis_bench_peaks)

add_library(
  lmdj_analysis_bench_loudness
  STATIC
    providers/loudness/src/provider.cpp
)
target_include_directories(
  lmdj_analysis_bench_loudness
  PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/providers/loudness/include"
)
target_link_libraries(
  lmdj_analysis_bench_loudness
  PUBLIC
    lmdj_analysis_bench_shared
    lmdj_provider_sdk
)
lmdj_target_warnings(lmdj_analysis_bench_loudness)
lmdj_target_sanitizers(lmdj_analysis_bench_loudness)

add_library(
  lmdj_analysis_bench_onsets
  STATIC
    providers/onsets/src/provider.cpp
)
target_include_directories(
  lmdj_analysis_bench_onsets
  PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/providers/onsets/include"
)
target_link_libraries(
  lmdj_analysis_bench_onsets
  PUBLIC
    lmdj_analysis_bench_shared
    lmdj_provider_sdk
)
lmdj_target_warnings(lmdj_analysis_bench_onsets)
lmdj_target_sanitizers(lmdj_analysis_bench_onsets)

add_executable(
  lmdj_analysis_bench
  src/main.cpp
)
target_link_libraries(
  lmdj_analysis_bench
  PRIVATE
    lmdj_analysis_bench_peaks
    lmdj_analysis_bench_loudness
    lmdj_analysis_bench_onsets
)
lmdj_target_warnings(lmdj_analysis_bench)
lmdj_target_sanitizers(lmdj_analysis_bench)

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

  add_executable(
    lmdj_analysis_bench_peaks_tests
    tests/peaks_test.cpp
  )
  target_include_directories(
    lmdj_analysis_bench_peaks_tests
    PRIVATE
      "${CMAKE_CURRENT_SOURCE_DIR}/tests"
  )
  target_link_libraries(
    lmdj_analysis_bench_peaks_tests
    PRIVATE
      lmdj_analysis_bench_peaks
  )
  lmdj_target_warnings(lmdj_analysis_bench_peaks_tests)
  lmdj_target_sanitizers(lmdj_analysis_bench_peaks_tests)
  lmdj_add_test(
    NAME analysis_bench.peaks
    TIER unit
    COMMAND lmdj_analysis_bench_peaks_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS analysis-bench
  )

  add_executable(
    lmdj_analysis_bench_loudness_tests
    tests/loudness_test.cpp
  )
  target_include_directories(
    lmdj_analysis_bench_loudness_tests
    PRIVATE
      "${CMAKE_CURRENT_SOURCE_DIR}/tests"
  )
  target_link_libraries(
    lmdj_analysis_bench_loudness_tests
    PRIVATE
      lmdj_analysis_bench_loudness
  )
  lmdj_target_warnings(lmdj_analysis_bench_loudness_tests)
  lmdj_target_sanitizers(lmdj_analysis_bench_loudness_tests)
  lmdj_add_test(
    NAME analysis_bench.loudness
    TIER unit
    COMMAND lmdj_analysis_bench_loudness_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS analysis-bench
  )

  add_executable(
    lmdj_analysis_bench_onsets_tests
    tests/onsets_test.cpp
  )
  target_include_directories(
    lmdj_analysis_bench_onsets_tests
    PRIVATE
      "${CMAKE_CURRENT_SOURCE_DIR}/tests"
  )
  target_link_libraries(
    lmdj_analysis_bench_onsets_tests
    PRIVATE
      lmdj_analysis_bench_onsets
  )
  lmdj_target_warnings(lmdj_analysis_bench_onsets_tests)
  lmdj_target_sanitizers(lmdj_analysis_bench_onsets_tests)
  lmdj_add_test(
    NAME analysis_bench.onsets
    TIER unit
    COMMAND lmdj_analysis_bench_onsets_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS analysis-bench
  )

  lmdj_add_test(
    NAME analysis_bench.smoke
    TIER component
    COMMAND
      "${Python3_EXECUTABLE}"
      "${CMAKE_CURRENT_SOURCE_DIR}/tests/bench_smoke_test.py"
      $<TARGET_FILE:lmdj_analysis_bench>
      "${CMAKE_SOURCE_DIR}/tests/fixtures/audio/kick.wav"
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS analysis-bench
  )

  if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/.venv/bin/python3")
    lmdj_add_test(
      NAME analysis_bench.compare
      TIER component
      COMMAND
        "${CMAKE_CURRENT_SOURCE_DIR}/.venv/bin/python3"
        "${CMAKE_CURRENT_SOURCE_DIR}/compare/compare.py"
        --bench $<TARGET_FILE:lmdj_analysis_bench>
        --fixtures-dir "${CMAKE_SOURCE_DIR}/tests/fixtures/audio"
        --report "${CMAKE_BINARY_DIR}/analysis-bench-report.md"
      WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
      LABELS analysis-bench
    )
  endif()
endif()
