add_library(
  lmdj_web_control_runtime
  STATIC
    src/control_runtime.cpp
)
add_library(lmdj::web_control_runtime ALIAS lmdj_web_control_runtime)
target_include_directories(
  lmdj_web_control_runtime
  PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/src"
)
target_link_libraries(
  lmdj_web_control_runtime
  PUBLIC
    lmdj::application
    lmdj::audio_runtime
  PRIVATE
    lmdj_picosha2
)
lmdj_target_warnings(lmdj_web_control_runtime)
lmdj_target_sanitizers(lmdj_web_control_runtime)

if(EMSCRIPTEN)
  add_executable(
    lmdj_web_runtime_host
    src/bridge.cpp
  )
  target_link_libraries(
    lmdj_web_runtime_host
    PRIVATE
      lmdj::web_control_runtime
  )
  target_link_options(
    lmdj_web_runtime_host
    PRIVATE
      -pthread
      -sWASMFS
      -sAUDIO_WORKLET
      -sWASM_WORKERS
      -sPROXY_TO_PTHREAD
      -sINITIAL_MEMORY=536870912
      -sALLOW_MEMORY_GROWTH=0
      -sEXIT_RUNTIME=0
      -sENVIRONMENT=web,worker
      -sEXPORTED_FUNCTIONS=_main,_lmdj_web_host_submit,_lmdj_web_host_poll,_lmdj_web_host_failed
      -sEXPORTED_RUNTIME_METHODS=ccall
  )
  set_target_properties(
    lmdj_web_runtime_host
    PROPERTIES OUTPUT_NAME lmdj-web-runtime-host
  )
  file(
    GENERATE
    OUTPUT
      "${CMAKE_CURRENT_BINARY_DIR}/lmdj_web_runtime_host.link-libraries.txt"
    CONTENT
      "$<TARGET_PROPERTY:lmdj_web_runtime_host,LINK_LIBRARIES>\n"
  )
  lmdj_target_warnings(lmdj_web_runtime_host)
endif()

if(BUILD_TESTING AND NOT EMSCRIPTEN)
  find_package(Threads REQUIRED)
  add_executable(
    lmdj_web_control_runtime_tests
    test/control_runtime_test.cpp
    src/bridge.cpp
  )
  target_include_directories(
    lmdj_web_control_runtime_tests
    PRIVATE
      "${CMAKE_CURRENT_SOURCE_DIR}/src"
      "${CMAKE_SOURCE_DIR}"
  )
  target_link_libraries(
    lmdj_web_control_runtime_tests
    PRIVATE
      lmdj::web_control_runtime
      lmdj_picosha2
      Threads::Threads
  )
  lmdj_target_warnings(lmdj_web_control_runtime_tests)
  lmdj_target_sanitizers(lmdj_web_control_runtime_tests)
  lmdj_add_test(
    NAME host.web_control_runtime
    TIER host
    COMMAND lmdj_web_control_runtime_tests
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    LABELS audio concurrency
  )
  lmdj_add_test(
    NAME host.web_source_boundary
    TIER contract
    COMMAND
      "${Python3_EXECUTABLE}"
      "${CMAKE_CURRENT_SOURCE_DIR}/test/web_host_source_boundary_test.py"
      "${CMAKE_CURRENT_SOURCE_DIR}"
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  )
endif()
