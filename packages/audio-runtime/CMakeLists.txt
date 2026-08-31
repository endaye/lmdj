add_library(
  lmdj_audio_runtime
  STATIC
    src/offline_renderer.cpp
    src/wav_writer.cpp
)
add_library(lmdj::audio_runtime ALIAS lmdj_audio_runtime)

target_sources(
  lmdj_audio_runtime
  PRIVATE
    src/master_fx.cpp
    src/prepared_sample_bank.cpp
    src/realtime_engine.cpp
)

if(EMSCRIPTEN)
  target_sources(
    lmdj_audio_runtime
    PRIVATE src/web/realtime_audio_worklet.cpp
  )
  if(LMDJ_WEB_AUDIO_CONFORMANCE)
    target_compile_definitions(
      lmdj_audio_runtime PRIVATE LMDJ_WEB_AUDIO_CONFORMANCE=1
    )
  endif()
endif()

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
  add_library(
    lmdj_audio_runtime_testable
    STATIC
      src/master_fx.cpp
      src/prepared_sample_bank.cpp
      src/realtime_engine.cpp
  )
  target_include_directories(
    lmdj_audio_runtime_testable
    PUBLIC
      "${CMAKE_CURRENT_SOURCE_DIR}/include"
  )
  target_link_libraries(
    lmdj_audio_runtime_testable
    PUBLIC
      lmdj::foundation
      lmdj::project_cooker
  )
  target_compile_definitions(
    lmdj_audio_runtime_testable
    PRIVATE LMDJ_AUDIO_RUNTIME_TESTING=1
  )
  lmdj_target_warnings(lmdj_audio_runtime_testable)
  lmdj_target_sanitizers(lmdj_audio_runtime_testable)

  add_executable(
    lmdj_prepared_sample_bank_tests
    "${CMAKE_SOURCE_DIR}/tests/core/audio/prepared_sample_bank_test.cpp"
  )
  target_include_directories(
    lmdj_prepared_sample_bank_tests PRIVATE "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_prepared_sample_bank_tests PRIVATE lmdj::audio_runtime
  )
  lmdj_target_warnings(lmdj_prepared_sample_bank_tests)
  lmdj_target_sanitizers(lmdj_prepared_sample_bank_tests)
  lmdj_add_test(
    NAME audio.prepared_sample_bank
    TIER component
    COMMAND lmdj_prepared_sample_bank_tests
    LABELS audio
  )

  add_executable(
    lmdj_realtime_engine_tests
    "${CMAKE_SOURCE_DIR}/tests/core/audio/realtime_engine_test.cpp"
  )
  target_include_directories(
    lmdj_realtime_engine_tests
    PRIVATE
      "${CMAKE_SOURCE_DIR}"
      "${CMAKE_CURRENT_SOURCE_DIR}/src"
  )
  target_link_libraries(
    lmdj_realtime_engine_tests PRIVATE lmdj_audio_runtime_testable
  )
  target_compile_definitions(
    lmdj_realtime_engine_tests PRIVATE LMDJ_AUDIO_RUNTIME_TESTING=1
  )
  lmdj_target_warnings(lmdj_realtime_engine_tests)
  lmdj_target_sanitizers(lmdj_realtime_engine_tests)
  lmdj_add_test(
    NAME audio.realtime_engine
    TIER component
    COMMAND lmdj_realtime_engine_tests
    LABELS audio concurrency
  )

  add_executable(
    lmdj_snapshot_publication_invariant_tests
    "${CMAKE_SOURCE_DIR}/tests/core/audio/snapshot_publication_invariant_test.cpp"
  )
  target_include_directories(
    lmdj_snapshot_publication_invariant_tests PRIVATE "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_snapshot_publication_invariant_tests PRIVATE lmdj::audio_runtime
  )
  lmdj_target_warnings(lmdj_snapshot_publication_invariant_tests)
  lmdj_target_sanitizers(lmdj_snapshot_publication_invariant_tests)
  lmdj_add_test(
    NAME audio.snapshot_publication_invariant
    TIER component
    COMMAND lmdj_snapshot_publication_invariant_tests
    LABELS audio concurrency
  )

  add_executable(
    lmdj_audio_realtime_queue_tests
    "${CMAKE_SOURCE_DIR}/tests/core/audio/fixed_spsc_queue_test.cpp"
  )
  target_include_directories(
    lmdj_audio_realtime_queue_tests PRIVATE "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_audio_realtime_queue_tests PRIVATE lmdj::audio_runtime
  )
  lmdj_target_warnings(lmdj_audio_realtime_queue_tests)
  lmdj_target_sanitizers(lmdj_audio_realtime_queue_tests)
  lmdj_add_test(
    NAME audio.realtime_queue
    TIER unit
    COMMAND lmdj_audio_realtime_queue_tests
    LABELS audio concurrency
  )

  add_executable(
    lmdj_master_fx_tests
    "${CMAKE_SOURCE_DIR}/tests/core/audio/master_fx_test.cpp"
  )
  target_include_directories(
    lmdj_master_fx_tests PRIVATE "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_master_fx_tests PRIVATE lmdj::audio_runtime
  )
  lmdj_target_warnings(lmdj_master_fx_tests)
  lmdj_target_sanitizers(lmdj_master_fx_tests)
  lmdj_add_test(
    NAME audio.master_fx
    TIER component
    COMMAND lmdj_master_fx_tests
    LABELS audio
  )

  add_executable(
    lmdj_master_fx_determinism_tests
    "${CMAKE_SOURCE_DIR}/tests/core/audio/master_fx_determinism_test.cpp"
  )
  target_include_directories(
    lmdj_master_fx_determinism_tests PRIVATE "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_master_fx_determinism_tests PRIVATE lmdj::audio_runtime
  )
  lmdj_target_warnings(lmdj_master_fx_determinism_tests)
  lmdj_target_sanitizers(lmdj_master_fx_determinism_tests)
  lmdj_add_test(
    NAME audio.master_fx_determinism
    TIER component
    COMMAND lmdj_master_fx_determinism_tests
    LABELS audio concurrency
  )

  add_executable(
    lmdj_master_fx_allocation_guard_tests
    "${CMAKE_SOURCE_DIR}/tests/core/audio/master_fx_allocation_guard_test.cpp"
  )
  target_include_directories(
    lmdj_master_fx_allocation_guard_tests PRIVATE "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_master_fx_allocation_guard_tests PRIVATE lmdj::audio_runtime
  )
  lmdj_target_warnings(lmdj_master_fx_allocation_guard_tests)
  lmdj_target_sanitizers(lmdj_master_fx_allocation_guard_tests)
  lmdj_add_test(
    NAME audio.master_fx_allocation_guard
    TIER component
    COMMAND lmdj_master_fx_allocation_guard_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS audio concurrency
  )

  find_package(Threads REQUIRED)
  add_executable(
    lmdj_realtime_engine_stress_tests
    "${CMAKE_SOURCE_DIR}/tests/core/audio/realtime_engine_stress_test.cpp"
  )
  target_include_directories(
    lmdj_realtime_engine_stress_tests PRIVATE "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_realtime_engine_stress_tests
    PRIVATE lmdj::audio_runtime Threads::Threads
  )
  lmdj_target_warnings(lmdj_realtime_engine_stress_tests)
  lmdj_target_sanitizers(lmdj_realtime_engine_stress_tests)
  lmdj_add_test(
    NAME audio.realtime_spsc_stress
    TIER stress
    COMMAND lmdj_realtime_engine_stress_tests
    LABELS audio concurrency
    TIMEOUT 180
  )

  add_executable(
    lmdj_snapshot_publication_stress_tests
    "${CMAKE_SOURCE_DIR}/tests/core/audio/snapshot_publication_stress_test.cpp"
  )
  target_include_directories(
    lmdj_snapshot_publication_stress_tests PRIVATE "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_snapshot_publication_stress_tests
    PRIVATE lmdj::audio_runtime Threads::Threads
  )
  lmdj_target_warnings(lmdj_snapshot_publication_stress_tests)
  lmdj_target_sanitizers(lmdj_snapshot_publication_stress_tests)
  lmdj_add_test(
    NAME audio.snapshot_publication_stress
    TIER stress
    COMMAND lmdj_snapshot_publication_stress_tests
    LABELS audio concurrency
    TIMEOUT 180
  )

  add_executable(
    lmdj_long_sample_publication_stress_tests
    "${CMAKE_SOURCE_DIR}/tests/core/audio/long_sample_publication_stress_test.cpp"
  )
  target_include_directories(
    lmdj_long_sample_publication_stress_tests PRIVATE "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_long_sample_publication_stress_tests
    PRIVATE lmdj::audio_runtime Threads::Threads
  )
  lmdj_target_warnings(lmdj_long_sample_publication_stress_tests)
  lmdj_target_sanitizers(lmdj_long_sample_publication_stress_tests)
  lmdj_add_test(
    NAME audio.long_sample_publication_stress
    TIER stress
    COMMAND lmdj_long_sample_publication_stress_tests
    LABELS audio concurrency
    TIMEOUT 180
  )

  add_executable(
    lmdj_master_fx_stress_tests
    "${CMAKE_SOURCE_DIR}/tests/core/audio/master_fx_stress_test.cpp"
  )
  target_include_directories(
    lmdj_master_fx_stress_tests PRIVATE "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_master_fx_stress_tests
    PRIVATE lmdj::audio_runtime Threads::Threads
  )
  if(LMDJ_SANITIZER STREQUAL "none")
    target_compile_definitions(
      lmdj_master_fx_stress_tests
      PRIVATE LMDJ_MASTER_FX_VERIFY_REALTIME_DEADLINE=1
    )
  else()
    target_compile_definitions(
      lmdj_master_fx_stress_tests
      PRIVATE LMDJ_MASTER_FX_VERIFY_REALTIME_DEADLINE=0
    )
  endif()
  lmdj_target_warnings(lmdj_master_fx_stress_tests)
  lmdj_target_sanitizers(lmdj_master_fx_stress_tests)
  lmdj_add_test(
    NAME audio.master_fx_stress
    TIER stress
    COMMAND lmdj_master_fx_stress_tests
    LABELS audio concurrency
    TIMEOUT 180
  )

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

