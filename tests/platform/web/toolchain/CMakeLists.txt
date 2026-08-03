cmake_minimum_required(VERSION 3.24)

project(lmdj_web_toolchain_conformance LANGUAGES CXX)

if(NOT EMSCRIPTEN)
  message(FATAL_ERROR "Web toolchain conformance requires Emscripten")
endif()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(probe_audio_callback OBJECT probe.cpp)
target_compile_definitions(probe_audio_callback PRIVATE LMDJ_PROBE_AUDIO_CALLBACK=1)
target_compile_options(
  probe_audio_callback
  PRIVATE
    -pthread
    -Wall
    -Wextra
    -Werror
    -Wno-unused-parameter
)

add_library(probe_control OBJECT probe.cpp)
target_compile_definitions(probe_control PRIVATE LMDJ_PROBE_CONTROL=1)
target_compile_options(
  probe_control
  PRIVATE
    -pthread
    -Wall
    -Wextra
    -Werror
    -Wno-unused-parameter
)

add_executable(
  probe
  $<TARGET_OBJECTS:probe_audio_callback>
  $<TARGET_OBJECTS:probe_control>
)

target_link_options(
  probe
  PRIVATE
    -pthread
    -sWASMFS
    -sAUDIO_WORKLET
    -sWASM_WORKERS
    -sPROXY_TO_PTHREAD
    -sINITIAL_MEMORY=536870912
    -sALLOW_MEMORY_GROWTH=0
    -sASYNCIFY=1
    "-sASYNCIFY_IMPORTS=['lmdj_opfs_acquire_writer','lmdj_opfs_replace_complete','lmdj_opfs_list_names']"
    "--pre-js=${CMAKE_CURRENT_SOURCE_DIR}/probe-pre.js"
    "-sEXPORTED_FUNCTIONS=['_main','_lmdj_start_audio_probe','_lmdj_get_audio_context','_lmdj_get_audio_state','_lmdj_get_audio_ready','_lmdj_get_configured_channels','_lmdj_get_control_browser_main','_lmdj_get_control_done','_lmdj_get_control_probes','_lmdj_get_observed_frames','_lmdj_get_shared_marker','_lmdj_get_quantum_mismatch','_lmdj_get_observed_sample_rate','_lmdj_observe_quantum_for_test','_lmdj_get_wasmfs_ok','_lmdj_get_lease_json','_lmdj_get_iteration_json','_lmdj_get_replacement_json']"
    "-sEXPORTED_RUNTIME_METHODS=['UTF8ToString']"
    -sEXIT_RUNTIME=0
    -sASSERTIONS=1
    -sENVIRONMENT=web,worker
)

get_filename_component(TOOLCHAIN_OUTPUT_DIR "${CMAKE_BINARY_DIR}" DIRECTORY)
set_target_properties(
  probe
  PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${TOOLCHAIN_OUTPUT_DIR}"
    OUTPUT_NAME probe
    SUFFIX ".js"
)

configure_file(
  "${CMAKE_CURRENT_SOURCE_DIR}/probe.html"
  "${TOOLCHAIN_OUTPUT_DIR}/probe.html"
  COPYONLY
)
