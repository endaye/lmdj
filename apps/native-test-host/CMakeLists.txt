add_executable(
  lmdj_native_host
  src/main.cpp
  src/capture_writer.cpp
)
set_target_properties(
  lmdj_native_host
  PROPERTIES OUTPUT_NAME lmdj-native-host
)
target_link_libraries(
  lmdj_native_host
  PRIVATE
    lmdj::application
    lmdj::audio_runtime
)
if(APPLE)
  target_link_libraries(
    lmdj_native_host PRIVATE lmdj::audio_coreaudio
  )
endif()
file(
  GENERATE
  OUTPUT
    "${CMAKE_CURRENT_BINARY_DIR}/lmdj_native_host.link-libraries.txt"
  CONTENT
    "$<TARGET_PROPERTY:lmdj_native_host,LINK_LIBRARIES>\n"
)
lmdj_target_warnings(lmdj_native_host)
lmdj_target_sanitizers(lmdj_native_host)

if(BUILD_TESTING)
  lmdj_add_test(
    NAME host.native_source_boundary
    TIER contract
    COMMAND
      "${Python3_EXECUTABLE}"
      "${CMAKE_SOURCE_DIR}/tests/host/native_host_source_boundary_test.py"
      "${CMAKE_CURRENT_SOURCE_DIR}"
      "${CMAKE_CURRENT_BINARY_DIR}/lmdj_native_host.link-libraries.txt"
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  )
  lmdj_add_test(
    NAME host.native
    TIER host
    COMMAND
      "${Python3_EXECUTABLE}"
      "${CMAKE_SOURCE_DIR}/tests/host/native_host_test.py"
      "$<TARGET_FILE:lmdj_native_host>"
      "$<TARGET_FILE:lmdj_core_cli>"
      "${CMAKE_SOURCE_DIR}/products/lmdj/assembly.json"
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    TIMEOUT 120
  )
endif()