if(APPLE)
  find_library(LMDJ_AUDIO_UNIT_FRAMEWORK AudioUnit REQUIRED)
  find_library(LMDJ_CORE_AUDIO_FRAMEWORK CoreAudio REQUIRED)
  find_library(LMDJ_CORE_FOUNDATION_FRAMEWORK CoreFoundation REQUIRED)
  add_library(
    lmdj_audio_coreaudio STATIC
    src/apple/coreaudio_services.cpp
    src/apple/coreaudio_output.cpp
  )
  add_library(lmdj::audio_coreaudio ALIAS lmdj_audio_coreaudio)
  target_include_directories(
    lmdj_audio_coreaudio
    PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include"
    PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src/apple"
  )
  target_link_libraries(
    lmdj_audio_coreaudio
    PUBLIC lmdj::audio_runtime
    PRIVATE
      "${LMDJ_AUDIO_UNIT_FRAMEWORK}"
      "${LMDJ_CORE_AUDIO_FRAMEWORK}"
      "${LMDJ_CORE_FOUNDATION_FRAMEWORK}"
  )
  lmdj_target_warnings(lmdj_audio_coreaudio)
  lmdj_target_sanitizers(lmdj_audio_coreaudio)

  if(BUILD_TESTING)
    add_executable(
      lmdj_audio_coreaudio_tests
      "${CMAKE_SOURCE_DIR}/tests/core/audio/coreaudio_output_test.cpp"
    )
    target_include_directories(
      lmdj_audio_coreaudio_tests
      PRIVATE "${CMAKE_SOURCE_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}/src/apple"
    )
    target_link_libraries(
      lmdj_audio_coreaudio_tests PRIVATE lmdj::audio_coreaudio
    )
    lmdj_target_warnings(lmdj_audio_coreaudio_tests)
    lmdj_target_sanitizers(lmdj_audio_coreaudio_tests)
    lmdj_add_test(
      NAME audio.coreaudio_output
      TIER component
      COMMAND lmdj_audio_coreaudio_tests
      LABELS audio
    )

    add_executable(
      lmdj_native_audio_probe
      "${CMAKE_SOURCE_DIR}/tests/platform/audio/native_audio_probe.cpp"
    )
    set_target_properties(
      lmdj_native_audio_probe PROPERTIES OUTPUT_NAME lmdj-native-audio-probe
    )
    target_link_libraries(
      lmdj_native_audio_probe
      PRIVATE lmdj::audio_coreaudio lmdj::foundation
    )
    lmdj_target_warnings(lmdj_native_audio_probe)
    lmdj_target_sanitizers(lmdj_native_audio_probe)
  endif()
endif()
