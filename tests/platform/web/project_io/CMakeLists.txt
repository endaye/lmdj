cmake_minimum_required(VERSION 3.24)

project(lmdj_project_io_web_conformance LANGUAGES CXX)

if(NOT EMSCRIPTEN)
  message(FATAL_ERROR "Web Project I/O conformance requires Emscripten")
endif()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
add_compile_options(-pthread)

get_filename_component(LMDJ_REPO_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../../.." ABSOLUTE)
set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/..")
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib")

include(FetchContent)
include("${LMDJ_REPO_ROOT}/cmake/LmdjDependencies.cmake")
include("${LMDJ_REPO_ROOT}/cmake/LmdjWarnings.cmake")
include("${LMDJ_REPO_ROOT}/cmake/LmdjCoverage.cmake")
add_subdirectory("${LMDJ_REPO_ROOT}/packages/foundation" foundation)
add_subdirectory("${LMDJ_REPO_ROOT}/packages/authoring-domain" authoring-domain)
set(LMDJ_PROJECT_IO_WEB_TESTING ON)
add_subdirectory("${LMDJ_REPO_ROOT}/packages/project-io" project-io)
target_compile_definitions(lmdj_project_io PRIVATE LMDJ_PROJECT_IO_TESTING=1)

add_executable(project_io_web_test project_io_web_test.cpp)
target_link_libraries(project_io_web_test PRIVATE lmdj::project_io)
target_compile_options(
  project_io_web_test
  PRIVATE
    -pthread
    -Wall
    -Wextra
    -Werror
)
target_link_options(
  project_io_web_test
  PRIVATE
    -pthread
    -sWASMFS
    -sPROXY_TO_PTHREAD
    # The parity journey synchronously joins two concurrent append workers.
    # Prewarm both so worker-script loading cannot block the proxied main.
    -sPTHREAD_POOL_SIZE=2
    -sINITIAL_MEMORY=536870912
    -sALLOW_MEMORY_GROWTH=0
    -sASYNCIFY=1
    -sEXIT_RUNTIME=0
    -sASSERTIONS=1
    -sENVIRONMENT=web,worker
    -sEXPORTED_RUNTIME_METHODS=UTF8ToString
)
set_target_properties(
  project_io_web_test
  PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/.."
    OUTPUT_NAME project_io_web_test
    SUFFIX ".html"
)

file(
  GENERATE
  OUTPUT "${CMAKE_BINARY_DIR}/project_io_web_production_link.cpp"
  CONTENT [=[
#include <memory>
#include <lmdj/project_io/storage_platform.hpp>
namespace lmdj::project_io {
std::shared_ptr<ProjectStoragePlatform> make_web_project_storage_platform();
}
int main() {
  return lmdj::project_io::make_web_project_storage_platform() == nullptr ? 1 : 0;
}
]=]
)
add_executable(
  project_io_web_production_link
  "${CMAKE_BINARY_DIR}/project_io_web_production_link.cpp"
  "${LMDJ_REPO_ROOT}/packages/project-io/src/web/storage_platform.cpp"
)
target_include_directories(
  project_io_web_production_link
  PRIVATE
    "${LMDJ_REPO_ROOT}/packages/project-io/include"
)
target_link_libraries(project_io_web_production_link PRIVATE lmdj::foundation)
target_link_options(
  project_io_web_production_link
  PRIVATE
    "--js-library=${LMDJ_REPO_ROOT}/packages/project-io/src/web/library_opfs_storage.js"
    -sASYNCIFY=1
    "-sASYNCIFY_IMPORTS=['lmdj_opfs_acquire_writer','lmdj_opfs_ensure_directory','lmdj_opfs_exists','lmdj_opfs_directory_exists','lmdj_opfs_byte_length','lmdj_opfs_read_complete','lmdj_opfs_create_immutable','lmdj_opfs_replace_complete','lmdj_opfs_append_durable','lmdj_opfs_remove','lmdj_opfs_list_names','lmdj_opfs_list_directories','lmdj_opfs_remove_tree','lmdj_opfs_publish_directory_if_absent','lmdj_opfs_validate_tree']"
    -sWASMFS
)
set_target_properties(
  project_io_web_production_link
  PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/.."
    LINK_DEPENDS
      "${LMDJ_REPO_ROOT}/packages/project-io/src/web/library_opfs_storage.js"
)
