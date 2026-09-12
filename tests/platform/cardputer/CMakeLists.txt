find_package(Threads REQUIRED)
add_executable(lmdj_cardputer_resource_observation_tests resource_observation_test.cpp)
target_compile_definitions(lmdj_cardputer_resource_observation_tests PRIVATE ESP_PLATFORM)
target_include_directories(lmdj_cardputer_resource_observation_tests PRIVATE
  "${CMAKE_CURRENT_SOURCE_DIR}/fake_esp" "${CMAKE_SOURCE_DIR}"
  "${CMAKE_SOURCE_DIR}/packages/application-facade/include"
  "${CMAKE_SOURCE_DIR}/packages/project-cooker/include")
lmdj_target_warnings(lmdj_cardputer_resource_observation_tests)
lmdj_target_sanitizers(lmdj_cardputer_resource_observation_tests)
foreach(scenario capabilities mapping absent stack interval resample)
  lmdj_add_test(NAME platform.cardputer.resources.${scenario} TIER component
    COMMAND lmdj_cardputer_resource_observation_tests ${scenario})
endforeach()
add_executable(lmdj_cardputer_audio_diagnostics_tests audio_diagnostics_test.cpp)
target_include_directories(lmdj_cardputer_audio_diagnostics_tests PRIVATE "${CMAKE_SOURCE_DIR}")
lmdj_target_warnings(lmdj_cardputer_audio_diagnostics_tests)
lmdj_target_sanitizers(lmdj_cardputer_audio_diagnostics_tests)
foreach(scenario percentile capacity invalid boundaries failures)
  lmdj_add_test(NAME platform.cardputer.audio_diagnostics.${scenario} TIER component
    COMMAND lmdj_cardputer_audio_diagnostics_tests ${scenario})
endforeach()
add_executable(lmdj_cardputer_dma_deadline_tests dma_deadline_test.cpp
  "${CMAKE_SOURCE_DIR}/apps/cardputer-host/main/audio_driver.cpp")
target_compile_definitions(lmdj_cardputer_dma_deadline_tests PRIVATE ESP_PLATFORM)
target_include_directories(lmdj_cardputer_dma_deadline_tests PRIVATE
  "${CMAKE_CURRENT_SOURCE_DIR}/fake_esp" "${CMAKE_SOURCE_DIR}")
lmdj_target_warnings(lmdj_cardputer_dma_deadline_tests)
lmdj_target_sanitizers(lmdj_cardputer_dma_deadline_tests)
foreach(scenario ontime before during)
  lmdj_add_test(NAME platform.cardputer.dma_deadline.${scenario} TIER component
    COMMAND lmdj_cardputer_dma_deadline_tests ${scenario})
endforeach()
add_executable(lmdj_cardputer_feedback_interleaving_tests
  pad_feedback_interleaving_test.cpp
  "${CMAKE_SOURCE_DIR}/apps/cardputer-host/main/runtime_host.cpp")
target_include_directories(lmdj_cardputer_feedback_interleaving_tests PRIVATE "${CMAKE_SOURCE_DIR}")
target_link_libraries(lmdj_cardputer_feedback_interleaving_tests PRIVATE lmdj::runtime_facade Threads::Threads)
lmdj_target_warnings(lmdj_cardputer_feedback_interleaving_tests)
lmdj_target_sanitizers(lmdj_cardputer_feedback_interleaving_tests)
lmdj_add_test(NAME platform.cardputer.input.feedback_interleaving TIER component
  COMMAND lmdj_cardputer_feedback_interleaving_tests)
# Keep the AudioSession implementation native while exercising the actual ESP
# scanner. The fake models FIFO count/pop, not electrical timing or speaker IO.
add_library(lmdj_cardputer_scanner_native_host OBJECT
  "${CMAKE_SOURCE_DIR}/apps/cardputer-host/main/runtime_host.cpp")
target_link_libraries(lmdj_cardputer_scanner_native_host PRIVATE lmdj::runtime_facade Threads::Threads)
lmdj_target_warnings(lmdj_cardputer_scanner_native_host)
lmdj_target_sanitizers(lmdj_cardputer_scanner_native_host)
add_executable(lmdj_cardputer_scanner_tests keyboard_scanner_test.cpp
  "${CMAKE_SOURCE_DIR}/apps/cardputer-host/main/keyboard_scanner.cpp"
  "${CMAKE_SOURCE_DIR}/apps/cardputer-host/main/keyboard.cpp"
  "${CMAKE_SOURCE_DIR}/apps/cardputer-host/main/display.cpp"
  "${CMAKE_SOURCE_DIR}/apps/cardputer-host/main/input_controller.cpp"
  $<TARGET_OBJECTS:lmdj_cardputer_scanner_native_host>)
target_compile_definitions(lmdj_cardputer_scanner_tests PRIVATE ESP_PLATFORM)
target_include_directories(lmdj_cardputer_scanner_tests PRIVATE
  "${CMAKE_CURRENT_SOURCE_DIR}/fake_esp" "${CMAKE_SOURCE_DIR}")
