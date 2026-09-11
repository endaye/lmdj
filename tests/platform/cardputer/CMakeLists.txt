find_package(Threads REQUIRED)
add_executable(lmdj_cardputer_audio_lifecycle_tests
  audio_lifecycle_test.cpp
  "${CMAKE_SOURCE_DIR}/apps/cardputer-host/main/audio_driver.cpp"
  "${CMAKE_SOURCE_DIR}/apps/cardputer-host/main/runtime_host.cpp")
target_link_libraries(lmdj_cardputer_audio_lifecycle_tests PRIVATE lmdj::runtime_facade Threads::Threads)
target_include_directories(lmdj_cardputer_audio_lifecycle_tests PRIVATE "${CMAKE_SOURCE_DIR}")
lmdj_target_warnings(lmdj_cardputer_audio_lifecycle_tests)
lmdj_target_sanitizers(lmdj_cardputer_audio_lifecycle_tests)
foreach(scenario prewarm stop quiescence_failure partial_configuration short_write
    invalid_block mute_failure enable_failure zero_failure drain_failure unmute_failure release_failure
    host_mapping host_profile host_physical_stop pcm_ramp pcm_nonfinite explicit_prewarm
    host_volume host_mute host_output_release host_start_output
    threaded_stop_reload threaded_output_failure threaded_destruction)
  lmdj_add_test(NAME platform.cardputer.audio.${scenario} TIER component
    COMMAND lmdj_cardputer_audio_lifecycle_tests ${scenario})
endforeach()
lmdj_add_test(NAME platform.cardputer.audio.threaded_stress TIER stress
  COMMAND lmdj_cardputer_audio_lifecycle_tests threaded_stress)
