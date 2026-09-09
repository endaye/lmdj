set(lmdj_slice_package_files
  include/lmdj/providers/local_sample_slice/factory.hpp
  include/lmdj/providers/local_sample_slice/validation.hpp
  module.json
  src/provider.cpp
  src/validation.cpp
)
set(lmdj_slice_entries "")
foreach(relative IN LISTS lmdj_slice_package_files)
  set(absolute "${CMAKE_CURRENT_SOURCE_DIR}/${relative}")
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${absolute}")
  file(SHA256 "${absolute}" digest)
  list(APPEND lmdj_slice_entries "{\"path\":\"providers/local-sample-slice/${relative}\",\"sha256\":\"${digest}\"}")
endforeach()
list(JOIN lmdj_slice_entries "," lmdj_slice_files_json)
set(lmdj_slice_manifest "{\"files\":[${lmdj_slice_files_json}],\"format\":\"provider-source-package\",\"provider_id\":\"local.sample.slice\",\"provider_version\":\"1.0.0\"}\n")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/local.sample.slice.source-package.json" "${lmdj_slice_manifest}")
string(SHA256 lmdj_slice_package_sha256 "${lmdj_slice_manifest}")

add_library(lmdj_provider_local_sample_slice STATIC src/provider.cpp src/validation.cpp)
target_include_directories(lmdj_provider_local_sample_slice PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_link_libraries(lmdj_provider_local_sample_slice PUBLIC lmdj::provider_sdk)
target_compile_definitions(lmdj_provider_local_sample_slice PRIVATE
  LMDJ_LOCAL_SAMPLE_SLICE_SOURCE_PACKAGE_SHA256="${lmdj_slice_package_sha256}")
lmdj_target_warnings(lmdj_provider_local_sample_slice)
lmdj_target_sanitizers(lmdj_provider_local_sample_slice)