target_link_libraries(lmdj_cardputer_scanner_tests PRIVATE lmdj::runtime_facade Threads::Threads)
lmdj_target_warnings(lmdj_cardputer_scanner_tests)
lmdj_target_sanitizers(lmdj_cardputer_scanner_tests)
foreach(scenario a s d f command)
  lmdj_add_test(NAME platform.cardputer.scanner.${scenario} TIER component
    COMMAND lmdj_cardputer_scanner_tests ${scenario})
endforeach()
add_executable(lmdj_cardputer_dac_startup_tests dac_startup_test.cpp
  "${CMAKE_SOURCE_DIR}/apps/cardputer-host/main/audio_driver.cpp")
target_compile_definitions(lmdj_cardputer_dac_startup_tests PRIVATE ESP_PLATFORM)
target_include_directories(lmdj_cardputer_dac_startup_tests PRIVATE
  "${CMAKE_CURRENT_SOURCE_DIR}/fake_esp" "${CMAKE_SOURCE_DIR}")
lmdj_target_warnings(lmdj_cardputer_dac_startup_tests)
lmdj_target_sanitizers(lmdj_cardputer_dac_startup_tests)
foreach(scenario order power_failure)
  lmdj_add_test(NAME platform.cardputer.dac_startup.${scenario} TIER component
    COMMAND lmdj_cardputer_dac_startup_tests ${scenario})
endforeach()
add_executable(lmdj_cardputer_codec_gain_tests codec_gain_test.cpp
  "${CMAKE_SOURCE_DIR}/products/lmdj/src/cardputer_assembly.cpp"
  "${CMAKE_SOURCE_DIR}/apps/cardputer-host/main/audio_driver.cpp")
target_compile_definitions(lmdj_cardputer_codec_gain_tests PRIVATE ESP_PLATFORM)
target_link_libraries(lmdj_cardputer_codec_gain_tests PRIVATE lmdj::runtime_facade)
target_include_directories(lmdj_cardputer_codec_gain_tests PRIVATE
  "${CMAKE_CURRENT_SOURCE_DIR}/fake_esp" "${CMAKE_SOURCE_DIR}")
lmdj_target_warnings(lmdj_cardputer_codec_gain_tests)
lmdj_target_sanitizers(lmdj_cardputer_codec_gain_tests)
lmdj_add_test(NAME platform.cardputer.codec_gain TIER component
  COMMAND lmdj_cardputer_codec_gain_tests)
# Compile the real ESP audio implementation against a GPIO-routing fake.
# This checks shared-bus lifetime, not DMA timing or physical sound; those
# remain covered by the existing audio tests and device acceptance.
add_executable(lmdj_cardputer_shared_i2c_tests shared_i2c_test.cpp
  "${CMAKE_SOURCE_DIR}/apps/cardputer-host/main/audio_driver.cpp")
target_compile_definitions(lmdj_cardputer_shared_i2c_tests PRIVATE ESP_PLATFORM)
target_include_directories(lmdj_cardputer_shared_i2c_tests PRIVATE
  "${CMAKE_CURRENT_SOURCE_DIR}/fake_esp" "${CMAKE_SOURCE_DIR}")
lmdj_target_warnings(lmdj_cardputer_shared_i2c_tests)
lmdj_target_sanitizers(lmdj_cardputer_shared_i2c_tests)
foreach(scenario restart partial retry owned)
  lmdj_add_test(NAME platform.cardputer.i2c.${scenario} TIER component
    COMMAND lmdj_cardputer_shared_i2c_tests ${scenario})
endforeach()
add_executable(lmdj_cardputer_status_payload_tests status_payload_test.cpp)
target_link_libraries(lmdj_cardputer_status_payload_tests PRIVATE lmdj::runtime_facade)
target_include_directories(lmdj_cardputer_status_payload_tests PRIVATE "${CMAKE_SOURCE_DIR}")
lmdj_target_warnings(lmdj_cardputer_status_payload_tests)
lmdj_target_sanitizers(lmdj_cardputer_status_payload_tests)
lmdj_add_test(NAME platform.cardputer.status_payload TIER component
  COMMAND lmdj_cardputer_status_payload_tests)

# Proposal-only observation codec vectors. This target intentionally excludes
# the active ESP component and does not register opcodes or alter Contract
# identities until the independent byte-table review is complete.
add_executable(lmdj_cardputer_observation_wire_tests observation_wire_test.cpp)
target_include_directories(lmdj_cardputer_observation_wire_tests PRIVATE "${CMAKE_SOURCE_DIR}")
lmdj_target_warnings(lmdj_cardputer_observation_wire_tests)
lmdj_target_sanitizers(lmdj_cardputer_observation_wire_tests)
foreach(scenario valid invalid decode diagnostics unavailable escape)
  lmdj_add_test(NAME platform.cardputer.observation_wire.${scenario} TIER component
    COMMAND lmdj_cardputer_observation_wire_tests ${scenario})
endforeach()

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

add_executable(lmdj_cardputer_input_tests
  input_controller_test.cpp
  "${CMAKE_SOURCE_DIR}/apps/cardputer-host/main/keyboard.cpp"
  "${CMAKE_SOURCE_DIR}/apps/cardputer-host/main/display.cpp"
  "${CMAKE_SOURCE_DIR}/apps/cardputer-host/main/input_controller.cpp"
  "${CMAKE_SOURCE_DIR}/apps/cardputer-host/main/runtime_host.cpp")
target_link_libraries(lmdj_cardputer_input_tests PRIVATE lmdj::runtime_facade Threads::Threads)
target_include_directories(lmdj_cardputer_input_tests PRIVATE "${CMAKE_SOURCE_DIR}")
lmdj_target_warnings(lmdj_cardputer_input_tests)
lmdj_target_sanitizers(lmdj_cardputer_input_tests)
foreach(scenario mapping repeat_release empty_receive overflow queue_retry display
    feedback_receipt feedback_stop feedback_release feedback_restart feedback_wrap)
  lmdj_add_test(NAME platform.cardputer.input.${scenario} TIER component
    COMMAND lmdj_cardputer_input_tests ${scenario})
endforeach()

add_executable(lmdj_cardputer_transfer_tests
  transfer_test.cpp
  "${CMAKE_SOURCE_DIR}/apps/cardputer-host/main/transfer.cpp")
target_link_libraries(lmdj_cardputer_transfer_tests PRIVATE Threads::Threads)
target_include_directories(lmdj_cardputer_transfer_tests PRIVATE "${CMAKE_SOURCE_DIR}")
lmdj_target_warnings(lmdj_cardputer_transfer_tests)
lmdj_target_sanitizers(lmdj_cardputer_transfer_tests)
foreach(scenario crc roundtrip limits malformed resync)
  lmdj_add_test(NAME platform.cardputer.transfer.${scenario} TIER component
    COMMAND lmdj_cardputer_transfer_tests ${scenario})
endforeach()

add_executable(lmdj_cardputer_transfer_transaction_tests
  transfer_transaction_test.cpp
  "${CMAKE_SOURCE_DIR}/apps/cardputer-host/main/transfer.cpp"
  "${CMAKE_SOURCE_DIR}/apps/cardputer-host/main/transfer_transaction.cpp")
target_link_libraries(lmdj_cardputer_transfer_transaction_tests PRIVATE Threads::Threads)
target_include_directories(lmdj_cardputer_transfer_transaction_tests PRIVATE
  "${CMAKE_SOURCE_DIR}" "${CMAKE_SOURCE_DIR}/third_party/picosha2")
lmdj_target_warnings(lmdj_cardputer_transfer_transaction_tests)
lmdj_target_sanitizers(lmdj_cardputer_transfer_transaction_tests)
foreach(scenario happy reject_identity disconnect)
  lmdj_add_test(NAME platform.cardputer.transfer_transaction.${scenario} TIER component
    COMMAND lmdj_cardputer_transfer_transaction_tests ${scenario})
endforeach()

add_executable(lmdj_cardputer_transfer_hash_memory_tests
  transfer_hash_memory_test.cpp
  "${CMAKE_SOURCE_DIR}/apps/cardputer-host/main/transfer_transaction.cpp"
  "${CMAKE_SOURCE_DIR}/apps/cardputer-host/main/transfer_session.cpp")
target_include_directories(lmdj_cardputer_transfer_hash_memory_tests PRIVATE
  "${CMAKE_SOURCE_DIR}" "${CMAKE_SOURCE_DIR}/third_party/picosha2")
lmdj_target_warnings(lmdj_cardputer_transfer_hash_memory_tests)
lmdj_target_sanitizers(lmdj_cardputer_transfer_hash_memory_tests)
foreach(scenario bounded corrupt allocation_failure session_allocation_failure)
  lmdj_add_test(NAME platform.cardputer.transfer_hash_memory.${scenario} TIER component
    COMMAND lmdj_cardputer_transfer_hash_memory_tests ${scenario})
endforeach()

add_executable(lmdj_cardputer_transfer_session_tests
  transfer_session_test.cpp
  "${CMAKE_SOURCE_DIR}/apps/cardputer-host/main/transfer.cpp"
  "${CMAKE_SOURCE_DIR}/apps/cardputer-host/main/transfer_transaction.cpp"
  "${CMAKE_SOURCE_DIR}/apps/cardputer-host/main/transfer_session.cpp")
target_link_libraries(lmdj_cardputer_transfer_session_tests PRIVATE Threads::Threads)
target_include_directories(lmdj_cardputer_transfer_session_tests PRIVATE
  "${CMAKE_SOURCE_DIR}" "${CMAKE_SOURCE_DIR}/third_party/picosha2")
lmdj_target_warnings(lmdj_cardputer_transfer_session_tests)
lmdj_target_sanitizers(lmdj_cardputer_transfer_session_tests)
lmdj_add_test(NAME platform.cardputer.transfer_session.lifecycle TIER component
  COMMAND lmdj_cardputer_transfer_session_tests lifecycle)
lmdj_add_test(NAME platform.cardputer.transfer_session.stale TIER component
  COMMAND lmdj_cardputer_transfer_session_tests stale)